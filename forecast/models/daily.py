"""Daily models: one penalised logistic regression per target and lead (direct approach).

Inputs: logit of the region x day-of-year climatology of the target day, fire-history features of the
issue date, region dummies (penalised). For the fire-day target also the weekday of the target day.
Optional `extra` features (weather of the target day, features/weather.py) make the weather tier; without
them it is the no-weather tier, which stays the comparison and the fallback.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from features.climatology import lookup
from features.fire_history import ISSUE_FEATURES
from models.logistic import Design, fit_logistic, predict_logistic

TARGETS = {"big": "big_fire_day", "fire": "fire_day"}


@dataclass
class DailyModel:
    target: str
    lead: int
    design: Design
    coef: np.ndarray
    platt: tuple[float, float] | None = None

    def to_dict(self) -> dict:
        return {"target": self.target, "lead": self.lead, "design": self.design.to_dict(),
                "coef": dict(zip(self.design.names(), map(float, self.coef))),
                "platt": None if self.platt is None else {"a": self.platt[0], "b": self.platt[1]}}


def add_climatology(pairs: pd.DataFrame, clim: pd.DataFrame) -> pd.DataFrame:
    out = pairs.copy()
    out["clim"] = lookup(clim, out["region_id"], out["target_doy"].to_numpy())
    out["clim_logit"] = np.log(out["clim"] / (1 - out["clim"]))
    return out


def make_design(target: str, regions: list[str], extra: tuple[str, ...] | list[str] = ()) -> Design:
    cat = {"region_id": sorted(regions)}
    if target == "fire":
        cat["target_weekday"] = list(range(7))
    return Design(continuous=["clim_logit", *ISSUE_FEATURES, *extra], categorical=cat)


def train(pairs: pd.DataFrame, target: str, lead: int, regions: list[str], l2_cont: float, l2_cat: float,
          extra: tuple[str, ...] | list[str] = (), design: Design | None = None, w0: np.ndarray | None = None) -> DailyModel:
    """design / w0: reuse a fitted design (same standardisation) and start values, for bootstrap refits."""
    design = design or make_design(target, regions, extra).fit(pairs)
    X = design.matrix(pairs)
    w = fit_logistic(X, pairs["y"].to_numpy().astype(float), design.penalty(l2_cont, l2_cat), w0=w0)
    return DailyModel(target, lead, design, w)


def refit_like(model: DailyModel, pairs: pd.DataFrame, l2_cont: float, l2_cat: float) -> DailyModel:
    """Refit on other rows (bootstrap) with the model's design, warm start and its Platt line.

    Cheaper than train_calibrated (no inner fit, few Newton steps). The band then shows the uncertainty of the
    coefficients; the calibration line is held fixed (Christoph Gahabka, docs/logistic_model.md, section 7)."""
    m = train(pairs, model.target, model.lead, [], l2_cont, l2_cat, design=model.design, w0=model.coef)
    m.platt = model.platt
    return m


def predict(model: DailyModel, pairs: pd.DataFrame) -> np.ndarray:
    p = predict_logistic(model.design.matrix(pairs), model.coef)
    return apply_platt(p, model.platt) if model.platt is not None else p


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def apply_platt(p: np.ndarray, ab: tuple[float, float]) -> np.ndarray:
    a, b = ab
    return 1.0 / (1.0 + np.exp(-(a + b * _logit(p))))


def train_calibrated(pairs: pd.DataFrame, target: str, lead: int, regions: list[str], l2_cont: float, l2_cat: float,
                     calib_years: int, extra: tuple[str, ...] | list[str] = ()) -> DailyModel:
    """Platt calibration: fit on all but the last `calib_years` years, learn y ~ a + b*logit(p) on those years,
    then refit on all years and attach (a, b)."""
    from evaluate import calibration_line
    end = pairs["target_date"].max()
    cut = end - pd.DateOffset(years=calib_years)
    inner, cal = pairs[pairs["target_date"] <= cut], pairs[pairs["target_date"] > cut]
    m_inner = train(inner, target, lead, regions, l2_cont, l2_cat, extra)
    ab = calibration_line(cal["y"].to_numpy().astype(float), predict(m_inner, cal))
    model = train(pairs, target, lead, regions, l2_cont, l2_cat, extra)
    model.platt = ab
    return model
