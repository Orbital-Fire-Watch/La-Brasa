"""Prueft die Hypothesen H1 bis H5 per Kreuzvalidierung und schreibt hypothesis_results.json (neben diesem Skript).

Aufruf: .venv/bin/python data_analysis/experiments/evaluate_hypotheses.py
Jede Variante aendert genau eine Einstellung gegenueber der aktuellen Konfiguration und wird mit
denselben KPI-Funktionen gemessen wie die Pipeline. Es werden keine Dateien der Pipeline veraendert.

Entscheidungsregel (vorab festgelegt): Eine Variante wird nur uebernommen, wenn sie ihre Zielgroesse
um mindestens 1 % verbessert und keine Schwelle reisst, die vorher erfuellt war.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent   # Pipeline-Wurzel (move_harmonisation_pipeline)
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.algorithms import daily_grid, uncertainty_model, validation_kpis  # noqa: E402
from pipeline.algorithms.calibration_factors import estimate_ratio_per_region, select_calibration_days  # noqa: E402
from pipeline.algorithms.event_quality import measure_event_agreement  # noqa: E402
from pipeline.config import load_config, path_of  # noqa: E402
from pipeline.data_loading.derive_hotspot_columns import assign_observation_date  # noqa: E402
from pipeline.io_utils import read_parquet, write_json  # noqa: E402

SUMMER_MONTHS = (6, 7, 8, 9)
H3_THRESHOLDS_MW = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 120.0)


def build_units(hotspots: pd.DataFrame, config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Baut die Einheiten der Kreuzvalidierung (NUTS-2 und Zelle) fuer eine Konfiguration, ohne etwas zu speichern."""
    params = config["daily"]
    points = hotspots.assign(obs_date=assign_observation_date(hotspots, params["date_assignment"], params["solar_day_shift_hours"]))
    sums = daily_grid.sum_hotspots_by_day(points, config)
    status = daily_grid.build_day_status(sums, daily_grid.find_satellite_coverage(config), config)
    calibration_days = select_calibration_days(daily_grid.build_daily_grid(sums, status), config)
    loyo = uncertainty_model.estimate_leave_one_year_out_factors(calibration_days, config)
    dates = pd.DatetimeIndex(sorted(calibration_days["date"].unique()))
    return {"nuts2": uncertainty_model.predict_leave_one_year_out(calibration_days, loyo),
            "cell": uncertainty_model.predict_cell_units(points, dates, loyo, config)}


def summarise_variant(units: dict[str, pd.DataFrame], config: dict[str, Any]) -> dict[str, float]:
    """Die Kennzahlen einer Variante, die fuer die Entscheidung zaehlen."""
    accuracy = validation_kpis.measure_accuracy(units, config)
    count_column, frp_column = validation_kpis.default_prediction_columns(config)
    calibration = validation_kpis.measure_uncertainty_calibration(units, count_column, frp_column, config)
    return {"d1_day_error": accuracy["d1_daily_count"]["median_factor_error"],
            "d3_month_error": accuracy["d3_monthly"]["median_factor_error"], "d3_month_class": accuracy["d3_monthly"]["class_accuracy"],
            "d3_month_kappa": accuracy["d3_monthly"]["kappa"], "d4_frp_r2": accuracy["d4_daily_frp"]["r2_log"],
            "d4_frp_ratio": accuracy["d4_daily_frp"]["median_ratio"], "d5_kappa": accuracy["d5_big_fire_region"]["kappa"],
            "d5_recall": accuracy["d5_big_fire_region"]["recall"], "d5_precision": accuracy["d5_big_fire_region"]["precision"],
            "d6_cell_kappa": accuracy["d6_big_fire_cell"]["kappa"], "d7_extreme": accuracy["d7_extreme_class"]["exact_share"],
            "d8_clim_r2": accuracy["d8_climatology"]["r2_log"], "d8_clim_corr_min": accuracy["d8_climatology"]["region_corr_min"],
            "u1_cov50_min": calibration["coverage50_min"], "u1_cov50_max": calibration["coverage50_max"],
            "u3_factor_shift": calibration["factor_shift_max"]}


def evaluate_variant(hotspots: pd.DataFrame, config: dict[str, Any], changes: dict[str, dict[str, Any]]) -> dict[str, float]:
    """Misst eine Variante: Kopie der Konfiguration mit den genannten Aenderungen."""
    variant = copy.deepcopy(config)
    for section, values in changes.items():
        variant[section].update(values)
    return summarise_variant(build_units(hotspots, variant), variant)


