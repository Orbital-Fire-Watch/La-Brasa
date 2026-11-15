#!/usr/bin/env python3
"""
update_daily.py - the daily data update, one entry point for cron.

Steps (each in the Python environment of its folder):
1. FIRMS:         pipeline/ingestion/fetch_firms.py        new archive days and the latest NRT days -> data/raw/
2. Harmonisation: harmonisation/run_pipeline.py            data/raw/ -> data/harmonised/ (unchanged stages skipped)
3. Database:      pipeline/load_to_db.py                   only with --load-db (the database is connected later)
4. Forecast:      forecast/daily.py                        weather + forecast for the new issue date

A failed step does not stop the following ones: with no new FIRMS data the harmonisation keeps the last state, and
the forecast still gets fresh weather. Every run appends one JSON line to data/logs/update_daily.jsonl and writes
data/logs/update_status.json (last run, what each step did, warnings).

Usage (from the repository root; plain python3, standard library only):
    python3 pipeline/update_daily.py                 # 1, 2, 4
    python3 pipeline/update_daily.py --load-db       # 1, 2, 3, 4
    python3 pipeline/update_daily.py --no-forecast   # only the fire data (1, 2)
    python3 pipeline/update_daily.py --skip-fetch    # harmonise + forecast with the raw files already there

Environment (optional): HARMONISATION_PYTHON, FORECAST_PYTHON, PIPELINE_PYTHON override the interpreters
(default: the .venv of each folder; PIPELINE_PYTHON defaults to the harmonisation one for fetch_firms).
UPDATE_THREADS (default 1) limits the BLAS threads of every step, so one run uses about one core.

Measured 15.11.2026 (laptop): full harmonisation recompute 1:48 min, max 2.05 GB RAM; unchanged data 1:10 min
(only its tests); forecast 26 s, 1.1 GB.

Exit code: 0 all steps ok, 1 a step failed or reported a problem, 3 another run is still active.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG_DIR = REPO / "data" / "logs"


def interpreter(env_var: str, folder: str) -> str:
    return os.environ.get(env_var) or str(REPO / folder / ".venv" / "bin" / "python")


def run(cmd: list[str], cwd: Path, timeout_s: int) -> tuple[int, str, float]:
    """Run a step; return (exit code, last lines of output, seconds). Output also goes to our stdout (cron log)."""
    t0 = time.time()
    env = dict(os.environ)
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):   # one core per step (server)
        env.setdefault(var, os.environ.get("UPDATE_THREADS", "1"))
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s, env=env)
        out = (p.stdout or "") + (p.stderr or "")
        code = p.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"timeout after {timeout_s} s\n{(e.stdout or '')}", 124
    except FileNotFoundError as e:
        out, code = f"cannot start: {e}", 127
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    sys.stdout.flush()
    return code, "\n".join(out.strip().splitlines()[-15:]), round(time.time() - t0, 1)


def step_fetch(days: int) -> dict:
    py = os.environ.get("PIPELINE_PYTHON") or interpreter("HARMONISATION_PYTHON", "harmonisation")
    code, tail, sec = run([py, str(REPO / "pipeline" / "ingestion" / "fetch_firms.py"), "--days", str(days)],
                          REPO, 900)
    res = {"exit": code, "seconds": sec}
    try:   # fetch_firms prints one JSON report
        txt = tail[tail.index("{"):] if "{" in tail else ""
        res["report"] = json.loads(txt) if txt else None
    except ValueError:
        res["report"] = None
    if code == 2:
        res["warning"] = "FIRMS_MAP_KEY missing in .env: no new fire data"
    elif code != 0:
        res["warning"] = "FIRMS request failed for at least one product (see report)"
    res["log_tail"] = tail if code not in (0,) else None
    return res


def step_harmonise() -> dict:
    code, tail, sec = run([interpreter("HARMONISATION_PYTHON", "harmonisation"), "run_pipeline.py"],
                          REPO / "harmonisation", 3600)
    res = {"exit": code, "seconds": sec}
    if code == 1:
        res["warning"] = "harmonisation: a KPI threshold was missed (outputs written, see its report)"
    elif code != 0:
        res["warning"] = f"harmonisation failed (exit {code}); the last harmonised state is kept"
        res["log_tail"] = tail
    return res


def step_load_db() -> dict:
    code, tail, sec = run([interpreter("PIPELINE_PYTHON", "pipeline"), "load_to_db.py"], REPO / "pipeline", 1800)
    res = {"exit": code, "seconds": sec}
    if code != 0:
        res["warning"] = f"load_to_db failed (exit {code})"
        res["log_tail"] = tail
    return res


def step_forecast() -> dict:
    code, tail, sec = run([interpreter("FORECAST_PYTHON", "forecast"), "daily.py"], REPO / "forecast", 1800)
    res = {"exit": code, "seconds": sec}
    if code != 0:
        res["warning"] = f"forecast daily.py exit {code}"
        res["log_tail"] = tail
    return res


def harmonised_end() -> str | None:
    """Last day of data/harmonised/ (last line of the CSV copy of day_status; no pandas needed)."""
    f = REPO / "data" / "harmonised" / "csv" / "day_status.csv"
    try:
        with open(f, "rb") as h:
            h.seek(0, os.SEEK_END)
            h.seek(max(h.tell() - 4096, 0))
            last = h.read().decode("utf-8", errors="replace").strip().splitlines()[-1]
        return last.split(",", 1)[0]
    except (OSError, IndexError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=5, help="NRT days fetched per product (1-10)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--load-db", action="store_true", help="also load the harmonised tables into Postgres")
    ap.add_argument("--no-forecast", action="store_true")
    args = ap.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(LOG_DIR / "update_daily.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another update_daily run is still active; exiting", file=sys.stderr)
        return 3

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[update_daily] {started}", flush=True)
    steps: dict = {}
    if not args.skip_fetch:
        print("[update_daily] 1/4 FIRMS", flush=True)
        steps["fetch_firms"] = step_fetch(args.days)
    print("[update_daily] 2/4 harmonisation", flush=True)
    steps["harmonise"] = step_harmonise()
    if args.load_db:
        print("[update_daily] 3/4 database", flush=True)
        steps["load_db"] = step_load_db()
    if not args.no_forecast:
        print("[update_daily] 4/4 forecast", flush=True)
        steps["forecast"] = step_forecast()

    warnings = [s["warning"] for s in steps.values() if s.get("warning")]
    record = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "steps": steps, "harmonised_end": harmonised_end(), "warnings": warnings,
              "ok": all(s["exit"] == 0 for s in steps.values())}
    with open(LOG_DIR / "update_daily.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    tmp = LOG_DIR / "update_status.json.tmp"
    tmp.write_text(json.dumps({k: v for k, v in record.items() if k != "steps"} |
                              {"steps": {k: {"exit": v["exit"], "seconds": v["seconds"]} for k, v in steps.items()}},
                              indent=1))
    tmp.replace(LOG_DIR / "update_status.json")
    print(f"[update_daily] done, ok={record['ok']}, warnings: {warnings or 'none'}", flush=True)
    return 0 if record["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
