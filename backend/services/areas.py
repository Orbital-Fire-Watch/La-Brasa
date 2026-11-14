"""Drawn areas: POST /api/areas and the `area_id` / `geometry` selectors of the data endpoints (spec 6.3).

There is no PostGIS. The point-in-polygon test uses Postgres' built-in `polygon @> point`, after a bbox
pre-filter. Registered areas are stored in the table `areas` (db/init/002_areas.sql). The id is a hash
of the cleaned geometry, so the same area always gets the same id.
"""
import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np
import psycopg
import shapely
from psycopg.types.json import Jsonb
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.validation import make_valid

from dtos import GEOMETRY_MAX_VERTICES
from errors import ApiError
from services.regions import coverage

EARTH_RADIUS_KM = 6371.0088
COORD_DIGITS = 4                      # ~10 m, like every other coordinate of the API
FIRST_SIMPLIFY_DEG = 0.0005           # ~50 m; doubled until the clipped outline fits the vertex limit


@dataclass(frozen=True)
class Area:
    geometry: dict                    # GeoJSON MultiPolygon, exactly what the map shows
    bbox: tuple[float, float, float, float]


MISSING_TABLE = ApiError(500, "INTERNAL_ERROR",
                         "Drawn areas need the table 'areas': run db/init/002_areas.sql once (see startup.md).")


def _invalid() -> ApiError:
    return ApiError(400, "GEOMETRY_INVALID", "The area is not a valid Polygon or MultiPolygon.")


def _polygonal(geom: BaseGeometry) -> MultiPolygon:
    """Repairs self-intersections (e.g. freehand drawing) and keeps only the polygon parts."""
    if not geom.is_valid:
        geom = make_valid(geom)
    parts = [geom] if isinstance(geom, Polygon) else [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    polys = [p for part in parts for p in (part.geoms if isinstance(part, MultiPolygon) else [part]) if not p.is_empty and p.area > 0]
    if not polys:
        raise _invalid()
    return MultiPolygon(polys)


def _vertices(g: MultiPolygon) -> int:
    return sum(len(p.exterior.coords) + sum(len(r.coords) for r in p.interiors) for p in g.geoms)


def _fit_vertex_limit(g: MultiPolygon) -> MultiPolygon:
    """Clipping to the coastline adds vertices; the result must stay below the limit, because the
    frontend sends it again when it re-registers the area."""
    tolerance = FIRST_SIMPLIFY_DEG
    while _vertices(g) > GEOMETRY_MAX_VERTICES:
        g = _polygonal(g.simplify(tolerance, preserve_topology=True))
        tolerance *= 2
    return g


def _rounded_geojson(g: MultiPolygon) -> dict:
    """RFC 7946 winding (outer rings counter-clockwise) and rounded coordinates."""
    polys = [orient(p, 1.0) for p in g.geoms]
    coords = [[[[round(x, COORD_DIGITS), round(y, COORD_DIGITS)] for x, y in ring] for ring in poly]
              for poly in mapping(MultiPolygon(polys))["coordinates"]]
    return {"type": "MultiPolygon", "coordinates": coords}


def _ring_area_km2(ring: list) -> float:
    """Area on the sphere (same formula as d3/turf), good to well below 1 % at these sizes."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        total += math.radians(x2 - x1) * (2 + math.sin(math.radians(y1)) + math.sin(math.radians(y2)))
    return abs(total) * EARTH_RADIUS_KM ** 2 / 2


def area_km2(geojson: dict) -> float:
    return sum(_ring_area_km2(p[0]) - sum(_ring_area_km2(h) for h in p[1:]) for p in geojson["coordinates"])


def _bbox(geojson: dict) -> tuple[float, float, float, float]:
    xs = [x for p in geojson["coordinates"] for r in p for x, _ in r]
    ys = [y for p in geojson["coordinates"] for r in p for _, y in r]
    return (min(xs), min(ys), max(xs), max(ys))


def register_area(conn, geometry: dict) -> dict:
    """Cleans the drawn geometry, clips it to Spain + Portugal and stores it. Body of the 6.3 response."""
    clipped = _polygonal(shape(geometry)).intersection(coverage(conn))
    if clipped.is_empty or clipped.area == 0:
        raise ApiError(400, "AREA_OUTSIDE_REGION", "The area lies completely outside Spain and Portugal.")
    # normalize() fixes ring order and start vertex, so sending the returned geometry again
    # (the frontend does that after AREA_NOT_FOUND) gives the same id
    geojson = _rounded_geojson(_fit_vertex_limit(_polygonal(clipped)).normalize())
    area_id = "a_" + hashlib.sha1(json.dumps(geojson["coordinates"]).encode()).hexdigest()[:12]
    try:
        conn.execute("INSERT INTO areas (area_id, geometry) VALUES (%s, %s) ON CONFLICT (area_id) DO NOTHING",
                     (area_id, Jsonb(geojson)))
    except psycopg.errors.UndefinedTable:
        raise MISSING_TABLE from None
    return {"area_id": area_id, "geometry": geojson, "bbox": _bbox(geojson),
            "area_km2": round(area_km2(geojson), 1), "vertices": _vertices(shape(geojson))}


def stored_area(conn, area_id: str) -> Area:
    try:
        row = conn.execute("SELECT geometry FROM areas WHERE area_id = %s", (area_id,)).fetchone()
    except psycopg.errors.UndefinedTable:
        raise MISSING_TABLE from None
    if row is None:
        raise ApiError(404, "AREA_NOT_FOUND", f"Unknown area '{area_id}'. Please register it again.")
    return Area(row["geometry"], _bbox(row["geometry"]))


def inline_area(geometry: dict) -> Area:
    """`geometry` sent with a request (interim solution of the spec): repaired, not clipped –
    the country filter of the scope already keeps the points inside Spain and Portugal."""
    geojson = _rounded_geojson(_polygonal(shape(geometry)))
    return Area(geojson, _bbox(geojson))


def _pg_polygon(ring: list) -> str:
    """Postgres polygon literal '((x,y),...)'. The closing point is not needed."""
    return "(" + ",".join(f"({x},{y})" for x, y in ring[:-1]) + ")"


def area_sql(area: Area, params: dict) -> str:
    """SQL condition 'hotspot lies in the area' (bbox first, the polygon test only for the rest)."""
    w, s, e, n = area.bbox
    params.update(area_w=w, area_s=s, area_e=e, area_n=n)
    polys = []
    for i, poly in enumerate(area.geometry["coordinates"]):
        params[f"area_{i}"] = _pg_polygon(poly[0])
        cond = [f"%(area_{i})s::polygon @> point(h.longitude, h.latitude)"]
        for j, hole in enumerate(poly[1:]):
            params[f"area_{i}_{j}"] = _pg_polygon(hole)
            cond.append(f"NOT %(area_{i}_{j})s::polygon @> point(h.longitude, h.latitude)")
        polys.append("(" + " AND ".join(cond) + ")")
    return (f"h.longitude BETWEEN %(area_w)s AND %(area_e)s AND h.latitude BETWEEN %(area_s)s AND %(area_n)s "
            f"AND ({' OR '.join(polys)})")


def contains(area: Area, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Point-in-area test for many points at once (the in-memory event index, services/events.py)."""
    w, s, e, n = area.bbox
    inside = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    idx = np.flatnonzero(inside)
    geom = shape(area.geometry)
    shapely.prepare(geom)
    inside[idx] = shapely.intersects_xy(geom, lon[idx], lat[idx])      # boundary counts as inside, like Postgres
    return inside
