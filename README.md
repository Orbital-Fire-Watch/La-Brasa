# La Brasa

A consistent 20+ year fire calendar for the Iberian Peninsula, built by harmonizing MODIS and VIIRS satellite hotspots.

Built for the NASA Space Apps Challenge 2026, challenge *Harmonization of MODIS and VIIRS Hot Spots*.

---

## Project summary

Satellites have tracked active fire hotspots for more than two decades, but the record is split across two sensor families. MODIS (Terra and Aqua, since 2000) is coarser at about 1 km and is nearing the end of its life. VIIRS (since 2012) is finer at 375 m and detects more small fires, with different overpass times and sensitivity. Side by side, the raw counts show a jump around 2012 that reflects the instrument and not the fires.

Orbital Firewatch converts the MODIS record onto the VIIRS scale, so that the sensor of origin no longer matters. The result is one continuous series, shown as a burning-activity calendar for any selected region of Spain and Portugal.

- **Calibrate once.** The relationship between MODIS and VIIRS (S-NPP) is estimated from the period in which both sensors observed in parallel (2012 onwards). The parameters are stored.
- **Apply, do not recompute.** New daily data is fitted with the stored parameters, so historical values do not shift every night.
- **Keep the originals.** Raw MODIS and VIIRS tables are kept next to the harmonized table, so the product can show harmonized and non-harmonized data side by side.
- **Two countries, one view.** Every hotspot is assigned to a country and a regional unit, so planners in Spain and Portugal see their own territory and can compare.

## Aim

Give emergency planners, firefighters, scientists and land managers a consistent, sensor-independent view of fire activity, so they can:

- see which months and years had the most burning in their region,
- compare the current month against the historical median,
- see how much the harmonization changes the picture,
- export the results as CSV.

## Conventions

### Directories and files
- directories separated with dashes ("-")
- files separated with underscores ("_")
- exception: names fixed by tools, such as `docker-compose.yml` and `README.md`

### Branches
- `feature/<description>` (for new features)
- `fix/<description>` (for bug fixes)
- `docs/<description>` (for documentation changes)

### Commits
Format: `<TAG>: <short description>`

| Tag | Meaning | Example |
|---|---|---|
| `ADD` | add something new | `ADD: tag_regions script for country and region_id` |
| `CHG` | change or improve existing code | `CHG: harmonize brightness with stored calibration` |
| `FIX` | fix a bug | `FIX: keep acq_time as text to preserve leading zeros` |
| `DEL` | remove something | `DEL: remove unused fake data module` |
| `DOC` | documentation only | `DOC: add data model section to README` |
| `REF` | restructure code, behavior unchanged | `REF: split API routes into separate files` |

- English, imperative mood, no trailing period, under 72 characters
- one logical change per commit
- never commit data files, `.env` files or keys

## Usage

Requirements: Git and Docker Desktop.

```bash
git clone <repository-url>
cd orbital-firewatch

cp .env.example .env        # then add your own FIRMS MAP_KEY
docker compose up --build
```

Default addresses (see `docker-compose.yml` if the ports were changed):

| Service | Address |
|---|---|
| Frontend | http://localhost:8080 |
| Backend API | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |

A free FIRMS MAP_KEY can be requested at https://firms.modaps.eosdis.nasa.gov/api/map_key/. It is only needed for the data update, not to run the app on existing data. The `.env` file is never committed.

### Updating the data

The update script continues from the latest date stored in the database:

1. Read the last stored acquisition date per sensor.
2. Request everything from two to three days before that date up to today, in blocks of at most five days (the limit of the FIRMS area API).
3. Add region information, apply the stored calibration, and upsert into the database.

Writes are upserts, so running the update twice is safe. Provisional near-real-time records are marked and replaced when final data becomes available.

```bash
docker compose run --rm updater
```

In production this runs as a nightly scheduled job. On a laptop, run it once before use to catch up on missed days.

---

## Architecture

