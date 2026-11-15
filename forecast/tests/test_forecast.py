"""Offline tests for features, models, scores and the output contract (synthetic data, no network)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import contract
from evaluate import bootstrap_skill_by_year, brier, ece, pr_auc, roc_auc, rps, skill
from features.climatology import day_of_year_noleap, doy_climatology, lookup, smooth_circular
from features.fire_history import ISSUE_FEATURES, issue_features, lead_pairs, load_daily
from models import weekly
from models.logistic import Design, fit_logistic, fit_multinomial, predict_logistic, predict_multinomial

HERE = Path(__file__).resolve().parent.parent


# --- synthetic harmonised tables -------------------------------------------------------------------
def _write_harmonised(tmp: Path, days: int = 120, seed: int = 1) -> Path:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2012-01-20", periods=days, freq="D")
    rows = []
    for r in ["AA1", "BB1", "CC1"]:
        frp = np.where(rng.random(days) < 0.3, rng.lognormal(2, 2, days), 0.0)
        n_snpp = np.where(frp > 0, rng.integers(0, 4, days), 0).astype(float)
        rows.append(pd.DataFrame({
            "region_id": r, "region_name": r, "date": dates.date, "basis_count": "viirs_measured",
            "is_complete_day": True, "possible_gap": False, "big_fire_day": frp >= 100, "n_snpp": n_snpp,
            "frp_snpp": frp, "frp_harm": frp, "strength_class": "minor"}))
    act = pd.concat(rows, ignore_index=True)
    act.loc[5, "possible_gap"] = True
    act.loc[7, "n_snpp"] = np.nan
    ds = pd.DataFrame({"date": dates.date, "snpp_operating": True, "is_provisional": False})
    ds.loc[days - 3:, "is_provisional"] = True
    act.to_parquet(tmp / "activity_daily_harmonised.parquet", index=False)
    ds.to_parquet(tmp / "day_status.parquet", index=False)
    return tmp


@pytest.fixture
def daily_df(tmp_path):
    return load_daily(_write_harmonised(tmp_path), "2012-01-20")


NN = {"AA1": ["BB1", "CC1"], "BB1": ["AA1", "CC1"], "CC1": ["AA1", "BB1"]}


# --- climatology ---------------------------------------------------------------------------------
def test_day_of_year_noleap():
    d = pd.Series(pd.to_datetime(["2020-02-28", "2020-02-29", "2020-03-01", "2021-03-01", "2020-12-31"]))
    assert day_of_year_noleap(d).tolist() == [59, 59, 60, 60, 365]


def test_smooth_circular_wraps_year_end():
    v = np.zeros((1, 365)); v[0, 0] = 15.0
    s = smooth_circular(v, 7)
    assert s[0, 364] == pytest.approx(1.0) and s[0, 7] == pytest.approx(1.0) and s[0, 8] == 0


def test_climatology_uses_only_masked_rows():
    region = pd.Series(["A"] * 730)
    doy = np.r_[np.arange(1, 366), np.arange(1, 366)]
    v = pd.Series(np.r_[np.zeros(365), np.ones(365)])
    train = np.r_[np.ones(365, bool), np.zeros(365, bool)]
    c = doy_climatology(region, doy, v, train, 7, clip=None)
    assert np.allclose(c.to_numpy(), 0)
    assert np.isnan(lookup(c, pd.Series(["X"]), np.array([5])))[0]


# --- targets and features ----------------------------------------------------------------------------
def test_targets_only_usable_rows_and_fire_uses_snpp(daily_df):
    d = daily_df
    assert d.loc[~d["usable"], "big"].isna().all()
    assert np.isnan(d.loc[7, "fire"])                       # n_snpp missing -> no fire target
    ok = d["fire"].notna()
    assert ((d.loc[ok, "fire"] == 1) == (d.loc[ok, "n_snpp"] > 0)).all()
    assert d["is_provisional"].sum() == 3 * 3


def test_features_do_not_look_ahead(daily_df):
    d = daily_df
    cut = d["date"].sort_values().iloc[len(d) // 2]
    f1 = issue_features(d, NN)
    d2 = d.copy()
    later = d2["date"] > cut
    d2.loc[later, ["logfrp", "big", "fire"]] = 1.0
    f2 = issue_features(d2, NN)
    keep = (d["date"] <= cut).to_numpy()
    assert np.array_equal(f1[keep].to_numpy(), f2[keep].to_numpy(), equal_nan=True)
    assert list(f1.columns) == ISSUE_FEATURES


def test_lead_pairs_align_target_day(daily_df):
    d = daily_df
    f = issue_features(d, NN)
    p = lead_pairs(d, f, "big", 3)
    r = d["region_id"] == "AA1"
    dd, pp = d[r].reset_index(drop=True), p[r.to_numpy()].reset_index(drop=True)
    assert (pp["target_date"] == pp["issue_date"] + pd.Timedelta(days=3)).all()
    assert np.array_equal(pp["y"].to_numpy()[:-3], dd["big"].to_numpy()[3:], equal_nan=True)
    assert pp["y"].iloc[-3:].isna().all()


# --- models ----------------------------------------------------------------------------------------
def test_logistic_recovers_coefficients():
    rng = np.random.default_rng(0)
    X = np.c_[np.ones(20000), rng.normal(size=(20000, 2))]
    w_true = np.array([-1.0, 1.5, -0.5])
    y = (rng.random(20000) < predict_logistic(X, w_true)).astype(float)
    w = fit_logistic(X, y, np.zeros(3))
    assert np.allclose(w, w_true, atol=0.08)


def test_design_standardises_and_imputes():
    df = pd.DataFrame({"a": [1.0, 3.0, np.nan], "r": ["x", "y", "x"]})
    des = Design(continuous=["a"], categorical={"r": ["x", "y"]}).fit(df)
    X = des.matrix(df)
    assert X.shape == (3, 4) and X[2, 1] == 0.0 and X[:, 2].tolist() == [1, 0, 1]
    assert des.penalty(1.0, 5.0).tolist() == [0.0, 1.0, 5.0, 5.0]


def test_multinomial_probabilities_and_fit():
    rng = np.random.default_rng(1)
    X = np.c_[np.ones(6000), rng.normal(size=6000)]
    W_true = np.array([[0.2, -0.3], [1.0, -1.0]])
    P = predict_multinomial(X, W_true)
    y = np.array([rng.choice(3, p=p) for p in P])
    W = fit_multinomial(X, y, 3, np.zeros(2))
    assert np.allclose(predict_multinomial(X, W).sum(axis=1), 1)
    assert np.allclose(W, W_true, atol=0.15)


def test_weekly_ties_go_to_lower_class():
    t = pd.DataFrame({"region_id": ["A"], "woy": [10], "q1": [0.0], "q2": [0.0]}).set_index(["region_id", "woy"])
    wc = weekly.WeekClimatology(t)
    weeks = pd.DataFrame({"region_id": ["A", "A"], "woy": [10, 10], "activity": [0.0, 0.5]})
    assert wc.classes(weeks).tolist() == [0, 2]


# --- scores -------------------------------------------------------------------------------------------
def test_brier_and_skill_by_hand():
    y = np.array([1, 0, 0, 1.0]); p = np.array([0.8, 0.1, 0.3, 0.6]); c = np.full(4, 0.5)
    assert brier(y, p) == pytest.approx((0.04 + 0.01 + 0.09 + 0.16) / 4)
    assert skill(brier(y, p), brier(y, c)) == pytest.approx(1 - 0.075 / 0.25)


def test_auc_pr_auc_ece_rps():
    y = np.array([0, 0, 1, 1.0]); s = np.array([0.1, 0.2, 0.8, 0.9])
    assert roc_auc(y, s) == 1.0 and pr_auc(y, s) == 1.0
    assert ece(np.array([0, 1, 0, 1.0]), np.full(4, 0.5), n_bins=2) == pytest.approx(0)
    assert rps(np.array([2]), np.array([[0.0, 0.0, 1.0]]))[0] == 0
    assert rps(np.array([0]), np.array([[0.0, 0.0, 1.0]]))[0] == pytest.approx(1.0)


def test_bootstrap_is_reproducible():
    years = np.repeat([2022, 2023, 2024], 10)
    m, r = np.linspace(0, 1, 30), np.linspace(0.5, 1.5, 30)
    assert bootstrap_skill_by_year(years, m, r, 200, 7) == bootstrap_skill_by_year(years, m, r, 200, 7)


# --- contract ----------------------------------------------------------------------------------------
RC = {"ratio_low": 0.67, "ratio_elevated": 1.5, "ratio_high": 3.0, "ratio_very_high": 6.0,
      "p_high": 0.25, "p_very_high": 0.5, "p_floor": 0.02}


def test_risk_class_rules():
    p = np.array([0.005, 0.01, 0.05, 0.05, 0.05, 0.05, 0.3, 0.6, 0.015])
    ratio = np.array([0.5, 1.0, 0.5, 1.0, 2.0, 4.0, 1.0, 1.0, 10.0])
    assert contract.risk_class(p, ratio, RC).tolist() == [
        "low", "normal", "low", "normal", "elevated", "high", "high", "very_high", "normal"]


def test_readme_documents_contract_columns():
    readme = (HERE / "README.md").read_text()
    for col in contract.DAILY_COLUMNS + contract.WEEKLY_COLUMNS:
        assert f"`{col}`" in readme, col
