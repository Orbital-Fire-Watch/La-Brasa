-- Cloud cover at the VIIRS overpasses per 0.25° cell and day (pipeline/ingestion/fetch_clouds.py, Meteomatics).
-- Loaded by pipeline/load_to_db.py from data/raw/clouds/cloud_daily.parquet, when that file exists.
--
-- Runs automatically on a new, empty database volume. For an existing database run it once:
--   docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/003_clouds.sql'
CREATE TABLE IF NOT EXISTS cloud_daily (
  date        DATE NOT NULL,
  cell_id     TEXT NOT NULL,                    -- as hotspots_harmonised.cell_id: floor(lat / 0.25)_floor(lon / 0.25)
  cloud_day   REAL,                             -- share of the sky covered at about 13:45 UTC, 0-1; NULL = no value
  cloud_night REAL,                             -- the same at about 01:45 UTC
  PRIMARY KEY (date, cell_id)
);
