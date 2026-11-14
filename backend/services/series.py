"""Daily and monthly series (POST /api/daily and /api/calendar) from one query, raw daily counts per sensor family
(POST /api/daily/sensors), and POST /api/by-region."""
import calendar as cal
import datetime as dt

from errors import ApiError
from services.meta import SENSOR_FLAGS, data_range
from services.scope import FIRES_SQL, FRP_SQL, HOTSPOTS_SQL, Scope


def day_status_map(conn) -> dict[dt.date, dict]:
    rows = conn.execute(
        f"SELECT date, is_complete_day, possible_gap, {', '.join(SENSOR_FLAGS)} FROM day_status"
    ).fetchall()
    return {r["date"]: {
        "complete": r["is_complete_day"], "gap": r["possible_gap"],
        "n_sensors": sum(int(r[flag]) for flag in SENSOR_FLAGS),
    } for r in rows}


def daily_values(conn, scope: Scope, first: dt.date, last: dt.date) -> dict[dt.date, tuple]:
    rows = conn.execute(
        f"SELECT h.obs_date AS d, {FIRES_SQL} AS fires, {HOTSPOTS_SQL} AS hotspots, {FRP_SQL} AS frp "
        f"FROM hotspots_harmonised h WHERE {scope.where} AND h.obs_date BETWEEN %(first)s AND %(last)s "
        f"GROUP BY h.obs_date",
        {**scope.params, "first": first, "last": last},
    ).fetchall()
    return {r["d"]: (float(r["fires"]), int(r["hotspots"]), float(r["frp"])) for r in rows}


def build_daily(conn, scope: Scope) -> dict:
    first, last = data_range(conn)
    status, values = day_status_map(conn), daily_values(conn, scope, first, last)
    fires, hotspots, frp, n_sensors = [], [], [], []
    for i in range((last - first).days + 1):
        day = first + dt.timedelta(days=i)
        st = status.get(day)
        n_sensors.append(st["n_sensors"] if st else 0)
        if st is None or not st["complete"] or st["n_sensors"] == 0:
            fires.append(None); hotspots.append(None); frp.append(None)   # no sensor delivered data
        else:
            f, h, p = values.get(day, (0.0, 0, 0.0))
            fires.append(round(f, 1)); hotspots.append(h); frp.append(round(p, 1))
    return {"start": first, "end": last, "fires": fires, "hotspots": hotspots, "frp_sum": frp,
            "n_sensors": n_sensors}


# Sensor family -> day_status flags of its satellites (schema version 2). A family is measured on a day when at
# least one of them operated.
FAMILY_FLAGS = {
    "modis": ("terra_operating", "aqua_operating"),
    "viirs": ("snpp_operating", "noaa20_operating", "noaa21_operating"),
}


def build_sensor_daily(conn, scope: Scope, start: dt.date | None, end: dt.date | None) -> dict:
    """Raw detections and raw FRP per day and family: the same points as /api/hotspots (in_series_n), unweighted."""
    first, last = data_range(conn)
    start, end = max(start or first, first), min(end or last, last)
    if start > end:
        raise ApiError(400, "INVALID_DATE_RANGE", f"The period lies outside the data ({first} to {last}).")
    measured = {}
    for r in conn.execute(
        f"SELECT date, is_complete_day, {', '.join(f for flags in FAMILY_FLAGS.values() for f in flags)} "
        "FROM day_status WHERE date BETWEEN %(start)s AND %(end)s", {"start": start, "end": end},
    ).fetchall():
        measured[r["date"]] = {fam: r["is_complete_day"] and any(r[f] for f in flags) for fam, flags in FAMILY_FLAGS.items()}
    values = {(r["d"], r["fam"]): (int(r["n"]), float(r["frp"])) for r in conn.execute(
        f"SELECT h.obs_date AS d, lower(h.sensor) AS fam, count(*) AS n, COALESCE(SUM(h.frp), 0) AS frp "
        f"FROM hotspots_harmonised h WHERE {scope.where} AND h.in_series_n "
        f"AND h.obs_date BETWEEN %(start)s AND %(end)s GROUP BY h.obs_date, lower(h.sensor)",
        {**scope.params, "start": start, "end": end},
    ).fetchall()}
    families = {fam: {"detections": [], "frp_sum": []} for fam in FAMILY_FLAGS}
    for i in range((end - start).days + 1):
        day = start + dt.timedelta(days=i)
        for fam, cols in families.items():
            if not measured.get(day, {}).get(fam):
                cols["detections"].append(None); cols["frp_sum"].append(None)
            else:
                n, frp = values.get((day, fam), (0, 0.0))
                cols["detections"].append(n); cols["frp_sum"].append(round(frp, 1))
    return {"start": start, "end": end, "families": families}


