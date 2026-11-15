"""Open-Meteo as the second weather source (after the Meteomatics hackathon account ends on 22.11.2026).

- forecast and recent days: ECMWF IFS 0.25° (`https://api.open-meteo.com/v1/forecast`, models=ecmwf_ifs025,
  past_days for the days before today),
- history: ERA5 (`https://archive-api.open-meteo.com/v1/archive`, models=era5), about 5 days behind today,
- ensemble: ECMWF IFS ensemble, 51 members (`https://ensemble-api.open-meteo.com/v1/ensemble`, models=ecmwf_ifs025).

No key. Free for non-commercial use, data licence CC BY 4.0 (attribution "Weather data by Open-Meteo.com").
Only point coordinates are sent.

Output has the same columns as the Meteomatics files (`t_2m:C`, ... and `validdate` at 12:00 UTC), so
features/weather.py reads both alike. Daily values as there: 12:00 UTC for temperature, humidity, wind and dew
point; the 24 h up to 12:00 UTC for precipitation (sum), maximum / minimum temperature and gusts (max).
Only the core group exists here; the Meteomatics indices (Fosberg, forest fire warning, drought) are not used by
the core feature sets.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
HOURLY = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation", "wind_gusts_10m", "dew_point_2m"]
HEADERS = {"User-Agent": "la-brasa-forecast"}
POINTS_PER_REQUEST = 60


def _get(url: str, params: dict, timeout: int = 300) -> list[dict]:
    for _ in range(6):
        r = requests.get(url, params=params, timeout=timeout, headers=HEADERS)
        if r.status_code != 429:
            break
        time.sleep(65)
    r.raise_for_status()
    res = r.json()
    return res if isinstance(res, list) else [res]


def _hourly_frames(url: str, points: list[tuple[float, float]], extra: dict, variables: list[str]) -> pd.DataFrame:
    frames = []
    for i in range(0, len(points), POINTS_PER_REQUEST):
        chunk = points[i:i + POINTS_PER_REQUEST]
        q = {"latitude": ",".join(f"{a:.4f}" for a, _ in chunk), "longitude": ",".join(f"{b:.4f}" for _, b in chunk),
             "hourly": ",".join(variables), "timezone": "GMT", "wind_speed_unit": "kmh", **extra}
        for (lat, lon), loc in zip(chunk, _get(url, q)):
            h = pd.DataFrame(loc["hourly"])
            h["time"] = pd.to_datetime(h["time"])
            h["lat"], h["lon"] = round(lat, 4), round(lon, 4)
            frames.append(h)
        time.sleep(1.0)
    return pd.concat(frames, ignore_index=True)


def daily_noon(h: pd.DataFrame, suffix: str = "") -> pd.DataFrame:
    """Daily values in the Meteomatics layout from hourly values (columns `<var><suffix>`)."""
    h = h.copy()
    h["day"] = (h["time"] + pd.Timedelta(hours=11)).dt.floor("D")       # (D-1 12:00, D 12:00] -> D
    g = h.groupby(["lat", "lon", "day"])
    c = {v: f"{v}{suffix}" for v in HOURLY}
    win = pd.DataFrame({"precip_24h:mm": g[c["precipitation"]].sum(min_count=24),
                        "t_max_2m_24h:C": g[c["temperature_2m"]].max(), "t_min_2m_24h:C": g[c["temperature_2m"]].min(),
                        "wind_gusts_10m_24h:kmh": g[c["wind_gusts_10m"]].max(), "n": g[c["temperature_2m"]].count()})
    at = h[h["time"].dt.hour == 12].set_index(["lat", "lon", "day"])[
        [c["temperature_2m"], c["relative_humidity_2m"], c["wind_speed_10m"], c["dew_point_2m"]]]
    at.columns = ["t_2m:C", "relative_humidity_2m:p", "wind_speed_10m:kmh", "dew_point_2m:C"]
    d = at.join(win, how="inner")
    d = d[d["n"] == 24].drop(columns="n").reset_index()
    d["validdate"] = (d["day"] + pd.Timedelta(hours=12)).dt.tz_localize("UTC")
    cols = ["lat", "lon", "validdate", "t_2m:C", "relative_humidity_2m:p", "wind_speed_10m:kmh", "precip_24h:mm",
            "t_max_2m_24h:C", "t_min_2m_24h:C", "wind_gusts_10m_24h:kmh", "dew_point_2m:C"]
    return d[cols].dropna().sort_values(["lat", "lon", "validdate"]).reset_index(drop=True)


def forecast(points: list[tuple[float, float]], past_days: int, forecast_days: int) -> pd.DataFrame:
    """IFS: the `past_days` days before today and `forecast_days` days from today."""
    h = _hourly_frames(FORECAST_URL, points, {"models": "ecmwf_ifs025", "past_days": past_days,
                                              "forecast_days": forecast_days}, HOURLY)
    return daily_noon(h)


def history(points: list[tuple[float, float]], start: str, end: str) -> pd.DataFrame:
    """ERA5 between start and end (the day before start is fetched too, for the 24 h windows)."""
    s = (pd.Timestamp(start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    h = _hourly_frames(ARCHIVE_URL, points, {"models": "era5", "start_date": s, "end_date": end}, HOURLY)
    d = daily_noon(h)
    return d[d["validdate"].dt.tz_convert(None).dt.normalize() >= pd.Timestamp(start)].reset_index(drop=True)


def ensemble(points: list[tuple[float, float]], forecast_days: int, members: int = 50) -> dict[int, pd.DataFrame]:
    """IFS ensemble: member 0 (control) and members 1..members, daily values per member."""
    # the API returns all members (<var>_memberNN) when the plain variable names are requested
    h = _hourly_frames(ENSEMBLE_URL, points, {"models": "ecmwf_ifs025", "forecast_days": forecast_days,
                                              "past_days": 1}, HOURLY)
    out = {}
    for m in range(members + 1):
        names = [f"{v}_member{m:02d}" if m else v for v in HOURLY]
        if not all(n in h.columns for n in names):
            continue
        sub = h[["time", "lat", "lon", *names]].copy()
        sub.columns = ["time", "lat", "lon", *HOURLY]
        if sub[HOURLY].notna().any().all():
            out[m] = daily_noon(sub)
    return out


def dew_point_check(d: pd.DataFrame) -> float:
    """Share of rows with dew point above temperature (should be ~0)."""
    return float((d["dew_point_2m:C"] > d["t_2m:C"] + 0.5).mean())
