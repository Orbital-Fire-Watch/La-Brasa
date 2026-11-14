# Backend review and open issues (2026-11-14)

Collects every open problem found so far, with context and a proposed solution. **Nothing here is implemented
yet.** The fixes are applied at the end, once the frontend exists and the goal is clear. Then unused parts of
the harmonisation may be dropped as well.

State reviewed: branch `backend`, commit `22ad890` ("CHG: adapt API to schema v2"), harmonised data schema v2
(data commit `7abd6a6`: 746,558 hotspots, 217,304 region-days, 2001-01-01 to 2026-11-13).
How it was checked: v2 Parquet loaded into a scratch database with `pipeline/load_to_db.py`, all endpoints called
through FastAPI's `TestClient`, and the results compared with the Parquet files (DuckDB). The 22 backend tests pass.

Older findings: `errors.md` in this folder (DTO bundle vs. data, decisions from earlier on 2026-11-14). Parts of it are
outdated, see section "Status of errors.md" at the end.

---

## 1. `hotspots` is a raw point count, not a harmonised metric

**Problem.** The API offers three metrics, `fires`, `hotspots` and `frp_sum`, as if they were equivalent
(`Metric` literal in `dtos.py`, colour metric for `/grid`, `max` in `/calendar`). Only `fires` (= SUM(`weight_n`))
and `frp_sum` (= SUM(`frp` × `weight_frp`)) are harmonised. `hotspots` (= `COUNT(*) WHERE in_series_n`) counts raw
points. The number of points per fire depends on which satellites are in the series:

| Years | hotspots ÷ fires | Reason |
|---|---|---|
| 2001–2011 | 0.35 | MODIS points (1 km), each weighted ×2.5–5.1 |
| 2012–2017 | 1.0 | SNPP only |
| 2018–2022 | 2.0 | SNPP + NOAA-20 see the same fire |
| 2023–2026 | 3.0 | three VIIRS satellites |

Example: August 2025, ES + PT: 83,173 `hotspots`, 27,722 `fires`. A chart of `hotspots` shows an artificial ×8 jump
between 2011 and 2023, exactly what the harmonisation removes.

**Contextual problem: naming.** `fires` is not a number of fires either. It is "VIIRS-equivalent hotspot detections
(mean of the operating VIIRS satellites)". A user reading "9,523 fires in August 2006" will take it as 9,523 fires.

**Proposal.**
- `fires` is the only count metric for comparisons over time (calendar, anomaly, colour scales, same-period comparison).
  Rename it in the DTO and the UI to something truthful, e.g. `detections` / "hotspot detections (VIIRS scale)".
- Keep the raw count only as information, renamed `detections_raw` (or keep `hotspots` but document it), and remove it
  from `Metric`, from `CalendarResponse.max` and from `same_period`. Tooltip text: "raw satellite detections, not
  comparable across years".
- In the raw MODIS mode (see 6) the raw count is the right metric, because nothing is weighted there.

## 2. Confidence filter (`min_confidence`) on sums: verified, not taken from the docs

**Problem.** Default `min_confidence="nominal"` (= nominal + high) drops the `low` class from every sum. API totals are
therefore about 5% below the harmonised table: ES11 58,139 vs. `n_harm` 61,129 (−4.9%), PT16 75,881 vs. 79,516 (−4.6%).
That level difference alone would be acceptable if it were the same before and after 2012. The harmonisation docs say it
is not ("Klassenfilter nur auf der Karte"). This was checked against the data instead of trusting the docs.

**Check.** The calibration factor k = VIIRS points / MODIS points, computed like `calibration_factors.py`, uses SNPP vs.
Terra + Aqua over the calibration window 2012-02-01 to 2021-12-31 on days where all three operate. It was recomputed per
confidence filter:

| Filter | k (all regions) | Bias of the filtered pre-2012 series | Per region |
|---|---|---|---|
| all classes (what the pipeline uses) | 2.996 | 0 (reference) | – |
| nominal + high | 2.961 | **+1.2%** | −4.2% to +7.7% |
| high only | 0.584 | **+413%** | +95% to +1086% |

