"""POST /api/grid, mode 'count': H3 cells with fires, hotspots and frp_sum.

The data stores H3 cells of resolution 8 (h3_r8). Coarser cells are made here with
h3.cell_to_parent after the SQL group by, so the database only needs one column.
A point belongs to the request if it lies in the area and in the bbox (spec: cell centre).
"""
import datetime as dt
from functools import lru_cache

import h3
import psycopg

from errors import ApiError
from services.scope import FIRES_SQL, FRP_SQL, HOTSPOTS_SQL, Scope


@lru_cache(maxsize=500_000)
def parent(cell: str, resolution: int) -> str:
    return h3.cell_to_parent(cell, resolution)


def build_grid_count(conn, scope: Scope, body) -> dict:
    if body.mode == "anomaly":
        raise ApiError(501, "NOT_IMPLEMENTED", "Mode 'anomaly' is not available yet.")
    if body.group_by == "day":
        raise ApiError(501, "NOT_IMPLEMENTED", "group_by 'day' is not available yet.")
    where, params = scope.where, {**scope.params, "start": body.start, "end": body.end}
    if body.bbox:
        where += " AND h.longitude BETWEEN %(w)s AND %(e)s AND h.latitude BETWEEN %(s)s AND %(n)s"
        params.update(w=body.bbox[0], s=body.bbox[1], e=body.bbox[2], n=body.bbox[3])
    try:
        rows = _query(conn, where, params)
    except psycopg.errors.UndefinedColumn:
        raise ApiError(501, "NOT_IMPLEMENTED", "The grid needs the column h3_r8 in hotspots_harmonised.") from None
    return _assemble(rows, body)


def _query(conn, where: str, params: dict):
    return conn.execute(
        f"SELECT h.h3_r8 AS cell, {FIRES_SQL} AS fires, {HOTSPOTS_SQL} AS hotspots, {FRP_SQL} AS frp, "
        f"min(h.obs_date) FILTER (WHERE h.in_series_n) AS first_seen, "
        f"max(h.obs_date) FILTER (WHERE h.in_series_n) AS last_seen "
        f"FROM hotspots_harmonised h WHERE {where} AND h.obs_date BETWEEN %(start)s AND %(end)s "
        f"GROUP BY h.h3_r8", params,
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