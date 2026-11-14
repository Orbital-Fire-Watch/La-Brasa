"""Gewichte je Hotspot: der Beitrag eines Punkts zur harmonisierten Summe."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pipeline.algorithms.calibration_factors import attach_factors
from pipeline.algorithms.daily_grid import BASIS_VIIRS, satellites_of_basis
from pipeline.algorithms.harmonise_daily import VARIANT_OF_BASIS


def is_satellite_in_basis(satellite: pd.Series, basis: pd.Series, config: dict[str, Any]) -> pd.Series:
    """Wahr, wenn der Satellit eines Punkts an dessen Tag zur Basis gehoert."""
    in_basis = pd.Series(False, index=satellite.index)
    for name, satellites in satellites_of_basis(config).items():
        in_basis |= (basis == name) & satellite.isin(satellites)
    return in_basis


def factor_of_basis(points: pd.DataFrame, basis: pd.Series, kind: str) -> pd.Series:
    """Faktor, mit dem ein Punkt in die Summe eingeht: 1 bei gemessenem VIIRS, sonst der Faktor der Region."""
    factor = pd.Series(np.where(basis == BASIS_VIIRS, 1.0, np.nan), index=points.index)
    for name, variant in VARIANT_OF_BASIS.items():
        factor = factor.where(basis != name, points[f"k_{kind}_{variant}"])
    return factor


def weight_hotspots(hotspots: pd.DataFrame, day_status: pd.DataFrame, factors: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt je Hotspot `in_series_*`, `weight_*` und die Basis seines Tages.

    Idee: Die Umrechnung ist linear (Summe x Faktor). Darum laesst sich der Faktor auf jeden
    einzelnen Punkt legen, und die harmonisierte Zahl einer beliebigen Flaeche ist einfach
    SUM(weight_n), die harmonisierte FRP SUM(frp * weight_frp). Ueber eine Region und einen Tag
    ergibt das exakt `n_harm` bzw. `frp_harm` der Tagestabelle (wird getestet).

    Regeln je Punkt:
    - `in_series_*` ist wahr, wenn der Satellit des Punkts an diesem Tag die Basis der Groesse ist.
      Das gilt je Satellit und nicht je Sensor: Im Juli 2002 gibt es schon Aqua-Punkte, die Anzahl
      laeuft bis zum 3.7. aber ueber Terra allein. Ab 2012 sind MODIS-Punkte nicht mehr in der
      Reihe, sonst stuende jedes Feuer doppelt da.
    - `weight_n` = 1 bei VIIRS, Regionsfaktor bei MODIS, 0 ausserhalb der Reihe.
    - `weight_frp` analog. Zaehlen fuer die Staerke nur Tag-Ueberfluege (`frp_daynight: day`),
      haben Nachtpunkte das FRP-Gewicht 0.
    - Punkte ohne Region bekommen die Gesamtfaktoren.

    Deutung: Ein Gewicht ist ein Beitrag zu einer Summe und keine Eigenschaft des Punkts. Ein
    MODIS-Punkt mit Gewicht 3 sind nicht drei Feuer. Verpasste kleine Feuer stellt kein Gewicht
    wieder her, und auf kleinen Flaechen ist die Summe entsprechend unsicher.
    """
    points = attach_factors(hotspots, factors).merge(
        day_status[["date", "basis_count", "basis_frp"]], left_on="obs_date", right_on="date", how="left").drop(columns="date")
    points[["basis_count", "basis_frp"]] = points[["basis_count", "basis_frp"]].fillna("none")
    in_series_n = is_satellite_in_basis(points["satellite"], points["basis_count"], config)
    in_series_frp = is_satellite_in_basis(points["satellite"], points["basis_frp"], config)
    if config["strength"]["frp_daynight"] == "day":
        in_series_frp &= points["daynight"] == "D"
    result = hotspots.copy()
    result["in_series_n"], result["in_series_frp"] = in_series_n.to_numpy(), in_series_frp.to_numpy()
    result["weight_n"] = factor_of_basis(points, points["basis_count"], "count").where(in_series_n, 0.0).to_numpy()
    result["weight_frp"] = factor_of_basis(points, points["basis_frp"], "frp").where(in_series_frp, 0.0).to_numpy()
    result["basis_count"], result["basis_frp"] = points["basis_count"].to_numpy(), points["basis_frp"].to_numpy()
    return result