Class shares in the same window: `low` is 5.3% of VIIRS and 4.2% of MODIS points, `high` is 7.4% of VIIRS but 38% of
MODIS points. MODIS "high" (confidence ≥ 80) and VIIRS "h" mean completely different things.

**Conclusion.**
- `nominal` + `high`: small but real break at 2012 (+1.2% overall, up to ±8% per region), on top of the −5% level shift.
- `high`: the series breaks completely. Pre-2012 values come out about 5× too high relative to post-2012.
- So the docs are right in essence, and the `high` case is far worse than the docs suggest.

**Proposal.**
- Sums (`/daily`, `/calendar`, `/grid`) always use all classes. That matches the calibration, the uncertainty bands and
  `activity_daily_harmonised`. Remove `min_confidence` from these requests, or ignore it and say so in the API docs.
- `min_confidence` stays only as a point filter on `/hotspots` and the export. Even there, document that "high" means
  different things for MODIS and VIIRS (38% vs. 7% of points).
- Alternative, only if the frontend really needs filtered sums: the harmonisation computes class-specific factors for
  nominal + high (feasible, the bias is small). A harmonised "high only" series is not meaningful and should not be offered.

## 3. The harmonised daily table is not used: no uncertainty, reliability or provisional status in the API

**Problem.** The backend sums `hotspots_harmonised` for every endpoint. It never reads `activity_daily_harmonised`,
which holds `n_harm_lo50/hi50/lo90/hi90`, `frp_harm_*`, `reliability`, `strength_class`, `big_fire_day`, `n_viirs` and
the raw satellite values. `day_status.is_provisional` is never used either. Consequences:
- The API cannot show the uncertainty of pre-2012 values. This is the most important caveat of the method (requirement A4).
- The calendar marks 2026-09 and 2026-10 as `complete`, although all days since 2026-08-01 are provisional NRT data (105 days).
- `strength_class` / `big_fire_day` (requirement A1) are not reachable.

Without the confidence filter the hotspot sums match `n_harm` exactly (difference ~1e-10), so the totals themselves are fine.

**Decision (2026-11-14):** nothing is dropped now, neither in the backend nor in the harmonisation. Once the frontend
exists, decide which outputs it shows, then wire them up or drop them.

**Proposal for later.**
- `/daily` and `/calendar` for a region or a country read `activity_daily_harmonised` (country = sum over its regions;
  check whether the bands may be summed or must be recomputed, since bands are not additive in general).
- Drawn areas and the grid keep summing hotspots; they have no bands. Say so in the response (`uncertainty: null`).
- Add an optional `uncertainty` block and a `provisional` flag to the DTOs (bump `API_VERSION` to 3.1).

**Unused today (candidates to drop or wire up after the frontend decision):**
- `activity_daily_harmonised`: the whole table.
- Tables `quality_by_scale`, `calib_factors`, `strength_confusion`, `big_fire_day_quality` (loaded, never read).
- Hotspot columns `cell_id`, `local_solar_hour`, `frp_class`, `scan`, `track`, `pixel_area_km2`, `basis_*`, `in_series_frp`.

## 4. One `possible_gap` day marks the whole month as incomplete

**Problem.** `services/series.py:build_calendar` sets a month to `incomplete` if any day has `possible_gap`. With 21 gap
days, 17 months are `incomplete`: 2001-04, 2001-12, 2004-02, 2005-08, 2009-09, 2012-03, 2012-06, 2021-01, 2024-01,
2024-02, 2024-09, 2025-02, 2025-03, 2025-05, 2026-03, 2026-06 and 2026-08. Two of them are fire seasons (2005-08, 2026-08).
These days do have values; `possible_gap` only means "a satellite reported nothing although neighbouring days did".
Incomplete months are also excluded from `max`, so they are missing from the colour scale.

