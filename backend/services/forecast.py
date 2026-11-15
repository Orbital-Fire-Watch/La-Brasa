"""Forecast endpoints (docs/forecast_backend_frontend.md, section 5.2): queries only, nothing is computed here.

The rows are written once a day by forecast/daily.py and loaded by pipeline/load_forecast_to_db.py.
Only the regions of the API countries are returned (the forecast also covers three French border regions). The country
is the first two letters of the NUTS code, so the forecast does not depend on the `regions` table, which
load_to_db.py replaces on every run.
"""
import datetime as dt

from core.config import API_COUNTRIES
from errors import ApiError

DAY_COLUMNS = ("region_id, target_date, lead_days, p_big_fire_day, p_big_fire_day_lo, p_big_fire_day_hi, p_fire_day, "
               "p_clim_big_fire_day, p_clim_fire_day, risk_ratio, risk_class, source, model_version")
NOT_AVAILABLE = "No forecast has been loaded yet."


def latest_issue_date(conn) -> dt.date:
    # also 503 when db/init/003_forecast.sql has not run on this database yet
    if conn.execute("SELECT to_regclass('forecast_daily') AS t").fetchone()["t"] is None:
        raise ApiError(503, "FORECAST_NOT_AVAILABLE", NOT_AVAILABLE)
    issue = conn.execute("SELECT max(issue_date) AS d FROM forecast_daily").fetchone()["d"]
    if issue is None:
        raise ApiError(503, "FORECAST_NOT_AVAILABLE", NOT_AVAILABLE)
    return issue


def _known_region(conn, issue: dt.date, region_id: str) -> bool:
    if region_id in API_COUNTRIES:
        return True
    return conn.execute(
        "SELECT EXISTS (SELECT 1 FROM forecast_daily WHERE issue_date = %s AND region_id = %s "
        "AND left(region_id, 2) = ANY(%s)) AS ok", (issue, region_id, list(API_COUNTRIES)),
    ).fetchone()["ok"]


def build_forecast_daily(conn, region_id: str | None, target_date: dt.date | None) -> dict:
    issue = latest_issue_date(conn)
    if region_id is not None and not _known_region(conn, issue, region_id):
        raise ApiError(404, "REGION_NOT_FOUND", f"Unknown region '{region_id}'.")
    if target_date is not None and not (issue < target_date <= issue + dt.timedelta(days=10)):
        raise ApiError(400, "INVALID_DATE_RANGE",
                       f"target_date must lie in the 10 days after the forecast of {issue.isoformat()}.")
    where, params = ["issue_date = %s", "left(region_id, 2) = ANY(%s)"], [issue, list(API_COUNTRIES)]
    if region_id is not None:
        # a country id (ES, PT) selects all its regions
        where.append("(region_id = %s OR left(region_id, 2) = %s)")
        params += [region_id, region_id]
    if target_date is not None:
        where.append("target_date = %s")
        params.append(target_date)
    rows = conn.execute(
        f"SELECT {DAY_COLUMNS} FROM forecast_daily WHERE {' AND '.join(where)} ORDER BY region_id, lead_days",
        params,
    ).fetchall()
    return {"issue_date": issue, "days": rows}


def build_forecast_status(conn) -> dict:
    latest_issue_date(conn)
    row = conn.execute(
        "SELECT last_run_utc, ok, issue_date, model_version, weather_used, weather_provider, warnings "
        "FROM forecast_status WHERE id = 1"
    ).fetchone()
    if row is None:
        raise ApiError(503, "FORECAST_NOT_AVAILABLE", NOT_AVAILABLE)
    today = dt.datetime.now(dt.timezone.utc).date()
    return {**row, "issue_date_age_days": (today - row["issue_date"]).days}
