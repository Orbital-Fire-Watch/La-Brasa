# Integration: data sync and new frontend

| | |
|---|---|
| Commit | `d2568b1` "DD: data sync (FIRMS -> harmonise -> load) and new frontend from design mock" |
| Branch | `app` |
| Date | 14.11.2026 |
| Size | 130 files, +3,792 / −5,294 lines |

This commit connects the parts that were developed separately (harmonisation, pipeline, backend, design mock) into
one working app:

- **Data sync:** one button in the app fetches new FIRMS data, harmonises it and loads it into the database.
- **New frontend:** the design mock (`frontend/design-mock/`) replaces the old selection and analysis pages.
- **Study regions:** the harmonisation keeps exactly the 21 regions the app shows.

---

## 1. Data flow after the change

```
 Frontend "Sync" button
        │  POST /api/sync  (then GET /api/sync every 2 s)
        ▼
 backend/services/sync.py ── background thread, one sync at a time
        │
        ▼
 pipeline/sync_data.py
   1. fetch      pipeline/ingestion/fetch_firms.py           → appends new NRT rows to data/raw/<product>/fire_nrt_*.csv
   2. harmonise  harmonisation/run_pipeline.py --incremental → recomputes days from (first new row − 3 days)
   3. load       pipeline/load_to_db.py --incremental        → replaces those days in PostgreSQL (one transaction)
        │
        ▼
 events index rebuilt (refresh_index) → state "succeeded" → new data_version in /api/meta → frontend reloads all views
```

If a step fails, the sync stops there and the database keeps the previous data.

---

## 2. Backend

### New endpoints

| Endpoint | API version | Purpose |
|---|---|---|
| `POST /api/sync` | 3.1 | Starts a sync and returns `202` with the `SyncStatus`. A POST while a sync runs returns the running one. `501 NOT_IMPLEMENTED` if `FIRMS_MAP_KEY` or the pipeline is missing |
| `GET /api/sync` | 3.1 | Status: `state` (`idle`/`running`/`succeeded`/`failed`), `step` (`fetch`/`harmonise`/`load`), `started_at`, `finished_at`, `new_rows`, `message` |
| `POST /api/daily/sensors` | 3.2 | Raw detections and raw FRP sum per day for MODIS (Terra + Aqua) and VIIRS (SNPP + NOAA-20 + NOAA-21). `null` = no satellite of that family operated that day, `0` = nothing detected |

`API_VERSION` is now `"3.2"` (`backend/dtos.py`).

### Changed files

| File | Change |
|---|---|
| `routes/sync.py` (new) | The two `/api/sync` routes |
| `services/sync.py` (new) | Runs `sync_data()` in a daemon thread. The status is kept in the process memory, so uvicorn must run **one worker**. The pipeline is imported only when a sync starts, so the API does not need the pipeline packages |
| `routes/data.py`, `services/series.py` | `POST /api/daily/sensors`, `build_sensor_daily()`: the same points as `/api/hotspots` (`in_series_n`), unweighted, by sensor family. A family counts as measured when the day is complete and at least one of its satellites operated |
| `services/events.py` | `refresh_index()`: after a sync the event index is rebuilt immediately, not only at the next 30-second check |
| `dtos.py` | `SyncStatus`, `SensorDailyRequest`, `SensorDailyResponse` (validates that all columns have one value per day) |
| `core/config.py` | `PIPELINE_DIR`, `SYNC_AVAILABLE` (FIRMS key set and `pipeline/sync_data.py` present) |
| `main.py` | Registers the sync router |

---

## 3. Pipeline

| File | Change |
|---|---|
| `pipeline/ingestion/fetch_firms.py` (new, 281 lines) | Fetches FIRMS NRT for MODIS, VIIRS SNPP, NOAA-20 and NOAA-21 through the area API (bbox `-10.0,35.9,5.0,44.9`). Reads the file paths from `harmonisation/pipeline_config.yaml`. Requests at most 5 days at a time and re-fetches the last 2 days of each file (late overpasses). Looks back at most 31 days. Converts API rows to the layout of the download files and appends only rows that are not in the file yet (same key as the deduplication in the harmonisation). **Writes nothing if any request fails.** `--dry-run` fetches without writing |
| `pipeline/sync_data.py` (new) | The three steps as one function `sync_data(on_step)`. The harmonisation runs in its own interpreter (`HARMONISATION_PYTHON`, default `harmonisation/.venv`) |
| `pipeline/load_to_db.py` | `--incremental`: reads `data/harmonised/incremental.json` (`since`) and, in one transaction, replaces `hotspots_harmonised` and `activity_daily_harmonised` from that day on and `day_status` completely. Deletes `incremental.json` after a successful load |
| `pipeline/requirements.txt` | `httpx` added |
| `pipeline/update_daily.py` | Removed, replaced by `sync_data.py` |

