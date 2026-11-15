"""Fetch weather (Meteomatics, or Open-Meteo as second source) for the fire-weighted points of each NUTS-2 region.

Run from La-Brasa/forecast:
    .venv/bin/python fetch_weather.py points                     # select points (no API call)
    .venv/bin/python fetch_weather.py check                      # account limits + test each parameter
    .venv/bin/python fetch_weather.py history --start 2012-01-20 --end 2026-11-08 [--group core]
    .venv/bin/python fetch_weather.py recent --start 2026-11-09 --end 2026-11-13   # after the end of ERA5
    .venv/bin/python fetch_weather.py forecast [--group core]    # from today, forecast_days ahead

    .venv/bin/python fetch_weather.py errors --start 2025-01-01 --end 2025-12-31   # IFS errors per lead (Open-Meteo)

    # second source, no key (after the Meteomatics account ends): core group only
    .venv/bin/python fetch_weather.py forecast --provider open-meteo
    .venv/bin/python fetch_weather.py recent --start 2026-11-20 --end 2026-11-24 --provider open-meteo
    .venv/bin/python fetch_weather.py history --start 2026-11-09 --end 2026-11-20 --provider open-meteo --append
    .venv/bin/python fetch_weather.py ensemble       # ECMWF ensemble (51 members) for the uncertainty band

The source model per use and group is meteomatics.models in config.yaml (history: ERA5 for core).
`errors` uses the Open-Meteo Previous Runs API (no key, CC BY 4.0, non-commercial), see features/forecast_errors.py.

Reads only data/harmonised/. Writes data/forecast/ and caches raw responses in
data/raw/weather/meteomatics/ (re-running reuses the cache, so interrupted downloads resume).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from features.meteomatics import (MeteomaticsAuthError, MeteomaticsClient, MeteomaticsError, credentials,
                                  day_chunks)
from features.points import select_points

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def load_config() -> dict:
    return yaml.safe_load((HERE / "config.yaml").read_text())


def out_dir(cfg: dict) -> Path:
    path = REPO / cfg["paths"]["output_dir"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_points(cfg: dict) -> pd.DataFrame:
    hotspots = pd.read_parquet(REPO / cfg["paths"]["harmonised_dir"] / "hotspots_harmonised.parquet",
                               columns=["cell_id", "region_id", "sensor", "obs_date"])
    p = cfg["points"]
    points = select_points(hotspots, p["training_start"], p["training_end"],
                           p["max_cells_per_region"], p.get("min_share_of_region", 0.0))
    points.to_parquet(out_dir(cfg) / "weather_points.parquet", index=False)
    return points


def load_points(cfg: dict) -> pd.DataFrame:
    path = out_dir(cfg) / "weather_points.parquet"
    return pd.read_parquet(path) if path.exists() else make_points(cfg)


def source_model(cfg: dict, kind: str, group: str) -> str:
    m = cfg["meteomatics"]
    return m.get("models", {}).get(kind, {}).get(group, m["model"])


def make_client(cfg: dict, model: str | None = None) -> MeteomaticsClient:
    m = cfg["meteomatics"]
    user, password = credentials(REPO / cfg["paths"]["env_file"])
    return MeteomaticsClient(user, password, cache_dir=REPO / cfg["paths"]["weather_cache_dir"],
                             base_url=m["base_url"], model=model or m["model"],
                             max_points_per_request=m["max_points_per_request"], chunk_days=m["chunk_days"],
                             timeout_s=m["timeout_s"], max_retries=m["max_retries"],
                             pause_between_requests_s=m["pause_between_requests_s"],
                             parallel_requests=m.get("parallel_requests", 1), progress=True)


def unique_points(points: pd.DataFrame) -> list[tuple[float, float]]:
    return list(dict.fromkeys(zip(points["lat"].round(4), points["lon"].round(4))))


def n_requests(n_points: int, start: date, end: date, max_points: int, chunk_days: int) -> int:
    return -(-n_points // max_points) * len(day_chunks(start, end, chunk_days))


def fetch(cfg: dict, start: date, end: date, groups: list[str], kind: str, use_cache: bool) -> int:
    m = cfg["meteomatics"]
    points = load_points(cfg)
    pts = unique_points(points)
    failures = 0
    for group in groups:
        params = m["parameter_groups"][group]
        model = source_model(cfg, kind, group)
        client = make_client(cfg, model)
        n = n_requests(len(pts), start, end, client.max_points_per_request, client.chunk_days)
        print(f"[{kind}/{group}] model {model}, {len(pts)} points, {start}..{end}, {n} requests (cached ones are skipped)")
        try:
            point_df = client.daily_series(start, end, params, pts, valid_hour_utc=m["valid_hour_utc"],
                                           use_cache=use_cache)
        except MeteomaticsAuthError:
            raise
        except MeteomaticsError as exc:
            failures += 1
            print(f"  group {group} failed: {exc}", file=sys.stderr)
            continue
        suffix = f"{kind}_{group}" if kind in ("history", "recent") else f"{kind}_{group}_{start.isoformat()}"
        write_points(cfg, point_df, suffix, params)
    return failures


def region_table(point_df: pd.DataFrame, points: pd.DataFrame, params: list[str]) -> pd.DataFrame:
    """Fire-weighted mean per region and valid time (vectorised; weights renormalised where values are missing)."""
    key = points[["region_id", "lat", "lon", "weight"]].copy()
    key[["lat", "lon"]] = key[["lat", "lon"]].round(4)
    pw = point_df.copy()
    pw[["lat", "lon"]] = pw[["lat", "lon"]].round(4)
    m = pw.merge(key, on=["lat", "lon"], how="inner")
    parts = {}
    for c in params:
        w = m["weight"].where(m[c].notna(), 0.0)
        parts[c + "__wx"], parts[c + "__w"] = m[c].fillna(0.0) * w, w
    agg = pd.concat([m[["region_id", "validdate"]], pd.DataFrame(parts)], axis=1).groupby(["region_id", "validdate"]).sum()
    out = pd.DataFrame({c: agg[c + "__wx"] / agg[c + "__w"].where(agg[c + "__w"] > 0) for c in params}, index=agg.index)
    out = out.reset_index()
    out.insert(2, "date", out["validdate"].dt.date)
    return out


def write_points(cfg: dict, point_df: pd.DataFrame, suffix: str, params: list[str], append: bool = False) -> None:
    """Write weather_points_<suffix> and weather_region_<suffix>; with append, add days after the existing end."""
    pf, rf = out_dir(cfg) / f"weather_points_{suffix}.parquet", out_dir(cfg) / f"weather_region_{suffix}.parquet"
    if append and pf.exists():
        old = pd.read_parquet(pf)
        point_df = point_df[point_df["validdate"] > old["validdate"].max()]
        point_df = pd.concat([old, point_df[old.columns]], ignore_index=True)
    point_df = point_df.sort_values(["lat", "lon", "validdate"]).reset_index(drop=True)
    region_df = region_table(point_df, load_points(cfg), params)
    point_df.to_parquet(pf, index=False)
    region_df.to_parquet(rf, index=False)
    print(f"  wrote data/forecast/weather_region_{suffix}.parquet ({len(region_df)} rows, "
          f"{region_df['date'].min()}..{region_df['date'].max()})")


def fetch_open_meteo(cfg: dict, kind: str, start: date, end: date, append: bool = False) -> int:
    """Core group from Open-Meteo: forecast / recent (ECMWF IFS) or history (ERA5)."""
    from features import open_meteo as om

    params = cfg["meteomatics"]["parameter_groups"]["core"]
    pts = unique_points(load_points(cfg))
    today = datetime.now(timezone.utc).date()
    print(f"[{kind}/core] open-meteo, {len(pts)} points, {start}..{end}")
    if kind == "history":
        df = om.history(pts, str(start), str(end))
        write_points(cfg, df, "history_core", params, append=append)
        return 0
    past = max((today - start).days, 0)
    df = om.forecast(pts, past_days=past, forecast_days=max((end - today).days + 1, 1))
    day = df["validdate"].dt.tz_convert(None).dt.normalize()
    df = df[(day >= pd.Timestamp(start)) & (day <= pd.Timestamp(end))]
    suffix = "recent_core" if kind == "recent" else f"forecast_core_{start.isoformat()}"
    write_points(cfg, df, suffix, params)
    return 0


def cmd_ensemble(cfg: dict) -> int:
    """ECMWF IFS ensemble (control + 50 members) from Open-Meteo for the strongest point of every region.
    Writes data/forecast/weather_ensemble_<today>.parquet (lat, lon, date, member and the core variables)."""
    from features import open_meteo as om
    from features import weather as wx

    points = load_points(cfg)
    top = points.sort_values(["region_id", "weight"], ascending=[True, False]).groupby("region_id").head(1)
    pts = list(zip(top["lat"].round(4), top["lon"].round(4)))
    today = datetime.now(timezone.utc).date()
    members = om.ensemble(pts, forecast_days=cfg["meteomatics"]["forecast_days"] + 1)
    frames = []
    for m, df in members.items():
        df = df.rename(columns=wx.RENAME)
        df["date"] = pd.to_datetime(df["validdate"].dt.tz_convert("UTC").dt.date)
        frames.append(df.drop(columns=["validdate"]).assign(member=m))
    out = pd.concat(frames, ignore_index=True)
    out = out[out["date"] >= pd.Timestamp(today)]
    path = out_dir(cfg) / f"weather_ensemble_{today.isoformat()}.parquet"
    out.to_parquet(path, index=False)
    print(f"wrote data/forecast/{path.name} ({out['member'].nunique()} members, {len(pts)} points, "
          f"{out['date'].min().date()}..{out['date'].max().date()})")
    return 0


def cmd_errors(cfg: dict, start: date, end: date) -> int:
    """Real IFS forecast errors per lead day against ERA5, one point per region (highest weight)."""
    from features import forecast_errors as fe
    from features import weather as wx

    points = load_points(cfg)
    top = points.sort_values(["region_id", "weight"], ascending=[True, False]).groupby("region_id").head(1)
    hourly = fe.fetch_previous_runs(top, str(start), str(end), REPO / "data" / "raw" / "weather" / "open_meteo")
    ifs = fe.daily_by_lead(hourly)
    era5 = wx._read_points(out_dir(cfg) / "weather_points_history_core.parquet")
    err = fe.error_table(ifs, era5, top.assign(lat=top["lat"].round(4), lon=top["lon"].round(4)))
    err.to_parquet(out_dir(cfg) / "ifs_errors.parquet", index=False)
    print(f"wrote data/forecast/ifs_errors.parquet ({len(err)} rows, {err['region_id'].nunique()} regions, "
          f"{err['date'].min().date()}..{err['date'].max().date()})")
    print(fe.error_summary(err).round(3).to_string(index=False))
    return 0


def cmd_check(cfg: dict) -> int:
    client = make_client(cfg)
    try:
        stats = client.user_stats()
    except MeteomaticsError as exc:
        print(f"user_stats failed: {exc}", file=sys.stderr)
        return 1
    print("Account / limits (user_stats_json):")
    print(stats)
    m = cfg["meteomatics"]
    lat, lon = unique_points(load_points(cfg))[0]
    today = datetime.now(timezone.utc).date()
    tests = {"history 2015-08": date(2015, 8, 1), "forecast today+2": today}
    ok = True
    for group, params in m["parameter_groups"].items():
        for label, d0 in tests.items():
            for param in params:
                try:
                    df = client.daily_series(d0, d0 + timedelta(days=2), [param], [(lat, lon)],
                                             valid_hour_utc=m["valid_hour_utc"], use_cache=False)
                    print(f"  OK   {group:5s} {label:17s} {param:34s} {df[param].round(2).tolist()}")
                except MeteomaticsAuthError as exc:
                    ok = False
                    print(f"  DENY {group:5s} {label:17s} {param:34s} {str(exc)[:160]}")
                except MeteomaticsError as exc:
                    ok = False
                    print(f"  FAIL {group:5s} {label:17s} {param:34s} {str(exc)[:160]}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("points")
    sub.add_parser("check")
    h = sub.add_parser("history")
    h.add_argument("--start", required=True, type=date.fromisoformat)
    h.add_argument("--end", required=True, type=date.fromisoformat)
    h.add_argument("--group", action="append")
    h.add_argument("--provider", choices=["meteomatics", "open-meteo"], default="meteomatics")
    h.add_argument("--append", action="store_true", help="open-meteo: add days after the end of the history file")
    r = sub.add_parser("recent")
    r.add_argument("--start", required=True, type=date.fromisoformat)
    r.add_argument("--end", required=True, type=date.fromisoformat)
    r.add_argument("--group", action="append")
    r.add_argument("--provider", choices=["meteomatics", "open-meteo"], default="meteomatics")
    sub.add_parser("ensemble")
    e = sub.add_parser("errors")
    e.add_argument("--start", required=True, type=date.fromisoformat)
    e.add_argument("--end", required=True, type=date.fromisoformat)
    f = sub.add_parser("forecast")
    f.add_argument("--group", action="append")
    f.add_argument("--provider", choices=["meteomatics", "open-meteo"], default="meteomatics")
    args = parser.parse_args()
    cfg = load_config()

    try:
        if args.cmd == "points":
            pts = make_points(cfg)
            print(f"{len(pts)} points in {pts['region_id'].nunique()} regions -> data/forecast/weather_points.parquet")
            return 0
        if args.cmd == "check":
            return cmd_check(cfg)
        if args.cmd == "errors":
            return cmd_errors(cfg, args.start, args.end)
        if args.cmd == "ensemble":
            return cmd_ensemble(cfg)
        groups = args.group or list(cfg["meteomatics"]["parameter_groups"])
        if getattr(args, "provider", "meteomatics") == "open-meteo":
            today = datetime.now(timezone.utc).date()
            if args.cmd == "forecast":
                return fetch_open_meteo(cfg, "forecast", today, today + timedelta(days=cfg["meteomatics"]["forecast_days"]))
            return fetch_open_meteo(cfg, args.cmd, args.start, args.end, append=getattr(args, "append", False))
        if args.cmd in ("history", "recent"):
            return 1 if fetch(cfg, args.start, args.end, groups, args.cmd, use_cache=args.cmd == "history") else 0
        today = datetime.now(timezone.utc).date()
        end = today + timedelta(days=cfg["meteomatics"]["forecast_days"])
        return 1 if fetch(cfg, today, end, groups, "forecast", use_cache=False) else 0
    except MeteomaticsAuthError as exc:
        print(f"Authentication problem: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
