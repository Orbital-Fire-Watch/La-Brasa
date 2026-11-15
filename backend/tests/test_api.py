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
from services.events import cluster, event_id  # noqa: E402
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
    assert meta["features"]["daily"] is True and meta["features"]["events"] is True
    assert meta["features"]["areas"] is True and meta["features"]["anomaly"] is True and meta["features"]["anomaly_window"] is True


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


CLOUDS = PARQUET.parent / "raw" / "clouds" / "cloud_daily.parquet"


@pytest.mark.skipif(not CLOUDS.exists(), reason="no cloud data (pipeline/ingestion/fetch_clouds.py)")
def test_daily_clouds_of_one_cell():
    clouds = pd.read_parquet(CLOUDS)
    row = clouds.dropna().iloc[-1]                                   # a cell and day with both values
    i, j = map(int, row["cell_id"].split("_"))
    lon, lat = (j + 0.4) * 0.25, (i + 0.4) * 0.25                     # a small square inside that one cell
    square = [[lon, lat], [lon + 0.05, lat], [lon + 0.05, lat + 0.05], [lon, lat + 0.05], [lon, lat]]
    r = post("/api/daily", {"geometry": {"type": "Polygon", "coordinates": [square]}})
    assert len(r["cloud_day"]) == len(r["cloud_night"]) == len(r["fires"])
    k = (row["date"] - pd.Timestamp(r["start"]).date()).days
    if 0 <= k < len(r["fires"]):
        assert r["cloud_day"][k] == pytest.approx(row["cloud_day"], abs=0.006)
        assert r["cloud_night"][k] == pytest.approx(row["cloud_night"], abs=0.006)


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
    assert isinstance(f["id"], int) and f["properties"]["time"].endswith("Z") and f["properties"]["event_id"].startswith("e_")
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


# ------------------------------------------------------------------ drawn areas
RECT = {"type": "Polygon", "coordinates": [[[-8.2, 42.1], [-7.5, 42.1], [-7.5, 42.5], [-8.2, 42.5], [-8.2, 42.1]]]}


def in_rect(df):
    return df[df["longitude"].between(-8.2, -7.5) & df["latitude"].between(42.1, 42.5)]


def test_drawn_area_filters_like_pandas(hot):
    area = post("/api/areas", {"geometry": RECT})
    assert area["area_id"].startswith("a_") and area["vertices"] == 5
    assert area["area_km2"] == pytest.approx(0.7 * 111.32 * 0.7396 * 0.4 * 111.32, rel=0.01)   # cos(42.3°) = 0.7396
    exp = nominal(in_rect(hot))
    by_id = post("/api/daily", {"area_id": area["area_id"]})
    inline = post("/api/daily", {"geometry": RECT})
    assert sum(by_id["hotspots"]) == sum(inline["hotspots"]) == exp["in_series_n"].sum()
    window = exp[(exp["obs_date"] >= pd.Timestamp(WINDOW["start"]).date()) & (exp["obs_date"] <= pd.Timestamp(WINDOW["end"]).date())]
    assert post("/api/hotspots", {**WINDOW, "area_id": area["area_id"]})["total"] == window["in_series_n"].sum()


def test_drawn_area_is_clipped_stable_and_exportable():
    coast = {"type": "Polygon", "coordinates": [[[-10.5, 42.0], [-8.0, 42.0], [-8.0, 43.5], [-10.5, 43.5], [-10.5, 42.0]]]}
    a, b = post("/api/areas", {"geometry": coast}), post("/api/areas", {"geometry": coast})
    assert a["area_id"] == b["area_id"]                                             # same area, same id
    again = post("/api/areas", {"geometry": a["geometry"]})                         # re-register after AREA_NOT_FOUND
    assert again["area_id"] == a["area_id"]
    assert a["bbox"][0] > -9.5 and a["vertices"] <= 1000                            # the sea part is cut off
    bowtie = {"type": "Polygon", "coordinates": [[[-8, 42], [-7, 43], [-7, 42], [-8, 43], [-8, 42]]]}
    assert post("/api/areas", {"geometry": bowtie})["area_km2"] > 0                # self-intersection is repaired
    area = post("/api/areas", {"geometry": RECT})
    total = post("/api/hotspots", {**WINDOW, "area_id": area["area_id"], "limit": 20000})["total"]
    r = client.get("/api/export.csv", params={**WINDOW, "area_id": area["area_id"]})
    assert len(r.text.strip().split("\n")) - 1 == total
    assert f'hotspots_{area["area_id"]}_' in r.headers["content-disposition"]


