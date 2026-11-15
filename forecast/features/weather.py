"""Weather per region and day: load, check (KPIs A5/A6), FWI and derived features.

Inputs (written by fetch_weather.py, all at 12:00 UTC, *_24h values over the 24 h ending then):
  data/forecast/weather_points_history_{core,fire}.parquet     per weather point (182 points, 2012-01-20 ..)
  data/forecast/weather_points_recent_{core,fire}.parquet      optional, days after the end of the history (ERA5)
  data/forecast/weather_points_forecast_{core,fire}_<day>.parquet   optional, 10-day forecast from <day>
  data/forecast/weather_points.parquet                          points and their weights per region

All features of a day use only weather up to and including that day. A forecast row for target day t0 + L takes
the weather features of that target day; in the evaluation this is analysed weather (an upper bound for the
real forecast, see skill_basis), in the live forecast it is history up to t0 continued with the forecast.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from features.climatology import day_of_year_noleap, smooth_circular
from features.fwi import COMPONENTS as FWI_COMPONENTS
from features.fwi import fwi_series

RENAME = {
    "t_2m:C": "t2m", "relative_humidity_2m:p": "rh", "wind_speed_10m:kmh": "wind", "precip_24h:mm": "precip",
    "t_max_2m_24h:C": "tmax", "t_min_2m_24h:C": "tmin", "wind_gusts_10m_24h:kmh": "gust", "dew_point_2m:C": "td",
    "fosberg_fire_weather_index:idx": "fosberg", "forest_fire_warning:idx": "ffw", "drought_index:idx": "drought",
}
GROUPS = {"core": ["t2m", "rh", "wind", "precip", "tmax", "tmin", "gust", "td"],
          "fire": ["fosberg", "ffw", "drought"]}
# KPI A6: physically plausible ranges (lower, upper); None = open. The Fosberg index is scaled to 100 at zero fuel
# moisture and 30 mph wind; stronger wind gives values above 100 (formula), so it has no upper bound here.
# The prompt fixes -25..50 °C for t_2m (noon). The daily minimum gets -40 °C: mountain cells reach -26 °C in cold
# waves (eastern Pyrenees, 9 Feb 2018, ERA5).
PLAUSIBLE = {"t2m": (-25, 50), "tmax": (-25, 50), "tmin": (-40, 50), "td": (-45, 40), "rh": (0, 100),
             "precip": (0, 300), "wind": (0, None), "gust": (0, None), "fosberg": (0, None), "ffw": (0, 1),
             "drought": (-4, 4)}
A5_MIN_SHARE = {"core": 0.995, "fire": 0.95}

# features of the target day used by the daily models (chosen on validation, see run_forecast.select_weather_set)
WEATHER_SETS = {
    "small": ["log_fwi", "dc", "rh", "tmax", "log_days_since_rain"],
    "fwi": ["ffmc", "dmc", "dc", "log_isi", "bui", "log_fwi", "tmax", "rh", "vpd", "gust", "precip",
            "log_days_since_rain", "rain30", "rain90_anom", "fosberg", "ffw", "drought"],
    "fwi_anom": ["ffmc", "dmc", "dc", "log_isi", "bui", "log_fwi", "tmax", "rh", "vpd", "gust", "precip",
                 "log_days_since_rain", "rain30", "rain90_anom", "fosberg", "ffw", "drought",
                 "fwi_anom", "dc_anom", "tmax_anom", "vpd_anom"],
}
# Sets from the core variables only (own FWI, own Fosberg): they work with every IFS source (Meteomatics until
# 22.11.2026, Open-Meteo afterwards) and can be perturbed with forecast errors (features/perturb.py).
CORE_SETS = {
    "small_core": ["log_fwi", "dc", "rh", "tmax", "log_days_since_rain"],
    "fwi_core": ["ffmc", "dmc", "dc", "log_isi", "bui", "log_fwi", "tmax", "rh", "vpd", "gust", "precip",
                 "log_days_since_rain", "rain30", "rain90_anom", "fosberg_own"],
    "fwi_anom_core": ["ffmc", "dmc", "dc", "log_isi", "bui", "log_fwi", "tmax", "rh", "vpd", "gust", "precip",
                      "log_days_since_rain", "rain30", "rain90_anom", "fosberg_own",
                      "fwi_anom", "dc_anom", "tmax_anom", "vpd_anom"],
    "fwi_anom_core_nl": ["ffmc", "dmc", "dc", "log_isi", "bui", "log_fwi", "tmax", "rh", "vpd", "gust", "precip",
                         "log_days_since_rain", "rain30", "rain90_anom", "fosberg_own",
                         "fwi_anom", "dc_anom", "tmax_anom", "vpd_anom",
                         "log_fwi_x_clim", "dc_x_clim", "log_fwi_sq"],
}
# non-linear terms built from target-day features and the seasonal curve (run_forecast.Pipeline.pairs)
INTERACTIONS = {"log_fwi_x_clim": ("log_fwi", "clim_logit"), "dc_x_clim": ("dc", "clim_logit"),
                "log_fwi_sq": ("log_fwi", "log_fwi")}
# slow drought features known on the issue date, for the weekly outlook (core variables only)
WEEKLY_WEATHER = ["dc", "dmc", "dc_anom", "rain90_anom"]
ANOMALY_OF = {"fwi_anom": "fwi", "dc_anom": "dc", "tmax_anom": "tmax", "vpd_anom": "vpd", "rain90_anom": "rain90"}
RAIN_DAY_MM = 1.0
DAYS_SINCE_RAIN_CAP = 120


# --- loading ------------------------------------------------------------------------------------------------
def _read_points(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path).rename(columns=RENAME)
    df["date"] = pd.to_datetime(df["validdate"].dt.tz_convert("UTC").dt.date)
    df[["lat", "lon"]] = df[["lat", "lon"]].round(4)
    return df.drop(columns=["validdate"])


def latest_forecast_file(out_dir: Path, group: str) -> Path | None:
    files = sorted(out_dir.glob(f"weather_points_forecast_{group}_*.parquet"))
    return files[-1] if files else None


def load_point_weather(out_dir: Path, with_forecast: bool = True) -> tuple[pd.DataFrame, dict]:
    """Point weather, one row per (lat, lon, date), history continued by the newest forecast file.

    Returns the table and info {group: {"history_end", "forecast_file", "forecast_end"}}. Column `lead_day` says
    where the core values come from: -1 history (ERA5), 0 recent days (IFS), j >= 0 forecast j days after the day
    the forecast was fetched (used by the bias correction, features/perturb.py).
    """
    parts, info = [], {}
    for group in GROUPS:
        h = _read_points(out_dir / f"weather_points_history_{group}.parquet")
        if group == "core":
            h["lead_day"] = -1
        gi = {"history_end": str(h["date"].max().date()), "recent_end": None, "forecast_file": None,
              "forecast_end": None}
        r_path = out_dir / f"weather_points_recent_{group}.parquet"
        if r_path.exists():
            r = _read_points(r_path)
            r = r[r["date"] > h["date"].max()]
            if group == "core":
                r["lead_day"] = 0
            if len(r):
                h = pd.concat([h, r], ignore_index=True)
                gi["recent_end"] = str(r["date"].max().date())
        f_path = latest_forecast_file(out_dir, group) if with_forecast else None
        if f_path is not None:
            f = _read_points(f_path)
            f = f[f["date"] > h["date"].max()]
            if group == "core":
                start = pd.Timestamp(f_path.stem.rsplit("_", 1)[-1])
                f["lead_day"] = (f["date"] - start).dt.days.clip(lower=0)
            if len(f):
                h = pd.concat([h, f], ignore_index=True)
                gi.update(forecast_file=f_path.name, forecast_end=str(f["date"].max().date()))
        parts.append(h.set_index(["lat", "lon", "date"]))
        info[group] = gi
    pts = parts[0].join(parts[1], how="outer").reset_index().sort_values(["lat", "lon", "date"])
    return pts.reset_index(drop=True), info


def load_points(out_dir: Path) -> pd.DataFrame:
    p = pd.read_parquet(out_dir / "weather_points.parquet")
    p[["lat", "lon"]] = p[["lat", "lon"]].round(4)
    return p


# --- FWI per point, then fire-weighted mean per region --------------------------------------------------------
def point_fwi(pts: pd.DataFrame) -> pd.DataFrame:
    """FWI components per point and day, all points at once (days x points matrices).

    Missing days are inserted as gaps: the codes then keep their value and the indices are NaN that day."""
    days = pd.date_range(pts["date"].min(), pts["date"].max(), freq="D")
    wide = {c: pts.pivot_table(index="date", columns=["lat", "lon"], values=c, aggfunc="first").reindex(days)
            for c in ("t2m", "rh", "wind", "precip")}
    cols = wide["t2m"].columns
    comp = fwi_series(wide["t2m"].to_numpy(), wide["rh"][cols].to_numpy(), wide["wind"][cols].to_numpy(),
                      np.clip(wide["precip"][cols].to_numpy(), 0, None), days.month.to_numpy())
    out = pd.DataFrame({"date": np.repeat(days.to_numpy(), len(cols)),
                        "lat": np.tile(cols.get_level_values(0).to_numpy(), len(days)),
                        "lon": np.tile(cols.get_level_values(1).to_numpy(), len(days))})
    for c in FWI_COMPONENTS:
        out[c] = comp[c].reshape(-1)
    return out


def to_regions(point_values: pd.DataFrame, points: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Weighted mean per region and date; weights renormalised over the points with a value (vectorised)."""
    m = point_values.merge(points[["region_id", "lat", "lon", "weight"]], on=["lat", "lon"], how="inner")
    res = {}
    for c in cols:
        ok = m[c].notna()
        w = m["weight"].where(ok, 0.0)
        res[c + "__wx"] = (m[c].fillna(0.0) * w)
        res[c + "__w"] = w
    agg = pd.concat([m[["region_id", "date"]], pd.DataFrame(res)], axis=1).groupby(["region_id", "date"]).sum()
    out = pd.DataFrame({c: agg[c + "__wx"] / agg[c + "__w"].replace(0.0, np.nan) for c in cols}, index=agg.index)
    return out.reset_index()


