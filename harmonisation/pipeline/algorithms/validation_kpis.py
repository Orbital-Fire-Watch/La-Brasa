"""KPI-Pruefung: misst die Guete der Harmonisierung und vergleicht sie mit den Schwellen der Konfiguration.

Grundsatz: Genauigkeit wird ausserhalb der Trainingsdaten gemessen. Die Eingabe sind die Einheiten
der Kreuzvalidierung (jedes Jahr mit Faktoren aus den uebrigen Jahren umgerechnet).
"""
from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from aggregation.climatology import DAYS_PER_YEAR, day_of_year_without_leap, smooth_circular
from aggregation.roll_up import roll_up_daily
from pipeline.algorithms.event_quality import cohen_kappa, measure_event_agreement
from pipeline.algorithms.harmonise_daily import classify_strength
from pipeline.algorithms.uncertainty_model import evaluate_holdout_directions, factor_error, roll_up_units
from pipeline.algorithms.viirs_kpis import viirs_checks

SQL_TRUNC = {"week": "week", "month": "month", "quarter": "quarter", "year": "year"}


def default_prediction_columns(config: dict[str, Any]) -> tuple[str, str]:
    """Die Spalten der Kreuzvalidierung, die der konfigurierten Basis entsprechen (Anzahl: Paar, FRP: laut Config)."""
    return "pred_n_pair", f"pred_frp_{config['strength']['frp_modis_source']}"


def select_evaluation_regions(region_units: pd.DataFrame, config: dict[str, Any]) -> list[str]:
    """Regionen mit genug VIIRS-Erkennungen, damit Tages- und Monatswerte nicht nur aus Rauschen bestehen."""
    totals = region_units.groupby("area_id")["n_viirs"].sum()
    selected = totals[totals >= config["kpi"]["eval_min_viirs_detections_region"]]
    return sorted(selected.index if len(selected) else totals.index)


def measure_daily_count_accuracy(units: pd.DataFrame, column: str, offset: float) -> dict[str, float]:
    """D1: Fehler der Anzahl je Region und Tag, nur aktive Tage (Messung oder Umrechnung groesser 0)."""
    active = units[(units["n_viirs"] > 0) | (units[column] > 0)]
    errors = factor_error(active[column], active["n_viirs"], offset)
    return {"median_factor_error": float(np.median(errors)), "p90_factor_error": float(np.quantile(errors, 0.9)),
            "n_active_days": int(len(active)), "share_active_days": float(len(active) / len(units))}


def measure_total_bias(units: pd.DataFrame, column: str) -> dict[str, float]:
    """D2: Abweichung der Gesamtsumme, je Zeitschritt aus den aufsummierten Einheiten berechnet."""
    result = {}
    for grain in ("day", "week", "month"):
        rolled = roll_up_units(units, grain)
        result[grain] = float(abs(rolled[column].sum() / rolled["n_viirs"].sum() - 1.0))
    return result


def classify_by_reference_terciles(monthly: pd.DataFrame, value_column: str) -> np.ndarray:
    """Teilt Monatswerte in unter / normal / ueber ein, gemessen an den VIIRS-Terzilen je Region und Kalendermonat."""
    bounds = monthly.groupby(["area_id", "month"])["n_viirs"].quantile([1 / 3, 2 / 3]).unstack()
    bounds.columns = ["lower", "upper"]
    joined = monthly[["area_id", "month"]].merge(bounds, left_on=["area_id", "month"], right_index=True, how="left")
    values = monthly[value_column].to_numpy()
    return np.where(values <= joined["lower"].to_numpy(), 0, np.where(values <= joined["upper"].to_numpy(), 1, 2))


def measure_monthly_accuracy(units: pd.DataFrame, column: str, offset: float) -> dict[str, float]:
    """D3: dieselben Kennzahlen wie in Version 1, berechnet aus den aufsummierten Tagen (Region x Monat)."""
    monthly = roll_up_units(units, "month")
    monthly = monthly.assign(month=monthly["period_start"].dt.month)
    errors = factor_error(monthly[column], monthly["n_viirs"], offset)
    predicted, measured = classify_by_reference_terciles(monthly, column), classify_by_reference_terciles(monthly, "n_viirs")
    return {"median_factor_error": float(np.median(errors)), "class_accuracy": float(np.mean(predicted == measured)),
            "kappa": cohen_kappa(predicted, measured), "n_region_months": int(len(monthly))}


