# Forecast: Brandgefahr für die nächsten Tage und Wochen

Dieser Ordner baut eine Vorhersage der Feueraktivität je NUTS-2-Region:

- **Tage 1–10:** Wahrscheinlichkeit je Region und Tag.
- **Wochen 2–4:** ein allgemeiner Ausblick („ruhiger / normal / riskanter als üblich“).

Er ist ein eigener Teil neben `harmonisation/`. Er liest nur `data/harmonised/*.parquet`, importiert keinen Code
aus anderen Ordnern und schreibt nach `data/forecast/`.

> **Stand 15.11.2026:** **Die Schritte 1–6 sind fertig.**
> - Modell ohne Wetter (1.5), Wetter, FWI und Modell mit Wetter (1.6, [docs/weather_model.md](docs/weather_model.md)).
> - **Ehrliche Güte mit echten Vorhersagefehlern** und Verbesserungen
>   ([docs/honest_evaluation.md](docs/honest_evaluation.md)): Gewinn gegenüber der Saisonkurve an Tag 5 0,109 mit
>   Wetter gegenüber 0,037 ohne, an Tag 10 0,053 gegenüber 0,005.
> - Die tägliche Vorhersage nutzt das Wetter und die ECMWF-Ensemble-Spanne.
> - Nach dem 22.11.2026 übernimmt automatisch Open-Meteo als Wetterquelle.

---

## 1. Was bisher gemacht wurde

### 1.1 Machbarkeitstest: Reichen die harmonisierten Daten?

Ja. Getestet auf `activity_daily_harmonised` mit diesem Aufbau:

- nur VIIRS-gemessene Tage (ab 20.01.2012), 23 Regionen, 124.476 Region-Tage,
- Training 2012–2021, Test 2022–2026,
- verglichen wurden die **Saisonkurve** (wie oft es in dieser Region um dieses Datum brennt, ±7 Tage
  geglättet) und ein **statistisches Modell** (Saisonkurve plus die Feueraktivität der letzten 1, 7 und 30 Tage).

Die Güte ist als Brier Skill Score (BSS) angegeben: 0 heißt nicht besser als der feste Durchschnitt, 1 heißt perfekt.

| Ziel | Vorlauf | BSS Saisonkurve | BSS Modell | AUC Modell |
|---|---|---|---|---|
| Großfeuer-Tag (FRP ≥ 100 MW) | 1 Tag | 0,06 | 0,19 | 0,89 |
| Großfeuer-Tag | 3 Tage | 0,06 | 0,12 | 0,86 |
| Großfeuer-Tag | 7 Tage | 0,06 | 0,08 | 0,84 |
| Großfeuer-Tag | ≥ 14 Tage | 0,06 | 0,06 | 0,83 |
| Feuertag (irgendeine Erkennung) | 1 Tag | 0,17 | 0,26 | 0,79 |
| Feuertag | 7 Tage | 0,17 | 0,20 | 0,75 |

Was das heißt:

- Die Feuerdaten allein tragen die **Tage 1–3**, weil laufende Feuer weiterbrennen.
- Für die **Tage 4–10** braucht es die Wettervorhersage, darum die Anbindung an Meteomatics.
- **Ab Woche 2** gibt es nur noch einen Ausblick gegenüber dem Normalen.

**Gefundener Messeffekt:** Ein Tag mit `n_harm > 0` („irgendeine Erkennung“) wird häufiger, sobald mehr
VIIRS-Satelliten fliegen (NOAA-20 ab 2018, NOAA-21 ab 2023). Der Grund: Jeder weitere Satellit kann eine
Erkennung beisteuern.

| Jahr | Anteil Feuertage, `n_harm > 0` | nur SNPP |
|---|---|---|
| 2017 | 0,33 | 0,33 |
| 2019 | 0,42 | 0,32 |
| 2024 | 0,39 | 0,23 |

Das ist kein echter Trend. Die Vorhersage nimmt deshalb **`big_fire_day`** als Hauptziel und **`n_snpp > 0`**
als Feuertag. Dasselbe betrifft die Klimatologie in `aggregation/` (`p_fire_day_viirs`). Das sollte das Team wissen.

### 1.2 Wetterpunkte je Region (`features/points.py`)

NUTS-2-Regionen sind groß, Andalucía hat etwa 87.000 km². Ein Mittel über die ganze Fläche verwässert das Wetter
dort, wo es brennt. Deshalb nimmt der Code je Region die **8 Zellen à 0,25° mit den meisten VIIRS-Erkennungen
2012–2021**. Jede Zelle wird nach ihrem Anteil an den Erkennungen der Region gewichtet. Die Testjahre fließen
nicht in die Auswahl ein.

