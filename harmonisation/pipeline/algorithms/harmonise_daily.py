"""Harmonisierung auf Tagesebene: VIIRS gemessen, sonst MODIS umgerechnet. Dazu Staerkeklasse und Grossfeuer-Tag."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pipeline.algorithms.calibration_factors import predict_viirs_equivalent
from pipeline.algorithms.daily_grid import BASIS_AQUA, BASIS_NONE, BASIS_PAIR, BASIS_TERRA, BASIS_VIIRS
from pipeline.config import satellite_key

VARIANT_OF_BASIS = {BASIS_PAIR: "pair", BASIS_AQUA: "aqua", BASIS_TERRA: "terra"}


def pick_value_by_basis(scaled: pd.DataFrame, basis: pd.Series, measure: str, kind: str) -> tuple[pd.Series, pd.Series]:
    """Waehlt je Zeile Wert und Faktor passend zur Basis: gemessen (Faktor 1) oder umgerechnet."""
    value = pd.Series(np.nan, index=scaled.index)
    factor = pd.Series(np.nan, index=scaled.index)
    measured = basis == BASIS_VIIRS
    value[measured], factor[measured] = scaled.loc[measured, f"{measure}_viirs"], 1.0
    for name, variant in VARIANT_OF_BASIS.items():
        rows = basis == name
        value[rows] = scaled.loc[rows, f"pred_{measure}_{variant}"]
        factor[rows] = scaled.loc[rows, f"k_{kind}_{variant}"]
    return value, factor


def raw_value_columns(config: dict[str, Any]) -> list[str]:
    """Rohspalten der Tagestabelle in fester Reihenfolge: je Satellit, dann die VIIRS-Referenz (erst n_*, dann frp_*)."""
    keys = [satellite_key(config, satellite) for satellite in config["satellites"]["modis_pair"] + config["satellites"]["viirs"]]
    return [f"{measure}_{key}" for measure in ("n", "frp") for key in keys + ["viirs"]]


def harmonise_daily_activity(grid: pd.DataFrame, day_status: pd.DataFrame, factors: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Erzeugt je Region und Tag die harmonisierten Werte in VIIRS-Aequivalenten.

    `n_harm` und `frp_harm` sind je nach Basis des Tages der gemessene VIIRS-Wert (das Mittel der
    aktiven VIIRS-Satelliten, `n_viirs`) oder die mit dem
    Faktor umgerechnete MODIS-Summe. Damit steht die ganze Reihe ab 2001 auf einer Skala, und der
    Wechsel des Sensors 2012 erscheint nicht mehr als Sprung (ohne Umrechnung stiege das Mittel
    scheinbar auf das 2,2-Fache).
    Wichtig fuer die Deutung: Ein umgerechneter Tageswert ist ein Erwartungswert, keine Messung.
    Er kann eine Kommazahl sein, und eine 0 heisst vor 2012 oft nur, dass MODIS nichts gesehen hat.
    Anzahl und FRP koennen an einem Tag verschiedene Basen haben (`basis_count`, `basis_frp`).
    """
    scaled = predict_viirs_equivalent(grid, factors).merge(day_status[["date", "basis_count", "basis_frp"]], on="date")
    result = scaled[["region_id", "date"] + raw_value_columns(config) + ["basis_count", "basis_frp"]].copy()
    result["n_harm"], result["factor_count"] = pick_value_by_basis(scaled, scaled["basis_count"], "n", "count")
    result["frp_harm"], result["factor_frp"] = pick_value_by_basis(scaled, scaled["basis_frp"], "frp", "frp")
    result["country"] = result["region_id"].str[:2]
    return result


def classify_strength(frp_sum: pd.Series, config: dict[str, Any]) -> pd.Series:
    """Teilt die FRP-Summe eines Tages in Staerkeklassen ein (Standard: unter 10, 10-100, 100-500, ab 500 MW)."""
    params = config["strength"]
    labels = np.array(params["class_labels"], dtype=object)
    classes = labels[np.digitize(frp_sum.fillna(0.0), params["class_bounds_mw"])]
    return pd.Series(pd.array(classes, dtype="string"), index=frp_sum.index).where(frp_sum.notna())


def flag_big_fire_day(frp_sum: pd.Series, is_measured: pd.Series, config: dict[str, Any]) -> pd.Series:
    """Markiert Tage mit grosser FRP-Summe. Fuer umgerechnete Zeilen gilt eine eigene Schwelle (Hypothese H3)."""
    params = config["strength"]
    threshold = np.where(is_measured, params["big_fire_threshold_mw"], params["big_fire_threshold_scaled_mw"])
    return (frp_sum >= threshold).astype("boolean").where(frp_sum.notna())


def add_strength_columns(daily: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt `strength_class` und `big_fire_day` aus der harmonisierten FRP-Summe des Tages.

    Die Staerke eines Tages ist die FRP-Summe (MW), nicht die Helligkeit und nicht das staerkste
    Einzelpixel: Ein VIIRS-Pixel ist kleiner und im Median nur 0,45-mal so stark wie ein
    MODIS-Pixel desselben Feuers, die Summe ueber alle Pixel ist dagegen vergleichbar.
    Wie verlaesslich die Klassen fuer umgerechnete Tage sind, steht in `strength_confusion` und
    `big_fire_day_quality`. Faustregel aus der Voranalyse: Sehr starke Tage trifft MODIS gut,
    mittlere Tage oft nicht.
    """
    measured = daily["basis_frp"] == BASIS_VIIRS
    return daily.assign(strength_class=classify_strength(daily["frp_harm"], config),
                        big_fire_day=flag_big_fire_day(daily["frp_harm"], measured, config))


def has_no_basis(daily: pd.DataFrame) -> pd.Series:
    """Zeilen ohne harmonisierten Wert (keine zulaessige Quelle an dem Tag)."""
    return (daily["basis_count"] == BASIS_NONE) | (daily["basis_frp"] == BASIS_NONE)
