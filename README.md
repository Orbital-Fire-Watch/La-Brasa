# La-Brasa

## How the data flows

```
NASA FIRMS
   │  pipeline/ingestion/       download new FIRMS data (API): archive + NRT
   ▼
data/raw/                       FIRMS CSVs: MODIS + VIIRS (SNPP, NOAA-20, NOAA-21) archive 2000–2026, NRT
   │  harmonisation/            clean, assign regions, calibrate, harmonise MODIS -> VIIRS
   ▼
data/harmonised/*.parquet       ← the contract between harmonisation and everything after it
   │                    │
   │                    │  forecast/            fire activity forecast per region (days 1–10, weeks 2–4)
   │                    ▼
   │                 data/forecast/             forecast tables and status (not in the database yet)
   │
   │  pipeline/load_to_db.py    copy the Parquet tables into Postgres (no calculations)
   ▼
Postgres (db/init/)             one table per Parquet file, plus `areas` (drawn areas of the API)
   │  backend/                  Fire-API v3 under /api: aggregation, events, export (FastAPI)
   ▼
frontend/                       web app: selection page and analysis page (React, MapLibre)
```

Each part only reads the output of the part before it and does not import its code.

| Folder | Does | Does not |
|---|---|---|
| `pipeline/` | download FIRMS data, load harmonised Parquet into Postgres, run the daily update and the app sync | clean or compute data |
| `harmonisation/` | turn raw CSVs into harmonised Parquet tables; method, analysis and docs | serve data to the product |
| `forecast/` | weather data and the fire activity forecast; reads only `data/harmonised/` | change harmonised data |
| `db/init/` | create the tables (runs once on an empty database volume) | |
| `backend/` | answer questions: aggregation, filtering, events, export | recompute harmonisation |
| `frontend/` | the web app; talks only to the backend (or to its built-in mock) | compute data |
| `data/` | local data, not in Git: `raw/`, `processed/`, `harmonised/`, `forecast/`, `logs/` | |

- Column meanings, units and "empty vs. 0": `harmonisation/docs/data_dictionary.md`.
- `data/harmonised/` is not in Git: every clone creates it with step 1 below.
- `data/harmonised/csv/` holds CSV copies of every table for inspecting the data. The product does not use them.
- `harmonisation/aggregation/` stays in harmonisation for now (its error model uses it). Parts of it move to the backend once the backend is designed.
- Forecast method, quality and setup: `forecast/README.md`. How it gets into the database, API and web app:
  `docs/forecast_backend_frontend.md`.

## Run it

Requirements: Docker, Python 3.13 (e.g. via `uv`), the FIRMS CSVs in `data/raw/`.

```bash
cp .env.example .env            # FIRMS_MAP_KEY is needed for new FIRMS data

# 1. harmonise: data/raw/*.csv -> data/harmonised/*.parquet (about 2 minutes)
cd harmonisation
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_pipeline.py
cd ..

# 2. start Postgres (creates the tables on first start)
docker compose up -d db

# 3. load the Parquet tables into Postgres
docker compose run --rm pipeline python load_to_db.py --dry-run   # check only
docker compose run --rm pipeline python load_to_db.py
```

Then start the API and the website: see `startup.md`.

After changing `db/init/001_schema.sql`, recreate the database: `docker compose down -v && docker compose up -d db`.

Loader and FIRMS tests (the database tests need the running `db` service):

```bash
cd pipeline
python -m venv .venv && .venv/bin/pip install -r requirements.txt
TEST_DATABASE_URL=postgresql://labrasa:change-me@localhost:5432/labrasa .venv/bin/python -m pytest
```

## Keeping the data up to date

There are two ways. Both use `pipeline/ingestion/fetch_firms.py` and need `FIRMS_MAP_KEY` in `.env`.

| | Daily update (server, cron) | App sync (button in the web app) |
|---|---|---|
| Start | `python3 pipeline/update_daily.py` | `POST /api/sync` (status: `GET /api/sync`) runs `pipeline/sync_data.py` |
| FIRMS | archive + NRT; NRT days that are now in the archive are removed | NRT only, new rows appended at the end |
| Harmonisation | `run_pipeline.py` (changed stages, with tests and KPIs) | `run_pipeline.py --incremental` (only the last days, no tests) |
| Database | only with `--load-db` | always, `load_to_db.py --incremental` |
| Forecast | `forecast/daily.py` | no |
| Docs | `pipeline/README.md` | `startup.md` |

## Open points

- Two ways of updating (table above). In the long run there should be one entry point; until then the daily
  update is the full, checked run and the app sync is the quick top-up in between.
- The forecast is not in the database, the API or the web app yet: `docs/forecast_backend_frontend.md`.
- The database is plain PostgreSQL 17. `postgis/postgis` has no image for Apple Silicon;
  if spatial queries are needed later, use a multi-arch PostGIS image.
