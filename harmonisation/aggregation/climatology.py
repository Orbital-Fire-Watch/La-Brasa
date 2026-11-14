"""Klimaprofil: der typische Jahresverlauf der Feueraktivitaet je Region (Grundlage fuer den Kalender)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 365
LAST_FEBRUARY_DAY = 59        # 28. Februar im Jahr ohne Schalttag


def day_of_year_without_leap(dates: pd.Series) -> pd.Series:
    """Tag im Jahr von 1 bis 365. Der 29. Februar zaehlt zum 28., die Tage danach ruecken auf."""
    dates = pd.to_datetime(dates)
    after_february = dates.dt.is_leap_year & (dates.dt.day_of_year > LAST_FEBRUARY_DAY)
    return dates.dt.day_of_year - after_february.astype(int)


def smooth_circular(values: np.ndarray, window_days: int) -> np.ndarray:
    """Gleitendes Mittel ueber +-`window_days` Tage, das ueber den Jahreswechsel hinweg weiterlaeuft."""
    padded = np.concatenate([values[..., -window_days:], values, values[..., :window_days]], axis=-1)
    kernel = np.ones(2 * window_days + 1) / (2 * window_days + 1)
    return np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="valid"), -1, padded)


def complete_years(daily: pd.DataFrame, year_range: list[int], measured_only: bool) -> list[int]:
    """Kalenderjahre im Bereich, in denen jeder Tag einen Wert hat (optional: jeder Tag gemessen)."""
    days = daily.drop_duplicates("date")
    ok = days["basis_count"].ne("none") & days["basis_frp"].ne("none")
    if measured_only:
        ok &= days["basis_count"].eq("viirs_measured") & days["basis_frp"].eq("viirs_measured")
    per_year = ok.groupby(pd.to_datetime(days["date"]).dt.year).agg(["sum", "size"])
    full = per_year[(per_year["sum"] == per_year["size"]) & (per_year["size"] >= DAYS_PER_YEAR)].index
    return [int(year) for year in full if year_range[0] <= year <= year_range[1]]


def yearly_profiles(daily: pd.DataFrame, column: str, years: list[int], window_days: int) -> tuple[np.ndarray, list[str]]:
    """Wuerfel Region x Jahr x Tag im Jahr mit den geglaetteten Tageswerten einer Spalte."""
    rows = daily[pd.to_datetime(daily["date"]).dt.year.isin(years)]
    rows = rows.assign(year=pd.to_datetime(rows["date"]).dt.year, doy=day_of_year_without_leap(rows["date"]),
                       value=rows[column].astype(float))
    table = rows.pivot_table(index=["region_id", "year"], columns="doy", values="value", aggfunc="mean")
    regions = sorted(rows["region_id"].unique())
    cube = table.to_numpy().reshape(len(regions), len(years), DAYS_PER_YEAR)
    return smooth_circular(cube, window_days), regions


def build_day_of_year_climatology(daily: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Baut je Region und Tag im Jahr den typischen Verlauf: Mittel, Quantile und Wahrscheinlichkeiten.

    Vorgehen: Jedes Jahr wird einzeln ueber +-`window_days` Tage geglaettet (zirkulaer ueber den
    Jahreswechsel), danach wird ueber die Jahre gemittelt. Die Glaettung ist noetig, weil ein
    einzelner Kalendertag aus 25 Jahren nur 25 Werte hat und stark vom Zufall abhaengt. In der
    Voranalyse stimmte der aus MODIS umgerechnete Verlauf mit +-7 Tagen gut mit VIIRS ueberein
    (R^2 0,94), ohne Glaettung deutlich schlechter (0,75).

    Zwei Gruppen von Spalten:
    - `*_all`: Mittel und Quantile ueber alle vollstaendigen Jahre (harmonisiert, ab 2001).
    - `*_viirs`: nur aus vollstaendig gemessenen VIIRS-Jahren. Dazu gehoeren die
      Wahrscheinlichkeiten `p_fire_day_viirs` und `p_big_fire_day_viirs`. Sie kommen bewusst nur
      aus VIIRS: MODIS meldet an etwa 60 % der Tage mit VIIRS-Feuer nichts, eine aus umgerechneten
      Jahren gezaehlte Haeufigkeit waere deutlich zu niedrig.
    Nur vollstaendige Kalenderjahre gehen ein. Der 29. Februar zaehlt zum 28.
    """
    params = config["climatology"]
    years_all = complete_years(daily, params["all_years"], measured_only=False)
    years_viirs = complete_years(daily, params["viirs_years"], measured_only=True)
    window = params["window_days"]
    flags = daily.assign(fire_day=(daily["n_harm"] > 0).astype(float), big_day=daily["big_fire_day"].astype("Float64").astype(float))
    n_all, regions = yearly_profiles(flags, "n_harm", years_all, window)
    frp_all, _ = yearly_profiles(flags, "frp_harm", years_all, window)
    columns = {"mean_n_harm_all": n_all.mean(1), "mean_frp_harm_all": frp_all.mean(1)}
    for label, quantile in (("p25", 0.25), ("p50", 0.5), ("p75", 0.75), ("p90", 0.9)):
        columns[f"{label}_n_harm_all"] = np.quantile(n_all, quantile, axis=1)
    for name, source in (("mean_n_harm_viirs", "n_harm"), ("mean_frp_harm_viirs", "frp_harm"),
                         ("p_fire_day_viirs", "fire_day"), ("p_big_fire_day_viirs", "big_day")):
        columns[name] = yearly_profiles(flags, source, years_viirs, window)[0].mean(1)
    index = pd.MultiIndex.from_product([regions, range(1, DAYS_PER_YEAR + 1)], names=["region_id", "day_of_year"])
    result = pd.DataFrame({name: values.ravel() for name, values in columns.items()}, index=index).reset_index()
    return result.assign(n_years_all=len(years_all), n_years_viirs=len(years_viirs), window_days=window)
