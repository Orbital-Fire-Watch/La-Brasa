-- Forecast tables (written by forecast/, loaded by pipeline/load_forecast_to_db.py; not touched by load_to_db.py).
-- Column meaning: docs/forecast_backend_frontend.md, section 3.
-- Existing database: run once with psql -f /docker-entrypoint-initdb.d/003_forecast.sql

CREATE TABLE IF NOT EXISTS forecast_daily (
  region_id           TEXT NOT NULL,
  issue_date          DATE NOT NULL,
  target_date         DATE NOT NULL,
  lead_days           SMALLINT NOT NULL CHECK (lead_days BETWEEN 1 AND 10),
  p_big_fire_day      DOUBLE PRECISION NOT NULL CHECK (p_big_fire_day BETWEEN 0 AND 1),
  p_fire_day          DOUBLE PRECISION NOT NULL CHECK (p_fire_day BETWEEN 0 AND 1),
  p_clim_big_fire_day DOUBLE PRECISION NOT NULL,
  p_clim_fire_day     DOUBLE PRECISION NOT NULL,
  risk_ratio          DOUBLE PRECISION NOT NULL,
  risk_class          TEXT NOT NULL CHECK (risk_class IN ('low','normal','elevated','high','very_high')),
  p_big_fire_day_lo   DOUBLE PRECISION NOT NULL,
  p_big_fire_day_hi   DOUBLE PRECISION NOT NULL,
  source              TEXT NOT NULL CHECK (source IN ('model','climatology')),
  model_version       TEXT NOT NULL,
  PRIMARY KEY (region_id, issue_date, lead_days)
);

CREATE TABLE IF NOT EXISTS forecast_weekly (
  region_id              TEXT NOT NULL,
  issue_date             DATE NOT NULL,
  week_start             DATE NOT NULL,
  week_ahead             SMALLINT NOT NULL CHECK (week_ahead BETWEEN 2 AND 4),
  p_below                DOUBLE PRECISION NOT NULL,
  p_normal               DOUBLE PRECISION NOT NULL,
  p_above                DOUBLE PRECISION NOT NULL,
  expected_big_fire_days DOUBLE PRECISION NOT NULL,
  clim_big_fire_days     DOUBLE PRECISION NOT NULL,
  source                 TEXT NOT NULL CHECK (source IN ('model','climatology')),
  model_version          TEXT NOT NULL,
  PRIMARY KEY (region_id, issue_date, week_ahead)
);

CREATE TABLE IF NOT EXISTS forecast_skill (
  product            TEXT NOT NULL,
  target             TEXT NOT NULL,
  lead               SMALLINT NOT NULL,
  region_id          TEXT NOT NULL,              -- region or 'all'
  bss_vs_climatology DOUBLE PRECISION,
  ci_lo              DOUBLE PRECISION,
  ci_hi              DOUBLE PRECISION,
  auc                DOUBLE PRECISION,
  pr_auc             DOUBLE PRECISION,
  ece                DOUBLE PRECISION,
  hit_rate           DOUBLE PRECISION,
  false_alarm_ratio  DOUBLE PRECISION,
  n_events           INTEGER,
  use_model          BOOLEAN NOT NULL,
  skill_basis        TEXT NOT NULL,
  PRIMARY KEY (product, target, lead, region_id)
);

-- state of the last daily run (data/forecast/status.json), one row
CREATE TABLE IF NOT EXISTS forecast_status (
  id                  SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  last_run_utc        TIMESTAMPTZ NOT NULL,
  ok                  BOOLEAN NOT NULL,
  issue_date          DATE NOT NULL,
  model_version       TEXT NOT NULL,
  weather_used        BOOLEAN NOT NULL,
  weather_provider    TEXT,
  warnings            JSONB NOT NULL DEFAULT '[]'
);
