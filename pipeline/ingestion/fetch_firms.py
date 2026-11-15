#!/usr/bin/env python3
"""
fetch_firms.py - bring the FIRMS raw files in data/raw/ up to date (daily).

What it does, per FIRMS product listed in harmonisation/pipeline_config.yaml (`sources`):

1. Archive (SP, final data): asks FIRMS for the days after the last archive day, 5 days per request (API limit),
   until an answer is empty. FIRMS publishes archive data with a delay of about 2-3 months, so most days nothing comes.
   New archive rows are added to the archive CSV, and the NRT rows of those days are removed from the NRT CSV, so
   that archive and NRT never overlap (as in the original downloads).
2. NRT (near real time): from the last day already in the NRT CSV (or the last `--days` days, whichever starts
   earlier; at most 60 days back) up to today, 5 days per request. New rows after the last archive day are added
   to the NRT CSV. So a run that was missed for some days fills the gap.

Rows are converted to the layout of the FIRMS download files (VIIRS: bright_ti4 -> brightness, bright_ti5 ->
bright_t31; satellite N -> SNPP, T/A -> Terra/Aqua). Duplicates (satellite, latitude, longitude, acq_date,
acq_time) are kept once. MODIS and SNPP rows are limited to the 0.25 deg cells that the existing MODIS/SNPP files
already cover, so the common area of the harmonisation (common_area.py) does not change. NOAA-20/21 use the
rectangle of their original download.

Every CSV that changes is first copied to <file>.bak (one generation) and then replaced atomically. Nothing is
deleted from the archive files.

Reads FIRMS_MAP_KEY from the environment or from La-Brasa/.env. The key is part of the URL path and is never
printed or logged.

Usage (from the repository root, with the harmonisation environment, which has PyYAML):
    harmonisation/.venv/bin/python pipeline/ingestion/fetch_firms.py             # archive + NRT
    harmonisation/.venv/bin/python pipeline/ingestion/fetch_firms.py --days 10
    harmonisation/.venv/bin/python pipeline/ingestion/fetch_firms.py --dry-run   # fetch and report, change nothing

Exit code: 0 ok (also when nothing new came), 1 a request failed, 2 no key.

For the app (POST /api/sync, pipeline/sync_data.py) there is a second, smaller mode: update_nrt_files(). It only
appends new NRT rows to the end of the NRT CSVs and leaves the archives and the row order alone, because
harmonisation/run_pipeline.py --incremental counts the rows behind the end of its last run. It raises FetchError.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "harmonisation" / "pipeline_config.yaml"
BASE = "https://firms.modaps.eosdis.nasa.gov"
# west,south,east,north: covers the NOAA-20/21 download rectangle (36.0-44.8 N, -9.5-4.9 E) with a small margin
BBOX = "-10.0,35.8,5.0,44.9"
MAX_DAY_RANGE = 5           # FIRMS area API: "Invalid day range. Expects [1..5]" (checked 15.11.2026)
NRT_BACKFILL_DAYS = 60      # after an outage, missing NRT days are fetched again, at most this far back
CELL_DEG = 0.25
KEY_COLUMNS = ["satellite", "latitude", "longitude", "acq_date", "acq_time"]

# FIRMS API source per config source name (pipeline_config.yaml `sources`)
API_SOURCE = {
    "modis_archive": "MODIS_SP", "modis_nrt": "MODIS_NRT",
    "snpp_archive": "VIIRS_SNPP_SP", "snpp_nrt": "VIIRS_SNPP_NRT",
    "noaa20_archive": "VIIRS_NOAA20_SP", "noaa20_nrt": "VIIRS_NOAA20_NRT",
    "noaa21_archive": "VIIRS_NOAA21_SP", "noaa21_nrt": "VIIRS_NOAA21_NRT",
}
# satellite codes of the API -> values in the download files (pipeline_config.yaml satellites.sensor_of)
SATELLITE = {"N": "SNPP", "SNPP": "SNPP", "NPP": "SNPP", "N20": "N20", "1": "N20", "NOAA-20": "N20",
             "N21": "N21", "2": "N21", "NOAA-21": "N21", "T": "Terra", "Terra": "Terra", "A": "Aqua", "Aqua": "Aqua"}
RENAME = {"bright_ti4": "brightness", "bright_ti5": "bright_t31"}
REFERENCE_SATELLITES = {"Terra", "Aqua", "SNPP"}      # limited to the cells their files already cover


class FirmsError(RuntimeError):
    pass


FetchError = FirmsError      # name used by pipeline/sync_data.py


# --- key and requests --------------------------------------------------------------------------------------------
def load_key() -> str | None:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = REPO / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key or None


def get_csv(key: str, source: str, day_range: int, start: date | None, retries: int = 3) -> str:
    """One area request. Returns the CSV text; raises FirmsError with the key removed from every message."""
    path = f"/api/area/csv/{key}/{source}/{BBOX}/{day_range}" + (f"/{start.isoformat()}" if start else "")
    last = ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(BASE + path, timeout=120) as r:
                body = r.read().decode("utf-8", errors="replace")
            if body.lstrip().lower().startswith("latitude") or not body.strip():
                return body
            last = body[:300].replace(key, "***")          # FIRMS answers errors as plain text with status 200
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}".replace(key, "***")
        except urllib.error.URLError as e:
            last = f"network: {e.reason}".replace(key, "***")
        time.sleep(5 * (attempt + 1))
    raise FirmsError(f"{source} {start or 'latest'}: {last}")


# --- conversion ----------------------------------------------------------------------------------------------------
def to_download_rows(text: str, header: list[str]) -> list[dict]:
    """API CSV -> rows with exactly the columns of the target download file."""
    rows = []
    for raw in csv.DictReader(io.StringIO(text)):
        r = {RENAME.get(k, k): (v or "").strip() for k, v in raw.items() if k}
        sat = SATELLITE.get(r.get("satellite", ""))
        if sat is None:
            raise FirmsError(f"unknown satellite code {r.get('satellite')!r}; extend SATELLITE in fetch_firms.py")
        r["satellite"] = sat
        r["acq_time"] = r.get("acq_time", "").zfill(4)
        rows.append({c: r.get(c, "") for c in header})
    return rows


def row_key(r: dict) -> tuple:
    return (r["satellite"], f"{float(r['latitude']):.5f}", f"{float(r['longitude']):.5f}", r["acq_date"],
            r["acq_time"].zfill(4))


def cell(r: dict) -> tuple[int, int]:
    return (math.floor(float(r["latitude"]) / CELL_DEG), math.floor(float(r["longitude"]) / CELL_DEG))


# --- files ------------------------------------------------------------------------------------------------------------
def read_csv_file(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv_file(path: Path, header: list[str], rows: list[dict]) -> None:
    """Backup, then atomic replace. Rows sorted by date, time, satellite, position (deterministic)."""
    rows = sorted(rows, key=lambda r: (r["acq_date"], r["acq_time"].zfill(4), r["satellite"],
                                       float(r["latitude"]), float(r["longitude"])))
    shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def last_date(rows: list[dict]) -> date | None:
    return max((date.fromisoformat(r["acq_date"]) for r in rows), default=None)


def load_sources() -> list[dict]:
    import yaml           # harmonisation environment

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    out = []
    for s in cfg["sources"]:
        p = Path(s["csv"])
        out.append({**s, "path": (CONFIG.parent / p).resolve() if not p.is_absolute() else p})
    return out


# --- update ---------------------------------------------------------------------------------------------------------
def reference_cells(sources: list[dict]) -> set[tuple[int, int]]:
    """0.25 deg cells with any MODIS or SNPP detection in the existing files (the reference download area)."""
    cells = set()
    for s in sources:
        if s["sensor"] == "MODIS" or s["name"].startswith("snpp"):
            _, rows = read_csv_file(s["path"])
            cells.update(cell(r) for r in rows if r["satellite"] in REFERENCE_SATELLITES)
    return cells


def keep_in_area(rows: list[dict], area: set) -> list[dict]:
    return [r for r in rows if r["satellite"] not in REFERENCE_SATELLITES or cell(r) in area]


def merge(existing: list[dict], new: list[dict]) -> tuple[list[dict], int]:
    seen = {row_key(r) for r in existing}
    added = []
    for r in new:
        k = row_key(r)
        if k not in seen:
            seen.add(k)
            added.append(r)
    return existing + added, len(added)


def update_pair(key: str, archive: dict, nrt: dict, area: set, days: int, today: date, dry_run: bool) -> dict:
    """Archive first (new final days, trim NRT), then the latest NRT days."""
    a_header, a_rows = read_csv_file(archive["path"])
    n_header, n_rows = read_csv_file(nrt["path"])
    rep = {"archive_end_before": str(last_date(a_rows)), "nrt_end_before": str(last_date(n_rows))}
    # 1. archive: chunks of 10 days after the last archive day, until an empty answer. A failure here (e.g. no
    #    archive product yet) does not stop the NRT update.
    new_a, start = [], last_date(a_rows) + timedelta(days=1)
    try:
        while start <= today:
            text = get_csv(key, API_SOURCE[archive["name"]], MAX_DAY_RANGE, start)
            rows = keep_in_area(to_download_rows(text, a_header), area)
            if not rows:
                break
            new_a += rows
            start += timedelta(days=MAX_DAY_RANGE)
    except FirmsError as exc:
        rep["archive_error"] = str(exc).replace(key, "***")[:300]
    a_all, a_added = merge(a_rows, new_a)
    a_end = last_date(a_all)
    # 2. NRT: from the last NRT day (gap after an outage) or the last `days` days, in 5-day chunks; only rows after
    #    the archive end; NRT rows of archive days are dropped
    n_end = last_date(n_rows) or a_end
    start = max(min(today - timedelta(days=days - 1), n_end), today - timedelta(days=NRT_BACKFILL_DAYS))
    new_n = []
    while start <= today:
        span = min(MAX_DAY_RANGE, (today - start).days + 1)
        new_n += to_download_rows(get_csv(key, API_SOURCE[nrt["name"]], span, start), n_header)
        start += timedelta(days=span)
    new_n = [r for r in keep_in_area(new_n, area) if date.fromisoformat(r["acq_date"]) > a_end]
    kept = [r for r in n_rows if date.fromisoformat(r["acq_date"]) > a_end]
    n_all, n_added = merge(kept, new_n)
    rep.update({"archive_added": a_added, "archive_end": str(a_end), "nrt_added": n_added,
                "nrt_removed_now_in_archive": len(n_rows) - len(kept), "nrt_end": str(last_date(n_all))})
    if not dry_run:
        if a_added:
            write_csv_file(archive["path"], a_header, a_all)
        if n_added or len(kept) != len(n_rows):
            write_csv_file(nrt["path"], n_header, n_all)
    return rep


# --- app sync (pipeline/sync_data.py) ---------------------------------------------------------------------------
def append_csv_rows(path: Path, header: list[str], rows: list[dict]) -> None:
    """Backup, then append at the end. The existing rows keep their order (run_pipeline.py --incremental)."""
    shutil.copy2(path, path.with_name(path.name + ".bak"))
    with open(path, "rb+") as f:          # make sure the last existing line ends with a newline
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=header, lineterminator="\n").writerows(rows)


def update_nrt_files(dry_run: bool = False, days: int = 5) -> int:
    """NRT only, append only: fetches the latest NRT days of every product and appends the rows that are new.

    Called by pipeline/sync_data.py before run_pipeline.py --incremental. Archives are not touched and no row is
    moved or removed. Fetches every product first and writes only if all requests worked. Returns the number of
    new rows; raises FetchError (= FirmsError) on any failure, with the key removed from the message.
    """
    key = load_key()
    if not key:
        raise FirmsError("FIRMS_MAP_KEY not found (environment or La-Brasa/.env)")
    try:
        today = datetime.now(timezone.utc).date()
        days = max(1, min(days, NRT_BACKFILL_DAYS))
        sources = load_sources()
        by_name = {s["name"]: s for s in sources}
        area = reference_cells(sources)
        pending = []
        for nrt in (s for s in sources if s["source"] == "nrt"):
            header, rows = read_csv_file(nrt["path"])
            _, archive_rows = read_csv_file(by_name[nrt["name"].replace("_nrt", "_archive")]["path"])
            a_end = last_date(archive_rows) or date.min
            n_end = last_date(rows) or today - timedelta(days=days - 1)
            start = max(min(today - timedelta(days=days - 1), n_end), today - timedelta(days=NRT_BACKFILL_DAYS))
            fetched = []
            while start <= today:
                span = min(MAX_DAY_RANGE, (today - start).days + 1)
                fetched += to_download_rows(get_csv(key, API_SOURCE[nrt["name"]], span, start), header)
                start += timedelta(days=span)
            fetched = [r for r in keep_in_area(fetched, area) if date.fromisoformat(r["acq_date"]) > a_end]
            merged, added = merge(rows, fetched)
            pending.append((nrt, header, merged[len(rows):]))
            print(f"{nrt['name']:<12} {added:>6} new rows -> {nrt['path'].name}")
        total = sum(len(new) for _, _, new in pending)
        if not dry_run:
            for nrt, header, new in pending:
                if new:
                    append_csv_rows(nrt["path"], header, new)
        print("Dry run: nothing was written." if dry_run else f"{total} new rows appended.")
        return total
    except FirmsError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise FirmsError(str(exc).replace(key, "***")[:300]) from exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=5, help="NRT days fetched at least (from today back)")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, do not change the CSVs")
    args = ap.parse_args()
    key = load_key()
    if not key:
        print("FIRMS_MAP_KEY not found (environment or La-Brasa/.env). Free key: "
              "https://firms.modaps.eosdis.nasa.gov/api/map_key/", file=sys.stderr)
        return 2
    days = max(1, min(args.days, NRT_BACKFILL_DAYS))
    today = datetime.now(timezone.utc).date()
    sources = load_sources()
    by_name = {s["name"]: s for s in sources}
    area = reference_cells(sources)
    report, failed = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dry_run": args.dry_run,
                      "products": {}}, False
    for name in sorted({s["name"].rsplit("_", 1)[0] for s in sources}):
        try:
            report["products"][name] = update_pair(key, by_name[f"{name}_archive"], by_name[f"{name}_nrt"], area,
                                                   days, today, args.dry_run)
        except (FirmsError, OSError, ValueError, KeyError) as exc:
            failed = True
            report["products"][name] = {"error": str(exc).replace(key, "***")[:300]}
    print(json.dumps(report, indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
