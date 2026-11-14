"""Gemeinsame Pfade und Helfer fuer alle Analyse-Skripte."""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent          # .../harmonisation/data_analysis
RAW = ROOT.parent.parent / "data" / "raw"       # gemeinsamer Datenordner des Repositorys (Iberien-CSVs)
GEO = ROOT.parent / "geo"                       # NUTS-2-Grenzen (eine Kopie fuer Pipeline und Analyse)
CACHE = ROOT / "cache"                          # Parquet-Zwischenstaende (neu erzeugbar)
RES = ROOT / "results"                          # Ergebnisse als JSON/CSV
CACHE.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)

IBERIA = CACHE / "iberia.parquet"
GLOBAL = CACHE / "global.parquet"

# Gemeinsamer Ueberlappungszeitraum Aqua / SNPP im Iberien-Archiv (volle Jahre)
OVERLAP_START = "2012-02-01"
OVERLAP_END = "2026-07-31"


def con():
    c = duckdb.connect()
    c.execute("PRAGMA threads=16")
    return c


def save(name, obj):
    """Ergebnis als JSON ablegen (wird vom Report eingelesen)."""
    path = RES / f"{name}.json"
    path.write_text(json.dumps(obj, indent=1, default=float))
    print("->", path.name)


def load(name):
    return json.loads((RES / f"{name}.json").read_text())
