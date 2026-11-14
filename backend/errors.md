# Fire-API v3 DTOs vs. harmonised data: findings

Date: 2026-11-14. Compared: `backend/fire-api-v3-dtos(1)/` (DTOs, stub, generated TypeScript) against `data/harmonised/` (Parquet), `db/init/001_schema.sql` and `harmonisation/`.

Scope note: the real frontend (`frontend/`) is still empty (only `.gitkeep`). "Frontend" below means the generated TypeScript contract (`frontend/src/api/schema.d.ts`, `types.ts`) in the DTO bundle.

## Result in short
- DTOs → frontend: consistent. The 42 stub tests pass.
- DTOs ↔ our data: 7 blocking mismatches and several smaller ones. After re-verification against the schema v2 data
  (commit `7abd6a6`, 746,558 hotspots, 217,304 region-days): 5 still open, 2 partly solved (#4, #5), plus new findings N1–N9
  at the end of this file. Status per item is marked **[Re-check]** below.

## Works
- `schema.d.ts` is generated from the same OpenAPI, so names, nullability and enums match.
- `from` is serialised as `from` (not `from_`).
- Grid union (anomaly / by-day / count) is distinguishable on the wire; `isGridByDay` / `isGridCount` in `types.ts` narrow correctly.
- `/api/daily` uses column arrays with `null` for missing days.
- Minor: `events_active` and `events_new` are documented as "omitted" while events are unavailable, but the stub returns `null`. Harmless for TypeScript, but contradicts the comment.

## Blocking mismatches

### 1. FR regions
- Data has `FRI1`, `FRJ1`, `FRJ2` and 34,445 hotspots (4.6%) with country `FR`.
- **[Re-check] still open** (v2 data: 34,445 FR rows).
- `RegionProperties.country` only allows `ES` | `PT` → serialising them gives a 500.
- Fix: filter FR out in the API, or widen the enum.

### 2. `province_id` is required, we only have NUTS-2
- `HotspotProperties.province_id` and `EventProperties.province_id` are non-nullable; examples use ISO codes like `ES-OR`.
- Our `region_id` is NUTS-2 (`ES11`); 16 hotspots have no region at all (v2 data; was 10).
- No NUTS-3 / province level in the data → `level="province"` and `/api/by-region?level=province` cannot be served.
- Fix: map NUTS-2 to `level="region"`, make `province_id` nullable, or load NUTS-3.

### 3. `hotspot.id` is an int, ours is a string
- `hotspot_id` is a 16-char hex string. DTO and MapLibre feature-state expect a stable integer.
- Fix: surrogate `BIGSERIAL` column.
- **[Re-check] still open**: `hotspot_id` is unique, 16 chars, still `TEXT PRIMARY KEY` in `db/init/001_schema.sql`.

### 4. Sensors
- Data has `satellite` (Terra, Aqua, SNPP) + `sensor` (MODIS / VIIRS). DTO enum is `MODIS_TERRA`, `MODIS_AQUA`, `VIIRS_SNPP`, `VIIRS_NOAA20`, `VIIRS_NOAA21` → needs a mapping.
- ~~NOAA-20 / NOAA-21 are not in the data.~~ **[Re-check] solved in v2:** `satellite` now has `SNPP`, `N20`, `N21`, `Terra`, `Aqua`,
  so all five DTO enum values exist. The mapping `N20` → `VIIRS_NOAA20`, `N21` → `VIIRS_NOAA21` is still needed.
- VIIRS SNPP ends 2026-11-02, so `SensorInfo.to` must not be `null` ("still delivering") for it. Confirmed: SNPP last
  hotspot 2026-11-02; NOAA-20/21 until 2026-11-13. For MODIS see N6.

### 5. Grid cells are the wrong type
- DTO wants H3 cells (resolution 3–8, 15 hex chars). Data has a 0.25° `cell_id` such as `157_-18`.
- Fix: compute H3 from lat/lon at load time (`h3` library). Our `cell_id` is not usable for the API.
- **[Re-check] partly solved in v2:** `hotspots_harmonised.h3_cell` exists, 15 hex chars, no nulls, matches the DTO
  `H3Cell` pattern. But it is **resolution 8 only**; resolutions 3–7 need `h3.cell_to_parent` (see N4).

### 6. Harmonisation outputs have no DTO fields
- `dtos.py` has no uncertainty, reliability, strength class, big-fire-day or provisional fields.
- Missing for the team requirements:
  - A4 (error rate): `n_harm_lo50/hi50/lo90/hi90`, `frp_harm_*`, `reliability`.
  - A1 (fire strength): `strength_class`, `big_fire_day`.
  - Provisional data: 105 NRT days (`is_provisional`, 2026-08-01 to 2026-11-13; was 94) and 21 `possible_gap` days.
  - **[Re-check] still open**: `dtos.py` has no uncertainty/reliability/provisional/strength fields (grep count 0); v2 also adds `n_viirs` / `frp_viirs`.
- Fix: extend the DTOs (optional `uncertainty` object on daily / calendar / grid, `provisional` flag), bump `api_version`, regenerate `schema.d.ts`.

### 7. `min_confidence` conflicts with harmonisation
- Data has a `low` confidence class (5.3% of hotspots in v2: 39,387 of 746,558). **[Re-check] still open.** DTO only knows `nominal` | `high`; the default silently drops `low`.
- The aggregation module warns that filtering by `confidence_class` before 2012 is wrongly scaled (factors are calibrated on all fires together). `min_confidence="high"` gives inconsistent numbers across the 2012 boundary.
- Fix: document it, or disable/flag the filter for pre-2012 data.

## Smaller points
- **`weight`:** data has `weight_n` (0 to 9.73; VIIRS 0.33–1.0 = 1/k) and `weight_frp` (0 to 1.40), DTO has one `weight`. Use `weight_n` or add a second field. `n_active` (CSV export column list) does not exist in our data.
- **`hotspots` count (int):** needs a rule. Post-2012 MODIS rows have `in_series_n=false` and weight 0, so counting all rows double-counts.
- **`/api/daily`:**
  - Region or ES+PT: use `activity_daily_harmonised`. Free polygon: use `aggregate_hotspots`, which omits empty days, so `day_status` decides 0 vs `null`.
  - ~~The 230 incomplete rows become `null`.~~ **[Re-check] outdated:** in v2 all 217,304 rows are `is_complete_day=true` and
    `n_harm`/`frp_harm` have no nulls, so `null` never appears in daily arrays inside the data range (see N3).
- **`last_date` ("today" in the UI):** ~~last complete day is about 2026-11-02~~ **[Re-check] outdated:** every day up to 2026-11-13 is complete, so the stub value 2026-11-13 is right, but see N3 (that day is provisional and partial).
- **`/api/regions`:** GISCO geometries are all `MultiPolygon` (matches the DTO). Country-level features and `parent` need a dissolve step. Canaries, Balearics, Azores, Ceuta/Melilla, Madeira are not in the data.
- **Events:** no `event_id` in the data. Fine while `features.events=false`; clustering is separate work.
- **Calendar `running_month`:** can be fed by `month_to_date_vs_history`.
- **`data_version` / `weight_version`:** not in the manifest as such (re-checked, still true); `code_fingerprint` and `config_fingerprint` in `manifest.json` can fill them.

## Recommended next steps
1. Decide: FR handling, NUTS-2 as `level="region"`, `province_id` nullability, surrogate integer hotspot id.
2. Extend DTOs with uncertainty and provisional fields; regenerate `openapi.json` and `schema.d.ts`.
3. Add H3 assignment to the load step.
4. Implement services (daily, calendar, grid, hotspots) on top of `harmonisation/aggregation/`.

## Update: harmonisation schema version 2 (review of branch `data_harmonisation`, 2026-11-14)

Validated: harmonisation tests 54 passed (1 skipped), loader tests 13 passed, committed v2 Parquet loads into a fresh
database, `n_viirs` = mean of the operating VIIRS satellites (exact), `SUM(weight_n)` = `n_harm` per region × day,
all 42 KPIs passed. Details: `harmonisation/docs/viirs_extension.md`.

### Findings above that v2 changes
- **#4 Sensors:** NOAA-20 and NOAA-21 are now in the data (`satellite` = `N20`, `N21`; columns `n_noaa20`, `n_noaa21`, ...).
  The mapping to the DTO enum is still needed (`SNPP` → `VIIRS_SNPP`, `N20` → `VIIRS_NOAA20`, `N21` → `VIIRS_NOAA21`).
  `VIIRS_SNPP` still ends 2026-11-02; NOAA-20/21 deliver until 2026-11-13.
- **#5 Grid cells:** `hotspots_harmonised.h3_cell` now exists, but **only at resolution 8** (see below).
- **`last_date`:** the "last complete day about 2026-11-02" point is outdated. NOAA-20/21 measure 03.–13.11.2026, so every
  day up to **2026-11-13** has `is_complete_day = true` (still `is_provisional = true`, NRT).
- **Measured reference:** for "measured" values use `n_viirs` / `frp_viirs`, not `n_snpp`. `n_snpp` is now one raw value
  among three.

### Points to note
- **H3 only at resolution 8.** The DTO allows resolution 3–8 and a map of Iberia needs about 5–6. Plain Postgres
  (no `h3-pg` extension) cannot compute parent cells, so either the backend derives them in Python
  (`h3.cell_to_parent`), or harmonisation adds coarser columns (`grid.h3_resolution` is one value today).
  Decide before building `/api/grid`.
- **Same fire up to three times on the map.** Since 2018 every VIIRS satellite reports the same fire as its own point
  (about 50 min apart). `in_series_n` only removes MODIS duplicates. Never count points: sum `weight_n`
  (1/k for VIIRS). For point maps, consider filtering to one satellite or showing the satellite.
- **Database must be recreated** for v2: `docker compose down -v && docker compose up -d db`, then
  `docker compose run --rm pipeline python load_to_db.py`. The committed Parquet files are enough, no raw data needed.
- **Raw data for rerunning harmonisation:** new folder layout `data/raw/modis/`, `viirs_snpp/`, `viirs_noaa20/`,
  `viirs_noaa21/`, including the NOAA-20/21 downloads (`harmonisation/docs/raw_sources.md`). These files exist only on
  the author's machine; agree on a shared location.
- **Test fixtures moved to `data/raw/fixtures/`.** Test data now sits next to the real downloads and needs `.gitignore`
  exceptions. Works, but `harmonisation/tests/fixtures/` was the cleaner place.
- **Known method limits** (open points in `viirs_extension.md`): a satellite that reports nothing on an operating day
  counts as 0 in the mean (21 days, only marked `possible_gap`); uncertainty bands of measured days do not yet reflect
  the three-satellite gain (narrower in reality: × 1.5 instead of × 2.0).
- **ER diagram** (`db/docs/`) was updated to v2 but is still crow's-foot notation, not the requested Chen notation.

## Re-verification of the new data (2026-11-14, data commit `7abd6a6`, schema v2)

Method: profiled `data/harmonised/*.parquet`, read `db/init/001_schema.sql`, the new `backend/` scaffold and both `AGENTS.md`
files, and compared them with the DTOs.

| # | Finding | Status in v2 data |
|---|---|---|
| 1 | FR regions vs `country` enum | open (34,445 FR hotspots) |
| 2 | `province_id` required, only NUTS-2 | open (16 hotspots without region) |
| 3 | `hotspot.id` int vs string | open |
| 4 | Sensors | partly solved: NOAA-20/21 present, mapping needed |
| 5 | H3 cells | partly solved: `h3_cell` at resolution 8 only |
| 6 | No uncertainty / strength / provisional DTO fields | open |
| 7 | `min_confidence` vs harmonisation | open (`low` = 5.3%) |
| – | `last_date` ~ 2026-11-02, 230 incomplete rows | outdated, see N3 |

### New findings

**N1. API path version differs: `/api/v1/...` vs `/api/...`**
- `backend/AGENTS.md` and `frontend/AGENTS.md` require all endpoints under `/api/v1/...`; the root `README.md` says
  "API under /api/v1". The DTO bundle (`stub_app.py`, `openapi.json`, `types.ts`: `"/api/meta"`, `"/api/calendar"`, ...) uses `/api/...`.
- Effect: the generated `paths` keys and the typed `apiPost` would not match a backend mounted at `/api/v1`.
- Fix: choose one. Either mount the DTO routers with prefix `/api/v1` and regenerate `schema.d.ts`, or relax the AGENTS rule.

**N2. Backend scaffold does not match the DTO bundle**
- `backend/` is empty stubs (`main.py` empty, `routes/*.py` and `core/db.py` are one-line comments, `services/fake_data.py` one comment).
- `routes/calendar.py` says `# GET /api/calendar`, the DTOs define **POST** `/api/calendar` (body = area selector + confidence).
- The DTO bundle is one `dtos.py` + `errors.py`; the scaffold expects `schemas/` and central error handling in `core/`.
  `errors.py` returns 400 + `ErrorResponse`; FastAPI's default is 422, so the bundle's `install_error_handlers` and the
  OpenAPI 422 removal in `stub_app.py` must be carried over.
- `backend/requirements.txt` has no `pandas`, `shapely` or `h3`, but the aggregation code needs pandas and shapely, and grids need `h3`.

**N3. Last day is provisional and partial, `null` never occurs**
- `is_complete_day` is `true` for all 217,304 region-days, including 2026-11-13, but that day is NRT (`is_provisional=true`,
  as are all 105 days from 2026-08-01), and `aqua_operating` / `terra_operating` are already `false` on 2026-11-13, so it is a partial day.
- `activity_daily_harmonised` has 0 nulls in `n_harm` / `frp_harm`. So `DailyResponse` nulls ("no sensor delivered") and the
  calendar status `incomplete` can no longer be derived from `is_complete_day`.
- Effect: the calendar would mark the running month and its last day as complete, and the same-period comparison
  (`running_month.through`) would use a partial day.
- Fix: derive `status` / `through` from `is_provisional` (or from the last day with all operating satellites), and expose
  `provisional` in the DTO (relates to #6).

**N4. H3 parents are not available in the database**
- Plain `postgres:17` (see `docker-compose.yml`), no `h3-pg` extension, no PostGIS. Resolutions 3–7 for `/api/grid` must be
  computed in Python (`h3.cell_to_parent` on distinct res-8 cells) or stored as extra columns by the loader.
- Anomaly mode (resolution ≤ 5, up to 366 days) should aggregate res-8 cells in SQL first (`GROUP BY h3_cell`), then map
  parents in Python. Do not load all ~750k points.

**N5. Regions and geometries are not in the database**
- Table `regions` has only `region_id`, `region_name`, `country`. `/api/regions` (geometry, `bbox`, `parent`, `level`) must read
  `harmonisation/geo/NUTS_RG_10M_2021_4326_LEVL_2.geojson` (all 23 used regions are `MultiPolygon`) or the DB needs a geometry column.
- No country-level rows (`level="country"`) exist; they need a dissolve of the NUTS-2 shapes (ES, PT) and a stable id such as `ES`.
- Free-drawn polygons (`geometry` in requests, `POST /api/areas`): without PostGIS the point-in-polygon test needs a bbox pre-filter
  in SQL plus `shapely` in Python (`hotspot_queries.is_inside_area` works on a full in-memory DataFrame today).
  `POST /api/areas` also needs clipping to ES + PT (`AreaResponse.geometry`, `area_km2`).

**N6. MODIS rows after 2021 and `SensorInfo` ranges**
- Terra/Aqua rows still exist up to 2026-11-10 / 2026-11-12, but after 2021 they are never part of the series
  (`in_series_n=false`, `weight_n=0`; 98,843 such rows). `meta.sensors[].to` therefore has two possible meanings:
  last raw detection or last day used for the harmonised series. Define it.
- `/api/hotspots` would return MODIS points with `weight=0` after 2021 unless filtered on `in_series_n` or `weight > 0`.

**N7. `confidence_raw` is mixed**
- MODIS: digits `0–100` (`'54'`), VIIRS: letters `n`, `h`, `l`. Fine as text in the CSV export. `HotspotProperties` has no field
  for it; add one only if the frontend wants the raw value.

**N8. `hotspots` metric vs three VIIRS satellites**
- Since 2018 the same fire appears up to three times (SNPP, NOAA-20, NOAA-21). `hotspots` (integer) counts points, `fires`
  (float) sums `weight_n`. Define `hotspots` as `COUNT(*) WHERE in_series_n` and state in the API docs that it is not
  deduplicated across satellites, otherwise the UI shows `hotspots` above `fires` by up to 3× and users read it as an error.

**N9. Uncertainty for the new VIIRS reference is conservative**
- Per the v2 notes, bands of measured days do not yet reflect the three-satellite gain (× 1.5 instead of × 2.0). If the API
  forwards `*_lo/hi` it forwards slightly too wide bands for 2018+ (data quality, not a contract error).

## Decisions and planned changes (2026-11-14)

Context: the frontend is only a prototype. The DTO bundle and its generated TypeScript types are provisional. Nothing below
is implemented yet. Revisit this list when the final frontend arrives and adjust the contract then.

Direction: keep the DTO bundle as the contract base and adapt it to the data. The `backend/` scaffold is empty, so only the
`AGENTS.md` conventions apply.

### DTO changes (bump `api_version` to 3.1, regenerate `openapi.json` and `schema.d.ts`)
1. `province_id` becomes `region_id`, nullable (NUTS-2 only; 16 hotspots have no region). Drop `level="province"` and
   `/by-region?level=province` until NUTS-3 is loaded. (#2)
2. Add an optional `uncertainty` block (`lo50/hi50/lo90/hi90`, `reliability`) on `/daily`, `/calendar` and grid cells. Add
   `strength_class` and `big_fire_day` on `/daily`, and a `provisional` flag. (#6, N3)
3. Hotspot `weight` stays a single field, defined as `weight_n`. (smaller points)
4. Keep `country` as `ES` | `PT`. FR is filtered in the backend. (#1)
5. Document `hotspots` as the raw count of `in_series_n` points, not deduplicated across satellites. (N8)
6. Use one API prefix: mount everything under `/api/v1` (AGENTS.md) and replace the hard-coded `/api/...` paths in
   `types.ts` with one base constant. (N1)

### Backend / data decisions
- FR: filter `country IN ('ES','PT')` in the repository layer.
- `hotspot.id`: surrogate `BIGSERIAL` in `db/init/001_schema.sql` (loader side). (#3)
- Sensors: one mapping function `SNPP`/`N20`/`N21`/`Terra`/`Aqua` to the DTO enum. Return only points with `in_series_n` and
  `weight > 0`, so MODIS after 2021 is hidden. Define what `sensors[].to` means. (#4, N6)
- Grid: `GROUP BY h3_cell` in SQL, then `h3.cell_to_parent` in Python for resolutions 3–7. (#5, N4)
- Regions: read geometry from the GeoJSON file at startup, dissolve countries once and cache. Free-drawn areas: bbox pre-filter
  plus `shapely`, no PostGIS. (N5)
- Calendar and `last_date`: derive `running_month` and status from `is_provisional`, not `is_complete_day`. (N3)
- Structure: `errors.py` goes to `core/` (keep 400 + `ErrorResponse`), `dtos.py` to `schemas/`, aggregation code from
  `harmonisation/aggregation/` behind `services/`. Fix `routes/calendar.py` to POST. Add `pandas`, `shapely`, `h3` to
  `requirements.txt`. (N2)

### Out of scope for now
- Events and clustering (`features.events=false`), NUTS-3 / province level, `POST /api/areas` clipping.

### Suggested order
1. DTO changes and regenerated types (after the final frontend is known).
2. `/meta`, `/regions`, `/daily` on the real data.
3. `/calendar`, then `/hotspots` and `/export.csv`.
4. `/grid`.
