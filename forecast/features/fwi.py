"""Canadian Forest Fire Weather Index (FWI) System, daily, vectorised over points.

Equations: Van Wagner (1987), Development and structure of the Canadian Forest Fire Weather Index System,
For. Tech. Rep. 35; Van Wagner & Pickett (1985), For. Tech. Rep. 33; as implemented in the cffdrs package of
the Canadian Forest Service (Wang et al. 2015/2017). Checked against the published test table (KPI A7,
tests/test_fwi.py).

Inputs per day: temperature (°C), relative humidity (%), wind speed (km/h) at local noon and the precipitation
of the previous 24 h (mm). Our weather is at 12:00 UTC, i.e. 12-13 h local time in Iberia.

The three moisture codes carry memory from day to day:
  FFMC  fine fuel moisture code   (litter, hours to days)
  DMC   duff moisture code        (loose organic layer, weeks)
  DC    drought code              (deep compact organic layer, months)
From them: ISI (initial spread index, FFMC + wind), BUI (buildup index, DMC + DC), FWI (ISI + BUI).

Day-length factors: standard table for 30-60 °N (all regions are at 36-44 °N).
The calculation runs all year without overwintering (snow cover is rare where fires burn in Iberia; EFFIS also
computes FWI continuously). Start values FFMC 85, DMC 6, DC 15 on the first day; in a winter start the codes
reach their weather-driven values within a few weeks (DC within a few months).
"""
from __future__ import annotations

import numpy as np

FFMC0, DMC0, DC0 = 85.0, 6.0, 15.0
# 250 * 59.5 / 101 = 147.277 (Van Wagner & Pickett 1985, cffdrs); the rounded 147.2 of Van Wagner 1987 is off by up to 0.25
FFMC_COEF = 250.0 * 59.5 / 101.0
# effective day length for DMC (Le) and day-length adjustment for DC (Lf), by month, 30-60 °N
DMC_DAY_LENGTH = np.array([6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0])
DC_DAY_LENGTH = np.array([-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6])
COMPONENTS = ["ffmc", "dmc", "dc", "isi", "bui", "fwi"]


def ffmc_step(ffmc0, t, rh, wind, rain):
    """Fine fuel moisture code of today from yesterday's FFMC and today's noon weather."""
    rh = np.clip(rh, 0.0, 100.0)
    mo = FFMC_COEF * (101.0 - ffmc0) / (59.5 + ffmc0)
    rf = rain - 0.5
    wet = rain > 0.5
    with np.errstate(divide="ignore", invalid="ignore"):
        rf_ = np.where(wet, rf, 1.0)
        add = 42.5 * rf_ * np.exp(-100.0 / (251.0 - mo)) * (1.0 - np.exp(-6.93 / rf_))
        add = np.where(mo > 150.0, add + 0.0015 * (mo - 150.0) ** 2 * np.sqrt(rf_), add)
    mo = np.where(wet, np.minimum(mo + add, 250.0), mo)
    ed = 0.942 * rh ** 0.679 + 11.0 * np.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * rh))
    ew = 0.618 * rh ** 0.753 + 10.0 * np.exp((rh - 100.0) / 10.0) + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * rh))
    ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * np.sqrt(wind) * (1.0 - (rh / 100.0) ** 8)
    kd = ko * 0.581 * np.exp(0.0365 * t)
    k1 = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * np.sqrt(wind) * (1.0 - ((100.0 - rh) / 100.0) ** 8)
    kw = k1 * 0.581 * np.exp(0.0365 * t)
    m = np.where(mo > ed, ed + (mo - ed) * 10.0 ** (-kd),
                 np.where(mo < ew, ew - (ew - mo) * 10.0 ** (-kw), mo))
    return np.clip(59.5 * (250.0 - m) / (FFMC_COEF + m), 0.0, 101.0)


