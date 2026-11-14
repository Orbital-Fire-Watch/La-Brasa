# La-Brasa

## How the data flows

```
NASA FIRMS
   │  pipeline/ingestion/       download new NRT data (FIRMS API)
   ▼
data/raw/                       FIRMS CSVs: MODIS + VIIRS SNPP archive 2000–2026, NRT
   │  harmonisation/            clean, assign regions, calibrate, harmonise MODIS -> VIIRS
   ▼
data/harmonised/*.parquet       ← the contract between harmonisation and everything after it
   │  pipeline/load_to_db.py    copy the Parquet tables into Postgres (no calculations)
   ▼
Postgres (db/init/)             one table per Parquet file
   │  backend/                  aggregation, API under /api/v1 (not built yet)
   ▼
frontend/                       (not built yet)
```

Each part only reads the output of the part before it and does not import its code.

| Folder | Does | Does not |
|---|---|---|
| `pipeline/` | download FIRMS NRT data, load harmonised Parquet into Postgres, run the daily update | clean or compute data |
| `harmonisation/` | turn raw CSVs into harmonised Parquet tables; method, analysis and docs | serve data to the product |
| `db/init/` | create the tables (runs once on an empty database volume) | |
| `backend/` | answer questions: aggregation, filtering, export | recompute harmonisation |
| `data/` | local data, not in Git: `raw/`, `processed/`, `harmonised/` | |

- Column meanings, units and "empty vs. 0": `harmonisation/docs/data_dictionary.md`.
- `data/harmonised/csv/` holds CSV copies of every table for inspecting the data. The product does not use them.
- `harmonisation/aggregation/` stays in harmonisation for now (its error model uses it). Parts of it move to the backend once the backend is designed.

## Run it

Requirements: Docker, Python 3.13 (e.g. via `uv`), the FIRMS CSVs in `data/raw/`.

```bash
cp .env.example .env

# 1. harmonise: data/raw/*.csv -> data/harmonised/*.parquet (about 1 minute)
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

After changing `db/init/001_schema.sql`, recreate the database: `docker compose down -v && docker compose up -d db`.

Loader tests (the database tests need the running `db` service):

```bash
cd pipeline
python -m venv .venv && .venv/bin/pip install -r requirements.txt
TEST_DATABASE_URL=postgresql://labrasa:change-me@localhost:5432/labrasa .venv/bin/python -m pytest
```

## Open points

- `pipeline/ingestion/fetch_firms.py` and `pipeline/update_daily.py` are not implemented yet
  (planned: fetch NRT -> `harmonisation/run_pipeline.py` -> `load_to_db.py`).
- The database is plain PostgreSQL 17. `postgis/postgis` has no image for Apple Silicon;
  if spatial queries are needed later, use a multi-arch PostGIS image.

