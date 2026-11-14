"""Export der harmonisierten Tabellen als CSV fuer das Frontend (data/harmonised/csv)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from pipeline.column_catalogue import TABLES
from pipeline.config import path_of
from pipeline.io_utils import get_logger

import pyarrow as pa

COPY_SQL = """COPY (SELECT {columns} FROM '{source}') TO '{target}' (FORMAT csv, HEADER true, DELIMITER ',', DATEFORMAT '%Y-%m-%d')"""
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"


def select_list(source: Path) -> str:
    """Spaltenliste fuer den Export. Zeitstempel werden ausdruecklich als ISO-Text formatiert (2025-08-01T13:20:00)."""
    parts = []
    for field in pq.read_schema(source):
        name = f'"{field.name}"'
        is_timestamp = pa.types.is_timestamp(field.type)
        parts.append(f"strftime({name}::TIMESTAMP, '{TIMESTAMP_FORMAT}') AS {name}" if is_timestamp else name)
    return ", ".join(parts)


def csv_directory(config: dict[str, Any]) -> Path:
    """Zielordner der CSV-Dateien (Standard: data/harmonised/csv)."""
    return path_of(config, "harmonised", config["export"]["csv_dir"])


def export_table_to_csv(source: Path, target: Path) -> int:
    """Schreibt eine Parquet-Tabelle als CSV und gibt die Zahl der Datenzeilen zurueck.

    Format, damit das Frontend die Dateien ohne Sonderbehandlung lesen kann: UTF-8, Komma als
    Trennzeichen, Punkt als Dezimalzeichen, Kopfzeile mit den Spaltennamen des Katalogs, Tage als
    ISO-Datum (2025-08-01), Zeitstempel als ISO-Zeit in UTC (2025-08-01T13:20:00), Wahrheitswerte als
    true/false. Leere Felder bedeuten "kein Wert" und sind etwas anderes als 0 (siehe column_guide.html).
    Die Spalten bleiben unveraendert, die Parquet-Datei ist die Quelle.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    duckdb.connect().execute(COPY_SQL.format(columns=select_list(source), source=source, target=target))
    return pq.read_metadata(source).num_rows


def export_tables_to_csv(config: dict[str, Any]) -> dict[str, Any]:
    """Exportiert alle gespeicherten Ausgabetabellen als CSV, sofern `export.csv` in der Konfiguration wahr ist."""
    if not config["export"]["csv"]:
        return {"exported": False}
    report = {}
    for name, table in TABLES.items():
        source = path_of(config, "harmonised", f"{name}.parquet")
        if not table.stored or not source.exists():
            continue
        target = csv_directory(config) / f"{name}.csv"
        rows = export_table_to_csv(source, target)
        report[name] = {"rows": rows, "megabytes": round(target.stat().st_size / 1e6, 1)}
        get_logger().info("csv      %-26s %8d Zeilen, %6.1f MB", name, rows, report[name]["megabytes"])
    return {"exported": True, "tables": report}
