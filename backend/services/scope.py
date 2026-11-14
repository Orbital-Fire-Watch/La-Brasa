"""Turns the area, confidence and series rules of a request into a SQL condition.

Rules (Fire-API spec section 2 and 5, adapted to the harmonised tables):
- Only Spain and Portugal. The three French border regions in the data are left out.
- 'nominal' = confidence_class nominal + high, 'high' = high only. 'low' is never returned.
- fires = SUM(weight_n), hotspots = points with in_series_n, frp_sum = SUM(frp * weight_frp).
"""
from dataclasses import dataclass, field

from core.config import API_COUNTRIES
from errors import ApiError

# Sensor id of the API from the two columns of the data. The data calls the NOAA satellites N20 / N21,
# the API NOAA20 / NOAA21, so a plain sensor || '_' || upper(satellite) would give invalid ids.
SENSOR_SQL = (
    "(h.sensor || '_' || CASE h.satellite WHEN 'N20' THEN 'NOAA20' WHEN 'N21' THEN 'NOAA21' "
    "ELSE upper(h.satellite) END)"
)

FIRES_SQL = "COALESCE(SUM(h.weight_n), 0)"
HOTSPOTS_SQL = "COUNT(*) FILTER (WHERE h.in_series_n)"
FRP_SQL = "COALESCE(SUM(h.frp * h.weight_frp), 0)"


@dataclass
class Scope:
    where: str
    params: dict = field(default_factory=dict)


def region_exists(conn, region_id: str) -> bool:
    if region_id in API_COUNTRIES:
        return True
    row = conn.execute(
        "SELECT 1 FROM regions WHERE region_id = %s AND country = ANY(%s)", (region_id, list(API_COUNTRIES))
    ).fetchone()
    return row is not None


def build_scope(conn, body) -> Scope:
    """body: any request with region_id / area_id / geometry (optional) and min_confidence."""
    region_id = getattr(body, "region_id", None)
    if getattr(body, "area_id", None) or getattr(body, "geometry", None):
        raise ApiError(501, "NOT_IMPLEMENTED", "Drawn areas (area_id, geometry) are not available yet.")
    if getattr(body, "event_id", None):
        raise ApiError(501, "NOT_IMPLEMENTED", "Events are not available yet.")

    params: dict = {}
    if region_id is None:
        parts = ["h.country = ANY(%(countries)s)"]
        params["countries"] = list(API_COUNTRIES)
    elif region_id in API_COUNTRIES:
        parts = ["h.country = %(country)s"]
        params["country"] = region_id
    else:
        if not region_exists(conn, region_id):
            raise ApiError(404, "REGION_NOT_FOUND", f"Unknown region '{region_id}'.")
        parts = ["h.region_id = %(region_id)s"]
        params["region_id"] = region_id

    if getattr(body, "min_confidence", "nominal") == "high":
        parts.append("h.confidence_class = 'high'")
    else:
        parts.append("h.confidence_class IN ('nominal', 'high')")
    return Scope(" AND ".join(parts), params)
