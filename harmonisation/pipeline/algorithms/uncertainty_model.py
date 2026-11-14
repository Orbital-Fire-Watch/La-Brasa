"""Fehlermodell: Wie genau ist die Umrechnung, je nach Flaeche, Zeitschritt, Basis und Groesse der Zahl?

Alles beruht auf Kreuzvalidierung: Jedes Jahr des Kalibrierfensters wird mit Faktoren aus den
uebrigen Jahren umgerechnet und mit der VIIRS-Messung verglichen.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aggregation.periods import period_start_of
from aggregation.roll_up import add_uncertainty_to_periods
from aggregation.uncertainty import ALL_CLASSES, ZERO_CLASS
from pipeline.algorithms.calibration_factors import MODIS_VARIANTS, estimate_calibration_factors, predict_viirs_equivalent
from pipeline.algorithms.daily_grid import BASIS_AQUA, BASIS_PAIR, BASIS_TERRA, BASIS_VIIRS, sum_hotspots_by_day

BASIS_OF_VARIANT = {"pair": BASIS_PAIR, "aqua": BASIS_AQUA, "terra": BASIS_TERRA}
MEASURED_COLUMN = {"count": "n_snpp", "frp": "frp_snpp"}
PREDICTION_PREFIX = {"count": "pred_n_", "frp": "pred_frp_"}
NO_REGION = "_none_"
VALUE_COLUMNS = ["n_snpp", "frp_snpp"] + [f"{prefix}{variant}" for prefix in PREDICTION_PREFIX.values() for variant in MODIS_VARIANTS]


def factor_error(expected: np.ndarray, measured: np.ndarray, offset: float) -> np.ndarray:
    """Multiplikativer Fehler je Wert: exp(|log((Erwartung + o) / (Messung + o))|), immer >= 1."""
    return np.exp(np.abs(np.log((np.asarray(expected, float) + offset) / (np.asarray(measured, float) + offset))))


def estimate_leave_one_year_out_factors(calibration_days: pd.DataFrame, config: dict[str, Any]) -> dict[int, pd.DataFrame]:
    """Schaetzt fuer jedes Jahr die Faktoren aus allen uebrigen Jahren des Kalibrierfensters."""
    years = calibration_days["date"].dt.year
    return {int(year): estimate_calibration_factors(calibration_days[years != year], config) for year in sorted(years.unique())}


def predict_leave_one_year_out(calibration_days: pd.DataFrame, loyo_factors: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Rechnet jedes Jahr mit den Faktoren aus den uebrigen Jahren um (Region x Tag).

    So wird kein Tag mit einem Faktor bewertet, in den er selbst eingegangen ist. Das Ergebnis
    enthaelt je MODIS-Variante `pred_n_*` und `pred_frp_*` neben der Messung `n_snpp`, `frp_snpp`.
    """
    years = calibration_days["date"].dt.year
    parts = [predict_viirs_equivalent(calibration_days[years == year], factors) for year, factors in loyo_factors.items()]
    units = pd.concat(parts, ignore_index=True)
    return units.rename(columns={"region_id": "area_id"})[["area_id", "date"] + VALUE_COLUMNS]


def predict_cell_units(hotspots: pd.DataFrame, calibration_dates: pd.DatetimeIndex, loyo_factors: dict[int, pd.DataFrame],
                       config: dict[str, Any]) -> pd.DataFrame:
    """Dasselbe auf Zellebene (0,25 Grad x Tag), lueckenlos ueber alle Zellen mit Erkennungen.

    Jeder Punkt einer Zelle wird mit dem Faktor seiner Region umgerechnet, genau wie spaeter bei
    den Gewichten. Zellen ohne Erkennung an einem Tag zaehlen als 0 / 0 und gehoeren dazu: Ohne
    sie saehe das Fehlermodell nur die aktiven Tage und waere zu pessimistisch.
    """
    points = hotspots[hotspots["obs_date"].isin(calibration_dates)]
    pieces = sum_hotspots_by_day(points, config, keys=["cell_id", "region_id"])
    pieces["region_id"] = pieces["region_id"].astype(object).fillna(NO_REGION)      # bekommt die Gesamtfaktoren
    wide = pieces.pivot_table(index=["cell_id", "region_id", "obs_date"], columns="satellite", values=["n", "frp"],
                              aggfunc="sum", fill_value=0)
    wide.columns = [f"{measure}_{satellite.lower()}" for measure, satellite in wide.columns]
    wide = wide.reset_index().rename(columns={"obs_date": "date"})
    years = wide["date"].dt.year
    scaled = pd.concat([predict_viirs_equivalent(wide[years == year], factors) for year, factors in loyo_factors.items()])
    sparse = scaled.groupby(["cell_id", "date"])[VALUE_COLUMNS].sum()
    index = pd.MultiIndex.from_product([sorted(points["cell_id"].unique()), calibration_dates], names=["area_id", "date"])
    return sparse.reindex(index, fill_value=0.0).astype("float32").reset_index()


