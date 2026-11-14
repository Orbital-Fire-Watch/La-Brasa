# Project validation: harmonisation + backend + frontend (2026-11-14)

State reviewed: branch `app`, commit `870ec9a` (frontend from `da2a04a`, backend from `22ad890`, real NUTS-2
boundaries `2e13065`), harmonised data schema v2 (746,558 hotspots, 217,304 region-days, 2001-01-01 to 2026-11-13).

## How it was checked

| Check | Result |
|---|---|
| Harmonisation tests (`harmonisation/.venv`, pytest) | 54 passed, 1 skipped |
| Pipeline loader tests incl. database tests (scratch DB) | 13 passed |
| Backend API tests against the v2 data (scratch DB, `load_to_db.py`) | 22 passed |
| Frontend: `tsc --noEmit`, `vitest run`, `npm run build` | 0 type errors, 27 tests passed, build ok (1.45 MB JS) |
| ESLint (typescript-eslint recommended + react-hooks, not configured in the repo) | 0 errors, 2 warnings |
| ruff (default + bugbear/pylint/security rules), pylint `-E/-W`, mypy on `backend/` | see T-items below; no functional bug found by the linters |
| Frontend types vs. backend OpenAPI (`openapi-typescript` on the backend's `/openapi.json`) | identical except doc comments |
| Frontend request patterns replayed against the backend (TestClient) | see T1–T3 |
| Data checks (DuckDB on `data/harmonised/*.parquet`) | see part 2 |

The scratch database was deleted afterwards. The user's database was not touched. Nothing was committed.

---

# Part 1: Technical errors

Severity: **high** = feature broken or wrong numbers, **medium** = wrong behaviour in edge cases or setup, **low** = hygiene.

## Frontend

### T1 (high): the Docker image always runs the mock API
- `frontend/Dockerfile` runs `npm run build` without `VITE_API_MODE`. `lib/config.ts` defaults to `mock`, so the image
  served by `docker compose` (port 8080) shows invented data. The production build even contains the mock worker
  (`dist/assets/worker-*.js`, 210 kB).
- `.env.local` is not in `frontend/.dockerignore`, so a developer's local `.env.local` is copied into the build and silently
  decides the mode of the image.
- **Fix:** in the build stage `ARG VITE_API_MODE=live` + `ENV VITE_API_MODE=$VITE_API_MODE`; add `.env*` (except
  `.env.example`) to `.dockerignore`. Optionally show a visible "MOCK DATA" badge whenever `apiMode === "mock"`.

### T2 (high): drawn areas, "frequent areas" and clicking an H3 cell break every view in live mode
- With `meta.features.areas = false` the frontend keeps the drawn polygon locally and sends `geometry` in every request
  (`hooks/useSelection.ts`, allowed by the spec as an interim solution). The backend answers `501 NOT_IMPLEMENTED` for
  `geometry` on `/daily`, `/calendar`, `/grid` and `/hotspots` (`services/scope.py:build_scope`). Verified by replaying the requests.
- The same path is used by "Gebiete, in denen es oft brennt" (`FrequentAreas` → `pickCell` → polygon) and by clicking a cell.
  After one click the whole analysis page shows errors.
- **Fix (choose one):** backend implements `geometry` (bbox pre-filter in SQL + `shapely` point-in-polygon, see
  `harmonisation/aggregation/hotspot_queries.is_inside_area`), or frontend disables drawing and cell picking while
  `features.areas` is false. For picked H3 cells the backend could accept an `h3_cell` selector directly (exact, no polygon needed).

### T3 (high): no clickable regions on the map, wrong names in "frequent areas"
- `components/map/FireMap.tsx:285-290` draws only features with `level === "province"` as the clickable region layer;
  `components/selection/FrequentAreas.tsx:31` looks up names in provinces. The API delivers only `country` and `region`
  (NUTS-2), so the map has no clickable regions and every frequent area is called "Grenzgebiet".
- **Fix:** use `level === "region"` (or the lowest level present). Rename "Provinz" labels (`useSelection.ts:13`,
  `mapFeatures.ts:141`). See C9 for the province question itself.

### T4 (medium): wrong coverage text
- `hooks/useSelection.ts:78`: "Festland und Balearen". The data has no Balearics (ES53), Canaries, Azores, Madeira,
  Ceuta or Melilla. **Fix:** "Festland (ohne Inseln)", or take the text from `/meta.region`.

### T5 (medium): calendar status differs between page 1 and page 2
- Page 1 takes the month status from `/api/calendar` (backend marks a month `incomplete` if one day has `possible_gap`:
  17 months, e.g. 2005-08, 2026-08). Page 2 derives the status from `/api/daily` nulls (there are none), so the same
  months are "complete" there. **Fix:** with the agreed day-level gap flag (see T12) both pages use the same rule.

### T6 (medium): lockfile churn between npm versions
- `npm ci` with npm 11.20 rewrites `package-lock.json` (+114/−152 lines); commit `65bb5c0` is such a churn commit.
- **Fix:** pin the toolchain: `"packageManager": "npm@<version>"` and `"engines"` in `package.json`, or one agreed Node/npm
  version in `startup.md`. The Dockerfile uses `node:26-alpine`, so match that.

### T7 (low): no linter configuration in the repository
- No ESLint/Prettier config. With a standard config there are 2 `react-hooks/exhaustive-deps` warnings:
  `components/map/FireMap.tsx:335` (`props.fitTo`) and `hooks/useMapLibre.ts:37` (`attribution`, `initialBbox`). Both look
  intentional (run once), but should be documented with a comment or a ref.
- **Fix:** commit `eslint.config.js` (typescript-eslint + react-hooks) and an `npm run lint` script.

### T8 (low): one 1.45 MB chunk; the size warning is switched off
- `vite.config.ts` raises `chunkSizeWarningLimit` to 1500 instead of splitting. **Fix:** `React.lazy` for `AnalysisPage`,
  dynamic import of the mock client only in mock mode (removes the worker from live builds), `manualChunks` for `maplibre-gl`.

## Backend

### T9 (high): confidence filter applied to all sums
- `services/scope.py:57-60` filters `confidence_class` for every endpoint, including sums. Measured: the default
  (`nominal`) gives −4.6 to −4.9% vs. `n_harm`; `high` breaks the series at 2012 by about ×5. Details and fix: C4.

### T10 (medium): grid bbox filters points, not cell centres
- `services/grid.py:28-30` filters points by bbox, then aggregates. A cell at the viewport edge contains only part of its
  points, so its value changes while panning (resolution 3, bbox `[-8,42,-7,43]`: all 4 returned cells have their centre outside).
- **Fix (decided):** widen the SQL bbox by one cell size, aggregate, keep cells whose centre (`h3.cell_to_latlng`) is inside.

### T11 (medium): no limits on large requests
- `/grid` count over 2001–2026 at res 8: 17 MB, 3.9 s. `/export.csv` for everything: 57 MB, 9.3 s (statement timeout 10 s).
  "Frequent areas" (res 5, all years) takes 1.4 s here; `startup.md` reports about 5 s on another machine.
- **Fix:** maximum period / cell count for `count` mode, a period limit for the export, both in `/meta.limits`. For
  "frequent areas", precompute once per `data_version` (cache) instead of on every click.

### T12 (medium): one `possible_gap` day marks the whole month `incomplete`
- `services/series.py:57`. **Fix (decided):** flag days, not months: `gap_days` per month, `possible_gap` per day in `/daily`.

### T13 (medium): `weight_version` / `data_version` do not follow the data
- `core/config.py:25` hard-codes `"w1"` although v2 changed the weights; `data_version` = last date + row count;
  `last_update` from `pg_stat_user_tables`. The frontend uses `data_version` to clear its cache (`App.tsx:18-21`) and
  prints both in the footer, so a new harmonisation run with the same row count is not noticed.
- **Fix:** `pipeline/load_to_db.py` stores `manifest.json` in a one-row table `dataset_info`; `/meta` reads
  `run_signature`, `config_fingerprint` and `written_at_utc` from it. Precondition: H1.

### T14 (low): setup and tests
- `backend/tests/test_api.py` imports `pandas`, which is not in `backend/requirements.txt`. The backend test command in
  `startup.md` therefore fails in a fresh venv. **Fix:** `requirements-dev.txt` with pytest, httpx, pandas, pyarrow.
- `requirements.txt` unpinned (`>=`); no `backend/.dockerignore` (`COPY . .` copies tests and tools). **Fix:** pin, add `.dockerignore`.
- Catch-all handler (`errors.py:74-77`) returns 500 without logging. **Fix:** `logger.exception(...)`.
- Lint: unused imports `routes/data.py:2`, `services/grid.py:7`, `services/hotspots.py:4`. mypy: `core/db.py:18`
  (row factory typing), `errors.py:67`, `services/regions.py:49`, `services/series.py:32`, `main.py:41`. Cosmetic.
- Hotspot integer id = first 13 hex characters of `hotspot_id` (0 collisions today). **Fix:** add a uniqueness test, since NRT keeps adding points.

### T15 (low): API path and stale docs
- Routes are `/api/...`; `backend/AGENTS.md`, `frontend/AGENTS.md` and the root `README.md` say `/api/v1/...`. The frontend
  now uses `/api/...` (`services/api/fireApi.ts`). **Fix:** decide once. Either move both to `/api/v1` (one prefix
  constant in the frontend, regenerate types) or change the AGENTS files. Do not leave the docs contradicting the code.
- `README_BACKEND.md` is still a drop-in guide (mentions `pipeline/make_fake_harmonised.py`, `tag_regions.py`, which do
  not exist); `main.py` points to `docs/Fire-API_Spezifikation_v3.md`, which does not exist (see C10).

## Pipeline, database, documentation

### T16 (medium): two run guides that contradict each other
- Root `README.md` (English) still says backend and frontend are "not built yet" and has no start instructions for them.
  `startup.md` (German) covers the full stack, but its troubleshooting row "ModuleNotFoundError: pandas → install
  `pipeline/requirements.txt`" is wrong (the pipeline does not use pandas; it is the backend tests that need it).
- **Fix:** one guide (link the other or merge), updated data flow diagram with backend and frontend.

## Harmonisation

### H1 (medium): `config_fingerprint` depends on the machine
- `pipeline/config.py:load_config` turns all paths into absolute paths, and `config_fingerprint` hashes the whole config
  including `paths` and `sources[].csv`. The fingerprint (and with it `run_signature`, KPI I1b "determinism") changes from
  one machine to the next. It would also make a `weight_version` built from it machine-dependent (T13).
- **Fix:** exclude `paths` and source file paths from the fingerprint (hash the input file checksums instead, which are already in the manifest).

### H2 (low): lint findings
- `run_pipeline.py:167,298`: `subprocess.run` without `check=`; `zip()` without `strict=` in `derive_hotspot_columns.py:88`
  and in the analysis scripts; `global` in `data_analysis/06b_filters_aggregation.py:27`. No functional bug found.
  `sha1` in `derive_hotspot_columns.py:27` is used for ids, not security, so it is fine.

### H3 (low): test fixtures live in `data/raw/fixtures/`
- Test data next to the real downloads needs `.gitignore` exceptions. **Fix:** `harmonisation/tests/fixtures/`.

---

# Part 2: Contextual errors

## 2.1 What the frontend wants to show (the ultimate goal)

The frontend is a **fire situation and history tool for mainland Spain and Portugal**. Its central question:
*"How unusual is the fire activity in my area right now, compared with the same time in past years?"*

| Page | Use case | API used |
|---|---|---|
| 1 Auswahl | choose an area: country / region list, map click, drawn polygon, coordinates, "frequent areas" | `/regions`, `/areas`, `/grid` |
| 1 | choose reference day, method (harmonised hotspots, FRP, events) and confidence | `/meta` |
| 1 | monthly calendar heatmap of all years for the area | `/calendar` |
| 1 | activity map of the last 30 days (H3 cells, points from zoom 11) | `/grid`, `/hotspots` |
| 2 Auswertung | "this week vs. same week in all other years" (factor, rank, median) | `/daily` + `lib/analysis.windowAnomaly` |
| 2 | active / new fires vs. yesterday, strongest fire | `/events` (fallback: H3 cells from `/grid`) |
| 2 | season phase (before / rising / peak / declining) from the typical curve | `/daily` + `climatology` (median per calendar day) |
| 2 | map with lookback 1/7/14 days, events or cells by age, "Ungewöhnlich" (anomaly vs. other years) | `/events`, `/grid` (anomaly), `/hotspots` |
| 2 | time slider ±60 days, season curve per year vs. typical, year heatmap / ring calendar | `/daily` |
| 2 | CSV download of the hotspots in the window | `/export.csv` |

Consequence for the other parts: almost every view **compares years**. The value of the product therefore depends on the
harmonised series being comparable *for the statistics the frontend computes*: medians, quantiles and ranks of daily,
weekly and monthly sums, per region and per H3 cell. Totals alone are not enough.

## 2.2 Frontend vs. best practices

**Good:** strict TypeScript; API types generated from OpenAPI with a type-checked `apiPost`; one HTTP client with timeout,
abort and error mapping; request cache keyed on `data_version`; debounced map queries; all view state in the URL
(shareable, reload-safe); feature flags from `/meta` with fallbacks; pure, tested calculation helpers (`lib/`);
loading, error and empty states everywhere; ARIA labels on charts and controls; a deterministic mock for offline work.

**Recommendations:**
1. **The mock has drifted from the real data and hides integration bugs** (T2, T3, C1, C9). It encodes old assumptions:
   provinces, MODIS-Aqua scale, NOAA-21 from 2024-01-17 (data: 2023-03-01), first day 2000-11-01 (data: 2001-01-01).
   Add a contract smoke test that runs the page queries against the live backend (or a recorded response set from real data).
2. Lint/format config in the repo (T7). Component tests for the two pages (React Testing Library); today only `lib/` and the mock are tested.
3. Code splitting (T8); load the mock only in mock mode.
4. Do not show internal values to users: `weight` in the hotspot popup (`lib/mapFeatures.ts:140`, see C6), `data_version` / `weight_version` in the footer.
5. Texts are hard-coded German in the components. If the audience includes international judges (NASA Space Apps), extract them (one dictionary per language).
6. Repeated query building (grid / hotspots / events with the same selector) in both pages could move into small hooks (`useGridQuery`, ...).

## 2.3 Contextual errors

### C1 (high): frontend and harmonisation use different reference scales
- Frontend and spec: `fires` = **MODIS-Aqua-equivalent** hotspots (`lib/methods.ts:22` help text; mock `K_SENSOR`:
  Aqua 1, Terra 0.9, VIIRS 0.25).
- Harmonisation: `fires` = **VIIRS-equivalent** detections (mean of the operating VIIRS satellites; MODIS × 2.5–5.1 per region).
- The real numbers are about 3–4× what the help text implies. The UI explains the unit wrongly, and the mock was built for the other scale.
- **Recommendation:** keep the VIIRS scale. It is the sensor that delivers today, and since 2012 the harmonised value is
  *exactly* the measured VIIRS value (verified: `n_harm == n_viirs` on all 124,476 region-days since 2012-01-20). Rewrite
  `METHOD_HELP`, the spec and the mock weights accordingly. Name the unit honestly, e.g. "Hotspots (VIIRS-Maßstab)".

### C2 (high): the harmonisation is correct on average, but the frontend compares distributions
The conversion is proportional per detection (`pred = MODIS count × k`). It is calibrated so that **sums** match VIIRS.
It does not reproduce VIIRS's **distribution**: MODIS misses small fires, so converted values are more often 0 and come
in larger steps. Test in the overlap 2012–2021, on the same days and regions, VIIRS measured vs. MODIS converted:

| Level | Mean VIIRS / MODIS-conv. | Median VIIRS / MODIS-conv. | Share of zeros VIIRS / MODIS-conv. |
|---|---|---|---|
| daily, Jun–Sep | 3.73 / 3.51 | 0 / 0 | 58% / 84% |
| weekly, Jun–Sep | 24.9 / 23.4 | **4.0 / 0** | **18% / 51%** |
| monthly | 71.4 / 70.8 | 18.0 / 16.2 | 3% / 19% |

The means agree, but medians and zero shares do not. All pre-2012 years (11 of 25) carry this artefact. The frontend's
comparisons are quantile-based:
- **Typical season curve / season phase** (`climatology` = median per calendar day). Days with a non-zero median, all years
  vs. 2012+ only: ES51 Catalonia 55 vs. 235, ES24 Aragón 19 vs. 108, ES12 Asturias 5 vs. 57, ES52 Valencia 20 vs. 125. For
  ES13, ES23, PT15 and PT17 the "typical" curve is zero all year. The season phase is computed from a curve shaped by the artefact.
- **"Diese Woche im Vergleich"** (median, rank, p25/p75/p90 of 7-day sums). For the week ending 2025-08-14 the median factor over
  the 20 regions is 4.1× with all years and 2.8× with 2012+. More regions get "median 0 → sonst keine Feuer in dieser Woche".
- **"Ungewöhnlich" map** (median per H3 cell, planned): the zero inflation is stronger per cell than per region.

**Recommendation (decision needed):**
- (a) Quantile-based statistics (median, quantiles, rank, season phase, anomaly) use 2012+ only by default. The frontend
  already does this for events (`EVENTS_COMPARABLE_FROM_YEAR`). Long-term views (calendar, year totals, season curves of
  individual years) keep 2001+ with an "umgerechnet" marking.
- (b) Or compare means, not medians, when pre-2012 years are included.
- (c) Or the harmonisation adds a distribution-aware conversion (e.g. quantile mapping per region and season, calibrated
  in the same window) for the views that need it. That is more work and needs its own validation.

### C3 (high): the uncertainty the harmonisation produces never reaches the user
- Harmonisation rates **99.5% of all pre-2012 region-days `converted_rough`** (79,815 + 12,561 of 92,828). On 84% of all
  pre-2012 region-days the value is 0 while `n_harm_hi90 > 0` (median upper bound 2.0), so a 0 there often does not mean "no fire".
- Its own frontend rules (`harmonisation/docs/doc_text.py` `FRONTEND_RULES`): "Vor 2012 immer mit Band", "0 ist nicht immer kein Feuer".
- The API does not deliver bands or `reliability`, and the frontend shows none: no band in the season chart, no marking of
  converted years in the heatmaps, KPI ranks without uncertainty.
- **Recommendation:** `/daily` (and `/calendar`) for regions and countries read `activity_daily_harmonised` and add
  `lo90/hi90` + `reliability`. The frontend draws the band in the season chart and hatches converted years. For weekly or
  monthly sums the bands are not additive: the harmonisation should provide window sums or the method to combine them.

### C4 (high): the confidence switch breaks the long-term comparison
- Verified by recomputing the calibration factor per filter (window 2012-02-01 to 2021-12-31, SNPP vs. Terra + Aqua):
  - all classes: k = 2.996 (used by the pipeline);
  - nominal + high: k = 2.961, i.e. the pre-2012 series is +1.2% too high (per region −4.2% to +7.7%);
  - **high only: k = 0.584, i.e. pre-2012 is +413% too high (per region +95% to +1086%).**
  - MODIS "high" (confidence ≥ 80) covers 38% of MODIS points; VIIRS "h" covers 7%. They are different things.
- The frontend offers "nur hohe Sicherheit" on both pages for all views (calendar, season curve, week comparison). With it,
  every pre-2012 year looks about 5× more active than today. The help text only warns not to compare with the standard
  view, not that the years are not comparable with each other.
- Even the default (`nominal`) puts all API sums 4.6–4.9% below the harmonised table.
- **Recommendation:** sums always use all classes, and the confidence setting only filters map points and the export. If filtered
  sums are really needed, the harmonisation must calibrate per class; "high only" cannot be harmonised meaningfully.

### C5 (high): "events" are a core frontend concept that nobody delivers
- The frontend builds on events: a method option, the default map view, the list, "Aktive Ereignisse", "Neu seit gestern",
  "Stärkstes Feuer" and the event detail. The backend answers `501`. The harmonisation does no clustering (only
  `big_fire_day` / `strength_class` per region-day). The frontend falls back to "active H3 cells", a different concept
  (one cell ≈ 36 km², one fire ≠ one cell).
- No owner is defined. Event counts also depend on the satellite fleet (the frontend already shows them only from 2012).
- **Recommendation:** decide ownership. Clustering of points is a computation on harmonised data, so it belongs in the
  backend or as a new harmonisation output table `events`. The rule is already written in the frontend's InfoTip
  (neighbouring H3 cells, gap ≤ 2 days); the harmonisation's `event_quality.py` could validate it. Until then, hide the
  method option and the "Ereignisse" view instead of showing them disabled.

### C6 (medium): raw, fleet-dependent numbers next to harmonised ones
- "Hotspots (roh)" in tooltips, the unit list and its sort order; "Aktive Gebiete" = cells with any detection. These raw counts
  depend on the fleet: since 2018 every fire appears up to 3× (hotspots ÷ fires = 1.0 in 2012–17, 2.0 in 2018–22, 3.0 since 2023).
  VIIRS sees more and smaller fires than MODIS, and SNPP stops on 2026-11-03, so "active vs. yesterday" drops artificially that day.
- The hotspot popup shows "Gewicht" (`lib/mapFeatures.ts:140`). The harmonisation's own rule: weights are not a property of a
  point, "nie im Popup anzeigen". A user reads 0.333 as "a third of a fire".
- **Recommendation:** label raw counts as "Erkennungen (roh, nicht zwischen Jahren vergleichbar)"; drop `weight` from the
  popup; on the map either show one satellite per day or mark multi-satellite duplicates; compare "active areas" only within the same fleet.

### C7 (medium): the current fire season is provisional, and nobody says so
- All days since 2026-08-01 (105 days, the whole current season) are NRT (`is_provisional`). The default reference day is
  `last_date` (2026-11-13, provisional). The week comparison and the anomaly map compare NRT data with archive data. The API
  has no provisional flag and the UI shows none.
- The newest day is also the most likely to be partial (once the daily update runs). SNPP NRT ended on 2026-11-02, MODIS NRT on 2026-11-12.
- **Recommendation:** `provisional` per day in `/daily` and per month in `/calendar`; a badge "vorläufig" in the UI; default
  reference day = last complete day. The harmonisation should quantify NRT vs. archive differences (not done yet).

### C8 (medium): the planned raw MODIS toggle is missing everywhere
- The team plans a toggle "harmonised / MODIS raw". Neither the frontend nor the API has it.
- A VIIRS toggle is not needed: harmonised **is** VIIRS since 2012 (C1), and before 2012 VIIRS does not exist.
- Raw MODIS needs its own explanations, or users will misread it:
  - Aqua joins on 2002-07-04 (the count roughly doubles);
  - Terra and Aqua drift from their overpass times from about 2022 (the reason the calibration window ends 2021);
  - Terra and Aqua report the same fire twice;
  - MODIS after 2012 is in the data (`in_series_n = false`, about 98,800 points) but is filtered out by `/hotspots` today.
- **Recommendation:** request field `source: "harmonised" | "modis"`. Raw MODIS = `n_terra + n_aqua` from the daily table, and
  all MODIS points; `sensors[]` in `/meta` states availability per source. Decide whether raw MODIS sums Terra + Aqua or averages them like VIIRS.

### C9 (medium): spatial model mismatch: provinces vs. NUTS-2
- The frontend and spec are designed for provinces (NUTS-3, ids like `ES-OR`, "Feuer bei <Provinz>"). The harmonisation assigns
  only NUTS-2 (20 regions ES/PT). Three French border regions are computed but hidden by the API. `startup.md` documents the gap, the code is unchanged.
- For a user, "Galicia" is much coarser than "Ourense"; the most fire-prone areas are provinces.
- **Recommendation:** decide whether provinces are part of the goal. If yes: the harmonisation adds a NUTS-3 column per hotspot
  (point-in-polygon, cheap), while calibration factors stay per NUTS-2 (enough detections). The daily table per NUTS-3 is then a
  sum of weights, with bands to be defined. If no: remove the province level from the DTO and the frontend.

### C10 (medium): the specification everybody refers to is not in the repository
- Frontend, mock and backend cite "spec §2, §5.2, §6.1, §7.3, ..." (`docs/Fire-API_Spezifikation_v3.md`), but `docs/` is empty.
  The spec encodes assumptions that the data contradicts (C1, C9, NOAA-21 start, first date). There is no single place where
  "what the product shows" and "what the data can support" are reconciled.
- **Recommendation:** commit the spec to `docs/`, update it to the data reality (scale, regions, sensors, confidence, events,
  provisional, uncertainty), and make it the reference for all three parts. The Fixing_Folder decisions belong in it.

### C11 (medium): what the harmonisation produces vs. what the product uses
- Produced but unused by the product: uncertainty bands, `reliability`, `strength_class`, `big_fire_day`, `quality_by_scale`,
  `calib_factors`, `strength_confusion`, `big_fire_day_quality`, per-satellite columns.
- Needed by the product but not produced: events, provinces, climatology / typical curves that are valid across eras (C2),
  a provisional flag in the API, raw MODIS series in the API.
- **Recommendation:** decide per item: show (big fire days and strength classes are cheap and serve requirement A1; bands
  are essential, C3) or drop. Move the effort to the missing items.

### C12 (low): CSV export: what users get vs. what they need
- `/export.csv` exports **points** with `weight`. Summing rows instead of weights, or counting the 3 satellite rows per fire,
  gives wrong totals. The export is also disabled for drawn areas.
- The download that supports the product's claim (a harmonised, comparable series) is the **daily series of the selection**
  (`date, value, lo90, hi90, reliability, provisional`), not the points.
- **Recommendation:** offer the daily series CSV as the main download; keep the point export as "Rohdaten" with a header note on `weight`.

---

## Suggested order

1. **Decisions** (team, short): reference scale (C1), confidence on sums (C4), quantile statistics from 2012+ (C2), events owner
   (C5), provinces yes/no (C9), API prefix (T15). Write them into the spec (C10).
2. **Make live mode work:** T1, T2, T3, T4.
3. **Honest numbers:** C3 (bands), C7 (provisional), C6 (raw counts, weight), T9/C4, T12, T5.
4. **Features:** C8 (raw MODIS toggle), C5 (events), T10, T11, C12.
5. **Hygiene:** T6, T7, T8, T13 + H1, T14, T16, H2, H3.
