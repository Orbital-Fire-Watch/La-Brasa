"""Offline tests for points selection and the Meteomatics client (no network)."""
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from features.meteomatics import (MeteomaticsAuthError, MeteomaticsClient, credentials, day_chunks,
                                  load_env_file, parse_csv)
from features.points import aggregate_to_regions, cell_centre, select_points


# --- points ---------------------------------------------------------------------------------
def test_cell_centre():
    c = cell_centre(pd.Series(["157_-18", "0_0"]))
    assert c.loc[0, "lat"] == pytest.approx(39.375)
    assert c.loc[0, "lon"] == pytest.approx(-4.375)
    assert c.loc[1, "lat"] == pytest.approx(0.125)


def _hotspots():
    rows = []
    for cell, n in [("160_-30", 6), ("161_-30", 3), ("162_-30", 1)]:
        rows += [dict(cell_id=cell, region_id="PT11", sensor="VIIRS", obs_date=date(2015, 8, 1))] * n
    rows += [dict(cell_id="163_-30", region_id="PT11", sensor="VIIRS", obs_date=date(2023, 8, 1))] * 50  # test years
    rows += [dict(cell_id="164_-30", region_id="PT11", sensor="MODIS", obs_date=date(2015, 8, 1))] * 50  # wrong sensor
    rows += [dict(cell_id="150_-10", region_id=None, sensor="VIIRS", obs_date=date(2015, 8, 1))] * 5  # sea
    return pd.DataFrame(rows)


def test_select_points_uses_training_viirs_only_and_weights_sum_to_one():
    p = select_points(_hotspots(), "2012-01-20", "2021-12-31", max_cells_per_region=2)
    assert p["cell_id"].tolist() == ["160_-30", "161_-30"]
    assert p["weight"].tolist() == pytest.approx([6 / 9, 3 / 9])
    assert p.groupby("region_id")["weight"].sum().tolist() == pytest.approx([1.0])


def test_aggregate_to_regions_weighted_and_renormalised():
    points = pd.DataFrame({"region_id": ["R", "R"], "lat": [40.125, 40.375], "lon": [-7.125, -7.125],
                           "weight": [0.75, 0.25]})
    t = pd.Timestamp("2020-07-01T12:00Z")
    pw = pd.DataFrame({"lat": [40.125, 40.375], "lon": [-7.125, -7.125], "validdate": [t, t],
                       "a": [10.0, 20.0], "b": [None, 4.0]})
    out = aggregate_to_regions(pw, points, ["a", "b"])
    assert out.loc[0, "a"] == pytest.approx(12.5)
    assert out.loc[0, "b"] == pytest.approx(4.0)


# --- client helpers -------------------------------------------------------------------------
def test_day_chunks_cover_range_without_overlap():
    ch = day_chunks(date(2020, 1, 1), date(2021, 1, 10), 366)
    assert ch == [(date(2020, 1, 1), date(2020, 12, 31)), (date(2021, 1, 1), date(2021, 1, 10))]


def test_parse_csv_multi_and_single_point():
    multi = "lat;lon;validdate;t_2m:C\n40.1;-7.1;2020-07-01T12:00:00Z;30.5\n40.2;-7.1;2020-07-01T12:00:00Z;-666\n"
    df = parse_csv(multi, [(40.1, -7.1), (40.2, -7.1)])
    assert list(df.columns) == ["lat", "lon", "validdate", "t_2m:C"]
    assert pd.isna(df.loc[1, "t_2m:C"])  # -666 placeholder -> missing
    single = "validdate;t_2m:C\n2020-07-01T12:00:00Z;30.5\n"
    df1 = parse_csv(single, [(40.1, -7.1)])
    assert df1.loc[0, "lat"] == 40.1 and df1.loc[0, "t_2m:C"] == 30.5


def test_env_file_and_missing_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("METEOMATICS_USERNAME", raising=False)
    monkeypatch.delenv("METEOMATICS_PASSWORD", raising=False)
    env = tmp_path / ".env"
    env.write_text("# c\nMETEOMATICS_USERNAME=u\nMETEOMATICS_PASSWORD='p'\n")
    assert load_env_file(env)["METEOMATICS_PASSWORD"] == "p"
    assert credentials(env) == ("u", "p")
    with pytest.raises(MeteomaticsAuthError):
        credentials(tmp_path / "missing.env")


class FakeResponse:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls, self.auth = list(responses), [], None

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def _client(tmp_path, responses):
    s = FakeSession(responses)
    c = MeteomaticsClient("user", "secret", cache_dir=tmp_path, session=s, pause_between_requests_s=0,
                          max_retries=1, max_points_per_request=2)
    return c, s


def test_url_has_no_credentials_and_cache_is_used(tmp_path):
    csv = "lat;lon;validdate;t_2m:C\n40.0;-7.0;2020-07-01T12:00:00Z;30\n41.0;-7.0;2020-07-01T12:00:00Z;31\n"
    c, s = _client(tmp_path, [FakeResponse(200, csv)])
    t = datetime(2020, 7, 1, 12, tzinfo=timezone.utc)
    df = c.fetch_once(t, t, "P1D", ["t_2m:C"], [(40.0, -7.0), (41.0, -7.0)])
    url, params = s.calls[0]
    assert url == "https://api.meteomatics.com/2020-07-01T12:00:00Z--2020-07-01T12:00:00Z:P1D/t_2m:C/40.0000,-7.0000+41.0000,-7.0000/csv"
    assert "secret" not in url and params == {"model": "mix"}
    assert s.auth == ("user", "secret")
    df2 = c.fetch_once(t, t, "P1D", ["t_2m:C"], [(40.0, -7.0), (41.0, -7.0)])  # from cache
    assert len(s.calls) == 1 and df2.equals(df)


def test_daily_series_splits_points(tmp_path):
    def csv(lat):
        return f"lat;lon;validdate;t_2m:C\n{lat};-7.0;2020-07-01T12:00:00Z;30\n{lat + 1};-7.0;2020-07-01T12:00:00Z;31\n"
    c, s = _client(tmp_path, [FakeResponse(200, csv(40.0)), FakeResponse(200, "validdate;t_2m:C\n2020-07-01T12:00:00Z;29\n")])
    df = c.daily_series(date(2020, 7, 1), date(2020, 7, 1), ["t_2m:C"], [(40.0, -7.0), (41.0, -7.0), (42.0, -7.0)])
    assert len(s.calls) == 2 and len(df) == 3


def test_auth_error_is_raised_without_retry(tmp_path):
    c, s = _client(tmp_path, [FakeResponse(401, "unauthorized")])
    t = datetime(2020, 7, 1, 12, tzinfo=timezone.utc)
    with pytest.raises(MeteomaticsAuthError):
        c.fetch_once(t, t, "P1D", ["t_2m:C"], [(40.0, -7.0)])
    assert len(s.calls) == 1
