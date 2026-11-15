"""POST /api/hotspots and GET /api/export.csv. Both fill event_id from the event index and can be
limited to the points of one event (filter event_id: all its points up to and including `end`)."""
import datetime as dt
from collections.abc import Iterator

from services.events import EventIndex, events_of, hotspots_of_event
from services.meta import SENSOR_FLAGS
from services.scope import SENSOR_SQL, Scope

N_ACTIVE_SQL = " + ".join(f"d.{flag}::int" for flag in SENSOR_FLAGS)   # operating sensors on that day
EXPORT_CHUNK = 2000
EXPORT_HEADER = "id,time,lat,lon,sensor,confidence,confidence_raw,frp,daynight,weight,n_active,province_id,event_id\n"


def feature_id(hotspot_id: str) -> int:
    """The API wants a numeric stable id (feature-state). The data has a 16-hex hash:
    13 hex digits = 52 bits, still an exact integer in JavaScript."""
    return int(hotspot_id[:13], 16)


def _period(ix: EventIndex, scope: Scope, start: dt.date | None, end: dt.date, event: str | None,
            raw: bool = False) -> tuple[str, dict]:
    where, params = scope.where + ("" if raw else " AND h.in_series_n"), {**scope.params, "start": start, "end": end}
    if event is not None:
        where += " AND h.hotspot_id = ANY(%(event_hotspots)s) AND h.obs_date <= %(end)s"
        params["event_hotspots"] = hotspots_of_event(ix, event, end)
    else:
        where += " AND h.obs_date BETWEEN %(start)s AND %(end)s"
    return where, params


def build_hotspots(conn, scope: Scope, body, ix: EventIndex) -> dict:
    where, params = _period(ix, scope, body.start, body.end, body.event_id, body.raw)
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
    events = events_of(ix, [r["hotspot_id"] for r in rows], body.end)
    features = [{
        "type": "Feature", "id": feature_id(r["hotspot_id"]),
        "geometry": {"type": "Point", "coordinates": (round(r["longitude"], 4), round(r["latitude"], 4))},
        "properties": {
            "time": r["acq_datetime_utc"], "sensor": r["sensor"], "confidence": r["confidence_class"],
            "frp": None if r["frp"] is None else round(r["frp"], 1), "daynight": r["daynight"],
            "weight": round(r["weight_n"], 3), "province_id": r["region_id"], "event_id": event},
    } for r, event in zip(rows, events)]
    return {"type": "FeatureCollection", "features": features, "total": total,
            "returned": len(features), "truncated": total > len(features)}


def export_rows(conn, scope: Scope, start, end, event: str | None, ix: EventIndex) -> Iterator[str]:
    """Stream all points of the selection as CSV lines with a server-side cursor."""
    yield EXPORT_HEADER
    where, params = _period(ix, scope, start, end, event)
    sql = (
        f"SELECT h.hotspot_id, h.acq_datetime_utc, h.latitude, h.longitude, {SENSOR_SQL} AS sensor, "
        f"h.confidence_class, h.confidence_raw, h.frp, h.daynight, h.weight_n, "
        f"({N_ACTIVE_SQL}) AS n_active, h.region_id "
        f"FROM hotspots_harmonised h JOIN day_status d ON d.date = h.obs_date "
        f"WHERE {where} "
        f"ORDER BY h.acq_datetime_utc, h.hotspot_id"
    )
    with conn.transaction(), conn.cursor(name="export") as cur:
        cur.execute(sql, params)
        while rows := cur.fetchmany(EXPORT_CHUNK):  # one round trip and one yield per chunk, not per line
            events = events_of(ix, [r["hotspot_id"] for r in rows], end)
            yield "".join(",".join([
                str(feature_id(r["hotspot_id"])), r["acq_datetime_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"{r['latitude']:.5f}", f"{r['longitude']:.5f}", r["sensor"], r["confidence_class"],
                r["confidence_raw"], "" if r["frp"] is None else f"{r['frp']:.1f}", r["daynight"],
                f"{r['weight_n']:.3f}", str(r["n_active"]), r["region_id"] or "", event or ""]) + "\n"
                for r, event in zip(rows, events))
