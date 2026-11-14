#!/usr/bin/env python3
"""
load_to_db.py - load CSV files into PostgreSQL (regions and raw hotspot tables).

Run in this order:
    # 1) Regions, once, before the hotspots (foreign key)
    python pipeline/ingestion/load_to_db.py regions --boundaries data/raw/NUTS_RG_01M_2021_4326.geojson

    # 2) Hotspots from tag_regions.py (one file or a folder)
    python pipeline/ingestion/load_to_db.py hotspots --table modis data/processed --pattern "modis*_tagged.csv"
    python pipeline/ingestion/load_to_db.py hotspots --table viirs data/processed/viirs_2019_tagged.csv

Options:
    --dry-run      validate and clean only, do not write to the database
    --no-refresh   do not refresh the monthly_comparison view at the end

What it does:
    - pads acq_time to four digits ('917' -> '0917')
    - counts and skips invalid rows (coordinates, date, time, satellite)
    - upserts: a final record replaces a provisional (NRT) one, never the reverse
    - refreshes the monthly_comparison view

Connection: DATABASE_URL, otherwise POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB
from the environment or .env, with host localhost and port 5432.

Install: pip install "psycopg[binary]" pandas
"""
import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pandas as pd

DEFAULT_EXCLUDE = ["ES70", "PT20", "PT30", "ES63", "ES64"]  # Canary Islands, Azores, Madeira, Ceuta, Melilla
KEY = ["satellite", "acq_date", "acq_time", "latitude", "longitude"]
TIME_PATTERN = r"^([01][0-9]|2[0-3])[0-5][0-9]$"

TABLES = {
    "modis": {"table": "modis_hotspots", "bright": "brightness", "instrument": "MODIS", "conf_type": "smallint"},
    "viirs": {"table": "viirs_hotspots", "bright": "bright_ti4", "instrument": "VIIRS", "conf_type": "char(1)"},
}


# --------------------------------------------------------------------------- Connection
def read_env(path=".env"):
    values = {}
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def connect(cli_url):
    import psycopg  # imported here so --dry-run works without psycopg

    # autocommit: each file runs in its own transaction (conn.transaction()).
    # Without autocommit, data would never be committed with --no-refresh.
    url = cli_url or os.environ.get("DATABASE_URL")
    if url:
        return psycopg.connect(url, autocommit=True)
    env = read_env()

    def get(name):
        return os.environ.get(name) or env.get(name)

    user, password, dbname = get("POSTGRES_USER"), get("POSTGRES_PASSWORD"), get("POSTGRES_DB")
    if not (user and password and dbname):
        sys.exit("No database settings found. Set DATABASE_URL or POSTGRES_* in .env.")
    return psycopg.connect(
        host="localhost", port=5432, user=user, password=password, dbname=dbname, autocommit=True
    )


# --------------------------------------------------------------------------- Cleaning
def columns_for(cfg):
    return [
        ("latitude", "real"), ("longitude", "real"), ("brightness", "real"),
        ("scan", "real"), ("track", "real"),
        ("acq_date", "date"), ("acq_time", "char(4)"),
        ("satellite", "text"), ("instrument", "text"),
        ("confidence", cfg["conf_type"]), ("version", "text"), ("frp", "real"),
        ("daynight", "char(1)"), ("country", "char(2)"), ("region_id", "text"),
    ]


