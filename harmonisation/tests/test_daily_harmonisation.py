"""Tests der Tagesstufe: abgeleitete Spalten, Basiswahl, 0 gegen NA, Gewichte, Staerke, Fehlerbaender."""
from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from helpers import make_raw_hotspots
from pipeline.algorithms import daily_grid
from pipeline.algorithms.harmonise_daily import classify_strength, flag_big_fire_day
from pipeline.algorithms.hotspot_weights import weight_hotspots
from pipeline.algorithms.validation_kpis import measure_weight_identity
from pipeline.config import path_of
from pipeline.data_loading import derive_hotspot_columns as derive
from pipeline.io_utils import read_parquet


def status_for(dates: list[str], config: dict[str, Any]) -> pd.DataFrame:
    """Statustabelle fuer einzelne Tage mit den echten Betriebsfenstern der Satelliten (Aqua ab 04.07.2002, SNPP ab 20.01.2012)."""
    frame = pd.DataFrame({"date": pd.to_datetime(dates)})
    frame["terra_operating"] = True
    frame["aqua_operating"] = frame["date"] >= "2002-07-04"
    frame["snpp_operating"] = frame["date"].between("2012-01-20", "2026-11-02")
    for quantity in ("count", "frp"):
        frame[f"basis_{quantity}"] = daily_grid.choose_basis_per_day(frame, config, quantity)
    return frame


def test_hotspot_id_is_stable_and_unique(config: dict[str, Any]) -> None:
    """Gleiche Messung ergibt dieselbe ID, unabhaengig von Reihenfolge und anderen Zeilen. Verschiedene Messungen unterscheiden sich."""
    rows = [{"acq_time": "1300"}, {"acq_time": "1310"}, {"satellite": "Terra"}, {"latitude": 40.00001}]
    first = derive.add_hotspot_id(make_raw_hotspots(rows, config), config)["hotspot_id"]
    second = derive.add_hotspot_id(make_raw_hotspots(rows[::-1] + [{"frp": 99.0, "acq_date": "2020-01-01"}], config), config)["hotspot_id"]
    assert first.is_unique and set(first) <= set(second) and list(first) == list(second[:4][::-1])


def test_observation_date_puts_one_night_on_one_day(config: dict[str, Any]) -> None:
    """H2: Mit Sonnendatum landen Terra-Abend (22:30) und Aqua-Nacht (1:30 des Folgetags) auf demselben Tag."""
    rows = derive.add_acquisition_datetime(make_raw_hotspots([
        {"acq_date": "2015-07-01", "acq_time": "1330"}, {"acq_date": "2015-07-01", "acq_time": "2230", "satellite": "Terra"},
        {"acq_date": "2015-07-02", "acq_time": "0130"}], config))
    solar = derive.assign_observation_date(rows, "solar", config["daily"]["solar_day_shift_hours"])
    utc = derive.assign_observation_date(rows, "utc", config["daily"]["solar_day_shift_hours"])
    assert solar.dt.strftime("%Y-%m-%d").tolist() == ["2015-07-01"] * 3
    assert utc.dt.strftime("%Y-%m-%d").tolist() == ["2015-07-01", "2015-07-01", "2015-07-02"]


def test_cell_id_and_pixel_area(config: dict[str, Any]) -> None:
    """Zelle = floor(Koordinate / 0,25), auch westlich von Greenwich. Pixelflaeche = scan x track."""
    rows = make_raw_hotspots([{"latitude": 40.30, "longitude": -3.70, "scan": 1.5, "track": 1.2}], config)
    assert derive.add_cell_id(rows, config)["cell_id"][0] == "161_-15"
    assert derive.add_pixel_area(rows)["pixel_area_km2"][0] == pytest.approx(1.8)


def test_basis_follows_operating_satellites(config: dict[str, Any]) -> None:
    """Terra allein bis 03.07.2002, dann das Paar, VIIRS ab 20.01.2012, und kein MODIS mehr ab 2022."""
    status = status_for(["2002-07-03", "2002-07-04", "2012-01-19", "2012-01-20", "2021-12-31", "2026-11-05"], config)
    assert status["basis_count"].tolist() == ["terra_scaled", "modis_pair_scaled", "modis_pair_scaled", "viirs_measured",
                                              "viirs_measured", "none"]
    assert status["basis_frp"].tolist() == ["terra_scaled", "aqua_scaled", "aqua_scaled", "viirs_measured", "viirs_measured", "none"]


def test_drift_years_can_be_allowed_explicitly(config: dict[str, Any]) -> None:
    """Nur mit `allow_drift_modis` wird MODIS nach 2021 als Ersatz zugelassen."""
    allowed = copy.deepcopy(config)
    allowed["daily"]["allow_drift_modis"] = True
    assert status_for(["2026-11-05"], allowed)["basis_count"].tolist() == ["modis_pair_scaled"]


