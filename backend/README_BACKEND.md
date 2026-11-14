# Backend – Fire-API v3.1 in La-Brasa einbauen

## Was in diesem Ordner liegt

```
backend/
├── main.py                 App, Router, CORS, gzip
├── dtos.py, errors.py      Vertrag und Fehlerformat (aus fire-api-v3-dtos, errors.py nur um 504 erweitert)
├── core/                   config.py (Umgebung), db.py (Verbindung)
├── services/               scope.py (Gebiet + Confidence → SQL), meta.py, regions.py, series.py (daily, calendar,
│                           by-region), grid.py (count + anomaly), hotspots.py (+ export), areas.py (gezeichnete
│                           Gebiete, Tabelle areas), events.py (Ereignisse: Clustering + Index im Speicher),
│                           sync.py (Datenaktualisierung im Hintergrund: pipeline/sync_data.py)
├── routes/                 data.py (Daten-Endpunkte, u. a. POST /api/daily/sensors: Rohdetektionen pro Tag und
│                           Sensorfamilie MODIS/VIIRS, api_version 3.2), sync.py (POST/GET /api/sync)
├── assets/                 nuts2_iberia.geojson (echte NUTS-2-Grenzen, GISCO 2021)
├── tools/                  make_regions_asset.py
├── tests/test_api.py       Tests gegen die Datenbank, Erwartungswerte unabhängig per pandas aus den Parquet-Dateien
├── requirements.txt        Laufzeit
└── requirements-dev.txt    + Tests (pytest, pandas, pyarrow)
```

`routes/data.py` ersetzt die bisherigen `routes/calendar.py`, `routes/export.py` und `routes/regions.py` des Teams. Passt die Namen an oder löscht die alten Dateien, wenn ihr dieses Gerüst übernehmt.

## Einbauen

1. Ordnerinhalt in `backend/` kopieren (`dtos.py`, `errors.py`, `main.py` ersetzen).
2. `db/init/001_schema.sql`: erledigt. Ab Schema-Version 2 hat `hotspots_harmonised` die Spalte `h3_cell` (H3, Auflösung 8), die das Backend für `/api/grid` nutzt.
3. Echte Regionsgrenzen erzeugen und committen:
   ```bash
   python backend/tools/make_regions_asset.py --input data/raw/NUTS_RG_01M_2021_4326_LEVL_2.geojson
   ```
   (Die GISCO-Datei kennt ihr aus `tag_regions.py`.) Diese Datei gehört ins Git, `data/` nicht.
4. `backend/Dockerfile`: `pip install -r requirements.txt`, `WORKDIR /app`, `COPY . .`, `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`.
5. `docker-compose.yml`: der Service `backend` braucht nur `DATABASE_URL` (ist schon gesetzt) und optional `CORS_ORIGINS`.

## Starten und testen

```bash
docker compose up -d db
python pipeline/load_to_db.py                      # Parquet → Postgres
cd backend
pip install -r requirements-dev.txt
DATABASE_URL=postgresql://USER:PASS@localhost:5432/DB uvicorn main:app --reload --port 8000
# http://localhost:8000/docs
DATABASE_URL=... pytest tests -q
```

Ohne echte Daten: `python pipeline/make_fake_harmonised.py` erzeugt erfundene Parquet-Tabellen im echten Format (Zahlen sind Fantasie).

## Typen fürs Frontend

Unverändert zum Vertrag: `openapi.json` dieses Backends ist identisch mit dem aus `fire-api-v3-dtos`.
```bash
npx openapi-typescript http://localhost:8000/openapi.json --default-non-nullable false -o src/api/schema.d.ts
```
