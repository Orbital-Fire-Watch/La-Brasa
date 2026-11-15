"""Scores for probability forecasts: Brier, skill, AUC, PR-AUC, calibration, warning threshold, RPS, bootstrap."""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.logistic import fit_logistic


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def skill(score_model: float, score_ref: float) -> float:
    return float(1 - score_model / score_ref) if score_ref > 0 else float("nan")


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = pd.Series(s).rank().to_numpy()
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def pr_auc(y: np.ndarray, s: np.ndarray) -> float:
    """Average precision (area under the precision-recall curve, step interpolation)."""
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-s, kind="mergesort")
    yy = y[order]
    precision = np.cumsum(yy) / np.arange(1, len(yy) + 1)
    return float((precision * yy).sum() / yy.sum())


def ece(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error over equal-count bins (deciles of p): weighted mean |observed - predicted|."""
    order = np.argsort(p, kind="mergesort")
    bins = np.array_split(order, n_bins)
    return float(sum(len(b) / len(p) * abs(y[b].mean() - p[b].mean()) for b in bins if len(b)))


def calibration_line(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """Intercept and slope of a logistic fit y ~ a + b * logit(p). Perfect calibration: (0, 1)."""
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    X = np.c_[np.ones(len(p)), np.log(pc / (1 - pc))]
    w = fit_logistic(X, y.astype(float), np.zeros(2))
    return float(w[0]), float(w[1])


def warning_scores(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    warn = p >= threshold
    tp = int((warn & (y == 1)).sum()); fp = int((warn & (y == 0)).sum()); fn = int((~warn & (y == 1)).sum())
    return {"threshold": float(threshold), "share_warned": float(warn.mean()),
            "hit_rate": tp / (tp + fn) if tp + fn else float("nan"),
            "false_alarm_ratio": fp / (tp + fp) if tp + fp else float("nan"),
            "csi": tp / (tp + fp + fn) if tp + fp + fn else float("nan")}


def binary_scores(y: np.ndarray, p: np.ndarray, p_ref: np.ndarray, threshold: float) -> dict:
    b, b_ref = brier(y, p), brier(y, p_ref)
    a, s = calibration_line(y, p)
    return {"n": int(len(y)), "n_events": int(y.sum()), "base_rate": float(y.mean()), "mean_p": float(p.mean()),
            "brier": b, "brier_clim": b_ref, "bss_vs_climatology": skill(b, b_ref),
            "bss_vs_base_rate": skill(b, brier(y, np.full(len(y), y.mean()))),
            "bss_clim_vs_base_rate": skill(b_ref, brier(y, np.full(len(y), y.mean()))),
            "log_loss": log_loss(y, p), "auc": roc_auc(y, p), "auc_clim": roc_auc(y, p_ref),
            "pr_auc": pr_auc(y, p), "pr_auc_clim": pr_auc(y, p_ref), "ece": ece(y, p),
            "calib_intercept": a, "calib_slope": s, **warning_scores(y, p, threshold)}


def bootstrap_skill_by_year(years: np.ndarray, loss_model: np.ndarray, loss_ref: np.ndarray,
                            n_boot: int, seed: int, level: float = 0.90) -> tuple[float, float]:
    """Block bootstrap over years of 1 - sum(loss_model) / sum(loss_ref). Returns (lower, upper)."""
    df = pd.DataFrame({"y": years, "m": loss_model, "r": loss_ref}).groupby("y")[["m", "r"]].sum()
    m, r = df["m"].to_numpy(), df["r"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(df), size=(n_boot, len(df)))
    s = 1 - m[idx].sum(axis=1) / r[idx].sum(axis=1)
    lo, hi = np.quantile(s, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def rps(y_class: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """Ranked probability score per case for ordered classes 0..K-1."""
    k = probs.shape[1]
    obs = np.eye(k)[y_class.astype(int)]
    return ((np.cumsum(probs, axis=1) - np.cumsum(obs, axis=1)) ** 2)[:, :-1].sum(axis=1) / (k - 1)
