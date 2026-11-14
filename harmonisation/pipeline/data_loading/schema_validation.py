"""Schema- und Plausibilitaetspruefungen nach jeder Stufe. Fehler brechen die Pipeline ab.

Die Spaltenlisten kommen aus `pipeline/column_catalogue.py`. Dieselbe Quelle erzeugt die
Dokumentation, Schema und Beschreibung koennen also nicht auseinanderlaufen.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.column_catalogue import columns_of

BASIS_VALUES = {"viirs_measured", "aqua_scaled", "modis_pair_scaled", "terra_scaled", "none"}


class SchemaError(ValueError):
    """Eine Tabelle verletzt ihr vereinbartes Schema."""


def require_columns(table: pd.DataFrame, table_name: str) -> None:
    """Bricht ab, wenn die Spalten nicht genau dem Katalog entsprechen (Namen und Reihenfolge)."""
    expected = columns_of(table_name)
    if list(table.columns) != expected:
        missing, extra = set(expected) - set(table.columns), set(table.columns) - set(expected)
        raise SchemaError(f"{table_name}: fehlend {sorted(missing)}, unerwartet {sorted(extra)}, oder falsche Reihenfolge")


def find_invalid_values(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Markiert Zeilen mit fehlenden Pflichtwerten oder Werten ausserhalb der erlaubten Bereiche."""
    ranges = config["validation_ranges"]
    dates = pd.to_datetime(hotspots["acq_date"])
    valid = (hotspots["latitude"].between(*ranges["latitude"])
             & hotspots["longitude"].between(*ranges["longitude"])
             & (hotspots["frp"] >= ranges["frp_min"])
             & dates.between(pd.Timestamp(ranges["date_min"]), pd.Timestamp(ranges["date_max"]))
             & (hotspots["scan"] > 0) & (hotspots["track"] > 0)
             & hotspots[["acq_time", "satellite", "daynight"]].notna().all(axis=1))
    return ~valid


def validate_clean_hotspots(hotspots: pd.DataFrame, config: dict[str, Any]) -> None:
    """Prueft `hotspots_clean`: Spalten, keine gedroppten Spalten, Wertebereiche, eindeutige IDs."""
    require_columns(hotspots, "hotspots_clean")
    dropped = sum(config["columns"].values(), [])
    if set(dropped) & set(hotspots.columns):
        raise SchemaError(f"hotspots_clean enthaelt gedroppte Spalten: {set(dropped) & set(hotspots.columns)}")
    if find_invalid_values(hotspots, config).any():
        raise SchemaError("hotspots_clean enthaelt Werte ausserhalb der erlaubten Bereiche")
    if hotspots["hotspot_id"].duplicated().any():
        raise SchemaError("hotspots_clean: hotspot_id ist nicht eindeutig")
    for column in ["satellite", "sensor", "source", "daynight", "frp_class", "obs_date", "cell_id", "h3_cell"]:
        if hotspots[column].isna().any():
            raise SchemaError(f"hotspots_clean: {column} enthaelt NULL")


def validate_day_status(day_status: pd.DataFrame) -> None:
    """Prueft `day_status`: jedes Datum genau einmal und lueckenlos, nur erlaubte Basiswerte."""
    require_columns(day_status, "day_status")
    dates = pd.to_datetime(day_status["date"])
    expected = pd.date_range(dates.min(), dates.max(), freq="D")
    if len(dates) != len(expected) or not (dates.reset_index(drop=True) == pd.Series(expected)).all():
        raise SchemaError("day_status: Datumsreihe hat Luecken oder Doppelte")
    for column in ("basis_count", "basis_frp"):
        if not set(day_status[column].unique()) <= BASIS_VALUES:
            raise SchemaError(f"day_status: unbekannter Wert in {column}")


def validate_daily_harmonised(daily: pd.DataFrame) -> None:
    """Prueft `activity_daily_harmonised`: Spalten, Schluessel, Werte genau an vollstaendigen Tagen."""
    require_columns(daily, "activity_daily_harmonised")
    if daily.duplicated(["region_id", "date"]).any():
        raise SchemaError("activity_daily_harmonised: doppelte Schluessel")
    if daily.groupby("region_id").size().nunique() != 1:
        raise SchemaError("activity_daily_harmonised: Regionen haben unterschiedlich viele Tage")
    has_value = daily["basis_count"] != "none"
    if daily.loc[has_value, "n_harm"].isna().any() or daily.loc[~has_value, "n_harm"].notna().any():
        raise SchemaError("activity_daily_harmonised: n_harm muss genau an Tagen mit Basis gefuellt sein")
    if (daily["n_harm"].dropna() < 0).any() or (daily["frp_harm"].dropna() < 0).any():
        raise SchemaError("activity_daily_harmonised: negative Werte")
    ordered = (daily["n_harm_lo90"] <= daily["n_harm_lo50"]) & (daily["n_harm_lo50"] <= daily["n_harm"]) \
        & (daily["n_harm"] <= daily["n_harm_hi50"]) & (daily["n_harm_hi50"] <= daily["n_harm_hi90"])
    if not ordered[has_value].all():
        raise SchemaError("activity_daily_harmonised: Fehlerbaender sind nicht geordnet")


def validate_hotspots_harmonised(hotspots: pd.DataFrame) -> None:
    """Prueft `hotspots_harmonised`: Spalten, eindeutige IDs, Gewicht 0 genau ausserhalb der Reihe."""
    require_columns(hotspots, "hotspots_harmonised")
    if hotspots["hotspot_id"].duplicated().any():
        raise SchemaError("hotspots_harmonised: hotspot_id ist nicht eindeutig")
    for flag, weight in (("in_series_n", "weight_n"), ("in_series_frp", "weight_frp")):
        if ((hotspots[weight] > 0) != hotspots[flag]).any() or (hotspots[weight] < 0).any():
            raise SchemaError(f"hotspots_harmonised: {weight} passt nicht zu {flag}")