# ------------------------------------------------------------------ grid, mode anomaly
def test_anomaly_matches_pandas(hot):
    start, end, res = pd.Timestamp("2025-08-07").date(), pd.Timestamp("2025-08-13").date(), 5
    g = post("/api/grid", {"mode": "anomaly", "start": start.isoformat(), "end": end.isoformat(), "resolution": res,
                           "region_id": "ES11", "compare": 3})
    assert g["compare_years"] == [2022, 2023, 2024] and g["years_compared"] == 3

    df = nominal(hot[hot["region_id"] == "ES11"]).copy()
    df["parent"] = [h3.cell_to_parent(c, res) for c in df["h3_cell"]]

    def per_cell(year):
        s, e = start.replace(year=year), end.replace(year=year)
        return df[(df["obs_date"] >= s) & (df["obs_date"] <= e)].groupby("parent")["weight_n"].sum()

    selected, history = per_cell(2025), [per_cell(y) for y in (2022, 2023, 2024)]
    cells = {c["cell"]: c for c in g["cells"]}
    for cell, value in selected[selected > 0].items():
        others = sorted(h.get(cell, 0.0) for h in history)
        assert cells[cell]["value"] == pytest.approx(value, abs=0.06)
        assert cells[cell]["median"] == pytest.approx(others[1], abs=0.06)
        assert cells[cell]["rank"] == 1 + sum(v > value for v in others)
    assert g["max_abs_diff"] == max(abs(c["diff"]) for c in g["cells"])


def test_anomaly_period_and_all_years(meta):
    g = post("/api/grid", {"mode": "anomaly", "period": "2025-08", "resolution": 4, "metric": "frp_sum"})
    assert (g["start"], g["end"], g["metric"]) == ("2025-08-01", "2025-08-31", "frp_sum")
    first, last = pd.Timestamp(meta["first_date"]).year, pd.Timestamp(meta["last_date"]).year
    assert g["compare_years"] == [y for y in range(first, last + 1) if y != 2025]   # later years count too


# ------------------------------------------------------------------ events
D = "2025-08-14"


def _day(iso: str) -> int:
    return pd.Timestamp(iso).date().toordinal()


def test_cluster_rule_from_the_spec():
    """Spec 5.6 / section 10: neighbour cell after 2 days = same event, same cell after 3 days = new event."""
    c = h3.latlng_to_cell(42.34, -7.86, 8)
    neighbour = next(n for n in h3.grid_disk(c, 1) if n != c)
    far = next(n for n in h3.grid_disk(c, 3) if h3.grid_distance(c, n) == 3)
    d0 = _day("2025-08-01")
    roots = cluster({d0: {c}, d0 + 2: {neighbour}, d0 + 5: {neighbour}, d0 + 6: {far}}).final
    assert roots[(d0 + 2, neighbour)] == roots[(d0, c)] == (d0, c)                 # 2 days later, neighbour: same
    assert roots[(d0 + 5, neighbour)] == (d0 + 5, neighbour)                       # 3 days after the last point: new
    assert roots[(d0 + 6, far)] == (d0 + 6, far)                                   # 3 cells away: new
    chain = cluster({d0: {c}, d0 + 1: {neighbour}, d0 + 2: {next(n for n in h3.grid_disk(neighbour, 1) if h3.grid_distance(c, n) == 2)}})
    assert len(set(chain.final.values())) == 1                                     # transitive
    # two fires 2 cells apart grow together on day 2: merged, the older keeps the id, the merge is remembered
    left, right = c, next(n for n in h3.grid_disk(c, 2) if h3.grid_distance(c, n) == 2)
    middle = next(n for n in h3.grid_disk(c, 1) if h3.grid_distance(n, right) == 1)
    merged = cluster({d0: {left}, d0 + 1: {right}, d0 + 2: {middle}})
    assert set(merged.final.values()) == {(d0, left)} and merged.merges == [(d0 + 2, (d0, left))]
    assert merged.own_day[(d0 + 1, right)] == (d0 + 1, right)                      # on its own day still separate
    assert event_id((d0, c)) == event_id((d0, c)) and event_id((d0, c)).startswith("e_") and len(event_id((d0, c))) == 14


