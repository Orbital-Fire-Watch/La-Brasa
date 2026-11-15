"""Cloud cover of a selection per day, for POST /api/daily (table cloud_daily, pipeline/ingestion/fetch_clouds.py).

The table holds the share of the sky covered at the VIIRS day and night passes per 0.25° cell and day. A selection
(region, country, drawn area, or all of Spain and Portugal) gets the mean over the cells it touches.
Without the table (database older than db/init/003_clouds.sql) the fields are left out.
"""
import datetime as dt
import math

from shapely.geometry import box, shape
from shapely.prepared import prep

from core.config import API_COUNTRIES
from services.areas import inline_area, stored_area
from services.regions import _boundaries, _union, coverage

CELL_DEG = 0.25                   # cell_id = floor(lat / 0.25)_floor(lon / 0.25), as in hotspots_harmonised
CACHE_SIZE = 64                   # selections kept; the mean over all of Iberia reads about 6 million rows

_cache: dict[tuple[tuple[str, ...], dt.date], dict] = {}


def _selection_shape(conn, body):
    region_id = getattr(body, "region_id", None)
    if region_id is None:
        if getattr(body, "area_id", None) is not None:
            return shape(stored_area(conn, body.area_id).geometry)
        if getattr(body, "geometry", None) is not None:
            return shape(inline_area(body.geometry.model_dump()).geometry)
        return coverage(conn)
    if region_id in API_COUNTRIES:
        rows = conn.execute("SELECT region_id FROM regions WHERE country = %s", (region_id,)).fetchall()
        return _union(frozenset(r["region_id"] for r in rows))
    return _boundaries()[region_id]


def _cells(geom) -> list[str]:
    """Every cell that touches the shape."""
    west, south, east, north = geom.bounds
    inside = prep(geom)
    return [
        f"{i}_{j}"
        for i in range(math.floor(south / CELL_DEG), math.floor(north / CELL_DEG) + 1)
        for j in range(math.floor(west / CELL_DEG), math.floor(east / CELL_DEG) + 1)
        if inside.intersects(box(j * CELL_DEG, i * CELL_DEG, (j + 1) * CELL_DEG, (i + 1) * CELL_DEG))
    ]


def _means(conn, cells: tuple[str, ...], newest: dt.date) -> dict[dt.date, tuple]:
    """date -> (mean cloud_day, mean cloud_night). Cached per selection until new cloud data is loaded (`newest`)."""
    key = (cells, newest)
    if key not in _cache:
        rows = conn.execute(
            "SELECT date, avg(cloud_day) AS day, avg(cloud_night) AS night FROM cloud_daily "
            "WHERE cell_id = ANY(%s) GROUP BY date", (list(cells),),
        ).fetchall()
        if len(_cache) >= CACHE_SIZE:
            _cache.clear()
        _cache[key] = {r["date"]: (r["day"], r["night"]) for r in rows}
    return _cache[key]


def _rounded(value) -> float | None:
    return None if value is None else round(float(value), 2)


def daily_clouds(conn, body, first: dt.date, last: dt.date) -> dict:
    """{"cloud_day": [...], "cloud_night": [...]} from first to last (share 0-1, null = no value); {} without the table."""
    if conn.execute("SELECT to_regclass('cloud_daily') AS t").fetchone()["t"] is None:
        return {}
    newest = conn.execute("SELECT max(date) AS d FROM cloud_daily").fetchone()["d"]
    if newest is None:
        return {}
    means = _means(conn, tuple(_cells(_selection_shape(conn, body))), newest)
    days = [means.get(first + dt.timedelta(days=i), (None, None)) for i in range((last - first).days + 1)]
    return {"cloud_day": [_rounded(d[0]) for d in days], "cloud_night": [_rounded(d[1]) for d in days]}