def measure_daily_frp_agreement(units: pd.DataFrame, column: str) -> dict[str, float]:
    """D4: Uebereinstimmung der FRP-Summe je Region und Tag, an Tagen mit Wert in beiden Reihen."""
    both = units[(units["frp_viirs"] > 0) & (units[column] > 0)]
    ratio = both["frp_viirs"] / both[column]
    r2 = float(np.corrcoef(np.log(both["frp_viirs"]), np.log(both[column]))[0, 1] ** 2)
    return {"r2_log": r2, "median_ratio": float(ratio.median()), "ratio_p10": float(ratio.quantile(0.1)),
            "ratio_p90": float(ratio.quantile(0.9)), "n_days": int(len(both))}


def measure_extreme_class_hit(units: pd.DataFrame, column: str, config: dict[str, Any]) -> dict[str, float]:
    """D7: Anteil der gemessenen Tage der hoechsten Staerkeklasse, die auch die Umrechnung dort einordnet."""
    top = config["strength"]["class_labels"][-1]
    measured = classify_strength(units["frp_viirs"], config) == top
    converted = classify_strength(units[column], config) == top
    return {"exact_share": float((measured & converted).sum() / max(int(measured.sum()), 1)), "n_days": int(measured.sum())}


def build_profile(units: pd.DataFrame, column: str, years: list[int], window_days: int) -> pd.DataFrame:
    """Geglaetteter mittlerer Jahresverlauf je Region (Region x Tag im Jahr) aus den Jahren `years`."""
    rows = units[units["date"].dt.year.between(*years)]
    rows = rows.assign(year=rows["date"].dt.year, doy=day_of_year_without_leap(rows["date"]))
    table = rows.pivot_table(index=["area_id", "year"], columns="doy", values=column, aggfunc="mean")
    regions = sorted(rows["area_id"].unique())
    cube = table.to_numpy().reshape(len(regions), -1, DAYS_PER_YEAR)
    return pd.DataFrame(smooth_circular(cube, window_days).mean(1), index=regions)


def measure_climatology_agreement(units: pd.DataFrame, column: str, config: dict[str, Any]) -> dict[str, float]:
    """D8: Trifft der aus MODIS umgerechnete typische Jahresverlauf den gemessenen VIIRS-Verlauf?"""
    years, window = config["kpi"]["climatology_check_years"], config["climatology"]["window_days"]
    measured, converted = build_profile(units, "n_viirs", years, window), build_profile(units, column, years, window)
    a, b = measured.to_numpy().ravel(), converted.to_numpy().ravel()
    offset = config["kpi"]["climatology_offset"]
    correlations = [float(np.corrcoef(measured.loc[region], converted.loc[region])[0, 1]) for region in measured.index]
    return {"r2_log": float(np.corrcoef(np.log1p(a), np.log1p(b))[0, 1] ** 2),
            "median_factor_error": float(np.median(factor_error(b, a, offset))),
            "region_corr_median": float(np.median(correlations)), "region_corr_min": float(np.min(correlations)),
            "n_regions": int(len(correlations))}


def measure_trend_of_ratio(units: pd.DataFrame, count_column: str, frp_column: str, config: dict[str, Any]) -> dict[str, float]:
    """D9: Hat das Jahresverhaeltnis Umrechnung / Messung einen Trend? Kleinster p-Wert aus Anzahl und FRP."""
    yearly = units.assign(year=units["date"].dt.year).groupby("year")[["n_viirs", "frp_viirs", count_column, frp_column]].sum()
    yearly = yearly[yearly.index.to_series().between(*config["kpi"]["trend_check_years"])]
    result = {}
    for name, column, reference in (("count", count_column, "n_viirs"), ("frp", frp_column, "frp_viirs")):
        fit = stats.linregress(yearly.index.to_numpy(float), np.log(yearly[column] / yearly[reference]).to_numpy())
        result[f"p_value_{name}"], result[f"slope_{name}"] = float(fit.pvalue), float(fit.slope)
    result["p_value_min"] = min(result["p_value_count"], result["p_value_frp"])
    return result


