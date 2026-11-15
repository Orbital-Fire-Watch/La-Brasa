"""Daily forecast job: fetch the newest weather, then `run_forecast.py predict`. Made for cron on the server.

Run from La-Brasa/forecast (after the daily FIRMS update and harmonisation):
    .venv/bin/python daily.py                 # weather + predict
    .venv/bin/python daily.py --no-fetch      # predict only, with the weather files already there
    .venv/bin/python daily.py --dry-run       # print the plan (dates, requests), change nothing

What it does, in this order:
1. Lock: a second run that starts while one is still running exits at once.
2. Weather, from Meteomatics while the hackathon account is valid (daily.meteomatics_valid_until), afterwards
   from Open-Meteo (daily.fallback_provider, no key, core group only):
   - Open-Meteo only: the ERA5 history is extended up to 6 days before today (`history --append`);
   - `recent` per group from the day after the history file up to yesterday (ERA5 ends ~5 days before today);
   - `forecast` from today for forecast_days;
   - the ECMWF ensemble (51 members, Open-Meteo) for the uncertainty band, if daily.ensemble is true.
   A failed or refused request does not stop the job: the forecast is then made without weather where it is missing.
3. Stale forecast guard: a weather forecast older than daily.max_forecast_age_days is not used (no-weather tier).
4. `predict` (light: loads data/forecast/models/bundle.pkl, no fitting).
5. Housekeeping: keeps the newest daily.keep_forecast_files weather forecast files per group.
6. Warning if the fire data (data/harmonised/, the issue date) are older than daily.max_issue_date_age_days.
7. data/forecast/status.json with the state of the last run (ok, issue date, weather used, warnings), and
   one JSON line per run in data/forecast/logs/daily_runs.jsonl (for monitoring), the full log in
   data/forecast/logs/daily_<date>.log when started via cron (see README 2.2).

Exit code: 0 ok (also when it fell back to the no-weather tier), 1 predict output failed its checks,
2 no trained bundle, 3 another run is still active.
"""
from __future__ import annotations

import run_forecast  # noqa: F401  (first: sets the BLAS thread limit before numpy is imported)

import argparse
import fcntl
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from features import weather as wx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "data" / "forecast"
LOG_DIR = OUT / "logs"


@dataclass
class Plan:
    today: str
    fetch: bool
    reason: str
    provider: str = "meteomatics"
    history_append: list | None = None              # [start, end] (Open-Meteo ERA5)
    recent: dict = field(default_factory=dict)     # group -> [start, end]
    forecast_from: str | None = None


def history_end(group: str) -> date | None:
    path = OUT / f"weather_region_history_{group}.parquet"
    if not path.exists():
        return None
    return pd.to_datetime(pd.read_parquet(path, columns=["date"])["date"]).max().date()


ERA5_LAG_DAYS = 6          # Open-Meteo ERA5 is complete up to about 5 days before today


def make_plan(today: date, history_ends: dict[str, date | None], valid_until: date | None, fetch: bool,
              fallback: str | None = "open-meteo") -> Plan:
    """Which weather to request today, from which provider. Pure function (tested)."""
    if not fetch:
        return Plan(str(today), False, "--no-fetch")
    if history_ends.get("core") is None:
        return Plan(str(today), False, "no weather history (run fetch_weather.py history first)")
    provider = "meteomatics"
    if valid_until is not None and today > valid_until:
        if not fallback:
            return Plan(str(today), False, f"Meteomatics account ended on {valid_until}, no fallback provider")
        provider = fallback
    plan = Plan(str(today), True, "ok", provider=provider, forecast_from=str(today))
    groups = dict(history_ends) if provider == "meteomatics" else {"core": history_ends["core"]}
    if provider == "open-meteo":
        h_start, h_end = history_ends["core"] + timedelta(days=1), today - timedelta(days=ERA5_LAG_DAYS)
        if h_start <= h_end:
            plan.history_append = [str(h_start), str(h_end)]
            groups["core"] = h_end
    for group, end in groups.items():
        if end is None:
            continue
        start, stop = end + timedelta(days=1), today - timedelta(days=1)
        if start <= stop:
            plan.recent[group] = [str(start), str(stop)]
    return plan


def forecast_file_date(path: Path) -> date:
    return date.fromisoformat(path.stem.rsplit("_", 1)[-1])


def fresh_forecast(today: date, max_age_days: int, groups: list[str]) -> bool:
    """True if every required group has a weather forecast fetched at most max_age_days ago."""
    for group in groups:
        f = wx.latest_forecast_file(OUT, group)
        if f is None or (today - forecast_file_date(f)).days > max_age_days:
            return False
    return True


def prune_forecast_files(keep: int) -> list[str]:
    removed = []
    ens = sorted(OUT.glob("weather_ensemble_*.parquet"), key=forecast_file_date)
    for f in ens[:-keep] if keep > 0 else []:
        f.unlink()
        removed.append(f.name)
    for group in wx.GROUPS:
        for kind in ("points", "region"):
            files = sorted(OUT.glob(f"weather_{kind}_forecast_{group}_*.parquet"), key=forecast_file_date)
            for f in files[:-keep] if keep > 0 else []:
                f.unlink()
                removed.append(f.name)
    return removed


