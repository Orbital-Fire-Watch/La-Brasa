-- Runs automatically on the first start of an EMPTY database volume.
-- After changing this file: docker compose down -v && docker compose up db
--
-- One table per harmonised Parquet file in data/harmonised/ (written by
-- harmonisation/run_pipeline.py, loaded by pipeline/load_to_db.py).
-- Column names and types mirror the Parquet files; their meaning is documented
-- in harmonisation/docs/data_dictionary.md. NOT NULL = "nie leer" there.
-- NULL means "no value" and is never the same as 0.

-- Regions that occur in the harmonised data (NUTS-2 2021; ES, PT and 3 FR regions)
CREATE TABLE regions (
  region_id   TEXT PRIMARY KEY,
  region_name TEXT NOT NULL,
  country     TEXT NOT NULL
);

-- Canonical dataset: one row per region and day
CREATE TABLE activity_daily_harmonised (
  region_id       TEXT NOT NULL REFERENCES regions (region_id),
  country         TEXT NOT NULL,
  region_name     TEXT NOT NULL,
  date            DATE NOT NULL,
  n_aqua          DOUBLE PRECISION,
  n_terra         DOUBLE PRECISION,
  n_snpp          DOUBLE PRECISION,
  frp_aqua        DOUBLE PRECISION,
  frp_terra       DOUBLE PRECISION,
  frp_snpp        DOUBLE PRECISION,
  basis_count     TEXT,
  basis_frp       TEXT,
  n_harm          DOUBLE PRECISION,
  frp_harm        DOUBLE PRECISION,
  factor_count    DOUBLE PRECISION,
  factor_frp      DOUBLE PRECISION,
  strength_class  TEXT,
  big_fire_day    BOOLEAN,
  n_harm_lo50     DOUBLE PRECISION,
  n_harm_hi50     DOUBLE PRECISION,
  n_harm_lo90     DOUBLE PRECISION,
  n_harm_hi90     DOUBLE PRECISION,
  frp_harm_lo50   DOUBLE PRECISION,
  frp_harm_hi50   DOUBLE PRECISION,
  frp_harm_lo90   DOUBLE PRECISION,
  frp_harm_hi90   DOUBLE PRECISION,
  reliability     TEXT,
  is_complete_day BOOLEAN NOT NULL,
  possible_gap    BOOLEAN NOT NULL,
  PRIMARY KEY (region_id, date)
);
CREATE INDEX ON activity_daily_harmonised (date);

-- One row per detection (pixel and overpass), with weights for the harmonised series
CREATE TABLE hotspots_harmonised (
  hotspot_id       TEXT PRIMARY KEY,
  latitude         DOUBLE PRECISION NOT NULL,
  longitude        DOUBLE PRECISION NOT NULL,
  cell_id          TEXT NOT NULL,
  acq_date         DATE NOT NULL,
  acq_time         TEXT NOT NULL,                -- HHMM, UTC
  acq_datetime_utc TIMESTAMPTZ NOT NULL,
  obs_date         DATE NOT NULL,
  local_solar_hour DOUBLE PRECISION NOT NULL,
  satellite        TEXT NOT NULL,
  sensor           TEXT NOT NULL,
  source           TEXT NOT NULL,
  daynight         TEXT NOT NULL,
  frp              DOUBLE PRECISION,
  frp_class        TEXT NOT NULL,
  confidence_class TEXT,
  confidence_raw   TEXT NOT NULL,
  scan             DOUBLE PRECISION NOT NULL,
  track            DOUBLE PRECISION NOT NULL,
  pixel_area_km2   DOUBLE PRECISION NOT NULL,
  region_id        TEXT REFERENCES regions (region_id),
  country          TEXT,
  in_series_n      BOOLEAN NOT NULL,
  in_series_frp    BOOLEAN NOT NULL,
  weight_n         DOUBLE PRECISION,
  weight_frp       DOUBLE PRECISION,
  basis_count      TEXT,
  basis_frp        TEXT
);
CREATE INDEX ON hotspots_harmonised (obs_date);
CREATE INDEX ON hotspots_harmonised (region_id, obs_date);