**Decision:** mark the day, not the month.
**Proposal.** The month keeps `complete` (or `running`). Add `gap_days: int` (or a list of dates) to `CalendarMonth`, and the
gap flag per day to `/daily` (e.g. `possible_gap: list[bool]`). `incomplete` is reserved for months the data does not
cover (the first month if the data starts mid-month).

## 5. Grid bbox filters points, not cell centres

**Problem.** `services/grid.py` filters points by `latitude/longitude BETWEEN bbox` and then aggregates to cells. Its own
docstring says "A point belongs to the request if ... in the bbox (spec: cell centre)". At resolution 3 with bbox
`[-8, 42, -7, 43]` all four returned cells have their centre outside the bbox and contain only the part of their points
that falls inside. When the user pans the map, the value of the same cell changes.

**Decision (own judgement): filter by cell centre.**
1. SQL pre-filter with the bbox widened by one cell size at the requested resolution
   (`h3.average_hexagon_edge_length(res, "km")` × 2, converted to degrees with the latitude), so every point of a border cell is included.
2. Aggregate to the requested resolution as today.
3. Keep only cells whose centre (`h3.cell_to_latlng`) lies inside the bbox.

Result: a cell always carries its full value, independent of the viewport. Fix the docstring if the frontend prefers clipping.

## 6. Raw MODIS toggle, sensor list and `n_sensors`

**Planned feature:** a toggle between "harmonised" and "MODIS (raw)".

**Is a "VIIRS (raw)" option needed? No.**
- Verified: since 2012-01-20 (`basis_count = viirs_measured`) `n_harm == n_viirs` and `frp_harm == frp_viirs` exactly
  (max difference 0.0) on all 124,476 region-days. Harmonised after 2012 *is* VIIRS.
- Before 2012 VIIRS does not exist. A VIIRS toggle would therefore show the same values after 2012 and nothing before.
- The only variant that differs is "SNPP only" instead of the mean of SNPP, NOAA-20 and NOAA-21. That's an expert detail, not a product feature.

**What raw MODIS means (to be defined in the DTO):**
- Values: `n_terra + n_aqua`, `frp_terra + frp_aqua` from `activity_daily_harmonised`; points: MODIS rows of
  `hotspots_harmonised` **including** the rows with `in_series_n = false` (all MODIS rows after 2012-01-19, about 98,800).
  Today `/hotspots` filters `in_series_n`, so raw MODIS points after 2012 are never returned.
- Raw MODIS has its own breaks, which the UI must explain:
  - Until 2002-07-03 only Terra exists; Aqua roughly doubles the count from 2002-07-04.
  - Terra and Aqua drift from their overpass times from about 2022 (reason the calibration window ends 2021).
  - Terra and Aqua see the same fire, so the raw count is not deduplicated.
- MODIS NRT data exists up to 2026-11-10 (Terra) / 2026-11-12 (Aqua).

**Problems in the current API.**
- `/meta.sensors` lists `MODIS_TERRA` / `MODIS_AQUA` until 2026-11-12 without saying that the harmonised series uses
  MODIS only until 2012-01-19.
- `n_sensors` counts all operating satellites (5 since 2023), although the harmonised series is based on 3 (VIIRS) and the MODIS series on 2.

**Proposal.**
- Add a request field `source: "harmonised" | "modis"` (default `harmonised`) to `/daily`, `/calendar`, `/grid` and `/hotspots`.
- `sensors[]` gets a field such as `in_harmonised_series: {from, to}` next to the raw availability `from/to`.
- `n_sensors` counts the satellites of the selected source.

## 7. `data_version` / `weight_version` do not follow the data

**Problem.**
- `weight_version` is hard-coded `"w1"` (`core/config.py:25`), although schema v2 changed the weights (1/k for VIIRS).
- `data_version` = last date + row count (`services/meta.py`). A new harmonisation run with the same number of rows
  keeps the same version.
- `last_update` comes from `pg_stat_user_tables.last_analyze`, which is reset after a database crash; the fallback is `now()`.
- Frontend caches keyed on these values would keep stale numbers.

