"""Drift-Monitor: bleibt die Ueberflugzeit der Satelliten im Kalibrierfenster stabil?"""
from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from pipeline.config import path_of

MINUTES_PER_HOUR = 60.0

DRIFT_SQL = """
SELECT satellite, year(acq_date) AS year, median(local_solar_hour) AS median_solar_hour, COUNT(*) AS n
FROM '{clean}' WHERE daynight = '{daynight}'
GROUP BY ALL HAVING COUNT(*) >= {min_n} ORDER BY ALL
"""


def monitor_overpass_drift(config: dict[str, Any]) -> pd.DataFrame:
    """Vergleicht je Satellit und Jahr die mittlere lokale Ueberflugzeit mit den Basisjahren.

    Hintergrund: Die Kalibrierung setzt voraus, dass MODIS und VIIRS dieselben Feuer zur selben
    Tageszeit sehen. Feuer brennen am Nachmittag am staerksten. Verschiebt sich die Ueberflugzeit
    eines Satelliten, sieht er systematisch mehr oder weniger Feuer, und der Faktor stimmt nicht
    mehr. Terra und Aqua werden seit 2022 nicht mehr auf ihrer Bahn gehalten.
    Gemessen wird der Median der lokalen Sonnenzeit der Tag-Erkennungen. Die Abweichung zum
    Mittel der Basisjahre (Standard 2012-2014) steht in Minuten in `deviation_minutes`. Satelliten
    ohne Daten in den Basisjahren (NOAA-20 ab 2018, NOAA-21 ab 2023) werden an ihren ersten
    `baseline_fallback_years` vollen Jahren gemessen (das Startjahr ist meist unvollstaendig).
    `exceeds_limit` ist wahr, wenn sie die erlaubte Grenze (Standard 15 Minuten) ueberschreitet,
    `in_calibration_window` markiert die Jahre, die in die Faktoren eingehen.
    Ein Jahr, bei dem beide Spalten wahr sind, ist ein Warnsignal.
    """
    params = config["drift_monitor"]
    query = DRIFT_SQL.format(clean=path_of(config, "processed", "hotspots_clean.parquet"),
                             daynight=params["daynight"], min_n=params["min_detections_per_year"])
    yearly = duckdb.connect().execute(query).df()
    yearly = yearly.merge(baseline_solar_hours(yearly, params), on="satellite", how="left")
    yearly["deviation_minutes"] = (yearly["median_solar_hour"] - yearly["baseline_solar_hour"]) * MINUTES_PER_HOUR
    yearly["exceeds_limit"] = yearly["deviation_minutes"].abs() > params["max_deviation_minutes"]
    window = config["calibration"]
    first_year, last_year = pd.Timestamp(window["window_start"]).year, pd.Timestamp(window["window_end"]).year
    yearly["in_calibration_window"] = yearly["year"].between(first_year, last_year)
    return yearly


def baseline_solar_hours(yearly: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
    """Mittlere Ueberflugzeit der Basisjahre je Satellit, ersatzweise seiner ersten vollen Jahre."""
    rows = []
    for satellite, group in yearly.groupby("satellite"):
        base = group[group["year"].isin(params["baseline_years"])]
        if base.empty:
            first_full = group["year"].min() + 1
            base = group[group["year"].between(first_full, first_full + params["baseline_fallback_years"] - 1)]
        rows.append((satellite, base["median_solar_hour"].mean()))
    return pd.DataFrame(rows, columns=["satellite", "baseline_solar_hour"]).set_index("satellite")["baseline_solar_hour"]


def summarise_drift_warnings(drift: pd.DataFrame) -> dict[str, Any]:
    """Fasst zusammen, ob ein Kalibrierjahr die Grenze verletzt und wie gross die Drift heute ist."""
    in_window = drift[drift["in_calibration_window"]]
    latest = drift.sort_values("year").groupby("satellite").tail(1)
    return {"calibration_years_exceeding_limit": in_window[in_window["exceeds_limit"]][["satellite", "year"]].to_dict("records"),
            "max_abs_deviation_minutes_in_window": float(in_window["deviation_minutes"].abs().max()),
            "latest_deviation_minutes": {row.satellite: round(float(row.deviation_minutes), 1) for row in latest.itertuples()}}
