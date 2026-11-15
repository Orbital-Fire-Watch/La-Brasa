"""Weather loading, checks (A5/A6), aggregation and derived features (features/weather.py), synthetic data only."""
import numpy as np
import pandas as pd
import pytest

from features import weather as wx


def synthetic_points(n_days=200, seed=0, start="2020-01-01"):
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, periods=n_days, freq="D")
    pts = [(40.125, -3.125), (40.375, -3.125), (42.125, -7.125)]
    rows = []
    for lat, lon in pts:
        t = 15 + 10 * np.sin(np.arange(n_days) / 58) + rng.normal(0, 2, n_days)
        rows.append(pd.DataFrame({
            "lat": lat, "lon": lon, "date": days, "t2m": t, "rh": np.clip(60 + rng.normal(0, 15, n_days), 5, 100),
            "wind": np.abs(rng.normal(12, 5, n_days)), "precip": np.where(rng.random(n_days) < 0.3, rng.gamma(2, 4, n_days), 0.0),
            "tmax": t + 3, "tmin": t - 6, "gust": np.abs(rng.normal(35, 10, n_days)), "td": t - 8,
            "fosberg": np.abs(rng.normal(10, 5, n_days)), "ffw": rng.random(n_days), "drought": rng.uniform(-4, 4, n_days)}))
    points = pd.DataFrame({"region_id": ["R1", "R1", "R2"], "lat": [p[0] for p in pts], "lon": [p[1] for p in pts],
                           "weight": [0.75, 0.25, 1.0]})
    return pd.concat(rows, ignore_index=True), points


def test_to_regions_weighted_mean_and_renormalised():
    pts, points = synthetic_points(5)
    pts.loc[(pts["lat"] == 40.375) & (pts["date"] == pts["date"].min()), "ffw"] = np.nan
    r = wx.to_regions(pts, points, ["t2m", "ffw"])
    d0 = pts["date"].min()
    a = pts[(pts["lat"] == 40.125) & (pts["date"] == d0)].iloc[0]
    b = pts[(pts["lat"] == 40.375) & (pts["date"] == d0)].iloc[0]
    row = r[(r["region_id"] == "R1") & (r["date"] == d0)].iloc[0]
    assert row["t2m"] == pytest.approx(0.75 * a["t2m"] + 0.25 * b["t2m"])
    assert row["ffw"] == pytest.approx(a["ffw"])         # weight of the missing point is dropped


def test_region_weather_has_fwi_and_derived_features():
    pts, points = synthetic_points()
    w = wx.add_derived(wx.region_weather(pts, points), train_end="2020-12-31")
    for c in ["ffmc", "dmc", "dc", "isi", "bui", "fwi", "vpd", "rain30", "rain90", "log_days_since_rain", "log_fwi",
              "fwi_anom", "dc_anom", "rain90_anom"]:
        assert c in w.columns
    assert (w["vpd"] >= 0).all() and (w["dc"] >= 0).all()
    assert len(w) == 2 * 200


def test_dryness_features_only_use_the_past():
    pts, points = synthetic_points()
    w1 = wx.add_derived(wx.region_weather(pts, points), train_end="2020-12-31")
    cut = pd.Timestamp("2020-05-01")
    pts2 = pts.copy()
    later = pts2["date"] > cut
    pts2.loc[later, "precip"] = 50.0
    pts2.loc[later, "t2m"] += 10
    w2 = wx.add_derived(wx.region_weather(pts2, points), train_end="2020-04-30")
    w1b = wx.add_derived(wx.region_weather(pts, points), train_end="2020-04-30")
    cols = ["rain30", "rain90", "log_days_since_rain", "ffmc", "dmc", "dc", "fwi", "vpd", "dc_anom", "fwi_anom"]
    a = w1b[w1b["date"] <= cut].reset_index(drop=True)[cols]
    b = w2[w2["date"] <= cut].reset_index(drop=True)[cols]
    pd.testing.assert_frame_equal(a, b)
    assert not w1[w1["date"] > cut]["dc"].equals(w2[w2["date"] > cut]["dc"])


def test_days_since_rain():
    flag = pd.Series([False, True, False, False, True, False])
    np.testing.assert_array_equal(wx._days_since(flag, cap=120), [120, 0, 1, 2, 0, 1])


def test_quality_report_detects_gaps_and_implausible_values():
    pts, points = synthetic_points(30)
    w = wx.add_derived(wx.region_weather(pts, points), train_end="2020-12-31")
    rep = wx.quality_report(pts, w, ["R1", "R2"], "2020-01-01", "2020-01-30")
    assert rep["A5"]["core"]["passed"] and rep["A6"]["passed"] and rep["A6"]["total"] == 0
    w_gap = w[~((w["region_id"] == "R2") & (w["date"] == pd.Timestamp("2020-01-10")))]
    pts_bad = pts.copy()
    pts_bad.loc[0, "rh"] = 120.0
    pts_bad.loc[1, "precip"] = -1.0
    rep2 = wx.quality_report(pts_bad, w_gap, ["R1", "R2"], "2020-01-01", "2020-01-30")
    assert rep2["A5"]["core"]["share_present"] == pytest.approx(1 - 1 / 60)
    assert rep2["gaps_region_year"]["core"] == {"R2_2020": 1}
    assert rep2["A6"]["violations"]["rh_point"] == 1 and rep2["A6"]["violations"]["precip_point"] == 1
    assert not rep2["A6"]["passed"]


def test_saturation_vapour_pressure():
    assert wx.saturation_vapour_pressure(np.array([20.0]))[0] == pytest.approx(2.338, abs=1e-3)
