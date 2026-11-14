"""Unsicherheit harmonisierter Zahlen: Nachschlagen im Fehlermodell und Berechnen der Fehlerbaender."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

BASIS_MEASURED = "viirs_measured"
ALL_CLASSES = "all"
ZERO_CLASS = "0"
OFFSET_KEY = {"count": "count_offset", "frp": "frp_offset_mw"}


def select_quality_rows(quality: pd.DataFrame, area_scale: str, grain: str, quantity: str, basis: str) -> pd.DataFrame:
    """Zeilen des Fehlermodells fuer eine Kombination aus Flaeche, Zeitschritt, Groesse und Basis."""
    rows = quality[(quality["area_scale"] == area_scale) & (quality["grain"] == grain)
                   & (quality["quantity"] == quantity) & (quality["basis"] == basis)]
    if rows.empty:
        raise KeyError(f"Kein Fehlermodell fuer {area_scale}/{grain}/{quantity}/{basis}")
    return rows


def lookup_error_factors(quality: pd.DataFrame, area_scale: str, grain: str, quantity: str, basis: str,
                         expected: np.ndarray, min_units: int) -> pd.DataFrame:
    """Schlaegt zu jeder umgerechneten Zahl die Fehlerfaktoren ihrer Groessenklasse nach.

    Der Fehler einer Umrechnung haengt stark von der Groesse der Zahl ab: Bei 500 Erkennungen
    liegt er um x 1,1, bei 3 Erkennungen um x 2 bis x 3. Ein einziger Faktor fuer alle Zeilen waere
    fuer kleine Zahlen zu optimistisch und fuer grosse zu pessimistisch. Die Klasse richtet sich
    nach der umgerechneten Zahl, weil nur sie beim Anzeigen bekannt ist.
    Hat eine Klasse zu wenige Faelle (`min_units`), gilt der Wert ueber alle Klassen der Skala.
    Rueckgabe je Zahl: `e50`, `e90` (Faktoren) sowie fuer die Klasse 0 die absoluten Obergrenzen
    `abs50`, `abs90`, weil ein Faktor auf 0 nichts aussagt.
    """
    rows = select_quality_rows(quality, area_scale, grain, quantity, basis)
    overall = rows[rows["size_class"] == ALL_CLASSES].iloc[0]
    classes = rows[rows["size_class"] != ALL_CLASSES].sort_values("class_upper")
    position = np.searchsorted(classes["class_upper"].to_numpy(), np.asarray(expected, float), side="left")
    picked = classes.iloc[np.clip(position, 0, len(classes) - 1)].reset_index(drop=True)
    enough = (picked["n_units"] >= min_units).to_numpy()
    result = pd.DataFrame({"e50": np.where(enough, picked["median_factor_error"], overall["median_factor_error"]),
                           "e90": np.where(enough, picked["p90_factor_error"], overall["p90_factor_error"]),
                           "abs50": picked["abs_upper_p50"].to_numpy(), "abs90": picked["abs_upper_p90"].to_numpy()})
    result["is_zero"] = np.asarray(expected, float) <= 0
    return result


def measured_error_factors(counts: np.ndarray, config: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Fehlerfaktoren fuer gemessene VIIRS-Werte: Zaehlrauschen mit einem Mindestwert.

    Eine Zaehlung von n zufaelligen Ereignissen streut um etwa Wurzel(n). Daraus folgt der Faktor
    1 + z / Wurzel(n + 1) mit z = 0,67 fuer das 50-%-Band und 1,64 fuer das 90-%-Band. Das allein
    waere zu optimistisch: Auch zwei baugleiche VIIRS-Instrumente weichen voneinander ab (in der
    Voranalyse x 1,2 bis x 1,3 in der 1-Grad-Zelle je Monat). Darum gilt ein Mindestfaktor aus der
    Konfiguration. Diese Baender sind eine begruendete Annahme und in Iberien nicht pruefbar, weil
    dort nur ein VIIRS-Instrument vorliegt.
    """
    params = config["uncertainty"]
    spread = 1.0 / np.sqrt(np.asarray(counts, float) + 1.0)
    e50 = np.maximum(params["measured_min_factor_50"], 1.0 + params["normal_quantile_50"] * spread)
    e90 = np.maximum(params["measured_min_factor_90"], 1.0 + params["normal_quantile_90"] * spread)
    return e50, e90


