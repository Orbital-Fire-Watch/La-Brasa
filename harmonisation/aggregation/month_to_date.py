"""Laufender Monat gegen die Historie: Vergleich fuer denselben Zeitraum (Tag 1 bis heute)."""
from __future__ import annotations

import numpy as np
import pandas as pd

VALUE_COLUMNS = ["n_harm", "frp_harm"]


def last_complete_day(daily: pd.DataFrame, today: pd.Timestamp) -> pd.Timestamp | None:
    """Letzter Tag bis `today`, der einen harmonisierten Wert hat."""
    days = daily.drop_duplicates("date")
    usable = days[(pd.to_datetime(days["date"]) <= today) & days["basis_count"].ne("none") & days["basis_frp"].ne("none")]
    return None if usable.empty else pd.to_datetime(usable["date"]).max()


def sum_month_to_day(daily: pd.DataFrame, month: int, last_day: int) -> pd.DataFrame:
    """Summen je Region und Jahr fuer Tag 1 bis `last_day` eines Kalendermonats, nur wenn alle Tage vollstaendig sind."""
    dates = pd.to_datetime(daily["date"])
    rows = daily[(dates.dt.month == month) & (dates.dt.day <= last_day)].assign(year=dates.dt.year)
    complete = rows["basis_count"].ne("none") & rows["basis_frp"].ne("none")
    measured = rows["basis_count"].eq("viirs_measured")
    grouped = rows.assign(_complete=complete, _measured=measured).groupby(["region_id", "year"])
    sums = grouped[VALUE_COLUMNS].sum(min_count=1).join(grouped.agg(n_days=("_complete", "sum"), n_measured=("_measured", "sum")))
    return sums[sums["n_days"] == last_day].reset_index()


def month_to_date_vs_history(daily: pd.DataFrame, today: str | pd.Timestamp) -> pd.DataFrame:
    """Vergleicht den laufenden Monat bis heute mit denselben Tagen frueherer Jahre.

    Warum nicht einfach gegen den Monatsmedian: Ein Monat, der erst zur Haelfte vorbei ist, liegt
    immer unter dem Median ganzer Monate. Hochrechnen auf den vollen Monat waere auch falsch,
    weil sich Feuer nicht gleichmaessig ueber den Monat verteilen. Verglichen wird deshalb Gleiches
    mit Gleichem: die Summe von Tag 1 bis zum letzten vollstaendigen Tag, in diesem Jahr und in
    jedem frueheren Jahr.
    Rueckgabe je Region: aktueller Wert, historischer Median, Verhaeltnis dazu, Rang als Perzentil
    (0 = ruhigster, 100 = aktivster Zeitraum), Zahl der Vergleichsjahre und wie viele davon
    gemessen sind. `as_of` ist der letzte Tag, der wirklich eingeht. Er kann vor `today` liegen,
    wenn die Daten noch nicht so weit reichen.
    """
    as_of = last_complete_day(daily, pd.Timestamp(today))
    if as_of is None or (as_of.year, as_of.month) != (pd.Timestamp(today).year, pd.Timestamp(today).month):
        return pd.DataFrame(columns=["region_id", "as_of", "days_counted"])
    sums = sum_month_to_day(daily, as_of.month, as_of.day)
    current = sums[sums["year"] == as_of.year].set_index("region_id")
    history = sums[sums["year"] < as_of.year]
    result = pd.DataFrame({"as_of": as_of, "days_counted": as_of.day}, index=current.index)
    for column in VALUE_COLUMNS:
        past = history.groupby("region_id")[column]
        median = past.median().reindex(current.index)
        rank = history.merge(current[[column]].rename(columns={column: "now"}), left_on="region_id", right_index=True)
        percentile = (rank[column] <= rank["now"]).groupby(rank["region_id"]).mean().reindex(current.index) * 100
        result[f"{column}_current"], result[f"{column}_history_median"] = current[column], median
        result[f"{column}_ratio_to_median"] = current[column] / median.replace(0, np.nan)
        result[f"{column}_percentile"] = percentile
    counts = history.groupby("region_id").agg(n_history_years=("year", "size"), n_history_years_measured=("n_measured", lambda v: int((v > 0).sum())))
    return result.join(counts).reset_index()
