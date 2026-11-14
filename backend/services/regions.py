"""GET /api/regions: NUTS-2 regions plus the countries ES and PT, from one GeoJSON asset.

The asset (backend/assets/nuts2_iberia.geojson) is made by tools/make_regions_asset.py.
Names and countries come from the database table 'regions', so the API only lists regions
that actually have data.
"""
import json
from functools import lru_cache

from shapely.geometry import MultiPolygon, mapping, shape
from shapely.ops import unary_union

from core.config import API_COUNTRIES, REGIONS_GEOJSON
from errors import ApiError

COUNTRY_NAMES = {"ES": "Spain", "PT": "Portugal"}


def _round(coords, digits=4):
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(c, digits) for c in coords]
    return [_round(c, digits) for c in coords]


def _multi(geom) -> dict:
    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])
    return {"type": "MultiPolygon", "coordinates": _round(mapping(geom)["coordinates"])}


def _bbox(geom) -> list[float]:
    return [round(v, 4) for v in geom.bounds]


@lru_cache(maxsize=1)
def _boundaries() -> dict:
    if not REGIONS_GEOJSON.exists():
        raise ApiError(500, "INTERNAL_ERROR", "Region boundaries file is missing on the server.")
    data = json.loads(REGIONS_GEOJSON.read_text(encoding="utf-8"))
    return {f["properties"]["NUTS_ID"]: shape(f["geometry"]) for f in data["features"]}


@lru_cache(maxsize=4)
def _union(region_ids: frozenset[str]):
    shapes = _boundaries()
    return unary_union([shapes[i] for i in region_ids if i in shapes])


def coverage(conn):
    """Spain + Portugal as one shape, from the same regions /api/regions lists (drawn areas are clipped to it)."""
    rows = conn.execute("SELECT region_id FROM regions WHERE country = ANY(%s)", (list(API_COUNTRIES),)).fetchall()
    return _union(frozenset(r["region_id"] for r in rows))


def build_regions(conn) -> dict:
    rows = conn.execute(
        "SELECT region_id, region_name, country FROM regions WHERE country = ANY(%s) ORDER BY region_id",
        (list(API_COUNTRIES),),
    ).fetchall()
    shapes = _boundaries()
    features, by_country = [], {c: [] for c in API_COUNTRIES}
    for r in rows:
        geom = shapes.get(r["region_id"])
        if geom is None:
            continue
        by_country[r["country"]].append(geom)
        features.append({"type": "Feature", "geometry": _multi(geom), "properties": {
            "id": r["region_id"], "name": r["region_name"], "level": "region",
            "country": r["country"], "parent": r["country"], "bbox": _bbox(geom)}})
    countries = []
    for code, geoms in by_country.items():
        if geoms:
            union = unary_union(geoms)
            countries.append({"type": "Feature", "geometry": _multi(union), "properties": {
                "id": code, "name": COUNTRY_NAMES[code], "level": "country",
                "country": code, "parent": None, "bbox": _bbox(union)}})
    return {"type": "FeatureCollection", "features": countries + features}
