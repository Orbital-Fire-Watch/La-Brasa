#!/usr/bin/env python3
"""
load_forecast_to_db.py - copy the forecast tables of data/forecast/ into PostgreSQL.

Run after forecast/daily.py (update_daily.py --load-db calls it):
    python pipeline/load_forecast_to_db.py               # load the latest run
    python pipeline/load_forecast_to_db.py --dry-run     # load and roll back: checks files, columns, constraints
    docker compose run --rm pipeline python load_forecast_to_db.py

What it does (docs/forecast_backend_frontend.md, section 4.2):
    - reads data/forecast/status.json; loads nothing if `ok` is not true, so the database keeps the last valid run
    - reads forecast_daily/weekly/skill.parquet and checks that their columns are exactly the database columns
      (db/init/003_forecast.sql), refuses NaN in number columns (empty must be NULL)
    - in ONE transaction: replaces the rows of the same issue_date in forecast_daily and forecast_weekly, drops runs
      older than KEEP_DAYS, replaces forecast_skill completely and overwrites the one row of forecast_status

It computes nothing. Connection and data folder as in load_to_db.py (DATABASE_URL, DATA_DIR).
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
import pyarrow.parquet as pq

from load_to_db import check_columns, check_no_nan, connect, copy_table, database_columns

KEEP_DAYS = 14
RUN_TABLES = ["forecast_daily", "forecast_weekly"]   # one set of rows per issue_date
SKILL_TABLE = "forecast_skill"                       # replaced whole
STATUS_TABLE = "forecast_status"
STATUS_COLUMNS = ["last_run_utc", "ok", "issue_date", "model_version", "weather_used", "weather_provider", "warnings"]


def read_status(forecast_dir: Path) -> dict:
    status = json.loads((forecast_dir / "status.json").read_text(encoding="utf-8"))
    missing = [c for c in STATUS_COLUMNS if c not in status]
    if missing:
        raise SystemExit(f"status.json lacks {missing}")
    return status


def read_tables(forecast_dir: Path) -> dict:
    tables = {}
    for name in [*RUN_TABLES, SKILL_TABLE]:
        table = pq.read_table(forecast_dir / f"{name}.parquet")
        check_no_nan(name, table)
        tables[name] = table
    return tables


def load(conn: psycopg.Connection, tables: dict, status: dict) -> dict[str, int]:
    issue_date = dt.date.fromisoformat(status["issue_date"])
    counts = {}
    with conn.transaction(), conn.cursor() as cur:
        for name, table in tables.items():
            check_columns(name, table, database_columns(cur, name))
        for name in RUN_TABLES:
            dates = {d.isoformat() if hasattr(d, "isoformat") else str(d) for d in tables[name].column("issue_date").to_pylist()}
            if dates != {issue_date.isoformat()}:
                raise SystemExit(f"{name}: issue_date {sorted(dates)} does not match status.json ({issue_date})")
            cur.execute(f"DELETE FROM {name} WHERE issue_date = %s OR issue_date < %s",
                        (issue_date, issue_date - dt.timedelta(days=KEEP_DAYS)))
            counts[name] = copy_table(cur, name, tables[name])
        cur.execute(f"DELETE FROM {SKILL_TABLE}")
        counts[SKILL_TABLE] = copy_table(cur, SKILL_TABLE, tables[SKILL_TABLE])
        cur.execute(
            f"INSERT INTO {STATUS_TABLE} (id, {', '.join(STATUS_COLUMNS)}) VALUES (1, %s, %s, %s, %s, %s, %s, %s) "
            f"ON CONFLICT (id) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in STATUS_COLUMNS),
            [status["last_run_utc"], status["ok"], issue_date, status["model_version"], status["weather_used"],
             status["weather_provider"], json.dumps(status["warnings"])],
        )
        counts[STATUS_TABLE] = 1
    return counts


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", help="default: DATABASE_URL or POSTGRES_* from .env")
    parser.add_argument("--data-dir", type=Path,
                        default=Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data")),
                        help="data folder containing forecast/ (default: DATA_DIR or <repository>/data)")
    parser.add_argument("--dry-run", action="store_true", help="load and roll back")
    return parser.parse_args(argv)


class _Rollback(Exception):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    forecast_dir = args.data_dir / "forecast"
    status = read_status(forecast_dir)
    if status["ok"] is not True:
        print(f"status.json: ok = {status['ok']}; nothing loaded, the database keeps the last valid run", file=sys.stderr)
        return 1
    tables = read_tables(forecast_dir)
    with connect(args.database_url) as conn:
        if args.dry_run:
            try:
                with conn.transaction():
                    counts = load(conn, tables, status)
                    raise _Rollback
            except _Rollback:
                print(f"dry run ok, rolled back: {counts}")
                return 0
        counts = load(conn, tables, status)
    print(f"loaded issue_date {status['issue_date']}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