Ergebnis: 184 Punkte in 23 Regionen, gespeichert in `data/forecast/weather_points.parquet`.

### 1.3 Meteomatics-Anbindung (`features/meteomatics.py`, `fetch_weather.py`)

- **Abfrageformat:** `https://api.meteomatics.com/<start>--<ende>:P1D/<parameter>/<lat,lon+…>/csv?model=<quelle>`.
- **Quelle je Zweck** (`config.yaml`, `meteomatics.models`):
  - Historie von `core`: `ecmwf-era5`.
  - Letzte Tage und Vorhersage: `ecmwf-ifs`.
  - Gruppe `fire`: `mix`.

  Die Historie von `mix` hat falsche Niederschläge und springende Böen, siehe
  [docs/weather_model.md](docs/weather_model.md), Abschnitt 2.1.
- **Zugangsdaten:** `METEOMATICS_USERNAME` und `METEOMATICS_PASSWORD` stehen in `La-Brasa/.env`. Diese Datei
  wird von Git ignoriert. In `.env.example` stehen nur leere Platzhalter. Die Zugangsdaten gehen per HTTP-Basic-Auth
  mit, nie in der URL, und werden nie ausgegeben.
- **Zeitpunkt der Werte:** täglich um 12:00 UTC (≈ Mittag in Iberien, der übliche Zeitpunkt für Feuerwetter-Indizes).
  Werte mit `_24h` beziehen sich auf die 24 Stunden bis zu diesem Zeitpunkt.
- **Parameter:** Alle sind mit dem Hackathon-Account geprüft, für die Historie und für die Vorhersage.

  | Gruppe | Parameter |
  |---|---|
  | `core` | `t_2m:C`, `relative_humidity_2m:p`, `wind_speed_10m:kmh`, `precip_24h:mm`, `t_max_2m_24h:C`, `t_min_2m_24h:C`, `wind_gusts_10m_24h:kmh`, `dew_point_2m:C` |
  | `fire` | `fosberg_fire_weather_index:idx` (0–100, bei starkem Wind auch darüber), `forest_fire_warning:idx` (0–1, Gefahr ab 0,5), `drought_index:idx` (−4 sehr trocken bis +4 sehr feucht) |

- **Limits des Hackathon-Accounts:**
  - 1.000 Anfragen pro Tag, 250 pro Minute, 10 gleichzeitig,
  - Historie ab 1900, Abfragen mit mehr als 10 Punkten erlaubt,
  - **läuft am 22.11.2026 ab.** Was bis dahin geladen ist, bleibt im Zwischenspeicher.
- **Aufteilung der Anfragen:** 50 Punkte × 1 Jahr je Anfrage, 8 Anfragen gleichzeitig. Die Historie 2012–2026
  braucht 60 Anfragen je Gruppe. Bei `mix` dauert eine Anfrage 3–4 Minuten, bei ERA5 wenige Sekunden.
  Insgesamt sind bisher etwa 190 Anfragen verbraucht: 120 für die erste Historie, 64 für ERA5 und `recent`, dazu Tests.
- **Zwischenspeicher:** Jede Antwort wird in `data/raw/weather/meteomatics/` gespeichert. Ein erneuter Start lädt
  nichts doppelt, und ein abgebrochener Download macht dort weiter, wo er aufgehört hat.
- **Fehlwerte:** Platzhalter von Meteomatics (−999, −666) werden als leer gelesen. Fehlt ein Wert an einzelnen
  Punkten, werden die Gewichte der übrigen Punkte neu verteilt.

### 1.5 Schritt 1: Modell ohne Wetter (`run_forecast.py`)

**Aufbau:**
- **Tagesmodell:** eine logistische Regression je Ziel und Vorlauf 1–10. Eingaben:
  - Saisonkurve des Zieltags (je Region und Kalendertag, ±7 Tage),
  - Feuerverlauf am Ausgabetag (log-FRP letzter Tag, 3, 7 und 30 Tage; Feuertage 7 und 30 Tage; Großfeuer-Anteil
    30 Tage; Tage seit dem letzten Großfeuer; log-FRP der 3 nächsten Regionen),
  - Regionseffekt mit Strafe,
  - beim Feuertag zusätzlich der Wochentag.

  L2 = 100 und Platt-Kalibrierung auf den letzten 2 Trainingsjahren. Gewählt wurde das auf einem
  Validierungs-Split (Training 2012–2019, Validierung 2020–2021), nicht auf den Testjahren. Code und Rechenweg
  ohne Fremdpakete (numpy).
