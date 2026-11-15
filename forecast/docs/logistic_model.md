---
title: "Penalised Logistic Regression for Regional Fire Forecasts"
subtitle: "without weather · La-Brasa forecast module, step 1"
author: "Christoph Gahabka"
date: "14 November 2026"
abstract: |
  We forecast, for 23 NUTS-2 regions, the probability of a *big fire day* (VIIRS FRP $\geq$ 100 MW) and of a
  *fire day* (any SNPP detection) 1–10 days ahead, and a three-class outlook (below / normal / above usual
  activity) for weeks 2–4. The models use no weather: only the seasonal climatology of the target day and the
  fire history up to the issue date. Each target and lead gets its own ridge-penalised logistic regression,
  fitted by Newton–Raphson (IRLS) in plain numpy and recalibrated with Platt scaling; the weekly outlook is a
  penalised multinomial regression. On the test years 2022–2026 the day-1 model improves the Brier score of the
  climatology by 21 % (90 % CI 19–24 %) with AUC 0.92. This note states the mathematics behind
  `models/logistic.py` and its callers and shows, after each formula, the code that implements it.
geometry: margin=2.3cm
fontsize: 10pt
numbersections: true
colorlinks: true
linkcolor: blue
header-includes: |
  \usepackage{fvextra}
  \RecustomVerbatimEnvironment{Highlighting}{Verbatim}{breaklines,breakanywhere,commandchars=\\\{\},fontsize=\small}
  \AtBeginDocument{\renewcommand{\boldsymbol}[1]{\symbf{#1}}}
  \newcommand{\sig}{\sigma}
  \newcommand{\logit}{\operatorname{logit}}
  \setlength{\parskip}{0.35em}
---

# Problem

Let $r \in \{1,\dots,G\}$, $G = 23$, index the regions and $t$ the days from 2012-01-20 (start of VIIRS) on.
On an *issue date* $t_0$ we know the data up to and including $t_0$ and want, for every lead
$L \in \{1,\dots,10\}$,

$$
p_{r,t_0,L} = \Pr\!\left(Y_{r,\,t_0+L} = 1 \mid \text{data up to } t_0\right),
\qquad Y \in \{Y^{\text{big}}, Y^{\text{fire}}\}.
$$

We use the **direct approach**: one model per target and lead ($2 \times 10 = 20$ models), each trained on the
pairs (features of $t_0$, target of $t_0+L$). Leads are not chained, so errors do not accumulate.

*Code: `features/fire_history.py`, `lead_pairs`*

```python
out["target_date"] = out["issue_date"] + pd.Timedelta(days=lead)
out["y"] = g[target].shift(-lead).to_numpy()          # target L days after the issue date
out["target_doy"] = day_of_year_noleap(out["target_date"])
```

Targets are set only on *usable* rows (VIIRS measured, complete day, no possible gap); elsewhere $Y$ is missing
and the row is dropped from training and scoring.

# Inputs

## Seasonal climatology

The reference forecast, and the strongest single input, is the mean of the target per region and day of year
$d \in \{1,\dots,365\}$ (29 February counts as 28 February) over the training rows, smoothed with a circular
moving mean of half-width $h = 7$ days:

$$
\bar y_r(d) = \operatorname{mean}\{\,Y_{r,t} : \operatorname{doy}(t) = d,\ t \in \mathcal T\,\},
\qquad
c_r(d) = \operatorname{clip}\!\Big(\tfrac{1}{2h+1}\sum_{k=-h}^{h} \bar y_r\big((d+k) \bmod 365\big),\ \varepsilon,\ 1-\varepsilon\Big),
$$

with $\varepsilon = 10^{-4}$. Days of year without data take the region mean. The climatology enters the model
on the logit scale, $\logit c_r(\operatorname{doy}(t_0+L))$, so a coefficient of 1 on it and 0 elsewhere
reproduces the climatology exactly.

*Code: `features/climatology.py`*

```python
def smooth_circular(values: np.ndarray, window_days: int) -> np.ndarray:
    k = np.ones(2 * window_days + 1) / (2 * window_days + 1)
    return np.array([np.convolve(np.r_[r[-window_days:], r, r[:window_days]], k, mode="valid") for r in values])

t = df.groupby(["region", "doy"])["v"].mean().unstack().reindex(columns=range(1, N_DOY + 1))
t = t.apply(lambda r: r.fillna(r.mean()), axis=1)
sm = smooth_circular(t.to_numpy(), window_days)
sm = np.clip(sm, clip, 1 - clip)
```

## Fire history on the issue date

With $\ell_{r,t} = \log(1 + \text{FRP}_{r,t})$ and the rolling mean
$m_w(x)_t = \frac{1}{w}\sum_{s=0}^{w-1} x_{t-s}$ (at least $\lceil w/2 \rceil$ values present), the
ten issue features are

| Feature | Definition at $t_0$ |
|---|---|
| `logfrp_last`, `logfrp_mean3/7/30` | $\ell_{t_0}$, $m_3(\ell)$, $m_7(\ell)$, $m_{30}(\ell)$ |
| `fire_last`, `fire_frac7/30` | $Y^{\text{fire}}_{t_0}$, $m_7(Y^{\text{fire}})$, $m_{30}(Y^{\text{fire}})$ |
| `big_frac30` | $m_{30}(Y^{\text{big}})$ |
| `log_days_since_big` | $\log\big(1 + \min(t_0 - t_{\text{last big}},\ 365)\big)$ |
| `nbr_logfrp_last` | mean of $\ell_{t_0}$ in the 3 nearest regions (by detection centroid) |

All windows end at $t_0$, so no feature looks ahead (KPI A2 tests this by scrambling later data).

## Design matrix

For row $i$ the design vector stacks an intercept, the $p = 11$ standardised continuous inputs and one-hot
indicators for the region (and, for $Y^{\text{fire}}$, the weekday of the target day, because detections
depend on the satellite overpass pattern):

$$
\boldsymbol x_i = \big(1,\ z_{i1},\dots,z_{ip},\ \boldsymbol e_{r(i)}^\top,\ [\boldsymbol e_{\text{wd}(i)}^\top]\big)^\top \in \mathbb R^{d},
\qquad
z_{ij} = \frac{x_{ij} - \mu_j}{s_j},
$$

where $\mu_j, s_j$ are the training mean and standard deviation. A missing value becomes $z_{ij} = 0$, i.e.
mean imputation. This gives $d = 1 + 11 + 23 = 35$ columns for big fire days and $d = 42$ for fire days.

*Code: `models/logistic.py`, `Design.matrix`*

```python
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
```

# The daily model: ridge logistic regression

## Likelihood and penalty

With linear predictor $\eta_i = \boldsymbol x_i^\top \boldsymbol w$ and $\sig(\eta) = 1/(1 + e^{-\eta})$, the model is
$p_i = \sig(\eta_i)$. We maximise the penalised log-likelihood

$$
\ell_\lambda(\boldsymbol w) = \sum_{i=1}^{n} \Big[\, y_i\,\eta_i - \log\big(1 + e^{\eta_i}\big) \Big]
- \tfrac12\, \boldsymbol w^\top \Lambda\, \boldsymbol w,
\qquad
\Lambda = \operatorname{diag}\big(0,\ \lambda_c \boldsymbol 1_p,\ \lambda_g \boldsymbol 1_G\,[,\ \lambda_g \boldsymbol 1_7]\big),
$$

with $\lambda_c = 100$ for the continuous inputs and $\lambda_g = 20$ for the indicators (chosen on a
validation split 2012–2019 / 2020–2021, not on the test years). The intercept is not penalised.

This is the posterior mode under independent Gaussian priors $w_j \sim \mathcal N(0, \lambda_j^{-1})$.
Note that the design contains the intercept *and all* $G$ region indicators, so $X^\top X$ is singular;
the penalty makes the problem identifiable and gives **partial pooling**: a region's effect is pulled towards
the common intercept, strongly when it has few events, weakly when it has many.

*Code: `models/logistic.py`, `Design.penalty`*

```python
def penalty(self, l2_continuous: float, l2_categorical: float) -> np.ndarray:
    n_cat = sum(len(v) for v in self.categorical.values())
    return np.r_[0.0, np.full(len(self.continuous), l2_continuous), np.full(n_cat, l2_categorical)]
```

## Newton–Raphson / IRLS

The gradient and the negative Hessian of $\ell_\lambda$ are

$$
\boldsymbol g(\boldsymbol w) = X^\top(\boldsymbol y - \boldsymbol p) - \Lambda \boldsymbol w,
\qquad
H(\boldsymbol w) = X^\top W X + \Lambda,
\qquad W = \operatorname{diag}\big(p_i(1 - p_i)\big).
$$

$H$ is positive definite: for $\boldsymbol v \neq 0$, either $\boldsymbol v$ has a penalised component and
$\boldsymbol v^\top \Lambda \boldsymbol v > 0$, or it is the intercept direction and $\boldsymbol 1^\top W \boldsymbol 1 > 0$. Hence
$\ell_\lambda$ is strictly concave and has a unique maximiser. Newton's method iterates

$$
\boldsymbol w^{(k+1)} = \boldsymbol w^{(k)} + H\big(\boldsymbol w^{(k)}\big)^{-1} \boldsymbol g\big(\boldsymbol w^{(k)}\big),
$$

which, written out, is a weighted ridge least-squares fit to the working response
$\boldsymbol u = \boldsymbol\eta + W^{-1}(\boldsymbol y - \boldsymbol p)$:

$$
\boldsymbol w^{(k+1)} = \big(X^\top W X + \Lambda\big)^{-1} X^\top W \boldsymbol u
\qquad \text{(iteratively reweighted least squares).}
$$

We start at $\boldsymbol w^{(0)} = 0$ (all $p_i = \tfrac12$), stop when $\lVert \Delta \boldsymbol w \rVert_\infty < 10^{-9}$
or after 60 steps, and clip $\eta$ to $[-35, 35]$ inside $\sig$ to avoid overflow. There is no line search and
no randomness, so the fit is deterministic (KPI A8).

*Code: `models/logistic.py`, `fit_logistic`*

```python
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
```

## Platt recalibration

Ridge shrinkage and drift between years can leave the probabilities too flat or too steep. Let $\tau$ be two
years before the last training target date. We fit an inner model $\hat p^{\text{in}}$ on the pairs with
$t \leq \tau$, and on the held-out pairs $\mathcal C = \{t > \tau\}$ fit the unpenalised two-parameter
logistic regression

$$
\Pr(Y = 1) = \sig\big(a + b \logit \hat p^{\text{in}}\big)
\quad\Rightarrow\quad (\hat a, \hat b).
$$

The final model is refitted on *all* training pairs and its output is mapped through the same line,
$\tilde p = \sig(\hat a + \hat b \logit \hat p)$. A perfectly calibrated forecast has $(a, b) = (0, 1)$;
$b < 1$ means overconfidence. The same fit applied to test predictions is the calibration-slope diagnostic
(KPI B6: $0.8 \leq b \leq 1.2$).

*Code: `models/daily.py`, `train_calibrated`; `evaluate.py`, `calibration_line`*

```python
cut = end - pd.DateOffset(years=calib_years)
inner, cal = pairs[pairs["target_date"] <= cut], pairs[pairs["target_date"] > cut]
m_inner = train(inner, target, lead, regions, l2_cont, l2_cat)
ab = calibration_line(cal["y"].to_numpy().astype(float), predict(m_inner, cal))
model = train(pairs, target, lead, regions, l2_cont, l2_cat)
model.platt = ab

def calibration_line(y, p):
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    X = np.c_[np.ones(len(p)), np.log(pc / (1 - pc))]
    w = fit_logistic(X, y.astype(float), np.zeros(2))
    return float(w[0]), float(w[1])
```

# The weekly outlook: multinomial regression

## Target classes

For region $r$ and Monday-to-Sunday week $w$, the activity is $A_{r,w} = \sum_{t \in w} \ell_{r,t}$ (complete
weeks only). From the training weeks of the same region and week of year $\pm 1$ (circular over 52 weeks) we
take the terciles $q_1, q_2$ and define

$$
C_{r,w} = \begin{cases} 0 \ (\text{below}) & A \leq q_1, \\ 1 \ (\text{normal}) & q_1 < A \leq q_2, \\
2 \ (\text{above}) & A > q_2. \end{cases}
$$

Many weeks have $A = 0$ and ties go to "below", so the empirical class shares $\pi_0, \pi_1, \pi_2$ are not
exactly $\tfrac13$. They (clipped at 0.02 and renormalised) are the climatological forecast. Week $k$ starts on
the first Monday after $t_0$ plus $7(k-1)$ days; training uses one issue date per week (Sundays).

## Softmax model with reference class

With class 0 as reference ($\boldsymbol W_0 = 0$) and $K = 3$,

$$
\Pr(C = c \mid \boldsymbol x) = \frac{\exp(\boldsymbol x^\top \boldsymbol W_c)}{1 + \sum_{c'=1}^{K-1} \exp(\boldsymbol x^\top \boldsymbol W_{c'})},
\qquad c = 0,\dots,K-1.
$$

The six inputs are the climatology as log-odds, $\log(\pi_0/\pi_1)$ and $\log(\pi_2/\pi_1)$, so the model can
reproduce the climatology, plus `logfrp_mean7`, `logfrp_mean30`, `big_frac30` and the 30-day anomaly
$m_{30}(\ell)_{t_0} - \bar\ell_r(\operatorname{doy}(t_0 - 15))$. Writing $Y_{ic} = \mathbb 1[C_i = c]$ and
$P_{ic}$ for the fitted probabilities, the gradient for class $a \in \{1, \dots, K-1\}$ and the Hessian blocks
are

$$
\boldsymbol g_a = X^\top(\boldsymbol Y_{\cdot a} - \boldsymbol P_{\cdot a}) - \Lambda \boldsymbol W_a,
\qquad
H_{ab} = X^\top \operatorname{diag}\!\big(P_{\cdot a}(\delta_{ab} - P_{\cdot b})\big)\, X,
$$

and the Newton step solves $\big(H + I_{K-1} \otimes \Lambda\big)\, \Delta = \boldsymbol g$ with $\Delta$ and $\boldsymbol g$
stacked class by class. Here $\Lambda = \operatorname{diag}(0, 1, \dots, 1)$ ($\lambda = 1$). The
probabilities subtract the row maximum before exponentiating, which leaves them unchanged and avoids overflow.

*Code: `models/logistic.py`, `fit_multinomial` and `predict_multinomial`*

```python
def fit_multinomial(X, y, n_classes, penalty, max_iter=60, tol=1e-9):
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


def predict_multinomial(X, W):
    Z = np.c_[np.zeros(len(X)), X @ W]
    Z -= Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)
```

# Verification and the shipping rule

**Scores.** For the daily model the Brier score and its skill against the climatology are

$$
\text{BS} = \frac1n \sum_i (p_i - y_i)^2,
\qquad
\text{BSS} = 1 - \frac{\text{BS}_{\text{model}}}{\text{BS}_{\text{clim}}},
$$

for the weekly outlook the ranked probability score over the cumulative probabilities $F_{ik}$ and observations
$O_{ik}$,

$$
\text{RPS}_i = \frac{1}{K-1} \sum_{k=1}^{K-1} (F_{ik} - O_{ik})^2,
\qquad
\text{RPSS} = 1 - \frac{\overline{\text{RPS}}_{\text{model}}}{\overline{\text{RPS}}_{\text{clim}}}.
$$

**Block bootstrap over years.** Days within a year are strongly dependent (fire seasons), so intervals resample
whole years. With per-year loss sums $M_y, R_y$ of model and climatology, each of $B = 1000$ replicates draws $m$
years $y^*_1,\dots,y^*_m$ with replacement and computes $S^* = 1 - \sum_j M_{y^*_j} / \sum_j R_{y^*_j}$; the
5 % and 95 % quantiles of $S^*$ form the 90 % interval.

*Code: `evaluate.py`, `bootstrap_skill_by_year` and `rps`*

```python
df = pd.DataFrame({"y": years, "m": loss_model, "r": loss_ref}).groupby("y")[["m", "r"]].sum()
m, r = df["m"].to_numpy(), df["r"].to_numpy()
idx = np.random.default_rng(seed).integers(0, len(df), size=(n_boot, len(df)))
s = 1 - m[idx].sum(axis=1) / r[idx].sum(axis=1)
lo, hi = np.quantile(s, [(1 - level) / 2, 1 - (1 - level) / 2])

def rps(y_class, probs):
    k = probs.shape[1]
    obs = np.eye(k)[y_class.astype(int)]
    return ((np.cumsum(probs, axis=1) - np.cumsum(obs, axis=1)) ** 2)[:, :-1].sum(axis=1) / (k - 1)
```

**Shipping rule.** A model is shipped for a (target, lead) only if its test skill is positive *and* the lower
bootstrap bound is $\geq 0$; otherwise the climatology is shipped (`source = climatology`). The decision is made
pooled over all regions, and separately for regions with at least 30 test events.

**Uncertainty band.** For big fire days the production model is refitted on $B_m = 20$ year-resampled training
sets; the 5 % and 95 % quantiles of the refitted forecasts, widened to contain $\hat p$, give
`p_big_fire_day_lo` and `p_big_fire_day_hi`.

```python
for _ in range(mc["bootstrap_models"]):
    pick = rng.choice(uniq, size=len(uniq), replace=True)
    idx = np.concatenate([by_year[y] for y in pick])
    sims.append(daily.predict(self.fit_daily(tr.iloc[idx], target, lead), live))
lo, hi = np.quantile(np.array(sims), mc["band_quantiles"], axis=0)
```

# Results

Training 2012-01-20 to 2021-12-31, test 2022-01-01 to 2026-07-31 (last archive day); skill against the
climatology with 90 % year-bootstrap intervals (from `forecast/README.md`, §1.5).

| Lead (days) | 1 | 3 | 5 | 7 | 10 |
|---|---|---|---|---|---|
| BSS big fire day | **0.213** | 0.081 | 0.042 | 0.025 | 0.011 |
| 90 % interval | 0.187–0.238 | 0.053–0.113 | 0.016–0.067 | 0.004–0.051 | −0.007–0.035 |
| AUC big fire day | 0.92 | 0.88 | 0.86 | 0.86 | 0.85 |
| PR-AUC big fire day | 0.46 | 0.29 | 0.22 | 0.20 | 0.18 |
| BSS fire day (SNPP) | 0.130 | 0.059 | 0.042 | 0.032 | 0.027 |

The climatology alone reaches AUC 0.83 and PR-AUC 0.14 for big fire days. Skill decays with lead as the fire
history loses information; from lead 8 on the interval contains 0 and the climatology is shipped.
Leave-one-year-out at lead 1 beats the climatology in all 15 years (BSS 0.10–0.25). The weekly outlook gains
RPSS 0.020 (0.009–0.033) in week 2, 0.009 in week 3 and 0.002 in week 4 (climatology shipped).

# Computational cost

One Newton step costs $O(n d^2)$ for $X^\top W X$ plus $O(d^3)$ for the solve; with $n \approx 1.1 \cdot 10^5$
and $d = 42$ that is about $2 \cdot 10^8$ multiply-adds, roughly 15 ms on the development machine. A full
`run_forecast.py all` performs about 510 such fits, each a few to a dozen Newton steps, and 400 of them are the uncertainty
band: $10$ leads $\times\ 20$ refits $\times\ 2$ (inner and full fit of the Platt step). The run is therefore
single-core, compute-bound and takes minutes. Warm starts from the production coefficients, year weights
instead of row copies, and reusing the production Platt line in the band would remove most of this cost
without changing the method.

# Limitations

- **No weather.** Beyond a few days the fire history carries little information; weather (steps 2–4) is what
  should lift leads 3–10.
- **Linear, additive effects** on the logit scale; interactions (e.g. season $\times$ recent activity) are
  only captured through the climatology input.
- **Platt line** is estimated on the inner model and applied to the refitted full model, which is close but
  not identical.
- **Leads are fitted independently**, so the 10 daily probabilities of one region need not form a coherent
  trajectory.
- **Weekly target drift.** The FRP sum grows with the number of VIIRS satellites (NOAA-20/21), which shifts
  the class shares in the test years.
