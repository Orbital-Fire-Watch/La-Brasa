"""Step 5 and the improvements: forecast-error perturbation, bias correction, seasonal curve with shrinkage,
holidays, own Fosberg index, Open-Meteo daily values. Synthetic data only, no internet."""
import numpy as np
import pandas as pd
import pytest

from features import weather as wx
from features.calendar import easter, is_holiday
from features.climatology import doy_climatology_shrunk, smooth_gauss_circular
from features.forecast_errors import dew_point
from features.open_meteo import daily_noon
from features.perturb import BASE, BiasCorrection, ErrorModel, Perturber
from tests.test_weather_features import synthetic_points


@pytest.fixture(scope="module")
def weather():
    pts, points = synthetic_points(n_days=150)
    return wx.add_derived(wx.region_weather(pts, points), train_end="2020-12-31")


def zero_errors(regions, lead_days=range(8)):
    rows = [{"region_id": r, "lead_day": ld, "era5_wet": wet, "month": m, **{f"e_{v}": 0.0 for v in BASE},
             "precip_era5": 1.0} for r in regions for ld in lead_days for wet in (False, True) for m in range(1, 13)
            for _ in range(10)]
    return pd.DataFrame(rows)


def test_zero_errors_reproduce_the_analysed_features(weather):
    per = Perturber(weather)
    em = ErrorModel(zero_errors(["R1", "R2"]), {v: 1.0 for v in BASE})
    rows = weather[(weather["date"] >= "2020-03-01") & (weather["date"] <= "2020-04-01")]
    for lead in (1, 4):
        f = per.noisy(rows["region_id"].to_numpy(), rows["date"], lead, em, np.random.default_rng(0))
        tgt = weather.set_index(["region_id", "date"]).reindex(
            pd.MultiIndex.from_arrays([rows["region_id"], rows["date"] + pd.Timedelta(days=lead)]))
        for c in ("ffmc", "dmc", "dc", "log_fwi", "rh", "rain30", "fwi_anom", "log_days_since_rain", "vpd"):
            np.testing.assert_allclose(f[c].to_numpy(), tgt[c].to_numpy(), rtol=1e-9, atol=1e-9, err_msg=c)


def test_errors_change_the_target_features_and_rain_dries_less(weather):
    per = Perturber(weather)
    err = zero_errors(["R1", "R2"])
    err["e_precip"] = 20.0                          # every forecast day gets 20 mm more rain
    em = ErrorModel(err, {v: 1.0 for v in BASE})
    rows = weather[(weather["date"] >= "2020-05-01") & (weather["date"] <= "2020-05-20")]
    f = per.noisy(rows["region_id"].to_numpy(), rows["date"], 5, em, np.random.default_rng(0))
    tgt = weather.set_index(["region_id", "date"]).reindex(
        pd.MultiIndex.from_arrays([rows["region_id"], rows["date"] + pd.Timedelta(days=5)]))
    assert (f["dc"].to_numpy() <= tgt["dc"].to_numpy() + 1e-9).all()
    assert (f["rain30"].to_numpy() >= tgt["rain30"].to_numpy() + 99).all()
    assert (f["log_days_since_rain"].to_numpy() == 0).all()


def test_missing_days_give_nan(weather):
    per = Perturber(weather)
    em = ErrorModel(zero_errors(["R1", "R2"]), {v: 1.0 for v in BASE})
    last = weather["date"].max()
    f = per.noisy(np.array(["R1"]), pd.Series([last]), 3, em, np.random.default_rng(0))
    assert f.isna().all(axis=None)


def test_bias_correction_removes_mean_error():
    err = zero_errors(["R1"])
    err["e_t2m"] = 1.5
    bc = BiasCorrection.fit(err)
    out = bc.apply({"t2m": np.array([20.0, 21.0]), "precip": np.array([2.0, 0.0])}, np.array(["R1", "R1"]),
                   np.array([7, 7]), 3)
    np.testing.assert_allclose(out["t2m"], [18.5, 19.5])


def test_error_model_scales_beyond_day_7():
    err = zero_errors(["R1"])
    err.loc[err["lead_day"] == 7, "e_t2m"] = np.tile([-1.0, 1.0], (err["lead_day"] == 7).sum() // 2)
    em = ErrorModel(err, {"t2m": 1.5, **{v: 1.0 for v in BASE if v != "t2m"}})
    rng = np.random.default_rng(0)
    e7 = em.draw(np.array(["R1"] * 400), 7, np.zeros(400, bool), np.full(400, 7), rng)["t2m"]
    e9 = em.draw(np.array(["R1"] * 400), 9, np.zeros(400, bool), np.full(400, 7), rng)["t2m"]
    assert np.std(e9) == pytest.approx(np.std(e7) * 1.5 ** 2, rel=0.05)


def test_shrunk_climatology_is_smooth_and_pulled_to_the_prior():
    days = pd.date_range("2012-01-01", "2021-12-31", freq="D")
    from features.climatology import day_of_year_noleap
    doy = day_of_year_noleap(pd.Series(days))
    y = np.zeros(len(days))
    y[np.flatnonzero(doy == 200)[0]] = 1.0          # one single event in ten years
    region = pd.Series(["R"] * len(days))
    c = doy_climatology_shrunk(region, doy, pd.Series(y), np.ones(len(days), bool), 10, 30, 20, clip=None)
    v = c.loc["R"].to_numpy()
    assert v.argmax() + 1 == 200
    assert np.max(np.abs(np.diff(v))) < 0.002          # no hard edges
    assert v[199] < 1 / 10                              # pulled below the raw rate of that day
    assert smooth_gauss_circular(np.ones((1, 365)), 10) == pytest.approx(np.ones((1, 365)))


def test_holidays():
    assert easter(2025).isoformat() == "2025-04-20" and easter(2026).isoformat() == "2026-04-05"
    h = is_holiday(pd.Series(["ES11", "PT11", "FRJ1", "ES11", "PT17"]),
                   pd.Series(pd.to_datetime(["2025-10-12", "2025-06-10", "2025-07-14", "2025-07-14", "2026-04-03"])))
    np.testing.assert_array_equal(h, [1, 1, 1, 0, 1])     # last: Good Friday in Portugal


def test_fosberg_and_dew_point():
    assert wx.fosberg_index(np.array([30.0]), np.array([15.0]), np.array([30.0]))[0] > \
        wx.fosberg_index(np.array([15.0]), np.array([80.0]), np.array([5.0]))[0]
    assert dew_point(np.array([20.0]), np.array([100.0]))[0] == pytest.approx(20.0, abs=0.01)
    assert dew_point(np.array([20.0]), np.array([50.0]))[0] == pytest.approx(9.3, abs=0.2)


def test_open_meteo_daily_values_use_the_24h_window_to_noon():
    t = pd.date_range("2026-01-01 00:00", "2026-01-03 23:00", freq="h")
    h = pd.DataFrame({"time": t, "lat": 40.0, "lon": -3.0, "temperature_2m": np.arange(len(t), dtype=float),
                      "relative_humidity_2m": 50.0, "wind_speed_10m": 10.0, "precipitation": 1.0,
                      "wind_gusts_10m": 20.0, "dew_point_2m": 0.0})
    d = daily_noon(h)
    row = d[d["validdate"] == pd.Timestamp("2026-01-02 12:00", tz="UTC")].iloc[0]
    assert row["precip_24h:mm"] == 24.0                      # 01-01 13:00 .. 01-02 12:00
    assert row["t_2m:C"] == 36.0 and row["t_max_2m_24h:C"] == 36.0 and row["t_min_2m_24h:C"] == 13.0
