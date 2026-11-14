"""KPIs der VIIRS-Referenz aus mehreren Satelliten (SNPP, NOAA-20, NOAA-21): Prüfungen N1 bis N4.

Die Referenzreihe `n_viirs` ist das Mittel der an einem Tag aktiven VIIRS-Satelliten. Diese
Prüfungen zeigen, dass das Mittel auf dem Niveau von SNPP bleibt (kein Sprung 2018 / 2023), dass
die Punktgewichte 1/k exakt aufgehen, dass das Mittel genauer ist als ein einzelner Satellit und
dass die Ortsmaske für statische Quellen auch die NOAA-Satelliten trifft.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from pipeline.algorithms.uncertainty_model import factor_error
from pipeline.config import viirs_keys

REFERENCE_KEY = "snpp"           # Vergleichsbasis von N1: die bisherige Referenz


def measure_viirs_level(daily: pd.DataFrame, regions: list[str], config: dict[str, Any]) -> dict[str, Any]:
    """N1: Verhältnis `n_viirs / n_snpp` je Region und Jahr, nur Tage, an denen SNPP und mindestens ein weiterer VIIRS-Satellit liefern.

    Liegt der Median nahe 1, setzt das Mittel die Reihe auf SNPP-Niveau fort, es gibt also keinen
    Sprung beim Start von NOAA-20 (2018) oder NOAA-21 (2023). Das kleinste Verhältnis je Region
    (N1b) deckt Gebiete auf, die ein Satellit nicht abdeckt: Dort zählt er als aktiv, meldet aber
    nichts, und das Mittel fällt auf etwa die Hälfte.
    """
    others = [f"n_{key}" for key in viirs_keys(config) if key != REFERENCE_KEY]
    rows = daily[daily["region_id"].isin(regions) & daily[f"n_{REFERENCE_KEY}"].notna() & daily[others].notna().any(axis=1)]
    yearly = rows.assign(year=rows["date"].dt.year).groupby(["region_id", "year"])[["n_viirs", f"n_{REFERENCE_KEY}"]].sum()
    yearly = yearly[yearly[f"n_{REFERENCE_KEY}"] >= config["kpi"]["viirs_level_min_snpp_per_region_year"]]
    ratio = yearly["n_viirs"] / yearly[f"n_{REFERENCE_KEY}"]
    by_region = yearly.groupby("region_id").sum()
    region_ratio = (by_region["n_viirs"] / by_region[f"n_{REFERENCE_KEY}"]).sort_values()
    return {"median": float(ratio.median()), "p10": float(ratio.quantile(0.1)), "p90": float(ratio.quantile(0.9)),
            "n_region_years": int(len(ratio)), "region_min": float(region_ratio.min()) if len(region_ratio) else float("nan"),
            "region_min_id": str(region_ratio.index[0]) if len(region_ratio) else None,
            "by_region": {region: round(float(value), 4) for region, value in region_ratio.items()}}


def measure_viirs_weight_identity(hotspots: pd.DataFrame, daily: pd.DataFrame) -> dict[str, float]:
    """N2: An gemessenen Tagen ergibt SUM(weight_n) je Region und Tag genau `n_viirs`, SUM(frp * weight_frp) genau `frp_viirs`."""
    points = hotspots.dropna(subset=["region_id"]).assign(frp_weighted=lambda rows: rows["frp"] * rows["weight_frp"])
    sums = points.groupby(["region_id", "obs_date"])[["weight_n", "frp_weighted"]].sum().reset_index()
    merged = daily[["region_id", "date", "basis_count", "basis_frp", "n_viirs", "frp_viirs"]].merge(
        sums, left_on=["region_id", "date"], right_on=["region_id", "obs_date"], how="left").fillna({"weight_n": 0.0, "frp_weighted": 0.0})
    count_rows, frp_rows = merged[merged["basis_count"] == "viirs_measured"], merged[merged["basis_frp"] == "viirs_measured"]
    deviation_n = (count_rows["weight_n"] - count_rows["n_viirs"]).abs() / np.maximum(count_rows["n_viirs"].abs(), 1.0)
    deviation_frp = (frp_rows["frp_weighted"] - frp_rows["frp_viirs"]).abs() / np.maximum(frp_rows["frp_viirs"].abs(), 1.0)
    deviation = pd.concat([deviation_n, deviation_frp])
    return {"max_relative_deviation": float(deviation.max()) if len(deviation) else 0.0, "n_region_days": int(len(count_rows))}


def rotation_errors(table: pd.DataFrame, keys: list[str], held_out: str, offset: float) -> dict[str, Any]:
    """Typischer Fehler gegen den zurückgehaltenen Satelliten: jeder andere einzeln und ihr Mittel."""
    others = [key for key in keys if key != held_out]
    active = (table[[f"n_{key}" for key in keys]] > 0).any(axis=1)
    rows, reference = table[active], table.loc[active, f"n_{held_out}"]
    single = {key: float(np.median(factor_error(rows[f"n_{key}"], reference, offset))) for key in others}
    mean = float(np.median(factor_error(rows[[f"n_{key}" for key in others]].mean(axis=1), reference, offset)))
    return {"held_out": held_out, "error_single": single, "error_mean": mean, "mean_better": bool(mean < min(single.values())),
            "n_units": int(active.sum())}


def measure_instrument_noise(daily: pd.DataFrame, regions: list[str], config: dict[str, Any]) -> dict[str, Any]:
    """N3: Ist das Mittel genauer als ein einzelner Satellit? Prüfung ohne Wahrheit, mit einem zurückgehaltenen Satelliten.

    An Tagen, an denen alle VIIRS-Satelliten liefern (ab 03/2023), wird jeder einmal als
    unabhängige Messung zurückgehalten. Trifft das Mittel der übrigen ihn besser (kleinerer
    typischer Faktorfehler je Region x Tag) als jeder der übrigen allein, dann gleicht das Mittel
    den Zufall eines einzelnen Überflugs aus. Gezählt wird, in wie vielen Rotationen das gilt.
    """
    keys = viirs_keys(config)
    rows = daily[daily["region_id"].isin(regions) & daily[[f"n_{key}" for key in keys]].notna().all(axis=1)]
    if rows.empty:
        return {"rotations_won": 0, "rotations": [], "n_region_days": 0}
    rotations = [rotation_errors(rows, keys, key, config["uncertainty"]["count_offset"]) for key in keys]
    return {"rotations_won": int(sum(row["mean_better"] for row in rotations)), "rotations": rotations, "n_region_days": int(len(rows))}


def mask_quality_of_viirs_satellites(mask: dict[str, Any], config: dict[str, Any]) -> dict[str, float]:
    """N4: schlechtester Recall und höchste Fehlentfernung der Ortsmaske über alle VIIRS-Satelliten."""
    rates = [mask["by_satellite"][satellite] for satellite in config["satellites"]["viirs"] if satellite in mask["by_satellite"]]
    return {"recall_min": float(min(rate["recall"] for rate in rates)), "false_removal_max": float(max(rate["false_removal"] for rate in rates))}


def viirs_checks(measured: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str, float, str, float]]:
    """Die Prüfungen N1 bis N4 als (ID, Name, Wert, Regel, Schwelle)."""
    limits, viirs = config["kpi"]["thresholds"], measured["viirs"]
    low, high = limits["n1_viirs_over_snpp_median_range"]
    mask = mask_quality_of_viirs_satellites(measured["mask"], config)
    return [
        ("N1a", "VIIRS-Mittel / SNPP je Region x Jahr: Median (untere Grenze)", viirs["level"]["median"], ">=", low),
        ("N1b", "VIIRS-Mittel / SNPP je Region x Jahr: Median (obere Grenze)", viirs["level"]["median"], "<=", high),
        ("N1c", "VIIRS-Mittel / SNPP: kleinstes Verhaeltnis je Region", viirs["level"]["region_min"], ">=", limits["n1c_viirs_over_snpp_region_min"]),
        ("N2", "Gewichte 1/k: Abweichung zu n_viirs / frp_viirs", viirs["weights"]["max_relative_deviation"], "<=", limits["n2_weight_identity_max"]),
        ("N3", "Mittel genauer als ein Satellit (gewonnene Rotationen)", float(viirs["noise"]["rotations_won"]), ">=",
         float(limits["n3_mean_beats_single_rotations_min"])),
        ("N4a", "Ortsmaske je VIIRS-Satellit: kleinster Recall", mask["recall_min"], ">=", limits["n4_mask_recall_min"]),
        ("N4b", "Ortsmaske je VIIRS-Satellit: hoechste Fehlentfernung", mask["false_removal_max"], "<=", limits["n4_mask_false_removal_max"]),
    ]
