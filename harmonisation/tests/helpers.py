"""Test-Hilfen: Konfiguration fuer den Test-Ausschnitt und kleine synthetische Raw-Tabellen."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
RAW_DEFAULTS = {"latitude": 40.0, "longitude": -4.0, "brightness": 320.0, "scan": 1.0, "track": 1.0,
                "acq_date": "2015-07-01", "acq_time": "1300", "satellite": "Aqua", "instrument": "MODIS",
                "confidence": "50", "version": "6.03", "bright_t31": 295.0, "frp": 12.0, "daynight": "D",
                "type": 0, "source": "archive"}


def make_fixture_config(base: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    """Konfiguration, die auf den Test-Ausschnitt liest und in ein temporaeres Verzeichnis schreibt."""
    fixture_config = copy.deepcopy(base)
    for layer in ("raw", "processed", "harmonised"):
        fixture_config["paths"][f"{layer}_dir"] = str(data_dir / layer)
    for source in fixture_config["sources"]:
        source["csv"] = str(FIXTURE_DIR / f"{source['name']}.csv")
    return fixture_config


def make_raw_hotspots(rows: list[dict[str, Any]], config: dict[str, Any]) -> pd.DataFrame:
    """Baut eine kleine Raw-Tabelle. Jede Zeile ueberschreibt nur die Felder, um die es im Test geht."""
    table = pd.DataFrame([{**RAW_DEFAULTS, **row} for row in rows])
    table["acq_date"] = pd.to_datetime(table["acq_date"])
    table["type"] = table["type"].astype("float")
    table["sensor"] = table["satellite"].map(config["satellites"]["sensor_of"])
    return table
