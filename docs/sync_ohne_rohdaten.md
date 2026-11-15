# Plan: Sync ohne Rohdaten

Ziel: Auf dem Server liegen nur noch die harmonisierten Daten. `POST /api/sync` holt FIRMS, bereinigt und
harmonisiert die neuen Tage, ersetzt sie in `data/harmonised/*.parquet` und lädt sie in die DB.
Der volle Lauf (`run_pipeline.py --force`) läuft weiter lokal aus den Roh-CSVs.

## Was auf dem Server liegt

- `data/harmonised/` (ohne `csv/`)
- dazu zwei kleine Dateien, die von `processed/` nach `harmonised/` umziehen:
  - `static_mask.parquet` (17 KB): Ortsmaske für Industrie und Fackeln, gelernt aus dem Archiv
  - `satellite_coverage.parquet` (1,4 KB): Betriebsfenster je Satellit

`data/raw/`, `data/processed/` und `data/harmonised/csv/` fallen weg.

## Was gleich bleibt

- **DB:** `load_to_db.py --incremental` ersetzt schon heute nur die Tage ab dem Schnitt
  (`day_status` ganz, 9.447 Zeilen). Keine Änderung.
- **Harmonisierung:** `daily_grid`, `harmonise_daily`, `weight_hotspots` und `incremental.json` bleiben unverändert.
- **Betriebsfenster:** Die Archiv-Fenster sind fix. Nur das Ende des NRT-Fensters je Satellit rückt auf die
  neueste geholte Zeile, minus 1 Tag (Regel `solar`: dem letzten Tag fehlt die Nacht). So rechnet
  `find_satellite_coverage` auch heute für die NRT-Dateien.

## Änderungen

### 1. Zwei Dateien nach `harmonised/`

- Der volle Lauf schreibt `static_mask` und `satellite_coverage` nach `harmonised/` statt nach `processed/`
  (`clean_hotspots.py`, `run_pipeline.py`, Eintrag in `HASHED_OUTPUTS`).
- Die vorhandenen Dateien einmal von Hand verschieben.

### 2. `pipeline/ingestion/fetch_firms.py`

- Das letzte Datum je Produkt kommt aus `hotspots_harmonised.parquet` (größtes `acq_date` seiner Satelliten)
  statt aus der CSV.
- Die geholten Tage komplett in eine Übergabedatei `data/processed/fetched/<quelle>.csv` schreiben, die jedes
  Mal überschrieben wird.
- Das Abgleichen mit den vorhandenen Schlüsseln (`read_existing`) und `append_rows` fallen weg.
- `new_rows` = Zeilen nach dem bisher letzten Tag. Das API-Feld bleibt gleich.

Die Übergabedatei braucht es, weil Fetch und Harmonisierung in getrennten Python-Prozessen laufen. Sie bleibt
CSV, damit die Typen über das bestehende `convert_csv_to_raw_parquet` exakt so entstehen wie heute. Nach dem
Sync wird sie gelöscht und ist kein Datenbestand.

### 3. `harmonisation/run_pipeline.py` → `run_incremental`

- `ingest_new_nrt_rows` und der Zeilenzähler in `pipeline_state.json` fallen weg.
- Die Übergabedateien mit `convert_csv_to_raw_parquet` typisieren. Der Schnitt ist das früheste `acq_date` der
  geholten Zeilen.
- `clean_hotspots_since(config, since, raw)`:
  - Die Rohzeilen kommen als Parameter rein.
  - Der alte Bestand kommt aus `hotspots_harmonised` ohne die 6 Spalten `in_series_n`, `in_series_frp`,
    `weight_n`, `weight_frp`, `basis_count`, `basis_frp`. Er hat dieselben Zeilen und Spalten wie
    `hotspots_clean`.
  - Die Maske kommt aus `harmonised/`.
- Betriebsfenster:
  - `harmonised/satellite_coverage.parquet` lesen.
  - Das NRT-Ende je Satellit auf die neueste geholte Zeile − 1 Tag setzen.
  - Die Datei zurückschreiben.
  - `run_stage_daily_grid` bekommt dafür einen optionalen Parameter `coverage`, sonst ruft es wie bisher
    `find_satellite_coverage` auf.
- Zum Schluss `data/processed/fetched/` löschen.

### 4. `pipeline/sync_data.py`

Nur Docstring und Aufruf anpassen.

### 5. Doku

Die betroffenen Zeilen in `harmonisation/README.md`, `harmonisation/CONTEXT.md` und
`harmonisation/docs/raw_sources.md` anpassen.

## Prüfung

- Keine neuen Tests. Die bestehenden laufen lassen: `harmonisation/tests`, `pipeline/tests`, `backend/tests`.
- Ein echter Sync lokal mit einer Kopie, in der nur `harmonised/` liegt. Dafür braucht es `FIRMS_MAP_KEY` und die
  lokale DB.

## Folgen

- **Voller Lauf lokal:** `--force` liest weiter die CSVs. Was der Sync geholt hat, steht dann nicht in den CSVs.
  Für einen vollen Lauf mit aktuellen Daten neue NRT-CSVs herunterladen, so wie heute schon die Archive.
- **Lücken:** Die FIRMS-API liefert höchstens die letzten 31 Tage. Wird länger nicht synchronisiert, gibt es eine
  Lücke. Wie heute gibt es dann eine Warnung, und die Lücke lässt sich nur lokal mit einem Archiv-Download
  schließen.
