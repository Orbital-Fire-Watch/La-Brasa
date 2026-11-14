"""POST /api/hotspots and GET /api/export.csv."""
from collections.abc import Iterator

from errors import ApiError
from services.scope import SENSOR_SQL, Scope

EXPORT_HEADER = "id,time,lat,lon,sensor,confidence,confidence_raw,frp,daynight,weight,n_active,province_id,event_id\n"


def feature_id(hotspot_id: str) -> int:
    """The API wants a numeric stable id (feature-state). The data has a 16-hex hash:
    13 hex digits = 52 bits, still an exact integer in JavaScript."""
    return int(hotspot_id[:13], 16)


def build_hotspots(conn, scope: Scope, body) -> dict:
    where, params = scope.where, {**scope.params, "start": body.start, "end": body.end}
    where += " AND h.in_series_n AND h.obs_date BETWEEN %(start)s AND %(end)s"
    if body.bbox:
        where += " AND h.longitude BETWEEN %(w)s AND %(e)s AND h.latitude BETWEEN %(s)s AND %(n)s"
        params.update(w=body.bbox[0], s=body.bbox[1], e=body.bbox[2], n=body.bbox[3])
    if body.min_frp:
        where += " AND h.frp >= %(min_frp)s"
        params["min_frp"] = body.min_frp
    total = conn.execute(f"SELECT count(*) AS n FROM hotspots_harmonised h WHERE {where}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT h.hotspot_id, h.latitude, h.longitude, h.acq_datetime_utc, {SENSOR_SQL} AS sensor, "
        f"h.confidence_class, h.frp, h.daynight, h.weight_n, h.region_id "
        f"FROM hotspots_harmonised h WHERE {where} "
        f"ORDER BY h.frp DESC NULLS LAST, h.hotspot_id LIMIT %(limit)s",    # truncate: highest FRP first
        {**params, "limit": body.limit},
    ).fetchall()
    features = [{
        "type": "Feature", "id": feature_id(r["hotspot_id"]),
        "geometry": {"type": "Point", "coordinates": (round(r["longitude"], 4), round(r["latitude"], 4))},
        "properties": {
            "time": r["acq_datetime_utc"], "sensor": r["sensor"], "confidence": r["confidence_class"],
            "frp": None if r["frp"] is None else round(r["frp"], 1), "daynight": r["daynight"],
            "weight": round(r["weight_n"], 3), "province_id": r["region_id"], "event_id": None},
    } for r in rows]
    return {"type": "FeatureCollection", "features": features, "total": total,
            "returned": len(features), "truncated": total > len(features)}


def export_rows(conn, scope: Scope, start, end) -> Iterator[str]:
    """Stream all points of the selection as CSV lines with a server-side cursor."""
    yield EXPORT_HEADER
    sql = (
        f"SELECT h.hotspot_id, h.acq_datetime_utc, h.latitude, h.longitude, {SENSOR_SQL} AS sensor, "
        f"h.confidence_class, h.confidence_raw, h.frp, h.daynight, h.weight_n, "
        f"(d.snpp_operating::int + d.aqua_operating::int + d.terra_operating::int) AS n_active, h.region_id "
        f"FROM hotspots_harmonised h JOIN day_status d ON d.date = h.obs_date "
        f"WHERE {scope.where} AND h.in_series_n AND h.obs_date BETWEEN %(start)s AND %(end)s "
        f"ORDER BY h.acq_datetime_utc, h.hotspot_id"
    )
    with conn.transaction(), conn.cursor(name="export") as cur:
        cur.itersize = 10_000                       # rows per round trip (default 100 is far too small)
        cur.execute(sql, {**scope.params, "start": start, "end": end})
        buffer = []                                  # one chunk per 2000 rows: a thread hop per line is too slow
        for r in cur:
            buffer.append(",".join([
                str(feature_id(r["hotspot_id"])), r["acq_datetime_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"{r['latitude']:.5f}", f"{r['longitude']:.5f}", r["sensor"], r["confidence_class"],
                r["confidence_raw"], "" if r["frp"] is None else f"{r['frp']:.1f}", r["daynight"],
                f"{r['weight_n']:.3f}", str(r["n_active"]), r["region_id"] or "", ""]) + "\n")
            if len(buffer) >= 2000:
                yield "".join(buffer)
                buffer = []
        if buffer:
            yield "".join(buffer)
