"""Real errors of the ECMWF IFS weather forecast per lead day, for the honest evaluation (step 5) and the bias
correction of the live forecast.

Meteomatics keeps no archived forecasts (get_init_date gives 0000-00-00 for past days, checked 15.11.2026). The
Open-Meteo Previous Runs API does: for every hour it returns the value forecast 0, 1, ..., 7 days before
(`<variable>_previous_dayN`, ECMWF IFS 0.25°). Comparing those with ERA5 at the same points gives the error that the
model meets in production, because it was trained on ERA5 and is fed with IFS forecasts.

Data: Open-Meteo (https://open-meteo.com), licence CC BY 4.0, free for non-commercial use.

Daily values as in features/weather.py: 12:00 UTC for t2m, rh, wind; the 24 h up to 12:00 UTC for precip (sum),
tmax and gust (max). The dew point follows from t2m and rh (Magnus formula).

Lead mapping: the daily job runs on the morning after the issue date t0 with the 00 UTC run of t0 + 1, so the
weather of target day t0 + L is a forecast (L - 1) days + 12 h ahead -> previous_day(L - 1). Leads 9 and 10 need
previous_day 8 and 9, which the API does not have; their errors are the day-7 errors scaled with the growth of the
error spread over days 4-7 (`growth_factors`, used in features/perturb.py). Gusts of previous runs are not
archived either; see `error_table`.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
MODEL = "ecmwf_ifs025"
HOURLY = {"temperature_2m": "t2m", "relative_humidity_2m": "rh", "wind_speed_10m": "wind", "precipitation": "precip",
          "wind_gusts_10m": "gust"}
MAX_PREVIOUS_DAY = 7
VARS = ["t2m", "rh", "wind", "precip", "tmax", "gust", "td"]


def dew_point(t_c: np.ndarray, rh: np.ndarray) -> np.ndarray:
    """Magnus formula (°C)."""
    a, b = 17.27, 237.3
    g = np.log(np.clip(rh, 1, 100) / 100.0) + a * t_c / (b + t_c)
    return b * g / (a - g)


def fetch_previous_runs(points: pd.DataFrame, start: str, end: str, cache_dir: Path, pause_s: float = 30.0) -> pd.DataFrame:
    """Hourly IFS values for previous_day0..7, one request per month for all points (cached per month).

    One month x 23 points x 40 series counts as ~210 calls at Open-Meteo (limit 600 per minute), hence the pause
    and the retry after HTTP 429."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    names = [f"{v}{'' if n == 0 else f'_previous_day{n}'}" for v in HOURLY for n in range(MAX_PREVIOUS_DAY + 1)]
    out = []
    months = pd.date_range(pd.Timestamp(start).replace(day=1), end, freq="MS")
    for m0 in months:
        m1 = min(m0 + pd.offsets.MonthEnd(0), pd.Timestamp(end))
        # one day before: the 24 h sums up to 12 UTC of the first day need the afternoon of the day before
        s = max(m0 - pd.Timedelta(days=1), pd.Timestamp(start) - pd.Timedelta(days=1))
        f = cache_dir / f"ifs_previous_runs_{m0:%Y-%m}.parquet"
        if not f.exists():
            q = {"latitude": ",".join(f"{x:.4f}" for x in points["lat"]), "longitude": ",".join(f"{x:.4f}" for x in points["lon"]),
                 "models": MODEL, "hourly": ",".join(names), "start_date": f"{s:%Y-%m-%d}", "end_date": f"{m1:%Y-%m-%d}",
                 "timezone": "GMT", "wind_speed_unit": "kmh"}
            for attempt in range(6):
                r = requests.get(URL, params=q, timeout=300, headers={"User-Agent": "la-brasa-forecast"})
                if r.status_code != 429:
                    break
                time.sleep(65)
            r.raise_for_status()
            res = r.json()
            res = res if isinstance(res, list) else [res]
            frames = []
            for (lat, lon), loc in zip(zip(points["lat"], points["lon"]), res):
                h = pd.DataFrame(loc["hourly"])
                h["time"] = pd.to_datetime(h["time"])
                h["lat"], h["lon"] = round(lat, 4), round(lon, 4)
                frames.append(h)
            pd.concat(frames, ignore_index=True).to_parquet(f, index=False)
            time.sleep(pause_s)
        out.append(pd.read_parquet(f))
    h = pd.concat(out, ignore_index=True).drop_duplicates(["lat", "lon", "time"])
    return h.sort_values(["lat", "lon", "time"]).reset_index(drop=True)