def sum_units_to_area(region_units: pd.DataFrame, area_scale: str) -> pd.DataFrame:
    """Fasst die Regionseinheiten zu Laendern (`country`) oder zum ganzen Gebiet (`all`) zusammen."""
    area = region_units["area_id"].str[:2] if area_scale == "country" else "all"
    return region_units.assign(area_id=area).groupby(["area_id", "date"], as_index=False)[VALUE_COLUMNS].sum()


def roll_up_units(units: pd.DataFrame, grain: str) -> pd.DataFrame:
    """Summiert Einheiten (Flaeche x Tag) auf einen groeberen Zeitschritt. `year` ist das Jahr des Beginns."""
    if grain == "day":
        return units.assign(year=units["date"].dt.year)
    periods = units.assign(period_start=period_start_of(units["date"], grain))
    summed = periods.groupby(["area_id", "period_start"], as_index=False, observed=True)[VALUE_COLUMNS].sum()
    return summed.assign(year=summed["period_start"].dt.year)


def class_index_of(expected: np.ndarray, bounds: list[float]) -> np.ndarray:
    """Groessenklasse je Wert: 0 fuer Werte <= 0, danach die Intervalle zwischen den Grenzen."""
    return np.searchsorted(np.asarray(bounds, float), np.asarray(expected, float), side="left")


def class_labels_of(bounds: list[float]) -> list[str]:
    """Beschriftungen der Groessenklassen, z. B. "0", "0-5", "5-20", ">500"."""
    labels = [ZERO_CLASS] + [f"{bounds[i]:g}-{bounds[i + 1]:g}" for i in range(len(bounds) - 1)]
    return labels + [f">{bounds[-1]:g}"]


def summarise_error_classes(expected: np.ndarray, measured: np.ndarray, bounds: list[float], offset: float) -> pd.DataFrame:
    """Fehlerkennzahlen je Groessenklasse der umgerechneten Zahl, dazu eine Zeile ueber alle Klassen.

    Je Klasse: typischer Fehler (Median), 90-%-Fehler, Zahl der Faelle und die Quantile der
    Messung selbst (`abs_upper_p50`, `abs_upper_p90`). Letztere werden fuer die Klasse 0 gebraucht:
    Dort sagt ein Faktor nichts, wohl aber die Aussage "wenn die Umrechnung 0 ergibt, misst VIIRS
    in 90 % der Faelle hoechstens so viel". Die Zeile "all" umfasst nur Klassen ueber 0 und dient
    als Rueckfall, wenn eine Klasse zu wenige Faelle hat.
    """
    frame = pd.DataFrame({"class": class_index_of(expected, bounds), "measured": np.asarray(measured, float),
                          "error": factor_error(expected, measured, offset)})
    labels, uppers = class_labels_of(bounds), list(bounds) + [np.inf]

    def describe(group: pd.DataFrame, label: str, upper: float) -> dict[str, Any]:
        """Kennzahlen einer Gruppe von Faellen."""
        return {"size_class": label, "class_upper": upper, "n_units": len(group),
                "median_factor_error": group["error"].median(), "p90_factor_error": group["error"].quantile(0.9),
                "abs_upper_p50": group["measured"].median(), "abs_upper_p90": group["measured"].quantile(0.9)}

    rows = [describe(frame[frame["class"] == index], labels[index], uppers[index]) for index in range(len(labels))
            if (frame["class"] == index).any()]
    rows.append(describe(frame[frame["class"] > 0], ALL_CLASSES, np.inf))
    return pd.DataFrame(rows)


def evaluate_holdout_directions(units: pd.DataFrame, expected_column: str, measured_column: str, bounds: list[float],
                                offset: float, split_years: list[list[int]]) -> pd.DataFrame:
    """Prueft die Fehlerbaender ehrlich: auf einer Haelfte der Jahre bestimmen, auf der anderen pruefen.

    Fuer jede Groessenklasse und jede der beiden Pruefrichtungen (A -> B und B -> A) wird gezaehlt,
    wie oft die Messung der Pruefhaelfte im 50-%- und im 90-%-Band der anderen Haelfte liegt
    (Soll: etwa 0,5 und 0,9). Die Richtungen bleiben getrennt: Zusammengezaehlt wuerden sich eine
    zu enge und eine zu weite Haelfte gegenseitig aufheben und immer nahe am Sollwert landen.
    `factor_shift` ist der Unterschied des typischen Fehlers zwischen den Haelften. Fuer die
    Klasse 0 gilt als Band die absolute Obergrenze.
    """
    halves = [units[units["year"].between(*years)] for years in split_years]
    stats = [summarise_error_classes(half[expected_column], half[measured_column], bounds, offset).set_index("size_class")
             for half in halves]
    rows = []
    for direction, (fit, test_half, other) in enumerate(((stats[0], halves[1], stats[1]), (stats[1], halves[0], stats[0]))):
        classes = class_index_of(test_half[expected_column], bounds)
        errors = factor_error(test_half[expected_column], test_half[measured_column], offset)
        for index, label in enumerate(class_labels_of(bounds)):
            chosen = classes == index
            if not chosen.any() or label not in fit.index or label not in other.index:
                continue
            reference, measured = fit.loc[label], test_half[measured_column].to_numpy()[chosen]
            in50 = measured <= reference["abs_upper_p50"] if index == 0 else errors[chosen] <= reference["median_factor_error"]
            in90 = measured <= reference["abs_upper_p90"] if index == 0 else errors[chosen] <= reference["p90_factor_error"]
            rows.append({"direction": direction, "size_class": label, "n_test": int(chosen.sum()),
                         "covered50": int(in50.sum()), "covered90": int(in90.sum()),
                         "factor_shift": abs(reference["median_factor_error"] / other.loc[label, "median_factor_error"] - 1.0)})
    result = pd.DataFrame(rows)
    return result.assign(coverage50=result["covered50"] / result["n_test"], coverage90=result["covered90"] / result["n_test"])