```
FIRMS CSV downloads (MODIS, S-NPP)          FIRMS API (daily updates)
              |                                       |
              +------------------+--------------------+
                                 |
                         tag_regions.py        add country and region_id
                                 |
                          harmonize.py         MODIS -> VIIRS scale
                                 |
                          load_to_db.py        upsert into PostgreSQL
                                 |
        +------------------------+------------------------+
        |                        |                        |
  modis_hotspots          viirs_hotspots        harmonized_hotspots
        +------------------------+------------------------+
                                 |
                      monthly_comparison (view)
                                 |
                          FastAPI backend
                                 |
                            Web frontend
```

| Component | Technology |
|---|---|
| Database | PostgreSQL |
| Backend | Python, FastAPI |
| Data processing | Python, pandas, GeoPandas |
| Frontend | HTML, TypeScript, Leaflet |
| Packaging | Docker Compose |

## Repository structure

```
.
├── docker-compose.yml
├── .env.example
├── .gitignore
├── db/
│   └── init/
│       ├── 001_schema.sql        Table definitions
│       └── 002_views.sql         Views
├── backend/                      FastAPI application
│   ├── Dockerfile
│   ├── main.py
│   ├── db.py                     Database connection
│   ├── test_data.py
│   ├── requirements.txt
│   └── routes/
│       ├── calendar.py
│       ├── export.py
│       └── regions.py
├── frontend/                     Web interface
│   ├── Dockerfile
│   ├── index.html
│   ├── map.ts
│   ├── charts.ts
│   └── assets/
├── pipeline/
│   ├── tag_regions.py            Adds country and region_id to CSV files
│   ├── harmonize.py              MODIS to VIIRS harmonization
│   ├── load_to_db.py             Loads CSV files into PostgreSQL
│   ├── fetch_firms.py            Retrieves new data from the FIRMS API
│   ├── update_daily.py           Catch-up update from the last stored date
│   ├── requirements.txt
│   ├── notebooks/
│   └── params/
│       └── calibration.json      Stored calibration parameters
└── data/                         Local data, not tracked by Git
    ├── DATA_README.md
    ├── raw/
    ├── tagged/
    ├── harmonized/
    └── boundary-files/
```

## Data model

| Table | Content |
|---|---|
| `regions` | Regional units with their country |
| `modis_hotspots` | Original MODIS detections (Terra, Aqua) |
| `viirs_hotspots` | Original VIIRS detections (S-NPP) |
| `harmonized_hotspots` | All detections on the VIIRS scale, each linked to its source row |
| `monthly_comparison` | View: counts per region and month for MODIS, VIIRS and harmonized data |

Each hotspot table carries position, brightness, scan and track, acquisition date and time (UTC), satellite, instrument, confidence, version, fire radiative power, day or night flag, country, region, and the time of ingestion. Regional units follow the Eurostat NUTS-2 classification.

## API

Planned endpoints. Responses are JSON unless noted.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Service status |
| `GET /api/regions` | Available regions with their country |
| `GET /api/calendar?region=...&from=...&to=...` | Monthly series for the region: MODIS, VIIRS and harmonized, with historical median and anomaly |
| `GET /api/export.csv?region=...&from=...&to=...` | CSV export of the selected search |

## Limitations

- The calibration is an estimate. Harmonized values are approximations, and the relationship between the sensors can vary by region, season and fire type.
- Satellite hotspots show thermal anomalies, not burned area. They include agricultural burns and other heat sources.
- Coverage is the mainland Iberian Peninsula. The Canary Islands, the Azores, Madeira, Ceuta and Melilla are excluded.
- Near-real-time data is provisional and can change.

## Data sources and credits

- Active fire detections: NASA FIRMS (Fire Information for Resource Management System), MODIS and VIIRS. https://firms.modaps.eosdis.nasa.gov
- Administrative regions: Eurostat GISCO, NUTS boundaries. Please follow the source's terms of use and attribution.
- Challenge: NASA Space Apps Challenge 2026.

## Team

Orbital Firewatch, five members.

| Area | Members |
|---|---|
| Harmonization and validation | [Name], [Name] |
| Frontend and design | [Name], [Name] |
| Infrastructure, API and data loading | [Name] |

## License

[To be decided. Check the Project Submission Guide for the requirements on open-source code.]