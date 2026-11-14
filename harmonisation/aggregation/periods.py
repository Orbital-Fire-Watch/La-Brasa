"""Zeitschritte: Zuordnung eines Datums zu Woche, Monat, Quartal oder Jahr."""
from __future__ import annotations

import pandas as pd

GRAINS = ("day", "week", "month", "quarter", "year")
PERIOD_CODE = {"month": "M", "quarter": "Q", "year": "Y"}
DAYS_PER_WEEK = 7


def period_start_of(dates: pd.Series, grain: str) -> pd.Series:
    """Beginn des Zeitschritts eines Datums: der Tag selbst, Montag (ISO-Woche), Monats-, Quartals- oder Jahreserster."""
    dates = pd.to_datetime(dates)
    if grain == "day":
        return dates.dt.normalize()
    if grain == "week":
        return (dates - pd.to_timedelta(dates.dt.day_of_week, unit="D")).dt.normalize()
    if grain in PERIOD_CODE:
        return dates.dt.to_period(PERIOD_CODE[grain]).dt.start_time
    raise ValueError(f"Unbekannter Zeitschritt: {grain}")


def period_end_of(period_start: pd.Series, grain: str) -> pd.Series:
    """Letzter Kalendertag des Zeitschritts (nicht der letzte Tag mit Daten)."""
    period_start = pd.to_datetime(period_start)
    if grain == "day":
        return period_start
    if grain == "week":
        return period_start + pd.Timedelta(days=DAYS_PER_WEEK - 1)
    return period_start.dt.to_period(PERIOD_CODE[grain]).dt.end_time.dt.normalize()


def days_in_period(period_start: pd.Series, grain: str) -> pd.Series:
    """Zahl der Kalendertage eines Zeitschritts."""
    return (period_end_of(period_start, grain) - pd.to_datetime(period_start)).dt.days + 1