def evaluate_scaled_thresholds(units: pd.DataFrame, config: dict[str, Any]) -> list[dict[str, float]]:
    """H3: Recall, Precision und Kappa der Grossfeuer-Tage fuer verschiedene Schwellen der umgerechneten Zeilen."""
    regions = validation_kpis.select_evaluation_regions(units, config)
    rows = units[units["area_id"].isin(regions)]
    measured = (rows["frp_snpp"] >= config["strength"]["big_fire_threshold_mw"]).to_numpy()
    frp_column = validation_kpis.default_prediction_columns(config)[1]
    results = []
    for threshold in H3_THRESHOLDS_MW:
        agreement = measure_event_agreement(measured, (rows[frp_column] >= threshold).to_numpy())
        results.append({"threshold_mw": threshold, "recall": agreement["recall"], "precision": agreement["precision"],
                        "kappa": agreement["kappa"], "balance_gap": abs(agreement["recall"] - agreement["precision"])})
    return results


def evaluate_season_factors(hotspots: pd.DataFrame, config: dict[str, Any]) -> dict[str, float]:
    """H4: eigener Zaehlfaktor fuer Juni bis September gegen einen Faktor fuer das ganze Jahr (Fehler je Tag und Monat)."""
    points = hotspots.assign(obs_date=assign_observation_date(hotspots, config["daily"]["date_assignment"], config["daily"]["solar_day_shift_hours"]))
    sums = daily_grid.sum_hotspots_by_day(points, config)
    status = daily_grid.build_day_status(sums, daily_grid.find_satellite_coverage(config), config)
    days = select_calibration_days(daily_grid.build_daily_grid(sums, status), config)
    days = days.assign(year=days["date"].dt.year, summer=days["date"].dt.month.isin(SUMMER_MONTHS))
    minimum, parts = config["calibration"]["min_modis_detections"], []
    for year in sorted(days["year"].unique()):
        train, test = days[days["year"] != year], days[days["year"] == year]
        for summer in (True, False):
            ratio = estimate_ratio_per_region(train[train["summer"] == summer], "n_snpp", "n_pair", minimum)
            factor = test.loc[test["summer"] == summer, "region_id"].map(ratio.set_index("region_id")["factor"])
            parts.append(test[test["summer"] == summer].assign(pred_n_pair=lambda rows, f=factor: rows["n_pair"] * f.to_numpy()))
    units = pd.concat(parts).rename(columns={"region_id": "area_id"})
    units = units[units["area_id"].isin(validation_kpis.select_evaluation_regions(units, config))]
    offset = config["uncertainty"]["count_offset"]
    monthly = validation_kpis.measure_monthly_accuracy(units.assign(frp_snpp=0.0, **{c: 0.0 for c in uncertainty_model.VALUE_COLUMNS if c not in units}),
                                                       "pred_n_pair", offset)
    return {"d1_day_error": validation_kpis.measure_daily_count_accuracy(units, "pred_n_pair", offset)["median_factor_error"],
            "d3_month_error": monthly["median_factor_error"], "d3_month_class": monthly["class_accuracy"], "d3_month_kappa": monthly["kappa"]}


def main() -> None:
    """Rechnet alle Varianten und schreibt die Ergebnisse."""
    config = load_config()
    hotspots = read_parquet(path_of(config, "processed", "hotspots_clean.parquet"))
    source, daynight, dates = config["strength"]["frp_modis_source"], config["strength"]["frp_daynight"], config["daily"]["date_assignment"]
    other = lambda value, first, second: second if value == first else first
    results = {"baseline": {"settings": {"frp_modis_source": source, "frp_daynight": daynight, "date_assignment": dates},
                            **evaluate_variant(hotspots, config, {})},
               "h1_frp_source": {"settings": {"frp_modis_source": other(source, "aqua", "pair")},
                                 **evaluate_variant(hotspots, config, {"strength": {"frp_modis_source": other(source, "aqua", "pair")}})},
               "h2_date_assignment": {"settings": {"date_assignment": other(dates, "utc", "solar")},
                                      **evaluate_variant(hotspots, config, {"daily": {"date_assignment": other(dates, "utc", "solar")}})},
               "h5_frp_daynight": {"settings": {"frp_daynight": other(daynight, "all", "day")},
                                   **evaluate_variant(hotspots, config, {"strength": {"frp_daynight": other(daynight, "all", "day")}})},
               "h3_scaled_threshold": evaluate_scaled_thresholds(build_units(hotspots, config)["nuts2"], config),
               "h4_season_factors": evaluate_season_factors(hotspots, config)}
    write_json(results, Path(__file__).resolve().parent / "hypothesis_results.json")
    table = pd.DataFrame({name: values for name, values in results.items() if isinstance(values, dict) and name != "h4_season_factors"}).drop(index="settings")
    print(table.astype(float).round(3).to_string())
    print("\nH3", pd.DataFrame(results["h3_scaled_threshold"]).round(3).to_string(index=False))
    print("\nH4", {key: round(value, 3) for key, value in results["h4_season_factors"].items()})


if __name__ == "__main__":
    main()
