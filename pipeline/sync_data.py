#!/usr/bin/env python3
"""
sync_data.py - fetch the newest FIRMS data -> harmonise -> load into PostgreSQL, as one function.

Called by the backend on POST /api/sync (
backend/services/sync.py). Can also be run by hand from the repository root:
    python pipeline/sync_data.py

Steps of sync_data(), stopping at the first one that fails:
    1. ingestion/fetch_firms.py appends the new NRT rows to data/raw/<product>/fire_nrt_*.csv,
       then ingestion/fetch_clouds.py adds the cloud cover of the new days. A failed cloud fetch is only
       logged: the app works without the newest cloud values.
    2. harmonisation/run_pipeline.py --incremental: only the days from (first new NRT row - 3 days)
       on are recomputed; calibration, error model and static mask stay from the last full run.
       No tests, no KPI check (run them by hand with run_pipeline.py --force). No new rows: nothing to do.
    3. load_to_db.py --incremental replaces only those days (and day_status) in one transaction.
       If the harmonisation crashed, nothing is loaded: the database keeps the previous run.

The harmonisation runs in its own interpreter: HARMONISATION_PYTHON, default harmonisation/.venv
(see harmonisation/README.md). The backend image sets it to its own Python, which has every package.
"""
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import load_to_db
from ingestion import fetch_clouds, fetch_firms

REPO_ROOT = Path(__file__).resolve().parent.parent
HARMONISATION_DIR = REPO_ROOT / "harmonisation"

Step = Literal["fetch", "harmonise", "load"]
STEPS: tuple[Step, ...] = ("fetch", "harmonise", "load")


class SyncError(Exception):
    """A step failed. The message says which one and why; the database keeps the previous run."""


@dataclass(frozen=True)
class SyncResult:
    new_rows: int


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def harmonisation_python() -> str:
    return os.environ.get("HARMONISATION_PYTHON") or str(HARMONISATION_DIR / ".venv" / "bin" / "python")


def run_pipeline(*args: str) -> int:
    """Runs harmonisation/run_pipeline.py in its own environment; its log goes straight to ours."""
    return subprocess.run([harmonisation_python(), "run_pipeline.py", *args], cwd=HARMONISATION_DIR).returncode


def sync_data(on_step: Callable[[Step], None] = lambda step: None) -> SyncResult:
    """Runs the three steps. `on_step` is called before each one. Raises SyncError when a step fails."""
    on_step("fetch")
    log("1/3 fetching FIRMS NRT")
    try:
        new_rows = fetch_firms.update_nrt_files()
    except fetch_firms.FetchError as err:
        raise SyncError(f"Fetching FIRMS failed: {err}") from err
    try:
        fetch_clouds.update_clouds()
    except fetch_clouds.FetchError as err:
        log(f"Warning: fetching the cloud cover failed, the cloud values stay as they are: {err}")

    on_step("harmonise")
    log("2/3 harmonisation")
    try:
        code = run_pipeline("--incremental")
    except OSError as err:
        raise SyncError(f"Cannot start the harmonisation with {harmonisation_python()}: {err}") from err
    if code != 0:
        raise SyncError(f"The harmonisation ended with exit code {code}. The database keeps the previous data.")

    on_step("load")
    log("3/3 loading into PostgreSQL")
    if load_to_db.main(["--incremental"]) != 0:
        raise SyncError("Loading into the database failed. The database keeps the previous data.")
    log("done")
    return SyncResult(new_rows)


def main() -> int:
    try:
        sync_data()
    except SyncError as err:
        log(f"Error: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