def region_weather(pts: pd.DataFrame, points: pd.DataFrame) -> pd.DataFrame:
    """Region x date: all Meteomatics variables plus the six FWI components (computed per point)."""
    base = to_regions(pts, points, GROUPS["core"] + GROUPS["fire"])
    fw = to_regions(point_fwi(pts), points, FWI_COMPONENTS)
    return base.merge(fw, on=["region_id", "date"], how="left").sort_values(["region_id", "date"]).reset_index(drop=True)


# --- derived features ---------------------------------------------------------------------------------------
def saturation_vapour_pressure(t_c: np.ndarray) -> np.ndarray:
    """kPa (Tetens / FAO-56)."""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def _days_since(flag: pd.Series, cap: int) -> np.ndarray:
    idx = np.arange(len(flag), dtype=float)
    last = pd.Series(np.where(flag.to_numpy(), idx, np.nan)).ffill().to_numpy()
    return np.minimum(np.nan_to_num(idx - last, nan=cap), cap)


def add_derived(w: pd.DataFrame, train_end: str) -> pd.DataFrame:
    """VPD, dryness before the day, log transforms and anomalies against the 2012..train_end mean per region and
    day of year (smoothed +-7 days). Requires gap-free days per region, sorted by region and date."""
    w = w.sort_values(["region_id", "date"]).reset_index(drop=True).copy()
    w["vpd"] = np.maximum(saturation_vapour_pressure(w["t2m"]) - saturation_vapour_pressure(w["td"]), 0.0)
    g = w.groupby("region_id", sort=False)
    w["rain30"] = g["precip"].transform(lambda s: s.rolling(30, min_periods=15).sum())
    w["rain90"] = g["precip"].transform(lambda s: s.rolling(90, min_periods=45).sum())
    w["log_days_since_rain"] = np.log1p(np.concatenate(
        [_days_since(s >= RAIN_DAY_MM, DAYS_SINCE_RAIN_CAP) for _, s in g["precip"]]))
    w["fosberg_own"] = fosberg_index(w["t2m"].to_numpy(), w["rh"].to_numpy(), w["wind"].to_numpy())
    w["log_fwi"] = np.log1p(w["fwi"])
    w["log_isi"] = np.log1p(w["isi"])
    w["doy"] = day_of_year_noleap(w["date"])
    train = w["date"] <= pd.Timestamp(train_end)
    for name, src in ANOMALY_OF.items():
        t = (w[train].groupby(["region_id", "doy"])[src].mean().unstack().reindex(columns=range(1, 366)))
        t = t.apply(lambda r: r.interpolate(limit_direction="both"), axis=1)
        sm = pd.DataFrame(smooth_circular(t.to_numpy(), 7), index=t.index, columns=t.columns)
        ri = sm.index.get_indexer(w["region_id"])
        w[name] = w[src].to_numpy() - sm.to_numpy()[ri, w["doy"].to_numpy() - 1]
    return w.drop(columns=["doy"])


