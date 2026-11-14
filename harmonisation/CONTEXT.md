# Projektkontext: Harmonisierung FIRMS MODIS → VIIRS (NASA Space Apps 2026)

Stand: 14.11.2026. Diese Datei fasst alles zusammen, was in der bisherigen Arbeit mit Claude passiert ist und
entschieden wurde. Sie ist dafür gedacht, einen neuen Chat ohne Informationsverlust zu beginnen.
**Für einen neuen Chat:** Diese Datei lesen lassen, dann `harmonisation_daily/docs/pipeline_overview.html` und
`harmonisation_daily/docs/column_guide.html` (oder `data_dictionary.md`).

---

## 0. Aktueller Stand (14.11.2026 nachmittags, Schema-Version 2) – zuerst lesen

Die Abschnitte 1 bis 10 beschreiben die Vorgeschichte (Version 2 mit SNPP als einziger VIIRS-Referenz, alte Pfade unter
`Daten_Satellit/`). Wo sie diesem Abschnitt widersprechen, gilt dieser Abschnitt.

- **Ort:** Pipeline in `La-Brasa/harmonisation/` (Git-Repo `La-Brasa`, Branch `data_harmonisation`). **Niemals committen**,
  der Nutzer committet selbst. Daten in `La-Brasa/data/` (nicht in Git): `raw/<produkt>/`, `processed/`, `harmonised/`.
- **Rohdaten:** `data/raw/modis/`, `viirs_snpp/` (Archiv aus dem ZIP, ohne beschädigte Zeile), `viirs_noaa20/` (`DL_FIRE_J1V-C2_848091`),
  `viirs_noaa21/` (`DL_FIRE_J2V-C2_848092`). Herkunft und Prüfsummen: `docs/raw_sources.md`. Der erste, unvollständige
  NOAA-Download liegt in `Daten_Satellit/NASA_SPACEAPP/Data_new_false/` und wird nicht verwendet.
- **VIIRS-Referenz = Mittel der aktiven VIIRS-Satelliten** (SNPP ab 20.01.2012, NOAA-20 ab 01.04.2018, NOAA-21 ab 01.03.2023):
  `n_viirs`, `frp_viirs`, `viirs_operating`. Gewicht je VIIRS-Punkt 1/k. Rohzahlen je Satellit bleiben (`n_snpp`, `n_noaa20`, `n_noaa21`).
- **Untersuchungsregionen** (`nuts.study_regions`): Alle Satelliten zählen nur in den 21 NUTS-2-Regionen der App
  (Festland-Spanien mit Balearen, Portugal). Die Downloads reichen verschieden weit, diese Regionen decken alle ganz ab.
- **Kalibrierung und Fehlermodell gegen SNPP allein** (`calibration.reference_satellites`), Ortsmaske je Sensor
  (`static_sources.mask_training_sensors`). Beides aus Iteration 1 der Erweiterung.
- **Neu:** `h3_cell` (H3, Auflösung 8) in `hotspots_harmonised`. `schema_version: 2` in Config und `manifest.json`.
- **KPIs:** alle 42 erfüllt (34 bisherige, unverändert gegenüber SNPP allein, dazu N1a–c, N2, N3, N4a–b, N5).
- **Datenbank:** `La-Brasa/db/init/001_schema.sql` und `pipeline/load_to_db.py` (prüft `SCHEMA_VERSION = 2`) angepasst,
  Modell in `db/docs/data_model.md`. Bestehende Datenbank neu anlegen: `docker compose down -v`.
- **Dokumentation:** `docs/viirs_extension.md` (für das Team), `docs/viirs_extension.html` (Entstehung mit Zahlen),
  `docs/pipeline_overview.html`, `docs/column_guide.html`, `docs/data_dictionary.md`, `docs/iteration_log.md`, `docs/raw_sources.md`.