def build_calendar(conn, scope: Scope) -> dict:
    first, last = data_range(conn)
    status, values = day_status_map(conn), daily_values(conn, scope, first, last)
    months: dict[tuple[int, int], dict] = {}
    day = first
    while day <= last:
        m = months.setdefault((day.year, day.month), {"fires": 0.0, "hotspots": 0, "frp": 0.0, "ok": True})
        f, h, p = values.get(day, (0.0, 0, 0.0))
        m["fires"] += f; m["hotspots"] += h; m["frp"] += p
        st = status.get(day)
        if st is None or st["gap"] or not st["complete"]:
            m["ok"] = False
        day += dt.timedelta(days=1)

    last_is_month_end = last.day == cal.monthrange(last.year, last.month)[1]
    data = []
    for (year, month), m in months.items():
        running = (year, month) == (last.year, last.month) and not last_is_month_end
        starts_late = (year, month) == (first.year, first.month) and first.day != 1
        status_name = "running" if running else "incomplete" if (starts_late or not m["ok"]) else "complete"
        data.append({"year": year, "month": month, "fires": round(m["fires"], 1), "hotspots": m["hotspots"],
                     "frp_sum": round(m["frp"], 1), "status": status_name})
    done = [d for d in data if d["status"] == "complete"]
    maximum = {"fires": max((d["fires"] for d in done), default=0.0),
               "hotspots": max((d["hotspots"] for d in done), default=0),
               "frp_sum": max((d["frp_sum"] for d in done), default=0.0)}

    running_month = None
    if not last_is_month_end:
        same = []
        for year in range(first.year, last.year):
            end_day = min(last.day, cal.monthrange(year, last.month)[1])
            f = h = p = 0.0
            for d in range(1, end_day + 1):
                v = values.get(dt.date(year, last.month, d))
                if v:
                    f += v[0]; p += v[2]
            same.append({"year": year, "fires": round(f, 1), "frp_sum": round(p, 1)})
        running_month = {"month": f"{last.year}-{last.month:02d}", "through": last, "same_period": same}
    return {"data": data, "max": maximum, "running_month": running_month}


def build_by_region(conn, scope: Scope, body) -> dict:
    """Values per NUTS-2 region of the selection (spec 6.11, could-have). The data has no province level."""
    if body.level == "province":
        raise ApiError(501, "NOT_IMPLEMENTED", "The data has no province level yet, only regions (NUTS-2).")
    rows = conn.execute(
        f"SELECT h.region_id AS id, r.region_name AS name, {FIRES_SQL} AS fires, {HOTSPOTS_SQL} AS hotspots, "
        f"{FRP_SQL} AS frp FROM hotspots_harmonised h JOIN regions r ON r.region_id = h.region_id "
        f"WHERE {scope.where} AND h.obs_date BETWEEN %(start)s AND %(end)s "
        f"GROUP BY h.region_id, r.region_name ORDER BY fires DESC, h.region_id",
        {**scope.params, "start": body.start, "end": body.end},
    ).fetchall()
    total = sum(float(r["fires"]) for r in rows)
    return {"level": "region", "total_fires": round(total, 1), "data": [
        {"id": r["id"], "name": r["name"], "fires": round(float(r["fires"]), 1), "hotspots": int(r["hotspots"]),
         "frp_sum": round(float(r["frp"]), 1), "share": round(float(r["fires"]) / total, 4) if total else 0.0}
        for r in rows]}
