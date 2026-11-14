"""GET /api/meta: data status from day_status and the hotspot table."""
import datetime as dt

from core.config import ATTRIBUTION, MAP_BBOX, WEIGHT_VERSION
from dtos import API_VERSION, LIMITS

# day_status flag -> API sensor id. NOAA-20/21 are not in the data yet, so they are not listed.
SENSOR_FLAGS = {
    "terra_operating": "MODIS_TERRA", "aqua_operating": "MODIS_AQUA", "snpp_operating": "VIIRS_SNPP",
}


def data_range(conn) -> tuple[dt.date, dt.date]:
    """first_date .. last_date = the days with is_complete_day (the newest days are incomplete)."""
    row = conn.execute(
        "SELECT min(date) AS first, max(date) FILTER (WHERE is_complete_day) AS last FROM day_status"
    ).fetchone()
    return row["first"], row["last"]


def build_meta(conn) -> dict:
    first, last = data_range(conn)
    sensors = []
    for flag, sensor_id in SENSOR_FLAGS.items():
        row = conn.execute(
            f"SELECT min(date) AS f, max(date) AS t FROM day_status WHERE {flag}"
        ).fetchone()
        if row["f"] is None:
            continue
        # still running = delivering on the newest row of day_status (it includes the incomplete days)
        still_running = conn.execute(
            f"SELECT {flag} AS on FROM day_status ORDER BY date DESC LIMIT 1"
        ).fetchone()["on"]
        sensors.append({"id": sensor_id, "from": row["f"], "to": None if still_running else row["t"]})
    n = conn.execute("SELECT count(*) AS n FROM hotspots_harmonised").fetchone()["n"]
    stamp = conn.execute(
        "SELECT greatest(last_analyze, last_autoanalyze) AS t FROM pg_stat_user_tables "
        "WHERE relname = 'hotspots_harmonised'"
    ).fetchone()
    updated = (stamp and stamp["t"]) or dt.datetime.now(dt.timezone.utc)
    return {
        "api_version": API_VERSION,
        "data_version": f"{last.isoformat()}.{n}",           # changes whenever the data is reloaded
        "weight_version": WEIGHT_VERSION,
        "first_date": first,
        "last_date": last,
        "last_update": updated,
        "region": "Spain + Portugal (mainland)",
        "bbox": MAP_BBOX,
        "sensors": sensors,
        "confidence_levels": ["nominal", "high"],
        "features": {"areas": False, "daily": True, "events": False, "anomaly": False,
                     "anomaly_window": False, "grid_by_day": False, "landcover": False},
        "limits": LIMITS,
        "attribution": ATTRIBUTION,
    }
