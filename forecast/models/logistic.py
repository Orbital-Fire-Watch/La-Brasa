"""Penalised logistic and multinomial regression in plain numpy (Newton / IRLS, deterministic).

Continuous features are standardised with training means and standard deviations; missing values become
the training mean (0 after standardisation). Region dummies get their own, larger L2 penalty, which pulls
regions with few events towards the common intercept (partial pooling).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Design:
    continuous: list[str]
    categorical: dict[str, list] = field(default_factory=dict)   # column -> levels
    mean: dict[str, float] = field(default_factory=dict)
    std: dict[str, float] = field(default_factory=dict)

    def fit(self, df: pd.DataFrame) -> "Design":
        for c in self.continuous:
            v = df[c].astype(float)
            self.mean[c] = float(v.mean())
            s = float(v.std())
            self.std[c] = s if s > 0 else 1.0
        return self

    def matrix(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.ones(len(df))]
        for c in self.continuous:
            z = (df[c].astype(float).to_numpy() - self.mean[c]) / self.std[c]
            cols.append(np.nan_to_num(z, nan=0.0))
        for c, levels in self.categorical.items():
            vals = df[c].to_numpy()
            for lev in levels:
                cols.append((vals == lev).astype(float))
        return np.column_stack(cols)

    def penalty(self, l2_continuous: float, l2_categorical: float) -> np.ndarray:
        n_cat = sum(len(v) for v in self.categorical.values())
        return np.r_[0.0, np.full(len(self.continuous), l2_continuous), np.full(n_cat, l2_categorical)]

    def names(self) -> list[str]:
        return ["intercept", *self.continuous, *[f"{c}={lev}" for c, levels in self.categorical.items() for lev in levels]]

    def to_dict(self) -> dict:
        return {"continuous": self.continuous, "categorical": {k: [str(x) for x in v] for k, v in self.categorical.items()},
                "mean": self.mean, "std": self.std}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(X: np.ndarray, y: np.ndarray, penalty: np.ndarray, max_iter: int = 60, tol: float = 1e-9) -> np.ndarray:
    """Ridge-penalised logistic regression by Newton-Raphson (IRLS). Returns coefficients."""
    w = np.zeros(X.shape[1])
    pen = np.diag(penalty)
    for _ in range(max_iter):
        p = _sigmoid(X @ w)
        grad = X.T @ (y - p) - penalty * w
        H = (X * (p * (1 - p))[:, None]).T @ X + pen
        step = np.linalg.solve(H, grad)
        w += step
        if np.max(np.abs(step)) < tol:
            break
    return w


def predict_logistic(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    return _sigmoid(X @ w)


def fit_multinomial(X: np.ndarray, y: np.ndarray, n_classes: int, penalty: np.ndarray,
                    max_iter: int = 60, tol: float = 1e-9) -> np.ndarray:
    """Ridge-penalised multinomial logistic regression (class 0 = reference) by Newton. Returns W (d x K-1)."""
    n, d = X.shape
    k = n_classes - 1
    W = np.zeros((d, k))
    Y = np.eye(n_classes)[y.astype(int)][:, 1:]
    pen = np.kron(np.eye(k), np.diag(penalty))
    for _ in range(max_iter):
        P = predict_multinomial(X, W)[:, 1:]
        grad = (X.T @ (Y - P)).T.reshape(-1) - (penalty[None, :] * W.T).reshape(-1)
        H = np.zeros((d * k, d * k))
        for a in range(k):
            for b in range(k):
                wgt = P[:, a] * ((a == b) - P[:, b])
                H[a * d:(a + 1) * d, b * d:(b + 1) * d] = (X * wgt[:, None]).T @ X
        step = np.linalg.solve(H + pen, grad)
        W += step.reshape(k, d).T
        if np.max(np.abs(step)) < tol:
            break
    return W


def predict_multinomial(X: np.ndarray, W: np.ndarray) -> np.ndarray:
    Z = np.c_[np.zeros(len(X)), X @ W]
    Z -= Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)
