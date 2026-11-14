"""Tests des Aggregationsmoduls: Roll-up, Unsicherheit, Flaechenabfrage, Klimaprofil, laufender Monat."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from aggregation import climatology, hotspot_queries, month_to_date, periods, uncertainty
from aggregation.roll_up import add_uncertainty_to_periods, roll_up_daily
from aggregation_helpers import make_daily, make_hotspots, make_quality
from pipeline.column_catalogue import columns_of


def test_period_starts() -> None:
    """Woche beginnt am Montag, Quartal und Jahr am jeweils Ersten. Das Ende ist das Kalenderende."""
    dates = pd.Series(pd.to_datetime(["2026-11-14", "2024-02-29"]))
    assert periods.period_start_of(dates, "week").dt.strftime("%Y-%m-%d").tolist() == ["2026-11-09", "2024-02-26"]
    assert periods.period_start_of(dates, "quarter").dt.strftime("%Y-%m-%d").tolist() == ["2026-10-01", "2024-01-01"]
    assert periods.period_end_of(periods.period_start_of(dates, "month"), "month").dt.day.tolist() == [30, 29]
    assert periods.days_in_period(periods.period_start_of(dates, "year"), "year").tolist() == [365, 366]


@pytest.mark.parametrize("grain", ["week", "month", "quarter", "year"])
def test_roll_up_equals_sum_of_days(grain: str) -> None:
    """Die Summe der Tage ist exakt der Wert des groeberen Zeitschritts, und die Gesamtsumme bleibt erhalten."""
    daily = make_daily("2018-01-01", "2019-12-29", measured_from="2018-01-01")
    rolled = roll_up_daily(daily, grain)
    complete = rolled[rolled["is_complete_period"]]
    keyed = daily.assign(period_start=periods.period_start_of(daily["date"], grain)).groupby(["region_id", "period_start"])["n_harm"].sum()
    expected = keyed.reindex(pd.MultiIndex.from_frame(complete[["region_id", "period_start"]])).to_numpy()
    assert np.allclose(complete["n_harm"].to_numpy(), expected, rtol=1e-12)
    assert list(rolled.columns) == columns_of("roll_up")
    if grain == "week":
        assert rolled["n_harm"].sum() == pytest.approx(daily["n_harm"].sum(), rel=1e-12)


def test_incomplete_period_has_no_value() -> None:
    """Ein angebrochener Monat (Daten enden am 12.) bekommt keinen Wert, bleibt aber als Zeile sichtbar."""
    rolled = roll_up_daily(make_daily("2026-10-01", "2026-11-30", measured_from="2026-10-01", last_value_day="2026-11-12"), "month")
    october, november = rolled[rolled["period_start"] == "2026-10-01"], rolled[rolled["period_start"] == "2026-11-01"]
    assert october["is_complete_period"].all() and october["n_harm"].notna().all()
    assert not november["is_complete_period"].any() and november["n_harm"].isna().all()
    assert (november["n_days_complete"] == 12).all() and november["n_harm_mean_per_day"].isna().all()


def test_mixed_period_is_flagged_and_fire_days_need_measurement() -> None:
    """Januar 2012: 19 umgerechnete und 12 gemessene Tage. Summe normal, Kennzeichnung mixed, keine Zahl der Feuertage."""
    rolled = roll_up_daily(make_daily("2011-12-01", "2012-02-29", measured_from="2012-01-20"), "month").set_index(["region_id", "period_start"])
    january, february = rolled.loc[("A", pd.Timestamp("2012-01-01"))], rolled.loc[("A", pd.Timestamp("2012-02-01"))]
    assert january["basis_mix"] == "mixed" and january["share_measured_days"] == pytest.approx(12 / 31)
    assert january["n_harm"] == sum(range(1, 32)) and pd.isna(january["n_days_with_fire"])
    assert february["basis_mix"] == "measured" and february["n_days_with_fire"] == 29
    assert rolled.loc[("A", pd.Timestamp("2011-12-01")), "basis_mix"] == "converted"


def test_uncertainty_for_periods(config: dict[str, Any]) -> None:
    """Umgerechnete Monate bekommen das Band ihrer Groessenklasse, gemessene das Zaehlrauschen, gemischte zaehlen als umgerechnet."""
    rolled = roll_up_daily(make_daily("2011-12-01", "2012-02-29", measured_from="2012-01-20"), "month")
    banded = add_uncertainty_to_periods(rolled, make_quality(), config).set_index(["region_id", "period_start"])
    converted, measured = banded.loc[("A", pd.Timestamp("2011-12-01"))], banded.loc[("A", pd.Timestamp("2012-02-01"))]
    # Die Klasse ">20" hat im Test-Fehlermodell zu wenige Faelle, es gilt der Wert ueber alle Klassen (1,5).
    assert converted["n_harm_hi50"] == pytest.approx((converted["n_harm"] + 1) * 1.5 - 1) and converted["reliability"] == "converted_solid"
    assert measured["reliability"] == "measured" and measured["n_harm_hi50"] < converted["n_harm_hi50"] / converted["n_harm"] * measured["n_harm"] * 1.01
    assert banded.loc[("A", pd.Timestamp("2012-01-01")), "reliability"] == "converted_solid"
    assert (banded["n_harm_lo90"] <= banded["n_harm_lo50"]).all() and (banded["n_harm_hi50"] <= banded["n_harm_hi90"]).all()


def test_estimate_uncertainty_for_any_aggregate(config: dict[str, Any]) -> None:
    """Klasse 0 bekommt die absolute Obergrenze, kleine Zahlen ein breites Band, zu duenn belegte Klassen den Gesamtwert."""
    quality = make_quality()
    zero = uncertainty.estimate_uncertainty(0.0, 0.0, "count", "nuts2", "month", "modis_pair_scaled", 0.0, quality, config)
    small = uncertainty.estimate_uncertainty(3.0, 3.0, "count", "nuts2", "month", "modis_pair_scaled", 0.0, quality, config)
    large = uncertainty.estimate_uncertainty(300.0, 300.0, "count", "nuts2", "month", "modis_pair_scaled", 0.0, quality, config)
    measured = uncertainty.estimate_uncertainty(300.0, 300.0, "count", "nuts2", "month", "modis_pair_scaled", 1.0, quality, config)
    assert (zero["lo50"], zero["hi50"], zero["hi90"]) == (0.0, 1.0, 7.0) and zero["reliability"] == "converted_rough"
    assert small["hi50"] == pytest.approx(4 * 2.0 - 1) and small["hi90"] == pytest.approx(4 * 5.0 - 1)
    assert large["hi50"] == pytest.approx(301 * 1.5 - 1) and large["reliability"] == "converted_solid"
    assert measured["reliability"] == "measured" and measured["hi50"] == pytest.approx(301 * 1.2 - 1)
    assert uncertainty.area_scale_for(500.0, config) == "cell" and uncertainty.area_scale_for(30000.0, config) == "nuts2"
    assert uncertainty.area_scale_for(5e6, config) == "all"


def test_select_and_aggregate_hotspots(tmp_path: Path) -> None:
    """Auswahl nach Rechteck, Polygon, Umkreis, Region und Zeitraum. Die Summe der Gewichte ist die harmonisierte Zahl."""
    hotspots = make_hotspots()
    box = {"bbox": [-3.8, 40.3, -3.5, 40.5]}
    assert len(hotspot_queries.select_hotspots(hotspots, box)) == 5
    assert len(hotspot_queries.select_hotspots(hotspots, box, ("2015-07-01", "2015-07-01"))) == 3
    assert len(hotspot_queries.select_hotspots(hotspots, {"polygon": [[-3.8, 40.3], [-3.5, 40.3], [-3.5, 40.5], [-3.8, 40.5]]})) == 5
    assert len(hotspot_queries.select_hotspots(hotspots, {"point": [-3.70, 40.40], "radius_km": 3.0})) == 4
    assert len(hotspot_queries.select_hotspots(hotspots, {"region_id": "ES30"})) == 6
    total = hotspot_queries.aggregate_hotspots(hotspots, box, ("2015-07-01", "2015-07-02")).iloc[0]
    assert total["n_harm"] == 3.0 and total["frp_harm"] == 35.0 and total["n_points_all"] == 4 and total["n_points_in_series"] == 3
    by_day = hotspot_queries.aggregate_hotspots(hotspots, box, by_day=True)
    assert by_day["n_harm"].tolist() == [3.0, 2.0, 1.0] and by_day["frp_harm"].tolist() == [48.0, 30.0, 5.0]
    assert hotspot_queries.approximate_area_km2(box) == pytest.approx(0.3 * 0.2 * 110.57 * 111.32 * np.cos(np.radians(40.4)), rel=1e-6)
    assert hotspot_queries.write_hotspots_csv(hotspot_queries.select_hotspots(hotspots, box), tmp_path / "x.csv") == 5
    assert (tmp_path / "x.csv").read_text().splitlines()[0].startswith("hotspot_id,latitude,longitude,acq_datetime_utc")


def test_day_of_year_folds_leap_day() -> None:
    """Der 29. Februar zaehlt zum 28., der 31. Dezember ist immer Tag 365."""
    dates = pd.Series(pd.to_datetime(["2024-02-28", "2024-02-29", "2024-03-01", "2024-12-31", "2023-12-31"]))
    assert climatology.day_of_year_without_leap(dates).tolist() == [59, 59, 60, 365, 365]


def test_smoothing_is_circular_and_keeps_the_mean() -> None:
    """Die Glaettung laeuft ueber den Jahreswechsel und veraendert den Jahresmittelwert nicht."""
    values = np.zeros((1, 365))
    values[0, 0] = 15.0
    smoothed = climatology.smooth_circular(values, 7)
    assert smoothed.mean() == pytest.approx(values.mean()) and smoothed[0, -7] == pytest.approx(1.0) and smoothed[0, 8] == 0.0


def test_climatology_uses_only_measured_years_for_probabilities(config: dict[str, Any]) -> None:
    """Mittel aus allen vollstaendigen Jahren, Wahrscheinlichkeiten nur aus vollstaendig gemessenen Jahren."""
    daily = make_daily("2009-01-01", "2016-06-30", measured_from="2012-01-20")
    profile = climatology.build_day_of_year_climatology(daily, {"climatology": {"window_days": 7, "all_years": [2001, 2025], "viirs_years": [2013, 2025]}})
    assert list(profile.columns) == columns_of("climatology") and len(profile) == 2 * 365
    assert profile["n_years_all"].iloc[0] == 7 and profile["n_years_viirs"].iloc[0] == 3
    assert np.allclose(profile["p_fire_day_viirs"], 1.0)
    assert profile.loc[profile["region_id"] == "A", "mean_n_harm_all"].mean() == pytest.approx(daily.loc[(daily["region_id"] == "A")
        & daily["date"].dt.year.between(2009, 2015) & ~((daily["date"].dt.month == 2) & (daily["date"].dt.day == 29)), "n_harm"].mean(), rel=0.01)


def test_month_to_date_compares_the_same_days() -> None:
    """Der laufende Monat wird mit denselben Tagen frueherer Jahre verglichen, nicht mit ganzen Monaten."""
    daily = make_daily("2020-01-01", "2026-11-30", measured_from="2020-01-01", last_value_day="2026-11-04")
    daily.loc[daily["date"].dt.year == 2026, ["n_harm", "frp_harm"]] *= 3
    result = month_to_date.month_to_date_vs_history(daily, "2026-11-12").set_index("region_id")
    assert list(result.reset_index().columns) == columns_of("month_to_date")
    assert result.loc["A", "as_of"] == pd.Timestamp("2026-11-04") and result.loc["A", "days_counted"] == 4
    assert result.loc["A", "n_harm_current"] == 30.0 and result.loc["A", "n_harm_history_median"] == 10.0
    assert result.loc["A", "n_harm_ratio_to_median"] == pytest.approx(3.0) and result.loc["A", "n_harm_percentile"] == 100.0
    assert result.loc["A", "n_history_years"] == 6 and result.loc["A", "n_history_years_measured"] == 6
    assert month_to_date.month_to_date_vs_history(daily, "2026-12-05").empty
