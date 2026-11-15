"""Forecast endpoints against a Postgres that holds the forecast tables (pipeline/load_forecast_to_db.py).

    DATABASE_URL=postgresql://... pytest backend/tests/test_forecast.py -q

Expected values come from data/forecast/*.parquet with pandas, not from the SQL of the backend.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

FORECAST = Path(__file__).resolve().parents[2] / "data" / "forecast"
client = TestClient(app)


@pytest.fixture(scope="module")
def daily() -> pd.DataFrame:
    df = pd.read_parquet(FORECAST / "forecast_daily.parquet")
    return df[df["region_id"].str[:2].isin(["ES", "PT"])]


def test_daily_all_regions_es_pt_only(daily):
    r = client.get("/api/forecast/daily")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=3600"
    body = r.json()
    assert len(body["days"]) == len(daily) == 200
    assert {d["region_id"][:2] for d in body["days"]} == {"ES", "PT"}


def test_daily_region_equals_parquet(daily):
    days = client.get("/api/forecast/daily", params={"region_id": "PT11"}).json()["days"]
    assert [d["lead_days"] for d in days] == list(range(1, 11))
    exp = daily[daily["region_id"] == "PT11"].sort_values("lead_days")
    for col in ["p_big_fire_day", "p_big_fire_day_lo", "p_big_fire_day_hi", "p_clim_big_fire_day", "risk_ratio"]:
        assert max(abs(a[col] - b) for a, b in zip(days, exp[col], strict=True)) <= 1e-9
    assert [d["risk_class"] for d in days] == list(exp["risk_class"])
    assert all(d["p_big_fire_day_lo"] <= d["p_big_fire_day"] <= d["p_big_fire_day_hi"] for d in days)


def test_daily_target_date_and_errors(daily):
    issue = pd.Timestamp(daily["issue_date"].iloc[0]).date()
    day3 = (issue + pd.Timedelta(days=3)).isoformat()
    days = client.get("/api/forecast/daily", params={"target_date": day3}).json()["days"]
    assert len(days) == 20 and {d["lead_days"] for d in days} == {3}
    assert client.get("/api/forecast/daily", params={"region_id": "XX99"}).json()["error"]["code"] == "REGION_NOT_FOUND"
    assert client.get("/api/forecast/daily", params={"region_id": "FRI1"}).status_code == 404
    far = (issue + pd.Timedelta(days=11)).isoformat()
    assert client.get("/api/forecast/daily", params={"target_date": far}).json()["error"]["code"] == "INVALID_DATE_RANGE"


def test_status():
    s = client.get("/api/forecast/status").json()
    today = pd.Timestamp.now(tz="UTC").date()
    assert s["issue_date_age_days"] == (today - pd.Timestamp(s["issue_date"]).date()).days
    assert isinstance(s["warnings"], list)
