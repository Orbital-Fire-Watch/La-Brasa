"""POST /api/grid: mode 'count' (H3 cells with fires, hotspots and frp_sum) and mode 'anomaly'
(the same window in other years, spec 6.6).

The data stores H3 cells of resolution 8 (column h3_cell). Coarser cells are made here with
h3.cell_to_parent after the SQL group by, so the database only needs one column.
A point belongs to the request if it lies in the area and in the bbox (spec: cell centre).
"""
import calendar as cal
import datetime as dt
import statistics
from functools import lru_cache

import h3
import psycopg

from errors import ApiError
from services.meta import data_range
from services.scope import FIRES_SQL, FRP_SQL, HOTSPOTS_SQL, Scope
from services.series import day_status_map

METRIC_SQL = {"fires": FIRES_SQL, "hotspots": HOTSPOTS_SQL, "frp_sum": FRP_SQL}


@lru_cache(maxsize=500_000)
def parent(cell: str, resolution: int) -> str:
    return h3.cell_to_parent(cell, resolution)


def build_grid(conn, scope: Scope, body) -> dict:
    return build_grid_anomaly(conn, scope, body) if body.mode == "anomaly" else build_grid_count(conn, scope, body)


def _with_bbox(scope: Scope, body) -> tuple[str, dict]:
    where, params = scope.where, dict(scope.params)
    if body.bbox:
        where += " AND h.longitude BETWEEN %(w)s AND %(e)s AND h.latitude BETWEEN %(s)s AND %(n)s"
        params.update(w=body.bbox[0], s=body.bbox[1], e=body.bbox[2], n=body.bbox[3])
    return where, params


def build_grid_count(conn, scope: Scope, body) -> dict:
    if body.group_by == "day":
        raise ApiError(501, "NOT_IMPLEMENTED", "group_by 'day' is not available yet.")
    where, params = _with_bbox(scope, body)
    params.update(start=body.start, end=body.end)
    try:
        rows = _query(conn, where, params)
    except psycopg.errors.UndefinedColumn:
        raise ApiError(501, "NOT_IMPLEMENTED", "The grid needs the column h3_cell in hotspots_harmonised.") from None
    return _assemble(rows, body)


def _query(conn, where: str, params: dict):
    return conn.execute(
        f"SELECT h.h3_cell AS cell, {FIRES_SQL} AS fires, {HOTSPOTS_SQL} AS hotspots, {FRP_SQL} AS frp, "
        f"min(h.obs_date) FILTER (WHERE h.in_series_n) AS first_seen, "
        f"max(h.obs_date) FILTER (WHERE h.in_series_n) AS last_seen "
        f"FROM hotspots_harmonised h WHERE {where} AND h.obs_date BETWEEN %(start)s AND %(end)s "
        f"GROUP BY h.h3_cell", params,
    ).fetchall()


def _assemble(rows, body) -> dict:
    cells: dict[str, dict] = {}
    for r in rows:
        if r["hotspots"] <= 0:
            continue
        key = r["cell"] if body.resolution == 8 else parent(r["cell"], body.resolution)
        c = cells.setdefault(key, {"cell": key, "fires": 0.0, "hotspots": 0, "frp_sum": 0.0,
                                   "first_seen": r["first_seen"], "last_seen": r["last_seen"]})
        c["fires"] += float(r["fires"]); c["hotspots"] += int(r["hotspots"]); c["frp_sum"] += float(r["frp"])
        c["first_seen"] = min(c["first_seen"], r["first_seen"])
        c["last_seen"] = max(c["last_seen"], r["last_seen"])
    out = sorted(cells.values(), key=lambda c: c["cell"])
    for c in out:
        c["fires"], c["frp_sum"] = round(c["fires"], 1), round(c["frp_sum"], 1)
    return {
        "mode": "count", "resolution": body.resolution, "days": (body.end - body.start).days + 1,
        "cells": out,
        "max": {"fires": max((c["fires"] for c in out), default=0.0),
                "hotspots": max((c["hotspots"] for c in out), default=0),
                "frp_sum": max((c["frp_sum"] for c in out), default=0.0)},
    }

