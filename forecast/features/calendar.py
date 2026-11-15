"""Public holidays in Spain, Portugal and France (national ones only), computed without extra packages.

Most fires in Iberia are started by people, and activity differs on days off. Regional holidays (e.g. Galicia,
Catalonia) are not included. Easter by the anonymous Gregorian algorithm (Meeus/Jones/Butcher).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

FIXED = {
    "ES": [(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)],
    "PT": [(1, 1), (4, 25), (5, 1), (6, 10), (8, 15), (10, 5), (11, 1), (12, 1), (12, 8), (12, 25)],
    "FR": [(1, 1), (5, 1), (5, 8), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)],
}
# days relative to Easter Sunday
MOVABLE = {"ES": [-2], "PT": [-2, 0, 60], "FR": [1, 39, 50]}


def easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def holidays(country: str, years: range) -> set[date]:
    out = set()
    for y in years:
        out.update(date(y, mo, dd) for mo, dd in FIXED[country])
        e = easter(y)
        out.update(e + timedelta(days=k) for k in MOVABLE[country])
    return out


def is_holiday(region_id: pd.Series, dates: pd.Series) -> np.ndarray:
    """1.0 where the date is a national public holiday of the region's country (first two letters of region_id)."""
    dates = pd.to_datetime(pd.Series(np.asarray(dates)))
    years = range(int(dates.dt.year.min()) - 1, int(dates.dt.year.max()) + 2)
    country = pd.Series(np.asarray(region_id)).str[:2]
    out = np.zeros(len(dates))
    for c in FIXED:
        sel = (country == c).to_numpy()
        if sel.any():
            hs = pd.to_datetime(sorted(holidays(c, years)))
            out[sel] = dates[sel].isin(hs).to_numpy().astype(float)
    return out
