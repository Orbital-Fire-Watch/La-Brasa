"""Day-of-year climatology per region (rebuilt here, no import from harmonisation/aggregation)."""
from __future__ import annotations

import numpy as np
import pandas as pd

N_DOY = 365


def day_of_year_noleap(dates: pd.Series) -> np.ndarray:
    """Day of year 1..365; 29 February counts as 28 February, later days of leap years shift back by one."""
    dates = pd.to_datetime(dates)
    doy = dates.dt.day_of_year.to_numpy()
    leap = dates.dt.is_leap_year.to_numpy()
    return np.where(leap & (doy > 59), doy - 1, doy).astype(int)


def smooth_circular(values: np.ndarray, window_days: int) -> np.ndarray:
    """Moving mean of +-window_days over a circular year (rows = regions, columns = 365 days)."""
    if window_days <= 0:
        return values.copy()
    k = np.ones(2 * window_days + 1) / (2 * window_days + 1)
    return np.array([np.convolve(np.r_[r[-window_days:], r, r[:window_days]], k, mode="valid") for r in values])


def smooth_gauss_circular(values: np.ndarray, sigma_days: float) -> np.ndarray:
    """Gaussian kernel smoothing over a circular year (rows = regions, columns = 365 days)."""
    if sigma_days <= 0:
        return values.copy()
    half = int(np.ceil(4 * sigma_days))
    x = np.arange(-half, half + 1)
    k = np.exp(-0.5 * (x / sigma_days) ** 2)
    k /= k.sum()
    reps = int(np.ceil(half / N_DOY)) + 1
    out = []
    for r in values:
        ext = np.tile(r, 2 * reps + 1)
        sm = np.convolve(ext, k, mode="same")
        out.append(sm[reps * N_DOY:(reps + 1) * N_DOY])
    return np.array(out)


def doy_climatology_shrunk(region: pd.Series, doy: np.ndarray, values: pd.Series, mask: np.ndarray,
                           sigma_days: float, prior_sigma_days: float, shrink_days: float,
                           clip: float | None = 1e-4) -> pd.DataFrame:
    """Kernel climatology with shrinkage (empirical Bayes), for targets with few events.

    S(d), N(d): sum of the target and number of observed days per region and day of year, both smoothed with a
    circular Gaussian kernel (sd sigma_days). The prior P(d) is the same with a wide kernel (prior_sigma_days).
    c(d) = (S(d) + m P(d)) / (N(d) + m) with m = shrink_days pseudo-days: where few days are observed, c is pulled to
    the wide seasonal rate; a single event no longer makes a 15-day block with a hard edge."""
    df = pd.DataFrame({"region": np.asarray(region), "doy": np.asarray(doy), "v": np.asarray(values, dtype=float)})
    df = df[np.asarray(mask) & df["v"].notna().to_numpy()]
    g = df.groupby(["region", "doy"])["v"]
    S = g.sum().unstack().reindex(columns=range(1, N_DOY + 1)).fillna(0.0)
    N = g.count().unstack().reindex(index=S.index, columns=range(1, N_DOY + 1)).fillna(0.0)
    s, n = smooth_gauss_circular(S.to_numpy(), sigma_days), smooth_gauss_circular(N.to_numpy(), sigma_days)
    sp, npr = smooth_gauss_circular(S.to_numpy(), prior_sigma_days), smooth_gauss_circular(N.to_numpy(), prior_sigma_days)
    prior = np.where(npr > 0, sp / np.maximum(npr, 1e-12), 0.0)
    c = (s + shrink_days * prior) / np.maximum(n + shrink_days, 1e-12)
    if clip is not None:
        c = np.clip(c, clip, 1 - clip)
    return pd.DataFrame(c, index=S.index, columns=S.columns)


def doy_climatology(region: pd.Series, doy: np.ndarray, values: pd.Series, mask: np.ndarray,
                    window_days: int, clip: float | None = 1e-4) -> pd.DataFrame:
    """Mean of `values` per region x day of year over rows where `mask` is true, circularly smoothed.

    Days of year without data take the region mean. With `clip`, values are bounded to [clip, 1 - clip]
    (for probabilities). Returns a DataFrame indexed by region with columns 1..365.
    """
    df = pd.DataFrame({"region": np.asarray(region), "doy": np.asarray(doy), "v": np.asarray(values, dtype=float)})
    df = df[np.asarray(mask) & df["v"].notna().to_numpy()]
    t = df.groupby(["region", "doy"])["v"].mean().unstack().reindex(columns=range(1, N_DOY + 1))
    t = t.apply(lambda r: r.fillna(r.mean()), axis=1)
    sm = smooth_circular(t.to_numpy(), window_days)
    if clip is not None:
        sm = np.clip(sm, clip, 1 - clip)
    return pd.DataFrame(sm, index=t.index, columns=t.columns)


def lookup(table: pd.DataFrame, region: pd.Series, doy: np.ndarray) -> np.ndarray:
    """Values of a climatology table for each (region, doy) pair; unknown regions give NaN."""
    r_idx = pd.Index(table.index).get_indexer(np.asarray(region))
    out = np.full(len(r_idx), np.nan)
    ok = r_idx >= 0
    out[ok] = table.to_numpy()[r_idx[ok], np.asarray(doy)[ok] - 1]
    return out
