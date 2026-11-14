"""Orchestrator und einziger Einstiegspunkt der taeglichen Harmonisierungs-Pipeline.

Aufruf:
    .venv/bin/python run_pipeline.py                 # alle Stufen, unveraenderte Stufen werden uebersprungen
    .venv/bin/python run_pipeline.py --force         # alles neu rechnen (prueft dabei den Determinismus)
    .venv/bin/python run_pipeline.py --stage clean daily_grid
    .venv/bin/python run_pipeline.py --config andere_config.yaml

Stufen: ingest -> clean -> daily_grid -> calibrate -> quantify_uncertainty -> harmonise_daily
        -> weight_hotspots -> export_csv -> test -> validate
Rueckgabewert 1, wenn eine KPI-Schwelle verfehlt wird.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pyarrow.parquet as pq

from pipeline.algorithms import daily_grid, event_quality, uncertainty_model, validation_kpis, viirs_kpis
from pipeline.algorithms.calibration_factors import estimate_calibration_factors, overall_factors, select_calibration_days
from pipeline.algorithms.drift_monitor import monitor_overpass_drift, summarise_drift_warnings
from pipeline.algorithms.harmonise_daily import add_strength_columns, harmonise_daily_activity
from pipeline.algorithms.hotspot_weights import weight_hotspots
from pipeline.column_catalogue import TABLES, columns_of
from pipeline.csv_export import csv_directory, export_tables_to_csv
from pipeline.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT, config_fingerprint, load_config, path_of, viirs_keys
from pipeline.data_loading import clean_hotspots, schema_validation
from pipeline.data_loading.assign_region import load_region_names
from pipeline.data_loading.ingest_csv_to_parquet import ingest_all_sources
from pipeline.data_loading.common_area import learn_common_area
from pipeline.data_loading.static_source_mask import evaluate_mask_on_holdout
from pipeline.io_utils import file_sha256, get_logger, read_json, read_parquet, write_json, write_parquet_deterministic

DATA_STAGES = ["ingest", "clean", "daily_grid", "calibrate", "quantify_uncertainty", "harmonise_daily", "weight_hotspots", "export_csv"]
ALL_STAGES = DATA_STAGES + ["test", "validate"]
STORED_TABLES = [name for name, table in TABLES.items() if table.stored and name != "hotspots_clean"]
HASHED_OUTPUTS = [("processed", f"{name}.parquet") for name in ("hotspots_clean", "rejected_hotspots", "static_mask", "activity_daily_raw",
                                                                "satellite_coverage", "daily_grid", "cv_units_nuts2", "drift_monitor")] \
    + [("harmonised", f"{name}.parquet") for name in STORED_TABLES] + [("harmonised", "calib_summary.json")]
HOTSPOT_DATES = ("acq_date", "obs_date")


def run_stage_ingest(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe ingest: CSV -> data/raw/*.parquet."""
    return ingest_all_sources(config)


