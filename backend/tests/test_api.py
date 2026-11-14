"""API tests against a running Postgres that holds the harmonised tables (real or fake data).

    DATABASE_URL=postgresql://... pytest backend/tests -q

The expected values are computed independently from the Parquet files in data/harmonised/
with pandas, not with the SQL of the backend.
"""
import os
import sys
from pathlib import Path

from typing import get_args

import h3
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")

from fastapi.testclient import TestClient  # noqa: E402

from core.db import connect  # noqa: E402
from dtos import Sensor  # noqa: E402
from main import app  # noqa: E402
from services.scope import SENSOR_SQL  # noqa: E402

PARQUET = Path(__file__).resolve().parents[2] / "data" / "harmonised"
client = TestClient(app)


@pytest.fixture(scope="module")
def hot() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET / "hotspots_harmonised.parquet")
    df = df[df["country"].isin(["ES", "PT"])].copy()
    df["frp_w"] = df["frp"] * df["weight_frp"]
    return df


FLAG_TO_SENSOR = {
    "terra_operating": "MODIS_TERRA", "aqua_operating": "MODIS_AQUA", "snpp_operating": "VIIRS_SNPP",
    "noaa20_operating": "VIIRS_NOAA20", "noaa21_operating": "VIIRS_NOAA21",
}
SATELLITE_TO_SENSOR = {"Terra": "MODIS_TERRA", "Aqua": "MODIS_AQUA", "SNPP": "VIIRS_SNPP",
                       "N20": "VIIRS_NOAA20", "N21": "VIIRS_NOAA21"}


@pytest.fixture(scope="module")
def status() -> pd.DataFrame:
    """day_status from the Parquet file, indexed by date (independent of the backend SQL)."""
    df = pd.read_parquet(PARQUET / "day_status.parquet")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("date").sort_index()


@pytest.fixture(scope="module")
def meta() -> dict:
    return client.get("/api/meta").json()


def hot_satellites() -> set[str]:
    return set(pd.read_parquet(PARQUET / "hotspots_harmonised.parquet", columns=["satellite"])["satellite"])


def nominal(df):
    return df[df["confidence_class"].isin(["nominal", "high"])]


def post(path, body, status=200):
    r = client.post(path, json=body)
    assert r.status_code == status, r.text
    return r.json()


# ------------------------------------------------------------------ meta, regions
def test_meta(meta, status):
    complete = status[status["is_complete_day"]]
    assert meta["first_date"] == status.index.min().isoformat()
    assert meta["last_date"] == complete.index.max().isoformat()    # newest complete day
    expected = {sensor for flag, sensor in FLAG_TO_SENSOR.items() if status[flag].any()}
    ids = {s["id"]: s for s in meta["sensors"]}
    assert set(ids) == expected
    for flag, sensor in FLAG_TO_SENSOR.items():
        on = status.index[status[flag]]
        still_running = bool(status[flag].iloc[-1])
        assert ids[sensor]["from"] == on.min().isoformat()
        assert ids[sensor]["to"] == (None if still_running else on.max().isoformat())
    assert meta["features"]["daily"] is True and meta["features"]["events"] is False


def test_sensor_ids_are_valid_dtos_values(hot):
    """Every (sensor, satellite) pair of the data must map to a value of the Sensor literal."""
    with connect() as conn:
        rows = conn.execute(f"SELECT DISTINCT h.satellite, {SENSOR_SQL} AS sensor FROM hotspots_harmonised h").fetchall()
    assert {r["sensor"] for r in rows} <= set(get_args(Sensor))
    assert {r["satellite"]: r["sensor"] for r in rows} == {s: SATELLITE_TO_SENSOR[s] for s in hot_satellites()}


def test_regions():
    body = client.get("/api/regions").json()
    props = [f["properties"] for f in body["features"]]
    assert {p["id"] for p in props if p["level"] == "country"} == {"ES", "PT"}
    regions = [p for p in props if p["level"] == "region"]
    assert len(regions) == 20 and all(p["country"] in ("ES", "PT") for p in regions)   # no French regions
    assert all(f["geometry"]["type"] == "MultiPolygon" for f in body["features"])