def correct_points(pts: pd.DataFrame, points: pd.DataFrame, correction) -> pd.DataFrame:
    """Bias correction of the IFS rows (recent days and forecast) towards ERA5, per region, month and lead day."""
    pts = pts.copy()
    live = pts["lead_day"].fillna(-1).to_numpy() >= 0
    if not live.any():
        return pts
    reg = pts.loc[live, ["lat", "lon"]].merge(points[["lat", "lon", "region_id"]].drop_duplicates(["lat", "lon"]),
                                              on=["lat", "lon"], how="left")["region_id"].to_numpy()
    sub = pts.loc[live]
    months = sub["date"].dt.month.to_numpy()
    out = {v: sub[v].to_numpy(float).copy() for v in ("t2m", "rh", "wind", "precip", "tmax", "gust", "td")}
    for ld in np.unique(sub["lead_day"].to_numpy(int)):
        m = sub["lead_day"].to_numpy(int) == ld
        corr = correction.apply({v: x[m] for v, x in out.items()}, reg[m], months[m], int(ld))
        for v in out:
            out[v][m] = corr[v]
    from features.perturb import clip_weather
    out = clip_weather(out)
    for v, x in out.items():
        pts.loc[live, v] = x
    return pts


def build_region_weather(out_dir: Path, train_end: str, with_forecast: bool = True,
                         correction=None) -> tuple[pd.DataFrame, dict]:
    pts, info = load_point_weather(out_dir, with_forecast)
    points = load_points(out_dir)
    if correction is not None:
        pts = correct_points(pts, points, correction)
        info = {**info, "bias_correction": True}
    w = add_derived(region_weather(pts, points), train_end)
    return w, info