def summarise_holdout(directions: pd.DataFrame) -> pd.DataFrame:
    """Fasst die beiden Pruefrichtungen je Groessenklasse zusammen: jeweils die niedrigere und die hoehere Abdeckung."""
    grouped = directions.groupby("size_class")
    return grouped.agg(n_test=("n_test", "min"), coverage50_holdout_low=("coverage50", "min"),
                       coverage50_holdout_high=("coverage50", "max"), coverage90_holdout_low=("coverage90", "min"),
                       coverage90_holdout_high=("coverage90", "max"), factor_shift=("factor_shift", "max")).reset_index()


def build_quality_by_scale(units_by_area: dict[str, pd.DataFrame], config: dict[str, Any]) -> pd.DataFrame:
    """Baut das Fehlermodell: Flaeche x Zeitschritt x Groesse x Basis x Groessenklasse.

    Der Fehler einer umgerechneten Zahl haengt von drei Dingen ab: wie gross die Flaeche ist, wie
    lang der Zeitraum und wie gross die Zahl selbst. Je mehr Erkennungen zusammenkommen, desto
    staerker gleicht sich der Zufall aus (ob MODIS ein kleines Feuer gerade sieht oder nicht).
    Die Tabelle beantwortet fuer jede Kombination: Wie weit liegt die Umrechnung typischerweise
    und in 90 % der Faelle von der VIIRS-Messung entfernt? Das Frontend schlaegt hier nach, statt
    einen einzigen Fehlerwert fuer alles zu zeigen.
    """
    params, parts = config["uncertainty"], []
    for area_scale, units in units_by_area.items():
        for grain in params["grains"]:
            rolled = roll_up_units(units, grain)
            for quantity, bounds, offset in (("count", params["count_class_bounds"], params["count_offset"]),
                                             ("frp", params["frp_class_bounds_mw"], params["frp_offset_mw"])):
                for variant in MODIS_VARIANTS:
                    expected, measured = f"{PREDICTION_PREFIX[quantity]}{variant}", MEASURED_COLUMN[quantity]
                    table = summarise_error_classes(rolled[expected], rolled[measured], bounds, offset)
                    holdout = summarise_holdout(evaluate_holdout_directions(rolled, expected, measured, bounds, offset, params["split_years"]))
                    table = table.merge(holdout, on="size_class", how="left")
                    parts.append(table.assign(area_scale=area_scale, grain=grain, quantity=quantity, basis=BASIS_OF_VARIANT[variant]))
    quality = pd.concat(parts, ignore_index=True)
    leading = ["area_scale", "grain", "quantity", "basis", "size_class", "class_upper", "n_units", "median_factor_error",
               "p90_factor_error", "abs_upper_p50", "abs_upper_p90", "coverage50_holdout_low", "coverage50_holdout_high",
               "coverage90_holdout_low", "coverage90_holdout_high", "factor_shift", "n_test"]
    return quality[leading]


def attach_uncertainty_bands(daily: pd.DataFrame, quality: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt je Tageszeile die Fehlerbaender (`*_lo50` bis `*_hi90`) und die Zuverlaessigkeitsstufe.

    Gemessene Tage bekommen das Zaehlrauschen mit Mindestfaktor, umgerechnete Tage die Faktoren
    ihrer Groessenklasse aus dem Fehlermodell (Skala NUTS-2 x Tag). Tage ohne Basis bleiben leer.
    """
    measured = daily["basis_count"] == BASIS_VIIRS
    prepared = daily.reset_index(drop=True).assign(
        grain="day", basis_mix=np.where(measured, "measured", "converted"),
        basis_count_converted=daily["basis_count"].where(daily["basis_count"].isin(BASIS_OF_VARIANT.values())).to_numpy(),
        basis_frp_converted=daily["basis_frp"].where(daily["basis_frp"].isin(BASIS_OF_VARIANT.values())).to_numpy())
    with_bands = add_uncertainty_to_periods(prepared, quality, config, area_scale="nuts2")
    return with_bands.drop(columns=["grain", "basis_mix", "basis_count_converted", "basis_frp_converted"])
