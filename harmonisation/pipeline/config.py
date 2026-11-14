"""Laden der Konfiguration und Aufloesen der Pfade."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "pipeline_config.yaml"


def load_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Liest die YAML-Konfiguration und macht alle Pfade absolut.

    Relative Pfade gelten ab dem Ordner der Konfigurationsdatei. So laeuft die Pipeline
    unabhaengig vom aktuellen Arbeitsverzeichnis.
    """
    config_path = Path(config_path).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    base = config_path.parent
    config["paths"] = {key: str(resolve_path(base, value)) for key, value in config["paths"].items()}
    for source in config["sources"]:
        source["csv"] = str(resolve_path(base, source["csv"]))
    config["_config_path"] = str(config_path)
    return config


def resolve_path(base: Path, value: str) -> Path:
    """Macht einen Pfad absolut, relativ zu `base`."""
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def path_of(config: dict[str, Any], layer: str, file_name: str) -> Path:
    """Pfad einer Datei in einer Datenebene (raw, processed, harmonised)."""
    return Path(config["paths"][f"{layer}_dir"]) / file_name


def satellite_key(config: dict[str, Any], satellite: str) -> str:
    """Namensteil der Spalten eines Satelliten, z. B. "N20" -> "noaa20" (n_noaa20, frp_noaa20, noaa20_operating)."""
    return config["satellites"]["column_key"][satellite]


def viirs_keys(config: dict[str, Any]) -> list[str]:
    """Namensteile der VIIRS-Satelliten, aus denen die Referenzreihe gemittelt wird (Standard: snpp, noaa20, noaa21)."""
    return [satellite_key(config, satellite) for satellite in config["satellites"]["viirs"]]


def calibration_keys(config: dict[str, Any]) -> list[str]:
    """Namensteile der VIIRS-Satelliten, gegen die Faktoren und Fehlermodell bestimmt werden (Standard: nur snpp)."""
    return [satellite_key(config, satellite) for satellite in config["calibration"]["reference_satellites"]]


def config_fingerprint(config: dict[str, Any]) -> str:
    """Stabiler Hash aller Parameter. Aendert sich, sobald ein Parameter geaendert wird."""
    relevant = {key: value for key, value in config.items() if not key.startswith("_")}
    text = json.dumps(relevant, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