def daily_by_lead(hourly: pd.DataFrame) -> pd.DataFrame:
    """One row per (point, valid day, lead day 0..7) with the daily variables of features/weather.py."""
    h = hourly.copy()
    # the 24 h window up to 12:00 UTC of day D is (D-1 13:00 .. D 12:00]: shift by 12 h and take the calendar day
    h["day"] = (h["time"] - pd.Timedelta(hours=12) + pd.Timedelta(hours=23)).dt.floor("D")
    noon = h["time"].dt.hour == 12
    rows = []
    for n in range(MAX_PREVIOUS_DAY + 1):
        sfx = "" if n == 0 else f"_previous_day{n}"
        col = {v: f"{k}{sfx}" for k, v in HOURLY.items()}
        g = h.groupby(["lat", "lon", "day"])
        win = pd.DataFrame({"precip": g[col["precip"]].sum(min_count=24), "tmax": g[col["t2m"]].max(),
                            "gust": g[col["gust"]].max(), "n_hours": g[col["t2m"]].count()})
        at = h[noon].set_index(["lat", "lon", "day"])[[col["t2m"], col["rh"], col["wind"]]]
        at.columns = ["t2m", "rh", "wind"]
        d = at.join(win, how="inner")
        d = d[d["n_hours"] == 24].drop(columns="n_hours")
        d["td"] = dew_point(d["t2m"].to_numpy(), d["rh"].to_numpy())
        d["lead_day"] = n
        rows.append(d.reset_index().rename(columns={"day": "date"}))
    out = pd.concat(rows, ignore_index=True)
    return out.dropna(subset=[v for v in VARS if v != "gust"])     # gusts of previous runs are not archived


def error_table(ifs_daily: pd.DataFrame, era5_points: pd.DataFrame, points: pd.DataFrame) -> pd.DataFrame:
    """Errors IFS - ERA5 per (point, date, lead day) and variable, with region, month and whether ERA5 had rain.

    Open-Meteo does not archive the gusts of previous runs. Their error at lead day >= 1 is the gust error of lead
    day 0 at the same point and day plus k times the growth of the wind error, with k the slope of gust on wind in
    ERA5 (least squares); k is stored in the column `gust_wind_slope`."""
    e = era5_points[["lat", "lon", "date", *VARS]].rename(columns={v: f"{v}_era5" for v in VARS})
    m = ifs_daily.merge(e, on=["lat", "lon", "date"], how="inner")
    m = m.merge(points[["lat", "lon", "region_id"]], on=["lat", "lon"], how="inner").reset_index(drop=True)
    out = m[["region_id", "lat", "lon", "date", "lead_day"]].copy()
    for v in VARS:
        out[f"e_{v}"] = m[v] - m[f"{v}_era5"]
    out["precip_era5"] = m["precip_era5"]
    out["era5_wet"] = m["precip_era5"] >= 1.0
    out["month"] = m["date"].dt.month
    k = float(np.polyfit(m["wind_era5"], m["gust_era5"], 1)[0])
    b0 = out[out["lead_day"] == 0].set_index(["lat", "lon", "date"])[["e_gust", "e_wind"]]
    b0 = b0.reindex(pd.MultiIndex.from_arrays([out["lat"], out["lon"], out["date"]]))
    miss = out["e_gust"].isna().to_numpy()
    est = b0["e_gust"].to_numpy() + k * (out["e_wind"].to_numpy() - b0["e_wind"].to_numpy())
    out.loc[miss, "e_gust"] = est[miss]
    out["gust_wind_slope"] = k
    return out.dropna(subset=[f"e_{v}" for v in VARS]).reset_index(drop=True)


def error_summary(err: pd.DataFrame) -> pd.DataFrame:
    """Bias and spread of the errors per lead day and variable (pooled over regions and months)."""
    rows = []
    for n, g in err.groupby("lead_day"):
        for v in VARS:
            x = g[f"e_{v}"]
            rows.append({"lead_day": int(n), "var": v, "bias": float(x.mean()), "sd": float(x.std()),
                         "mae": float(x.abs().mean()), "n": int(len(x))})
    return pd.DataFrame(rows)


def bias_table(err: pd.DataFrame) -> pd.DataFrame:
    """Mean error per region, month and lead day (for the bias correction of the live forecast)."""
    cols = [f"e_{v}" for v in VARS]
    return err.groupby(["region_id", "month", "lead_day"])[cols].mean().reset_index()


def growth_factors(err: pd.DataFrame) -> dict[str, float]:
    """Daily growth of the error spread over lead days 4-7 per variable (to extrapolate to lead days 8-9)."""
    out = {}
    for v in VARS:
        sd = err[err["lead_day"].between(4, 7)].groupby("lead_day")[f"e_{v}"].std()
        slope = np.polyfit(sd.index.to_numpy(float), np.log(sd.to_numpy()), 1)[0]
        out[v] = float(np.exp(max(slope, 0.0)))
    return out
