"""Daily and monthly series (POST /api/daily and /api/calendar) from one query."""
import calendar as cal
import datetime as dt

from services.meta import data_range
from services.scope import FIRES_SQL, FRP_SQL, HOTSPOTS_SQL, Scope


def day_status_map(conn) -> dict[dt.date, dict]:
    rows = conn.execute(
        "SELECT date, is_complete_day, possible_gap, snpp_operating, aqua_operating, terra_operating "
        "FROM day_status"
    ).fetchall()
    return {r["date"]: {
        "complete": r["is_complete_day"], "gap": r["possible_gap"],
        "n_sensors": int(r["snpp_operating"]) + int(r["aqua_operating"]) + int(r["terra_operating"]),
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