# ------------------------------------------------------------------ daily, calendar
def test_daily_matches_pandas(hot, meta):
    r = post("/api/daily", {"region_id": "ES11"})
    expected = nominal(hot[hot["region_id"] == "ES11"]).groupby("obs_date").agg(
        fires=("weight_n", "sum"), hotspots=("in_series_n", "sum"), frp=("frp_w", "sum"))
    start = pd.Timestamp(r["start"]).date()
    assert r["end"] == meta["last_date"] and len(r["fires"]) == (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days + 1
    assert abs(sum(v or 0 for v in r["fires"]) - expected["fires"].sum()) < 0.1 * len(r["fires"]) ** 0.5 + 1   # rounding per day
    day = expected["fires"].idxmax()
    i = (day - start).days
    assert r["fires"][i] == pytest.approx(expected.loc[day, "fires"], abs=0.06)
    assert r["hotspots"][i] == expected.loc[day, "hotspots"]
    assert r["frp_sum"][i] == pytest.approx(expected.loc[day, "frp"], abs=0.06)


def test_daily_n_sensors_counts_all_operating_satellites(status):
    r = post("/api/daily", {"region_id": "ES11"})
    flags = list(FLAG_TO_SENSOR)
    expected = status.loc[pd.Timestamp(r["start"]).date():pd.Timestamp(r["end"]).date(), flags].sum(axis=1)
    assert r["n_sensors"] == expected.tolist()
    assert max(r["n_sensors"]) == 5                                  # all five satellites overlap in 2023-2026


def test_daily_zero_is_not_null():
    r = post("/api/daily", {"region_id": "ES23"})                  # small region: many days without fire
    assert 0 in r["hotspots"] and r["fires"][r["hotspots"].index(0)] == 0   # a day with data but no fire is 0
    assert all(v is not None for v in r["fires"])                  # all days up to last_date are complete


def test_confidence_high_is_subset(hot):
    a = post("/api/daily", {"region_id": "PT11", "min_confidence": "nominal"})
    b = post("/api/daily", {"region_id": "PT11", "min_confidence": "high"})
    assert sum(b["hotspots"]) < sum(a["hotspots"])
    expected_high = (hot[(hot["region_id"] == "PT11") & (hot["confidence_class"] == "high")]["in_series_n"]).sum()
    assert sum(b["hotspots"]) == expected_high


def test_calendar_consistent_with_daily(hot, meta):
    daily = post("/api/daily", {"region_id": "ES41"})
    cal = post("/api/calendar", {"region_id": "ES41"})
    first, last = pd.Timestamp(meta["first_date"]), pd.Timestamp(meta["last_date"])
    assert len(cal["data"]) == (last.year - first.year) * 12 + last.month - first.month + 1
    assert cal["data"][-1]["status"] == "running" and cal["data"][0]["status"] == "complete"
    assert sum(m["hotspots"] for m in cal["data"]) == sum(daily["hotspots"])
    # the calendar sums the unrounded values; the daily array is rounded per day, so only compare to the exact value
    exact = nominal(hot[hot["region_id"] == "ES41"])["weight_n"].sum()
    assert sum(m["fires"] for m in cal["data"]) == pytest.approx(exact, abs=0.05 * len(cal["data"]))
    assert cal["max"]["fires"] == max(m["fires"] for m in cal["data"] if m["status"] == "complete")
    run = cal["running_month"]
    assert run["month"] == last.strftime("%Y-%m") and run["through"] == meta["last_date"]
    assert [y["year"] for y in run["same_period"]] == list(range(first.year, last.year))


def test_country_is_sum_of_regions():
    es = post("/api/daily", {"region_id": "ES"})
    parts = [post("/api/daily", {"region_id": r}) for r in ("ES11", "ES12", "ES13", "ES21", "ES22", "ES23", "ES24",
             "ES30", "ES41", "ES42", "ES43", "ES51", "ES52", "ES61", "ES62")]
    assert sum(es["hotspots"]) == sum(sum(p["hotspots"]) for p in parts)


# ------------------------------------------------------------------ grid
WINDOW = {"start": "2025-08-01", "end": "2025-08-14"}


def test_grid_totals_and_resolutions(hot):
    exp = nominal(hot[(hot["obs_date"] >= pd.Timestamp(WINDOW["start"]).date()) & (hot["obs_date"] <= pd.Timestamp(WINDOW["end"]).date())])
    for res in (8, 6, 4, 3):
        g = post("/api/grid", {**WINDOW, "resolution": res})
        assert g["days"] == 14 and all(h3.is_valid_cell(c["cell"]) and h3.get_resolution(c["cell"]) == res for c in g["cells"])
        assert sum(c["hotspots"] for c in g["cells"]) == exp["in_series_n"].sum()
        assert sum(c["fires"] for c in g["cells"]) == pytest.approx(exp["weight_n"].sum(), abs=0.1 * len(g["cells"]) + 1)
        assert g["max"]["hotspots"] == max(c["hotspots"] for c in g["cells"])
    coarse, fine = (post("/api/grid", {**WINDOW, "resolution": r}) for r in (3, 8))
    assert len(coarse["cells"]) < len(fine["cells"])


def test_grid_first_last_seen_and_bbox():
    g = post("/api/grid", {**WINDOW, "resolution": 6, "bbox": [-9.3, 41.8, -6.8, 43.8], "region_id": "ES11"})
    assert g["cells"] and all(WINDOW["start"] <= c["first_seen"] <= c["last_seen"] <= WINDOW["end"] for c in g["cells"])
    empty = post("/api/grid", {**WINDOW, "resolution": 6, "bbox": [-1, 30, 0, 31]})
    assert empty["cells"] == [] and empty["max"] == {"fires": 0.0, "hotspots": 0, "frp_sum": 0.0}


# ------------------------------------------------------------------ hotspots, export
def test_hotspots_truncate_by_frp(hot):
    body = {**WINDOW, "limit": 10, "region_id": "PT11"}
    r = post("/api/hotspots", body)
    exp = nominal(hot[(hot["region_id"] == "PT11") & hot["in_series_n"]
                      & (hot["obs_date"] >= pd.Timestamp(WINDOW["start"]).date()) & (hot["obs_date"] <= pd.Timestamp(WINDOW["end"]).date())])
    assert r["total"] == len(exp) and r["returned"] == min(10, len(exp)) and r["truncated"] == (len(exp) > 10)
    frps = [f["properties"]["frp"] for f in r["features"]]
    assert frps == sorted(frps, reverse=True)
    f = r["features"][0]
    assert isinstance(f["id"], int) and f["properties"]["time"].endswith("Z") and f["properties"]["event_id"] is None
    top = exp[exp["frp"] == exp["frp"].max()]                      # several satellites may tie on the top FRP
    assert f["properties"]["sensor"] in {SATELLITE_TO_SENSOR[s] for s in top["satellite"]}
    assert f["properties"]["province_id"] == "PT11"
    assert {x["properties"]["sensor"] for x in r["features"]} <= set(get_args(Sensor))


def test_export_matches_hotspots(status):
    q = {**WINDOW, "region_id": "ES41"}
    total = post("/api/hotspots", {**q, "limit": 20000})["total"]
    r = client.get("/api/export.csv", params=q)
    lines = r.text.strip().split("\n")
    assert r.headers["content-type"].startswith("text/csv")
    assert lines[0] == "id,time,lat,lon,sensor,confidence,confidence_raw,frp,daynight,weight,n_active,province_id,event_id"
    assert len(lines) - 1 == total and 'filename="hotspots_ES41_2025-08-01_2025-08-14.csv"' in r.headers["content-disposition"]
    assert r.headers["x-weight-version"] == "w1"
    first_row = lines[1].split(",")
    day = pd.Timestamp(first_row[1]).date()                        # n_active = sensors operating on that day
    assert first_row[10] == str(int(status.loc[day, list(FLAG_TO_SENSOR)].sum()))
    assert {line.split(",")[4] for line in lines[1:]} <= set(get_args(Sensor))


# ------------------------------------------------------------------ errors
@pytest.mark.parametrize("path,body,status,code", [
    ("/api/daily", {"region_id": "XX99"}, 404, "REGION_NOT_FOUND"),
    ("/api/daily", {"region_id": "FRI1"}, 404, "REGION_NOT_FOUND"),            # French region is not part of the API
    ("/api/daily", {"area_id": "a_7f3c9e2b41d0"}, 501, "NOT_IMPLEMENTED"),
    ("/api/daily", {"region_id": "ES11", "area_id": "a_7f3c9e2b41d0"}, 400, "AREA_CONFLICT"),
    ("/api/hotspots", {"start": "2025-08-14", "end": "2025-08-01"}, 400, "INVALID_DATE_RANGE"),
    ("/api/hotspots", {**WINDOW, "limit": 99999}, 400, "LIMIT_TOO_HIGH"),
    ("/api/grid", {**WINDOW, "resolution": 9}, 400, "RESOLUTION_OUT_OF_RANGE"),
    ("/api/grid", {**WINDOW, "resolution": 5, "mode": "anomaly"}, 501, "NOT_IMPLEMENTED"),
    ("/api/events", {"date": "2025-08-14"}, 501, "NOT_IMPLEMENTED"),
])
def test_errors(path, body, status, code):
    r = post(path, body, status)
    assert r["error"]["code"] == code and r["error"]["message"]
