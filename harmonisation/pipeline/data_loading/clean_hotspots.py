"""Stufe clean: Raw-Parquet bereinigen und anreichern -> data/processed/hotspots_clean.parquet.

Reihenfolge: laden -> ungueltige Werte verwerfen -> Duplikate entfernen -> Region zuordnen und auf die
Untersuchungsregionen beschraenken -> statische Quellen filtern -> Spalten ableiten -> Spalten droppen. Jede verworfene Zeile landet mit Grund in
rejected_hotspots.parquet, damit die Zeilenbilanz aufgeht. (Uebernommen aus Version 1 und erweitert.)
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.column_catalogue import columns_of
from pipeline.config import path_of
from pipeline.data_loading import derive_hotspot_columns as derive
from pipeline.data_loading import schema_validation
from pipeline.data_loading.assign_region import assign_nuts2_region
from pipeline.data_loading.classify_hotspots import add_confidence_class, add_frp_class, add_local_solar_hour
from pipeline.data_loading.ingest_csv_to_parquet import raw_parquet_path
from pipeline.data_loading.static_source_mask import flag_hotspots_in_masks, learn_static_masks, masks_as_table
from pipeline.io_utils import get_logger, read_parquet, write_parquet_deterministic

SORT_KEY = ["acq_date", "acq_time", "satellite", "latitude", "longitude"]


def load_raw_hotspots(config: dict[str, Any]) -> pd.DataFrame:
    """Liest alle Raw-Parquets und ergaenzt `sensor` (aus `satellite`) und `source` (archive / nrt).

    `sensor` kommt bewusst aus `satellite` und nicht aus `instrument`: In den SNPP-Dateien steht
    in `instrument` der Wert "SNPP" statt "VIIRS", die Spalte ist also nicht verlaesslich.
    """
    parts = [read_parquet(raw_parquet_path(config, source)).assign(source=source["source"]) for source in config["sources"]]
    hotspots = pd.concat(parts, ignore_index=True)
    hotspots["sensor"] = hotspots["satellite"].map(config["satellites"]["sensor_of"])
    return hotspots


def split_rejected(hotspots: pd.DataFrame, reject: pd.Series, reason: str | pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Teilt eine Tabelle in behaltene und verworfene Zeilen. Verworfene bekommen `reject_reason`."""
    rejected = hotspots[reject].copy()
    rejected["reject_reason"] = reason[reject] if isinstance(reason, pd.Series) else reason
    return hotspots[~reject].copy(), rejected


