"""Stufe 1: FIRMS-CSVs 1:1 in typisierte Parquet-Dateien schreiben (data/raw).

Hier passiert keine fachliche Logik: keine Filter, keine neuen Spalten, keine gedroppten
Spalten. Die Raw-Ebene ist die unveraenderte Quelle, aus der sich alles neu berechnen laesst.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from pipeline.config import path_of
from pipeline.io_utils import file_sha256, get_logger

RAW_COLUMNS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
               "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type"]

TYPED_SELECT = """
SELECT
    TRY_CAST(latitude AS DOUBLE)   AS latitude,
    TRY_CAST(longitude AS DOUBLE)  AS longitude,
    TRY_CAST(brightness AS DOUBLE) AS brightness,
    TRY_CAST(scan AS DOUBLE)       AS scan,
    TRY_CAST(track AS DOUBLE)      AS track,
    TRY_CAST(acq_date AS DATE) AS acq_date,
    lpad(acq_time, 4, '0') AS acq_time,
    satellite, instrument, confidence, version,
    TRY_CAST(bright_t31 AS DOUBLE) AS bright_t31,
    TRY_CAST(frp AS DOUBLE)        AS frp,
    daynight,
    {type_expr}        AS type
FROM read_csv('{csv}', all_varchar = true, header = true)
"""


def raw_parquet_path(config: dict[str, Any], source: dict[str, str]) -> Path:
    """Pfad des Raw-Parquets einer Quelle."""
    return path_of(config, "raw", f"{source['name']}.parquet")


def csv_has_type_column(csv_path: str) -> bool:
    """Prueft, ob die CSV die Spalte `type` hat. Im NRT fehlt sie."""
    with open(csv_path, encoding="utf-8") as handle:
        return "type" in handle.readline().strip().split(",")


def convert_csv_to_raw_parquet(csv_path: str, parquet_path: Path) -> int:
    """Schreibt eine CSV als typisiertes Parquet und gibt die Zeilenzahl zurueck.

    Alle Spalten werden zuerst als Text gelesen und dann gezielt umgewandelt. Das verhindert,
    dass DuckDB Typen raet: `confidence` ist bei MODIS eine Zahl und bei VIIRS ein Buchstabe,
    `acq_time` verliert als Zahl seine fuehrenden Nullen ("0114" wuerde zu 114).
    Fehlt `type` (NRT), wird die Spalte mit NULL angelegt, damit alle Quellen dasselbe Schema haben.
    Laesst sich ein Wert nicht umwandeln (z. B. versehentlich eingefuegter Text in einer Zahl), wird
    er leer statt die Pipeline abzubrechen. Die Zeile wird in der Bereinigung als `invalid_value`
    verworfen und erscheint in der Zeilenbilanz.
    """
    type_expr = "TRY_CAST(type AS INTEGER)" if csv_has_type_column(csv_path) else "NULL::INTEGER"
    query = TYPED_SELECT.format(type_expr=type_expr, csv=csv_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    connection.execute("SET threads = 1")       # feste Zeilenreihenfolge = gleicher Datei-Hash
    connection.execute(f"COPY ({query}) TO '{parquet_path}' (FORMAT parquet, COMPRESSION zstd)")
    return connection.execute(f"SELECT COUNT(*) FROM '{parquet_path}'").fetchone()[0]


def count_unreadable_rows(parquet_path: Path) -> int:
    """Zaehlt Zeilen, in denen ein Pflichtwert nach der Umwandlung leer ist (Hinweis auf eine beschaedigte CSV-Zeile)."""
    required = ["latitude", "longitude", "scan", "track", "acq_date", "acq_time", "satellite", "frp", "daynight"]
    condition = " OR ".join(f"{column} IS NULL" for column in required)
    return duckdb.connect().execute(f"SELECT COUNT(*) FROM '{parquet_path}' WHERE {condition}").fetchone()[0]


def ingest_all_sources(config: dict[str, Any]) -> dict[str, Any]:
    """Wandelt alle konfigurierten CSVs um und berichtet Zeilenzahl und Eingabe-Hash je Quelle."""
    logger = get_logger()
    report = {}
    for source in config["sources"]:
        target = raw_parquet_path(config, source)
        rows = convert_csv_to_raw_parquet(source["csv"], target)
        unreadable = count_unreadable_rows(target)
        report[source["name"]] = {"rows": rows, "csv_sha256": file_sha256(Path(source["csv"])),
                                  "csv": Path(source["csv"]).name, "unreadable_rows": unreadable}
        logger.info("ingest   %-14s %8d Zeilen -> %s", source["name"], rows, target.name)
        if unreadable:
            logger.warning("ingest   %-14s %d Zeile(n) mit unlesbaren Werten in der CSV, sie werden verworfen", source["name"], unreadable)
    return report