def test_events_are_connected_and_complete(hot):
    """Independent check with pandas on the real data: an event is exactly one connected group of points."""
    top = post("/api/events", {"date": D, "lookback_days": 7, "limit": 3})["features"]
    pts = hot[hot["in_series_n"] & hot["confidence_class"].isin(["nominal", "high"])]
    for f in top:
        ids = {p["id"] for p in post("/api/hotspots", {"start": D, "end": D, "event_id": f["id"], "limit": 20000})["features"]}
        start, last = pd.Timestamp(f["properties"]["start"]).date(), pd.Timestamp(D).date()
        near = pts[(pts["obs_date"] >= start - pd.Timedelta(days=2)) & (pts["obs_date"] <= last)]    # as of D = last
        nodes = {(d.toordinal(), c) for d, c in zip(near["obs_date"], near["h3_cell"])}
        member = near["hotspot_id"].map(lambda h: int(h[:13], 16) in ids)
        inside = {(d.toordinal(), c) for d, c in zip(near["obs_date"][member], near["h3_cell"][member])}
        assert len(ids) == f["properties"]["hotspots"] == member.sum()
        def touching(node):
            day, cell = node
            return {(day + k, n) for k in range(-2, 3) for n in h3.grid_disk(cell, 1)} & nodes
        # complete: nothing outside the event touches it; connected: walking from the start reaches all of it
        assert all(touching(n) <= inside for n in inside)
        seen, todo = set(), [min(inside)]
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo.extend(touching(n) & inside)
        assert seen == inside


def test_event_values_as_of_d():
    first = post("/api/events", {"date": D, "lookback_days": 7, "limit": 1})["features"][0]
    p = first["properties"]
    assert p["duration_days"] == (pd.Timestamp(p["last_seen"]) - pd.Timestamp(p["start"])).days + 1
    detail = client.get(f"/api/events/{first['id']}", params={"date": D}).json()
    assert len(detail["daily"]) == p["duration_days"] and sum(x["hotspots"] for x in detail["daily"]) == p["hotspots"]
    assert sum(x["new_cells"] for x in detail["daily"]) == p["cells"]
    points = post("/api/hotspots", {"start": D, "end": D, "event_id": first["id"], "limit": 20000})["features"]
    assert sum(x["properties"]["weight"] for x in points) == pytest.approx(p["fires"], abs=0.05 * len(points) ** 0.5 + 0.1)
    # one day earlier the event knows nothing of day D
    earlier = (pd.Timestamp(D) - pd.Timedelta(days=1)).date().isoformat()
    if p["start"] < D:
        before = client.get(f"/api/events/{first['id']}", params={"date": earlier}).json()["properties"]
        on_d = sum(x["hotspots"] for x in detail["daily"] if x["date"] == D)
        # less if other fires only grew into it on D: the day before they were still events of their own
        assert before["hotspots"] <= p["hotspots"] - on_d and before["last_seen"] <= earlier
    assert client.get(f"/api/events/{first['id']}", params={"date": "2001-01-01"}).json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_events_list_rules():
    body = {"date": D, "lookback_days": 14, "region_id": "ES11"}
    r = post("/api/events", body)
    assert r["total"] == r["returned"] and all(
        D >= f["properties"]["last_seen"] >= (pd.Timestamp(D) - pd.Timedelta(days=13)).date().isoformat() for f in r["features"])
    frp = [f["properties"]["frp_sum"] for f in r["features"]]
    assert frp == sorted(frp, reverse=True)                                        # default sort: strength
    longest = post("/api/events", {**body, "sort": "duration_days"})["features"]
    assert [f["properties"]["duration_days"] for f in longest] == sorted((f["properties"]["duration_days"] for f in longest), reverse=True)
    assert r["summary"]["active"] == sum(f["properties"]["active"] for f in r["features"])
    high = post("/api/events", {**body, "min_confidence": "high"})
    assert high["total"] <= r["total"] and {f["id"] for f in high["features"]} <= {f["id"] for f in r["features"]}
    one = post("/api/events", {**body, "limit": 1})
    assert one["returned"] == 1 and one["truncated"] == (r["total"] > 1) and one["summary"] == r["summary"]