def run_stage_clean(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe clean: Raw -> hotspots_clean, rejected_hotspots, static_mask."""
    return clean_hotspots.clean_all_hotspots(config)


def run_stage_daily_grid(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe daily_grid: Tagessummen, Betriebsfenster, Status je Tag und lueckenloses Tagesraster."""
    hotspots = read_parquet(path_of(config, "processed", "hotspots_clean.parquet"))
    sums = daily_grid.sum_hotspots_by_day(hotspots, config)
    coverage = daily_grid.find_satellite_coverage(config)
    status = daily_grid.build_day_status(sums, coverage, config)[columns_of("day_status")]
    schema_validation.validate_day_status(status)
    grid = daily_grid.build_daily_grid(sums, status, config)
    write_parquet_deterministic(sums, path_of(config, "processed", "activity_daily_raw.parquet"), ["region_id", "obs_date", "satellite"], ("obs_date",))
    write_parquet_deterministic(coverage, path_of(config, "processed", "satellite_coverage.parquet"), date_columns=("window_start", "window_end"))
    write_parquet_deterministic(grid, path_of(config, "processed", "daily_grid.parquet"), date_columns=("date",))
    write_parquet_deterministic(status, path_of(config, "harmonised", "day_status.parquet"), date_columns=("date",))
    by_basis = status["basis_count"].value_counts().to_dict()
    get_logger().info("grid     %d Tage x %d Regionen, Basis der Anzahl: %s", len(status), grid["region_id"].nunique(), by_basis)
    return {"days": len(status), "regions": int(grid["region_id"].nunique()), "days_by_basis_count": by_basis,
            "days_by_basis_frp": status["basis_frp"].value_counts().to_dict(), "possible_gap_days": int(status["possible_gap"].sum()),
            "provisional_days": int(status["is_provisional"].sum())}


def run_stage_calibrate(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe calibrate: Faktoren je Region aus den Kalibriertagen, dazu der Drift-Monitor."""
    grid = read_parquet(path_of(config, "processed", "daily_grid.parquet"))
    factors = estimate_calibration_factors(select_calibration_days(grid, config), config)[columns_of("calib_factors")]
    drift = monitor_overpass_drift(config)
    summary = {"overall_factors": overall_factors(factors), "drift": summarise_drift_warnings(drift),
               "regions_with_fallback": int(factors["used_fallback_pair"].sum())}
    write_parquet_deterministic(factors, path_of(config, "harmonised", "calib_factors.parquet"), ["region_id"])
    write_parquet_deterministic(drift, path_of(config, "processed", "drift_monitor.parquet"))
    write_json(summary, path_of(config, "harmonised", "calib_summary.json"))
    values = summary["overall_factors"]
    get_logger().info("calib    Anzahl: Paar %.3f, Aqua %.3f, Terra %.3f | FRP: Paar %.3f, Aqua %.3f", values["k_count_pair"],
                      values["k_count_aqua"], values["k_count_terra"], values["k_frp_pair"], values["k_frp_aqua"])
    return summary


def build_cross_validation_units(config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Einheiten der Kreuzvalidierung fuer alle Flaechenskalen (Zelle, NUTS-2, Land, Gebiet)."""
    grid = read_parquet(path_of(config, "processed", "daily_grid.parquet"))
    hotspots = read_parquet(path_of(config, "processed", "hotspots_clean.parquet"))
    calibration_days = select_calibration_days(grid, config)
    loyo = uncertainty_model.estimate_leave_one_year_out_factors(calibration_days, config)
    region_units = uncertainty_model.predict_leave_one_year_out(calibration_days, loyo)
    operating = calibration_days[["date"] + [c for c in calibration_days if c.endswith("_operating")]].drop_duplicates("date")
    return {"cell": uncertainty_model.predict_cell_units(hotspots, operating, loyo, config), "nuts2": region_units,
            "country": uncertainty_model.sum_units_to_area(region_units, "country"),
            "all": uncertainty_model.sum_units_to_area(region_units, "all")}


def run_stage_quantify_uncertainty(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe quantify_uncertainty: Fehlermodell und Qualitaet der Tagesereignisse aus der Kreuzvalidierung."""
    units = build_cross_validation_units(config)
    units = {scale: units[scale] for scale in config["uncertainty"]["area_scales"]}
    quality = uncertainty_model.build_quality_by_scale(units, config)[columns_of("quality_by_scale")]
    confusion = event_quality.build_strength_confusion(units["nuts2"], config)[columns_of("strength_confusion")]
    big_fire = event_quality.build_big_fire_day_quality(units, config)[columns_of("big_fire_day_quality")]
    write_parquet_deterministic(units["nuts2"], path_of(config, "processed", "cv_units_nuts2.parquet"), ["area_id", "date"], ("date",))
    write_parquet_deterministic(units["cell"], path_of(config, "processed", "cv_units_cell.parquet"), date_columns=("date",))
    write_parquet_deterministic(quality, path_of(config, "harmonised", "quality_by_scale.parquet"))
    write_parquet_deterministic(confusion, path_of(config, "harmonised", "strength_confusion.parquet"))
    write_parquet_deterministic(big_fire, path_of(config, "harmonised", "big_fire_day_quality.parquet"))
    get_logger().info("quality  %d Zeilen im Fehlermodell, %d Zellen x %d Tage geprueft", len(quality),
                      units["cell"]["area_id"].nunique(), units["nuts2"]["date"].nunique())
    return {"quality_rows": len(quality), "cells": int(units["cell"]["area_id"].nunique()),
            "cv_days": int(units["nuts2"]["date"].nunique())}


def run_stage_harmonise_daily(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe harmonise_daily: Tagesraster x Faktoren -> activity_daily_harmonised mit Staerke und Fehlerbaendern."""
    grid = read_parquet(path_of(config, "processed", "daily_grid.parquet"))
    status = read_parquet(path_of(config, "harmonised", "day_status.parquet"))
    factors = read_parquet(path_of(config, "harmonised", "calib_factors.parquet"))
    quality = read_parquet(path_of(config, "harmonised", "quality_by_scale.parquet"))
    daily = add_strength_columns(harmonise_daily_activity(grid, status, factors, config), config)
    daily = uncertainty_model.attach_uncertainty_bands(daily, quality, config)
    daily = daily.merge(status[["date", "is_complete_day", "possible_gap"]], on="date")
    daily["region_name"] = daily["region_id"].map(load_region_names(config))
    daily = daily[columns_of("activity_daily_harmonised")]
    schema_validation.validate_daily_harmonised(daily)
    write_parquet_deterministic(daily, path_of(config, "harmonised", "activity_daily_harmonised.parquet"), ["region_id", "date"], ("date",))
    by_reliability = daily["reliability"].value_counts(dropna=False).to_dict()
    get_logger().info("harmon.  %d Zeilen, Zuverlaessigkeit: %s", len(daily), by_reliability)
    return {"rows": len(daily), "rows_by_reliability": {str(key): int(value) for key, value in by_reliability.items()},
            "first_date": str(daily["date"].min().date()), "last_date": str(daily["date"].max().date()),
            "big_fire_days": int(daily["big_fire_day"].sum())}


def run_stage_weight_hotspots(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe weight_hotspots: Gewichte je Punkt -> hotspots_harmonised."""
    hotspots = read_parquet(path_of(config, "processed", "hotspots_clean.parquet"))
    status = read_parquet(path_of(config, "harmonised", "day_status.parquet"))
    factors = read_parquet(path_of(config, "harmonised", "calib_factors.parquet"))
    weighted = weight_hotspots(hotspots, status, factors, config)[columns_of("hotspots_harmonised")]
    schema_validation.validate_hotspots_harmonised(weighted)
    write_parquet_deterministic(weighted, path_of(config, "harmonised", "hotspots_harmonised.parquet"), clean_hotspots.SORT_KEY, HOTSPOT_DATES)
    in_series = int(weighted["in_series_n"].sum())
    get_logger().info("weights  %d Punkte, davon %d in der Reihe", len(weighted), in_series)
    return {"rows": len(weighted), "rows_in_series": in_series, "sum_weight_n": float(weighted["weight_n"].sum())}


def run_stage_export_csv(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe export_csv: CSV-Kopien der Ausgabetabellen nach data/harmonised/csv (nur zum Ansehen, nicht vom Produkt genutzt)."""
    return export_tables_to_csv(config)


def run_stage_test(config: dict[str, Any]) -> dict[str, Any]:
    """Stufe test: fuehrt die pytest-Suiten (tests/ und aggregation/tests/) aus."""
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(PROJECT_ROOT / "tests"), str(PROJECT_ROOT / "aggregation" / "tests")],
                            cwd=PROJECT_ROOT, capture_output=True, text=True)
    last_line = (result.stdout.strip().splitlines() or [""])[-1]
    get_logger().info("test     %s", last_line)
    return {"passed": result.returncode == 0, "summary": last_line}


def load_typed_archive_hotspots(config: dict[str, Any]) -> pd.DataFrame:
    """Gueltige, eindeutige Archivzeilen mit bekanntem `type` im gemeinsamen Gebiet (Grundlage fuer die Pruefung der Ortsmaske)."""
    valid, _ = clean_hotspots.reject_invalid_rows(clean_hotspots.load_raw_hotspots(config), config)
    unique, _ = clean_hotspots.deduplicate_hotspots(valid, config)
    inside, _ = clean_hotspots.restrict_to_common_area(unique, learn_common_area(unique, config), config)
    return inside[inside["type"].notna()]


def check_status_and_types(config: dict[str, Any]) -> bool:
    """S1: Datumsfelder sind DATE, und leere Rohzahlen stehen genau an Tagen ohne Betrieb des Satelliten (auch n_viirs)."""
    checks = {"activity_daily_harmonised": ["date"], "day_status": ["date"], "hotspots_harmonised": list(HOTSPOT_DATES)}
    for name, columns in checks.items():
        schema = pq.read_schema(path_of(config, "harmonised", f"{name}.parquet"))
        if any(str(schema.field(column).type) != "date32[day]" for column in columns):
            return False
    daily = read_parquet(path_of(config, "harmonised", "activity_daily_harmonised.parquet"))
    status = read_parquet(path_of(config, "harmonised", "day_status.parquet"))
    merged = daily.merge(status, on="date", suffixes=("", "_status"))
    keys = list(config["satellites"]["column_key"].values()) + ["viirs"]
    return all(bool((merged[f"n_{key}"].isna() == ~merged[f"{key}_operating"]).all()) for key in keys)


def schema_matches_documentation(config: dict[str, Any]) -> bool:
    """I1d: Jede gespeicherte Tabelle hat genau die Spalten, die der Katalog (und damit die Doku) nennt."""
    return all(pq.read_schema(path_of(config, "harmonised", f"{name}.parquet")).names == columns_of(name) for name in STORED_TABLES)


def documented_columns(table_title: str) -> list[str]:
    """Spaltennamen eines Abschnitts von docs/data_dictionary.md (Zeilen der Form | `name` | ...)."""
    text = (PROJECT_ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
    parts = text.split(f"## {table_title}\n")
    section = parts[1].split("\n## ")[0] if len(parts) > 1 else ""
    return [line.split("`")[1] for line in section.splitlines() if line.startswith("| `")]


def schema_matches_everywhere(config: dict[str, Any]) -> bool:
    """N5: Parquet, CSV-Kopfzeile, Katalog und data_dictionary.md nennen dieselben Spalten in derselben Reihenfolge."""
    for name in STORED_TABLES:
        expected = columns_of(name)
        csv_path = csv_directory(config) / f"{name}.csv"
        csv_header = csv_path.read_text(encoding="utf-8").split("\n", 1)[0].split(",") if csv_path.exists() else expected
        if not (pq.read_schema(path_of(config, "harmonised", f"{name}.parquet")).names == csv_header == documented_columns(TABLES[name].title) == expected):
            return False
    return True


def measure_viirs_reference(config: dict[str, Any], daily: pd.DataFrame, hotspots: pd.DataFrame, regions: list[str]) -> dict[str, Any]:
    """N1 bis N3: Niveau des VIIRS-Mittels gegen SNPP, Gewichte 1/k, Rauschen gegen einen zurueckgehaltenen Satelliten."""
    return {"level": viirs_kpis.measure_viirs_level(daily, regions, config),
            "weights": viirs_kpis.measure_viirs_weight_identity(hotspots, daily),
            "noise": viirs_kpis.measure_instrument_noise(daily, regions, config), "satellites": viirs_keys(config)}


def run_stage_validate(config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Stufe validate: misst alle KPIs, vergleicht sie mit den Schwellen und schreibt kpi_report.json."""
    units = {"nuts2": read_parquet(path_of(config, "processed", "cv_units_nuts2.parquet")),
             "cell": read_parquet(path_of(config, "processed", "cv_units_cell.parquet"))}
    daily_path = path_of(config, "harmonised", "activity_daily_harmonised.parquet")
    daily, hotspots = read_parquet(daily_path), read_parquet(path_of(config, "harmonised", "hotspots_harmonised.parquet"))
    count_column, frp_column = validation_kpis.default_prediction_columns(config)
    accuracy = validation_kpis.measure_accuracy(units, config)
    measured = {"accuracy": accuracy, "viirs": measure_viirs_reference(config, daily, hotspots, accuracy["evaluation_regions"]),
                "uncertainty": validation_kpis.measure_uncertainty_calibration(units, count_column, frp_column, config),
                "roll_up": validation_kpis.measure_roll_up_exactness(daily, str(daily_path)),
                "weights": validation_kpis.measure_weight_identity(hotspots, daily),
                "mask": evaluate_mask_on_holdout(load_typed_archive_hotspots(config), config),
                "region_coverage": float(hotspots["region_id"].notna().mean()),
                "status_checks": check_status_and_types(config),
                "integrity": {"row_balance": state.get("clean", {}).get("report", {}).get("balanced"),
                              "deterministic": state.get("determinism", {}).get("identical"),
                              "tests_passed": state.get("test", {}).get("report", {}).get("passed"),
                              "schema_matches_documentation": schema_matches_documentation(config),
                              "schema_everywhere": schema_matches_everywhere(config)}}
    kpis = validation_kpis.evaluate_thresholds(measured, config)
    report = {"all_passed": all(row["passed"] for row in kpis), "kpis": kpis, "measured": measured,
              "informational": {"possible_gap_days": state.get("daily_grid", {}).get("report", {}).get("possible_gap_days"),
                                "drift": read_json(path_of(config, "harmonised", "calib_summary.json"))["drift"]}}
    write_json(report, path_of(config, "harmonised", "kpi_report.json"))
    for row in kpis:
        get_logger().info("kpi      %-5s %-52s %10s  %s %-8s %s", row["id"], row["name"],
                          f"{row['value']:.3g}" if isinstance(row["value"], float) else row["value"], row["rule"],
                          row["threshold"], "ok" if row["passed"] else "VERFEHLT")
    return {"all_passed": report["all_passed"], "failed": [row["id"] for row in kpis if not row["passed"]]}


STAGE_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "ingest": run_stage_ingest, "clean": run_stage_clean, "daily_grid": run_stage_daily_grid, "calibrate": run_stage_calibrate,
    "quantify_uncertainty": run_stage_quantify_uncertainty, "harmonise_daily": run_stage_harmonise_daily,
    "weight_hotspots": run_stage_weight_hotspots, "export_csv": run_stage_export_csv, "test": run_stage_test}


def code_fingerprint() -> str:
    """Hash aller Python-Dateien von Pipeline und Aggregation. Aendert sich der Code, laufen die Stufen neu."""
    digest = hashlib.sha256()
    files = sorted((PROJECT_ROOT / "pipeline").rglob("*.py")) + sorted((PROJECT_ROOT / "aggregation").glob("*.py"))
    for path in files + [PROJECT_ROOT / "run_pipeline.py"]:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def run_signature(config: dict[str, Any]) -> str:
    """Kennung eines Laufs aus Parametern, Code und Eingabedateien. Gleiche Kennung = gleiches Ergebnis erwartet."""
    inputs = [file_sha256(Path(source["csv"])) for source in config["sources"]]
    inputs.append(file_sha256(Path(config["paths"]["nuts_geojson"])))
    text = "|".join([config_fingerprint(config), code_fingerprint()] + inputs)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def hash_outputs(config: dict[str, Any]) -> dict[str, str]:
    """SHA-256 aller Ausgabetabellen (ohne Manifest und Berichte, die Zeitstempel enthalten)."""
    paths = {f"{layer}/{name}": path_of(config, layer, name) for layer, name in HASHED_OUTPUTS}
    return {key: file_sha256(path) for key, path in paths.items() if path.exists()}


def check_determinism(state: dict[str, Any], signature: str, new_hashes: dict[str, str]) -> dict[str, Any]:
    """Vergleicht die Ausgabe-Hashes mit dem vorigen Lauf derselben Kennung."""
    previous = state.get("output_hashes", {})
    if state.get("signature") != signature or not previous:
        return {"checked": False, "identical": None}
    return {"checked": True, "identical": previous == new_hashes}


def git_commit() -> str | None:
    """Aktueller Git-Stand, falls das Projekt in einem Repository mit Commits liegt."""
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def write_manifest(config: dict[str, Any], state: dict[str, Any]) -> None:
    """Schreibt manifest.json: was lief, mit welchen Parametern und Eingaben, und was herauskam."""
    manifest = {"written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "schema_version": config["schema_version"], "run_signature": state.get("signature"), "git_commit": git_commit(),
                "config_fingerprint": config_fingerprint(config), "code_fingerprint": code_fingerprint(),
                "nuts_version": config["nuts"]["version"], "calibration_window": config["calibration"],
                "input_files": {source["name"]: file_sha256(Path(source["csv"])) for source in config["sources"]},
                "parameters": {key: value for key, value in config.items() if not key.startswith("_")},
                "stages": {name: state[name] for name in ALL_STAGES if name in state},
                "determinism": state.get("determinism"), "output_hashes": state.get("output_hashes")}
    write_json(manifest, path_of(config, "harmonised", "manifest.json"))


def run_pipeline(config: dict[str, Any], stages: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    """Fuehrt die gewaehlten Stufen in fester Reihenfolge aus und gibt den Zustand des Laufs zurueck.

    Eine Datenstufe wird uebersprungen, wenn Parameter, Code und Eingabedateien seit dem letzten
    Lauf unveraendert sind (gleiche Kennung) und sie damals durchlief. `force` rechnet alles neu
    und vergleicht die neuen Dateien mit den alten: Sind sie identisch, ist der Lauf deterministisch.
    """
    logger = get_logger()
    state_path = path_of(config, "harmonised", "pipeline_state.json")
    state = read_json(state_path) if state_path.exists() else {}
    signature = run_signature(config)
    unchanged = state.get("signature") == signature
    for name in [stage for stage in ALL_STAGES if stage in (stages or ALL_STAGES)]:
        if name in DATA_STAGES and unchanged and not force and state.get(name, {}).get("done"):
            logger.info("%-21s unveraendert, uebersprungen", name)
            continue
        started = time.perf_counter()
        report = run_stage_validate(config, state) if name == "validate" else STAGE_FUNCTIONS[name](config)
        state[name] = {"done": True, "seconds": round(time.perf_counter() - started, 2), "report": report}
        if name == DATA_STAGES[-1]:
            hashes = hash_outputs(config)
            state["determinism"] = check_determinism(state, signature, hashes) if unchanged else {"checked": False, "identical": None}
            state["output_hashes"], state["signature"] = hashes, signature
    write_json(state, state_path)
    write_manifest(config, state)
    return state


def parse_arguments() -> argparse.Namespace:
    """Liest die Kommandozeile."""
    parser = argparse.ArgumentParser(description="Taegliche Harmonisierungs-Pipeline FIRMS MODIS -> VIIRS")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Pfad zur pipeline_config.yaml")
    parser.add_argument("--stage", nargs="+", choices=ALL_STAGES, help="nur diese Stufen ausfuehren")
    parser.add_argument("--force", action="store_true", help="alle Stufen neu rechnen")
    return parser.parse_args()


def main() -> int:
    """Einstiegspunkt der Kommandozeile. Gibt 1 zurueck, wenn eine KPI-Schwelle verfehlt wird."""
    arguments = parse_arguments()
    started = time.perf_counter()
    state = run_pipeline(load_config(arguments.config), arguments.stage, arguments.force)
    get_logger().info("fertig in %.1f s", time.perf_counter() - started)
    return 0 if state.get("validate", {}).get("report", {}).get("all_passed", True) else 1


if __name__ == "__main__":
    sys.exit(main())
