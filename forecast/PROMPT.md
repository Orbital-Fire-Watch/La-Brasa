# Task: Build a short-term fire forecast for La-Brasa (days 1–10 daily, weeks 2–4 outlook)

You are working in the repository `/home/leni/Projekte/La-Brasa` (NASA Space Apps Challenge 2026,
challenge "MODIS and VIIRS Hot Spots"). The team builds a map and calendar of fire danger for the
Iberian Peninsula. The harmonisation of the satellite data is finished. Your job is a **new, separate
forecast module** that predicts fire activity per NUTS-2 region for the next 1–10 days and gives a
general outlook for weeks 2–4.

Read this whole prompt before writing code. Then read, in this order:
`README.md`, `harmonisation/CONTEXT.md` (section 0 first), `harmonisation/docs/data_dictionary.md`.

---

## 1. Hard rules (do not break these)

1. **Never run `git commit` or `git push`.** Only change the working tree. The user commits.
2. **Do not modify existing code or files.** Nothing in `harmonisation/`, `pipeline/`, `backend/`,
   `db/`, `frontend/`, `docker-compose.yml`, `.gitignore`, `.env.example`. If a change there seems
   necessary, stop and ask, with the exact proposed diff.
3. Everything new lives in `La-Brasa/forecast/` (code) and `La-Brasa/data/forecast/` (outputs).
   Raw weather downloads are cached in `La-Brasa/data/raw/weather/<provider>/`.
4. The forecast module **only reads** `data/harmonised/*.parquet` (and `harmonisation/geo/*.geojson`
   as a read-only file). It does **not import** any code from `harmonisation/` or `aggregation/`.
   Re-implement the small pieces you need (e.g. the day-of-year climatology) and test them.
5. Own virtual environment `forecast/.venv` and own `forecast/requirements.txt` with pinned versions.
   The harmonisation venv uses Python 3.14; any 3.13+ is fine.
6. Secrets (API keys, usernames, passwords) only in `La-Brasa/.env`, read via environment variables.
   Never print, log or write them anywhere else. Never ask the user to paste them into the chat.
7. Weather API requests contain only coordinates, dates and variable names. No personal data.
8. Code, comments and docs in English (like `README.md`).

---

## 2. The data you get (already produced, do not recompute)

Main table: `data/harmonised/activity_daily_harmonised.parquet`, one row per NUTS-2 region and day,
gap-free from 2001-01-01 to 2026-11-13 (updated by the pipeline). 23 regions (ES, PT and three
French regions partly inside the box lat 36–43.8, lon −9.5–3.3).

Columns you need:

| Column | Meaning |
|---|---|
| `region_id`, `region_name`, `country`, `date` | key |
| `basis_count` | `viirs_measured` from 2012-01-20, before that MODIS converted. **Use only `viirs_measured` rows for training.** Daily MODIS conversions have ≈ ×2 error and miss ≈ 60 % of fire days. |
| `n_harm`, `frp_harm` | harmonised count / FRP sum (MW) of the day; on measured days = mean over the active VIIRS satellites |
| `n_snpp`, `frp_snpp` | raw SNPP values (single, stable satellite since 2012-01-20) |
| `big_fire_day` | `frp_harm ≥ 100 MW` |
| `is_complete_day`, `possible_gap` | exclude incomplete days and suspected data gaps from training targets |

Other tables: `hotspots_harmonised.parquet` (one row per detection, with `cell_id` = 0.25° cell,
`region_id`, `obs_date`, `frp`, `satellite`, `in_series_n`), `day_status.parquet` (per day: which
satellites operate, `is_provisional` for NRT days).

### Known pitfall: the satellite-count artefact

`n_harm > 0` ("any detection") becomes more frequent when more VIIRS satellites are in orbit
(NOAA-20 from 2018-04-01, NOAA-21 from 2023-03-01), because any one satellite's detection makes
the day non-zero. Share of region-days with fire:

| Year | `n_harm > 0` | `n_snpp > 0` |
|---|---|---|
| 2017 | 0.33 | 0.33 |
| 2019 | 0.42 | 0.32 |
| 2024 | 0.39 | 0.23 |

