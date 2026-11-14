"""Tests des Gesamtlaufs: Determinismus, Ueberspringen unveraenderter Stufen, Schema gleich Dokumentation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

import run_pipeline
from helpers import PROJECT_ROOT, make_fixture_config
from pipeline.column_catalogue import TABLES, columns_of
from pipeline.config import path_of
from pipeline.csv_export import csv_directory


def test_forced_rerun_is_deterministic(config: dict[str, Any], tmp_path: Path) -> None:
    """Zwei vollstaendige Laeufe auf denselben Eingaben erzeugen Datei fuer Datei dieselben Hashes."""
    fixture_config = make_fixture_config(config, tmp_path)
    first = run_pipeline.run_pipeline(fixture_config, stages=run_pipeline.DATA_STAGES)
    second = run_pipeline.run_pipeline(fixture_config, stages=run_pipeline.DATA_STAGES, force=True)
    assert first["output_hashes"] == second["output_hashes"] and len(second["output_hashes"]) == len(run_pipeline.HASHED_OUTPUTS)
    assert second["determinism"] == {"checked": True, "identical": True}


def test_unchanged_stages_are_skipped(config: dict[str, Any], tmp_path: Path) -> None:
    """Ein zweiter Lauf ohne Aenderung rechnet nichts neu und laesst die Dateien unberuehrt."""
    fixture_config = make_fixture_config(config, tmp_path)
    run_pipeline.run_pipeline(fixture_config, stages=run_pipeline.DATA_STAGES)
    target = path_of(fixture_config, "harmonised", "activity_daily_harmonised.parquet")
    modified_before = target.stat().st_mtime_ns
    run_pipeline.run_pipeline(fixture_config, stages=run_pipeline.DATA_STAGES)
    assert target.stat().st_mtime_ns == modified_before


def test_stored_tables_match_the_catalogue(fixture_run: dict[str, Any]) -> None:
    """Jede gespeicherte Tabelle hat genau die Spalten des Katalogs, in derselben Reihenfolge."""
    for name in run_pipeline.STORED_TABLES:
        assert pq.read_schema(path_of(fixture_run["config"], "harmonised", f"{name}.parquet")).names == columns_of(name), name


def test_data_dictionary_lists_every_column() -> None:
    """Das Datenwoerterbuch nennt jede Spalte jeder Tabelle des Katalogs (Doku und Schema aus einer Quelle)."""
    text = (PROJECT_ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
    for name, table in TABLES.items():
        section = text.split(f"## {table.title}")[1].split("\n## ")[0]
        assert [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")] == columns_of(name), name


def test_every_function_has_a_docstring_and_stays_short() -> None:
    """Konvention: jede Funktion mit Docstring und Typannotationen, keine ueber etwa 40 Zeilen."""
    import ast
    files = list((PROJECT_ROOT / "pipeline").rglob("*.py")) + list((PROJECT_ROOT / "aggregation").glob("*.py")) + [PROJECT_ROOT / "run_pipeline.py"]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef):
                body_start = node.body[1].lineno if len(node.body) > 1 else node.body[0].lineno
                assert ast.get_docstring(node), f"{path.name}:{node.name} ohne Docstring"
                assert node.returns is not None, f"{path.name}:{node.name} ohne Rueckgabetyp"
                assert node.end_lineno - body_start + 1 <= 45, f"{path.name}:{node.name} ist zu lang"


def test_csv_export_matches_parquet(fixture_run: dict[str, Any]) -> None:
    """Jede Ausgabetabelle liegt als CSV vor: gleiche Spalten, gleiche Zeilenzahl, ISO-Datum, true/false, leer statt NaN."""
    config = fixture_run["config"]
    for name in run_pipeline.STORED_TABLES:
        csv = pd.read_csv(csv_directory(config) / f"{name}.csv", dtype=str, keep_default_na=False)
        assert list(csv.columns) == columns_of(name), name
        assert len(csv) == pq.read_metadata(path_of(config, "harmonised", f"{name}.parquet")).num_rows, name
    daily = pd.read_csv(csv_directory(config) / "activity_daily_harmonised.csv", dtype=str, keep_default_na=False)
    assert daily["date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    assert set(daily["is_complete_day"]) <= {"true", "false"} and not daily.isin(["nan", "NaN", "None"]).any().any()
    hotspots = pd.read_csv(csv_directory(config) / "hotspots_harmonised.csv", dtype=str, keep_default_na=False)
    assert hotspots["acq_datetime_utc"].str.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}").all()