-- One row per day: which satellites operated, basis of the series, provisional (NRT)
CREATE TABLE day_status (
  date            DATE PRIMARY KEY,
  snpp_operating  BOOLEAN NOT NULL,
  aqua_operating  BOOLEAN NOT NULL,
  terra_operating BOOLEAN NOT NULL,
  basis_count     TEXT,
  basis_frp       TEXT,
  is_complete_day BOOLEAN NOT NULL,
  is_provisional  BOOLEAN NOT NULL,
  possible_gap    BOOLEAN NOT NULL
);

-- Error model from cross-validation, per area scale, time step, quantity, basis and size class
CREATE TABLE quality_by_scale (
  area_scale              TEXT NOT NULL,
  grain                   TEXT NOT NULL,
  quantity                TEXT NOT NULL,
  basis                   TEXT NOT NULL,
  size_class              TEXT NOT NULL,
  class_upper             DOUBLE PRECISION,
  n_units                 BIGINT NOT NULL,
  median_factor_error     DOUBLE PRECISION NOT NULL,
  p90_factor_error        DOUBLE PRECISION NOT NULL,
  abs_upper_p50           DOUBLE PRECISION NOT NULL,
  abs_upper_p90           DOUBLE PRECISION NOT NULL,
  coverage50_holdout_low  DOUBLE PRECISION,
  coverage50_holdout_high DOUBLE PRECISION,
  coverage90_holdout_low  DOUBLE PRECISION,
  coverage90_holdout_high DOUBLE PRECISION,
  factor_shift            DOUBLE PRECISION,
  n_test                  DOUBLE PRECISION,
  PRIMARY KEY (area_scale, grain, quantity, basis, size_class)
);

-- Calibration factors MODIS -> VIIRS per region
CREATE TABLE calib_factors (
  region_id             TEXT PRIMARY KEY REFERENCES regions (region_id),
  k_count_pair          DOUBLE PRECISION NOT NULL,
  k_count_aqua          DOUBLE PRECISION NOT NULL,
  k_count_terra         DOUBLE PRECISION NOT NULL,
  k_frp_pair            DOUBLE PRECISION NOT NULL,
  k_frp_aqua            DOUBLE PRECISION NOT NULL,
  k_frp_terra           DOUBLE PRECISION NOT NULL,
  used_fallback_pair    BOOLEAN NOT NULL,
  used_fallback_aqua    BOOLEAN NOT NULL,
  used_fallback_terra   BOOLEAN NOT NULL,
  n_viirs_calib         DOUBLE PRECISION NOT NULL,
  n_pair_calib          DOUBLE PRECISION NOT NULL,
  n_aqua_calib          DOUBLE PRECISION NOT NULL,
  n_terra_calib         DOUBLE PRECISION NOT NULL,
  k_count_pair_overall  DOUBLE PRECISION NOT NULL,
  k_count_aqua_overall  DOUBLE PRECISION NOT NULL,
  k_count_terra_overall DOUBLE PRECISION NOT NULL,
  calib_start           DATE NOT NULL,
  calib_end             DATE NOT NULL
);

-- Reliability of the strength class: measured vs converted class
CREATE TABLE strength_confusion (
  basis                   TEXT NOT NULL,
  measured_class          TEXT NOT NULL,
  converted_class         TEXT NOT NULL,
  n_days                  BIGINT NOT NULL,
  share_of_measured_class DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (basis, measured_class, converted_class)
);

-- Reliability of the big-fire-day flag per area scale and basis
CREATE TABLE big_fire_day_quality (
  area_scale             TEXT NOT NULL,
  basis                  TEXT NOT NULL,
  threshold_measured_mw  DOUBLE PRECISION NOT NULL,
  threshold_converted_mw DOUBLE PRECISION NOT NULL,
  recall                 DOUBLE PRECISION NOT NULL,
  "precision"            DOUBLE PRECISION NOT NULL,
  kappa                  DOUBLE PRECISION NOT NULL,
  n_events_measured      BIGINT NOT NULL,
  n_events_converted     BIGINT NOT NULL,
  n_units                BIGINT NOT NULL,
  PRIMARY KEY (area_scale, basis)
);