---

## 4. Harmonisation

### Study regions instead of the common area

- `nuts.study_regions` in `pipeline_config.yaml` lists the 21 regions of the app map
  (`backend/assets/nuts2_iberia.geojson`): mainland Spain with the Balearics and mainland Portugal.
- `restrict_to_study_regions()` assigns the NUTS-2 region right after deduplication. Everything outside is dropped
  with reason `outside_study_regions` (88,155 rows).
- `common_area.py` and the `common_area` config are removed.
- **Why:** the old common area (0.25° cells learned from the data) kept the French border regions FRI1, FRJ1 and FRJ2
  (34,445 hotspots), although MODIS and SNPP coverage stops at about 43.5° N, so those regions were cut off. The
  fixed list cannot change when new downloads arrive, and the boundary is the exact region boundary instead of a
  grid. A test keeps the list equal to the app map.
- **Effect on the regions in the data:**

  | Before (23) | After (21) |
  |---|---|
  | incl. FRI1, FRJ1, FRJ2, without ES53 | without France, **with ES53 (Balearics)** |

### Incremental run (`run_pipeline.py --incremental`)

- `ingest_new_nrt_rows()` re-reads the NRT CSVs. New rows are the ones after the row count of the last run, because
  `fetch_firms.py` only appends. If a file has fewer rows than before, a full run (`--force`) is required.
- Only the days from (first new row − 3 days) on are recomputed (`clean_hotspots_since()`). The calibration factors,
  error model and static mask depend only on the archive (2012–2021), so they are reused from the last full run.
- No tests and no KPIs in this mode. The first day to reload is written to `harmonised/incremental.json` for
  `load_to_db.py --incremental`.
- `git rev-parse` in the manifest no longer fails when git is missing (backend image).

### Recomputed outputs

All tables in `data/harmonised/` were recomputed. Pre-analysis 08 was limited to the same regions:
pair factor 2.9956 → 2.9953, Terra 6.0014 → 5.8906. Result: 41 of 42 checks passed, 55 tests passed, two runs
identical. Missed: **U1b** 0.5801 against the threshold 0.58 (134 of 231 units). The threshold was not changed and is
open for the team (`harmonisation/docs/iteration_log.md`).

---

## 5. Deployment

| File | Change |
|---|---|
| `backend/Dockerfile` | The build context is now the repository root. The image contains `backend/`, `pipeline/` and `harmonisation/` with all their requirements in one Python (`HARMONISATION_PYTHON=python`). Working directory `/app/backend`, one uvicorn worker |
| `.dockerignore` (new) | Keeps `.env`, `.git`, `data/`, `frontend/`, `db/`, `docs/`, notebooks, venvs and caches out of the image |
| `docker-compose.yml` | Backend: `build.context: .`, `dockerfile: backend/Dockerfile`, `FIRMS_MAP_KEY` from `.env`, `./data:/app/data` mounted (the sync writes there) |
| `frontend/Dockerfile` | `VITE_API_MODE=live`: the image always uses the real backend, regardless of `.env.local` |
| `db/init/001_schema.sql`, `db/docs/*` | Only comments and diagram: `country` is now `ES, PT` (no `FR`) |