# ---------------------------------------------------------------------------- mode 'anomaly'

def shift_years(day: dt.date, years: int) -> dt.date:
    """Same calendar day in another year; 29 February becomes 28 February."""
    year = day.year + years
    return day.replace(year=year, day=min(day.day, cal.monthrange(year, day.month)[1]))


def _window(body, last: dt.date) -> tuple[dt.date, dt.date]:
    if body.period is None:
        return body.start, body.end
    year, _, month = body.period.partition("-")
    if month:
        start = dt.date(int(year), int(month), 1)
        end = dt.date(int(year), int(month), cal.monthrange(int(year), int(month))[1])
    else:
        start, end = dt.date(int(year), 1, 1), dt.date(int(year), 12, 31)
    return start, min(end, last)


def comparison_years(conn, start: dt.date, end: dt.date, compare) -> list[int]:
    """Years whose shifted window lies completely in the data, every day with at least one sensor.
    compare = N: only the N most recent of these years before the selected one (spec 6.6)."""
    first, last = data_range(conn)
    status = day_status_map(conn)

    def complete(s: dt.date, e: dt.date) -> bool:
        if s < first or e > last:
            return False
        days = ((s + dt.timedelta(days=i)) for i in range((e - s).days + 1))
        return all((st := status.get(d)) is not None and st["complete"] and st["n_sensors"] > 0 for d in days)

    years = [y for y in range(first.year, last.year + 1)
             if y != start.year and complete(shift_years(start, y - start.year), shift_years(end, y - start.year))]
    if compare != "all":
        years = [y for y in years if y < start.year][-compare:]
    return years


def build_grid_anomaly(conn, scope: Scope, body) -> dict:
    """Value of every cell in the window compared with the median of the same window in the comparison years."""
    start, end = _window(body, data_range(conn)[1])
    if start > end:
        raise ApiError(400, "INVALID_DATE_RANGE", "The window lies after the last day with data.")
    years = comparison_years(conn, start, end, body.compare)
    windows = [(y, shift_years(start, y - start.year), shift_years(end, y - start.year)) for y in [start.year, *years]]
    where, params = _with_bbox(scope, body)
    params.update(wy=[w[0] for w in windows], ws=[w[1] for w in windows], we=[w[2] for w in windows])
    rows = conn.execute(
        f"SELECT w.y AS year, h.h3_cell AS cell, {METRIC_SQL[body.metric]} AS v "
        f"FROM hotspots_harmonised h "
        f"JOIN unnest(%(wy)s::int[], %(ws)s::date[], %(we)s::date[]) AS w(y, s, e) ON h.obs_date BETWEEN w.s AND w.e "
        f"WHERE {where} GROUP BY w.y, h.h3_cell", params,
    ).fetchall()

    per_year: dict[int, dict[str, float]] = {y: {} for y, _, _ in windows}
    for r in rows:
        if r["v"] <= 0:
            continue
        cell = r["cell"] if body.resolution == 8 else parent(r["cell"], body.resolution)
        values = per_year[r["year"]]
        values[cell] = values.get(cell, 0.0) + float(r["v"])

    selected, history = per_year[start.year], [per_year[y] for y in years]
    cells = []
    for cell in sorted(set(selected).union(*history)):
        value = selected.get(cell, 0.0)
        others = [h.get(cell, 0.0) for h in history]
        median = statistics.median(others) if others else 0.0
        if value == 0 and median == 0:
            continue
        cells.append({"cell": cell, "value": round(value, 1), "median": round(median, 1),
                      "diff": round(value - median, 1), "rank": 1 + sum(v > value for v in others)})
    return {
        "mode": "anomaly", "resolution": body.resolution, "metric": body.metric, "start": start, "end": end,
        "years_compared": len(years), "compare_years": years, "cells": cells,
        "max_abs_diff": max((abs(c["diff"]) for c in cells), default=0.0),
    }
