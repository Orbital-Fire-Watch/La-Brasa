"""Plan of the daily job (daily.py): which weather is requested on which day."""
from datetime import date
from pathlib import Path

from daily import forecast_file_date, make_plan


def test_recent_fills_gap_after_history_up_to_yesterday():
    p = make_plan(date(2026, 11, 15), {"core": date(2026, 11, 8), "fire": date(2026, 11, 13)}, date(2026, 11, 22), True)
    assert p.fetch and p.forecast_from == "2026-11-15"
    assert p.recent == {"core": ["2026-11-09", "2026-11-14"], "fire": ["2026-11-14", "2026-11-14"]}


def test_no_recent_when_history_reaches_yesterday():
    p = make_plan(date(2026, 11, 14), {"core": date(2026, 11, 13), "fire": date(2026, 11, 13)}, None, True)
    assert p.fetch and p.recent == {}


def test_no_requests_after_the_account_ended():
    p = make_plan(date(2026, 11, 23), {"core": date(2026, 11, 8), "fire": date(2026, 11, 13)}, date(2026, 11, 22), True)
    assert not p.fetch and "ended" in p.reason
    p = make_plan(date(2026, 11, 22), {"core": date(2026, 11, 8), "fire": date(2026, 11, 13)}, date(2026, 11, 22), True)
    assert p.fetch                                     # the last valid day still fetches


def test_no_requests_without_history_or_with_no_fetch():
    assert not make_plan(date(2026, 11, 15), {"core": None, "fire": date(2026, 11, 13)}, None, True).fetch
    assert not make_plan(date(2026, 11, 15), {"core": date(2026, 11, 8)}, None, False).fetch


def test_forecast_file_date_from_name():
    assert forecast_file_date(Path("weather_points_forecast_core_2026-11-14.parquet")) == date(2026, 11, 14)