def clean(df, cfg):
    """Return the cleaned rows (all database columns) and the number of dropped rows."""
    for col in ("latitude", "longitude", "acq_date", "acq_time", "satellite", cfg["bright"]):
        if col not in df.columns:
            sys.exit(f"Column '{col}' is missing in the CSV.")

    def text(col):
        if col in df.columns:
            return df[col].astype(str).str.strip()
        return pd.Series("", index=df.index)

    def num(col):
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce")
        return pd.Series(float("nan"), index=df.index)

    lat, lon = num("latitude"), num("longitude")
    date = pd.to_datetime(text("acq_date"), format="%Y-%m-%d", errors="coerce")
    time = text("acq_time").str.zfill(4)  # the API returns '917' instead of '0917'
    satellite = text("satellite")

    valid = (
        lat.between(-90, 90) & lon.between(-180, 180)
        & date.notna() & time.str.match(TIME_PATTERN) & (satellite != "")
    )

    conf_raw = text("confidence")
    if cfg["conf_type"] == "smallint":
        c = num("confidence")
        confidence = c.where(c.between(0, 100)).round().astype("Int64")
    else:
        low = conf_raw.str.lower()
        confidence = low.where(low.isin(["l", "n", "h"]), "")

    instrument = text("instrument")
    instrument = instrument.where(instrument != "", cfg["instrument"])
    daynight = text("daynight").str.upper()
    daynight = daynight.where(daynight.isin(["D", "N"]), "")

    out = pd.DataFrame({
        "latitude": lat, "longitude": lon,
        "brightness": num(cfg["bright"]),
        "scan": num("scan"), "track": num("track"),
        "acq_date": date.dt.strftime("%Y-%m-%d"), "acq_time": time,
        "satellite": satellite, "instrument": instrument,
        "confidence": confidence, "version": text("version"), "frp": num("frp"),
        "daynight": daynight, "country": text("country").str.upper(), "region_id": text("region_id"),
    })
    return out[valid], int((~valid).sum())


# --------------------------------------------------------------------------- SQL
def build_sql(cfg, cols):
    names = [n for n, _ in cols]
    table = cfg["table"]
    staging_cols = ", ".join(f"{n} text" for n in names)
    casts = ", ".join(f"NULLIF({n}, '')::{t} AS {n}" for n, t in cols)
    updates = ", ".join(f"{n} = EXCLUDED.{n}" for n in names if n not in KEY)
    key = ", ".join(KEY)
    create_stg = f"CREATE TEMP TABLE stg (row_id bigserial, {staging_cols}) ON COMMIT DROP"
    upsert = f"""
        INSERT INTO {table} AS t ({", ".join(names)})
        SELECT DISTINCT ON ({key}) {", ".join(names)}
        FROM (SELECT row_id, {casts} FROM stg) s
        ORDER BY {key}, row_id DESC
        ON CONFLICT ({key}) DO UPDATE SET {updates}, ingested_at = now()
        WHERE t.provisional OR COALESCE(right(EXCLUDED.version, 3), '') <> 'NRT'
    """
    copy = f"COPY stg ({', '.join(names)}) FROM STDIN WITH (FORMAT csv)"
    return create_stg, copy, upsert


# --------------------------------------------------------------------------- Hotspots
def find_files(path, pattern):
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob(pattern))
    elif path.exists():
        files = [path]
    else:
        sys.exit(f"Path not found: {path}")
    if not files:
        sys.exit("No matching CSV files found.")
    return files


def load_file(path, cfg, cols, conn, known_regions, sqls, chunk_size, dry_run):
    names = [n for n, _ in cols]
    create_stg, copy_sql, upsert_sql = sqls
    stats = {"read": 0, "dropped": 0, "loaded": 0}
    tx = conn.transaction() if conn is not None else contextlib.nullcontext()
    with tx:
        cur = conn.cursor() if conn is not None else None
        if cur is not None:
            cur.execute(create_stg)
        reader = pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=chunk_size)
        for chunk in reader:
            stats["read"] += len(chunk)
            out, dropped = clean(chunk, cfg)
            stats["dropped"] += dropped
            if out.empty:
                continue
            if dry_run:
                if stats["loaded"] == 0:
                    print("   Sample after cleaning:")
                    print("   " + out.head(3).to_csv(index=False).replace("\n", "\n   "))
                stats["loaded"] += len(out)
                continue
            if known_regions is not None:
                unknown = set(out.loc[out["region_id"] != "", "region_id"]) - known_regions
                if unknown:
                    sys.exit(
                        f"Unknown region_id in {path.name}: {sorted(unknown)[:5]}\n"
                        "Load the regions first: load_to_db.py regions --boundaries ..."
                    )
            buf = io.StringIO()
            out[names].to_csv(buf, index=False, header=False)
            with cur.copy(copy_sql) as copy:
                copy.write(buf.getvalue())
            cur.execute(upsert_sql)
            stats["loaded"] += cur.rowcount
            cur.execute("TRUNCATE stg")
    return stats


