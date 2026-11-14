"""Laden der harmonisierten Tabellen fuer Auswertungen."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def load_table(path: Path | str) -> pd.DataFrame:
    """Liest eine Parquet-Tabelle. Datums- und Zeitspalten kommen als datetime64 zurueck.

    In den Dateien stehen Tage als reines Datum (DATE). Pandas wuerde daraus Python-Objekte machen,
    mit denen sich nicht filtern und rechnen laesst. Alle Funktionen dieses Moduls erwarten
    Tabellen, die so geladen wurden.
    """
    arrow_table = pq.read_table(path)
    table = arrow_table.to_pandas()
    for field in arrow_table.schema:
        if pa.types.is_date(field.type) or pa.types.is_timestamp(field.type):
            table[field.name] = pd.to_datetime(table[field.name]).astype("datetime64[ns]")
    return table