- **Wochenmodell:** multinomiale logistische Regression auf „weniger / üblich / mehr“ als in früheren Jahren.
  Die Klassen sind die Terzile der wöchentlichen Summe von log1p(FRP) je Region und Kalenderwoche ±1. Gleichstände
  bei 0 zählen zu „weniger“. Im Winter ist „üblich“ deshalb oft fast leer.
- **Auswertung:** Training 2012-01-20 bis 2021-12-31, Test 2022-01-01 bis 2026-07-31 (letzter Archivtag).
  Bootstrap über Jahre.
- **Rückfall:** Das Modell wird nur ausgeliefert, wenn der Gewinn > 0 ist und die untere Bootstrap-Grenze ≥ 0.
  Entschieden wird über alle Regionen zusammen, Regionen mit ≥ 30 Ereignissen im Test bekommen eine eigene
  Entscheidung. Sonst gilt `source = climatology`.
- **Ausgelieferte Modelle:** Für die Vorhersage werden die Modelle auf allen Archivdaten neu geschätzt. Die Spanne
  `p_big_fire_day_lo` / `_hi` kommt aus 20 Neuschätzungen auf zufällig gezogenen Jahren.

**Ergebnisse im Test** (Gewinn = 1 − Brier(Modell) / Brier(Saisonkurve), 90-%-Intervall über Jahre):

| Ziel | Tag 1 | Tag 3 | Tag 5 | Tag 7 | Tag 10 |
|---|---|---|---|---|---|
| Großfeuer-Tag, Gewinn | **0,213** (0,187–0,238) | 0,081 (0,053–0,113) | 0,042 (0,016–0,067) | 0,025 (0,004–0,051) | 0,011 (−0,007–0,035) → Saisonkurve |
| Großfeuer-Tag, AUC / PR-AUC | 0,92 / 0,46 | 0,88 / 0,29 | 0,86 / 0,22 | 0,86 / 0,20 | 0,85 / 0,18 |
| Feuertag (SNPP), Gewinn | 0,130 | 0,059 | 0,042 | 0,032 | 0,027 |

Die Saisonkurve allein hat für Großfeuer-Tage AUC 0,83 und PR-AUC 0,14. Für die Tage 8–10 schließt das Intervall
die 0 ein, dort wird die Saisonkurve ausgeliefert. Im Leave-one-year-out (2012–2026) ist das Modell an Tag 1 in allen
15 Jahren besser als die Saisonkurve (Gewinn 0,10–0,25).

Warnschwelle „oberste 10 %“, Tag 1: Das Modell findet 71 % der Großfeuer-Tage, 77 % der Warnungen sind Fehlalarme.
Bei 2,9 % Ereignissen ist das zu erwarten.

**Risikoklassen im Test, Tag 1:**

| Klasse | Anteil der Region-Tage | davon Großfeuer-Tage |
|---|---|---|
| `low` | 39,8 % | 1,5 % |
| `normal` | 54,4 % | 1,2 % |
| `elevated` | 2,2 % | 11 % |
| `high` | 2,2 % | 25 % |
| `very_high` | 1,4 % | 54 % |

**Wochenausblick:** RPSS gegenüber der Klimatologie: Woche 2 0,020 (0,009–0,033), Woche 3 0,009, Woche 4 0,002
(Intervall schließt 0 ein → Klimatologie). Ein kleiner, aber echter Gewinn.

**KPIs** (`data/forecast/forecast_kpi_report.json`): 24 von 26 Pflicht-KPIs bestanden.

| Verfehlt | Wert | Schwelle | Grund |
|---|---|---|---|
| B6 Kalibrierung | Steigung 0,798 bei Tag 8–9 | 0,8–1,2 | Knapp. Diese Vorläufe werden ohnehin als Saisonkurve ausgeliefert. ECE überall ≤ 0,010 |
| D3 Kalibrierung Woche | ECE 0,059 | ≤ 0,05 | Die Klimatologie selbst liegt bei 0,067. Die Wochensumme der FRP driftet mit der Zahl der VIIRS-Satelliten (siehe unten) |

**Zwei Entscheidungen für das Team:**
1. **Wochenziel:** `frp_harm` driftet nach oben, sobald NOAA-20/21 dazukommen (Anteil Tage mit FRP > 0:
   0,32 → 0,41–0,45). Eine SNPP-Variante wurde getestet (`model.weekly.activity_frp: frp_snpp`). Sie driftet in
   den Testjahren nach unten (SNPP −12 %) und ist nicht besser. Vorerst bleibt die ursprüngliche Definition.
