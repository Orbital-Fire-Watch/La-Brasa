#!/usr/bin/env python3
"""
fetch_clouds.py - cloud cover at the VIIRS overpass times, per 0.25° cell and day, from Meteomatics.

FIRMS only lists detections: a fire under clouds is missing, and the day looks like "no fire". This file
says per cell and day how cloudy it was when the satellites passed, so the app can show "cloudy" instead.

By hand, from the repository root:
    python pipeline/ingestion/fetch_clouds.py                       # from the last day in the file (or FIRST_DATE) to today
    python pipeline/ingestion/fetch_clouds.py --since 2024-08-01    # (re)fetch from this day on
    python pipeline/ingestion/fetch_clouds.py --dry-run             # fetch and report, write nothing
Also step 1 of pipeline/sync_data.py (POST /api/sync), after fetch_firms.py.

What it does:
    - cells: every 0.25° cell (cell_id as in the hotspots: floor(lat / 0.25)_floor(lon / 0.25)) that touches
      one of the app's regions (backend/assets/nuts2_iberia.geojson)
    - asks Meteomatics for PARAMETER at the cell centres, at NIGHT_PASS_UTC and DAY_PASS_UTC of every day
      (VIIRS passes at about 01:30 and 13:30 local solar time, about 01:45 and 13:45 UTC over Iberia),
      in chunks of DAYS_PER_REQUEST days
    - writes CLOUD_FILE: cell_id, date, cloud_day, cloud_night (share of the sky covered, 0-1, null = no value)
    - re-fetches the last OVERLAP_DAYS days of the file: for the newest days Meteomatics may have given a forecast
    - retries a request up to ATTEMPTS times (timeouts, 429, 5xx) and saves the file every CHECKPOINT_REQUESTS
      requests, so a failed run keeps what it fetched and the next run continues from there

Reads METEOMATICS_USERNAME and METEOMATICS_PASSWORD from the environment or from .env in the repository root.
They are never printed. Exit code 0 = ok, 1 = error.
"""
import argparse
import json
import math
import os
import sys
import time
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from shapely.geometry import box, shape
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO_ROOT / "data"))
CLOUD_FILE = DATA_DIR / "raw" / "clouds" / "cloud_daily.parquet"
REGIONS_GEOJSON = REPO_ROOT / "backend" / "assets" / "nuts2_iberia.geojson"
BASE_URL = "https://api.meteomatics.com"

CELL_DEG = 0.25                         # same grid as cell_id of the hotspots (harmonisation: grid.cell_deg)
PARAMETER = "effective_cloud_cover:p"   # percent; "effective" leaves out thin clouds the fire detection sees through
NIGHT_PASS_UTC = "01:45"                # one request per chunk: night pass, +12 h = day pass, +12 h, ...
DAY_PASS_UTC = "13:45"
DAY_PASS_HOUR_UTC = int(DAY_PASS_UTC[:2])
FIRST_DATE = date(2012, 1, 20)          # first day of VIIRS (SNPP); before it the series is converted MODIS
DAYS_PER_REQUEST = 31
OVERLAP_DAYS = 2
TIMEOUT_SECONDS = 120
ATTEMPTS = 4                            # waits RETRY_WAIT_SECONDS * attempt between them
RETRY_WAIT_SECONDS = 15
CHECKPOINT_REQUESTS = 12                # about one year of days per save
INVALID_VALUES = (-666.0, -777.0, -888.0, -999.0)   # Meteomatics codes for "no value"

SCHEMA = pa.schema([("cell_id", pa.string()), ("date", pa.date32()), ("cloud_day", pa.float64()), ("cloud_night", pa.float64())])

Cell = tuple[int, int]                  # (lat index, lon index)


class FetchError(Exception):
    """Meteomatics answered with an error, or the credentials are missing."""


# --------------------------------------------------------------------------- Configuration
def load_credentials() -> tuple[str, str]:
    names = ("METEOMATICS_USERNAME", "METEOMATICS_PASSWORD")
    values = {name: os.environ.get(name, "").strip() for name in names}
    env = REPO_ROOT / ".env"
    if not all(values.values()) and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() in names and not values[name.strip()]:
                values[name.strip()] = value.strip().strip('"').strip("'")
    missing = [name for name in names if not values[name]]
    if missing:
        raise FetchError(f"{', '.join(missing)} not found. Add it to .env or set it as an environment variable.")
    return values[names[0]], values[names[1]]


def study_cells() -> set[Cell]:
    """Every cell that touches one of the app's regions."""
    features = json.loads(REGIONS_GEOJSON.read_text(encoding="utf-8"))["features"]
    regions = unary_union([shape(f["geometry"]) for f in features])
    west, south, east, north = regions.bounds
    return {
        (i, j)
        for i in range(math.floor(south / CELL_DEG), math.floor(north / CELL_DEG) + 1)
        for j in range(math.floor(west / CELL_DEG), math.floor(east / CELL_DEG) + 1)
        if regions.intersects(box(j * CELL_DEG, i * CELL_DEG, (j + 1) * CELL_DEG, (i + 1) * CELL_DEG))
    }


def cell_id(cell: Cell) -> str:
    return f"{cell[0]}_{cell[1]}"


# --------------------------------------------------------------------------- Meteomatics API
def grid_path(cells: set[Cell]) -> str:
    """Grid of the cell centres that covers all cells: lat_max,lon_min_lat_min,lon_max:step."""
    lat = [(i + 0.5) * CELL_DEG for i, _ in cells]
    lon = [(j + 0.5) * CELL_DEG for _, j in cells]
    return f"{max(lat)},{min(lon)}_{min(lat)},{max(lon)}:{CELL_DEG},{CELL_DEG}"