# --- KPI A5 / A6 and gap tables -----------------------------------------------------------------------------
def quality_report(pts: pd.DataFrame, regions_w: pd.DataFrame, regions: list[str], start: str, end: str) -> dict:
    """Completeness (A5) per group on the full region x day grid, plausibility (A6), gaps per region and year,
    point-level gaps and simple consistency / outlier checks. History rows only (date <= end)."""
    days = pd.date_range(start, end, freq="D")
    grid = pd.MultiIndex.from_product([sorted(regions), days], names=["region_id", "date"])
    rw = regions_w.set_index(["region_id", "date"]).reindex(grid)
    rep: dict = {"period": [start, end], "n_regions": len(regions), "n_days": len(days), "A5": {}, "A6": {},
                 "gaps_region_year": {}, "points": {}, "consistency": {}, "outliers": {}}
    for group, cols in GROUPS.items():
        present = float(rw[cols].notna().to_numpy().mean())
        rep["A5"][group] = {"share_present": present, "threshold": A5_MIN_SHARE[group],
                            "passed": present >= A5_MIN_SHARE[group]}
        miss = rw[cols].isna().any(axis=1).groupby([rw.index.get_level_values(0), rw.index.get_level_values(1).year]).sum()
        rep["gaps_region_year"][group] = {f"{r}_{y}": int(v) for (r, y), v in miss.items() if v > 0}
        p = pts[pts["date"] <= pd.Timestamp(end)]
        by_pt = p[cols].isna().any(axis=1).groupby([p["lat"], p["lon"]]).mean()
        rep["points"][group] = {"n_points": int(len(by_pt)), "points_with_gaps": int((by_pt > 0).sum()),
                                "points_always_missing": int((by_pt == 1).sum()),
                                "share_missing_point_days": float(p[cols].isna().any(axis=1).mean())}
    viol, total = {}, 0
    for c, (lo, hi) in PLAUSIBLE.items():
        for name, v in (("region", rw[c]), ("point", pts.loc[pts["date"] <= pd.Timestamp(end), c])):
            bad = int((v < lo).sum() if lo is not None else 0) + int((v > hi).sum() if hi is not None else 0)
            viol[f"{c}_{name}"] = bad
            total += bad
    rep["A6"] = {"violations": viol, "total": total, "passed": total == 0}
    tol = 0.5
    rep["consistency"] = {
        "dew_point_above_t2m": int((rw["td"] > rw["t2m"] + tol).sum()),
        "t2m_below_tmin": int((rw["t2m"] < rw["tmin"] - tol).sum()),
        "t2m_above_tmax": int((rw["t2m"] > rw["tmax"] + tol).sum()),
        "tolerance_C": tol,
    }
    d1 = rw["t2m"].groupby(level=0).diff().abs()
    runs = {}
    for c in ("t2m", "rh", "wind"):
        same = rw[c].groupby(level=0).diff().eq(0)
        run_id = (~same).groupby(level=0).cumsum()
        longest = same.groupby([rw.index.get_level_values(0), run_id]).sum().max()
        runs[c] = int(longest) + 1
    rep["outliers"] = {"t2m_day_to_day_jump_gt_15C": int((d1 > 15).sum()), "precip_gt_100mm": int((rw["precip"] > 100).sum()),
                       "longest_constant_run_days": runs}
    return rep