2. **Risikoklassen:** Im ersten Vorschlag überschnitten sich `low` und `normal`, `low` kam nie vor. Jetzt (`config.yaml`,
   `risk_class`): nach `risk_ratio` < 0,67 / 1,5 / 3 / 6, `p ≥ 0,25` mindestens `high`, `p ≥ 0,5` `very_high`, und
   `p < 0,02` höchstens `normal`. So wird eine winzige Wahrscheinlichkeit nicht rot, nur weil sie ein Vielfaches
   der Saison ist.

### 1.6 Schritte 2–4: Wetter prüfen, FWI, Modell mit Wetter

Die Einzelheiten zu Dateien und Rechenweg stehen in [docs/weather_model.md](docs/weather_model.md). Kurz:

- **Schritt 2, Wetterdaten:**
  - Vollständig (A5: 100 %) und plausibel (A6: 0 Verstöße), nachdem die Historie von `core` mit ERA5 neu geladen
    wurde.
  - `mix` hatte z. B. 2023 in Galicien nur 42 mm Regen im Jahr, ERA5 dagegen etwa 1400 mm.
  - Signalprüfung in der Saison: Die Abweichung des FWI vom Üblichen trennt Großfeuer-Tage am besten (AUC 0,76).
- **Schritt 3, FWI-System:**
  - `features/fwi.py` rechnet FFMC, DMC, DC, ISI, BUI und FWI je Wetterpunkt und mittelt danach je Region.
  - Gegen die veröffentlichte Testtabelle (Van Wagner & Pickett 1985) liegt die größte Abweichung bei 0,005
    (A7: < 0,1).
- **Schritt 4, Modell mit Wetter:**
  - Merkmale des Zieltags aus den Grundvariablen: FWI-System, Fosberg (selbst berechnet), Temperatur, Feuchte, VPD,
    Böen, Regen davor, Abweichungen vom Üblichen und drei nichtlineare Terme. 22 Merkmale, ausgewählt auf der
    Validierung 2020–2021.
- **Schritt 5, ehrliche Güte** ([docs/honest_evaluation.md](docs/honest_evaluation.md)):
  - Im Test bekommen die Vorhersagetage echte IFS-Fehler je Vorlauf (Open-Meteo Previous Runs 2025, gegen ERA5).
  - Das Modell wird auf Wetter mit solchen Fehlern trainiert. Ohne das wäre es mit echten Vorhersagen schlechter als
    ohne Wetter.

    | Großfeuer-Tag, Gewinn gegenüber der Saisonkurve | Tag 1 | Tag 3 | Tag 5 | Tag 7 | Tag 10 |
    |---|---|---|---|---|---|
    | ohne Wetter | 0,213 | 0,078 | 0,037 | 0,020 | 0,005 |
    | **mit Wetter, mit echten Vorhersagefehlern** | **0,250** | **0,147** | **0,109** | **0,077** | **0,053** |

  - Kalibrierung: ECE ≤ 0,009, Steigung 1,01–1,13.
  - B3 und B4 sind bestanden.
  - Beim Wochenausblick bringt das Wetter nichts, er bleibt bei der Stufe ohne Wetter.
  - Weitere Verbesserungen: eine glattere Saisonkurve, die Bias-Korrektur der IFS-Vorhersage und eine
    Ensemble-Spanne.
- **KPIs:** Alle Pflicht-KPIs außer D3 sind bestanden (Wochenausblick, ECE 0,059 bei Schwelle 0,05, wie in Schritt 1).
- **Ausgeliefert** wird je Vorlauf die Stufe mit Wetter, wenn sie im Test besser ist und für den Zieltag Wetter
  vorliegt. Sonst die Stufe ohne Wetter. `model_version` je Zeile sagt, welche.

### 1.7 Änderungen außerhalb dieses Ordners

- `.gitignore`: neue Zeile `data/forecast/`.
- `.env.example`: leere Platzhalter für Meteomatics (vom Nutzer eingetragen).
- Sonst wurde nichts geändert. `harmonisation/`, `pipeline/`, `backend/` und `db/` sind unberührt.

---

## 2. Ausführen

```bash
cd La-Brasa/forecast
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # einmalig
.venv/bin/python -m pytest -q                                         # 50 Tests, ohne Internet

.venv/bin/python fetch_weather.py points     # Wetterpunkte wählen (keine API-Anfrage)
.venv/bin/python fetch_weather.py check      # Limits des Accounts + jeden Parameter testen (~23 Anfragen)
.venv/bin/python fetch_weather.py history --start 2012-01-20 --end 2026-11-08   # ERA5 (core) + mix (fire), ~120 Anfragen
.venv/bin/python fetch_weather.py recent --start 2026-11-09 --end 2026-11-13     # Tage nach dem Ende von ERA5 (IFS)
.venv/bin/python fetch_weather.py forecast   # Vorhersage ab heute für 10 Tage (~8 Anfragen)
.venv/bin/python fetch_weather.py errors --start 2025-01-01 --end 2025-12-31   # echte IFS-Fehler (Open-Meteo, einmalig)
.venv/bin/python fetch_weather.py ensemble   # ECMWF-Ensemble für die Spanne (Open-Meteo)

.venv/bin/python run_forecast.py weather-qc         # Wetter prüfen (A5/A6) -> data/forecast/weather_qc.json
.venv/bin/python run_forecast.py train              # auswerten + trainieren -> models/bundle.pkl + Vorhersage + KPIs (~6,5 min)
.venv/bin/python run_forecast.py predict            # tägliche Vorhersage aus bundle.pkl, ohne Training (~7 s)
.venv/bin/python run_forecast.py train --no-weather # nur die Stufe ohne Wetter
```

