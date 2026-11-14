-- Runs automatically on the first start of an EMPTY database volume.

CREATE TABLE regions (
  region_id TEXT PRIMARY KEY,                       -- NUTS-2 code, e.g. PT11
  name      TEXT NOT NULL,
  country   CHAR(2) NOT NULL CHECK (country IN ('ES', 'PT'))
);

-- Raw MODIS detections (Terra, Aqua)
CREATE TABLE modis_hotspots (
  id          BIGSERIAL PRIMARY KEY,
  latitude    REAL     NOT NULL,
  longitude   REAL     NOT NULL,
  brightness  REAL,                                 -- original value
  scan        REAL,
  track       REAL,
  acq_date    DATE     NOT NULL,
  acq_time    CHAR(4)  NOT NULL
              CHECK (acq_tBIGSERIALime ~ '^([01][0-9]|2[0-3])[0-5][0-9]$'),   -- HHMM, UTC, pad with zfill(4)
  satellite   TEXT     NOT NULL,                    -- Terra or Aqua
  instrument  TEXT     NOT NULL DEFAULT 'MODIS',
  sensor      TEXT     NOT NULL DEFAULT 'MODIS',
  confidence  SMALLINT CHECK (confidence BETWEEN 0 AND 100),
  version     TEXT,                                 -- e.g. 6.1NRT or 61.03
  frp         REAL,
  daynight    CHAR(1)  CHECK (daynight IN ('D', 'N')),
  -- type     SMALLINT,                             -- optional, only present in SP data
  country     CHAR(2),
  region_id   TEXT REFERENCES regions(region_id),
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  provisional BOOLEAN GENERATED ALWAYS AS
              (COALESCE(right(version, 3) = 'NRT', FALSE)) STORED,
  UNIQUE (satellite, acq_date, acq_time, latitude, longitude)
);

-- Raw VIIRS detections (S-NPP, NOAA-20, NOAA-21)
CREATE TABLE viirs_hotspots (
  id          BIGSERIAL PRIMARY KEY,
  latitude    REAL     NOT NULL,
  longitude   REAL     NOT NULL,
  brightness  REAL,                                 -- original bright_ti4
  scan        REAL,
  track       REAL,
  acq_date    DATE     NOT NULL,
  acq_time    CHAR(4)  NOT NULL
              CHECK (acq_time ~ '^([01][0-9]|2[0-3])[0-5][0-9]$'),
  satellite   TEXT     NOT NULL,                    -- N (S-NPP), N20, N21
  instrument  TEXT     NOT NULL DEFAULT 'VIIRS',
  sensor      TEXT     NOT NULL DEFAULT 'VIIRS',
  confidence  CHAR(1)  CHECK (confidence IN ('l', 'n', 'h')),
  version     TEXT,                                 -- e.g. 2.0NRT or 2
  frp         REAL,
  daynight    CHAR(1)  CHECK (daynight IN ('D', 'N')),
  -- type     SMALLINT,                             -- optional, only present in SP data
  country     CHAR(2),
  region_id   TEXT REFERENCES regions(region_id),
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  provisional BOOLEAN GENERATED ALWAYS AS
              (COALESCE(right(version, 3) = 'NRT', FALSE)) STORED,
  UNIQUE (satellite, acq_date, acq_time, latitude, longitude)
);

-- Harmonized series on the VIIRS scale:
-- MODIS up to 2012-01-31 (converted), VIIRS from 2012-02-01.
-- Keep the dates in sync with pipeline/config.py.
CREATE TABLE harmonized_hotspots (
  id          BIGSERIAL PRIMARY KEY,
  modis_id    BIGINT REFERENCES modis_hotspots(id),
  viirs_id    BIGINT REFERENCES viirs_hotspots(id),
  latitude    REAL     NOT NULL,
  longitude   REAL     NOT NULL,
  brightness  REAL     NOT NULL,                    -- harmonized, VIIRS scale
  scan        REAL,
  track       REAL,
  acq_date    DATE     NOT NULL,
  acq_time    CHAR(4)  NOT NULL
              CHECK (acq_time ~ '^([01][0-9]|2[0-3])[0-5][0-9]$'),
  satellite   TEXT     NOT NULL,
  instrument  TEXT     NOT NULL,
  sensor      TEXT     NOT NULL,                    -- sensor of origin: MODIS or VIIRS
  confidence  CHAR(1)  CHECK (confidence IN ('l', 'n', 'h')),
  version     TEXT,
  frp         REAL,
  daynight    CHAR(1)  CHECK (daynight IN ('D', 'N')),
  weight      REAL     NOT NULL DEFAULT 1 CHECK (weight > 0),   -- open decision, see team notes
  country     CHAR(2),
  region_id   TEXT REFERENCES regions(region_id),
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  provisional BOOLEAN GENERATED ALWAYS AS
              (COALESCE(right(version, 3) = 'NRT', FALSE)) STORED,
  CONSTRAINT chk_one_source CHECK
    ((modis_id IS NOT NULL)::int + (viirs_id IS NOT NULL)::int = 1),
  CONSTRAINT chk_source_period CHECK (
    (modis_id IS NOT NULL AND acq_date <= DATE '2012-01-31') OR
    (viirs_id IS NOT NULL AND acq_date >= DATE '2012-02-01')
  )
);

CREATE INDEX ON modis_hotspots      (region_id, acq_date);
CREATE INDEX ON viirs_hotspots      (region_id, acq_date);
CREATE INDEX ON harmonized_hotspots (region_id, acq_date);
CREATE UNIQUE INDEX ON harmonized_hotspots (modis_id) WHERE modis_id IS NOT NULL;
CREATE UNIQUE INDEX ON harmonized_hotspots (viirs_id) WHERE viirs_id IS NOT NULL;