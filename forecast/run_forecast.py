"""Forecast pipeline: check the weather, evaluate the models, fit the production models and write today's forecast.

Run from La-Brasa/forecast:
    .venv/bin/python run_forecast.py train                  # evaluate + fit, save models/bundle.pkl, write forecast + KPIs
    .venv/bin/python run_forecast.py predict                # daily: load the bundle, no fitting (seconds, 1 core)
    .venv/bin/python run_forecast.py all                    # same as train
    .venv/bin/python run_forecast.py train --no-weather     # no-weather tier only (fallback, KPI F7)
    .venv/bin/python run_forecast.py weather-qc             # step 2 only: weather checks A5/A6 -> weather_qc.json

`train` is the heavy part (minutes): run it on a workstation when data or config change (e.g. weekly) and copy
data/forecast/models/bundle.pkl to the server. `predict` is light and is the daily job on the server.
Linear algebra uses FORECAST_THREADS threads (default 1): one thread is faster here than many, see README.

Two model tiers per target and lead:
    noweather  climatology + fire history (step 1)
    weather    the same + weather of the target day (FWI system, Meteomatics, dryness before the day)
The weather tier is shipped for a lead where it beats the no-weather tier on the test years and the live run has
weather for the target day; otherwise the no-weather tier. Either is shipped only if it beats the climatology
(rule 3.5), otherwise source = climatology.

Reads data/harmonised/ and data/forecast/weather_*. Writes data/forecast/: forecast_daily, forecast_weekly,
forecast_skill (+ csv/), weather_qc.json, forecast_evaluation.json, forecast_kpi_report.json, manifest.json,
models/*.json. Exit code 1 if a mandatory KPI fails.
"""
from __future__ import annotations

import os

# Before numpy is imported: one BLAS thread by default. The matrices are small (~100k x 60); with many threads
# OpenBLAS spends its time synchronising (24 threads: 1.2 s per fit, 1 thread: 0.5 s) and occupies every core.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, os.environ.get("FORECAST_THREADS", "1"))

import argparse
import hashlib
import json
import pickle
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
from features.fwi import COMPONENTS as FWI_COMPONENTS
from features.fwi import fwi_series
from features import weather as wx
from models import daily, weekly

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
HARM = REPO / "data" / "harmonised"
OUT = REPO / "data" / "forecast"
FWI_REFERENCE = HERE / "tests" / "data" / "fwi_reference_vanwagner1985.csv"
TIERS = ("noweather", "weather")
BUNDLE = OUT / "models" / "bundle.pkl"
BUNDLE_FORMAT = 1


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


def weather_files() -> list[Path]:
    return sorted(OUT.glob("weather_points_*.parquet")) + [OUT / "weather_points.parquet"]


def fwi_reference_check() -> float:
    """KPI A7: largest absolute deviation from the published test table over all six components."""
    r = pd.read_csv(FWI_REFERENCE, comment="#")
    o = fwi_series(r["TEMP"].to_numpy(), r["RH"].to_numpy(), r["WS"].to_numpy(), r["PREC"].to_numpy(), r["MON"].to_numpy())
    return float(max(np.abs(o[c][:, 0] - r[c.upper()].to_numpy()).max() for c in FWI_COMPONENTS))