### 2.1 Betrieb: was wo läuft

| | `train` | `predict` |
|---|---|---|
| Was | Auswertung beider Stufen, Auswahl der Merkmale, Produktionsmodelle samt Bootstrap, KPIs, Tests | lädt `models/bundle.pkl`, berechnet die Merkmale des Ausgabetags, wendet die Gewichte an |
| Wann | wenn sich Daten-Archiv, Code oder `config.yaml` ändern, z. B. wöchentlich | täglich, nach neuen FIRMS-Daten und neuer Wettervorhersage |
| Wo | Arbeitsrechner (Laptop) | Server |
| Gemessen (15.11.2026) | 6,5 min, 1 Kern, max. 1,1 GB RAM | **7 s mit Ensemble, 1 Kern, max. 1,1 GB RAM** |

Der Server hat 4 vCores, 8 GB RAM, davon höchstens 3,4 GB für diesen Teil. `predict` passt mit großem Abstand.
Nach `train` wird nur `data/forecast/models/bundle.pkl` (~1 MB) auf den Server kopiert. `predict` prüft, ob
`config.yaml` und die Regionen noch dazu passen, und warnt sonst. `predict` liest die Datei mit `pickle`. Deshalb nur
eine Datei laden, die `train` aus diesem Repository erzeugt hat.

**Threads:** Die Lineare Algebra läuft standardmäßig auf **einem** Kern (`FORECAST_THREADS`, Standard 1). Das ist
hier sogar schneller: Ein Modell braucht mit 1 Thread 0,5 s, mit 24 Threads 1,2 s, weil OpenBLAS sich bei so
kleinen Matrizen vor allem selbst abstimmt. Vorher hat genau das den Laptop voll ausgelastet.

```bash
.venv/bin/python analysis/data_analysis.py          # Datenanalyse neu bauen → docs/data_analysis.html
```

### 2.2 Automatisierung: täglicher Lauf per Cron

Eine Schritt-für-Schritt-Anleitung für den Server steht in [docs/server_setup.md](docs/server_setup.md).

`daily.py` ist der tägliche Job. Er ermittelt die Daten selbst und macht der Reihe nach:

1. **Wetter holen:** `recent` für die Tage nach dem Ende der Historie bis gestern, `forecast` ab heute und das
   Ensemble.
   - Bis zum 22.11. von Meteomatics, etwa 16 Anfragen.
   - Danach von Open-Meteo; dabei wird auch die ERA5-Historie verlängert.
2. **`predict`** ausführen.
3. **Aufräumen:** Es bleiben nur die letzten 14 Vorhersage-Dateien je Gruppe.
4. **Protokoll:** eine Zeile je Lauf in `data/forecast/logs/daily_runs.jsonl`.

Gemessen: 14 s, 1 Kern, 1,1 GB RAM.

| Fall | Verhalten |
|---|---|
| Meteomatics antwortet nicht oder lehnt ab | weiter ohne neues Wetter. Ist die letzte Vorhersage älter als 1 Tag (`daily.max_forecast_age_days`), läuft `predict` mit der Stufe ohne Wetter. |
| nach dem 22.11.2026 (`daily.meteomatics_valid_until`) | keine Anfragen mehr, automatisch die Stufe ohne Wetter |
| ein zweiter Lauf startet, während einer läuft | endet sofort (Sperrdatei, Rückgabewert 3) |
| keine trainierten Modelle (`bundle.pkl` fehlt) | Rückgabewert 2 |
| Ausgabe verletzt den Vertrag (F1–F3) | Rückgabewert 1, die letzten gültigen Tabellen bleiben stehen |
| Feuerdaten älter als 2 Tage | Warnung: Die Vorhersage rückt nicht weiter, solange `data/harmonised/` nicht aktualisiert wird |

