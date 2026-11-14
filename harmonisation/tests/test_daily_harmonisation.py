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
from pipeline.algorithms.calibration_factors import select_calibration_days
from pipeline.algorithms.harmonise_daily import classify_strength, flag_big_fire_day
from pipeline.algorithms.hotspot_weights import weight_hotspots
from pipeline.algorithms.validation_kpis import measure_weight_identity
from pipeline.config import path_of
from pipeline.data_loading import derive_hotspot_columns as derive
from pipeline.io_utils import read_parquet


VIIRS_WINDOWS = {"snpp": ("2012-01-20", "2026-11-02"), "noaa20": ("2018-04-01", "2026-11-13"), "noaa21": ("2023-03-01", "2026-11-13")}


def status_for(dates: list[str], config: dict[str, Any]) -> pd.DataFrame:
    """Statustabelle fuer einzelne Tage mit den echten Betriebsfenstern (Aqua ab 04.07.2002, SNPP ab 20.01.2012, NOAA-20 ab 01.04.2018, NOAA-21 ab 01.03.2023)."""
    frame = pd.DataFrame({"date": pd.to_datetime(dates)})
    frame["terra_operating"] = True
    frame["aqua_operating"] = frame["date"] >= "2002-07-04"
    for key, (start, end) in VIIRS_WINDOWS.items():
        frame[f"{key}_operating"] = frame["date"].between(start, end)
    frame["viirs_operating"] = frame[[f"{key}_operating" for key in VIIRS_WINDOWS]].any(axis=1)
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
    """Terra allein bis 03.07.2002, dann das Paar, VIIRS ab 20.01.2012. Nach dem Ende von SNPP-NRT (02.11.2026) messen NOAA-20/21 weiter."""
    status = status_for(["2002-07-03", "2002-07-04", "2012-01-19", "2012-01-20", "2021-12-31", "2026-11-05", "2026-11-14"], config)
    assert status["basis_count"].tolist() == ["terra_scaled", "modis_pair_scaled", "modis_pair_scaled", "viirs_measured",
                                              "viirs_measured", "viirs_measured", "none"]
    assert status["basis_frp"].tolist() == ["terra_scaled", "aqua_scaled", "aqua_scaled", "viirs_measured", "viirs_measured",
                                            "viirs_measured", "none"]


def test_drift_years_can_be_allowed_explicitly(config: dict[str, Any]) -> None:
    """Nur mit `allow_drift_modis` wird MODIS nach 2021 als Ersatz zugelassen."""
    allowed = copy.deepcopy(config)
    allowed["daily"]["allow_drift_modis"] = True
    assert status_for(["2026-11-14"], allowed)["basis_count"].tolist() == ["modis_pair_scaled"]


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
    """Vor dem Start eines Satelliten ist seine Rohzahl leer, danach 0 an Tagen ohne Feuer. Tage ohne Basis haben keinen Wert."""
    daily = read_parquet(path_of(fixture_run["config"], "harmonised", "activity_daily_harmonised.parquet"))
    early, late = daily[daily["date"] == "2005-06-01"], daily[daily["date"] == "2015-01-15"]
    assert early[["n_snpp", "n_noaa20", "n_noaa21", "n_viirs"]].isna().all().all() and early["n_terra"].notna().all() and early["n_harm"].notna().all()
    assert late["n_snpp"].notna().all() and (late["n_snpp"] == 0).any() and late["n_noaa20"].isna().all()
    assert (late["n_viirs"] == late["n_snpp"]).all() and (late["n_harm"] == late["n_viirs"]).all()
    # Mit NOAA-20/21 bis 13.11.2026 hat jeder Tag der Reihe eine Basis; den Fall "none" prueft test_basis_follows_operating_satellites.
    without_basis = daily[daily["basis_count"] == "none"]
    assert without_basis["n_harm"].isna().all() and not without_basis["is_complete_day"].any()
    assert ((daily["basis_count"] == "none") == ~daily["is_complete_day"]).all()


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


def test_viirs_reference_is_mean_of_operating_satellites(config: dict[str, Any]) -> None:
    """n_viirs = Mittel der aktiven VIIRS-Satelliten. Aktiv ohne Feuer zaehlt 0, nicht aktiv zaehlt nicht mit, keiner aktiv = leer."""
    status = status_for(["2011-06-01", "2015-06-01", "2019-06-01", "2024-06-01"], config)
    sums = pd.DataFrame({"region_id": "ES30", "obs_date": pd.to_datetime(["2015-06-01", "2019-06-01", "2024-06-01", "2024-06-01", "2024-06-01"]),
                         "satellite": ["SNPP", "SNPP", "SNPP", "N20", "N21"], "n": [4.0, 4.0, 3.0, 6.0, 0.0], "frp": [40.0, 40.0, 30.0, 60.0, 0.0]})
    grid = daily_grid.build_daily_grid(sums[sums["n"] > 0], status, config)
    assert grid["n_viirs"].tolist()[1:] == [4.0, 2.0, 3.0] and pd.isna(grid["n_viirs"].iloc[0])
    assert grid["frp_viirs"].tolist()[1:] == [40.0, 20.0, 30.0]
    assert grid["n_noaa21"].isna().tolist() == [True, True, True, False] and grid["n_noaa21"].iloc[3] == 0.0