# =============================================================================================
class Pipeline:
    def __init__(self, cfg: dict, use_weather: bool, neighbours: dict | None = None, weather_qc: bool = True):
        self.cfg = cfg
        self.mc = cfg["model"]
        self.train_end = pd.Timestamp(self.mc["train_end"])
        self.test_start = pd.Timestamp(self.mc["test_start"])
        self.d = load_daily(HARM, self.mc["viirs_start"])
        self.last_archive = self.d.loc[~self.d["is_provisional"], "date"].max()
        self.issue_date = self.d["date"].max()
        self.regions = sorted(self.d["region_id"].unique())
        # neighbours come from the training data (hotspots up to train_end); predict reuses them from the bundle
        self.nn = neighbours or region_neighbours(HARM, self.mc["train_end"], self.mc["neighbours"])
        self.feats = issue_features(self.d, self.nn)
        self.ev: dict = {"daily": {t: {} for t in TIERS}, "weekly": {t: {} for t in TIERS}, "loyo": {},
                         "risk_class_test": {}, "weather_selection": {}, "shipped_tier": {}}
        self.skill_rows: dict = {t: {} for t in TIERS}   # tier -> (product, target, lead) -> list of rows
        self.use_model: dict = {}          # (tier, target, lead, region or 'all') -> bool
        self.models_out: dict = {}
        self.weather = None
        self.weather_info: dict = {}
        self.weather_qc: dict | None = None
        self.weather_cols: list[str] = []
        self.weekly_weather_cols: list[str] = []
        if use_weather and (OUT / "weather_points_history_core.parquet").exists():
            self.weather, self.weather_info = wx.build_region_weather(OUT, self.mc["train_end"])
        if self.weather is not None and weather_qc:
            hist_end = max(pd.Timestamp(gi["recent_end"] or gi["history_end"]) for gi in self.weather_info.values())
            pts, _ = wx.load_point_weather(OUT, with_forecast=False)
            self.weather_qc = wx.quality_report(pts, self.weather[self.weather["date"] <= hist_end], self.regions,
                                                self.mc["viirs_start"], str(min(hist_end, self.issue_date).date()))
            self.weather_qc["signal"] = wx.signal_check(self.weather, self.d, self.mc["train_end"])
        self.tiers = TIERS if self.weather is not None else ("noweather",)

    # --- helpers -----------------------------------------------------------------------------
    def climatology(self, target: str, mask: np.ndarray, clip=1e-4) -> pd.DataFrame:
        d = self.d
        return doy_climatology(d["region_id"], d["doy"].to_numpy(), d[target], mask & d[target].notna().to_numpy(),
                               self.mc["clim_window_days"], clip=clip)

    def add_weather(self, df: pd.DataFrame, cols: list[str], date_col: str) -> pd.DataFrame:
        if not cols or self.weather is None:
            return df
        w = self.weather.set_index(["region_id", "date"])[cols]
        vals = w.reindex(pd.MultiIndex.from_arrays([df["region_id"], df[date_col]])).to_numpy()
        out = df.copy()
        out[cols] = vals
        return out

    def pairs(self, target: str, lead: int, clim: pd.DataFrame, cols: list[str] = ()) -> pd.DataFrame:
        pr = daily.add_climatology(lead_pairs(self.d, self.feats, target, lead), clim)
        return self.add_weather(pr, list(cols), "target_date")

    def extra(self, tier: str) -> list[str]:
        return self.weather_cols if tier == "weather" else []

    def fit_daily(self, tr: pd.DataFrame, target: str, lead: int, extra: list[str] = ()) -> daily.DailyModel:
        mc = self.mc
        if mc.get("platt_calibration", False):
            return daily.train_calibrated(tr, target, lead, self.regions, mc["l2_continuous"], mc["l2_region"],
                                          mc["calib_years"], extra)
        return daily.train(tr, target, lead, self.regions, mc["l2_continuous"], mc["l2_region"], extra)

    # --- step 4a: choose the weather features on validation (train 2012-2019, validate 2020-2021) ---------------
    def select_weather_set(self) -> None:
        if self.weather is None:
            return
        val_start = self.train_end - pd.DateOffset(years=2) + pd.Timedelta(days=1)
        fit_rows = (self.d["date"] < val_start).to_numpy()
        leads = self.mc["weather"]["selection_leads"]
        all_cols = sorted({c for cols in wx.WEATHER_SETS.values() for c in cols})
        res = {}
        for target in self.mc["targets"]:
            clim = self.climatology(target, fit_rows)
            for lead in leads:
                pr = self.pairs(target, lead, clim, all_cols)
                ok = pr["y"].notna()
                tr = pr[ok & (pr["target_date"] < val_start)]
                va = pr[ok & (pr["target_date"] >= val_start) & (pr["target_date"] <= self.train_end)]
                y, c = va["y"].to_numpy(), va["clim"].to_numpy()
                b_ref = np.mean((c - y) ** 2)
                for name, cols in [("none", []), *wx.WEATHER_SETS.items()]:
                    p = daily.predict(self.fit_daily(tr, target, lead, cols), va)
                    res.setdefault(target, {}).setdefault(name, {})[lead] = float(1 - np.mean((p - y) ** 2) / b_ref)
        mean_big = {name: float(np.mean(list(v.values()))) for name, v in res["big"].items()}
        best = max(wx.WEATHER_SETS, key=lambda n: mean_big[n])
        self.weather_cols = list(wx.WEATHER_SETS[best])
        self.ev["weather_selection"] = {"validation": [str(val_start.date()), str(self.train_end.date())],
                                        "gain_vs_climatology": res, "mean_gain_big": mean_big, "chosen": best}
        print(f"  weather set chosen on validation: {best} ({len(self.weather_cols)} features)", flush=True)

    # --- evaluation: train 2012-2021, test 2022 .. last archive day ------------------------------
    def evaluate_daily(self) -> None:
        mc = self.mc
        train_rows = (self.d["date"] <= self.train_end).to_numpy()
        for target in mc["targets"]:
            clim = self.climatology(target, train_rows)
            for lead in mc["leads"]:
                pr = self.pairs(target, lead, clim, self.weather_cols)
                ok = pr["y"].notna()
                tr = pr[ok & (pr["target_date"] <= self.train_end)]
                te = pr[ok & (pr["target_date"] >= self.test_start) & (pr["target_date"] <= self.last_archive)]
                for tier in self.tiers:
                    self._evaluate_tier(tier, target, lead, tr, te)
            print(f"  evaluated daily target={target}", flush=True)

    def _evaluate_tier(self, tier, target, lead, tr, te) -> None:
        mc = self.mc
        model = self.fit_daily(tr, target, lead, self.extra(tier))
        thr = float(np.quantile(daily.predict(model, tr), 1 - mc["warn_share"]))
        p, c, y = daily.predict(model, te), te["clim"].to_numpy(), te["y"].to_numpy()
        sc = binary_scores(y, p, c, thr)
        years = te["target_date"].dt.year.to_numpy()
        sc["ci_lo"], sc["ci_hi"] = bootstrap_skill_by_year(years, (p - y) ** 2, (c - y) ** 2, mc["bootstrap"], mc["seed"])
        self.ev["daily"][tier][f"{target}_{lead}"] = sc
        use_all = bool(sc["bss_vs_climatology"] > 0 and sc["ci_lo"] >= 0)
        self.use_model[(tier, target, lead, "all")] = use_all
        basis = "analysis" if tier == "weather" else "no_weather"
        rows = [self._skill_row("daily", target, lead, "all", sc, use_all, basis)]
        for r, g in te.assign(p=p).groupby("region_id"):
            yr, pr_, cr = g["y"].to_numpy(), g["p"].to_numpy(), g["clim"].to_numpy()
            scr = binary_scores(yr, pr_, cr, thr)
            scr["ci_lo"], scr["ci_hi"] = bootstrap_skill_by_year(
                g["target_date"].dt.year.to_numpy(), (pr_ - yr) ** 2, (cr - yr) ** 2, mc["bootstrap"], mc["seed"])
            use_r = bool(scr["bss_vs_climatology"] > 0 and scr["ci_lo"] >= 0) \
                if scr["n_events"] >= mc["min_region_events"] else use_all
            self.use_model[(tier, target, lead, r)] = use_r
            rows.append(self._skill_row("daily", target, lead, r, scr, use_r, basis))
        self.skill_rows[tier][("daily", target, lead)] = rows
        if target == "big" and lead in (1, 5, 10):
            rc = contract.risk_class(p, p / c, self.cfg["risk_class"])
            tab = pd.DataFrame({"cls": rc, "y": y}).groupby("cls")["y"].agg(["size", "mean"])
            tab["share"] = tab["size"] / len(y)
            self.ev["risk_class_test"].setdefault(tier, {})[lead] = tab.reindex(contract.RISK_CLASSES).to_dict("index")

    def preferred_tier(self, target: str, lead: int) -> str:
        """Weather tier if it has a higher test gain than the no-weather tier (pooled)."""
        if "weather" not in self.tiers:
            return "noweather"
        g = {t: self.ev["daily"][t][f"{target}_{lead}"]["bss_vs_climatology"] for t in self.tiers}
        return "weather" if g["weather"] > g["noweather"] else "noweather"

    def _skill_row(self, product, target, lead, region, sc, use, basis) -> dict:
        return {"product": product, "target": daily.TARGETS.get(target, target), "lead": lead, "region_id": region,
                "bss_vs_climatology": sc.get("bss_vs_climatology"), "ci_lo": sc.get("ci_lo"), "ci_hi": sc.get("ci_hi"),
                "auc": sc.get("auc"), "pr_auc": sc.get("pr_auc"), "ece": sc.get("ece"), "hit_rate": sc.get("hit_rate"),
                "false_alarm_ratio": sc.get("false_alarm_ratio"), "n_events": sc.get("n_events"),
                "use_model": use, "skill_basis": basis}

    def evaluate_loyo(self) -> None:
        """Leave one year out, big_fire_day, lead 1, both tiers (training years include later years)."""
        d = self.d
        years = sorted(d.loc[~d["is_provisional"] & d["big"].notna(), "date"].dt.year.unique())
        out = {t: {} for t in self.tiers}
        for yr in years:
            mask = ((d["date"].dt.year != yr) & ~d["is_provisional"]).to_numpy()
            clim = self.climatology("big", mask)
            pr = self.pairs("big", 1, clim, self.weather_cols)
            ok = pr["y"].notna() & ~pr["target_provisional"].astype(bool)
            tr = pr[ok & (pr["target_date"].dt.year != yr)]
            te = pr[ok & (pr["target_date"].dt.year == yr)]
            c, y = te["clim"].to_numpy(), te["y"].to_numpy()
            for tier in self.tiers:
                p = daily.predict(self.fit_daily(tr, "big", 1, self.extra(tier)), te)
                out[tier][int(yr)] = {"gain": 1 - np.mean((p - y) ** 2) / np.mean((c - y) ** 2), "n_events": int(y.sum())}
        self.ev["loyo"] = out
        print("  evaluated leave-one-year-out", flush=True)

    def _week_inputs(self, train_mask_fn, clim_mask):
        d = self.d
        weeks = weekly.weekly_table(d, week_col(self.mc))
        wclim = weekly.fit_week_climatology(weeks, train_mask_fn(weeks), self.mc["weekly"]["window_weeks"])
        lclim = self.climatology("logfrp", clim_mask, clip=None)
        return weeks, wclim, lclim

    def evaluate_weekly(self) -> None:
        mc, wc = self.mc, self.mc["weekly"]
        d = self.d
        weeks, wclim, lclim = self._week_inputs(lambda w: (w["week_start"] + pd.Timedelta(days=6) <= self.train_end).to_numpy(),
                                                (d["date"] <= self.train_end).to_numpy())
        wk_train = (weeks["week_start"] + pd.Timedelta(days=6) <= self.train_end).to_numpy()
        sundays = (d["date"].dt.day_of_week == 6).to_numpy()
        shares_train = weeks[wk_train & weeks["complete"]].assign(c=lambda w: wclim.classes(w))["c"].value_counts(normalize=True)
        self.ev["weekly_class_shares_train"] = {int(k): float(v) for k, v in shares_train.sort_index().items()}
        self.weekly_weather_cols = list(wx.WEEKLY_WEATHER) if self.weather is not None else []
        for k in wc["weeks_ahead"]:
            pw = self.add_weather(weekly.week_pairs(d, self.feats, weeks, wclim, lclim, k, sundays),
                                  self.weekly_weather_cols, "issue_date")
            end = pw["week_start"] + pd.Timedelta(days=6)
            tr = pw[pw["complete"] & (end <= self.train_end)]
            te = pw[pw["complete"] & (pw["week_start"] >= self.test_start) & (end <= self.last_archive)]
            C = te[["clim_p_below", "clim_p_normal", "clim_p_above"]].to_numpy()
            yc = te["y_class"].to_numpy()
            for tier in self.tiers:
                extra = self.weekly_weather_cols if tier == "weather" else []
                P = weekly.predict(weekly.train(tr, k, wc["l2"], extra), te)
                r_m, r_c = rps(yc, P), rps(yc, C)
                sc = {"n": int(len(te)), "rps": float(r_m.mean()), "rps_clim": float(r_c.mean()),
                      "rpss": float(1 - r_m.mean() / r_c.mean()),
                      "ece_p_above": ece((yc == 2).astype(float), P[:, 2]),
                      "ece_p_above_clim": ece((yc == 2).astype(float), C[:, 2]),
                      "observed_shares": [float((yc == c).mean()) for c in range(3)], "mean_p": P.mean(axis=0).tolist()}
                sc["ci_lo"], sc["ci_hi"] = bootstrap_skill_by_year(te["week_start"].dt.year.to_numpy(), r_m, r_c,
                                                                   mc["bootstrap"], mc["seed"])
                use = bool(sc["rpss"] > 0 and sc["ci_lo"] >= 0)
                self.use_model[(tier, "week", k, "all")] = use
                self.ev["weekly"][tier][k] = sc
                self.skill_rows[tier][("weekly", "week", k)] = [{
                    "product": "weekly", "target": "week_activity", "lead": k, "region_id": "all",
                    "bss_vs_climatology": sc["rpss"], "ci_lo": sc["ci_lo"], "ci_hi": sc["ci_hi"], "auc": np.nan,
                    "pr_auc": np.nan, "ece": sc["ece_p_above"], "hit_rate": np.nan, "false_alarm_ratio": np.nan,
                    "n_events": int((yc == 2).sum()), "use_model": use,
                    "skill_basis": "analysis" if tier == "weather" else "no_weather"}]
        print("  evaluated weekly", flush=True)

    def preferred_week_tier(self, k: int) -> str:
        if "weather" not in self.tiers:
            return "noweather"
        return "weather" if self.ev["weekly"]["weather"][k]["rpss"] > self.ev["weekly"]["noweather"][k]["rpss"] else "noweather"

    # --- production: fit on all archive data (train) and apply the fitted models (predict) ---------------
    def fit_production(self) -> dict:
        """All production models and lookup tables in one bundle, so `predict` does not fit anything.

        For every target and lead the no-weather tier is always fitted (fallback when the weather forecast is
        missing), the weather tier where it is preferred. big_fire_day also gets bootstrap refits for lo / hi."""
        mc, wc, d = self.mc, self.mc["weekly"], self.d
        archive = (~d["is_provisional"]).to_numpy()
        rng = np.random.default_rng(mc["seed"])
        b = {"format": BUNDLE_FORMAT, "model_version": {"weather": mc["version"], "noweather": mc["version_noweather"]},
             "config_fingerprint": fingerprint({k: self.cfg[k] for k in ("model", "risk_class")}),
             "code_fingerprint": code_fingerprint(), "trained_issue_date": str(self.issue_date.date()),
             "last_archive_day": str(self.last_archive.date()), "regions": self.regions, "neighbours": self.nn,
             "weather_cols": self.weather_cols, "weekly_weather_cols": self.weekly_weather_cols,
             "skill_rows": self.skill_rows, "climatology": {}, "daily": {}, "weekly": {}}
        for target in mc["targets"]:
            clim = self.climatology(target, archive)
            b["climatology"][target] = clim
            for lead in mc["leads"]:
                pr = self.pairs(target, lead, clim, self.weather_cols)
                tr = pr[pr["y"].notna() & ~pr["target_provisional"].fillna(True).astype(bool)]
                pref = self.preferred_tier(target, lead)
                entry = {"preferred": pref, "tiers": {}}
                for tier in (("noweather", "weather") if pref == "weather" else ("noweather",)):
                    extra = self.extra(tier)
                    boots = []
                    if target == "big":
                        yrs = tr["target_date"].dt.year.to_numpy()
                        uniq = np.unique(yrs)
                        by_year = {y: np.flatnonzero(yrs == y) for y in uniq}
                        for _ in range(mc["bootstrap_models"]):
                            pick = rng.choice(uniq, size=len(uniq), replace=True)
                            boots.append(self.fit_daily(tr.iloc[np.concatenate([by_year[y] for y in pick])], target, lead, extra))
                    use = {r: bool(self.use_model.get((tier, target, lead, r), self.use_model.get((tier, target, lead, "all"), False)))
                           for r in self.regions}
                    entry["tiers"][tier] = {"model": self.fit_daily(tr, target, lead, extra), "bootstrap": boots, "use": use}
                b["daily"][f"{target}_{lead}"] = entry
            print(f"  fitted production daily target={target}", flush=True)
        weeks, wclim, lclim = self._week_inputs(
            lambda w: ((w["week_start"] + pd.Timedelta(days=6) <= self.last_archive) & ~w["provisional"]).to_numpy(),
            (~d["is_provisional"]).to_numpy())
        b["week_climatology"], b["logfrp_climatology"] = wclim, lclim
        sundays = (d["date"].dt.day_of_week == 6).to_numpy()
        for k in wc["weeks_ahead"]:
            pref = self.preferred_week_tier(k)
            entry = {"preferred": pref, "tiers": {}}
            for tier in (("noweather", "weather") if pref == "weather" else ("noweather",)):
                extra = self.weekly_weather_cols if tier == "weather" else []
                pw = self.add_weather(weekly.week_pairs(d, self.feats, weeks, wclim, lclim, k, sundays), extra, "issue_date")
                tr = pw[pw["complete"] & ~pw["provisional"] & (pw["week_start"] + pd.Timedelta(days=6) <= self.last_archive)]
                entry["tiers"][tier] = {"model": weekly.train(tr, k, wc["l2"], extra),
                                        "use": bool(self.use_model.get((tier, "week", k, "all"), False))}
            b["weekly"][k] = entry
        print("  fitted production weekly", flush=True)
        return b

    def apply(self, b: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Today's forecast from a fitted bundle: features of the issue date, no model fitting (cheap)."""
        self.weather_cols, self.weekly_weather_cols = list(b["weather_cols"]), list(b["weekly_weather_cols"])
        return self._apply_daily(b), self._apply_weekly(b)

    def _apply_daily(self, b: dict) -> pd.DataFrame:
        mc = self.mc
        out = {}
        for target in mc["targets"]:
            clim = b["climatology"][target]
            for lead in mc["leads"]:
                pr = self.pairs(target, lead, clim, self.weather_cols if self.weather is not None else [])
                live = pr[pr["issue_date"] == self.issue_date].copy()
                e = b["daily"][f"{target}_{lead}"]
                tier = e["preferred"]
                if tier == "weather" and (self.weather is None or not live[self.weather_cols].notna().all(axis=None)):
                    tier = "noweather"          # no weather (forecast) for this target day: no-weather tier
                self.ev["shipped_tier"][f"{target}_{lead}"] = tier
                t = e["tiers"][tier]
                self.models_out[f"daily_{target}_lead{lead}"] = {"tier": tier, **t["model"].to_dict()}
                live["p"] = daily.predict(t["model"], live)
                if t["bootstrap"]:
                    sims = np.array([daily.predict(m, live) for m in t["bootstrap"]])
                    lo, hi = np.quantile(sims, mc["band_quantiles"], axis=0)
                    live["lo"], live["hi"] = np.minimum(lo, live["p"]), np.maximum(hi, live["p"])
                live["use"] = [t["use"].get(r, False) for r in live["region_id"]]
                out[(target, lead)] = live
        rows = []
        for lead in mc["leads"]:
            version = b["model_version"][self.ev["shipped_tier"][f"big_{lead}"]]
            bb, f = out[("big", lead)].set_index("region_id"), out[("fire", lead)].set_index("region_id")
            for r in self.regions:
                pb = bb.at[r, "p"] if bb.at[r, "use"] else bb.at[r, "clim"]
                lo = bb.at[r, "lo"] if bb.at[r, "use"] else pb
                hi = bb.at[r, "hi"] if bb.at[r, "use"] else pb
                pf = f.at[r, "p"] if f.at[r, "use"] else f.at[r, "clim"]
                rows.append({"region_id": r, "issue_date": self.issue_date.date(), "target_date": bb.at[r, "target_date"].date(),
                             "lead_days": lead, "p_big_fire_day": pb, "p_fire_day": pf,
                             "p_clim_big_fire_day": bb.at[r, "clim"], "p_clim_fire_day": f.at[r, "clim"],
                             "risk_ratio": pb / bb.at[r, "clim"], "p_big_fire_day_lo": min(lo, pb), "p_big_fire_day_hi": max(hi, pb),
                             "source": "model" if bb.at[r, "use"] else "climatology", "model_version": version})
        df = pd.DataFrame(rows)
        df["risk_class"] = contract.risk_class(df["p_big_fire_day"], df["risk_ratio"], self.cfg["risk_class"])
        return df[contract.DAILY_COLUMNS]

    def _apply_weekly(self, b: dict) -> pd.DataFrame:
        mc, d = self.mc, self.d
        weeks = weekly.weekly_table(d, week_col(mc))
        wclim, lclim = b["week_climatology"], b["logfrp_climatology"]
        live_mask = (d["date"] == self.issue_date).to_numpy()
        rows = []
        for k, e in b["weekly"].items():
            tier = e["preferred"]
            extra = self.weekly_weather_cols if tier == "weather" else []
            live = self.add_weather(weekly.week_pairs(d, self.feats, weeks, wclim, lclim, k, live_mask), extra, "issue_date")
            if extra and (self.weather is None or not live[extra].notna().all(axis=None)):
                tier = "noweather"
            self.ev["shipped_tier"][f"week_{k}"] = tier
            t = e["tiers"][tier]
            self.models_out[f"weekly_week{k}"] = {"tier": tier, **t["model"].to_dict()}
            P = weekly.predict(t["model"], live)
            C = live[["clim_p_below", "clim_p_normal", "clim_p_above"]].to_numpy()
            P = P if t["use"] else C
            bm = np.nan_to_num(wclim.get(live["region_id"], live["woy"].to_numpy(), ["big_mean_0", "big_mean_1", "big_mean_2"]))
            for i, r in enumerate(live["region_id"]):
                rows.append({"region_id": r, "issue_date": self.issue_date.date(), "week_start": live["week_start"].iloc[i].date(),
                             "week_ahead": k, "p_below": P[i, 0], "p_normal": P[i, 1], "p_above": P[i, 2],
                             "expected_big_fire_days": float(P[i] @ bm[i]), "clim_big_fire_days": float(C[i] @ bm[i]),
                             "source": "model" if t["use"] else "climatology", "model_version": b["model_version"][tier]})
        return pd.DataFrame(rows)[contract.WEEKLY_COLUMNS]

    def skill_table(self, skill_rows: dict | None = None) -> pd.DataFrame:
        """forecast_skill: per product, target and lead the rows of the tier that is shipped live."""
        skill_rows = skill_rows or self.skill_rows
        rows = []
        for (product, target, lead) in skill_rows["noweather"]:
            key = f"{target}_{lead}" if product == "daily" else f"week_{lead}"
            tier = self.ev["shipped_tier"].get(key, "noweather")
            rows += skill_rows[tier][(product, target, lead)]
        return pd.DataFrame(rows)


# =============================================================================================
def leakage_checks(pipe: Pipeline) -> dict:
    """A2: features up to a cut-off do not change when later data change (fire history and weather).
    A3: climatologies and weather anomalies use training years only."""
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
    a2_weather = None
    if pipe.weather is not None:
        # Change all weather after a cut-off in the test years (the anomaly climatology 2012..train_end stays fixed),
        # recompute FWI (recursion) and the derived features: every value up to the cut-off must stay equal.
        wcut = pd.Timestamp("2023-06-30")
        base_cols = ["region_id", "date", *wx.GROUPS["core"], *wx.GROUPS["fire"]]
        w1 = pipe.weather[base_cols].copy()
        w2 = w1.copy()
        lw = w2["date"] > wcut
        for c in ("t2m", "rh", "wind", "precip", "tmax", "td"):
            w2.loc[lw, c] = w2.loc[lw, c] * 0.5 + 3.0
        f_a = wx.add_derived(_recompute_fwi_regions(w1), pipe.mc["train_end"])
        f_b = wx.add_derived(_recompute_fwi_regions(w2), pipe.mc["train_end"])
        cols = sorted({c for s in wx.WEATHER_SETS.values() for c in s} | set(wx.WEEKLY_WEATHER))
        a = f_a[f_a["date"] <= wcut].sort_values(["region_id", "date"])[cols].to_numpy()
        b = f_b[f_b["date"] <= wcut].sort_values(["region_id", "date"])[cols].to_numpy()
        changed_after = not np.allclose(f_a[f_a["date"] > wcut][cols].to_numpy(), f_b[f_b["date"] > wcut][cols].to_numpy(),
                                        equal_nan=True)
        a2_weather = bool(np.allclose(a, b, equal_nan=True, rtol=0, atol=1e-12) and changed_after)
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
    w2t = weekly.fit_week_climatology(weeks2, wk_train, 1).table
    a3 = bool(np.array_equal(c1.to_numpy(), c2.to_numpy()) and np.array_equal(w1.to_numpy(), w2t.to_numpy(), equal_nan=True))
    return {"A2": a2 and a2_weather is not False, "A2_fire_history": a2, "A2_weather": a2_weather, "A3": a3}


def _recompute_fwi_regions(w: pd.DataFrame) -> pd.DataFrame:
    """Leakage check helper: FWI on region means (a stand-in for the point calculation, same recursion)."""
    out = []
    for r, g in w.groupby("region_id", sort=True):
        g = g.sort_values("date").copy()
        comp = fwi_series(g["t2m"].to_numpy(), g["rh"].to_numpy(), g["wind"].to_numpy(),
                          np.clip(g["precip"].to_numpy(), 0, None), g["date"].dt.month.to_numpy())
        for c in FWI_COMPONENTS:
            g[c] = comp[c][:, 0]
        out.append(g)
    return pd.concat(out, ignore_index=True)


def kpi_report(pipe: Pipeline, daily_df, weekly_df, skill_df, checks, runtime, tests_ok, prev_manifest, manifest,
               fwi_dev: float) -> list[dict]:
    k, ev, d = pipe.cfg["kpi"], pipe.ev, pipe.d
    leads = pipe.mc["leads"]
    rows = []

    def add(kid, text, value, threshold, passed, mandatory=True):
        rows.append({"kpi": kid, "check": text, "value": jsonable(value), "threshold": threshold,
                     "passed": None if passed is None else bool(passed), "mandatory": mandatory})

    bad_big = int(d.loc[~d["usable"], "big"].notna().sum())
    bad_fire = int((d["fire"].notna() & (~d["usable"] | d["n_snpp"].isna())).sum())
    add("A1", "targets only from usable rows (VIIRS measured, complete, no possible_gap)", bad_big + bad_fire, "0", bad_big + bad_fire == 0)
    add("A2", "no look-ahead: fire-history and weather features up to 2019-06-30 unchanged after changing later data",
        {"fire_history": checks["A2_fire_history"], "weather": checks["A2_weather"]}, "true", checks["A2"])
    add("A3", "climatology and week terciles from training years only", checks["A3"], "true", checks["A3"])
    fire_ok = bool(((d["fire"] == 1) == (d["n_snpp"] > 0))[d["fire"].notna()].all())
    add("A4", "fire_day = n_snpp > 0 (SNPP only)", fire_ok, "true", fire_ok)
    qc = pipe.weather_qc
    if qc is not None:
        a5 = {g: v["share_present"] for g, v in qc["A5"].items()}
        add("A5", "weather complete, region x day (core / fire)", a5, ">= 0.995 / >= 0.95", all(v["passed"] for v in qc["A5"].values()))
        add("A6", "weather plausible (ranges, region and point values)", qc["A6"]["total"], "0 violations", qc["A6"]["passed"])
    else:
        add("A5", "weather complete", "no weather", ">= 0.995 / >= 0.95", None, mandatory=False)
        add("A6", "weather plausible", "no weather", "0 violations", None, mandatory=False)
    add("A7", "own FWI vs published test table (max |deviation| over all components)", fwi_dev, "< 0.1", fwi_dev < 0.1)
    same_fp = prev_manifest and prev_manifest.get("fingerprints") == manifest["fingerprints"]
    if same_fp:
        ident = prev_manifest.get("output_hashes") == manifest["output_hashes"]
        add("A8", "determinism: identical outputs to the previous run with the same inputs and code", ident, "true", ident)
    else:
        add("A8", "determinism: needs a second run with the same inputs and code", "first run", "true", None)

    shipped = lambda t, l: pipe.preferred_tier(t, l)
    g = lambda t, l, key, tier=None: ev["daily"][tier or shipped(t, l)][f"{t}_{l}"][key]
    add("B1", "gain vs climatology, big_fire_day, lead 1", g("big", 1, "bss_vs_climatology"), f">= {k['B1_gain_lead1']}",
        g("big", 1, "bss_vs_climatology") >= k["B1_gain_lead1"])
    add("B2", "gain vs climatology, big_fire_day, lead 3", g("big", 3, "bss_vs_climatology"), f">= {k['B2_gain_lead3']}",
        g("big", 3, "bss_vs_climatology") >= k["B2_gain_lead3"])
    if "weather" in pipe.tiers:
        diff = {l: g("big", l, "bss_vs_climatology", "weather") - g("big", l, "bss_vs_climatology", "noweather") for l in leads}
        add("B3", "weather helps: gain with weather > without, leads 2-7 (target also 8-10)",
            {"gain_difference": diff, "leads_8_10_better": all(diff[l] > 0 for l in (8, 9, 10))}, "> 0 for leads 2-7",
            all(diff[l] > 0 for l in range(2, 8)))
        b4, b4lo = g("big", 5, "bss_vs_climatology", "weather"), g("big", 5, "ci_lo", "weather")
        add("B4", "gain with weather, lead 5", {"gain": b4, "ci_lo": b4lo, "target_0.05_reached": b4 >= 0.05},
            "> 0 and ci_lo >= 0 (target >= 0.05)", b4 > 0 and b4lo >= 0)
    else:
        add("B3", "needs weather", "n/a", "-", None, mandatory=False)
        add("B4", "needs weather", "n/a", "-", None, mandatory=False)
    auc_all = all(g("big", l, "auc") >= g("big", l, "auc_clim") for l in leads)
    add("B5", "AUC lead 1 and every lead >= AUC of climatology", {"auc_lead1": g("big", 1, "auc"), "all_leads_ge_clim": auc_all},
        f">= {k['B5_auc_lead1']} and true", g("big", 1, "auc") >= k["B5_auc_lead1"] and auc_all)
    eces = {l: g("big", l, "ece") for l in leads}
    slopes = {l: g("big", l, "calib_slope") for l in leads}
    lo, hi = k["B6_slope"]
    model_leads = [l for l in leads if pipe.use_model.get((shipped("big", l), "big", l, "all"), False)]
    b6 = max(eces.values()) <= k["B6_ece"] and all(lo <= s <= hi for s in slopes.values())
    add("B6", "calibration: ECE (deciles) and slope, every lead", {
        "ece_max": max(eces.values()), "slope_min": min(slopes.values()), "slope_max": max(slopes.values()),
        "per_lead": {"ece": eces, "slope": slopes},
        "info_leads_shipped_as_model": model_leads}, f"ECE <= {k['B6_ece']}, slope {lo}-{hi}", b6)
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

    wk = {w: ev["weekly"][pipe.preferred_week_tier(w)][w] for w in pipe.mc["weekly"]["weeks_ahead"]}
    d1 = wk[2]["rpss"] > 0 and all(wk[w]["rpss"] >= 0 or not pipe.use_model[(pipe.preferred_week_tier(w), "week", w, "all")]
                                   for w in (3, 4))
    add("D1", "RPSS vs climatology: week 2 > 0; weeks 3-4 >= 0 or fallback", {w: wk[w]["rpss"] for w in wk}, "> 0 / >= 0", d1)
    probs = weekly_df[["p_below", "p_normal", "p_above"]].to_numpy()
    d2 = bool(np.allclose(probs.sum(axis=1), 1, atol=1e-9) and (probs >= 0).all() and (probs <= 1).all())
    add("D2", "weekly probabilities valid", d2, "sum = 1, in [0, 1]", d2)
    d3 = max(wk[w]["ece_p_above"] for w in wk)
    add("D3", "ECE of p_above, weeks 2-4", {"model": d3, "climatology": max(wk[w]["ece_p_above_clim"] for w in wk)},
        f"<= {k['D3_ece']}", d3 <= k["D3_ece"])

    loyo = ev["loyo"][pipe.preferred_tier("big", 1)]
    share = float(np.mean([v["gain"] > 0 for v in loyo.values()]))
    add("E1", "leave-one-year-out, lead 1: share of years with gain > 0", share, f">= {k['E1_share_years']}", share >= k["E1_share_years"])
    small = sorted(d[(d["date"] <= pipe.train_end)].groupby("region_id")["big"].sum().loc[lambda s: s < 30].index)
    add("E2", "regions with < 30 big-fire days in training (flagged)", small, "report", None, mandatory=False)
    e3 = bool(skill_df.loc[skill_df["region_id"] == "all", ["ci_lo", "ci_hi"]].notna().all().all())
    add("E3", "bootstrap intervals for all pooled skill values", e3, "true", e3)
    bases = sorted(skill_df.loc[(skill_df["product"] == "daily") & (skill_df["lead"] >= 4), "skill_basis"].unique())
    add("E4", "skill basis for days 4-10 (analysis = perfect weather, an upper bound until step 5)", bases, "set",
        bool(bases), mandatory=False)

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
    pred_min = getattr(pipe, "apply_seconds", float("nan")) / 60
    add("F5", "runtime: train (evaluation + production fit) and applying the models (minutes, without API, "
        "`predict` adds loading data and weather)", {"train": round(runtime / 60, 2), "apply": round(pred_min, 3)},
        f"<= {k['F5_train_minutes']} / <= {k['F5_predict_minutes']}",
        runtime / 60 <= k["F5_train_minutes"] and pred_min <= k["F5_predict_minutes"])
    add("F6", "pytest (offline)", tests_ok, "true", tests_ok)
    f7 = f1 and f2 and f3
    add("F7", "valid outputs; the no-weather tier is evaluated and used where weather is missing", f7, "true", f7)
    return rows


def run_tests() -> bool | None:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=HERE,
                       capture_output=True, text=True)
    print("  pytest:", (r.stdout.strip().splitlines() or ["?"])[-1], flush=True)
    return r.returncode == 0