**Wichtig:** Der Ausgabetag ist der letzte Tag in `data/harmonised/`. Damit die Vorhersage jeden Tag weiterrückt,
muss vorher die tägliche Aktualisierung der Feuerdaten laufen, also FIRMS laden und harmonisieren. Laut der README im
Hauptordner ist `pipeline/update_daily.py` noch nicht umgesetzt. Das liegt außerhalb dieses Ordners und ist
Team-Aufgabe. Bis dahin holt `daily.py` zwar jeden Tag neues Wetter, der Ausgabetag bleibt aber stehen.

**Crontab auf dem Server** (`crontab -e`, Zeiten in UTC, Pfad anpassen):

```cron
# täglich 07:30 UTC, nach der Aktualisierung der Feuerdaten (die selbst z. B. um 07:00 läuft)
30 7 * * *  cd /srv/La-Brasa/forecast && nice -n 10 .venv/bin/python daily.py >> ../data/forecast/logs/daily_$(date -u +\%F).log 2>&1

# optional, nur wenn train auf dem Server laufen soll: sonntags 03:00 UTC, niedrigste Priorität
0 3 * * 0   cd /srv/La-Brasa/forecast && nice -n 19 .venv/bin/python run_forecast.py train --skip-tests >> ../data/forecast/logs/train_$(date -u +\%F).log 2>&1
```

In der crontab muss `%` als `\%` geschrieben werden. Mit Docker startet Cron auf dem Rechner stattdessen
`docker compose run --rm forecast python daily.py`, mit einem Dienst `forecast` wie in
[docs/integration_backend_frontend.md](docs/integration_backend_frontend.md), 3.4. Diesen Dienst gibt es noch nicht.

**Prüfen, ob es läuft:**

```bash
tail -1 data/forecast/logs/daily_runs.jsonl          # letzter Lauf: Ausgabetag, Stufe, Rückgabewert, Dauer
.venv/bin/python daily.py --dry-run                  # was heute angefragt würde, ohne etwas zu ändern
```

Mit `--group core` oder `--group fire` lädt man nur eine Gruppe. Den Fortschritt eines laufenden Downloads zeigt
`data/forecast/history_download.log`.

---

## 3. Dateien in `data/forecast/`

| Datei | Stand | Zeile | Inhalt |
|---|---|---|---|
| `weather_points.parquet` | vorhanden | Region × Zelle | `region_id`, `cell_id`, `lat`, `lon`, `n_detections`, `weight` |
| `weather_region_history_<gruppe>.parquet`, `weather_region_recent_core.parquet` | vorhanden (core: ERA5 bis 08.11., recent: IFS 09.–13.11.) | Region × Tag | `region_id`, `validdate` (12:00 UTC), `date`, dazu eine Spalte je Parameter mit dem Meteomatics-Namen als Spaltenname, z. B. `t_2m:C` |
| `weather_region_forecast_<gruppe>_<datum>.parquet` | nach `forecast` | Region × Tag | wie oben, für die nächsten 10 Tage ab `<datum>` |
| `weather_points_*.parquet` | wie oben | Punkt × Tag | dieselben Werte je Punkt, vor der Mittelung |
| `forecast_daily.parquet` | vorhanden (ohne Wetter) | Region × Ausgabetag × Zieltag | siehe 4.1 |
| `forecast_weekly.parquet` | vorhanden (ohne Wetter) | Region × Ausgabetag × Woche | siehe 4.2 |
| `forecast_skill.parquet` | vorhanden | Produkt × Ziel × Vorlauf × Region | siehe 4.3, zusätzlich `ci_lo`, `ci_hi`, `pr_auc`, `ece`, `n_events`, `skill_basis` |
| `csv/*.csv` | vorhanden | | CSV-Kopien der drei Tabellen für das Frontend |
| `forecast_kpi_report.json`, `forecast_evaluation.json`, `manifest.json`, `models/*.json` | vorhanden | | KPIs, alle Testzahlen beider Stufen, Herkunft, Koeffizienten |
| `weather_qc.json` | vorhanden | | Prüfung der Wetterdaten (A5, A6, Lücken, Ausreißer, Signal) |
| `backup_mix_core/` | vorhanden | | die verworfene `core`-Historie aus `mix` |

Die Spaltennamen der Wettertabellen enthalten Doppelpunkte (`t_2m:C`). Im Frontend als Schlüssel in Anführungszeichen
ansprechen oder beim Laden umbenennen.

---

## 4. Nutzung im Frontend

Leitidee: Die Vorhersage ergänzt den **Kalender** und die **Karte**, die es schon gibt. Sie ersetzt sie nicht.
Für Tage, für die kein gutes Modell vorliegt, liefert sie die Saisonkurve und sagt das auch (`source = climatology`).
Das Frontend zeigt also nie eine „Vorhersage“, die schlechter ist als das normale Jahresprofil.

