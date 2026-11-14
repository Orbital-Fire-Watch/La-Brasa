"""Qualitaet der nicht addierbaren Tagesgroessen: Staerkeklasse und Grossfeuer-Tag."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pipeline.algorithms.calibration_factors import MODIS_VARIANTS
from pipeline.algorithms.harmonise_daily import classify_strength
from pipeline.algorithms.uncertainty_model import BASIS_OF_VARIANT


def cohen_kappa(first: np.ndarray, second: np.ndarray) -> float:
    """Cohens Kappa: Uebereinstimmung zweier Einteilungen ueber den Zufall hinaus (0 = Zufall, 1 = perfekt)."""
    labels = np.union1d(first, second)
    observed = float(np.mean(first == second))
    expected = float(sum(np.mean(first == label) * np.mean(second == label) for label in labels))
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def measure_event_agreement(measured: np.ndarray, converted: np.ndarray) -> dict[str, float]:
    """Recall, Precision und Kappa fuer ein Ja/Nein-Ereignis (gemessen gegen umgerechnet).

    Recall: Anteil der gemessenen Ereignisse, die auch die Umrechnung zeigt.
    Precision: Anteil der Ereignisse der Umrechnung, die auch gemessen wurden.
    """
    both = int((measured & converted).sum())
    return {"recall": both / max(int(measured.sum()), 1), "precision": both / max(int(converted.sum()), 1),
            "kappa": cohen_kappa(measured, converted), "n_events_measured": int(measured.sum()),
            "n_events_converted": int(converted.sum()), "n_units": int(len(measured))}


def build_strength_confusion(region_units: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Vergleicht je Basis die Staerkeklasse der VIIRS-Messung mit der Klasse der Umrechnung (Region x Tag).

    Je gemessener Klasse steht, wie sich die umgerechneten Tage auf die Klassen verteilen. Daran
    laesst sich ablesen, wie weit man einer Klasse vor 2012 trauen kann: Sehr starke Tage trifft
    MODIS meist, mittlere Tage landen oft eine Klasse zu tief oder ganz bei "kein Signal".
    """
    measured = classify_strength(region_units["frp_snpp"], config)
    parts = []
    for variant in MODIS_VARIANTS:
        converted = classify_strength(region_units[f"pred_frp_{variant}"], config)
        counts = pd.crosstab(measured, converted).stack().rename("n_days").reset_index()
        counts.columns = ["measured_class", "converted_class", "n_days"]
        counts["share_of_measured_class"] = counts["n_days"] / counts.groupby("measured_class")["n_days"].transform("sum")
        parts.append(counts.assign(basis=BASIS_OF_VARIANT[variant]))
    return pd.concat(parts, ignore_index=True)[["basis", "measured_class", "converted_class", "n_days", "share_of_measured_class"]]


def build_big_fire_day_quality(units_by_area: dict[str, pd.DataFrame], config: dict[str, Any]) -> pd.DataFrame:
    """Misst je Basis und Flaechenskala, wie gut umgerechnete Tage Grossfeuer-Tage wiedergeben.

    Ein Grossfeuer-Tag ist ein Tag mit FRP-Summe ab der Schwelle der Konfiguration (Standard
    100 MW). Fuer umgerechnete Tage kann eine eigene Schwelle gelten (Hypothese H3). Gezaehlt
    werden alle Tage, auch die ruhigen.
    """
    params, rows = config["strength"], []
    for area_scale in ("nuts2", "cell"):
        units = units_by_area[area_scale]
        measured = (units["frp_snpp"] >= params["big_fire_threshold_mw"]).to_numpy()
        for variant in MODIS_VARIANTS:
            converted = (units[f"pred_frp_{variant}"] >= params["big_fire_threshold_scaled_mw"]).to_numpy()
            rows.append({"area_scale": area_scale, "basis": BASIS_OF_VARIANT[variant],
                         "threshold_measured_mw": params["big_fire_threshold_mw"],
                         "threshold_converted_mw": params["big_fire_threshold_scaled_mw"],
                         **measure_event_agreement(measured, converted)})
    return pd.DataFrame(rows)