def write_weather_qc(pipe: Pipeline) -> None:
    if pipe.weather_qc is None:
        return
    (OUT / "weather_qc.json").write_text(json.dumps(jsonable({**pipe.weather_qc, "sources": pipe.cfg["meteomatics"].get("models"),
                                                             "files": pipe.weather_info}), indent=1))


def write_outputs(daily_df: pd.DataFrame, weekly_df: pd.DataFrame, skill_df: pd.DataFrame, models_out: dict) -> dict:
    (OUT / "csv").mkdir(parents=True, exist_ok=True)
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    outputs = {"forecast_daily": daily_df, "forecast_weekly": weekly_df, "forecast_skill": skill_df}
    for name, df in outputs.items():
        df.to_parquet(OUT / f"{name}.parquet", index=False)
        df.to_csv(OUT / "csv" / f"{name}.csv", index=False)
    for name, m in models_out.items():
        (OUT / "models" / f"{name}.json").write_text(json.dumps(jsonable(m), indent=1))
    return {n: sha256(OUT / f"{n}.parquet") for n in outputs}


def output_checks(pipe: Pipeline, daily_df: pd.DataFrame, weekly_df: pd.DataFrame, skill_df: pd.DataFrame) -> dict:
    """F1-F3 (contract columns, row counts, valid values); also run by `predict`."""
    p = daily_df
    f1 = list(daily_df.columns) == contract.DAILY_COLUMNS and list(weekly_df.columns) == contract.WEEKLY_COLUMNS \
        and all(c in skill_df.columns for c in contract.SKILL_COLUMNS)
    f2 = len(daily_df) == len(pipe.regions) * len(pipe.mc["leads"]) and len(weekly_df) == len(pipe.regions) * 3
    probs = weekly_df[["p_below", "p_normal", "p_above"]].to_numpy()
    f3 = bool(p[["p_big_fire_day", "p_fire_day", "p_clim_big_fire_day", "p_clim_fire_day"]].apply(lambda s: s.between(0, 1)).all().all()
              and (p["p_big_fire_day_lo"] <= p["p_big_fire_day"] + 1e-12).all() and (p["p_big_fire_day"] <= p["p_big_fire_day_hi"] + 1e-12).all()
              and np.allclose(p["risk_ratio"], p["p_big_fire_day"] / p["p_clim_big_fire_day"], atol=1e-9)
              and p["source"].isin(contract.SOURCES).all() and p["risk_class"].isin(contract.RISK_CLASSES).all()
              and np.allclose(probs.sum(axis=1), 1, atol=1e-9) and (probs >= 0).all() and (probs <= 1).all())
    return {"F1": f1, "F2": f2, "F3": f3}