def test_weights_are_one_over_k_on_transition_days(config: dict[str, Any]) -> None:
    """Gewicht je VIIRS-Punkt = 1/k: 1 vor dem 01.04.2018, 1/2 ab NOAA-20, 1/3 ab NOAA-21 (01.03.2023)."""
    days = ["2018-03-31", "2018-04-01", "2023-02-28", "2023-03-01"]
    hotspots = make_raw_hotspots([{"acq_date": day, "satellite": satellite} for day in days for satellite in ("SNPP", "N20", "N21")], config)
    hotspots = hotspots.assign(obs_date=hotspots["acq_date"], region_id="ES30")
    factors = pd.DataFrame({"region_id": ["ES30"], **{f"k_{kind}_{variant}": [2.0] for kind in ("count", "frp") for variant in ("pair", "aqua", "terra")},
                            **{f"k_count_{variant}_overall": [2.0] for variant in ("pair", "aqua", "terra")}})
    weighted = weight_hotspots(hotspots, status_for(days, config), factors, config)
    expected = [1.0, 0.0, 0.0, 0.5, 0.5, 0.0, 0.5, 0.5, 0.0, 1 / 3, 1 / 3, 1 / 3]
    assert weighted["weight_n"].tolist() == pytest.approx(expected)
    assert weighted["in_series_n"].tolist() == [value > 0 for value in expected]


def test_calibration_keeps_days_before_noaa20(config: dict[str, Any]) -> None:
    """Kalibriertage brauchen VIIRS (irgendeinen Satelliten) und beide MODIS, nicht NOAA-20: sonst fielen 2012 bis 03/2018 heraus."""
    status = status_for(["2015-06-01", "2019-06-01", "2022-06-01"], config)
    sums = pd.DataFrame({"region_id": "ES30", "obs_date": pd.to_datetime(["2015-06-01"]), "satellite": ["SNPP"], "n": [3.0], "frp": [9.0]})
    days = select_calibration_days(daily_grid.build_daily_grid(sums, status, config), config)
    assert days["date"].dt.strftime("%Y-%m-%d").tolist() == ["2015-06-01", "2019-06-01"]


def test_renamed_reference_columns(fixture_run: dict[str, Any]) -> None:
    """Die Referenz heisst n_viirs / frp_viirs / viirs_operating. SNPP bleibt als Rohzahl, das Manifest nennt die Schema-Version."""
    config = fixture_run["config"]
    daily_columns = pq.read_schema(path_of(config, "harmonised", "activity_daily_harmonised.parquet")).names
    status_columns = pq.read_schema(path_of(config, "harmonised", "day_status.parquet")).names
    assert {"n_viirs", "frp_viirs", "n_snpp", "n_noaa20", "n_noaa21", "frp_noaa20", "frp_noaa21"} <= set(daily_columns)
    assert {"viirs_operating", "snpp_operating", "noaa20_operating", "noaa21_operating"} <= set(status_columns)
    hotspots = read_parquet(path_of(config, "harmonised", "hotspots_harmonised.parquet"))
    assert {"N20", "N21"} <= set(hotspots["satellite"]) and set(hotspots.loc[hotspots["satellite"].isin(["N20", "N21"]), "sensor"]) == {"VIIRS"}
    assert config["schema_version"] == 2


def test_h3_cell_matches_coordinates(config: dict[str, Any]) -> None:
    """h3_cell ist die H3-Zelle der Pixelmitte in der konfigurierten Aufloesung; ihr Mittelpunkt liegt nahe am Punkt."""
    import h3
    rows = derive.add_h3_cell(make_raw_hotspots([{"latitude": 40.4168, "longitude": -3.7038}, {"latitude": 37.389, "longitude": -5.984}], config), config)
    assert rows["h3_cell"].tolist() == [h3.latlng_to_cell(40.4168, -3.7038, 8), h3.latlng_to_cell(37.389, -5.984, 8)]
    assert all(h3.get_resolution(cell) == config["grid"]["h3_resolution"] for cell in rows["h3_cell"])
    lat, lon = h3.cell_to_latlng(rows["h3_cell"].iloc[0])
    assert abs(lat - 40.4168) < 0.01 and abs(lon + 3.7038) < 0.01
