"""Forecast pipeline: evaluate the models, fit the production models and write today's forecast.

Run from La-Brasa/forecast:
    .venv/bin/python run_forecast.py all --no-weather      # step 1: everything without weather
    .venv/bin/python run_forecast.py all --no-weather --skip-tests

Reads data/harmonised/. Writes data/forecast/: forecast_daily, forecast_weekly, forecast_skill (+ csv/),
forecast_evaluation.json, forecast_kpi_report.json, manifest.json, models/*.json.
Exit code 1 if a mandatory KPI fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import contract
from evaluate import binary_scores, bootstrap_skill_by_year, ece, rps
from features.climatology import doy_climatology
from features.fire_history import issue_features, lead_pairs, load_daily, region_neighbours
from models import daily, weekly

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
HARM = REPO / "data" / "harmonised"
OUT = REPO / "data" / "forecast"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def code_fingerprint() -> str:
    files = sorted(p for p in HERE.rglob("*.py") if ".venv" not in p.parts and "tests" not in p.parts
                   and "analysis" not in p.parts)
    return hashlib.sha256(b"".join(p.read_bytes() for p in files)).hexdigest()[:16]


def week_col(mc: dict) -> str:
    """Daily column summed into the weekly activity (config model.weekly.activity_frp)."""
    return "logfrp_snpp" if mc["weekly"].get("activity_frp", "frp_harm") == "frp_snpp" else "logfrp"


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (pd.Timestamp,)):
        return str(x.date())
    return x


# =============================================================================================
class Pipeline:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.mc = cfg["model"]
        self.train_end = pd.Timestamp(self.mc["train_end"])
        self.test_start = pd.Timestamp(self.mc["test_start"])
        self.d = load_daily(HARM, self.mc["viirs_start"])
        self.last_archive = self.d.loc[~self.d["is_provisional"], "date"].max()
        self.issue_date = self.d["date"].max()
        self.regions = sorted(self.d["region_id"].unique())
        self.nn = region_neighbours(HARM, self.mc["train_end"], self.mc["neighbours"])
        self.feats = issue_features(self.d, self.nn)
        self.ev: dict = {"daily": {}, "daily_region": {}, "weekly": {}, "loyo": {}, "risk_class_test": {}}
        self.skill_rows: list[dict] = []
        self.use_model: dict = {}          # (target, lead, region or 'all') -> bool
        self.models_out: dict = {}

    # --- helpers -----------------------------------------------------------------------------
    def climatology(self, target: str, mask: np.ndarray, clip=1e-4) -> pd.DataFrame:
        d = self.d
        return doy_climatology(d["region_id"], d["doy"].to_numpy(), d[target], mask & d[target].notna().to_numpy(),
                               self.mc["clim_window_days"], clip=clip)

    def pairs(self, target: str, lead: int, clim: pd.DataFrame) -> pd.DataFrame:
        return daily.add_climatology(lead_pairs(self.d, self.feats, target, lead), clim)

    def fit_daily(self, tr: pd.DataFrame, target: str, lead: int) -> daily.DailyModel:
        mc = self.mc
        if mc.get("platt_calibration", False):
            return daily.train_calibrated(tr, target, lead, self.regions, mc["l2_continuous"], mc["l2_region"],
                                          mc["calib_years"])
        return daily.train(tr, target, lead, self.regions, mc["l2_continuous"], mc["l2_region"])

    # --- evaluation: train 2012-2021, test 2022 .. last archive day ------------------------------
    def evaluate_daily(self) -> None:
        mc = self.mc
        train_rows = (self.d["date"] <= self.train_end).to_numpy()
        for target in mc["targets"]:
            clim = self.climatology(target, train_rows)
            for lead in mc["leads"]:
                pr = self.pairs(target, lead, clim)
                ok = pr["y"].notna()
                tr = pr[ok & (pr["target_date"] <= self.train_end)]
                te = pr[ok & (pr["target_date"] >= self.test_start) & (pr["target_date"] <= self.last_archive)]
                model = self.fit_daily(tr, target, lead)
                thr = float(np.quantile(daily.predict(model, tr), 1 - mc["warn_share"]))
                p, c, y = daily.predict(model, te), te["clim"].to_numpy(), te["y"].to_numpy()
                sc = binary_scores(y, p, c, thr)
                years = te["target_date"].dt.year.to_numpy()
                sc["ci_lo"], sc["ci_hi"] = bootstrap_skill_by_year(years, (p - y) ** 2, (c - y) ** 2,
                                                                   mc["bootstrap"], mc["seed"])
                self.ev["daily"][f"{target}_{lead}"] = sc
                use_all = bool(sc["bss_vs_climatology"] > 0 and sc["ci_lo"] >= 0)
                self.use_model[(target, lead, "all")] = use_all
                self.skill_rows.append(self._skill_row("daily", target, lead, "all", sc, use_all))
                # per region
                for r, g in te.assign(p=p).groupby("region_id"):
                    yr, pr_, cr = g["y"].to_numpy(), g["p"].to_numpy(), g["clim"].to_numpy()
                    scr = binary_scores(yr, pr_, cr, thr)
                    scr["ci_lo"], scr["ci_hi"] = bootstrap_skill_by_year(
                        g["target_date"].dt.year.to_numpy(), (pr_ - yr) ** 2, (cr - yr) ** 2, mc["bootstrap"], mc["seed"])
                    if scr["n_events"] >= mc["min_region_events"]:
                        use_r = bool(scr["bss_vs_climatology"] > 0 and scr["ci_lo"] >= 0)
                    else:
                        use_r = use_all
                    self.use_model[(target, lead, r)] = use_r
                    self.skill_rows.append(self._skill_row("daily", target, lead, r, scr, use_r))
                if target == "big" and lead in (1, 5, 10):
                    rc = contract.risk_class(p, p / c, self.cfg["risk_class"])
                    tab = pd.DataFrame({"cls": rc, "y": y}).groupby("cls")["y"].agg(["size", "mean"])
                    tab["share"] = tab["size"] / len(y)
                    self.ev["risk_class_test"][lead] = tab.reindex(contract.RISK_CLASSES).to_dict("index")
            print(f"  evaluated daily target={target}", flush=True)

    def _skill_row(self, product, target, lead, region, sc, use) -> dict:
        return {"product": product, "target": daily.TARGETS.get(target, target), "lead": lead, "region_id": region,
                "bss_vs_climatology": sc.get("bss_vs_climatology"), "ci_lo": sc.get("ci_lo"), "ci_hi": sc.get("ci_hi"),
                "auc": sc.get("auc"), "pr_auc": sc.get("pr_auc"), "ece": sc.get("ece"), "hit_rate": sc.get("hit_rate"),
                "false_alarm_ratio": sc.get("false_alarm_ratio"), "n_events": sc.get("n_events"),
                "use_model": use, "skill_basis": "no_weather"}

    def evaluate_loyo(self) -> None:
        """Leave one year out, big_fire_day, lead 1 (training years include later years)."""
        d = self.d
        years = sorted(d.loc[~d["is_provisional"] & d["big"].notna(), "date"].dt.year.unique())
        out = {}
        for yr in years:
            mask = ((d["date"].dt.year != yr) & ~d["is_provisional"]).to_numpy()
            clim = self.climatology("big", mask)
            pr = self.pairs("big", 1, clim)
            ok = pr["y"].notna() & ~pr["target_provisional"].astype(bool)
            tr = pr[ok & (pr["target_date"].dt.year != yr)]
            te = pr[ok & (pr["target_date"].dt.year == yr)]
            m = self.fit_daily(tr, "big", 1)
            p, c, y = daily.predict(m, te), te["clim"].to_numpy(), te["y"].to_numpy()
            out[int(yr)] = {"gain": 1 - np.mean((p - y) ** 2) / np.mean((c - y) ** 2), "n_events": int(y.sum())}
        self.ev["loyo"] = out
        print("  evaluated leave-one-year-out", flush=True)

    def evaluate_weekly(self) -> None:
        mc, wc = self.mc, self.mc["weekly"]
        d = self.d
        weeks = weekly.weekly_table(d, week_col(self.mc))
        wk_train = (weeks["week_start"] + pd.Timedelta(days=6) <= self.train_end).to_numpy()
        wclim = weekly.fit_week_climatology(weeks, wk_train, wc["window_weeks"])
        lclim = self.climatology("logfrp", (d["date"] <= self.train_end).to_numpy(), clip=None)
        sundays = (d["date"].dt.day_of_week == 6).to_numpy()
        shares_train = weeks[wk_train & weeks["complete"]].assign(c=lambda w: wclim.classes(w))["c"].value_counts(normalize=True)
        self.ev["weekly_class_shares_train"] = {int(k): float(v) for k, v in shares_train.sort_index().items()}
        for k in wc["weeks_ahead"]:
            pw = weekly.week_pairs(d, self.feats, weeks, wclim, lclim, k, sundays)
            end = pw["week_start"] + pd.Timedelta(days=6)
            tr = pw[pw["complete"] & (end <= self.train_end)]
            te = pw[pw["complete"] & (pw["week_start"] >= self.test_start) & (end <= self.last_archive)]
            m = weekly.train(tr, k, wc["l2"])
            P = weekly.predict(m, te)
            C = te[["clim_p_below", "clim_p_normal", "clim_p_above"]].to_numpy()
            yc = te["y_class"].to_numpy()
            r_m, r_c = rps(yc, P), rps(yc, C)
            sc = {"n": int(len(te)), "rps": float(r_m.mean()), "rps_clim": float(r_c.mean()),
                  "rpss": float(1 - r_m.mean() / r_c.mean()),
                  "ece_p_above": ece((yc == 2).astype(float), P[:, 2]),
                  "ece_p_above_clim": ece((yc == 2).astype(float), C[:, 2]),
                  "observed_shares": [float((yc == c).mean()) for c in range(3)],
                  "mean_p": P.mean(axis=0).tolist()}
            sc["ci_lo"], sc["ci_hi"] = bootstrap_skill_by_year(te["week_start"].dt.year.to_numpy(), r_m, r_c,
                                                               mc["bootstrap"], mc["seed"])
            use = bool(sc["rpss"] > 0 and sc["ci_lo"] >= 0)
            self.use_model[("week", k, "all")] = use
            self.ev["weekly"][k] = sc
            self.skill_rows.append({"product": "weekly", "target": "week_activity", "lead": k, "region_id": "all",
                                    "bss_vs_climatology": sc["rpss"], "ci_lo": sc["ci_lo"], "ci_hi": sc["ci_hi"],
                                    "auc": np.nan, "pr_auc": np.nan, "ece": sc["ece_p_above"], "hit_rate": np.nan,
                                    "false_alarm_ratio": np.nan, "n_events": int((yc == 2).sum()),
                                    "use_model": use, "skill_basis": "no_weather"})
        print("  evaluated weekly", flush=True)

    # --- production fit on all archive data, forecast for the latest day -------------------------
    def predict_daily(self) -> pd.DataFrame:
        mc = self.mc
        d = self.d
        archive = (~d["is_provisional"]).to_numpy()
        rng = np.random.default_rng(mc["seed"])
        out = {}
        for target in mc["targets"]:
            clim = self.climatology(target, archive)
            for lead in mc["leads"]:
                pr = self.pairs(target, lead, clim)
                tr = pr[pr["y"].notna() & ~pr["target_provisional"].fillna(True).astype(bool)]
                live = pr[pr["issue_date"] == self.issue_date].copy()
                m = self.fit_daily(tr, target, lead)
                self.models_out[f"daily_{target}_lead{lead}"] = m.to_dict()
                live["p"] = daily.predict(m, live)
                if target == "big":
                    yrs = tr["target_date"].dt.year.to_numpy()
                    uniq = np.unique(yrs)
                    by_year = {y: np.flatnonzero(yrs == y) for y in uniq}
                    sims = []
                    for _ in range(mc["bootstrap_models"]):
                        pick = rng.choice(uniq, size=len(uniq), replace=True)
                        idx = np.concatenate([by_year[y] for y in pick])
                        sims.append(daily.predict(self.fit_daily(tr.iloc[idx], target, lead), live))
                    lo, hi = np.quantile(np.array(sims), mc["band_quantiles"], axis=0)
                    live["lo"], live["hi"] = np.minimum(lo, live["p"]), np.maximum(hi, live["p"])
                use = np.array([self.use_model.get((target, lead, r), self.use_model.get((target, lead, "all"), False))
                                for r in live["region_id"]])
                live["use"] = use
                out[(target, lead)] = live
            print(f"  fitted production daily target={target}", flush=True)
        rows = []
        for lead in mc["leads"]:
            b, f = out[("big", lead)].set_index("region_id"), out[("fire", lead)].set_index("region_id")
            for r in self.regions:
                pb = b.at[r, "p"] if b.at[r, "use"] else b.at[r, "clim"]
                lo = b.at[r, "lo"] if b.at[r, "use"] else pb
                hi = b.at[r, "hi"] if b.at[r, "use"] else pb
                pf = f.at[r, "p"] if f.at[r, "use"] else f.at[r, "clim"]
                rows.append({"region_id": r, "issue_date": self.issue_date.date(), "target_date": b.at[r, "target_date"].date(),
                             "lead_days": lead, "p_big_fire_day": pb, "p_fire_day": pf,
                             "p_clim_big_fire_day": b.at[r, "clim"], "p_clim_fire_day": f.at[r, "clim"],
                             "risk_ratio": pb / b.at[r, "clim"], "p_big_fire_day_lo": min(lo, pb), "p_big_fire_day_hi": max(hi, pb),
                             "source": "model" if b.at[r, "use"] else "climatology", "model_version": mc["version"]})
        df = pd.DataFrame(rows)
        df["risk_class"] = contract.risk_class(df["p_big_fire_day"], df["risk_ratio"], self.cfg["risk_class"])
        return df[contract.DAILY_COLUMNS]

    def predict_weekly(self) -> pd.DataFrame:
        mc, wc = self.mc, self.mc["weekly"]
        d = self.d
        weeks = weekly.weekly_table(d, week_col(self.mc))
        wk_arch = ((weeks["week_start"] + pd.Timedelta(days=6) <= self.last_archive) & ~weeks["provisional"]).to_numpy()
        wclim = weekly.fit_week_climatology(weeks, wk_arch, wc["window_weeks"])
        lclim = self.climatology("logfrp", (~d["is_provisional"]).to_numpy(), clip=None)
        sundays = (d["date"].dt.day_of_week == 6).to_numpy()
        live_mask = (d["date"] == self.issue_date).to_numpy()
        rows = []
        for k in wc["weeks_ahead"]:
            pw = weekly.week_pairs(d, self.feats, weeks, wclim, lclim, k, sundays)
            tr = pw[pw["complete"] & ~pw["provisional"] & (pw["week_start"] + pd.Timedelta(days=6) <= self.last_archive)]
            m = weekly.train(tr, k, wc["l2"])
            self.models_out[f"weekly_week{k}"] = m.to_dict()
            live = weekly.week_pairs(d, self.feats, weeks, wclim, lclim, k, live_mask)
            P = weekly.predict(m, live)
            C = live[["clim_p_below", "clim_p_normal", "clim_p_above"]].to_numpy()
            use = self.use_model.get(("week", k, "all"), False)
            P = P if use else C
            bm = wclim.get(live["region_id"], live["woy"].to_numpy(), ["big_mean_0", "big_mean_1", "big_mean_2"])
            bm = np.nan_to_num(bm)
            for i, r in enumerate(live["region_id"]):
                rows.append({"region_id": r, "issue_date": self.issue_date.date(), "week_start": live["week_start"].iloc[i].date(),
                             "week_ahead": k, "p_below": P[i, 0], "p_normal": P[i, 1], "p_above": P[i, 2],
                             "expected_big_fire_days": float(P[i] @ bm[i]), "clim_big_fire_days": float(C[i] @ bm[i]),
                             "source": "model" if use else "climatology", "model_version": mc["version"]})
        print("  fitted production weekly", flush=True)
        return pd.DataFrame(rows)[contract.WEEKLY_COLUMNS]


# =============================================================================================
def leakage_checks(pipe: Pipeline) -> dict:
    """A2: features up to a cut-off do not change when later data change. A3: climatologies use training only."""
    d = pipe.d
    cut = pd.Timestamp("2019-06-30")
    rng = np.random.default_rng(0)
    d2 = d.copy()
    later = d2["date"] > cut
    for c in ["logfrp", "big", "fire"]:
        d2.loc[later, c] = np.where(d2.loc[later, c].notna(), rng.random(later.sum()) * 5 if c == "logfrp"
                                    else (rng.random(later.sum()) > 0.5).astype(float), np.nan)
    f1 = pipe.feats[(d["date"] <= cut).to_numpy()]
    f2 = issue_features(d2, pipe.nn)[(d2["date"] <= cut).to_numpy()]
    a2 = bool(np.array_equal(f1.to_numpy(), f2.to_numpy(), equal_nan=True))
    train_rows = (d["date"] <= pipe.train_end).to_numpy()
    c1 = doy_climatology(d["region_id"], d["doy"].to_numpy(), d["big"], train_rows & d["big"].notna().to_numpy(), 7)
    d3 = d.copy()
    test = d3["date"] > pipe.train_end
    d3.loc[test, "big"] = 1.0 - d3.loc[test, "big"]
    c2 = doy_climatology(d3["region_id"], d3["doy"].to_numpy(), d3["big"], train_rows & d3["big"].notna().to_numpy(), 7)
    weeks = weekly.weekly_table(d, week_col(pipe.mc))
    wk_train = (weeks["week_start"] + pd.Timedelta(days=6) <= pipe.train_end).to_numpy()
    w1 = weekly.fit_week_climatology(weeks, wk_train, 1).table
    weeks2 = weeks.copy()
    weeks2.loc[~wk_train, "activity"] = weeks2.loc[~wk_train, "activity"] * 3 + 1
    w2 = weekly.fit_week_climatology(weeks2, wk_train, 1).table
    a3 = bool(np.array_equal(c1.to_numpy(), c2.to_numpy()) and np.array_equal(w1.to_numpy(), w2.to_numpy(), equal_nan=True))
    return {"A2": a2, "A3": a3}


def kpi_report(pipe: Pipeline, daily_df, weekly_df, skill_df, checks, runtime, tests_ok, prev_manifest, manifest) -> list[dict]:
    k, ev, d = pipe.cfg["kpi"], pipe.ev, pipe.d
    leads = pipe.mc["leads"]
    rows = []

    def add(kid, text, value, threshold, passed, mandatory=True):
        rows.append({"kpi": kid, "check": text, "value": jsonable(value), "threshold": threshold,
                     "passed": None if passed is None else bool(passed), "mandatory": mandatory})

    bad_big = int(d.loc[~d["usable"], "big"].notna().sum())
    bad_fire = int((d["fire"].notna() & (~d["usable"] | d["n_snpp"].isna())).sum())
    add("A1", "targets only from usable rows (VIIRS measured, complete, no possible_gap)", bad_big + bad_fire, "0", bad_big + bad_fire == 0)
    add("A2", "no look-ahead: features up to 2019-06-30 unchanged after changing later data", checks["A2"], "true", checks["A2"])
    add("A3", "climatology and week terciles from training years only", checks["A3"], "true", checks["A3"])
    fire_ok = bool(((d["fire"] == 1) == (d["n_snpp"] > 0))[d["fire"].notna()].all())
    add("A4", "fire_day = n_snpp > 0 (SNPP only)", fire_ok, "true", fire_ok)
    same_fp = prev_manifest and prev_manifest.get("fingerprints") == manifest["fingerprints"]
    if same_fp:
        ident = prev_manifest.get("output_hashes") == manifest["output_hashes"]
        add("A8", "determinism: identical outputs to the previous run with the same inputs and code", ident, "true", ident)
    else:
        add("A8", "determinism: needs a second run with the same inputs and code", "first run", "true", None)
    for kid in ("A5", "A6", "A7", "B3", "B4"):
        add(kid, "needs weather (step 2-4)", "n/a", "-", None, mandatory=False)

    g = lambda t, l, key: ev["daily"][f"{t}_{l}"][key]
    add("B1", "gain vs climatology, big_fire_day, lead 1", g("big", 1, "bss_vs_climatology"), f">= {k['B1_gain_lead1']}",
        g("big", 1, "bss_vs_climatology") >= k["B1_gain_lead1"])
    add("B2", "gain vs climatology, big_fire_day, lead 3", g("big", 3, "bss_vs_climatology"), f">= {k['B2_gain_lead3']}",
        g("big", 3, "bss_vs_climatology") >= k["B2_gain_lead3"])
    auc_all = all(g("big", l, "auc") >= g("big", l, "auc_clim") for l in leads)
    add("B5", "AUC lead 1 and every lead >= AUC of climatology", {"auc_lead1": g("big", 1, "auc"), "all_leads_ge_clim": auc_all},
        f">= {k['B5_auc_lead1']} and true", g("big", 1, "auc") >= k["B5_auc_lead1"] and auc_all)
    eces = {l: g("big", l, "ece") for l in leads}
    slopes = {l: g("big", l, "calib_slope") for l in leads}
    lo, hi = k["B6_slope"]
    add("B6", "calibration: ECE (deciles) and slope, every lead", {"ece_max": max(eces.values()),
        "slope_min": min(slopes.values()), "slope_max": max(slopes.values())},
        f"ECE <= {k['B6_ece']}, slope {lo}-{hi}", max(eces.values()) <= k["B6_ece"] and all(lo <= s <= hi for s in slopes.values()))
    add("B7", "warning threshold (top 10 %), lead 1: hit rate / false alarm ratio",
        {"hit_rate": g("big", 1, "hit_rate"), "false_alarm_ratio": g("big", 1, "false_alarm_ratio")}, "report; target hit rate >= 0.5",
        None, mandatory=False)
    # Rule 3.5: decisions are made pooled and for regions with >= min_region_events test events; smaller regions
    # follow the pooled decision, so their (noisy) own skill is not part of this check.
    decided = (skill_df["region_id"] == "all") | (skill_df["n_events"] >= pipe.mc["min_region_events"])
    shipped_bad = skill_df[(skill_df["product"] == "daily") & decided & skill_df["use_model"] & (skill_df["bss_vs_climatology"] <= 0)]
    small_neg = skill_df[(skill_df["product"] == "daily") & ~decided & skill_df["use_model"] & (skill_df["bss_vs_climatology"] < 0)]
    add("B8", "fallback: no shipped decision (pooled / regions >= 30 events) with gain <= 0 on the test years",
        {"violations": len(shipped_bad), "small_regions_following_pooled_with_negative_gain": len(small_neg)}, "0",
        len(shipped_bad) == 0)

    add("C1", "gain vs climatology, fire_day, lead 1", g("fire", 1, "bss_vs_climatology"), "> 0 (target >= 0.08)",
        g("fire", 1, "bss_vs_climatology") > 0)
    ece_f = max(g("fire", l, "ece") for l in leads)
    add("C2", "ECE fire_day, every lead", ece_f, f"<= {k['C2_ece']}", ece_f <= k["C2_ece"])
    ratios = {}
    for start in ("2018-04-01", "2023-03-01"):
        t = pd.Timestamp(start)
        before = d[(d["date"] >= t - pd.DateOffset(years=2)) & (d["date"] < t)]["fire"].mean()
        after = d[(d["date"] >= t) & (d["date"] < t + pd.DateOffset(years=2)) & ~d["is_provisional"]]["fire"].mean()
        ratios[start] = after / before
    clo, chi = k["C3_ratio"]
    add("C3", "fire_day base rate 2 years after / before satellite starts", ratios, f"{clo}-{chi} (note)",
        all(clo <= r <= chi for r in ratios.values()), mandatory=False)

    wk = ev["weekly"]
    d1 = wk[2]["rpss"] > 0 and all(wk[w]["rpss"] >= 0 or not pipe.use_model[("week", w, "all")] for w in (3, 4))
    add("D1", "RPSS vs climatology: week 2 > 0; weeks 3-4 >= 0 or fallback", {w: wk[w]["rpss"] for w in wk}, "> 0 / >= 0", d1)
    probs = weekly_df[["p_below", "p_normal", "p_above"]].to_numpy()
    d2 = bool(np.allclose(probs.sum(axis=1), 1, atol=1e-9) and (probs >= 0).all() and (probs <= 1).all())
    add("D2", "weekly probabilities valid", d2, "sum = 1, in [0, 1]", d2)
    d3 = max(wk[w]["ece_p_above"] for w in wk)
    add("D3", "ECE of p_above, weeks 2-4", d3, f"<= {k['D3_ece']}", d3 <= k["D3_ece"])

    loyo = ev["loyo"]
    share = float(np.mean([v["gain"] > 0 for v in loyo.values()]))
    add("E1", "leave-one-year-out, lead 1: share of years with gain > 0", share, f">= {k['E1_share_years']}", share >= k["E1_share_years"])
    small = sorted(d[(d["date"] <= pipe.train_end)].groupby("region_id")["big"].sum().loc[lambda s: s < 30].index)
    add("E2", "regions with < 30 big-fire days in training (flagged)", small, "report", None, mandatory=False)
    e3 = bool(skill_df.loc[skill_df["region_id"] == "all", ["ci_lo", "ci_hi"]].notna().all().all())
    add("E3", "bootstrap intervals for all pooled skill values", e3, "true", e3)
    add("E4", "skill basis for days 4-10", "no_weather", "set", True, mandatory=False)

    f1 = list(daily_df.columns) == contract.DAILY_COLUMNS and list(weekly_df.columns) == contract.WEEKLY_COLUMNS \
        and all(c in skill_df.columns for c in contract.SKILL_COLUMNS)
    add("F1", "output columns match the contract", f1, "true", f1)
    f2 = len(daily_df) == len(pipe.regions) * len(leads) and len(weekly_df) == len(pipe.regions) * 3
    add("F2", "rows per issue date: daily 23 x 10, weekly 23 x 3", {"daily": len(daily_df), "weekly": len(weekly_df)}, "230 / 69", f2)
    p = daily_df
    f3 = bool(p[["p_big_fire_day", "p_fire_day", "p_clim_big_fire_day", "p_clim_fire_day"]].apply(lambda s: s.between(0, 1)).all().all()
              and (p["p_big_fire_day_lo"] <= p["p_big_fire_day"] + 1e-12).all() and (p["p_big_fire_day"] <= p["p_big_fire_day_hi"] + 1e-12).all()
              and np.allclose(p["risk_ratio"], p["p_big_fire_day"] / p["p_clim_big_fire_day"], atol=1e-9)
              and p["source"].isin(contract.SOURCES).all() and p["risk_class"].isin(contract.RISK_CLASSES).all())
    add("F3", "values valid (p in [0,1], lo <= p <= hi, risk_ratio, source, risk_class)", f3, "true", f3)
    f4 = all(key in manifest for key in ("model_version", "fingerprints", "input_hashes", "issue_date", "training_period"))
    add("F4", "manifest complete", f4, "true", f4)
    add("F5", "runtime evaluation + production (minutes, without API)", round(runtime / 60, 2),
        f"<= {k['F5_train_minutes']}", runtime / 60 <= k["F5_train_minutes"])
    add("F6", "pytest (offline)", tests_ok, "true", tests_ok)
    add("F7", "runs without weather and writes valid outputs", f1 and f2 and f3, "true", f1 and f2 and f3)
    return rows


def run_tests() -> bool | None:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=HERE,
                       capture_output=True, text=True)
    print("  pytest:", (r.stdout.strip().splitlines() or ["?"])[-1], flush=True)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["all"])
    ap.add_argument("--no-weather", action="store_true", help="models without weather (step 1; weather not integrated yet)")
    ap.add_argument("--force", action="store_true", help="recompute even if inputs are unchanged (always recomputes for now)")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()
    if not args.no_weather:
        print("Weather features are not integrated yet (step 4); running without weather.", flush=True)
    cfg = yaml.safe_load((HERE / "config.yaml").read_text())
    t0 = time.time()
    pipe = Pipeline(cfg)
    print(f"data: {len(pipe.d)} rows, issue date {pipe.issue_date.date()}, last archive day {pipe.last_archive.date()}", flush=True)
    pipe.evaluate_daily()
    pipe.evaluate_loyo()
    pipe.evaluate_weekly()
    daily_df = pipe.predict_daily()
    weekly_df = pipe.predict_weekly()
    runtime = time.time() - t0
    skill_df = pd.DataFrame(pipe.skill_rows)
    checks = leakage_checks(pipe)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "csv").mkdir(exist_ok=True)
    (OUT / "models").mkdir(exist_ok=True)
    outputs = {"forecast_daily": daily_df, "forecast_weekly": weekly_df, "forecast_skill": skill_df}
    for name, df in outputs.items():
        df.to_parquet(OUT / f"{name}.parquet", index=False)
        df.to_csv(OUT / "csv" / f"{name}.csv", index=False)
    for name, m in pipe.models_out.items():
        (OUT / "models" / f"{name}.json").write_text(json.dumps(jsonable(m), indent=1))
    (OUT / "forecast_evaluation.json").write_text(json.dumps(jsonable(pipe.ev), indent=1))

    prev = json.loads((OUT / "manifest.json").read_text()) if (OUT / "manifest.json").exists() else None
    inputs = {n: sha256(HARM / n) for n in ("activity_daily_harmonised.parquet", "day_status.parquet", "hotspots_harmonised.parquet")}
    manifest = {"model_version": cfg["model"]["version"], "issue_date": str(pipe.issue_date.date()),
                "last_archive_day": str(pipe.last_archive.date()),
                "training_period": {"evaluation": [cfg["model"]["viirs_start"], cfg["model"]["train_end"]],
                                    "test": [cfg["model"]["test_start"], str(pipe.last_archive.date())],
                                    "production": [cfg["model"]["viirs_start"], str(pipe.last_archive.date())]},
                "fingerprints": {"config": fingerprint({k: cfg[k] for k in ("model", "risk_class")}), "code": code_fingerprint(),
                                 "inputs": fingerprint(inputs)},
                "input_hashes": inputs, "skill_basis": "no_weather",
                "output_hashes": {n: sha256(OUT / f"{n}.parquet") for n in outputs}}
    tests_ok = None if args.skip_tests else run_tests()
    kpis = kpi_report(pipe, daily_df, weekly_df, skill_df, checks, runtime, tests_ok, prev, manifest)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (OUT / "forecast_kpi_report.json").write_text(json.dumps({"generated_for_issue_date": str(pipe.issue_date.date()),
                                                             "kpis": kpis}, indent=1))
    failed = [r["kpi"] for r in kpis if r["mandatory"] and r["passed"] is False]
    print(f"done in {runtime / 60:.1f} min; mandatory KPIs failed: {failed or 'none'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