- **Voranalyse der Erweiterung:** `data_analysis/09_viirs_satellites.py` → `results/viirs_satellites.json`.
- **Ausführen:** `cd La-Brasa/harmonisation && .venv/bin/python run_pipeline.py` (≈ 90 s, 54 Tests).
  `.venv` neu anlegen mit `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (enthält jetzt `h3`).
- **Offene Punkte:** siehe `docs/viirs_extension.md`, Abschnitt „Offene Punkte“ (Bänder gemessener Tage, Ausfälle einzelner
  Satelliten, H3-Auflösung als Teamentscheidung).

## 1. Projekt und Aufgabe

- **Hackathon:** NASA Space Apps Challenge 2026, 14.–15.11.2026, Challenge „MODIS and VIIRS Hot Spots“ (FIRMS-Daten).
- **Ziel des Teams:** Ein Frontend mit **Karte und Kalender zur Brandgefahr**. Später auch eine Vorhersage.
- **Unser Teil (dieser Ordner): nur die Harmonisierung** der Daten und ihre saubere Bereitstellung. Keine Vorhersage,
  keine Wetterdaten, kein Frontend.
- **Anforderungen des Teams an die Daten:**
  - A1: Tagesauflösung, an einzelnen Tagen soll die **Stärke** der Feuer sichtbar sein.
  - A2: Frei gezeichnete Fläche oder lat/lon-Eingabe, dazu **CSV-Download** der Hotspots einer Suche.
  - A3: **Aktueller Monat gegen historischen Median.**
  - A4: **Fehlerrate mitliefern**, damit das Frontend Wert und Unsicherheit zeigen kann.
- Stündliche Daten sind nicht möglich: Terra, Aqua und SNPP sind polarumlaufend und überfliegen eine Stelle nur
  zweimal am Tag (Aqua/SNPP ≈ 13:30 und 1:30 Ortszeit, Terra ≈ 10:30 und 22:30). Für echte Stundendaten bräuchte
  man geostationäre Satelliten (für Europa Meteosat), die nicht in den Daten sind.

## 2. Ordner unter `/home/leni/Projekte/Daten_Satellit`

| Ordner / Datei | Inhalt | Status |
|---|---|---|
| `NASA_SPACEAPP/DL_FIRE_M-C61_845369/` | MODIS (Terra + Aqua) Iberien, Archiv 11/2000–08/2026 und NRT 09–11/2026 | Quelldaten |
| `NASA_SPACEAPP/DL_FIRE_SV-C2_845370/` | VIIRS SNPP Iberien, Archiv 01/2012–07/2026 und NRT 08–11/2026 | Quelldaten, **eine Zeile beschädigt** (siehe 9) |
| `NASA_SPACEAPP/*.zip` | Original-Downloads, intakt | Sicherung |
| `DL_FIRE_*_8350xx/` (4 Ordner) | Weltweite Daten aller 5 Satelliten (Terra, Aqua, SNPP, NOAA-20, NOAA-21), 17.10.2025–17.10.2026, 57 Mio. Zeilen | nur für die Gegenprobe benutzt |
| `data_analysis/` | **Voranalyse** (Skripte 00–08, Bericht `harmonisierung_bericht.html`) | fertig |
| `harmonisation_pipeline/` | **Version 1:** Pipeline auf Monatsebene (NUTS-2 × Monat) | fertig, unverändert lassen |
| `harmonisation_daily/` | **Version 2 (aktuell):** Tagesebene, Punktgewichte, Fehlermodell, Aggregationsmodul | fertig, alle KPIs erfüllt |
| `CONTEXT.md` | diese Datei | |

`NASA_SPACEAPP/merge_firms.py` (ein früher Versuch, CSVs nach SQLite zu mergen) und ein Ordner
`DL_FIRE_SV-C2_845370 (2)` sind irgendwann verschwunden. Beides wird nicht gebraucht.

## 3. Die Daten (was man wissen muss)

- **Eine Zeile = ein beim Überflug als heiß erkanntes Pixel**, kein Feuer und keine Fläche.
- Iberien-Download: 573.462 Zeilen. Box Lat 36–43,8, Lon −9,5–3,3. Enthält Spanien, Portugal, drei Regionen in SW-Frankreich.
- **Spalten der CSVs (beide Sensoren gleich benannt):** latitude, longitude, brightness, scan, track, acq_date, acq_time
  (UTC, HHMM-Text), satellite, instrument, confidence, version, bright_t31, frp, daynight, type (fehlt im NRT).
- `confidence`: MODIS Zahl 0–100, VIIRS l/n/h. VIIRS-„h“ heißt nur „Kanal bei 367 K gesättigt“.
- `type`: 0 Vegetationsfeuer, 1 Vulkan, 2 statische Landquelle (Industrie, Fackeln), 3 Offshore.
- `version`: MODIS 6.03 (bis 2022), 61.03 (ab 2023), 6.1NRT. VIIRS 2, 2.0NRT.
- `instrument` ist bei SNPP „SNPP“ statt „VIIRS“ (unzuverlässig).

## 4. Zentrale Befunde der Voranalyse (`data_analysis/`)

Alle Zahlen Iberien, `type` = 0, Kalibrierfenster 02/2012–12/2021.

1. **Der Unterschied liegt darin, welche Feuer erkannt werden.** Aqua erkennt ein VIIRS-Feuercluster erst ab ≈ 34 MW (Tag)
   bzw. 21 MW (Nacht) mit 50 % Wahrscheinlichkeit. Aqua sieht nur 24 % der VIIRS-Cluster, die aber 83 % der Strahlungsleistung
   enthalten. 43 % aller VIIRS-Erkennungen liegen in Clustern, die Aqua gar nicht meldet.
2. **Zählfaktor:** SNPP meldet 6,0× so viele Erkennungen wie Aqua allein, **≈ 3,0× wie Aqua + Terra**. Tag 4,1×, Nacht 11×
   (gegenüber Aqua). Je Region 4,5–10 (gegen Aqua) bzw. 2,5–5,1 (gegen Aqua + Terra).
3. **FRP-Summe:** SNPP/Aqua ≈ 1,04 (fast gleich). **Aqua + Terra zusammen liegt 1,6× über SNPP → Faktor 0,64.**
   Weltweit nicht übertragbar (Faktor 0,9–3,3).
4. **0,25°-Raster ist als Vergleichsebene zu fein:** R² (log) je Zelle und Monat 0,37, je NUTS-2 und Monat 0,73, je Jahr 0,89.
   Pro Tag NUTS-2 nur 0,39.
5. **Einfach schlägt aufwendig:** 17 Umrechnungen getestet (Faktoren je Monat, Tag/Nacht, Poisson-Modelle, Gradient
   Boosting, Quantil-Mapping, FRP-Klassen-Gewichte). **Ein Faktor je Region** traf die VIIRS-Klasse am besten (64 %).
6. **Statische Quellen:** 32 % der SNPP-Nacht-Erkennungen sind statisch, bei Aqua 4 %. Im NRT fehlt `type` → Ortsmaske
   aus dem Archiv (Recall ≈ 93–95 %, 1,5–1,7 % echte Feuer fälschlich entfernt).
7. **Bahndrift ab 2022:** Aqua misst 2026 ≈ 14:53 statt 13:05 Ortszeit (+108 min), Terra 9:21 statt 11:01 (−101 min).
   SNPP stabil. Darum Kalibrierung nur 2012–2021 und kein MODIS mehr nach 2021.
8. **Rauschboden:** Zwei baugleiche VIIRS-Instrumente (NOAA-20 vs. SNPP) weichen in der 1°-Zelle × Monat schon um
   × 1,18 (weltweit) bis × 1,27 (Iberien) ab. NOAA-20/21 liegen im Mittel innerhalb weniger Prozent von SNPP.
9. **Tagesebene:** MODIS meldet an ≈ 60 % der Tage mit VIIRS-Feuer (Region × Tag) **nichts**. Tagesfehler × 2,08,
   Woche × 2,0, Monat × 1,5, Jahr × 1,12.
10. **Fehler hängt von der Größe der Zahl ab** (Region × Monat): × 3,0 bei umgerechnet 0, × 2,3 bei 1–5, × 1,65 bei 6–20,
    × 1,34 bei 21–100, × 1,26 bei 101–500, × 1,14 darüber. Ein fester Faktor × 1,46 wäre für kleine Zahlen viel zu optimistisch.
11. **Großfeuer-Tage** (FRP-Summe ≥ 100 MW je Region × Tag): MODIS findet 62–67 %, Kappa ≈ 0,62–0,67. Stärkeklasse ≥ 500 MW
    wird zu ≈ 72–76 % richtig eingestuft. Mittlere Tage (10–100 MW) schlecht.
12. **Tagesstärke:** FRP-Summe je Tag ist die einzige vergleichbare Größe (R² 0,59 mit Aqua allein, 0,52 mit Aqua + Terra).
    Das stärkste Einzelpixel ist nicht vergleichbar (VIIRS-Pixel im Median 0,45× so stark).
13. **Klimaprofil (typischer Jahresverlauf):** Aus MODIS umgerechnet gegen VIIRS, ±7 Tage geglättet: R² 0,94, Fehler × 1,24.
    Ungeglättet nur 0,75.

## 5. Getroffene Entscheidungen (nicht neu verhandeln)

**Spalten**
- **Raus:** `brightness`, `bright_t31` (nicht vergleichbar, VIIRS sättigt bei 367 K, Aussagen kommen aus `frp`),
  `instrument`, `version` (ersetzt durch `sensor`, `source`), `type` nach dem Filter, `static_filter_basis` (= `source`).
- **Behalten:** latitude, longitude, acq_date, acq_time, satellite, daynight, frp, scan, track,
  `confidence` (als `confidence_raw` + `confidence_class`, Nutzer wollte sie ausdrücklich behalten).
- **Neu:** sensor, source, region_id (NUTS-2 2021, lokal per Punkt-in-Polygon, keine API), country (= erste 2 Zeichen von
  region_id), frp_class (low < 10, mid 10–50, high ≥ 50 MW je Pixel), confidence_class, local_solar_hour, hotspot_id,
  acq_datetime_utc, obs_date, cell_id (0,25°), pixel_area_km2.

**Filter:** Nur `type` = 0. Im NRT (ohne type) Ortsmaske aus dem Archiv. `WHERE type = 0` würde das NRT komplett löschen.

**Harmonisierung**
- VIIRS SNPP ist ab dem 20.01.2012 die Referenz (gemessen). Davor MODIS × Faktor je Region. Sensoren nie addieren.
- Anzahl vor 2012: (Aqua + Terra) × Faktor. Stärke (FRP) vor 2012: **Aqua allein** × Faktor (H1). Vor 04.07.2002 nur Terra.
- Kalibrierfenster 02/2012–12/2021, Faktor = Summe VIIRS / Summe MODIS je Region, Rückfall auf Gesamtfaktor unter 300 MODIS-Erkennungen.
- Ab 2022 kein MODIS (Drift). Tage ohne VIIRS danach haben keinen Wert.
- **Kanonischer Datensatz ist Region × Tag.** Woche/Monat/Jahr werden nicht gespeichert, sondern über eine getestete
  Funktion im getrennten Modul `aggregation/` abgeleitet (Wunsch des Nutzers: „Pipeline liefert daily, Aggregation lädt und rechnet hoch“).
- Unvollständige Zeiträume bekommen keinen Wert. 0 (kein Feuer) wird von leer (kein Satellit / keine Daten) unterschieden.
- Fehlerrate heißt `uncertainty`, nicht `confidence`.
- Wahrscheinlichkeiten im Klimaprofil (Anteil Jahre mit Feuer) **nur aus VIIRS-Jahren**.

## 6. Version 2: `harmonisation_daily/` (aktueller Stand)

**Ausführen**
```
cd Daten_Satellit/harmonisation_daily
.venv/bin/python run_pipeline.py              # alle Stufen (~40 s inkl. Tests), Unverändertes wird übersprungen
.venv/bin/python run_pipeline.py --force      # alles neu, prüft Determinismus
.venv/bin/python -m pytest -q tests aggregation/tests     # 47 Tests
.venv/bin/python data_analysis/experiments/evaluate_hypotheses.py       # H1–H5
.venv/bin/python docs/build_docs.py                       # Doku neu bauen
```
Eigene venv (`.venv`, Pakete in `requirements.txt`). Rückgabewert 1, wenn eine KPI-Schwelle verfehlt wird.

**Struktur**
- `run_pipeline.py` – Orchestrator, Stufen: ingest → clean → daily_grid → calibrate → quantify_uncertainty →
  harmonise_daily → weight_hotspots → export_csv → test → validate.
- `pipeline_config.yaml` – alle Parameter, Schwellen, KPI-Grenzen.
- `pipeline/column_catalogue.py` – **eine Quelle** für Schema-Prüfung, `data_dictionary.md` und `column_guide.html`.
- `pipeline/data_loading/` – ingest_csv_to_parquet, clean_hotspots, static_source_mask, assign_region,
  classify_hotspots, derive_hotspot_columns, schema_validation.
- `pipeline/algorithms/` – daily_grid, calibration_factors, harmonise_daily, hotspot_weights, uncertainty_model,
  event_quality, validation_kpis, drift_monitor.
- `aggregation/` (nicht im Orchestrator, schreibt nie in `data/`) – loading (`load_table`), periods, roll_up
  (`roll_up_daily`, `add_uncertainty_to_periods`), uncertainty (`estimate_uncertainty`, `area_scale_for`),
  hotspot_queries (`select_hotspots`, `aggregate_hotspots`, `write_hotspots_csv`), climatology
  (`build_day_of_year_climatology`), month_to_date (`month_to_date_vs_history`).
- `tests/`, `aggregation/tests/`, `data_analysis/experiments/`, `docs/`.

**Ausgaben in `data/harmonised/`**
| Datei | Zeile | Zweck |
|---|---|---|
| `activity_daily_harmonised.parquet` | Region × Tag (217.281 Zeilen, 23 Regionen, 2001-01-01 bis 2026-11-12) | kanonischer Datensatz: Rohzahlen je Satellit, `basis_count`/`basis_frp`, `n_harm`, `frp_harm`, Faktoren, `strength_class` (minor <10, moderate 10–100, strong 100–500, extreme ≥500 MW), `big_fire_day`, Bänder `*_lo50/hi50/lo90/hi90`, `reliability` (measured / converted_solid ≥100 / converted_rough), `is_complete_day`, `possible_gap` |
| `hotspots_harmonised.parquet` | Erkennung (488.599, davon 389.758 in der Reihe) | Karte, Flächen, CSV: alle Punktspalten + `in_series_n/frp`, `weight_n`, `weight_frp`, Basis. SUM(weight_n) über Region × Tag = n_harm exakt |
| `day_status.parquet` | Tag (9.447) | Betrieb je Satellit, Basis, vollständig, vorläufig (NRT), possible_gap |
| `quality_by_scale.parquet` | Fläche (cell/nuts2/country/all) × Zeitschritt (day–year) × Größe × Basis × Größenklasse | Fehlermodell aus Kreuzvalidierung, inkl. absoluter Obergrenze für umgerechnet 0 und Holdout-Abdeckung |
| `calib_factors.parquet` | Region | Faktoren Paar/Aqua/Terra für Anzahl und FRP |
| `strength_confusion.parquet`, `big_fire_day_quality.parquet` | | Verlässlichkeit von Stärkeklasse und Großfeuer-Tag |
| `kpi_report.json`, `manifest.json`, `pipeline_state.json`, `calib_summary.json` | | Prüfung, Herkunft, Hashes |
| `csv/*.csv` | wie die Parquet-Dateien | **CSV-Kopien aller 7 Tabellen fürs Frontend** (Stufe `export_csv`, Modul `pipeline/csv_export.py`, abschaltbar über `export.csv`). UTF-8, Komma-getrennt, Dezimalpunkt, Datum `2025-08-01`, Zeitstempel `2025-08-01T13:20:00` (UTC), `true`/`false`, leeres Feld = kein Wert (≠ 0). Größen: hotspots 103 MB, daily 48 MB, Rest < 1 MB. Parquet ist die Quelle, CSVs werden bei jedem Lauf neu geschrieben. |

**Gesamtfaktoren:** Anzahl Paar 2,996, Aqua 5,98, Terra 6,00. FRP Paar 0,641, Aqua 1,178.
**Zeilenbilanz:** 573.462 gelesen = 488.599 behalten + 84.863 verworfen (type_2 81.609, type_3 1.799, static_mask 1.454, invalid_value 1).
**Tage:** 5.401 VIIRS gemessen, 3.487 Aqua+Terra umgerechnet, 549 nur Terra, 10 ohne Wert (03.–12.11.2026), 15 possible_gap, 94 vorläufig.

**KPI-Stand: alle 34 Prüfungen erfüllt** (Schwellen vorab in der Config, nie gesenkt; Kreuzvalidierung „ein Jahr auslassen“ 2012–2021,
bewertet auf 18 Regionen mit ≥ 2.000 VIIRS-Erkennungen):
D1 Tag × 2,08 / p90 × 6,0 · D2 Bias 0,1 % · D3 Monat × 1,46, Klasse 63,7 %, Kappa 0,44 · D4 FRP-R² 0,59, Verhältnis 0,975 ·
D5 Großfeuer Kappa 0,67, Recall 67 %, Precision 70 % · D6 Zelle Kappa 0,63 · D7 extreme 76 % · D8 Klimaprofil R² 0,945,
× 1,23, Korrelation Median 0,93 / Min 0,83 · D9 p = 0,21 · D10/D11 exakt (≈1e-15) · U1 50-%-Band 0,432–0,578 (knapp) ·
U2 90-%-Band 0,881–0,916 · U3 Stabilität 0,088 · M1 Maske 92,6 % / 1,5 % · M2 Region 99,998 % · S1, I1a–d erfüllt.

**Hypothesen** (`data_analysis/experiments/hypothesis_results.json`):
- H1 Stärke aus Aqua allein: bestätigt (FRP-R² 0,59 vs 0,52).
- H2 Sonnendatum statt UTC (eine Nacht auf einem Datum): Anzahl besser, Stärke schlechter (8 von 10 Jahren) → **nicht übernommen**, umschaltbar `daily.date_assignment`.
- H3 eigene Großfeuer-Schwelle für umgerechnete Tage: **80 MW übernommen** (gleicht Recall/Precision aus).
- H4 (im Auftrag nicht definiert, gelesen als Faktor für Juni–September): kleiner Gewinn, nicht übernommen – Entscheidung fürs Team.
- H5 Stärke nur aus Tag-Überflügen: nicht übernommen.

**Iterationen** (`docs/iteration_log.md`): Iteration 1 verfehlte U3 und deckte einen Messfehler (Mitteln über beide
Prüfrichtungen) auf. Iteration 2: FRP-Größenklassen 0–10 und 10–100 zusammengelegt, H3 = 80 MW → alles erfüllt, Stopp.

**Dokumentation**
- `docs/pipeline_overview.html` – Aufbau, Funktionskatalog, gedroppte Spalten, Fehlermodell, KPIs, Hypothesen.
  Artifact (privat): https://claude.ai/artifact/Qpm8yGb1mmxQkXTPSS7VGS
- `docs/column_guide.html` – **Spaltenbericht für das Frontend**: je Datensatz jede Spalte, Lesart von 0/leer, Nutzung im
  Frontend, Zuordnung „Funktion → Daten“, Darstellungsregeln, Codebeispiele.
  Artifact (privat): https://claude.ai/artifact/RhAnr1SiptFH7rCm5kHRQ5
- `docs/data_dictionary.md` – dasselbe als Markdown, wird von einem Test gegen das Schema geprüft.

## 7. Version 1 und Voranalyse (zur Einordnung)

- `harmonisation_pipeline/` – Monatsebene (NUTS-2 × Monat). Ausgabe `data/harmonised/activity_harmonised.parquet`
  (+ einmalig erzeugte CSVs `activity_harmonised.csv`, `calib_factors.csv`). 17 KPIs erfüllt. Doku
  `docs/pipeline_overview.html` (Artifact https://claude.ai/artifact/PNY3tKm9zGiXynwQUGeCqY). Version 2 reproduziert deren
  Monatswerte exakt (Regressionstest).
- `data_analysis/` – Skripte 00–08 (+06b), Ergebnisse in `results/*.json`, Parquet-Cache in `cache/` (1,3 GB, neu erzeugbar),
  NUTS-Grenzen in `geo/`. Bericht `harmonisierung_bericht.html` (Artifact https://claude.ai/artifact/FxWAbVZt3f2hqejXv8LGi9).
- Alle Artifacts sind privat; Teammitglieder sehen sie erst nach Freigabe über das Share-Menü.

## 8. Regeln für das Frontend (aus den Befunden)

- Vor 2012 jede Zahl mit Band zeigen, `reliability` als Ampel.
- 0 vor 2012 heißt oft nur „MODIS sah nichts“ (`n_harm_hi90` gibt die Obergrenze).
- Leer ≠ 0: grau zeigen („keine Daten“), Schlüssel ist `day_status`.
- Filter auf `frp_class` / `confidence_class` nur auf der Karte, nicht für Summen über die Jahre.
- Pixelwerte (`frp` je Punkt, Klassen) nicht zwischen Sensoren vergleichen.
- `weight_n` nie als Punkteigenschaft zeigen (Gewicht 3 ≠ drei Feuer), nur summieren.
- Karte ohne Doppelte: `in_series_n` = wahr.
- Feuertage und Wahrscheinlichkeiten nur ab 2012 (VIIRS).
- `source` = nrt / `is_provisional` als „vorläufig“ kennzeichnen.
- Laufender Monat: `month_to_date_vs_history` vergleicht Tag 1 bis heute mit denselben Tagen früherer Jahre (keine Hochrechnung).

## 9. Offene Punkte und bekannte Probleme

1. **Beschädigte Quellzeile:** `NASA_SPACEAPP/DL_FIRE_SV-C2_845370/fire_archive_SV-C2_845370.csv`, Zeile 362617, Spalte `track`
   enthält `0.https://firms.modaps.eosdis.nasa.gov/data/download/DL_FIRE_M-C61_845369.zip77` statt `0.77` (Datei am 13.11.2026
   21:56 verändert, vermutlich versehentlich eingefügt). Das ZIP `NASA_SPACEAPP/DL_FIRE_SV-C2_845370.zip` enthält die korrekte
   Fassung. Die Pipeline verwirft die Zeile als `invalid_value`. **Empfehlung:** Datei aus dem ZIP wiederherstellen (Claude durfte
   das nicht ohne Freigabe). Danach `run_pipeline.py` neu laufen lassen.
2. **Ordner `harmonisation_daily/.shot/`** (Screenshot-Reste) bitte von Hand löschen – das automatische Löschen wurde blockiert.
3. **H4** (Faktoren je Jahreszeit) ist eine Teamentscheidung (kleiner Gewinn, mehr Komplexität).
4. **Vorhersageziel** noch offen: 3 Klassen je Region × Monat (MODIS/VIIRS stimmen zu 64 % überein) oder 2 Klassen (79 %) oder Quartale.
5. **NRT:** Ob die Vorhersage für kommende Monate gebraucht wird (dann NRT nötig) oder nur historisch, ist offen. NRT ist eingebaut.
6. **Andere Regionen** (z. B. Argentinien): Faktoren nicht übertragbar, NUTS-2 nur in Europa → neue Kalibrierung und Regionsraster nötig.
7. **Bänder für gemessene VIIRS-Werte** sind eine Annahme (Poisson + Mindestfaktor 1,2 / 1,8), in Iberien nicht prüfbar.
8. Keine Git-Commits gemacht. `data/`-Ordner sind in `.gitignore`.

## 10. Arbeitsweise und Vorlieben des Nutzers

- Kommunikation auf Deutsch. Code: Bezeichner Englisch und sprechend, Docstrings/Kommentare Deutsch, Typannotationen,
  jede Funktion mit Docstring (Algorithmen ausführlich), Funktionen ≤ ~40 Zeilen, Skripte nach Verantwortung getrennt,
  ein Orchestrator als Einstieg, Parameter nur in der Config.
- Wenn der Nutzer „nur bewerten“ oder „nicht implementieren“ sagt: nichts ändern, nur analysieren (gern mit Read-only-Rechnungen).
- Bevorzugt kompakte, nachvollziehbare HTML-Berichte mit Begründungen („warum“), keine Romane.
- KPIs vor der Messung festlegen, außerhalb der Trainingsdaten messen, Schwellen nie nachträglich senken.
- Bei Prompts: Nutzer lässt sich gern optimierte Prompts schreiben, die Fachwissen und Fallstricke ergänzen.
