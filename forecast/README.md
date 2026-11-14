# Forecast: Brandgefahr für die nächsten Tage und Wochen

Dieser Ordner baut eine Vorhersage der Feueraktivität je NUTS-2-Region:

- **Tage 1–10:** Wahrscheinlichkeit je Region und Tag.
- **Wochen 2–4:** ein allgemeiner Ausblick („ruhiger / normal / riskanter als üblich“).

Er ist ein eigener Teil neben `harmonisation/`. Er liest nur `data/harmonised/*.parquet`, importiert keinen Code
aus anderen Ordnern und schreibt nach `data/forecast/`.

> **Stand 14.11.2026:** Der Teil mit den Wetterdaten ist fertig (Wetterpunkte, Meteomatics-Anbindung, Tests),
> der Download der Historie 2012–2026 läuft. **Das Vorhersagemodell selbst ist noch nicht gebaut.**
> Die Tabellen `forecast_daily`, `forecast_weekly` und `forecast_skill` in Abschnitt 4 sind der **geplante**
> Vertrag mit dem Frontend. Das Frontend kann schon dagegen entwickeln, die Dateien gibt es aber noch nicht.

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

- **Abfrageformat:** `https://api.meteomatics.com/<start>--<ende>:P1D/<parameter>/<lat,lon+…>/csv?model=mix`.
- **Zugangsdaten:** `METEOMATICS_USERNAME` und `METEOMATICS_PASSWORD` stehen in `La-Brasa/.env`. Diese Datei
  wird von Git ignoriert. In `.env.example` stehen nur leere Platzhalter. Die Zugangsdaten gehen per HTTP-Basic-Auth
  mit, nie in der URL, und werden nie ausgegeben.
- **Zeitpunkt der Werte:** täglich um 12:00 UTC (≈ Mittag in Iberien, der übliche Zeitpunkt für Feuerwetter-Indizes).
  Werte mit `_24h` beziehen sich auf die 24 Stunden bis zu diesem Zeitpunkt.
- **Parameter:** Alle sind mit dem Hackathon-Account geprüft, für die Historie und für die Vorhersage.

  | Gruppe | Parameter |
  |---|---|
  | `core` | `t_2m:C`, `relative_humidity_2m:p`, `wind_speed_10m:kmh`, `precip_24h:mm`, `t_max_2m_24h:C`, `t_min_2m_24h:C`, `wind_gusts_10m_24h:kmh`, `dew_point_2m:C` |
  | `fire` | `fosberg_fire_weather_index:idx` (0–100), `forest_fire_warning:idx` (0–1, Gefahr ab 0,5), `drought_index:idx` (−4 sehr trocken bis +4 sehr feucht) |

- **Limits des Hackathon-Accounts:**
  - 1.000 Anfragen pro Tag, 250 pro Minute, 10 gleichzeitig,
  - Historie ab 1900, Abfragen mit mehr als 10 Punkten erlaubt,
  - **läuft am 22.11.2026 ab.** Was bis dahin geladen ist, bleibt im Zwischenspeicher.
- **Aufteilung der Anfragen:** 50 Punkte × 1 Jahr je Anfrage, 8 Anfragen gleichzeitig. Die Historie 2012–2026
  braucht 60 Anfragen je Gruppe, also 120 insgesamt. Eine Anfrage dauert 3–4 Minuten.
- **Zwischenspeicher:** Jede Antwort wird in `data/raw/weather/meteomatics/` gespeichert. Ein erneuter Start lädt
  nichts doppelt, und ein abgebrochener Download macht dort weiter, wo er aufgehört hat.
- **Fehlwerte:** Platzhalter von Meteomatics (−999, −666) werden als leer gelesen. Fehlt ein Wert an einzelnen
  Punkten, werden die Gewichte der übrigen Punkte neu verteilt.

### 1.4 Änderungen außerhalb dieses Ordners

- `.gitignore`: neue Zeile `data/forecast/`.
- `.env.example`: leere Platzhalter für Meteomatics (vom Nutzer eingetragen).
- Sonst wurde nichts geändert. `harmonisation/`, `pipeline/`, `backend/` und `db/` sind unberührt.

---

## 2. Ausführen

```bash
cd La-Brasa/forecast
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # einmalig
.venv/bin/python -m pytest -q                                         # 9 Tests, ohne Internet

.venv/bin/python fetch_weather.py points     # Wetterpunkte wählen (keine API-Anfrage)
.venv/bin/python fetch_weather.py check      # Limits des Accounts + jeden Parameter testen (~23 Anfragen)
.venv/bin/python fetch_weather.py history --start 2012-01-20 --end 2026-11-13   # ~120 Anfragen, etwa 1 Stunde
.venv/bin/python fetch_weather.py forecast   # Vorhersage ab heute für 10 Tage (wenige Anfragen)
```

Mit `--group core` oder `--group fire` lädt man nur eine Gruppe. Den Fortschritt eines laufenden Downloads zeigt
`data/forecast/history_download.log`.

---

## 3. Dateien in `data/forecast/`

| Datei | Stand | Zeile | Inhalt |
|---|---|---|---|
| `weather_points.parquet` | vorhanden | Region × Zelle | `region_id`, `cell_id`, `lat`, `lon`, `n_detections`, `weight` |
| `weather_region_history_<gruppe>.parquet` | entsteht nach dem Download | Region × Tag | `region_id`, `validdate` (12:00 UTC), `date`, dazu eine Spalte je Parameter mit dem Meteomatics-Namen als Spaltenname, z. B. `t_2m:C` |
| `weather_region_forecast_<gruppe>_<datum>.parquet` | nach `forecast` | Region × Tag | wie oben, für die nächsten 10 Tage ab `<datum>` |
| `weather_points_*.parquet` | wie oben | Punkt × Tag | dieselben Werte je Punkt, vor der Mittelung |
| `forecast_daily.parquet` | **geplant** | Region × Ausgabetag × Zieltag | siehe 4.1 |
| `forecast_weekly.parquet` | **geplant** | Region × Ausgabetag × Woche | siehe 4.2 |
| `forecast_skill.parquet` | **geplant** | Produkt × Ziel × Vorlauf × Region | siehe 4.3 |

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

1. Download der Historie abschließen und prüfen (Lücken, plausible Werte je Region).
2. Modell **ohne Wetter**: Saisonkurve und Feuerverlauf, je Vorlauf 1–10 ein Modell, Auswertung, Rückfall auf die
   Saisonkurve, Ausgabe von `forecast_daily`, `forecast_weekly`, `forecast_skill`.
3. **Mit Wetter**: Meteomatics-Variablen und Feuerwetter-Indizes dazunehmen und den Gewinn je Vorlauf zeigen.
4. **Ehrliche Auswertung** für die Tage 4–10 mit archivierten Vorhersagen, sofern Meteomatics sie liefert (noch zu prüfen).
5. Täglicher Lauf: Vorhersage holen, dann die Tabellen schreiben.

Mehr Hintergrund, Methode und Regeln: [PROMPT.md](PROMPT.md).