def cmd_predict(cfg: dict, use_weather: bool) -> int:
    t0 = time.time()
    if not BUNDLE.exists():
        print(f"no fitted models: run `run_forecast.py train` first ({BUNDLE.relative_to(REPO)} missing)", file=sys.stderr)
        return 2
    with open(BUNDLE, "rb") as f:      # written by `train` of this repository only; never load a bundle from elsewhere
        b = pickle.load(f)
    if b.get("format") != BUNDLE_FORMAT:
        print("bundle has another format: run `run_forecast.py train` again", file=sys.stderr)
        return 2
    cfg_fp = fingerprint({k: cfg[k] for k in ("model", "risk_class")})
    if b["config_fingerprint"] != cfg_fp:
        print("warning: config.yaml changed since training (model / risk_class); retrain for consistent results",
              file=sys.stderr)
    pipe = Pipeline(cfg, use_weather=use_weather and bool(b["weather_cols"]), neighbours=b["neighbours"], weather_qc=False)
    if sorted(b["regions"]) != pipe.regions:
        print("regions differ from the training data: run `run_forecast.py train` again", file=sys.stderr)
        return 2
    daily_df, weekly_df = pipe.apply(b)
    skill_df = pipe.skill_table(b["skill_rows"])
    runtime = time.time() - t0
    checks = output_checks(pipe, daily_df, weekly_df, skill_df)
    if not all(checks.values()):
        # keep the last valid tables for the backend; nothing is overwritten
        print(f"predict output failed its checks {checks}; previous outputs kept", file=sys.stderr, flush=True)
        return 1
    out_hashes = write_outputs(daily_df, weekly_df, skill_df, pipe.models_out)
    manifest = json.loads((OUT / "manifest.json").read_text()) if (OUT / "manifest.json").exists() else {}
    inputs = {n: sha256(HARM / n) for n in ("activity_daily_harmonised.parquet", "day_status.parquet")}
    if pipe.weather is not None:
        inputs.update({p.name: sha256(p) for p in weather_files() if p.exists()})
    manifest.update({
        "model_version": b["model_version"]["weather"] if "weather" in pipe.ev["shipped_tier"].values() else b["model_version"]["noweather"],
        "issue_date": str(pipe.issue_date.date()), "weather": pipe.weather_info, "shipped_tier": pipe.ev["shipped_tier"],
        "skill_basis": sorted(skill_df["skill_basis"].unique()), "output_hashes": out_hashes,
        "predict": {"bundle_trained_issue_date": b["trained_issue_date"], "bundle_last_archive_day": b["last_archive_day"],
                    "input_hashes": inputs, "runtime_s": round(runtime, 1), "checks": checks,
                    "threads": os.environ.get("OPENBLAS_NUM_THREADS")}})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    ok = all(checks.values())
    print(f"predict for issue date {pipe.issue_date.date()} in {runtime:.1f} s; tiers {sorted(set(pipe.ev['shipped_tier'].values()))}; "
          f"checks {'ok' if ok else checks}", flush=True)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["train", "predict", "all", "weather-qc"])
    ap.add_argument("--no-weather", action="store_true", help="no-weather tier only")
    ap.add_argument("--force", action="store_true", help="recompute even if inputs are unchanged (always recomputes for now)")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load((HERE / "config.yaml").read_text())
    if args.cmd == "predict":
        return cmd_predict(cfg, use_weather=not args.no_weather)
    t0 = time.time()
    pipe = Pipeline(cfg, use_weather=not args.no_weather)
    print(f"data: {len(pipe.d)} rows, issue date {pipe.issue_date.date()}, last archive day {pipe.last_archive.date()}, "
          f"weather: {pipe.weather_info or 'none'}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    write_weather_qc(pipe)
    if args.cmd == "weather-qc":
        qc = pipe.weather_qc
        print(json.dumps(jsonable({"A5": qc["A5"], "A6": qc["A6"]["total"]}) if qc else "no weather", indent=1))
        return 0 if qc and qc["A6"]["passed"] and all(v["passed"] for v in qc["A5"].values()) else 1
    pipe.select_weather_set()
    pipe.evaluate_daily()
    pipe.evaluate_loyo()
    pipe.evaluate_weekly()
    bundle = pipe.fit_production()
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    with open(BUNDLE, "wb") as f:
        pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
    t_apply = time.time()
    daily_df, weekly_df = pipe.apply(bundle)
    pipe.apply_seconds = time.time() - t_apply
    runtime = time.time() - t0
    skill_df = pipe.skill_table()
    checks = leakage_checks(pipe)
    fwi_dev = fwi_reference_check()
    out_hashes = write_outputs(daily_df, weekly_df, skill_df, pipe.models_out)
    ev = {**pipe.ev, "weather_features": {"daily": pipe.weather_cols, "weekly": pipe.weekly_weather_cols}}
    (OUT / "forecast_evaluation.json").write_text(json.dumps(jsonable(ev), indent=1))

    prev = json.loads((OUT / "manifest.json").read_text()) if (OUT / "manifest.json").exists() else None
    inputs = {n: sha256(HARM / n) for n in ("activity_daily_harmonised.parquet", "day_status.parquet", "hotspots_harmonised.parquet")}
    if pipe.weather is not None:
        inputs.update({p.name: sha256(p) for p in weather_files() if p.exists()})
    version = cfg["model"]["version"] if "weather" in pipe.ev["shipped_tier"].values() else cfg["model"]["version_noweather"]
    manifest = {"model_version": version, "evaluated_tiers": list(pipe.tiers), "issue_date": str(pipe.issue_date.date()),
                "last_archive_day": str(pipe.last_archive.date()),
                "training_period": {"evaluation": [cfg["model"]["viirs_start"], cfg["model"]["train_end"]],
                                    "test": [cfg["model"]["test_start"], str(pipe.last_archive.date())],
                                    "production": [cfg["model"]["viirs_start"], str(pipe.last_archive.date())]},
                "fingerprints": {"config": fingerprint({k: cfg[k] for k in ("model", "risk_class", "meteomatics")}),
                                 "code": code_fingerprint(), "inputs": fingerprint(inputs)},
                "input_hashes": inputs, "weather": pipe.weather_info, "shipped_tier": pipe.ev["shipped_tier"],
                "skill_basis": sorted(skill_df["skill_basis"].unique()), "bundle": {"file": str(BUNDLE.relative_to(REPO)),
                                                                                   "sha256": sha256(BUNDLE)},
                "threads": os.environ.get("OPENBLAS_NUM_THREADS"), "output_hashes": out_hashes}
    tests_ok = None if args.skip_tests else run_tests()
    kpis = kpi_report(pipe, daily_df, weekly_df, skill_df, checks, runtime, tests_ok, prev, manifest, fwi_dev)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (OUT / "forecast_kpi_report.json").write_text(json.dumps({"generated_for_issue_date": str(pipe.issue_date.date()),
                                                             "kpis": kpis}, indent=1))
    failed = [r["kpi"] for r in kpis if r["mandatory"] and r["passed"] is False]
    print(f"done in {runtime / 60:.1f} min; mandatory KPIs failed: {failed or 'none'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
