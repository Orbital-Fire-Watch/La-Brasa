"""Tests for load_to_db.py.

The database tests need a running PostgreSQL and are skipped otherwise:
    docker compose up -d db
    TEST_DATABASE_URL=postgresql://labrasa:change-me@localhost:5432/labrasa pytest
They create the real schema (db/init/001_schema.sql) in a temporary schema and roll
everything back, so existing data is never touched.
"""
import os
from datetime import date, datetime
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import load_to_db

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "init" / "001_schema.sql"
DATA_DICTIONARY = Path(__file__).resolve().parents[2] / "harmonisation" / "docs" / "data_dictionary.md"
TEST_SCHEMA = "loader_test"

# One value per database type, used to build a valid row for every table
SAMPLE_VALUES = {
    "text": (pa.string(), "x"),
    "double precision": (pa.float64(), 1.5),
    "bigint": (pa.int64(), 1),
    "boolean": (pa.bool_(), True),
    "date": (pa.date32(), date(2020, 1, 1)),
    "timestamp with time zone": (pa.timestamp("ns"), datetime(2020, 1, 1, 13, 20)),
}
OVERRIDES = {
    ("activity_daily_harmonised", "n_aqua"): None,  # no value
    ("activity_daily_harmonised", "n_terra"): 0.0,  # no fire
}


# --------------------------------------------------------------------------- without database
def test_check_no_nan_rejects_nan() -> None:
    table = pa.table({"n_harm": pa.array([1.0, float("nan")])})

    with pytest.raises(load_to_db.LoadError, match="NaN"):
        load_to_db.check_no_nan("activity_daily_harmonised", table)


def test_check_no_nan_accepts_null() -> None:
    load_to_db.check_no_nan("activity_daily_harmonised", pa.table({"n_harm": pa.array([1.0, None])}))


def test_regions_from_rejects_region_with_two_names() -> None:
    daily = pa.table({"region_id": ["ES11", "ES11"], "region_name": ["Galicia", "Galiza"], "country": ["ES", "ES"]})

    with pytest.raises(load_to_db.LoadError, match="more than one name"):
        load_to_db.regions_from(daily)


def test_read_tables_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(load_to_db.LoadError, match="run_pipeline.py"):
        load_to_db.read_tables(tmp_path)


def test_check_schema_version_rejects_old_harmonisation(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"schema_version": 1}', encoding="utf-8")

    with pytest.raises(load_to_db.LoadError, match="schema version 1"):
        load_to_db.check_schema_version(tmp_path)


def test_check_schema_version_accepts_current(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(f'{{"schema_version": {load_to_db.SCHEMA_VERSION}}}', encoding="utf-8")

    load_to_db.check_schema_version(tmp_path)


def sql_columns(table: str) -> list[str]:
    """Column names of one CREATE TABLE statement in db/init/001_schema.sql, in order."""
    body = SCHEMA_SQL.read_text(encoding="utf-8").split(f"CREATE TABLE {table} (")[1].split("\n);")[0]
    lines = [line.split("--")[0].strip() for line in body.splitlines()]
    return [line.split()[0].strip('"') for line in lines if line and not line.startswith("PRIMARY KEY")]


def test_schema_sql_matches_data_dictionary() -> None:
    """Every table has the same columns in the same order as harmonisation/docs/data_dictionary.md."""
    text = DATA_DICTIONARY.read_text(encoding="utf-8")
    for name in load_to_db.TABLES:
        section = text.split(f"## {name}\n")[1].split("\n## ")[0]
        documented = [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")]
        assert sql_columns(name) == documented, name


# --------------------------------------------------------------------------- with database
@pytest.fixture
def conn():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    with psycopg.connect(url, autocommit=True) as connection, connection.transaction(force_rollback=True):
        connection.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
        connection.execute(f"SET LOCAL search_path TO {TEST_SCHEMA}, public")
        connection.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        yield connection


def sample_table(conn: psycopg.Connection, name: str) -> pa.Table:
    """One valid row for `name`, built from the column types in the database."""
    columns = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (TEST_SCHEMA, name),
    ).fetchall()
    arrays, names = [], []
    for column, data_type in columns:
        arrow_type, value = SAMPLE_VALUES[data_type]
        if column == "region_id":
            value = "ES11"
        value = OVERRIDES.get((name, column), value)
        arrays.append(pa.array([value], type=arrow_type))
        names.append(column)
    return pa.table(arrays, names=names)


def sample_tables(conn: psycopg.Connection) -> dict[str, pa.Table]:
    return {name: sample_table(conn, name) for name in load_to_db.TABLES}


def test_load_all_fills_every_table(conn: psycopg.Connection) -> None:
    counts = load_to_db.load_all(conn, sample_tables(conn))

    assert counts == {"regions": 1, **{name: 1 for name in load_to_db.TABLES}}
    assert conn.execute("SELECT region_id FROM regions").fetchall() == [("ES11",)]


def test_load_all_keeps_null_and_zero_apart(conn: psycopg.Connection) -> None:
    load_to_db.load_all(conn, sample_tables(conn))

    row = conn.execute("SELECT n_aqua, n_terra FROM activity_daily_harmonised").fetchone()

    assert row == (None, 0.0)


def test_load_all_stores_timestamps_as_utc(conn: psycopg.Connection) -> None:
    load_to_db.load_all(conn, sample_tables(conn))

    (stored,) = conn.execute("SELECT acq_datetime_utc AT TIME ZONE 'UTC' FROM hotspots_harmonised").fetchone()

    assert stored == datetime(2020, 1, 1, 13, 20)


def test_load_all_replaces_previous_rows(conn: psycopg.Connection) -> None:
    load_to_db.load_all(conn, sample_tables(conn))
    load_to_db.load_all(conn, sample_tables(conn))

    assert conn.execute("SELECT count(*) FROM day_status").fetchone() == (1,)


def test_load_all_rejects_column_mismatch_and_keeps_old_data(conn: psycopg.Connection) -> None:
    load_to_db.load_all(conn, sample_tables(conn))
    tables = sample_tables(conn)
    tables["day_status"] = tables["day_status"].drop_columns(["possible_gap"])

    with pytest.raises(load_to_db.LoadError, match="possible_gap"):
        load_to_db.load_all(conn, tables)

    assert conn.execute("SELECT count(*) FROM hotspots_harmonised").fetchone() == (1,)


def test_read_tables_reads_parquet_files(conn: psycopg.Connection, tmp_path: Path) -> None:
    for name, table in sample_tables(conn).items():
        pq.write_table(table, tmp_path / f"{name}.parquet")

    tables = load_to_db.read_tables(tmp_path)

    assert set(tables) == set(load_to_db.TABLES)