### 4.1 Tage 1–10: `forecast_daily` (geplant)

| Spalte | Bedeutung | Im Frontend |
|---|---|---|
| `region_id` | NUTS-2-Region | Schlüssel, Verknüpfung mit `activity_daily_harmonised` |
| `issue_date` | Tag, an dem die Vorhersage erstellt wurde | „Stand: 14.11.“; immer die neueste nehmen |
| `target_date` | Tag, für den sie gilt | x-Achse im Kalender |
| `lead_days` | 1–10, Abstand von `issue_date` | Unsicherheit wächst mit dem Vorlauf; ab Tag 7 blasser zeichnen |
| `p_big_fire_day` | Wahrscheinlichkeit eines Großfeuer-Tags (FRP ≥ 100 MW) | Hauptwert, „18 %“ |
| `p_fire_day` | Wahrscheinlichkeit irgendeiner Erkennung (SNPP-Basis) | Nebenwert im Tooltip |
| `p_clim_big_fire_day`, `p_clim_fire_day` | dieselben Größen laut Saisonkurve | Vergleich „üblich wären 6 %“ |
| `risk_ratio` | `p / p_clim` | Text „3× so hoch wie üblich“ |
| `risk_class` | `low`, `normal`, `elevated`, `high`, `very_high` | Farbe des Kalendertags und der Region auf der Karte |
| `p_big_fire_day_lo`, `p_big_fire_day_hi` | Spanne aus der Ensemble-Wettervorhersage | Fehlerbalken oder Text „10–25 %“ |
| `source` | `model` oder `climatology` | Bei `climatology`: Hinweis „nur Saisonwert, keine Vorhersage“ |
| `model_version` | Modellversion | Fußnote |

Darstellung:

- **Kalender:** Hinter dem letzten gemessenen Tag folgen 10 Vorhersagetage. Die Farbe kommt aus `risk_class`.
  Vorhersagetage sind deutlich von gemessenen zu unterscheiden, z. B. gestrichelter Rahmen oder Schraffur und
  die Überschrift „Vorhersage“.
- **Karte:** Ein Regler „heute + n Tage“ (1–10) färbt die Regionen nach `risk_class` für den gewählten Tag.
  Optional liegen die aktuellen Hotspots darüber.
- **Tooltip:** „Großfeuer-Wahrscheinlichkeit 18 % (üblich 6 %, also 3×). Vorhersage vom 14.11., 4 Tage voraus.“
- **Zuverlässigkeit:** Neben der Region ein Symbol aus `forecast_skill` (4.3), z. B. „Treffsicherheit an Tag 4:
  mittel“.

### 4.2 Wochen 2–4: `forecast_weekly` (geplant)

| Spalte | Bedeutung | Im Frontend |
|---|---|---|
| `region_id`, `issue_date` | wie oben | |
| `week_start` | Montag der Woche | Beschriftung „Woche ab 30.11.“ |
| `week_ahead` | 2, 3 oder 4 | Reihenfolge |
| `p_below`, `p_normal`, `p_above` | Wahrscheinlichkeit für weniger / üblich viele / mehr Großfeuer-Tage als in früheren Jahren in dieser Woche | dreigeteilter Balken; ohne Information je 33 % |
| `expected_big_fire_days`, `clim_big_fire_days` | erwartete und übliche Zahl der Großfeuer-Tage | Text „erwartet 1,4, üblich 0,9“ |
| `source`, `model_version` | wie oben | |

Darstellung:

- **Keine Tageswerte, keine Prozent pro Tag.** Je Woche ein Balken oder eine Ampel mit drei Stufen, Text wie
  „55 % Chance auf mehr Feueraktivität als üblich“.
- Liegt `p_above` nahe 33 %, besser „keine klare Tendenz“ schreiben als einen Wert hervorheben.

### 4.3 Wie verlässlich? `forecast_skill` (geplant)

| Spalte | Bedeutung |
|---|---|
| `product` | `daily` oder `weekly` |
| `target` | `big_fire_day`, `fire_day` |
| `lead` | Tage (daily) oder Wochen (weekly) |
| `region_id` | Region oder `all` |
| `bss_vs_climatology` | Gewinn gegenüber der Saisonkurve (> 0 = besser) |
| `auc`, `hit_rate`, `false_alarm_ratio` | Treffsicherheit für Großfeuer-Tage |
| `use_model` | ob für diesen Vorlauf das Modell oder die Saisonkurve ausgeliefert wird |

Im Frontend als kleine Infografik „So gut trifft die Vorhersage“ (Güte über den Vorlauf 1–10) und als Ampel je Region.