This is a measurement effect, not a trend. Therefore:
- **Main target: `big_fire_day`** (based on mean FRP, barely affected).
- **Second target: fire day defined as `n_snpp > 0`** (one consistent satellite).
- Add a test that fails if a target's yearly base rate jumps at 2018-04-01 or 2023-03-01.

### Base rates (measured days 2012-01-20 to 2026-11-13)

124,476 region-days, ≈ 3,600 big-fire days. Big-fire days are very unevenly spread: PT11 Norte 657,
PT16 Centro 376, ES41 Castilla y León 416, ES61 Andalucía 405, but ES21 País Vasco 5, ES23 La Rioja 9.
Small regions need partial pooling (see 4.3).

---

## 3. Feasibility result already obtained (use as the baseline to beat)

Setup: train 2012–2021, test 2022–2026, measured days only. Models: (a) climatology = probability per
region × day of year, ±7 days circular smoothing, training years only; (b) logistic regression on
logit(climatology) + fire on the last known day + share of fire days over the last 7 and 30 days +
mean log(1+FRP) over 7 days + share of big-fire days over 30 days, all ending at the issue date.
BSS = Brier skill score against the constant base rate.

| Target | Lead (days) | BSS climatology | BSS model | Model vs. climatology | AUC clim → model |
|---|---|---|---|---|---|
| fire day (`n_harm>0`) | 1 | 0.17 | 0.26 | +11 % | 0.74 → 0.79 |
| fire day | 3 | 0.17 | 0.21 | +6 % | 0.74 → 0.76 |
| fire day | 7 | 0.17 | 0.20 | +3 % | 0.74 → 0.75 |
| fire day | 14–28 | 0.17 | 0.18 | +1–2 % | 0.74 |
| big-fire day | 1 | 0.06 | 0.19 | +13 % | 0.83 → 0.89 |
| big-fire day | 3 | 0.06 | 0.12 | +6 % | 0.83 → 0.86 |
| big-fire day | 7 | 0.06 | 0.08 | +2 % | 0.83 → 0.84 |
| big-fire day | ≥ 14 | 0.06 | 0.06 | ≈ 0 | 0.83 |

Conclusion: fire history carries days 1–3. Days 4–10 need **weather forecasts**. Weeks 2–4 need
**antecedent drought and long-range anomalies** and are shown as categories, not daily values.
(That test used `n_harm > 0`; redo it with `n_snpp > 0` as the first step.)

---

## 4. What to build

### 4.1 Two products

| | Days 1–10: daily forecast | Weeks 2–4: outlook |
|---|---|---|
| Unit | region × target day | region × week (Monday–Sunday) |
| Target | P(big-fire day), P(fire day, SNPP-based) | number of big-fire days in the week, in terciles of past years for that region and week of year |
| Output | probability + ratio to climatology + risk class | P(below / normal / above normal) |
| Signals | climatology, recent fire activity, weather forecast for the target day, antecedent dryness | climatology, last-30-day activity, 30/90-day precipitation and temperature anomalies, drought codes, extended-range forecast anomalies |

### 4.2 Features (all known at the issue date, no leakage)

- **Seasonality:** logit of the region × day-of-year climatology, computed from training years only
  (inside each cross-validation fold).
- **Fire history:** as in section 3 (lags 1, 3, 7, 30 days, counted back from the issue date, not the target date).
- **Weather on the target day** (forecast at inference): daily max temperature, min relative
  humidity, vapour pressure deficit, max wind speed / gust, 24 h precipitation.
- **Canadian Fire Weather Index (FWI) system:** FFMC, DMC, DC, ISI, BUI, FWI. It's the standard fire-danger
  index in Europe (EFFIS uses it) and performs well in the Mediterranean. Compute it yourself from noon
  local weather (temperature, RH, wind, 24 h precipitation) with a tested implementation (e.g. `xclim`'s
  FWI indicators, or a small reference implementation checked against published test values). DC and
  DMC are the drought memory and matter most for weeks 2–4.
- **Antecedent dryness:** days since ≥ 1 mm rain, precipitation sums over 30 and 90 days, and their
  anomaly versus the 2012–2021 climatology of that region and date.