def band_limits(expected: np.ndarray, factor: np.ndarray, offset: float) -> tuple[np.ndarray, np.ndarray]:
    """Unter- und Obergrenze eines Fehlerbands: (Zahl + o) / Faktor - o bis (Zahl + o) x Faktor - o.

    Der Versatz o ist derselbe wie bei der Messung des Fehlers (+1 bei Anzahlen). Er sorgt dafuer,
    dass auch kleine Zahlen ein sinnvolles Band bekommen. Die Untergrenze ist nie negativ.
    """
    expected = np.asarray(expected, float)
    return np.maximum(0.0, (expected + offset) / factor - offset), (expected + offset) * factor - offset


def uncertainty_bands(expected: np.ndarray, quantity: str, is_measured: np.ndarray, reference_count: np.ndarray,
                      converted: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Berechnet die vier Bandgrenzen (lo50, hi50, lo90, hi90) fuer gemessene und umgerechnete Zahlen.

    Umgerechnet: Faktoren aus dem Fehlermodell. Fuer die Klasse 0 gilt statt eines Faktors die
    absolute Obergrenze (z. B. "0, bis etwa 11"): Das Band beginnt bei 0 und endet beim 50-%- bzw.
    90-%-Quantil dessen, was VIIRS in solchen Faellen gemessen hat.
    Gemessen: Zaehlrauschen mit Mindestfaktor, bezogen auf die Anzahl der Erkennungen der Zeile.
    Das 50-%-Band enthaelt die Messung in etwa der Haelfte der Faelle, das 90-%-Band in etwa
    neun von zehn. Es sind typische Bereiche und keine Garantien.
    """
    offset = config["uncertainty"][OFFSET_KEY[quantity]]
    e50_measured, e90_measured = measured_error_factors(reference_count, config)
    e50 = np.where(is_measured, e50_measured, converted["e50"])
    e90 = np.where(is_measured, e90_measured, converted["e90"])
    lo50, hi50 = band_limits(expected, e50, offset)
    lo90, hi90 = band_limits(expected, e90, offset)
    zero = converted["is_zero"].to_numpy() & ~np.asarray(is_measured)
    lo50, lo90 = np.where(zero, 0.0, lo50), np.where(zero, 0.0, lo90)
    hi50, hi90 = np.where(zero, converted["abs50"], hi50), np.where(zero, converted["abs90"], hi90)
    return pd.DataFrame({"lo50": lo50, "hi50": np.maximum(hi50, expected), "lo90": np.minimum(lo90, lo50),
                         "hi90": np.maximum(hi90, np.maximum(hi50, expected))})


def classify_reliability(is_measured: np.ndarray, expected_count: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    """Zuverlaessigkeitsstufe: measured, converted_solid (grosse Zahl) oder converted_rough (kleine Zahl)."""
    solid = np.asarray(expected_count, float) >= config["uncertainty"]["reliability_solid_min_count"]
    return np.where(is_measured, "measured", np.where(solid, "converted_solid", "converted_rough"))


def area_scale_for(area_km2: float, config: dict[str, Any]) -> str:
    """Waehlt die Flaechenskala des Fehlermodells, die zu einer frei gewaehlten Flaeche passt."""
    for scale, upper in config["uncertainty"]["area_scale_max_km2"].items():
        if area_km2 <= upper:
            return scale
    return "all"


def estimate_uncertainty(expected: float, expected_count: float, quantity: str, area_scale: str, grain: str, basis: str,
                         share_measured: float, quality: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """Liefert Baender und Zuverlaessigkeit fuer ein beliebiges Aggregat (Flaeche x Zeitraum).

    `share_measured` ist der Anteil der Tage mit gemessenem VIIRS. Nur ein vollstaendig gemessener
    Zeitraum (Anteil 1) gilt als gemessen. Sobald ein Teil umgerechnet ist, gilt vorsichtshalber
    das Fehlermodell der Umrechnung fuer die Basis `basis`.
    Das Fehlermodell kennt nur die Skalen, auf denen es geprueft wurde (Zelle, NUTS-2, Land,
    Gebiet x Tag bis Jahr). Fuer andere Flaechen waehlt `area_scale_for` die naechstliegende.
    """
    measured = np.array([share_measured >= 1.0])
    lookup_basis = basis if not measured[0] else quality.loc[(quality["quantity"] == quantity), "basis"].iloc[0]
    converted = lookup_error_factors(quality, area_scale, grain, quantity, lookup_basis, np.array([expected]),
                                     config["uncertainty"]["min_units_per_class"])
    bands = uncertainty_bands(np.array([expected]), quantity, measured, np.array([expected_count]), converted, config).iloc[0]
    reliability = classify_reliability(measured, np.array([expected_count]), config)[0]
    return {"value": float(expected), "lo50": float(bands["lo50"]), "hi50": float(bands["hi50"]),
            "lo90": float(bands["lo90"]), "hi90": float(bands["hi90"]), "reliability": str(reliability)}