### 4.4 Was man heute schon zeigen kann

Sobald der Download fertig ist, liegen die **Wetterdaten je Region** vor, Historie und 10-Tage-Vorhersage.
Damit lassen sich schon vor dem Modell zeigen:

- **Feuerwetter je Region:** Fosberg-Index (0–100) oder Waldbrandwarnung (0–1, Gefahr ab 0,5) für die nächsten
  10 Tage, als Kurve oder Kalenderfarbe.
- **Dürreindex** (−4 bis +4) als Karte „wie trocken ist es gerade“.
- **Rückblick:** Temperatur, Niederschlag und Fosberg-Index neben der Feuerkurve aus `activity_daily_harmonised`.
  So sieht man, wie Wetter und Feuer zusammenhängen.

Das sind Meteomatics-Indizes, keine eigene Vorhersage. Im Frontend auch so benennen („Feuerwetter-Index von Meteomatics“).

### 4.5 Wie die Daten ins Frontend kommen

Die Vorhersage ist **noch nicht** in Postgres und hat keinen Endpunkt im Backend. Das ist eine Teamentscheidung,
weil dafür `db/init/` und `backend/` geändert werden müssten. Vorschlag:

- **Für die Demo:** Das Frontend oder ein kleines Skript liest die Parquet-Dateien bzw. CSV/JSON-Kopien daraus.
- **Später:** neue Tabellen `forecast_daily`, `forecast_weekly`, `forecast_skill` in Postgres, geladen wie die
  harmonisierten Tabellen. Dazu Endpunkte, z. B.:

```
GET /api/v1/forecast/daily?region_id=PT11            -> neueste Vorhersage, 10 Zeilen
GET /api/v1/forecast/daily?target_date=2026-11-18    -> alle Regionen für die Karte
GET /api/v1/forecast/weekly?region_id=PT11           -> Wochen 2–4
GET /api/v1/forecast/skill                           -> Güte je Vorlauf
```

```json
{
  "region_id": "PT11", "issue_date": "2026-11-14", "target_date": "2026-11-18", "lead_days": 4,
  "p_big_fire_day": 0.18, "p_clim_big_fire_day": 0.06, "risk_ratio": 3.0, "risk_class": "high",
  "p_big_fire_day_lo": 0.10, "p_big_fire_day_hi": 0.25, "source": "model", "model_version": "0.1"
}
```

### 4.6 Texte, die das Frontend mitliefern sollte

- Vorhergesagt wird **erkannte Feueraktivität je Region** (Satelliten-Überflüge ≈ 2× am Tag). Einzelne Brände,
  ihre Entstehung und die verbrannte Fläche sind nicht Teil der Vorhersage.
- Die meisten Brände in Iberien werden von Menschen ausgelöst. Die Vorhersage sagt, **wie günstig die Bedingungen**
  sind, nicht ob jemand ein Feuer legt.
- Tage 1–3 stützen sich vor allem auf laufende Feuer, Tage 4–10 auf die Wettervorhersage. Wochen 2–4 sind nur eine Tendenz.
- Regionen mit wenigen Großfeuer-Tagen (z. B. ES21 País Vasco, ES23 La Rioja, ES62 Murcia, PT17 Lisboa) haben
  große Unsicherheit.
- Die letzten Tage beruhen auf vorläufigen NRT-Daten (`day_status.is_provisional`) und können sich noch ändern.

---

## 5. Nächste Schritte

Erledigt: Schritt 1 (ohne Wetter), Schritt 2 (Wetter prüfen), Schritt 3 (FWI), Schritt 4 (Modell mit Wetter).

5. ~~Ehrliche Auswertung~~ erledigt am 15.11.: Meteomatics hat keine archivierten Vorhersagen, deshalb werden echte
   IFS-Fehler von Open-Meteo genutzt (`skill_basis = analysis_with_noise`,
   [docs/honest_evaluation.md](docs/honest_evaluation.md)).
6. ~~Live-Vorhersage mit Wetter~~ erledigt am 15.11.: `fetch_weather.py recent` + `forecast`, dann
   `run_forecast.py predict` ([docs/weather_model.md](docs/weather_model.md), Abschnitt 7). Bis zum 22.11. täglich.
   Die weichere Saisonkurve ist inzwischen umgesetzt.
7. ~~Täglicher Lauf~~ erledigt: `daily.py`, nach dem 22.11. mit Open-Meteo.
8. Offen, Team: tägliche Aktualisierung der Feuerdaten, Datenbank und Backend, Wochenziel (D3), Regel 3.5 je Region
   ([docs/honest_evaluation.md](docs/honest_evaluation.md), Abschnitt 7).