def reject_invalid_rows(hotspots: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Verwirft Zeilen mit unbekanntem Satelliten oder Werten ausserhalb der erlaubten Bereiche."""
    invalid = schema_validation.find_invalid_values(hotspots, config) | hotspots["sensor"].isna()
    return split_rejected(hotspots, invalid, "invalid_value")


def deduplicate_hotspots(hotspots: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Entfernt doppelte Erkennungen. Bei gleichem Schluessel gewinnt das Archiv vor dem NRT.

    Schluessel: Satellit, Koordinaten, Datum, Uhrzeit. Ein Duplikat entsteht, wenn sich Archiv-
    und NRT-Download zeitlich ueberlappen. Das Archiv ist die geprueftere Fassung.
    Bewusst NICHT entfernt werden Erkennungen verschiedener Satelliten am selben Ort und
    Erkennungen desselben Satelliten zu verschiedenen Uhrzeiten: Auf dieser Breite ueberlappen sich
    die VIIRS-Bildstreifen, ein Ort wird oft von zwei Ueberfluegen am Tag erfasst (29 % der
    Tag-Erkennungen von SNPP). Das sind echte Einzelbeobachtungen.
    """
    params = config["deduplication"]
    priority = hotspots["source"].map({name: rank for rank, name in enumerate(params["source_priority"])})
    ordered = hotspots.assign(_priority=priority).sort_values("_priority", kind="mergesort")
    duplicate = ordered.duplicated(params["key"], keep="first").reindex(hotspots.index)
    return split_rejected(hotspots, duplicate, "duplicate")


def restrict_to_study_regions(hotspots: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ordnet die NUTS-2-Region zu und verwirft Erkennungen ausserhalb von `nuts.study_regions` (Grund `outside_study_regions`).

    Warum: Die Downloads decken verschiedene Gebiete ab. MODIS und SNPP reichen nach Frankreich bis etwa
    43,5 Grad Nord, NOAA-20/21 und die taegliche API (pipeline/ingestion/fetch_firms.py) sind groessere
    Rechtecke. Ohne Angleichung meldeten NOAA-20/21 Feuer, die SNPP und MODIS gar nicht sehen koennen
    (Voranalyse 09). Die Untersuchungsregionen (die Regionen der App) decken alle Downloads vollstaendig
    ab, dort zaehlen alle Satelliten gleich. Die Regionen sind fest vorgegeben statt aus Daten gelernt:
    Neue Downloads oder das taeglich wachsende NRT koennen das Gebiet nicht veraendern, und die Grenze ist
    die exakte Regionsgrenze statt eines Rasters. Verworfen werden Frankreich, offenes Meer und Inseln
    ausserhalb der Liste.
    """
    hotspots = assign_nuts2_region(hotspots, config)
    return split_rejected(hotspots, ~hotspots["region_id"].isin(config["nuts"]["study_regions"]), "outside_study_regions")


def filter_static_sources(hotspots: pd.DataFrame, masks: dict[str, pd.DataFrame], config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Behaelt nur Vegetationsfeuer. Archiv: ueber `type`. NRT (ohne `type`): ueber die Ortsmaske seines Sensors.

    Warum: Statische Quellen (Industrie, Fackeln, Plattformen) brennen das ganze Jahr und sind
    keine Feueraktivitaet. Sie verzerren ausserdem den Sensorvergleich: 32 % der naechtlichen
    SNPP-Erkennungen sind statisch, bei Aqua nur 4 %.
    Fallstrick: Im NRT ist `type` leer. Ein einfaches `type == 0` waere dort nie wahr und wuerde
    alle NRT-Zeilen loeschen. Darum werden Zeilen mit und ohne `type` getrennt behandelt.
    """
    params = config["static_sources"]
    has_type = hotspots["type"].notna()
    static_by_type = has_type & (hotspots["type"] != params["vegetation_fire_type"])
    in_mask = pd.Series(flag_hotspots_in_masks(hotspots, masks, params["mask_cell_deg"]), index=hotspots.index)
    reason = ("type_" + hotspots["type"].astype("Int64").astype("string")).where(has_type, "static_mask")
    return split_rejected(hotspots, static_by_type | (~has_type & in_mask), reason)


def drop_not_comparable_columns(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Droppt `brightness` und `bright_t31`.

    Grund: Die Helligkeit ist zwischen den Sensoren nicht vergleichbar. Der VIIRS-Kanal I-4
    saettigt bei 367 K (14 % der Tag-Erkennungen stehen genau auf diesem Wert), MODIS reicht bis
    ueber 500 K. Bei MODIS laesst sich die FRP zudem fast exakt aus der Helligkeit berechnen
    (R^2 0,97). Alle Intensitaetsaussagen kommen aus `frp`.
    """
    return hotspots.drop(columns=config["columns"]["drop_not_comparable"])


def drop_redundant_columns(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Droppt `instrument` und `version`.

    Grund: `instrument` ist uneinheitlich befuellt ("SNPP" statt "VIIRS") und durch `sensor`
    ersetzt. `version` beschreibt nur die Herkunft und ist durch `source` ersetzt.
    """
    return hotspots.drop(columns=config["columns"]["drop_redundant"])


def drop_type_after_filter(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Droppt `type`, nachdem der Filter gelaufen ist.

    Grund: Nach dem Filter ist `type` in jeder Archivzeile 0 und im NRT leer. Welche Regel
    gegriffen hat, ergibt sich aus `source` (archive: type, nrt: Ortsmaske).
    """
    return hotspots.drop(columns=config["columns"]["drop_after_filter"])


def enrich_hotspots(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt alle abgeleiteten Spalten und droppt die vereinbarten Spalten. Die Region steht schon seit `restrict_to_study_regions`."""
    hotspots = add_frp_class(hotspots, config)
    hotspots = add_confidence_class(hotspots, config)
    hotspots = add_local_solar_hour(hotspots)
    hotspots = derive.add_hotspot_id(hotspots, config)
    hotspots = derive.add_acquisition_datetime(hotspots)
    hotspots = derive.add_observation_date(hotspots, config)
    hotspots = derive.add_cell_id(hotspots, config)
    hotspots = derive.add_h3_cell(hotspots, config)
    hotspots = derive.add_pixel_area(hotspots)
    hotspots = drop_not_comparable_columns(hotspots, config)
    hotspots = drop_redundant_columns(hotspots, config)
    hotspots = drop_type_after_filter(hotspots, config)
    return hotspots[columns_of("hotspots_clean")]


def clean_all_hotspots(config: dict[str, Any]) -> dict[str, Any]:
    """Fuehrt die ganze Bereinigung aus, schreibt die Tabellen und gibt die Zeilenbilanz zurueck."""
    raw = load_raw_hotspots(config)
    valid, rejected_invalid = reject_invalid_rows(raw, config)
    unique, rejected_duplicates = deduplicate_hotspots(valid, config)
    inside, rejected_area = restrict_to_study_regions(unique, config)
    masks = learn_static_masks(inside[inside["type"].notna()], config)
    fires, rejected_static = filter_static_sources(inside, masks, config)
    mask = masks_as_table(masks)
    clean = enrich_hotspots(fires, config)
    schema_validation.validate_clean_hotspots(clean, config)
    rejected = pd.concat([rejected_invalid, rejected_duplicates, rejected_area, rejected_static], ignore_index=True)
    write_parquet_deterministic(clean, path_of(config, "processed", "hotspots_clean.parquet"), SORT_KEY, ("acq_date", "obs_date"))
    write_parquet_deterministic(rejected, path_of(config, "processed", "rejected_hotspots.parquet"), SORT_KEY + ["source"], ("acq_date",))
    write_parquet_deterministic(mask, path_of(config, "processed", "static_mask.parquet"))
    balance = {"rows_read": len(raw), "rows_kept": len(clean), "rows_rejected": len(rejected),
               "rejected_by_reason": rejected["reject_reason"].value_counts().sort_index().to_dict(),
               "mask_core_cells": int(mask["is_core"].sum()), "balanced": len(raw) == len(clean) + len(rejected)}
    get_logger().info("clean    gelesen %d = behalten %d + verworfen %d  (%s)", balance["rows_read"], balance["rows_kept"],
                      balance["rows_rejected"], "Bilanz ok" if balance["balanced"] else "BILANZ FALSCH")
    return balance


def masks_from_table(mask: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Umkehrung von `masks_as_table`: die gespeicherte Maske wieder je Sensor."""
    return {sensor: cells.drop(columns="sensor").reset_index(drop=True) for sensor, cells in mask.groupby("sensor")}


def clean_hotspots_since(config: dict[str, Any], since: pd.Timestamp) -> int:
    """Bereinigt nur die Tage ab `since` neu und ersetzt sie in hotspots_clean (Sync der App).

    Gleiche Schritte wie `clean_all_hotspots`, aber mit der gespeicherten Ortsmaske: Sie lernt nur aus dem
    Archiv und aendert sich durch neue NRT-Zeilen nicht. Alle Schritte wirken je Zeile oder je Tag, darum
    ergibt das Fenster dieselben Zeilen wie ein voller Lauf. `obs_date` liegt nie nach `acq_date`
    (Tageswechsel 6 Uhr Sonnenzeit), also reichen die Rohzeilen ab `since`.
    rejected_hotspots.parquet bleibt beim Stand des letzten vollen Laufs.
    """
    raw = load_raw_hotspots(config)
    raw = raw[pd.to_datetime(raw["acq_date"]) >= since]
    valid, _ = reject_invalid_rows(raw, config)
    unique, _ = deduplicate_hotspots(valid, config)
    inside, _ = restrict_to_study_regions(unique, config)
    masks = masks_from_table(read_parquet(path_of(config, "processed", "static_mask.parquet")))
    fires, _ = filter_static_sources(inside, masks, config)
    new = enrich_hotspots(fires, config)
    new = new[new["obs_date"] >= since]
    path = path_of(config, "processed", "hotspots_clean.parquet")
    old = read_parquet(path)
    clean = pd.concat([old[old["obs_date"] < since], new], ignore_index=True)
    schema_validation.validate_clean_hotspots(clean, config)
    write_parquet_deterministic(clean, path, SORT_KEY, ("acq_date", "obs_date"))
    get_logger().info("clean    ab %s: %d Punkte neu bereinigt, %d insgesamt", since.date(), len(new), len(clean))
    return len(new)