- **Human factors:** Iberian fires are mostly human-ignited. Add day of week and public holidays
  (`holidays` package, ES/PT/FR). Experts include these, and their effect is measurable.
- **Calendar:** day of year is already in the climatology. Don't add raw year (it would learn the satellite
  artefact or overfit trends).

### 4.3 Models (simple, explainable, calibrated)

- **Daily:** one logistic regression per lead time 1–10 ("direct" approach, no iterating). Nonlinear
  weather effects via a few spline or binned terms (e.g. FWI, max temperature). Region effect as an
  L2-penalised intercept (partial pooling), so small regions shrink towards the Iberian mean.
  Use `statsmodels` or `scikit-learn`. A gradient-boosting comparison (e.g. LightGBM) is allowed as a
  check, but only ship it if it clearly wins out of sample. In the harmonisation work, simple models won.
- **Weekly:** ordinal or multinomial logistic regression on the tercile category, few features
  (climatology expectation, last-30-day activity, DC/DMC anomaly, 30/90-day precipitation anomaly,
  temperature anomaly, extended-range anomaly if available).
- **Calibration:** check reliability per lead time. If miscalibrated, add Platt or isotonic calibration
  fitted on a held-out year, never on test data.
- **Imbalance:** do not resample or reweight classes. Output true probabilities.

### 4.4 Training and the forecast-vs-observation trap

At inference the weather inputs are *forecasts*; in training the natural choice is *observed*
(reanalysis) weather. That makes test scores look better than reality, increasingly with lead time. What experts do:
1. Prefer **archived forecasts** for training/evaluation at the right lead time (see 5: Open-Meteo
   Historical Forecast and Previous Runs APIs). Check how far back they go, probably only 2021/2022 onwards.
2. Otherwise train on reanalysis (ERA5) but **evaluate days 4–10 with archived forecasts** for the
   years where they exist, or with reanalysis plus lead-dependent noise matched to known forecast
   errors. Label the reported skill accordingly.
3. **Ensembles:** at inference, run the model on each ensemble member (Open-Meteo Ensemble API) and
   average the probabilities. This propagates weather uncertainty and usually improves calibration.

### 4.5 Evaluation (decides what the frontend shows)

- **Temporal splits only:** leave-one-year-out over 2012–2026 plus a final hold-out 2022–2026 with a
  model trained on 2012–2021. Never random splits (neighbouring days and regions are correlated).
- **Scores per lead time and target:** Brier score and BSS against climatology, log loss, ROC-AUC,
  reliability diagram, for big-fire days hit rate / false alarm ratio at the chosen warning threshold.
  Weekly: ranked probability skill score (RPSS) against climatological terciles (1/3, 1/3, 1/3).
- **Confidence intervals** via block bootstrap over years.
- **Per region** as well as pooled. Flag regions with too few events.
- **Fallback rule:** for each lead time (and region, if robust), use the model only where its BSS
  versus climatology is > 0 on the hold-out years with a bootstrap lower bound ≥ 0. Otherwise output
  the climatology and mark `source = "climatology"`. The frontend must never show a forecast worse
  than the normal seasonal profile.
- Write everything to `data/forecast/forecast_skill.parquet` and a short `forecast/docs/evaluation.md`.

---

## 5. Weather data

Regions are large (Andalucía ≈ 87,000 km²). Don't use plain area means. Choose **fire-weighted points**:
per region the 0.25° cells (`cell_id` in `hotspots_harmonised`) that hold most historical VIIRS
detections, about 5–10 cells per region, ≈ 150–200 points in total. Region weather = weighted mean
over these points, with weights = the cell's share of the region's detections (training years only).

Providers (wrap them behind one interface `WeatherProvider` with `history(points, start, end)` and
`forecast(points, issue_date)`, cache every raw response as Parquet in `data/raw/weather/<provider>/`,
make all fetches resumable and rate-limited):

1. **Open-Meteo** (default, no registration, free for non-commercial use, keep within its fair-use limits):
   - Historical weather API (ERA5 / ERA5-Land reanalysis) for 2012 to today: training data.
   - Forecast API (up to 16 days) and Ensemble API: inference.
   - Historical Forecast API and Previous Runs API: archived forecasts by lead day, for honest evaluation.
   - Seasonal forecast API: anomalies for weeks 2–4.
   Check the current documentation for variables, coverage periods and limits before relying on them.
