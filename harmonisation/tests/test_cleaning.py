"""Tests der Bereinigung: statische Quellen, NRT ohne type, Duplikate, unlesbare Werte, gedroppte Spalten, Zeilenbilanz."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from helpers import make_raw_hotspots
from pipeline.column_catalogue import columns_of
from pipeline.data_loading import clean_hotspots
from pipeline.data_loading.ingest_csv_to_parquet import convert_csv_to_raw_parquet, count_unreadable_rows
from pipeline.data_loading.static_source_mask import learn_static_mask, learn_static_masks
from pipeline.io_utils import read_parquet
from pipeline.config import path_of

STATIC_SITE = {"latitude": 39.4712, "longitude": -0.3251}


def build_archive_with_static_site(config: dict[str, Any]) -> pd.DataFrame:
    """Archivzeilen: vier statische Erkennungen an einem Ort und ein echtes Feuer anderswo."""
    static_rows = [{**STATIC_SITE, "type": 2, "acq_date": f"2016-0{month}-10"} for month in range(1, 5)]
    return make_raw_hotspots(static_rows + [{"latitude": 41.0, "longitude": -7.0, "type": 0}], config)


def test_nrt_rows_without_type_survive_static_filter(config: dict[str, Any]) -> None:
    """Der NULL-Fall: NRT-Zeilen ohne `type` duerfen nicht pauschal verschwinden."""
    archive = build_archive_with_static_site(config)
    nrt = make_raw_hotspots([{"latitude": 42.5, "longitude": -6.0, "type": None, "source": "nrt"},
                             {"latitude": 37.9, "longitude": -5.1, "type": None, "source": "nrt"}], config)
    kept, rejected = clean_hotspots.filter_static_sources(pd.concat([archive, nrt], ignore_index=True), learn_static_masks(archive, config), config)
    assert (kept["source"] == "nrt").sum() == 2
    assert (rejected["reject_reason"] == "type_2").sum() == 4


def test_mask_rejects_nrt_rows_at_static_site(config: dict[str, Any]) -> None:
    """Eine NRT-Zeile am Ort einer bekannten statischen Quelle wird ueber die Maske verworfen."""
    archive = build_archive_with_static_site(config)
    nrt = make_raw_hotspots([{**STATIC_SITE, "type": None, "source": "nrt"}], config)
    kept, rejected = clean_hotspots.filter_static_sources(nrt, learn_static_masks(archive, config), config)
    assert kept.empty and list(rejected["reject_reason"]) == ["static_mask"]


def test_mask_is_learned_only_from_typed_rows(config: dict[str, Any]) -> None:
    """Ein Ort mit zu wenigen statischen Erkennungen wird keine Kernzelle."""
    rows = make_raw_hotspots([{**STATIC_SITE, "type": 2}, {**STATIC_SITE, "type": 2, "acq_date": "2016-02-01"}], config)
    assert learn_static_mask(rows, config).empty


def test_all_static_types_are_rejected(config: dict[str, Any]) -> None:
    """type 1, 2 und 3 werden verworfen, nur type 0 bleibt."""
    rows = make_raw_hotspots([{"type": 0}, {"type": 1}, {"type": 2}, {"type": 3}], config)
    kept, rejected = clean_hotspots.filter_static_sources(rows, learn_static_masks(rows, config), config)
    assert len(kept) == 1 and sorted(rejected["reject_reason"]) == ["type_1", "type_2", "type_3"]


def test_deduplication_prefers_archive(config: dict[str, Any]) -> None:
    """Gleiche Messung in Archiv und NRT: das Archiv bleibt. Andere Uhrzeit ist kein Duplikat."""
    rows = make_raw_hotspots([{"source": "nrt", "type": None}, {"source": "archive"},
                              {"source": "archive", "acq_time": "1440"}, {"satellite": "Terra"}], config)
    kept, rejected = clean_hotspots.deduplicate_hotspots(rows, config)
    assert len(kept) == 3 and list(rejected["source"]) == ["nrt"]


def test_invalid_rows_are_rejected(config: dict[str, Any]) -> None:
    """Unmoegliche Koordinaten, negative FRP, unbekannte Satelliten und fehlende Pflichtwerte werden verworfen."""
    rows = make_raw_hotspots([{}, {"latitude": 95.0}, {"frp": -1.0}, {"satellite": "Unbekannt"}, {"track": None}], config)
    kept, rejected = clean_hotspots.reject_invalid_rows(rows, config)
    assert len(kept) == 1 and len(rejected) == 4


def test_unreadable_csv_value_does_not_stop_the_pipeline(config: dict[str, Any], tmp_path: Path) -> None:
    """Eingefuegter Text in einer Zahl bricht das Einlesen nicht ab: Der Wert wird leer und die Zeile gezaehlt."""
    csv = tmp_path / "broken.csv"
    csv.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type\n"
                   "42.7,-6.7,342.8,0.75,0.https://example.org/x77,2026-07-31,1443,SNPP,SNPP,n,2,305.5,10.8,D,0\n"
                   "42.8,-6.8,340.0,0.75,0.77,2026-07-31,1443,SNPP,SNPP,n,2,305.5,10.8,D,0\n", encoding="utf-8")
    target = tmp_path / "broken.parquet"
    assert convert_csv_to_raw_parquet(str(csv), target) == 2 and count_unreadable_rows(target) == 1


def test_dropped_columns_are_absent_and_schema_holds(fixture_run: dict[str, Any]) -> None:
    """Die bereinigte Tabelle hat genau das vereinbarte Schema und keine gedroppte Spalte."""
    fixture_config = fixture_run["config"]
    clean = read_parquet(path_of(fixture_config, "processed", "hotspots_clean.parquet"))
    dropped = sum(fixture_config["columns"].values(), []) + ["static_filter_basis"]
    assert list(clean.columns) == columns_of("hotspots_clean")
    assert not set(dropped) & set(clean.columns)


def test_row_balance_adds_up(fixture_run: dict[str, Any]) -> None:
    """Gelesen = behalten + verworfen, und jede verworfene Zeile hat einen Grund."""
    fixture_config = fixture_run["config"]
    balance = fixture_run["state"]["clean"]["report"]
    rejected = read_parquet(path_of(fixture_config, "processed", "rejected_hotspots.parquet"))
    assert balance["balanced"] and balance["rows_read"] == balance["rows_kept"] + balance["rows_rejected"]
    assert rejected["reject_reason"].notna().all()
    assert {"brightness", "type"} <= set(rejected.columns)


def test_nrt_rows_reach_the_clean_table(fixture_run: dict[str, Any]) -> None:
    """Im Gesamtlauf kommen NRT-Zeilen beider Sensoren in der bereinigten Tabelle an."""
    clean = read_parquet(path_of(fixture_run["config"], "processed", "hotspots_clean.parquet"))
    assert set(clean.loc[clean["source"] == "nrt", "sensor"]) == {"MODIS", "VIIRS"}


def test_mask_from_any_viirs_satellite_filters_noaa_nrt(config: dict[str, Any]) -> None:
    """NOAA-20-Archivzeilen mit type lehren die Maske; NOAA-21-NRT ohne type am selben Ort wird verworfen, anderswo behalten."""
    archive = make_raw_hotspots([{**STATIC_SITE, "type": 2, "satellite": "N20", "acq_date": f"2019-0{month}-10"} for month in range(1, 5)], config)
    nrt = make_raw_hotspots([{**STATIC_SITE, "type": None, "source": "nrt", "satellite": "N21"},
                             {"latitude": 41.0, "longitude": -7.0, "type": None, "source": "nrt", "satellite": "N21"}], config)
    kept, rejected = clean_hotspots.filter_static_sources(nrt, learn_static_masks(archive, config), config)
    assert list(kept["latitude"]) == [41.0] and list(rejected["reject_reason"]) == ["static_mask"]
    assert set(nrt["sensor"]) == {"VIIRS"}


def test_noaa_rows_outside_common_area_are_rejected(config: dict[str, Any]) -> None:
    """Das gemeinsame Gebiet lernt nur aus Terra, Aqua und SNPP. NOAA-Punkte ausserhalb fallen mit Grund heraus, innerhalb bleiben sie."""
    from pipeline.data_loading.common_area import learn_common_area
    rows = make_raw_hotspots([{"satellite": "SNPP", "latitude": 40.1, "longitude": -3.6}, {"satellite": "Aqua", "latitude": 41.1, "longitude": -5.1},
                              {"satellite": "N20", "latitude": 40.2, "longitude": -3.7}, {"satellite": "N21", "latitude": 44.5, "longitude": 1.0},
                              {"satellite": "N20", "latitude": 44.5, "longitude": 1.0}], config)
    kept, rejected = clean_hotspots.restrict_to_common_area(rows, learn_common_area(rows, config), config)
    assert kept["satellite"].tolist() == ["SNPP", "Aqua", "N20"]
    assert rejected["satellite"].tolist() == ["N21", "N20"] and set(rejected["reject_reason"]) == {"outside_common_area"}


def test_viirs_mask_ignores_modis_static_rows(config: dict[str, Any]) -> None:
    """Iteration 1: Eine nur von MODIS gemeldete statische Quelle maskiert MODIS-NRT, aber keine VIIRS-NRT-Zeilen."""
    archive = make_raw_hotspots([{**STATIC_SITE, "type": 2, "satellite": "Aqua", "acq_date": f"2016-0{month}-10"} for month in range(1, 5)], config)
    nrt = make_raw_hotspots([{**STATIC_SITE, "type": None, "source": "nrt", "satellite": satellite} for satellite in ("Aqua", "SNPP", "N20")], config)
    kept, rejected = clean_hotspots.filter_static_sources(nrt, learn_static_masks(archive, config), config)
    assert rejected["satellite"].tolist() == ["Aqua"] and kept["satellite"].tolist() == ["SNPP", "N20"]
