"""Roll-up: aus dem Tagesdatensatz Woche, Monat, Quartal oder Jahr ableiten."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aggregation.periods import days_in_period, period_end_of, period_start_of
from aggregation.uncertainty import BASIS_MEASURED, classify_reliability, lookup_error_factors, uncertainty_bands

RAW_COLUMNS = ["n_aqua", "n_terra", "n_snpp", "frp_aqua", "frp_terra", "frp_snpp"]
ROLL_UP_COLUMNS = ["region_id", "grain", "period_start", "period_end", "n_days", "n_days_complete", "is_complete_period",
                   "share_measured_days", "basis_mix", "basis_count_converted", "basis_frp_converted", "n_harm", "frp_harm",
                   "n_harm_mean_per_day", "frp_harm_mean_per_day", "n_big_fire_days", "n_days_with_fire"] + RAW_COLUMNS
BASIS_NONE = "none"


def summarise_days(daily: pd.DataFrame, grain: str) -> pd.DataFrame:
    """Summiert die Tage je Region und Zeitschritt und zaehlt vollstaendige, gemessene und markierte Tage."""
    days = daily.assign(period_start=period_start_of(daily["date"], grain),
                        _complete=daily["basis_count"].ne(BASIS_NONE) & daily["basis_frp"].ne(BASIS_NONE),
                        _measured=daily["basis_count"].eq(BASIS_MEASURED) & daily["basis_frp"].eq(BASIS_MEASURED),
                        _fire=(daily["n_harm"] > 0), _big=daily["big_fire_day"].fillna(False).astype(bool))
    grouped = days.groupby(["region_id", "period_start"])
    sums = grouped[["n_harm", "frp_harm"] + RAW_COLUMNS].sum(min_count=1)
    counts = grouped.agg(n_days=("date", "size"), n_days_complete=("_complete", "sum"), n_days_measured=("_measured", "sum"),
                         n_days_with_fire=("_fire", "sum"), n_big_fire_days=("_big", "sum"))
    converted_basis = days[~days["_measured"] & days["_complete"]].groupby(["region_id", "period_start"]).agg(
        basis_count_converted=("basis_count", "first"), basis_frp_converted=("basis_frp", "first"))
    return sums.join(counts).join(converted_basis).reset_index()


def roll_up_daily(daily: pd.DataFrame, grain: str) -> pd.DataFrame:
    """Leitet aus dem Tagesdatensatz einen groeberen Zeitschritt ab (week, month, quarter, year).

    Addiert werden nur additive Groessen: `n_harm`, `frp_harm` und die Rohzahlen je Satellit.
    Weil der Umrechnungsfaktor ein Multiplikator je Region ist, ist die Summe der umgerechneten
    Tage exakt gleich der umgerechneten Summe. Der Monatswert haengt also nicht davon ab, ob vor
    oder nach dem Aufsummieren skaliert wurde.

    Regeln:
    - Ein Zeitschritt ist nur vollstaendig, wenn jeder seiner Kalendertage vorhanden ist und eine
      Basis hat. Ein unvollstaendiger Zeitschritt bekommt keinen Wert: Er waere zu niedrig und
      saehe wie ein ruhiger Zeitraum aus.
    - Gemischte Zeitschritte (Januar 2012: 19 umgerechnete und 12 gemessene Tage) werden normal
      summiert. `share_measured_days` und `basis_mix` (measured, converted, mixed) zeigen die
      Mischung, bei der Unsicherheit zaehlen sie vorsichtshalber als umgerechnet.
    - `n_days_with_fire` gibt es nur fuer vollstaendig gemessene Zeitschritte. Aus umgerechneten
      Tagen laesst sich die Zahl der Feuertage nicht ableiten, weil MODIS an etwa 60 % der Tage
      mit VIIRS-Feuer gar nichts meldet.
    - Mittel pro Tag = Summe / Zahl der Tage.
    """
    periods = summarise_days(daily, grain)
    periods["period_end"] = period_end_of(periods["period_start"], grain)
    periods["grain"] = grain
    expected_days = days_in_period(periods["period_start"], grain)
    periods["is_complete_period"] = (periods["n_days"] == expected_days) & (periods["n_days_complete"] == expected_days)
    periods["share_measured_days"] = periods["n_days_measured"] / expected_days
    periods["basis_mix"] = np.select([periods["share_measured_days"] >= 1.0, periods["n_days_measured"] == 0],
                                     ["measured", "converted"], default="mixed")
    incomplete = ~periods["is_complete_period"]
    periods.loc[incomplete, ["n_harm", "frp_harm"]] = np.nan
    periods["n_harm_mean_per_day"] = periods["n_harm"] / expected_days
    periods["frp_harm_mean_per_day"] = periods["frp_harm"] / expected_days
    fully_measured = periods["basis_mix"] == "measured"
    periods["n_days_with_fire"] = periods["n_days_with_fire"].where(fully_measured & ~incomplete).astype("Float64")
    periods["n_big_fire_days"] = periods["n_big_fire_days"].where(~incomplete).astype("Float64")
    return periods.sort_values(["region_id", "period_start"]).reset_index(drop=True)[ROLL_UP_COLUMNS]


def add_uncertainty_to_periods(periods: pd.DataFrame, quality: pd.DataFrame, config: dict[str, Any], area_scale: str = "nuts2") -> pd.DataFrame:
    """Ergaenzt die Fehlerbaender und die Zuverlaessigkeitsstufe fuer abgeleitete Zeitschritte.

    Die Unsicherheit laesst sich nicht aus den Tagen aufsummieren: Tagesfehler gleichen sich ueber
    laengere Zeitraeume teilweise aus (Tag etwa x 2, Monat x 1,5, Jahr x 1,1). Darum wird sie je
    Zeitschritt im Fehlermodell `quality_by_scale` nachgeschlagen, das aus der Kreuzvalidierung stammt.
    """
    result, grain = periods.copy(), periods["grain"].iloc[0]
    measured = (periods["basis_mix"] == "measured").to_numpy()
    min_units = config["uncertainty"]["min_units_per_class"]
    for quantity, value, basis_column in (("count", "n_harm", "basis_count_converted"), ("frp", "frp_harm", "basis_frp_converted")):
        expected = periods[value].fillna(0.0).to_numpy()
        default_basis = quality.loc[(quality["quantity"] == quantity) & (quality["grain"] == grain), "basis"].iloc[0]
        basis = periods[basis_column].fillna(default_basis)
        converted = pd.concat([lookup_error_factors(quality, area_scale, grain, quantity, name, expected[(basis == name).to_numpy()], min_units)
                               .set_index(np.flatnonzero((basis == name).to_numpy())) for name in basis.unique()]).sort_index()
        bands = uncertainty_bands(expected, quantity, measured, periods["n_harm"].fillna(0.0).to_numpy(), converted, config)
        for column in bands.columns:
            result[f"{value}_{column}"] = bands[column].where(periods[value].notna().to_numpy()).to_numpy()
    result["reliability"] = pd.Series(classify_reliability(measured, periods["n_harm"].fillna(0.0).to_numpy(), config),
                                      index=periods.index).where(periods["n_harm"].notna())
    return result