def test_daily_event_counts_match_hotspots():
    """events_active on a day = number of different events among the hotspots of that day in the area."""
    daily = post("/api/daily", {"region_id": "PT16"})
    i = (pd.Timestamp(D) - pd.Timestamp(daily["start"])).days
    points = post("/api/hotspots", {"start": D, "end": D, "region_id": "PT16", "limit": 20000})["features"]
    assert daily["events_active"][i] == len({p["properties"]["event_id"] for p in points})
    starting = [e for e in post("/api/events", {"date": D, "lookback_days": 1, "region_id": "PT16"})["features"]
                if e["properties"]["new"]]
    assert daily["events_new"][i] == len(starting)
    assert len(daily["events_active"]) == len(daily["fires"])


def test_export_of_one_event():
    first = post("/api/events", {"date": D, "lookback_days": 7, "limit": 1})["features"][0]
    r = client.get("/api/export.csv", params={"event_id": first["id"], "end": D})
    lines = r.text.strip().split("\n")[1:]
    assert len(lines) == first["properties"]["hotspots"] and all(line.endswith("," + first["id"]) for line in lines)


def test_by_region_shares_add_up(hot):
    r = post("/api/by-region", {**WINDOW, "level": "region"})
    assert sum(x["share"] for x in r["data"]) == pytest.approx(1, abs=0.001)
    exp = nominal(hot[(hot["obs_date"] >= pd.Timestamp(WINDOW["start"]).date()) & (hot["obs_date"] <= pd.Timestamp(WINDOW["end"]).date())])
    assert sum(x["hotspots"] for x in r["data"]) == exp["in_series_n"].sum()


# ------------------------------------------------------------------ errors
@pytest.mark.parametrize("path,body,status,code", [
    ("/api/daily", {"region_id": "XX99"}, 404, "REGION_NOT_FOUND"),
    ("/api/daily", {"region_id": "FRI1"}, 404, "REGION_NOT_FOUND"),            # French region is not part of the API
    ("/api/daily", {"area_id": "a_7f3c9e2b41d0"}, 404, "AREA_NOT_FOUND"),
    ("/api/areas", {"geometry": {"type": "Polygon", "coordinates": [[[-14, 40], [-13, 40], [-13, 41], [-14, 40]]]}},
     400, "AREA_OUTSIDE_REGION"),                                                  # Atlantic only
    ("/api/areas", {"geometry": {"type": "Polygon", "coordinates": [[[-8, 42], [-7, 42], [-8, 42]]]}},
     400, "GEOMETRY_INVALID"),                                                     # no area at all
    ("/api/daily", {"region_id": "ES11", "area_id": "a_7f3c9e2b41d0"}, 400, "AREA_CONFLICT"),
    ("/api/hotspots", {"start": "2025-08-14", "end": "2025-08-01"}, 400, "INVALID_DATE_RANGE"),
    ("/api/hotspots", {**WINDOW, "limit": 99999}, 400, "LIMIT_TOO_HIGH"),
    ("/api/grid", {**WINDOW, "resolution": 9}, 400, "RESOLUTION_OUT_OF_RANGE"),
    ("/api/grid", {**WINDOW, "resolution": 6, "mode": "anomaly"}, 400, "RESOLUTION_OUT_OF_RANGE"),
    ("/api/events", {"date": "2025-08-14", "lookback_days": 61}, 400, "INVALID_DATE_RANGE"),
    ("/api/hotspots", {**WINDOW, "event_id": "e_000000000000"}, 404, "EVENT_NOT_FOUND"),
    ("/api/by-region", {**WINDOW, "level": "province"}, 501, "NOT_IMPLEMENTED"),
])
def test_errors(path, body, status, code):
    r = post(path, body, status)
    assert r["error"]["code"] == code and r["error"]["message"]
