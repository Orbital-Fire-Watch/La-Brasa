"""Targets and no-weather features from the harmonised daily table.

All features of a row describe the *issue date* (the last known day) and use only data up to and
including that day. A forecast for lead L pairs the features of day t0 with the target of day t0 + L.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from features.climatology import day_of_year_noleap

ISSUE_FEATURES = ["logfrp_last", "logfrp_mean3", "logfrp_mean7", "logfrp_mean30", "fire_last", "fire_frac7",
                  "fire_frac30", "big_frac30", "log_days_since_big", "nbr_logfrp_last"]


def load_daily(harm_dir: Path, viirs_start: str) -> pd.DataFrame:
    """Daily table from viirs_start on, with targets.

    big   = big_fire_day on usable rows (VIIRS measured, complete, no possible gap), else NaN
    fire  = n_snpp > 0 on usable rows where SNPP operates, else NaN (SNPP only: no satellite-count effect)
    logfrp = log1p(frp_harm) on usable rows, else NaN
    """
    d = pd.read_parquet(harm_dir / "activity_daily_harmonised.parquet",
                        columns=["region_id", "region_name", "date", "basis_count", "is_complete_day", "possible_gap",
                                 "big_fire_day", "n_snpp", "frp_snpp", "frp_harm", "strength_class"])
    ds = pd.read_parquet(harm_dir / "day_status.parquet", columns=["date", "snpp_operating", "is_provisional"])
    d["date"] = pd.to_datetime(d["date"])
    ds["date"] = pd.to_datetime(ds["date"])
    d = d.merge(ds, on="date", how="left")
    d = d[d["date"] >= pd.Timestamp(viirs_start)].sort_values(["region_id", "date"]).reset_index(drop=True)
    usable = (d["basis_count"] == "viirs_measured") & d["is_complete_day"].astype(bool) & ~d["possible_gap"].astype(bool)
    d["usable"] = usable
    d["big"] = np.where(usable, d["big_fire_day"].astype(float), np.nan)
    snpp_ok = usable & d["snpp_operating"].fillna(False).astype(bool) & d["n_snpp"].notna()
    d["fire"] = np.where(snpp_ok, (d["n_snpp"] > 0).astype(float), np.nan)
    d["logfrp"] = np.where(usable, np.log1p(d["frp_harm"].fillna(0.0)), np.nan)
    d["logfrp_snpp"] = np.where(snpp_ok, np.log1p(d["frp_snpp"].fillna(0.0)), np.nan)
    d["doy"] = day_of_year_noleap(d["date"])
    d["is_provisional"] = d["is_provisional"].fillna(True).astype(bool)
    return d


def region_neighbours(harm_dir: Path, train_end: str, k: int) -> dict[str, list[str]]:
    """k nearest regions by the centroid of their VIIRS detections up to train_end (great-circle distance)."""
    h = pd.read_parquet(harm_dir / "hotspots_harmonised.parquet",
                        columns=["region_id", "latitude", "longitude", "sensor", "obs_date"])
    h = h[(h["sensor"] == "VIIRS") & h["region_id"].notna() & (pd.to_datetime(h["obs_date"]) <= pd.Timestamp(train_end))]
    cen = h.groupby("region_id")[["latitude", "longitude"]].mean().sort_index()
    lat, lon = np.radians(cen["latitude"].to_numpy()), np.radians(cen["longitude"].to_numpy())
    cosd = np.sin(lat[:, None]) * np.sin(lat) + np.cos(lat[:, None]) * np.cos(lat) * np.cos(lon[:, None] - lon)
    dist = np.arccos(np.clip(cosd, -1, 1))
    np.fill_diagonal(dist, np.inf)
    return {r: [cen.index[j] for j in np.argsort(dist[i], kind="stable")[:k]] for i, r in enumerate(cen.index)}


def _wide(d: pd.DataFrame, col: str) -> pd.DataFrame:
    return d.pivot(index="date", columns="region_id", values=col).sort_index()


def _roll(m: pd.DataFrame, w: int) -> pd.DataFrame:
    return m.rolling(w, min_periods=int(np.ceil(w / 2))).mean()


def _days_since_event(m: pd.DataFrame, cap: int) -> pd.DataFrame:
    """Days since the last day with value 1 (0 on an event day); NaN counts as no event; capped."""
    idx = np.arange(len(m), dtype=float)[:, None]
    last = pd.DataFrame(np.where(m.to_numpy() == 1, idx, np.nan), index=m.index, columns=m.columns).ffill()
    out = idx - last.to_numpy()
    return pd.DataFrame(np.minimum(np.nan_to_num(out, nan=cap), cap), index=m.index, columns=m.columns)


def issue_features(d: pd.DataFrame, neighbours: dict[str, list[str]], cap_days: int = 365) -> pd.DataFrame:
    """Features per (region, issue date), aligned to the rows of `d`. Only past and present values are used."""
    P, F, B = _wide(d, "logfrp"), _wide(d, "fire"), _wide(d, "big")
    nbr = pd.DataFrame({r: P[[n for n in ns if n in P.columns]].mean(axis=1) for r, ns in neighbours.items()
                        if r in P.columns}).reindex(columns=P.columns)
    mats = {
        "logfrp_last": P, "logfrp_mean3": _roll(P, 3), "logfrp_mean7": _roll(P, 7), "logfrp_mean30": _roll(P, 30),
        "fire_last": F, "fire_frac7": _roll(F, 7), "fire_frac30": _roll(F, 30), "big_frac30": _roll(B, 30),
        "log_days_since_big": np.log1p(_days_since_event(B, cap_days)), "nbr_logfrp_last": nbr,
    }
    key = pd.MultiIndex.from_arrays([d["date"], d["region_id"]])
    out = pd.DataFrame({name: m.stack(future_stack=True).reindex(key).to_numpy() for name, m in mats.items()},
                       index=d.index)
    return out[ISSUE_FEATURES]


def lead_pairs(d: pd.DataFrame, feats: pd.DataFrame, target: str, lead: int) -> pd.DataFrame:
    """Rows of (issue date t0, target day t0 + lead): features of t0, target value and day of year of t0 + lead.

    Requires `d` sorted by region and date with gap-free daily rows per region.
    """
    g = d.groupby("region_id", sort=False)
    out = feats.copy()
    out["region_id"] = d["region_id"].to_numpy()
    out["issue_date"] = d["date"].to_numpy()
    out["target_date"] = out["issue_date"] + pd.Timedelta(days=lead)
    out["y"] = g[target].shift(-lead).to_numpy()
    out["target_doy"] = day_of_year_noleap(out["target_date"])
    out["target_weekday"] = out["target_date"].dt.day_of_week.to_numpy()
    out["target_provisional"] = g["is_provisional"].shift(-lead).to_numpy()
    out["lead"] = lead
    return out
