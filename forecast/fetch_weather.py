"""Fetch Meteomatics weather for the fire-weighted points of each NUTS-2 region.

Run from La-Brasa/forecast:
    .venv/bin/python fetch_weather.py points                     # select points (no API call)
    .venv/bin/python fetch_weather.py check                      # account limits + test each parameter
    .venv/bin/python fetch_weather.py history --start 2012-01-20 --end 2026-11-13 [--group core]
    .venv/bin/python fetch_weather.py forecast [--group core]    # from today, forecast_days ahead

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
from features.points import aggregate_to_regions, select_points

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


def make_client(cfg: dict) -> MeteomaticsClient:
    m = cfg["meteomatics"]
    user, password = credentials(REPO / cfg["paths"]["env_file"])
    return MeteomaticsClient(user, password, cache_dir=REPO / cfg["paths"]["weather_cache_dir"],
                             base_url=m["base_url"], model=m["model"],
                             max_points_per_request=m["max_points_per_request"], chunk_days=m["chunk_days"],
                             timeout_s=m["timeout_s"], max_retries=m["max_retries"],
                             pause_between_requests_s=m["pause_between_requests_s"],
                             parallel_requests=m.get("parallel_requests", 1), progress=True)


def unique_points(points: pd.DataFrame) -> list[tuple[float, float]]:
    return list(dict.fromkeys(zip(points["lat"].round(4), points["lon"].round(4))))


def n_requests(n_points: int, start: date, end: date, max_points: int, chunk_days: int) -> int:
    return -(-n_points // max_points) * len(day_chunks(start, end, chunk_days))


def fetch(cfg: dict, client: MeteomaticsClient, start: date, end: date, groups: list[str],
          kind: str, use_cache: bool) -> int:
    m = cfg["meteomatics"]
    points = load_points(cfg)
    pts = unique_points(points)
    failures = 0
    for group in groups:
        params = m["parameter_groups"][group]
        n = n_requests(len(pts), start, end, client.max_points_per_request, client.chunk_days)
        print(f"[{kind}/{group}] {len(pts)} points, {start}..{end}, {n} requests (cached ones are skipped)")
        try:
            point_df = client.daily_series(start, end, params, pts, valid_hour_utc=m["valid_hour_utc"],
                                           use_cache=use_cache)
        except MeteomaticsAuthError:
            raise
        except MeteomaticsError as exc:
            failures += 1
            print(f"  group {group} failed: {exc}", file=sys.stderr)
            continue
        region_df = aggregate_to_regions(point_df, points, params)
        region_df.insert(2, "date", region_df["validdate"].dt.date)
        suffix = f"{kind}_{group}" if kind == "history" else f"{kind}_{group}_{start.isoformat()}"
        point_df.to_parquet(out_dir(cfg) / f"weather_points_{suffix}.parquet", index=False)
        region_df.to_parquet(out_dir(cfg) / f"weather_region_{suffix}.parquet", index=False)
        print(f"  wrote data/forecast/weather_region_{suffix}.parquet ({len(region_df)} rows)")
    return failures


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
    f = sub.add_parser("forecast")
    f.add_argument("--group", action="append")
    args = parser.parse_args()
    cfg = load_config()

    try:
        if args.cmd == "points":
            pts = make_points(cfg)
            print(f"{len(pts)} points in {pts['region_id'].nunique()} regions -> data/forecast/weather_points.parquet")
            return 0
        if args.cmd == "check":
            return cmd_check(cfg)
        groups = args.group or list(cfg["meteomatics"]["parameter_groups"])
        client = make_client(cfg)
        if args.cmd == "history":
            return 1 if fetch(cfg, client, args.start, args.end, groups, "history", use_cache=True) else 0
        today = datetime.now(timezone.utc).date()
        end = today + timedelta(days=cfg["meteomatics"]["forecast_days"])
        return 1 if fetch(cfg, client, today, end, groups, "forecast", use_cache=False) else 0
    except MeteomaticsAuthError as exc:
        print(f"Authentication problem: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