**Proposal.**
- `pipeline/load_to_db.py` writes `manifest.json` into a one-row table `dataset_info` (`run_signature`,
  `config_fingerprint`, `code_fingerprint`, `schema_version`, `git_commit`, `written_at_utc`, `loaded_at`), in the same transaction.
- `/meta` reads it: `data_version = run_signature`, `weight_version = config_fingerprint` (or a hash of config + code),
  `last_update = written_at_utc`.
- Precondition: fix `config_fingerprint` first. It currently contains absolute paths, so it differs per machine
  (KPI I1b fails on another machine). Exclude the `paths` section from the fingerprint.

## 8. Large requests have no limit; what `/export.csv` is for

**Measured.**
- `/grid` 2001–2026 at resolution 8: 170,900 cells, 17 MB, 3.9 s.
- `/export.csv` for everything: 583,594 rows, 57 MB, 9.3 s, close to `STATEMENT_TIMEOUT_MS = 10000`. Data grows daily once the NRT update runs.

**Where `/export.csv` is needed.** In the API spec (DTO bundle) it is a "Muss" (must-have) endpoint: the
frontend's download button exports the hotspot points of the current selection (area + period) as CSV. The map does not
use it. Value: users or judges can analyse the data themselves.

**Contextual problem.** It exports *points* with `weight`, but the harmonisation itself says weights are not a property
of a point and are only meaningful as sums. A point CSV is therefore easy to misread (summing rows instead of weights,
3 rows per fire since 2023). The download users actually need is probably the **harmonised daily series** of the
selection (`date, n_harm, bands, reliability, provisional`), or the published Parquet files.

**Proposal.**
- Decide with the frontend: (a) a daily-series CSV per region (small, safe), (b) a point export with a period limit
  (e.g. 366 days) and a header comment on how to use `weight`, or (c) a static download of `data/harmonised/*.parquet`.
- For `/grid` count mode: a maximum period or a maximum number of cells (`Limits`), documented in `/meta.limits`.

---

## 9. Further open points

| # | Problem | Proposal |
|---|---|---|
| 9.1 | `assets/nuts2_iberia.geojson` is a **test file with rectangles**; `/api/regions` serves them | `python backend/tools/make_regions_asset.py --input harmonisation/geo/NUTS_RG_10M_2021_4326_LEVL_2.geojson` (tested: 21 regions, 30 KB). Fix the path in the tool docstring and `README_BACKEND.md` (`data/raw/NUTS_RG_01M...` does not exist). Add `ES53` (Balearics) to `EXCLUDE`. |
| 9.2 | API prefix `/api/...` (`routes/data.py:22`, `routes/pending.py:14`) vs. `/api/v1/...` in `AGENTS.md` and root `README.md` | Switch together with the DTO changes (frontend types are generated from OpenAPI) |
| 9.3 | `/hotspots` shows every fire up to 3× since 2018 (one point per VIIRS satellite) and truncates by highest FRP (limit 20,000; one week of August 2025 has 39,861 points) | Frontend decision: show all, one satellite only, or merge. Sorting by FRP across MODIS/VIIRS mixes non-comparable pixel values |
| 9.4 | `HotspotProperties.weight` invites showing the weight in popups | Document "sum only, never show per point", or drop it from the point response |
| 9.5 | Catch-all handler in `errors.py` returns 500 **without logging** | `logger.exception(...)` in `_unexpected` (AGENTS.md: use `logging`) |
| 9.6 | DTO: `province_id` still required, `level="province"` still offered (no NUTS-3 data), `API_VERSION` still 3.0 | As planned in errors.md: `region_id` nullable, drop `province`, bump the version |
| 9.7 | `README_BACKEND.md` outdated: drop-in instructions, `pipeline/make_fake_harmonised.py` and `tag_regions.py` do not exist; `main.py` refers to `docs/Fire-API_Spezifikation_v3.md`, which does not exist | Rewrite to the current state; add or remove the spec reference |
| 9.8 | Hotspot integer id = first 13 hex characters of `hotspot_id` (52 bits). 0 collisions today | Keep (better than the planned BIGSERIAL: it stays the same across reloads). Add a uniqueness test, since NRT keeps adding points |
| 9.9 | Harmonisation: `config_fingerprint` contains absolute paths (KPI I1b fails on another machine); test fixtures live in `data/raw/fixtures/` | See 7; fixtures back to `harmonisation/tests/fixtures/` |
| 9.10 | Future `update_daily.py`: `is_complete_day` is true even if a day is downloaded before it ends | Harmonisation sets it false for days whose download time is before the end of the day + NRT latency |

