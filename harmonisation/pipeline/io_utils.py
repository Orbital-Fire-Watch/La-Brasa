"""Hilfsfunktionen fuer Dateien, Hashes und Logging."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

LOGGER_NAME = "harmonisation"


def get_logger() -> logging.Logger:
    """Gibt den gemeinsamen Logger der Pipeline zurueck."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def write_parquet_deterministic(table: pd.DataFrame, path: Path, sort_by: list[str] | None = None,
                                date_columns: tuple[str, ...] = ()) -> None:
    """Schreibt ein Parquet so, dass gleiche Daten immer dieselbe Datei ergeben.

    Dafuer werden die Zeilen fest sortiert, der Index verworfen und keine Pandas-Metadaten
    geschrieben. Ohne das koennten zwei Laeufe dieselben Daten in anderer Reihenfolge ablegen,
    und der Hash-Vergleich (Determinismus-Test) wuerde faelschlich anschlagen.
    `date_columns` werden als reines Datum (DATE) gespeichert statt als Zeitstempel mit 00:00:00.
    """
    if sort_by:
        table = table.sort_values(sort_by, kind="mergesort")
    arrow_table = pa.Table.from_pandas(table.reset_index(drop=True), preserve_index=False)
    for name in date_columns:
        position = arrow_table.schema.get_field_index(name)
        arrow_table = arrow_table.set_column(position, name, pc.cast(arrow_table.column(name), pa.date32(), safe=False))
    arrow_table = arrow_table.replace_schema_metadata(None)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table, path, compression="zstd")


def read_parquet(path: Path) -> pd.DataFrame:
    """Liest ein Parquet als DataFrame. DATE-Spalten kommen als datetime64 zurueck, damit sich damit rechnen laesst."""
    arrow_table = pq.read_table(path)
    table = arrow_table.to_pandas()
    for field in arrow_table.schema:
        if pa.types.is_date(field.type) or pa.types.is_timestamp(field.type):
            table[field.name] = pd.to_datetime(table[field.name]).astype("datetime64[ns]")
    return table


def file_sha256(path: Path) -> str:
    """SHA-256 einer Datei, in Bloecken gelesen."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(obj: Any, path: Path) -> None:
    """Schreibt ein Objekt als JSON mit sortierten Schluesseln."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str), encoding="utf-8")


def read_json(path: Path) -> Any:
    """Liest eine JSON-Datei."""
    return json.loads(path.read_text(encoding="utf-8"))
