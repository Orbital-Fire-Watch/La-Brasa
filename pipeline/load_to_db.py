#!/usr/bin/env python3
"""
load_to_db.py - copy the harmonised Parquet tables into PostgreSQL.

Run after harmonisation/run_pipeline.py:
    python pipeline/load_to_db.py                # replace all tables
    python pipeline/load_to_db.py --dry-run      # load and roll back: checks files, columns, constraints
    python pipeline/load_to_db.py --incremental  # only the days from harmonised/incremental.json on (sync of the app)
    docker compose run --rm pipeline python load_to_db.py

What it does:
    - checks that data/harmonised/manifest.json has the schema version this loader and
      db/init/001_schema.sql were written for (SCHEMA_VERSION)
    - reads data/harmonised/<table>.parquet for every table in TABLES
    - checks that the Parquet columns are exactly the database columns (db/init/001_schema.sql)
    - refuses NaN in number columns: an empty value must be NULL, never NaN
    - fills `regions` with the distinct regions of activity_daily_harmonised
    - replaces ALL tables in ONE transaction, so the database always holds one complete
      harmonisation run, never a half-loaded table or a mix of two runs

It does not clean or compute anything. That happens only in harmonisation/.

Data folder: DATA_DIR (default: <repository>/data).
Connection: --database-url, DATABASE_URL, otherwise POSTGRES_USER, POSTGRES_PASSWORD and
POSTGRES_DB from the environment or .env, with host localhost and port 5432.

Install: pip install -r pipeline/requirements.txt
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from psycopg import sql

# Every harmonised table that the product uses. Order = load order (after regions).
TABLES = [
    "activity_daily_harmonised",
    "hotspots_harmonised",
    "day_status",
    "quality_by_scale",
    "calib_factors",
    "strength_confusion",
    "big_fire_day_quality",
]
REGIONS_TABLE = "regions"
REGIONS_SOURCE = "activity_daily_harmonised"
REGION_COLUMNS = ["region_id", "region_name", "country"]
BATCH_ROWS = 50_000
# --incremental: run_pipeline.py --incremental names the first recomputed day here; deleted once loaded.
PENDING_LOAD = "incremental.json"
# Tables replaced from that day on (table -> date column); day_status is small and replaced whole.
INCREMENTAL_TABLES = {"hotspots_harmonised": "obs_date", "activity_daily_harmonised": "date"}
# Schema version of the harmonised tables that db/init/001_schema.sql describes.
# 2 = VIIRS reference n_viirs / frp_viirs from SNPP, NOAA-20 and NOAA-21 (harmonisation/docs/viirs_extension.md).
SCHEMA_VERSION = 2
RECREATE_HINT = "An existing database keeps its old tables: recreate it with docker compose down -v && docker compose up -d db."


class LoadError(Exception):
    """A file or table does not match the contract between harmonisation and database."""


# --------------------------------------------------------------------------- Connection
def read_env(path: str = ".env") -> dict[str, str]:
    values = {}
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def connect(cli_url: str | None) -> psycopg.Connection:
    # autocommit: transactions are opened explicitly with conn.transaction()
    url = cli_url or os.environ.get("DATABASE_URL")
    if url:
        return psycopg.connect(url, autocommit=True)
    env = read_env()

    def get(name: str) -> str | None:
        return os.environ.get(name) or env.get(name)

    user, password, dbname = get("POSTGRES_USER"), get("POSTGRES_PASSWORD"), get("POSTGRES_DB")
    if not (user and password and dbname):
        raise LoadError("No database settings found. Set DATABASE_URL or POSTGRES_* in .env.")
    return psycopg.connect(
        host="localhost", port=5432, user=user, password=password, dbname=dbname, autocommit=True
    )


# --------------------------------------------------------------------------- Files
def check_schema_version(harmonised_dir: Path) -> None:
    """The harmonised files must have the schema version this loader was written for."""
    manifest = harmonised_dir / "manifest.json"
    if not manifest.exists():
        raise LoadError(f"{manifest} not found. Run harmonisation/run_pipeline.py first.")
    version = json.loads(manifest.read_text(encoding="utf-8")).get("schema_version")
    if version != SCHEMA_VERSION:
        raise LoadError(
            f"Harmonised data has schema version {version}, the loader and db/init/001_schema.sql expect {SCHEMA_VERSION}. "
            "Run the current harmonisation/run_pipeline.py, or update the schema and SCHEMA_VERSION together."
        )


def read_tables(harmonised_dir: Path) -> dict[str, pa.Table]:
    """Read all harmonised tables and check them for NaN."""
    tables = {}
    for name in TABLES:
        path = harmonised_dir / f"{name}.parquet"
        if not path.exists():
            raise LoadError(f"{path} not found. Run harmonisation/run_pipeline.py first.")
        table = pq.read_table(path)
        check_no_nan(name, table)
        tables[name] = table
    return tables


def check_no_nan(name: str, table: pa.Table) -> None:
    for column in table.column_names:
        values = table[column]
        if pa.types.is_floating(values.type) and pc.any(pc.is_nan(values)).as_py():
            raise LoadError(f"{name}.{column} contains NaN. Empty values must be stored as null.")


def regions_from(daily: pa.Table) -> pa.Table:
    """Distinct regions of the daily table, one row per region_id."""
    regions = daily.select(REGION_COLUMNS).group_by(REGION_COLUMNS).aggregate([])
    if len(pc.unique(regions["region_id"])) != regions.num_rows:
        raise LoadError(f"{REGIONS_SOURCE}: a region_id has more than one name or country.")
    return regions.sort_by("region_id")


# --------------------------------------------------------------------------- Database
def database_columns(cur: psycopg.Cursor, table: str) -> list[str]:
    rows = cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    if not rows:
        raise LoadError(f"Table {table} does not exist. Was db/init/001_schema.sql applied?")
    return [row[0] for row in rows]


def check_columns(name: str, table: pa.Table, db_columns: list[str]) -> None:
    missing = sorted(set(db_columns) - set(table.column_names))
    extra = sorted(set(table.column_names) - set(db_columns))
    if missing or extra:
        raise LoadError(
            f"{name}: columns differ between Parquet and database. "
            f"Missing in Parquet: {missing}. Missing in database: {extra}. "
            "Update db/init/001_schema.sql to match harmonisation/docs/data_dictionary.md. " + RECREATE_HINT
        )


def copy_table(cur: psycopg.Cursor, name: str, table: pa.Table) -> int:
    """COPY all rows. Nulls stay NULL, so "no value" and 0 remain different."""
    columns = sql.SQL(", ").join(map(sql.Identifier, table.column_names))
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(name), columns)
    with cur.copy(statement) as copy:
        for batch in table.to_batches(BATCH_ROWS):
            for row in zip(*(column.to_pylist() for column in batch.columns), strict=True):
                copy.write_row(row)
    return table.num_rows


def load_all(conn: psycopg.Connection, tables: dict[str, pa.Table]) -> dict[str, int]:
    """Replace every table in one transaction. Returns the number of rows per table."""
    ordered = {REGIONS_TABLE: regions_from(tables[REGIONS_SOURCE]), **tables}
    with conn.transaction(), conn.cursor() as cur:
        # Timestamps in the Parquet files are UTC without an offset.
        cur.execute("SET LOCAL TIME ZONE 'UTC'")
        for name, table in ordered.items():
            check_columns(name, table, database_columns(cur, name))
        cur.execute(sql.SQL("TRUNCATE {}").format(sql.SQL(", ").join(map(sql.Identifier, ordered))))
        return {name: copy_table(cur, name, table) for name, table in ordered.items()}


def load_since(conn: psycopg.Connection, harmonised_dir: Path, since: dt.date) -> dict[str, int]:
    """Replace the rows from `since` on (and day_status whole) in one transaction. The other tables stay."""
    tables = {name: pq.read_table(harmonised_dir / f"{name}.parquet") for name in [*INCREMENTAL_TABLES, "day_status"]}
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SET LOCAL TIME ZONE 'UTC'")
        counts = {}
        for name, table in tables.items():
            check_no_nan(name, table)
            check_columns(name, table, database_columns(cur, name))
            if name in INCREMENTAL_TABLES:
                column = INCREMENTAL_TABLES[name]
                table = table.filter(pc.greater_equal(table[column], pa.scalar(since, pa.date32())))
                cur.execute(sql.SQL("DELETE FROM {} WHERE {} >= %s").format(sql.Identifier(name), sql.Identifier(column)), (since,))
            else:
                cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(name)))
            counts[name] = copy_table(cur, name, table)
        return counts


def analyze(conn: psycopg.Connection, names: Sequence[str]) -> None:
    """Refresh the planner statistics after a full reload."""
    conn.execute(sql.SQL("ANALYZE {}").format(sql.SQL(", ").join(map(sql.Identifier, names))))


# --------------------------------------------------------------------------- Entry point
def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy the harmonised Parquet tables into PostgreSQL")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data")),
        help="data folder containing harmonised/ (default: DATA_DIR or <repository>/data)",
    )
    parser.add_argument("--database-url")
    parser.add_argument("--dry-run", action="store_true", help="load everything, then roll back")
    parser.add_argument("--incremental", action="store_true", help=f"only the days from harmonised/{PENDING_LOAD} on")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.incremental:
        return main_incremental(args)
    try:
        check_schema_version(args.data_dir / "harmonised")
        tables = read_tables(args.data_dir / "harmonised")
        with connect(args.database_url) as conn:
            if args.dry_run:
                with conn.transaction(force_rollback=True):
                    counts = load_all(conn, tables)
            else:
                counts = load_all(conn, tables)
                analyze(conn, list(counts))
    except (LoadError, psycopg.Error) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    for name, rows in counts.items():
        print(f"{name:<28} {rows:>9} rows")
    print("Dry run: nothing was written." if args.dry_run else "All tables replaced.")
    return 0


def main_incremental(args: argparse.Namespace) -> int:
    harmonised_dir = args.data_dir / "harmonised"
    pending = harmonised_dir / PENDING_LOAD
    if not pending.exists():
        print("Nothing new to load.")
        return 0
    since = dt.date.fromisoformat(json.loads(pending.read_text(encoding="utf-8"))["since"])
    try:
        check_schema_version(harmonised_dir)
        with connect(args.database_url) as conn:
            counts = load_since(conn, harmonised_dir, since)
            analyze(conn, list(counts))
    except (LoadError, psycopg.Error) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    pending.unlink()
    for name, rows in counts.items():
        print(f"{name:<28} {rows:>9} rows")
    print(f"Rows from {since} on replaced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
