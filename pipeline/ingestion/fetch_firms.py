#!/usr/bin/env python3
"""
fetch_firms.py - append the latest FIRMS NRT hotspots to the raw CSVs of the harmonisation.

Step 1 of pipeline/sync_data.py (POST /api/sync). By hand, from the repository root:
    python pipeline/ingestion/fetch_firms.py              # fetch and append
    python pipeline/ingestion/fetch_firms.py --dry-run    # fetch and report, write nothing

What it does:
    - reads the NRT sources (`source: nrt`) from harmonisation/pipeline_config.yaml, so every
      file path is defined once; the archive files stay manual downloads
    - asks FIRMS which dates each product has (data_availability)
    - requests the area API in chunks of up to DAYS_PER_REQUEST days, starting OVERLAP_DAYS
      before the last date in the file: the last day of an NRT file is usually incomplete
    - converts the API rows to the layout of the FIRMS download files that the harmonisation reads
      (bright_ti4 -> brightness, satellite "N" -> "SNPP", acq_time "114" -> "0114", ...)
    - appends only rows that are not in the file yet (same key as the harmonisation's dedup)
    - writes nothing if any request fails, so a run never updates some products and not others

The harmonisation notices the changed CSVs by their hash and recomputes everything on its next run
(harmonisation/run_pipeline.py, or pipeline/sync_data.py for fetch + harmonise + load).

Reads FIRMS_MAP_KEY from the environment or from .env in the repository root.
The key is part of the API URL path and is never printed. Exit code 0 = ok, 1 = error.
"""
import argparse
import csv
import io
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "harmonisation" / "pipeline_config.yaml"
BASE_URL = "https://firms.modaps.eosdis.nasa.gov"
# west,south,east,north: covers every download in data/raw (the NOAA ones reach 44.8 N, 4.9 E).
# The harmonisation keeps only hotspots inside its study regions (nuts.study_regions), whatever the bbox.
BBOX = "-10.0,35.9,5.0,44.9"
DAYS_PER_REQUEST = 5      # maximum day range of the FIRMS area API
OVERLAP_DAYS = 2          # re-fetch the last days of a file, late overpasses complete them
MAX_LOOKBACK_DAYS = 31    # never fetch further back; an older gap needs a new archive download
TIMEOUT_SECONDS = 90

# Column layout of the FIRMS NRT download files (data/raw/<product>/fire_nrt_*.csv)
NRT_COLUMNS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
               "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight"]
API_RENAMES = {"bright_ti4": "brightness", "bright_ti5": "bright_t31"}
# Same key as `deduplication.key` in pipeline_config.yaml
KEY_COLUMNS = ["satellite", "latitude", "longitude", "acq_date", "acq_time"]
SORT_COLUMNS = ["acq_date", "acq_time", "satellite", "latitude", "longitude"]


@dataclass(frozen=True)
class Product:
    api_source: str
    satellite_names: dict[str, str]   # value in the API -> value in the download files (config `satellites`)


# Config source name -> FIRMS API product. The API abbreviates some satellite names.
PRODUCTS = {
    "modis_nrt": Product("MODIS_NRT", {"T": "Terra", "A": "Aqua", "Terra": "Terra", "Aqua": "Aqua"}),
    "snpp_nrt": Product("VIIRS_SNPP_NRT", {"N": "SNPP", "NPP": "SNPP", "SNPP": "SNPP"}),
    "noaa20_nrt": Product("VIIRS_NOAA20_NRT", {"N20": "N20", "1": "N20"}),
    "noaa21_nrt": Product("VIIRS_NOAA21_NRT", {"N21": "N21", "2": "N21"}),
}


class FetchError(Exception):
    """FIRMS answered with an error, or its data does not fit the download layout."""


@dataclass(frozen=True)
class Target:
    name: str
    csv: Path
    product: Product


@dataclass(frozen=True)
class Update:
    target: Target
    first_date: date
    last_date: date
    fetched_rows: int
    new_rows: list[list[str]]