def measure_roll_up_exactness(daily: pd.DataFrame, daily_path: str) -> dict[str, float]:
    """D10: Vergleicht die Roll-up-Funktion mit einer unabhaengigen SQL-Summe (groesste relative Abweichung)."""
    worst, compared = 0.0, 0
    connection = duckdb.connect()
    for grain, trunc in SQL_TRUNC.items():
        periods = roll_up_daily(daily, grain)
        reference = connection.execute(f"""SELECT region_id, date_trunc('{trunc}', date)::TIMESTAMP AS period_start,
            SUM(n_harm) AS n_ref, SUM(frp_harm) AS frp_ref FROM '{daily_path}' GROUP BY ALL""").df()
        reference["period_start"] = reference["period_start"].astype("datetime64[ns]")
        merged = periods[periods["is_complete_period"]].merge(reference, on=["region_id", "period_start"], how="left")
        for value, ref in (("n_harm", "n_ref"), ("frp_harm", "frp_ref")):
            deviation = (merged[value] - merged[ref]).abs() / np.maximum(merged[ref].abs(), 1.0)
            worst = max(worst, float(deviation.max()))
        compared += len(merged)
    return {"max_relative_deviation": worst, "n_periods_compared": compared}


def measure_weight_identity(hotspots: pd.DataFrame, daily: pd.DataFrame) -> dict[str, float]:
    """D11: Summe der Punktgewichte je Region und Tag gegen `n_harm` und `frp_harm` der Tagestabelle."""
    points = hotspots.dropna(subset=["region_id"]).assign(frp_weighted=lambda rows: rows["frp"] * rows["weight_frp"])
    sums = points.groupby(["region_id", "obs_date"])[["weight_n", "frp_weighted"]].sum().reset_index()
    merged = daily[["region_id", "date", "n_harm", "frp_harm"]].merge(
        sums, left_on=["region_id", "date"], right_on=["region_id", "obs_date"], how="left").fillna({"weight_n": 0.0, "frp_weighted": 0.0})
    with_value = merged[merged["n_harm"].notna()]
    deviation_n = (with_value["weight_n"] - with_value["n_harm"]).abs() / np.maximum(with_value["n_harm"].abs(), 1.0)
    deviation_frp = (with_value["frp_weighted"] - with_value["frp_harm"]).abs() / np.maximum(with_value["frp_harm"].abs(), 1.0)
    stray = float(merged.loc[merged["n_harm"].isna(), "weight_n"].sum())
    return {"max_relative_deviation": float(max(deviation_n.max(), deviation_frp.max())), "weight_on_days_without_value": stray}