def dmc_step(dmc0, t, rh, rain, month):
    """Duff moisture code. month 1-12 (array or scalar)."""
    rh = np.clip(rh, 0.0, 100.0)
    t = np.maximum(t, -1.1)
    le = DMC_DAY_LENGTH[np.asarray(month) - 1]
    rk = 1.894 * (t + 1.1) * (100.0 - rh) * le * 1e-4
    wet = rain > 1.5
    re = 0.92 * rain - 1.27
    mo = 20.0 + 280.0 / np.exp(0.023 * dmc0)           # as in the FORTRAN program / cffdrs
    with np.errstate(divide="ignore", invalid="ignore"):
        b = np.where(dmc0 <= 33.0, 100.0 / (0.5 + 0.3 * dmc0),
                     np.where(dmc0 <= 65.0, 14.0 - 1.3 * np.log(np.maximum(dmc0, 1e-9)),
                              6.2 * np.log(np.maximum(dmc0, 1e-9)) - 17.2))
        mr = mo + 1000.0 * re / (48.77 + b * re)
        pr = np.maximum(43.43 * (5.6348 - np.log(np.maximum(mr - 20.0, 1e-9))), 0.0)
    pr = np.where(wet, pr, dmc0)
    return np.maximum(pr + rk, 0.0)


def dc_step(dc0, t, rain, month):
    """Drought code. month 1-12."""
    t = np.maximum(t, -2.8)
    lf = DC_DAY_LENGTH[np.asarray(month) - 1]
    pe = np.maximum((0.36 * (t + 2.8) + lf) / 2.0, 0.0)
    wet = rain > 2.8
    rd = 0.83 * rain - 1.27
    qo = 800.0 * np.exp(-dc0 / 400.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        qr = qo + 3.937 * rd
        dr = np.maximum(400.0 * np.log(800.0 / qr), 0.0)
    dr = np.where(wet, dr, dc0)
    return np.maximum(dr + pe, 0.0)


def isi(ffmc, wind):
    m = FFMC_COEF * (101.0 - ffmc) / (59.5 + ffmc)
    ff = 91.9 * np.exp(-0.1386 * m) * (1.0 + m ** 5.31 / 4.93e7)
    return 0.208 * np.exp(0.05039 * wind) * ff


def bui(dmc, dc):
    dmc, dc = np.asarray(dmc, float), np.asarray(dc, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        low = 0.8 * dmc * dc / (dmc + 0.4 * dc)
        high = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) * (0.92 + (0.0114 * dmc) ** 1.7)
    out = np.where(dmc <= 0.4 * dc, low, high)
    return np.where((dmc == 0) & (dc == 0), 0.0, np.maximum(np.nan_to_num(out), 0.0))


def fwi(isi_, bui_):
    fd = np.where(bui_ <= 80.0, 0.626 * bui_ ** 0.809 + 2.0, 1000.0 / (25.0 + 108.64 * np.exp(-0.023 * bui_)))
    b = 0.1 * isi_ * fd
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.exp(2.72 * (0.434 * np.log(np.maximum(b, 1e-12))) ** 0.647)
    return np.where(b > 1.0, s, b)


def fwi_series(t: np.ndarray, rh: np.ndarray, wind: np.ndarray, rain: np.ndarray, month: np.ndarray,
               start: tuple[float, float, float] = (FFMC0, DMC0, DC0)) -> dict[str, np.ndarray]:
    """All six components for consecutive days.

    t, rh, wind, rain: arrays (n_days, n_points); month: (n_days,). Days must be consecutive and gap-free.
    A missing input on a day keeps yesterday's codes (no drying, no wetting) and gives NaN indices that day.
    """
    t, rh, wind, rain = (np.atleast_2d(np.asarray(a, float).T).T for a in (t, rh, wind, rain))
    n_days, n_pts = t.shape
    out = {c: np.full((n_days, n_pts), np.nan) for c in COMPONENTS}
    f, p, d = (np.full(n_pts, v, dtype=float) for v in start)
    for i in range(n_days):
        ok = ~(np.isnan(t[i]) | np.isnan(rh[i]) | np.isnan(wind[i]) | np.isnan(rain[i]))
        ti, hi, wi, ri = (np.where(ok, a[i], 0.0) for a in (t, rh, wind, rain))
        f = np.where(ok, ffmc_step(f, ti, hi, wi, ri), f)
        p = np.where(ok, dmc_step(p, ti, hi, ri, month[i]), p)
        d = np.where(ok, dc_step(d, ti, ri, month[i]), d)
        s, b = isi(f, wi), bui(p, d)
        for name, val in (("ffmc", f), ("dmc", p), ("dc", d), ("isi", s), ("bui", b), ("fwi", fwi(s, b))):
            out[name][i] = np.where(ok, val, np.nan)
    return out
