#!/usr/bin/env python3
"""
test_firms.py - quick check of the FIRMS API for the Iberian Peninsula.

Reads FIRMS_MAP_KEY from the environment or from .env in the current folder.
The key is part of the API URL path and is never printed.

Usage (from the repository root):
    python pipeline/test_firms.py          # 1 day
    python pipeline/test_firms.py 5        # 5 days per request
    python pipeline/test_firms.py 10       # check whether 10 days are allowed

Standard library only.
"""
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://firms.modaps.eosdis.nasa.gov"
BBOX = "-10.0,35.9,3.5,44.0"  # west,south,east,north - rough box, tag_regions.py filters the rest
PAST_DATE = "2024-08-15"      # date for the SP tests (standard processing, archive)

# (source, date or None). NRT = recent data, SP = final archive data
TESTS = [
    ("MODIS_NRT", None),
    ("VIIRS_SNPP_NRT", None),
    ("MODIS_SP", PAST_DATE),
    ("VIIRS_SNPP_SP", PAST_DATE),
]


def load_key():
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = Path(".env")
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FIRMS_MAP_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("FIRMS_MAP_KEY not found. Add it to .env or set it as an environment variable.")
    return key


def get(path, key):
    """Return (status code, text). The key is never printed."""
    url = BASE + path.replace("{KEY}", key)
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            body = r.read().decode("utf-8", errors="replace")
            return r.status, body.replace(key, "***")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body.replace(key, "***")
    except urllib.error.URLError as e:
        return None, str(e.reason).replace(key, "***")


def show_text(label, status, body, max_chars=400):
    print(f"\n== {label}")
    print(f"   Status: {status}")
    print("   " + body[:max_chars].strip().replace("\n", "\n   "))


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    key = load_key()
    print(f"Key found ({len(key)} characters). Area: {BBOX}, days per request: {days}")

    # 0) Key status (used transactions)
    status, body = get("/mapserver/mapkey_status/?MAP_KEY={KEY}", key)
    show_text("Key status", status, body)

    # 1) Available sources and date ranges
    status, body = get("/api/data_availability/csv/{KEY}/ALL", key)
    show_text("Available sources and date ranges (first lines)", status, body, max_chars=1200)

    # 2) Small area requests
    for source, date in TESTS:
        path = f"/api/area/csv/{{KEY}}/{source}/{BBOX}/{days}"
        if date:
            path += f"/{date}"
        status, body = get(path, key)
        label = f"{source}" + (f" from {date}" if date else " (latest data)")
        lines = [l for l in body.splitlines() if l.strip()]
        print(f"\n== {label}")
        print(f"   Status: {status}")
        if lines and lines[0].lower().startswith("latitude"):
            print(f"   OK: {len(lines) - 1} rows")
            print(f"   Columns: {lines[0]}")
            if len(lines) > 1:
                print(f"   First row: {lines[1]}")
        else:
            print("   No CSV response. Message:")
            print("   " + body[:300].strip().replace("\n", "\n   "))


if __name__ == "__main__":
    main()