def cmd_hotspots(args):
    cfg = TABLES[args.table]
    cols = columns_for(cfg)
    sqls = build_sql(cfg, cols)
    files = find_files(args.input, args.pattern)

    conn, known = None, None
    if not args.dry_run:
        conn = connect(args.database_url)
        known = {r[0] for r in conn.execute("SELECT region_id FROM regions").fetchall()}
        if not known:
            sys.exit("The regions table is empty. Run first: load_to_db.py regions --boundaries ...")

    total = {"read": 0, "dropped": 0, "loaded": 0}
    for path in files:
        stats = load_file(path, cfg, cols, conn, known, sqls, args.chunk_size, args.dry_run)
        verb = "would load" if args.dry_run else "written"
        print(f"{path.name}: {stats['read']} read, {stats['dropped']} invalid, {stats['loaded']} {verb}")
        for k in total:
            total[k] += stats[k]
    if len(files) > 1:
        print(f"Total: {total['read']} read, {total['dropped']} invalid, {total['loaded']} processed")

    if conn is not None:
        if not args.no_refresh:
            try:
                conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_comparison")
                print("View monthly_comparison refreshed.")
            except Exception as exc:  # view is missing or was never populated
                print(f"Note: view not refreshed ({exc.__class__.__name__}). The data is saved.")
        conn.close()


# --------------------------------------------------------------------------- Regions
def cmd_regions(args):
    data = json.loads(Path(args.boundaries).read_text(encoding="utf-8"))
    rows = {}
    for feature in data["features"]:
        p = feature["properties"]
        rid = str(p.get(args.id_col, "")).strip()
        country = str(p.get(args.country_col, "")).strip().upper()
        if not rid or country not in args.countries:
            continue
        if args.level_col in p and int(p[args.level_col]) != args.level:
            continue
        if args.exclude and rid.startswith(tuple(args.exclude)):
            continue
        rows[rid] = (rid, str(p.get(args.name_col, rid)).strip(), country)
    if not rows:
        sys.exit("No regions found. Check column names, level and countries.")
    print(f"{len(rows)} regions found ({', '.join(sorted({r[2] for r in rows.values()}))}).")
    if args.dry_run:
        for r in list(rows.values())[:5]:
            print("  ", r)
        return
    conn = connect(args.database_url)
    with conn.transaction():
        conn.cursor().executemany(
            "INSERT INTO regions (region_id, name, country) VALUES (%s, %s, %s) "
            "ON CONFLICT (region_id) DO UPDATE SET name = EXCLUDED.name, country = EXCLUDED.country",
            list(rows.values()),
        )
    conn.close()
    print("Regions loaded.")


# --------------------------------------------------------------------------- Entry point
def main():
    parser = argparse.ArgumentParser(description="Load CSV files into PostgreSQL")
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("regions", help="Load regions from a NUTS GeoJSON file")
    reg.add_argument("--boundaries", required=True, help="NUTS GeoJSON file")
    reg.add_argument("--id-col", default="NUTS_ID")
    reg.add_argument("--name-col", default="NUTS_NAME")
    reg.add_argument("--country-col", default="CNTR_CODE")
    reg.add_argument("--level-col", default="LEVL_CODE")
    reg.add_argument("--level", type=int, default=2)
    reg.add_argument("--countries", nargs="*", default=["ES", "PT"])
    reg.add_argument("--exclude", nargs="*", default=DEFAULT_EXCLUDE)
    reg.add_argument("--database-url")
    reg.add_argument("--dry-run", action="store_true")
    reg.set_defaults(func=cmd_regions)

    hot = sub.add_parser("hotspots", help="Load hotspot CSVs into modis_hotspots or viirs_hotspots")
    hot.add_argument("input", help="CSV file or folder")
    hot.add_argument("--table", choices=sorted(TABLES), required=True)
    hot.add_argument("--pattern", default="*_tagged.csv")
    hot.add_argument("--chunk-size", type=int, default=200_000)
    hot.add_argument("--database-url")
    hot.add_argument("--dry-run", action="store_true")
    hot.add_argument("--no-refresh", action="store_true")
    hot.set_defaults(func=cmd_hotspots)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()