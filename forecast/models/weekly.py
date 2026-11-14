"""Weekly outlook (weeks 2-4): below / normal / above usual fire activity.

Target per region and week (Monday-Sunday): sum of log1p(frp_harm) over the week, only complete weeks.
Classes come from the terciles of the training weeks of the same region and week of year (+-window weeks).
Many weeks have activity 0; ties go to the lower class (x <= q1 -> below), so the actual class shares in
the training years are not exactly 1/3. Those empirical shares are the climatological forecast (reference).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from features.climatology import day_of_year_noleap, lookup
from models.logistic import Design, fit_multinomial, predict_multinomial

N_WEEK = 52
WEEK_FEATURES = ["clim_log_below", "clim_log_above", "logfrp_mean7", "logfrp_mean30", "anom30", "big_frac30"]


def week_of_year(week_start: pd.Series) -> np.ndarray:
    return np.minimum(pd.to_datetime(week_start).dt.isocalendar().week.to_numpy().astype(int), N_WEEK)


def weekly_table(d: pd.DataFrame, value_col: str = "logfrp") -> pd.DataFrame:
    """Per region and week: activity = sum of `value_col` (logfrp or logfrp_snpp); complete = 7 days with a value."""
    w = d[["region_id", "date", value_col, "big", "is_provisional"]].copy()
    w["has_value"] = w[value_col].notna()
    w["week_start"] = w["date"] - pd.to_timedelta(w["date"].dt.day_of_week, unit="D")
    out = w.groupby(["region_id", "week_start"]).agg(
        n_days=("date", "size"), n_usable=("has_value", "sum"), activity=(value_col, "sum"),
        big_days=("big", "sum"), provisional=("is_provisional", "max")).reset_index()
    out["complete"] = (out["n_days"] == 7) & (out["n_usable"] == 7)
    out["woy"] = week_of_year(out["week_start"])
    return out


@dataclass
class WeekClimatology:
    table: pd.DataFrame   # index (region_id, woy): q1, q2, share_0..2, big_mean_0..2

    def classes(self, weeks: pd.DataFrame) -> np.ndarray:
        t = self.table.reindex(pd.MultiIndex.from_arrays([weeks["region_id"], weeks["woy"]]))
        x = weeks["activity"].to_numpy()
        return np.where(x <= t["q1"].to_numpy(), 0, np.where(x > t["q2"].to_numpy(), 2, 1))

    def get(self, region: pd.Series, woy: np.ndarray, cols: list[str]) -> np.ndarray:
        return self.table.reindex(pd.MultiIndex.from_arrays([region, woy]))[cols].to_numpy()


def fit_week_climatology(weeks: pd.DataFrame, train_mask: np.ndarray, window: int) -> WeekClimatology:
    tr = weeks[train_mask & weeks["complete"].to_numpy()]
    rows = []
    for region, g in tr.groupby("region_id"):
        for woy in range(1, N_WEEK + 1):
            dist = np.minimum(np.abs(g["woy"] - woy), N_WEEK - np.abs(g["woy"] - woy))
            s = g[dist <= window]
            x = s["activity"].to_numpy()
            q1, q2 = np.quantile(x, [1 / 3, 2 / 3])
            cls = np.where(x <= q1, 0, np.where(x > q2, 2, 1))
            row = {"region_id": region, "woy": woy, "q1": q1, "q2": q2, "n_weeks": len(x)}
            for c in range(3):
                row[f"share_{c}"] = float((cls == c).mean())
                row[f"big_mean_{c}"] = float(s["big_days"].to_numpy()[cls == c].mean()) if (cls == c).any() else 0.0
            rows.append(row)
    return WeekClimatology(pd.DataFrame(rows).set_index(["region_id", "woy"]))


def week_pairs(d: pd.DataFrame, feats: pd.DataFrame, weeks: pd.DataFrame, wclim: WeekClimatology,
               logfrp_clim: pd.DataFrame, week_ahead: int, issue_mask: np.ndarray) -> pd.DataFrame:
    """Pairs (issue date t0, target week). Week 1 starts on the first Monday after t0; week k = week 1 + 7(k-1) days."""
    base = d.loc[issue_mask, ["region_id", "date"]].copy()
    f = feats.loc[issue_mask]
    base["issue_date"] = base["date"]
    days_to_monday = 7 - base["issue_date"].dt.day_of_week
    base["week_start"] = base["issue_date"] + pd.to_timedelta(days_to_monday + 7 * (week_ahead - 1), unit="D")
    base["woy"] = week_of_year(base["week_start"])
    for c in ["logfrp_mean7", "logfrp_mean30", "big_frac30"]:
        base[c] = f[c].to_numpy()
    mid = base["issue_date"] - pd.Timedelta(days=15)
    base["anom30"] = base["logfrp_mean30"] - lookup(logfrp_clim, base["region_id"], day_of_year_noleap(mid))
    sh = wclim.get(base["region_id"], base["woy"].to_numpy(), ["share_0", "share_1", "share_2"])
    sh = np.clip(np.nan_to_num(sh, nan=1 / 3), 0.02, 1)
    sh = sh / sh.sum(axis=1, keepdims=True)
    base[["clim_p_below", "clim_p_normal", "clim_p_above"]] = sh
    base["clim_log_below"] = np.log(sh[:, 0] / sh[:, 1])
    base["clim_log_above"] = np.log(sh[:, 2] / sh[:, 1])
    tgt = weeks.set_index(["region_id", "week_start"])
    key = pd.MultiIndex.from_arrays([base["region_id"], base["week_start"]])
    t = tgt.reindex(key)
    base["complete"] = t["complete"].fillna(False).to_numpy().astype(bool)
    base["provisional"] = t["provisional"].fillna(True).to_numpy().astype(bool)
    base["activity"] = t["activity"].to_numpy()
    base["big_days"] = t["big_days"].to_numpy()
    base["y_class"] = np.where(base["complete"], wclim.classes(base.assign(activity=base["activity"].fillna(0))), -1)
    base["week_ahead"] = week_ahead
    return base.drop(columns=["date"])


@dataclass
class WeeklyModel:
    week_ahead: int
    design: Design
    W: np.ndarray

    def to_dict(self) -> dict:
        return {"week_ahead": self.week_ahead, "design": self.design.to_dict(), "W": self.W.tolist()}


def train(pairs: pd.DataFrame, week_ahead: int, l2: float) -> WeeklyModel:
    design = Design(continuous=WEEK_FEATURES).fit(pairs)
    X = design.matrix(pairs)
    W = fit_multinomial(X, pairs["y_class"].to_numpy(), 3, design.penalty(l2, l2))
    return WeeklyModel(week_ahead, design, W)


def predict(model: WeeklyModel, pairs: pd.DataFrame) -> np.ndarray:
    return predict_multinomial(model.design.matrix(pairs), model.W)