def measure_uncertainty_calibration(units_by_area: dict[str, pd.DataFrame], count_column: str, frp_column: str,
                                    config: dict[str, Any]) -> dict[str, Any]:
    """U1 bis U3: Halten die Fehlerbaender, was sie versprechen, und sind die Fehlerfaktoren stabil?

    Auf einer Haelfte der Jahre bestimmt, auf der anderen geprueft, und umgekehrt. Jede Richtung
    zaehlt einzeln, gewertet wird die jeweils unguenstigste. Skalen aus `kpi.uncertainty_check_scales`.
    Gewertet werden nur Groessenklassen ueber 0 mit genug Prueffaellen in beiden Haelften: Fuer die
    Klasse 0 gilt kein Faktorband, sondern eine absolute Obergrenze.
    """
    params, minimum, rows = config["uncertainty"], config["kpi"]["uncertainty_min_units"], []
    for area_scale, grain in config["kpi"]["uncertainty_check_scales"]:
        rolled = roll_up_units(units_by_area[area_scale], grain)
        for quantity, column, measured, bounds, offset in (
                ("count", count_column, "n_viirs", params["count_class_bounds"], params["count_offset"]),
                ("frp", frp_column, "frp_viirs", params["frp_class_bounds_mw"], params["frp_offset_mw"])):
            directions = evaluate_holdout_directions(rolled, column, measured, bounds, offset, params["split_years"])
            rows.append(directions[directions["size_class"] != "0"].assign(area_scale=area_scale, grain=grain, quantity=quantity))
    table = pd.concat(rows, ignore_index=True)
    judged = table[table.groupby(["area_scale", "grain", "quantity", "size_class"])["n_test"].transform("min") >= minimum]
    totals = table.groupby(["area_scale", "grain", "quantity", "direction"])[["covered90", "n_test"]].sum()
    overall90 = totals["covered90"] / totals["n_test"]
    return {"coverage50_min": float(judged["coverage50"].min()), "coverage50_max": float(judged["coverage50"].max()),
            "coverage90_min": float(overall90.min()), "coverage90_max": float(overall90.max()),
            "factor_shift_max": float(judged["factor_shift"].max()), "n_classes_judged": int(len(judged) // 2),
            "by_class": table.round(4).to_dict("records")}


def measure_accuracy(units_by_area: dict[str, pd.DataFrame], config: dict[str, Any]) -> dict[str, Any]:
    """Misst D1 bis D9 aus den Einheiten der Kreuzvalidierung."""
    count_column, frp_column = default_prediction_columns(config)
    regions = select_evaluation_regions(units_by_area["nuts2"], config)
    units = units_by_area["nuts2"][units_by_area["nuts2"]["area_id"].isin(regions)]
    offset, strength = config["uncertainty"]["count_offset"], config["strength"]
    events = lambda table: measure_event_agreement((table["frp_viirs"] >= strength["big_fire_threshold_mw"]).to_numpy(),
                                                   (table[frp_column] >= strength["big_fire_threshold_scaled_mw"]).to_numpy())
    return {"d1_daily_count": measure_daily_count_accuracy(units, count_column, offset),
            "d2_total_bias": measure_total_bias(units, count_column),
            "d3_monthly": measure_monthly_accuracy(units, count_column, offset),
            "d4_daily_frp": measure_daily_frp_agreement(units, frp_column),
            "d5_big_fire_region": events(units), "d6_big_fire_cell": events(units_by_area["cell"]),
            "d7_extreme_class": measure_extreme_class_hit(units, frp_column, config),
            "d8_climatology": measure_climatology_agreement(units, count_column, config),
            "d9_trend": measure_trend_of_ratio(units_by_area["nuts2"], count_column, frp_column, config),
            "evaluation_regions": regions, "count_column": count_column, "frp_column": frp_column}


def accuracy_checks(measured: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str, float, str, float]]:
    """Die Pruefungen D1 bis M2 als (ID, Name, Wert, Regel, Schwelle)."""
    limits, acc, unc = config["kpi"]["thresholds"], measured["accuracy"], measured["uncertainty"]
    ratio_low, ratio_high = limits["d4_frp_day_median_ratio_range"]
    return [
        ("D1a", "Anzahl je Region x Tag: typischer Fehler", acc["d1_daily_count"]["median_factor_error"], "<=", limits["d1_day_median_factor_error_max"]),
        ("D1b", "Anzahl je Region x Tag: 90-%-Fehler", acc["d1_daily_count"]["p90_factor_error"], "<=", limits["d1_day_p90_factor_error_max"]),
        ("D2", "Gesamtverzerrung (Tag, Woche, Monat)", max(acc["d2_total_bias"].values()), "<=", limits["d2_total_bias_max"]),
        ("D3a", "Monat: typischer Fehler", acc["d3_monthly"]["median_factor_error"], "<=", limits["d3_month_median_factor_error_max"]),
        ("D3b", "Monat: Klasse getroffen", acc["d3_monthly"]["class_accuracy"], ">=", limits["d3_month_class_accuracy_min"]),
        ("D3c", "Monat: Kappa", acc["d3_monthly"]["kappa"], ">=", limits["d3_month_kappa_min"]),
        ("D4a", "FRP je Region x Tag: R2", acc["d4_daily_frp"]["r2_log"], ">=", limits["d4_frp_day_r2_min"]),
        ("D4b", "FRP je Region x Tag: Median-Verhaeltnis (untere Grenze)", acc["d4_daily_frp"]["median_ratio"], ">=", ratio_low),
        ("D4c", "FRP je Region x Tag: Median-Verhaeltnis (obere Grenze)", acc["d4_daily_frp"]["median_ratio"], "<=", ratio_high),
        ("D5a", "Grossfeuer-Tag je Region: Kappa", acc["d5_big_fire_region"]["kappa"], ">=", limits["d5_big_fire_kappa_min"]),
        ("D5b", "Grossfeuer-Tag je Region: Recall", acc["d5_big_fire_region"]["recall"], ">=", limits["d5_big_fire_recall_min"]),
        ("D5c", "Grossfeuer-Tag je Region: Precision", acc["d5_big_fire_region"]["precision"], ">=", limits["d5_big_fire_precision_min"]),
        ("D6", "Grossfeuer-Tag je Zelle: Kappa", acc["d6_big_fire_cell"]["kappa"], ">=", limits["d6_big_fire_cell_kappa_min"]),
        ("D7", "Staerkeklasse extreme exakt getroffen", acc["d7_extreme_class"]["exact_share"], ">=", limits["d7_extreme_class_exact_min"]),
        ("D8a", "Klimaprofil: R2", acc["d8_climatology"]["r2_log"], ">=", limits["d8_climatology_r2_min"]),
        ("D8b", "Klimaprofil: typischer Fehler", acc["d8_climatology"]["median_factor_error"], "<=", limits["d8_climatology_median_factor_error_max"]),
        ("D8c", "Klimaprofil: Korrelation je Region (Median)", acc["d8_climatology"]["region_corr_median"], ">=", limits["d8_climatology_region_corr_median_min"]),
        ("D8d", "Klimaprofil: Korrelation je Region (Minimum)", acc["d8_climatology"]["region_corr_min"], ">=", limits["d8_climatology_region_corr_min_min"]),
        ("D9", "Kein Trend im Verhaeltnis (kleinster p-Wert)", acc["d9_trend"]["p_value_min"], ">=", limits["d9_trend_p_value_min"]),
        ("D10", "Roll-up: groesste Abweichung zur Summe der Tage", measured["roll_up"]["max_relative_deviation"], "<=", config["kpi"]["rollup_tolerance"]),
        ("D11", "Gewichte: groesste Abweichung zu n_harm / frp_harm", measured["weights"]["max_relative_deviation"], "<=", config["kpi"]["rollup_tolerance"]),
        ("U1a", "50-%-Band: kleinste Abdeckung je Groessenklasse", unc["coverage50_min"], ">=", limits["u1_coverage50_range"][0]),
        ("U2a", "90-%-Band: kleinste Abdeckung gesamt", unc["coverage90_min"], ">=", limits["u2_coverage90_range"][0]),
        ("U2b", "90-%-Band: groesste Abdeckung gesamt", unc["coverage90_max"], "<=", limits["u2_coverage90_range"][1]),
        ("U3", "Stabilitaet der Fehlerfaktoren (groesste Abweichung)", unc["factor_shift_max"], "<=", limits["u3_factor_stability_max"]),
        ("M1a", "Ortsmaske: erkannte statische Quellen", measured["mask"]["all"]["recall"], ">=", limits["m1_mask_recall_min"]),
        ("M1b", "Ortsmaske: faelschlich entfernte Feuer", measured["mask"]["all"]["false_removal"], "<=", limits["m1_mask_false_removal_max"]),
        ("M2", "Hotspots mit Region", measured["region_coverage"], ">=", limits["m2_region_coverage_min"]),
    ]