def signal_check(w: pd.DataFrame, fire: pd.DataFrame, train_end: str, months=(6, 7, 8, 9)) -> dict:
    """How well each weather feature of a day separates big-fire days from other days (ROC-AUC, 0.5 = no signal).

    Training years only, fire season months only (so the season itself does not create the signal), pooled over
    regions; raw value and value minus the region mean of that month (removes 'hot regions burn more')."""
    from evaluate import roc_auc
    m = fire[["region_id", "date", "big"]].merge(w, on=["region_id", "date"], how="inner")
    m = m[m["big"].notna() & (m["date"] <= pd.Timestamp(train_end)) & m["date"].dt.month.isin(months)]
    y = m["big"].to_numpy()
    cols = sorted({c for s in WEATHER_SETS.values() for c in s})
    out = {}
    for c in cols:
        v = m[c]
        ok = v.notna().to_numpy()
        within = v - m.groupby(["region_id", m["date"].dt.month])[c].transform("mean")
        out[c] = {"auc": roc_auc(y[ok], v.to_numpy()[ok]), "auc_within_region_month": roc_auc(y[ok], within.to_numpy()[ok])}
    return {"months": list(months), "train_end": train_end, "n": int(len(m)), "n_big": int(y.sum()), "features": out}


def fosberg_index(t_c: np.ndarray, rh: np.ndarray, wind_kmh: np.ndarray) -> np.ndarray:
    """Fosberg fire weather index (Fosberg 1978; Goodrick 2002), from temperature, humidity and wind.

    Equilibrium moisture content m (%) from T (°F) and RH, moisture damping eta, wind U in mph:
    FFWI = eta * sqrt(1 + U^2) / 0.3002. Computed here so that the model does not need the Meteomatics index."""
    t = np.asarray(t_c, float) * 9 / 5 + 32
    h = np.clip(np.asarray(rh, float), 0, 100)
    u = np.asarray(wind_kmh, float) / 1.609344
    m = np.where(h < 10, 0.03229 + 0.281073 * h - 0.000578 * h * t,
                 np.where(h < 50, 2.22749 + 0.160107 * h - 0.01478 * t,
                          21.0606 + 0.005565 * h ** 2 - 0.00035 * h * t - 0.483199 * h))
    x = np.clip(m, 0, 30) / 30.0
    eta = 1 - 2 * x + 1.5 * x ** 2 - 0.5 * x ** 3
    return eta * np.sqrt(1 + u ** 2) / 0.3002