New environment variable: **`FIRMS_MAP_KEY`** (free, https://firms.modaps.eosdis.nasa.gov/api/map_key/).
Without it the app works, but sync answers `501`.

---

## 6. Frontend

### Design mock promoted to the app

- The code from `frontend/design-mock/src/` moved into the main tree:

  | From `design-mock/` | To |
  |---|---|
  | `src/pages/StartPage.tsx` | `routes/StartPage.tsx` |
  | `src/pages/AnalysisPage.tsx` | merged into `routes/AnalysisPage.tsx` |
  | `src/components/*` | `components/` (`Header`, `SensorCompare`, `map/OrbitalMap`, `map/MapTools`, `start/MonthGrid`, `start/StartTiles`, `analysis/AnalysisParts`, `analysis/YearCompare`) |
  | `src/ui.tsx` | `components/ui/Elements.tsx` |
  | `src/i18n/*` | `i18n/*` (EN, ES, PT) |
  | `src/hooks.ts`, `prefs.tsx`, `selection.ts`, `sync.tsx` | `hooks/useIdleReveal.ts`, `usePrefs.tsx`, `useSelectionInfo.ts`, `useSync.tsx` |
  | `src/palette.ts`, `sensors.ts`, `config.ts`, `ytd.ts` | `lib/palette.ts`, `lib/sensors.ts`, `lib/uiConfig.ts`, `lib/ytd.ts` |
  | `src/mock.css` | `styles/design.css` |
  | `CONTEXT.md`, `info.html`, `assets/la-brasa-logo.svg` | `DESIGN.md`, `info.html`, `assets/` |
  | `src/api/sync.ts`, `src/api/sensorDaily.ts` | `services/api/sync.ts`, `services/api/sensorDaily.ts` + `hooks/useSensorDaily.ts` |

- **Removed:** the old `SelectionPage`, `components/selection/*` (region picker, draw toolbar, coordinate dialog,
  frequent areas, settings bar), `components/analysis/` (`KpiCards`, `SummaryBar`, `TimeSlider`, `UnitDetail`,
  `UnitList`), `components/map/FireMap.tsx`, `Brand.tsx`, `ui/InfoTip.tsx`, `ui/Status.tsx`, `lib/units.ts` and the
  rest of `design-mock/` (`MockApp.tsx`, `mockState.ts`, its own `index.html`, `tsconfig.json`).
- `App.tsx` now wraps the app in `PrefsProvider`, `I18nProvider` and the sync context. Both pages are loaded directly
  (no lazy loading anymore).
- `index.html`: dark theme by default, the La Brasa logo as icon, title "La Brasa", `lang="en"`.

### URL scheme (breaking for old links)

The page is now a query parameter instead of a path, so the app works under any base path:

```
before: /analysis?region=ES-OR&date=2025-08-14&...
after:  /?page=analysis&region=ES-OR&date=2025-08-14&...
```

New parameter `display`: `harmonised` (default), `modis`, `viirs` or `compare` (raw sensors side by side, from
`/api/daily/sensors`).

### Sync button

- `services/api/sync.ts`: `runSync()` sends `POST /api/sync` and then polls `GET /api/sync` every 2 s, giving up
  after 30 minutes. If the server answers `501`, the frontend only requests all data again (`reload_only`).
- `hooks/useSync.tsx`: after a sync the query cache is cleared and the app uses a local version
  `<data_version>#r<N>`. Every query key contains the data version, so all views load again while the map stays
  mounted. Results shown: "Updated …, N new hotspots", "Up to date", "reload only" or "Sync failed" with the
  backend message.
- `services/api/schema.d.ts` was regenerated from the backend OpenAPI. `services/mock/handlers.ts` simulates
  `/api/sync` (ends at the next poll with 0 new rows) and `/api/daily/sensors`.

---

## 7. Documentation

- `startup.md`: new section 5 "Daten aktualisieren" (how the sync works, requirements, limits).
- `README.md`, `backend/README_BACKEND.md`, `frontend/README.md`, `harmonisation/README.md`, `CONTEXT.md`, data
  dictionary, raw sources, pipeline overview and VIIRS extension docs updated for the sync and the study regions.
- `harmonisation/docs/iteration_log.md`: entry "Untersuchungsregionen statt gemeinsamem Gebiet".
- `Fixing_Folder/` removed (`00_READ_FIRST.md`, `errors.md`, `backend_review_2026-11-14.md`,
  `project_validation_2026-11-14.md`).

---

## 8. Open points

| # | Point | Where |
|---|---|---|
| 1 | `startup.md` §5 still says "Es gibt keinen Cronjob und keinen Button in der App", but the app now has the Sync button | `startup.md:74` |
| 2 | **The forecast was trained on the old regions.** `weather_prediction` reads 23 regions (incl. FRI1, FRJ1, FRJ2, without ES53). After merging, `run_forecast.py` must be run again on the 21 study regions; the KPI label "daily 23 x 10, weekly 23 x 3" and the "23 NUTS-2 regions" in the forecast docs and paper need updating | `forecast/run_forecast.py` (F2), `forecast/README.md`, `forecast/docs/logistic_model.md` |
| 3 | `POST /api/sync` has no authentication: anyone who can reach the page can start a sync (5–15 FIRMS requests each; limit 5,000 per 10 min) | `backend/routes/sync.py` |
| 4 | The sync status is in process memory: the backend must stay at one uvicorn worker | `backend/Dockerfile` |
| 5 | `data/harmonised/*` is in git, and every sync changes it, so `git pull` then reports local changes | `startup.md` §5 |
| 6 | FIRMS NRT goes back only about 2 months and `fetch_firms.py` fetches at most 31 days. A longer gap needs a new archive download | `pipeline/ingestion/fetch_firms.py` |
| 7 | The mock reports `api_version` `"3.1"`, the backend `"3.2"` | `frontend/services/mock/handlers.ts:180` |
| 8 | KPI U1b missed by a small margin (0.5801 vs. 0.58), threshold decision open | `harmonisation/docs/iteration_log.md` |
| 9 | On Linux the container writes to `data/` as root, so new files belong to root | `startup.md` §5 |
