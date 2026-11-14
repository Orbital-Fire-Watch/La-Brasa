"""Daily and monthly series (POST /api/daily and /api/calendar) from one query, and POST /api/by-region."""
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