def request_chunk(client: httpx.Client, auth: tuple[str, str], cells: set[Cell], first: date, last: date) -> dict:
    """PARAMETER at both passes of every day from first to last. Error messages never contain the credentials."""
    times = f"{first}T{NIGHT_PASS_UTC}:00Z--{last}T{DAY_PASS_UTC}:00Z:PT12H"
    url = f"{BASE_URL}/{times}/{PARAMETER}/{grid_path(cells)}/json"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = client.get(url, auth=auth)
        except httpx.HTTPError as err:
            problem = f"Request failed: {type(err).__name__}"
        else:
            if response.status_code == 200:
                return response.json()
            body = response.text
            for secret in auth:
                body = body.replace(secret, "***")
            problem = f"Meteomatics answered {response.status_code}: {body[:300].strip()}"
            if response.status_code != 429 and response.status_code < 500:
                raise FetchError(problem)
        if attempt < ATTEMPTS:
            print(f"{problem} - retry {attempt} of {ATTEMPTS - 1}", flush=True)
            time.sleep(RETRY_WAIT_SECONDS * attempt)
    raise FetchError(problem)


def parse_chunk(body: dict, cells: set[Cell]) -> dict[tuple[str, date], list[float | None]]:
    """(cell_id, date) -> [cloud_day, cloud_night] as share 0-1. Grid points outside the cells are dropped."""
    out: dict[tuple[str, date], list[float | None]] = {}
    for point in body["data"][0]["coordinates"]:
        cell = (round(point["lat"] / CELL_DEG - 0.5), round(point["lon"] / CELL_DEG - 0.5))
        if cell not in cells:
            continue
        for entry in point["dates"]:
            when = datetime.fromisoformat(entry["date"].replace("Z", "+00:00"))
            value = entry["value"]
            share = None if value is None or value in INVALID_VALUES else min(max(value / 100, 0.0), 1.0)
            slot = out.setdefault((cell_id(cell), when.date()), [None, None])
            slot[0 if when.hour == DAY_PASS_HOUR_UTC else 1] = share
    return out


# --------------------------------------------------------------------------- File
def read_existing() -> pa.Table:
    return pq.read_table(CLOUD_FILE).cast(SCHEMA) if CLOUD_FILE.exists() else SCHEMA.empty_table()


def last_full_day(now: datetime) -> date:
    """The newest day whose day pass is over."""
    today = now.astimezone(timezone.utc)
    return today.date() if today.hour > DAY_PASS_HOUR_UTC else today.date() - timedelta(days=1)


def fetch_range(existing: pa.Table, since: date | None, until: date | None) -> tuple[date, date]:
    if since is None:
        last = pc.max(existing["date"]).as_py() if existing.num_rows else None
        since = FIRST_DATE if last is None else last - timedelta(days=OVERLAP_DAYS - 1)
    return since, until or last_full_day(datetime.now(timezone.utc))


def merge(existing: pa.Table, fetched: dict[tuple[str, date], list[float | None]], first: date, last: date) -> pa.Table:
    """Existing rows outside [first, last] plus the fetched rows, sorted by date and cell."""
    keep = existing.filter(pc.or_(pc.less(existing["date"], pa.scalar(first, pa.date32())),
                                  pc.greater(existing["date"], pa.scalar(last, pa.date32()))))
    keys = list(fetched)
    new = pa.table({"cell_id": [k[0] for k in keys], "date": [k[1] for k in keys],
                    "cloud_day": [fetched[k][0] for k in keys], "cloud_night": [fetched[k][1] for k in keys]}, schema=SCHEMA)
    return pa.concat_tables([keep, new]).sort_by([("date", "ascending"), ("cell_id", "ascending")])


def write_atomic(table: pa.Table) -> None:
    CLOUD_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CLOUD_FILE.with_suffix(".tmp")
    pq.write_table(table, tmp)
    tmp.replace(CLOUD_FILE)


# --------------------------------------------------------------------------- Entry point
def update_clouds(since: date | None = None, until: date | None = None, dry_run: bool = False,
                  client: httpx.Client | None = None) -> int:
    """Fetches [since, until] into CLOUD_FILE, saved every CHECKPOINT_REQUESTS requests. Returns the fetched cell-days."""
    auth, cells, existing = load_credentials(), study_cells(), read_existing()
    first, last = fetch_range(existing, since, until)
    if first > last:
        print("Clouds: nothing to fetch.")
        return 0
    fetched: dict[tuple[str, date], list[float | None]] = {}
    total, unsaved_from, requests = 0, first, 0
    with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
        start = first
        while start <= last:
            end = min(start + timedelta(days=DAYS_PER_REQUEST - 1), last)
            fetched.update(parse_chunk(request_chunk(http, auth, cells, start, end), cells))
            requests += 1
            print(f"Clouds {start} to {end}: {len(cells)} cells", flush=True)
            if not dry_run and (requests % CHECKPOINT_REQUESTS == 0 or end == last):
                existing = merge(existing, fetched, unsaved_from, end)
                write_atomic(existing)
                total, fetched, unsaved_from = total + len(fetched), {}, end + timedelta(days=1)
            start = end + timedelta(days=1)
    print("Dry run: nothing was written." if dry_run else f"Clouds: {total} cell-days from {first} to {last} written.")
    return total if not dry_run else len(fetched)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch cloud cover at the VIIRS overpasses from Meteomatics")
    parser.add_argument("--since", type=date.fromisoformat, help="first day to (re)fetch, YYYY-MM-DD")
    parser.add_argument("--until", type=date.fromisoformat, help="last day to fetch, YYYY-MM-DD (default: newest full day)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        update_clouds(args.since, args.until, args.dry_run)
    except FetchError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