---

## 10. Planned structure: evaluation (to be implemented later, not now)

Current layout: `main.py`, `dtos.py`, `errors.py` at the top level; `core/` (config, db); `services/` (SQL **and**
assembly logic); `routes/`; empty `models/`, `repositories/`, `schemas/`.

| Change | Do it? | Why |
|---|---|---|
| `dtos.py` → `schemas/` | yes | Contract code has a folder for it; currently it is empty |
| `errors.py` → `core/errors.py`, `ERRORS_DOC` to `routes/` | yes | Error types are shared infrastructure. The OpenAPI response docs are an HTTP concern, and moving them removes the `core` → `schemas` import |
| SQL from `services/` into `repositories/` | yes | Coming changes (point 3: daily table; point 6: `source` toggle; point 7: `dataset_info`) are mostly data access. The assembly logic (arrays, months, H3 parents, GeoJSON) can then be tested without a database |
| Delete `models/` | yes | No ORM; tables are defined in `db/init/001_schema.sql` |
| Import `harmonisation/aggregation/` into the backend (planned in errors.md) | **no** | The aggregation is pandas in memory (750k rows per request), and the backend's Docker build context is `./backend`. The SQL version gives the same sums (tests compare against pandas). Keep one cross-check test instead |
| Logging in the catch-all handler | yes | 9.5 |
| `requirements.txt` pinned with `==`; split runtime / `requirements-dev.txt` (pytest, httpx, **pandas, pyarrow**: the tests import them but they are not listed) | yes | Same style as `pipeline/`; the image does not need pandas |
| `backend/.dockerignore` (`.venv`, `__pycache__`, `.pytest_cache`, `tests/`) | yes | `COPY . .` copies everything today |
| Rewrite `README_BACKEND.md`, fix the `main.py` docstring | yes | 9.7 |
| `/api/v1` prefix | with the DTO changes | 9.2, contract change |

**Polars instead of pandas? No.**
- The backend has no dataframe code at runtime: aggregation happens in SQL. pandas is only used in the tests as an
  independent oracle (22 tests, ~6 s).
- The harmonisation is pandas-based and validated by 54 tests, 42 KPIs and a determinism check on byte-identical output.
  Rewriting it risks different floats and KPI results for no measurable gain at 750k rows (a full run takes minutes).
- Reconsider only if the harmonisation becomes too slow with daily NRT updates. Even then, DuckDB, which is already used
  in the harmonisation analysis, is the smaller step.

---

## Status of errors.md (what is outdated there)

- #1 FR regions: **solved** (filtered in the backend).
- #3 integer hotspot id: **solved differently** (hash prefix instead of BIGSERIAL, see 9.8).
- #4 sensors: **solved** (`SENSOR_SQL` maps `N20`/`N21`, with a test).
- #5 H3: **solved** (`h3_cell`, parent cells in Python).
- N2: mostly solved (POST calendar, 400 errors, h3/shapely in requirements); open: tests need pandas/pyarrow.
- #2, #6, #7, N1, N3, N5 (geometry asset), N6, N8: **still open**, now covered by points 1–9 above.
- References to `backend/fire-api-v3-dtos(1)/` are stale: that folder no longer exists; its content is now `backend/dtos.py`, `errors.py`, `main.py`.