# --------------------------------------------------------------------------- Configuration
def load_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = REPO_ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise FetchError("FIRMS_MAP_KEY not found. Add it to .env or set it as an environment variable.")
    return key


def load_targets(config_path: Path) -> list[Target]:
    """The NRT CSVs of the harmonisation config, paths resolved like harmonisation/pipeline/config.py does."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    targets = []
    for source in config["sources"]:
        if source["source"] != "nrt":
            continue
        if source["name"] not in PRODUCTS:
            raise FetchError(f"No FIRMS API product known for source {source['name']}. Add it to PRODUCTS.")
        path = Path(source["csv"])
        csv_path = path if path.is_absolute() else (config_path.parent / path).resolve()
        targets.append(Target(source["name"], csv_path, PRODUCTS[source["name"]]))
    return targets


# --------------------------------------------------------------------------- FIRMS API
def get_text(client: httpx.Client, path: str, key: str) -> str:
    """GET a FIRMS path containing {KEY}. Error messages never contain the key."""
    try:
        response = client.get(BASE_URL + path.replace("{KEY}", key))
    except httpx.HTTPError as err:
        raise FetchError(f"Request failed: {type(err).__name__}: {str(err).replace(key, '***')}") from None
    body = response.text.replace(key, "***")
    if response.status_code != 200:
        raise FetchError(f"FIRMS answered {response.status_code}: {body[:300].strip()}")
    return body


def parse_csv(body: str, first_column: str) -> list[dict[str, str]]:
    """Rows of a FIRMS CSV answer. FIRMS reports some errors as plain text with status 200."""
    if not body.strip():
        return []
    if not body.lstrip().lower().startswith(first_column):
        raise FetchError(f"FIRMS did not answer with CSV: {body[:300].strip()}")
    return list(csv.DictReader(io.StringIO(body.lstrip())))


def fetch_availability(client: httpx.Client, key: str) -> dict[str, tuple[date, date]]:
    """First and last date per FIRMS product."""
    rows = parse_csv(get_text(client, "/api/data_availability/csv/{KEY}/ALL", key), "data_id")
    return {row["data_id"]: (date.fromisoformat(row["min_date"]), date.fromisoformat(row["max_date"])) for row in rows}


def fetch_area(client: httpx.Client, key: str, product: Product, first: date, last: date) -> list[dict[str, str]]:
    """All API rows of a product from `first` to `last` (inclusive), in chunks the API allows."""
    rows = []
    start = first
    while start <= last:
        days = min(DAYS_PER_REQUEST, (last - start).days + 1)
        path = f"/api/area/csv/{{KEY}}/{product.api_source}/{BBOX}/{days}/{start.isoformat()}"
        rows += parse_csv(get_text(client, path, key), "latitude")
        start += timedelta(days=days)
    return rows


# --------------------------------------------------------------------------- Files
def read_existing(csv_path: Path) -> tuple[set[tuple[str, ...]], date | None]:
    """Keys and last acq_date of the rows already in an NRT file."""
    if not csv_path.exists():
        return set(), None
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header != NRT_COLUMNS:
            raise FetchError(f"{csv_path} does not have the FIRMS NRT columns {NRT_COLUMNS}, but {header}.")
        index = [NRT_COLUMNS.index(column) for column in KEY_COLUMNS]
        keys = {tuple(row[i] for i in index) for row in reader if row}
    date_index = KEY_COLUMNS.index("acq_date")
    return keys, max((date.fromisoformat(key[date_index]) for key in keys), default=None)


def to_download_row(api_row: dict[str, str], product: Product) -> list[str]:
    """One API row in the column layout and with the values of the FIRMS download files."""
    row = {API_RENAMES.get(column, column): value for column, value in api_row.items()}
    missing = [column for column in NRT_COLUMNS if column not in row]
    if missing:
        raise FetchError(f"{product.api_source}: the API answer lacks the columns {missing}.")
    satellite = product.satellite_names.get(row["satellite"])
    if satellite is None:
        raise FetchError(f"{product.api_source}: unknown satellite value {row['satellite']!r}. Add it to PRODUCTS.")
    row["satellite"] = satellite
    row["acq_time"] = row["acq_time"].zfill(4)
    return [row[column] for column in NRT_COLUMNS]


def new_rows_of(api_rows: list[dict[str, str]], product: Product, existing: set[tuple[str, ...]]) -> list[list[str]]:
    """Converted rows that are not in the file yet, without duplicates among themselves, sorted by time."""
    key_index = [NRT_COLUMNS.index(column) for column in KEY_COLUMNS]
    sort_index = [NRT_COLUMNS.index(column) for column in SORT_COLUMNS]
    seen, rows = set(existing), []
    for api_row in api_rows:
        row = to_download_row(api_row, product)
        key = tuple(row[i] for i in key_index)
        if key not in seen:
            seen.add(key)
            rows.append(row)
    return sorted(rows, key=lambda row: [row[i] for i in sort_index])


def append_rows(csv_path: Path, rows: list[list[str]]) -> None:
    """Append rows by writing a complete copy and replacing the file, so a crash never leaves half a row."""
    old = csv_path.read_text(encoding="utf-8") if csv_path.exists() else ",".join(NRT_COLUMNS) + "\n"
    if not old.endswith("\n"):
        old += "\n"
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = csv_path.with_name(csv_path.name + ".tmp")
    temporary.write_text(old + buffer.getvalue(), encoding="utf-8")
    os.replace(temporary, csv_path)


# --------------------------------------------------------------------------- Update
def plan_window(last_in_file: date | None, available: tuple[date, date] | None, today: date) -> tuple[date, date]:
    """Dates to request: from shortly before the last date in the file up to the newest date FIRMS has."""
    last = min(today, available[1]) if available else today
    earliest = last - timedelta(days=MAX_LOOKBACK_DAYS - 1)
    first = max(last_in_file - timedelta(days=OVERLAP_DAYS), earliest) if last_in_file else earliest
    if available:
        first = max(first, available[0])
    return first, last


def fetch_updates(client: httpx.Client, key: str, targets: list[Target], today: date) -> list[Update]:
    """Fetches every product before anything is written."""
    availability = fetch_availability(client, key)
    updates = []
    for target in targets:
        existing, last_in_file = read_existing(target.csv)
        first, last = plan_window(last_in_file, availability.get(target.product.api_source), today)
        if last_in_file and first > last_in_file + timedelta(days=1):
            print(f"Warning: {target.name} ends on {last_in_file}, the fetch starts on {first}. "
                  "Fill the gap with a new archive download (harmonisation/docs/raw_sources.md).", file=sys.stderr)
        api_rows = fetch_area(client, key, target.product, first, last) if first <= last else []
        updates.append(Update(target, first, last, len(api_rows), new_rows_of(api_rows, target.product, existing)))
    return updates


def update_nrt_files(config_path: Path = DEFAULT_CONFIG, dry_run: bool = False, client: httpx.Client | None = None,
                     today: date | None = None) -> int:
    """Fetches all NRT products, then appends the new rows. Returns the number of new rows."""
    key = load_key()
    targets = load_targets(config_path)
    with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
        updates = fetch_updates(http, key, targets, today or datetime.now(timezone.utc).date())
    for update in updates:
        if update.new_rows and not dry_run:
            append_rows(update.target.csv, update.new_rows)
        print(f"{update.target.name:<12} {update.first_date} to {update.last_date}: "
              f"{update.fetched_rows:>6} rows fetched, {len(update.new_rows):>6} new -> {update.target.csv.name}")
    total = sum(len(update.new_rows) for update in updates)
    print("Dry run: nothing was written." if dry_run else f"{total} new rows appended.")
    return total


# --------------------------------------------------------------------------- Entry point
def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append the latest FIRMS NRT hotspots to data/raw")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="harmonisation config with the NRT sources")
    parser.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        update_nrt_files(args.config, args.dry_run)
    except FetchError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