def test_in_series_and_weights_are_decided_per_satellite(config: dict[str, Any]) -> None:
    """Juli 2002: Aqua-Punkte vor dem Start der Aqua-Reihe zaehlen nicht. Januar 2012: VIIRS erst ab dem 20."""
    hotspots = make_raw_hotspots([
        {"acq_date": "2002-07-03", "satellite": "Terra"}, {"acq_date": "2002-07-03", "satellite": "Aqua"},
        {"acq_date": "2002-07-10", "satellite": "Aqua"}, {"acq_date": "2012-01-10", "satellite": "SNPP"},
        {"acq_date": "2012-01-25", "satellite": "SNPP"}, {"acq_date": "2012-01-25", "satellite": "Aqua"}], config)
    hotspots = hotspots.assign(obs_date=hotspots["acq_date"], region_id="ES30")
    factors = pd.DataFrame({"region_id": ["ES30"], **{f"k_{kind}_{variant}": [value] for kind, variant, value in [
        ("count", "pair", 3.0), ("count", "aqua", 6.0), ("count", "terra", 5.0), ("frp", "pair", 0.6), ("frp", "aqua", 1.2), ("frp", "terra", 1.4)]},
        **{f"k_count_{variant}_overall": [9.0] for variant in ("pair", "aqua", "terra")}})
    status = status_for(["2002-07-03", "2002-07-10", "2012-01-10", "2012-01-25"], config)
    weighted = weight_hotspots(hotspots, status, factors, config)
    assert weighted["in_series_n"].tolist() == [True, False, True, False, True, False]
    assert weighted["weight_n"].tolist() == [5.0, 0.0, 3.0, 0.0, 1.0, 0.0]
    assert weighted["weight_frp"].tolist() == [1.4, 0.0, 1.2, 0.0, 1.0, 0.0]


def test_zero_and_missing_are_distinguished(fixture_run: dict[str, Any]) -> None:
    """Vor dem Start von SNPP ist n_snpp leer, danach 0 an Tagen ohne Feuer. Tage ohne Basis haben keinen Wert."""
    daily = read_parquet(path_of(fixture_run["config"], "harmonised", "activity_daily_harmonised.parquet"))
    early, late = daily[daily["date"] == "2005-06-01"], daily[daily["date"] == "2015-01-15"]
    assert early["n_snpp"].isna().all() and early["n_terra"].notna().all() and early["n_harm"].notna().all()
    assert late["n_snpp"].notna().all() and (late["n_snpp"] == 0).any()
    without_basis = daily[daily["basis_count"] == "none"]
    assert len(without_basis) and without_basis["n_harm"].isna().all() and not without_basis["is_complete_day"].any()


def test_weights_sum_to_daily_values(fixture_run: dict[str, Any]) -> None:
    """Summe der Punktgewichte je Region und Tag = n_harm und frp_harm der Tagestabelle."""
    config = fixture_run["config"]
    daily = read_parquet(path_of(config, "harmonised", "activity_daily_harmonised.parquet"))
    hotspots = read_parquet(path_of(config, "harmonised", "hotspots_harmonised.parquet"))
    identity = measure_weight_identity(hotspots, daily)
    assert identity["max_relative_deviation"] < 1e-9 and identity["weight_on_days_without_value"] == 0.0


def test_date_columns_are_stored_as_dates(fixture_run: dict[str, Any]) -> None:
    """Tage stehen in den Dateien als reines Datum (DATE), nicht als Zeitstempel mit 00:00:00."""
    config = fixture_run["config"]
    for name, columns in (("activity_daily_harmonised", ["date"]), ("day_status", ["date"]), ("hotspots_harmonised", ["acq_date", "obs_date"])):
        schema = pq.read_schema(path_of(config, "harmonised", f"{name}.parquet"))
        assert [str(schema.field(column).type) for column in columns] == ["date32[day]"] * len(columns)
    assert str(pq.read_schema(path_of(config, "harmonised", "hotspots_harmonised.parquet")).field("acq_datetime_utc").type).startswith("timestamp")


def test_strength_class_and_big_fire_flag(config: dict[str, Any]) -> None:
    """Klassengrenzen gehoeren zur hoeheren Klasse. Umgerechnete Tage haben ihre eigene Grossfeuer-Schwelle."""
    frp = pd.Series([0.0, 9.9, 10.0, 100.0, 499.0, 500.0, np.nan])
    assert classify_strength(frp, config).tolist()[:6] == ["minor", "minor", "moderate", "strong", "strong", "extreme"]
    assert pd.isna(classify_strength(frp, config)[6])
    scaled_threshold = config["strength"]["big_fire_threshold_scaled_mw"]
    flags = flag_big_fire_day(pd.Series([99.0, 100.0, scaled_threshold, scaled_threshold - 1]), pd.Series([True, True, False, False]), config)
    assert flags.tolist() == [False, True, True, False]


def test_uncertainty_bands_are_ordered_and_wider_for_small_numbers(fixture_run: dict[str, Any]) -> None:
    """lo90 <= lo50 <= Wert <= hi50 <= hi90, und umgerechnete Tage haben breitere Baender als gemessene."""
    daily = read_parquet(path_of(fixture_run["config"], "harmonised", "activity_daily_harmonised.parquet")).dropna(subset=["n_harm"])
    assert (daily["n_harm_lo90"] <= daily["n_harm_lo50"]).all() and (daily["n_harm_lo50"] <= daily["n_harm"]).all()
    assert (daily["n_harm"] <= daily["n_harm_hi50"]).all() and (daily["n_harm_hi50"] <= daily["n_harm_hi90"]).all()
    assert set(daily["reliability"].unique()) <= {"measured", "converted_solid", "converted_rough"}
    assert (daily.loc[daily["basis_count"] == "viirs_measured", "reliability"] == "measured").all()