2. **Meteomatics** (optional, requires an account): username and password in `.env` as
   `METEOMATICS_USERNAME` / `METEOMATICS_PASSWORD`. Only implement it if the user has an account;
   check which parameters (e.g. fire weather indices) and request quotas that account has. Use it as a
   second forecast source or for comparison, not for the multi-year history unless the quota allows it.
3. **Copernicus** (optional, free account): CEMS fire danger indices (FWI from ERA5) as a cross-check
   of your own FWI computation.

Keep the provider consistent between training and inference where possible (e.g. ERA5 history and an
ECMWF-based forecast). Document any switch.

---

## 6. Outputs (`data/forecast/`, Parquet, plus `manifest.json` with versions, input hashes, issue date)

- `forecast_daily.parquet`: `region_id`, `issue_date`, `target_date`, `lead_days` (1–10),
  `p_big_fire_day`, `p_fire_day`, `p_clim_big_fire_day`, `p_clim_fire_day`, `risk_ratio`
  (= p / p_clim), `risk_class` (e.g. low / normal / elevated / high / very high, defined from
  `risk_ratio` and absolute p), `p_big_fire_day_lo`, `p_big_fire_day_hi` (ensemble spread),
  `source` (`model` / `climatology`), `model_version`.
- `forecast_weekly.parquet`: `region_id`, `issue_date`, `week_start`, `week_ahead` (2–4), `p_below`,
  `p_normal`, `p_above`, `expected_big_fire_days`, `clim_big_fire_days`, `source`, `model_version`.
- `forecast_skill.parquet`: one row per product, target, lead time, region (or `all`): scores from 4.5
  and the fallback decision.

Column documentation in `forecast/docs/data_dictionary.md`, in the same style as
`harmonisation/docs/data_dictionary.md`, including "0 vs. empty" semantics.

---

## 7. Folder layout

```
forecast/
  PROMPT.md               this file
  README.md               how to run, what it does and doesn't do
  requirements.txt
  config.yaml             periods, leads, thresholds, providers, points per region
  run_forecast.py         CLI: fetch → features → train/evaluate → forecast; --offline uses cache only
  features/fire_history.py
  features/climatology.py
  features/weather.py     providers + cache + fire-weighted points
  features/fwi.py
  models/daily.py
  models/weekly.py
  evaluate.py
  tests/                  pytest; no network in tests (use fixtures)
  docs/evaluation.md  docs/data_dictionary.md
```

`data/forecast/` is not in `.gitignore`. Tell the user; don't edit `.gitignore` yourself.

---

## 8. Work plan (deliver in this order, each step runnable on its own)

1. **Skeleton + baselines without weather:** climatology, fire-history features, daily logistic
   models per lead time, weekly tercile model, evaluation, fallback, output tables. Redo the
   feasibility test with `n_snpp > 0` and `big_fire_day`. Show the skill table to the user.
2. **Weather history:** fire-weighted points, Open-Meteo ERA5 download 2012 to today (cached), FWI
   computation with tests.
3. **Models with weather:** re-evaluate, report the gain per lead time compared with step 1, apply the fallback rule.
4. **Honest evaluation with archived forecasts** for the years where they exist.
5. **Live run:** today's forecast (deterministic + ensemble) → `forecast_daily`, `forecast_weekly`.
6. Optional: Meteomatics provider, if the user has credentials.

After each step: run the tests, give a short summary with the numbers, and list open points. Report
failures with the actual output. Don't hide them.

---

## 9. What must be communicated with the results

- The forecast is about **detected fire activity per region** (satellite overpasses ≈ 2× per day),
  not about individual fires, ignitions or burned area.
- Days 1–3 are driven by ongoing fires, days 4–10 by the weather forecast, and weeks 2–4 only say "calmer /
  normal / riskier than usual".
- Reported skill for days 4–10 is an upper estimate unless it was evaluated with archived forecasts.
- Regions with few big-fire days (e.g. ES21, ES23, ES62, PT17) have wide uncertainty.
- NRT days (`day_status.is_provisional`) can still change; the latest days are provisional inputs.