def fetch_weather(cfg: dict, plan: Plan) -> dict:
    """Run the planned requests. Returns per step 'ok' or the error text; never raises for API problems."""
    import fetch_weather as fw
    from features.meteomatics import MeteomaticsAuthError, MeteomaticsError

    status = {}
    today = date.fromisoformat(plan.today)
    end = today + timedelta(days=cfg["meteomatics"]["forecast_days"])
    steps = []
    if plan.history_append:
        steps.append(("history", "core", date.fromisoformat(plan.history_append[0]), date.fromisoformat(plan.history_append[1])))
    steps += [("recent", g, date.fromisoformat(a), date.fromisoformat(b)) for g, (a, b) in plan.recent.items()]
    groups = list(cfg["meteomatics"]["parameter_groups"]) if plan.provider == "meteomatics" else ["core"]
    steps += [("forecast", g, today, end) for g in groups]
    for kind, group, start, stop in steps:
        key = f"{plan.provider}:{kind}/{group}"
        try:
            if plan.provider == "open-meteo":
                failures = fw.fetch_open_meteo(cfg, kind, start, stop, append=kind == "history")
            else:
                failures = fw.fetch(cfg, start, stop, [group], kind, use_cache=False)
            status[key] = "ok" if failures == 0 else "failed"
        except MeteomaticsError as exc:          # includes authentication errors (account ended, wrong password)
            status[key] = f"error: {str(exc)[:200]}"
            if isinstance(exc, MeteomaticsAuthError) or getattr(exc, "status", None) in (401, 403):
                for k, g, *_ in steps:            # no point in trying the remaining steps
                    status.setdefault(f"{plan.provider}:{k}/{g}", "skipped (authentication)")
                break
        except Exception as exc:                 # network down etc.: keep going without weather
            status[key] = f"error: {type(exc).__name__}: {str(exc)[:200]}"
    if cfg.get("daily", {}).get("ensemble", False):
        try:                                     # uncertainty band only; the forecast works without it
            fw.cmd_ensemble(cfg)
            status["open-meteo:ensemble/core"] = "ok"
        except Exception as exc:
            status["open-meteo:ensemble/core"] = f"error: {type(exc).__name__}: {str(exc)[:200]}"
    return status


def write_status(record: dict, dc: dict) -> None:
    """data/forecast/status.json: the state of the last run in a few fields, for the backend / monitoring.

    ok = the tables were written and are current; warnings say what is degraded (old fire data, no weather)."""
    warnings = []
    age = record.get("issue_date_age_days")
    if age is not None and age > int(dc.get("max_issue_date_age_days", 2)):
        warnings.append(f"fire data end on {record['issue_date']} ({age} days ago)")
    if not record.get("weather_used"):
        warnings.append("no fresh weather forecast: forecast without weather")
    failed = [k for k, v in record.get("fetch", {}).items() if v != "ok"]
    if failed:
        warnings.append(f"weather requests failed: {', '.join(failed)}")
    status = {"last_run_utc": record["started_utc"], "ok": record.get("predict_exit") == 0,
              "issue_date": record.get("issue_date"), "issue_date_age_days": age,
              "model_version": record.get("model_version"), "weather_used": record.get("weather_used"),
              "weather_provider": record["plan"].get("provider") if record["plan"].get("fetch") else None,
              "warnings": warnings}
    tmp = OUT / "status.json.tmp"
    tmp.write_text(json.dumps(status, indent=1))
    tmp.replace(OUT / "status.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-fetch", action="store_true", help="do not call Meteomatics")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()
    cfg = yaml.safe_load((HERE / "config.yaml").read_text())
    dc = cfg.get("daily", {})
    valid_until = date.fromisoformat(str(dc["meteomatics_valid_until"])) if dc.get("meteomatics_valid_until") else None
    today = datetime.now(timezone.utc).date()
    plan = make_plan(today, {g: history_end(g) for g in wx.GROUPS}, valid_until, fetch=not args.no_fetch,
                     fallback=dc.get("fallback_provider", "open-meteo"))
    if args.dry_run:
        print(json.dumps(asdict(plan), indent=1))
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(LOG_DIR / "daily.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another daily run is still active; exiting", file=sys.stderr)
        return 3

    t0 = time.time()
    record = {"started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "plan": asdict(plan)}
    print(f"[daily] {record['started_utc']} plan: {plan.reason}", flush=True)
    record["fetch"] = fetch_weather(cfg, plan) if plan.fetch else {}
    use_weather = fresh_forecast(today, int(dc.get("max_forecast_age_days", 1)), list(dc.get("required_groups", ["core"])))
    record["weather_used"] = use_weather
    if not use_weather:
        print("[daily] no fresh weather forecast: predict with the no-weather tier", flush=True)
    code = run_forecast.cmd_predict(cfg, use_weather=use_weather)
    record["predict_exit"] = code
    record["pruned"] = prune_forecast_files(int(dc.get("keep_forecast_files", 14)))
    manifest = json.loads((OUT / "manifest.json").read_text()) if (OUT / "manifest.json").exists() else {}
    record.update({"issue_date": manifest.get("issue_date"), "model_version": manifest.get("model_version"),
                   "shipped_tiers": sorted(set(manifest.get("shipped_tier", {}).values())),
                   "runtime_s": round(time.time() - t0, 1)})
    # The issue date is the last day of data/harmonised/. If the fire data are not updated every day, the forecast
    # does not move forward; say so loudly (the FIRMS update itself is not part of this folder).
    if record["issue_date"]:
        age = (today - date.fromisoformat(record["issue_date"])).days
        record["issue_date_age_days"] = age
        if age > int(dc.get("max_issue_date_age_days", 2)):
            print(f"[daily] WARNING: fire data end on {record['issue_date']} ({age} days ago); update data/harmonised/ "
                  "first, otherwise the forecast does not move forward", file=sys.stderr, flush=True)
    with open(LOG_DIR / "daily_runs.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    write_status(record, dc)
    print(f"[daily] done in {record['runtime_s']} s, issue date {record['issue_date']}, tiers {record['shipped_tiers']}, "
          f"exit {code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