def evaluate_thresholds(measured: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Vergleicht jeden Messwert mit seiner Schwelle und gibt je KPI eine Zeile mit `passed` zurueck."""
    checks = accuracy_checks(measured, config) + viirs_checks(measured, config)
    rows = [{"id": kpi, "name": name, "value": float(value), "rule": rule, "threshold": float(limit),
             "passed": bool(value <= limit if rule == "<=" else value >= limit)} for kpi, name, value, rule, limit in checks]
    flags = [("S1", "day_status lueckenlos, 0 gegen NA korrekt, Datumsfelder als DATE", measured["status_checks"]),
             ("I1a", "Zeilenbilanz geht auf", measured["integrity"]["row_balance"]),
             ("I1b", "Zwei Laeufe ergeben dieselben Dateien", measured["integrity"]["deterministic"]),
             ("I1c", "Alle Tests bestanden", measured["integrity"]["tests_passed"]),
             ("I1d", "Schema gleich Dokumentation", measured["integrity"]["schema_matches_documentation"]),
             ("N5", "Schema gleich in Parquet, CSV, Katalog und data_dictionary.md", measured["integrity"]["schema_everywhere"])]
    rows += [{"id": kpi, "name": name, "value": value, "rule": "==", "threshold": True, "passed": value is True} for kpi, name, value in flags]
    return rows
