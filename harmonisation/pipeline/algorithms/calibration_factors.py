"""Kalibrierung: Umrechnungsfaktoren MODIS -> VIIRS-Aequivalent je Region (uebernommen aus Version 1, erweitert)."""
from __future__ import annotations

from typing import Any

import pandas as pd

MODIS_VARIANTS = ("pair", "aqua", "terra")


def add_modis_pair_sums(grid: pd.DataFrame) -> pd.DataFrame:
    """Ergaenzt `n_pair` und `frp_pair` als Summe aus Aqua und Terra (NA, wenn einer von beiden fehlt)."""
    return grid.assign(n_pair=grid[["n_aqua", "n_terra"]].sum(axis=1, min_count=2),
                       frp_pair=grid[["frp_aqua", "frp_terra"]].sum(axis=1, min_count=2))


def select_calibration_days(grid: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Waehlt die Tage des Kalibrierfensters, an denen alle drei Satelliten in Betrieb sind.

    Das Fenster (Standard 02/2012 bis 12/2021) ist der Zeitraum, in dem VIIRS und MODIS
    gleichzeitig und zur festen Tageszeit messen. Ab 2022 driften Terra und Aqua von ihrer
    Ueberflugzeit weg. Spaetere Jahre wuerden den Faktor verfaelschen.
    """
    window = config["calibration"]
    in_window = grid["date"].between(pd.Timestamp(window["window_start"]), pd.Timestamp(window["window_end"]))
    operating = grid[[column for column in grid.columns if column.endswith("_operating")]].all(axis=1)
    return add_modis_pair_sums(grid[in_window & operating])


def estimate_ratio_per_region(rows: pd.DataFrame, numerator: str, denominator: str, min_denominator: float) -> pd.DataFrame:
    """Schaetzt je Region den Faktor = Summe(Zaehler) / Summe(Nenner), mit Rueckfall auf den Gesamtfaktor.

    Der Faktor ist ein Verhaeltnis von Summen ueber das ganze Kalibrierfenster und nicht der
    Mittelwert taeglicher Verhaeltnisse. Tage ohne MODIS-Erkennung (Division durch 0) machen so
    keine Probleme, und die Gesamtsumme der umgerechneten Reihe stimmt im Fenster exakt mit der
    VIIRS-Summe ueberein. Hat eine Region im Nenner weniger als `min_denominator` Erkennungen, ist
    ihr eigenes Verhaeltnis zu unsicher. Sie bekommt dann den Gesamtfaktor ueber alle Regionen.
    """
    sums = rows.groupby("region_id")[[numerator, denominator]].sum()
    overall = sums[numerator].sum() / sums[denominator].sum()
    reliable = sums[denominator] >= min_denominator
    factor = (sums[numerator] / sums[denominator].where(reliable)).fillna(overall)
    return pd.DataFrame({"factor": factor, "denominator_sum": sums[denominator], "used_fallback": ~reliable,
                         "overall_factor": overall}).reset_index()


def estimate_calibration_factors(calibration_days: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Berechnet alle Umrechnungsfaktoren je Region aus den Kalibriertagen.

    Je MODIS-Variante (Paar Aqua + Terra, nur Aqua, nur Terra) gibt es:
    - `k_count_*`: VIIRS-Erkennungen je MODIS-Erkennung, je Region.
    - `k_frp_*`: VIIRS-FRP je MODIS-FRP, ein Wert fuer alle Regionen.

    Warum ein Faktor je Region: MODIS uebersieht kleine Feuer (50 % Erkennung erst ab etwa 34 MW
    am Tag), VIIRS nicht. Wie viele MODIS verpasst, haengt von der typischen Feuergroesse einer
    Region ab. Darum schwankt der Faktor zwischen Regionen (2,5 bis 5,1), ist aber je Region ueber
    die Jahre stabil. Aufwendigere Modelle waren im Test nicht besser (Version 1, 17 Wege).
    Warum der FRP-Faktor fuer alle Regionen gilt: Einzelne Grossfeuer bestimmen die FRP-Summe einer
    Region, ein Regionswert waere dadurch instabil.
    Die drei Varianten werden gebraucht, weil die Basis vom Tag abhaengt: vor 07/2002 gibt es nur
    Terra, und fuer die Tagesstaerke ist Aqua allein die bessere Quelle (Hypothese H1).
    """
    minimum = config["calibration"]["min_modis_detections"]
    factors = pd.DataFrame({"region_id": sorted(calibration_days["region_id"].unique())})
    for variant in MODIS_VARIANTS:
        ratio = estimate_ratio_per_region(calibration_days, "n_snpp", f"n_{variant}", minimum)
        factors = factors.merge(ratio.rename(columns={
            "factor": f"k_count_{variant}", "denominator_sum": f"n_{variant}_calib",
            "used_fallback": f"used_fallback_{variant}", "overall_factor": f"k_count_{variant}_overall"}), on="region_id")
        factors[f"k_frp_{variant}"] = calibration_days["frp_snpp"].sum() / calibration_days[f"frp_{variant}"].sum()
    viirs = calibration_days.groupby("region_id")["n_snpp"].sum().rename("n_viirs_calib")
    factors = factors.merge(viirs, on="region_id")
    return factors.assign(calib_start=config["calibration"]["window_start"], calib_end=config["calibration"]["window_end"])


def overall_factors(factors: pd.DataFrame) -> dict[str, float]:
    """Die Gesamtfaktoren (fuer Regionen ohne Kalibrierdaten und Punkte ohne Region)."""
    result = {}
    for variant in MODIS_VARIANTS:
        result[f"k_count_{variant}"] = float(factors[f"k_count_{variant}_overall"].iloc[0])
        result[f"k_frp_{variant}"] = float(factors[f"k_frp_{variant}"].iloc[0])
    return result


def attach_factors(table: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Haengt die Faktoren ueber `region_id` an. Zeilen ohne Region oder Kalibrierdaten bekommen die Gesamtfaktoren."""
    columns = ["region_id"] + [f"k_{kind}_{variant}" for kind in ("count", "frp") for variant in MODIS_VARIANTS]
    return table.merge(factors[columns], on="region_id", how="left").fillna(overall_factors(factors))


def predict_viirs_equivalent(grid: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Rechnet MODIS-Zahlen in VIIRS-Aequivalente um: Vorhersage = MODIS-Summe x Faktor.

    Ergaenzt je Variante `pred_n_*` und `pred_frp_*`. Die Umrechnung ist proportional: Ein Tag ohne
    MODIS-Erkennung ergibt 0. Das war im Test der Vorteil gegenueber Modellen mit Sockelwert, die
    auch fuer leere Zeitraeume positive Werte vorhersagen. Der Preis: Die 0 ist an vielen Tagen
    falsch, weil MODIS dort nur nichts gesehen hat. Dafuer gibt es die Fehlerbaender.
    """
    scaled = attach_factors(add_modis_pair_sums(grid), factors)
    for variant in MODIS_VARIANTS:
        scaled[f"pred_n_{variant}"] = scaled[f"n_{variant}"] * scaled[f"k_count_{variant}"]
        scaled[f"pred_frp_{variant}"] = scaled[f"frp_{variant}"] * scaled[f"k_frp_{variant}"]
    return scaled
