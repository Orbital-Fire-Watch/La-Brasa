# Forecast in Backend und Frontend einbinden

Stand: 15.11.2026. Für alle, die die Brandgefahr-Vorhersage in Datenbank, Backend und Frontend einbauen.

**Kurz:**
- Die Vorhersage wird **einmal am Tag** vorab gerechnet und als fertige Tabellen in `data/forecast/` geschrieben.
- Das Backend rechnet nichts. Es liest nur die neueste Ausgabe und gibt sie weiter.
- Das Format der Tabellen ist fest. Offene Team-Entscheidungen, etwa die Grenzen der Risikoklassen oder das
  Wochenziel, ändern nur Werte, nicht die Spalten.
- Backend und Frontend können also jetzt gebaut werden.

Hintergrund zum Modell: `forecast/README.md`, `forecast/docs/honest_evaluation.md`. Betrieb auf dem Server:
`pipeline/README.md`, `forecast/docs/server_setup.md`.

---

## 1. Was es schon gibt und was fehlt

| Teil | Ort | Status |
|---|---|---|
| täglicher Ablauf: FIRMS → Harmonisierung → Forecast | `pipeline/update_daily.py` | **fertig**, erster echter Lauf am 15.11.2026 |
| Vorhersage-Tabellen (Parquet + CSV) | `data/forecast/forecast_{daily,weekly,skill}.parquet`, `csv/` | **fertig**, täglich neu, nicht in Git |
| Stand des letzten Laufs | `data/forecast/status.json`, `data/logs/update_status.json` | **fertig** |
| Format der Tabellen | `forecast/contract.py`, Abschnitt 3 hier | **fest** |
| Datenbank-Tabellen | `db/init/003_forecast.sql` | fehlt (Vorschlag in 4.1) |
| Laden in Postgres | `pipeline/load_forecast_to_db.py` | fehlt (4.2) |
| API-Endpoints | `backend/` | fehlt (Abschnitt 5) |
| Anzeige | `frontend/` | fehlt (Abschnitt 6) |

**Vorher zusammenführen:**
- `weather_prediction` muss in den Arbeitsbranch (`app` bzw. `main`) gemergt werden. Damit kommen `forecast/`,
  `pipeline/update_daily.py` und die `.gitignore`-Einträge mit (`data/forecast/`, `data/harmonised/*`, `data/logs/`
  und die Prompt-Dateien).
- `data/harmonised/` ist seit dem 15.11. **nicht mehr in Git**. Wer den Merge zieht, verliert die Dateien dort im
  Arbeitsordner. Deshalb den Ordner vorher kopieren oder danach mit `harmonisation/run_pipeline.py` neu erzeugen.

---

## 2. Datenfluss

```
täglich, cron (pipeline/update_daily.py)
  1. FIRMS-API        -> data/raw/*/fire_{archive,nrt}_*.csv
  2. Harmonisierung   -> data/harmonised/*.parquet
  3. load_to_db.py    -> Postgres: harmonisierte Tabellen            (mit --load-db)
  4. forecast/daily.py -> data/forecast/forecast_*.parquet, status.json
  5. NEU: load_forecast_to_db.py -> Postgres: forecast_*             (4.2)

bei jeder Anfrage
  Frontend -> GET /api/forecast/... -> Backend liest forecast_* aus Postgres
```

- **Ausgabetag (`issue_date`):** der letzte Tag mit Feuerdaten, also normalerweise gestern oder heute. Die
  Vorhersage gilt für die 10 Tage danach.
- **Neue Werte:** einmal am Tag nach dem Lauf, gegen 07:30 UTC. Antworten darf das Backend bis dahin zwischenspeichern.
- **Zugangsdaten:** Das Backend braucht keine. Meteomatics bzw. Open-Meteo und FIRMS kommen nur im täglichen Lauf vor.

---

## 3. Datenvertrag

### 3.1 `forecast_daily`: Tage 1–10

230 Zeilen je Ausgabetag: 23 Regionen × 10 Vorläufe. Darunter sind 3 französische Grenzregionen (FRI1, FRJ1,
FRJ2), die die API nicht ausliefert (`API_COUNTRIES = ("ES", "PT")`). Keine Spalte ist leer.

| Spalte | Typ | Bedeutung | Im Frontend |
|---|---|---|---|
| `region_id` | text | NUTS-2-Region | Schlüssel, Verknüpfung mit `regions` |
| `issue_date` | date | Tag, an dem die Vorhersage erstellt wurde | „Stand: 15.11.“ |
| `target_date` | date | Tag, für den sie gilt | x-Achse, Tagesregler |
| `lead_days` | int 1–10 | `target_date − issue_date` | ab Tag 7 blasser zeichnen |
| `p_big_fire_day` | float 0–1 | **Hauptwert:** Wahrscheinlichkeit eines Großfeuer-Tags (Satelliten messen zusammen ≥ 100 MW Feuerleistung in der Region) | „2,5 %“ |
| `p_big_fire_day_lo`, `_hi` | float 0–1 | Spanne (5–95 %): Unsicherheit der Modellgewichte und des Wetters (51 Ensemble-Mitglieder); immer lo ≤ p ≤ hi | Fehlerbalken, „1–4 %“ |
| `p_fire_day` | float 0–1 | Wahrscheinlichkeit irgendeiner Erkennung (Satellit SNPP) | Nebenwert im Tooltip |
| `p_clim_big_fire_day`, `p_clim_fire_day` | float | dieselben Größen laut Saisonkurve (wie oft es dort um dieses Datum brennt) | „üblich wären 0,5 %“ |
| `risk_ratio` | float | `p_big_fire_day / p_clim_big_fire_day` | Text „5× so hoch wie üblich“, **nicht** zum Färben |
| `risk_class` | text | `low`, `normal`, `elevated`, `high`, `very_high` | **Farbe** von Region und Kalendertag |
| `source` | text | `model` oder `climatology` | bei `climatology`: „nur Saisonwert, keine Vorhersage“ |
| `model_version` | text | `0.2-weather` (mit Wetter) oder `0.1-noweather` (ohne Wetter, Rückfall) | Fußnote; bei `noweather` Hinweis „ohne Wetter“ |

**Warum nach `risk_class` färben und nicht nach `risk_ratio`:** Im Winter ist die Saisonkurve fast 0. Dann gibt eine
winzige Wahrscheinlichkeit schnell ein hohes Verhältnis. `risk_class` hat das schon berücksichtigt: Unter 2 % ist
eine Region höchstens `normal`.

Wie oft nach einer Klasse im Test tatsächlich ein Großfeuer-Tag folgte (Tag 1):

| Klasse | Großfeuer-Tag folgte |
|---|---|
| `low` | 0,9 % |
| `normal` | 1,6 % |
| `elevated` | 11 % |
| `high` | 25 % |
| `very_high` | 54 % |

### 3.2 `forecast_weekly`: Wochen 2–4

69 Zeilen je Ausgabetag: 23 Regionen × 3 Wochen. Keine Spalte ist leer.

| Spalte | Bedeutung | Im Frontend |
|---|---|---|
| `region_id`, `issue_date`, `source`, `model_version` | wie oben | |
| `week_start` | Montag der Woche | „Woche ab 23.11.“ |
| `week_ahead` | 2, 3, 4 | Reihenfolge |
| `p_below`, `p_normal`, `p_above` | Wahrscheinlichkeit für weniger / üblich viel / mehr Feueraktivität als in früheren Jahren in dieser Woche; Summe = 1 | dreigeteilter Balken |
| `expected_big_fire_days`, `clim_big_fire_days` | erwartete und übliche Zahl der Großfeuer-Tage | „erwartet 0,17, üblich 0,14“ |

Keine Prozent pro Tag anzeigen, es ist nur eine Tendenz. Liegt `p_above` nahe 1/3, „keine klare Tendenz“ schreiben.

### 3.3 `forecast_skill`: Wie verlässlich?

Etwa 480 Zeilen. Sie ändern sich nur, wenn das Modell neu trainiert wird.

| Spalte | Bedeutung |
|---|---|
| `product` | `daily` oder `weekly` |
| `target` | `big_fire_day`, `fire_day`, `week_activity` |
| `lead` | Tage (daily) bzw. Wochen (weekly) |
| `region_id` | Region oder `all` |
| `bss_vs_climatology`, `ci_lo`, `ci_hi` | Gewinn gegenüber der Saisonkurve mit 90-%-Intervall; > 0 heißt besser |
| `auc`, `pr_auc`, `ece`, `hit_rate`, `false_alarm_ratio` | Trennschärfe, Kalibrierung, Warnschwelle; **können leer sein** (zusammen 93-mal, z. B. Regionen ohne Warnung) |
| `n_events` | Großfeuer-Tage im Test |
| `use_model` | wird für diesen Vorlauf das Modell ausgeliefert (sonst die Saisonkurve) |
| `skill_basis` | `analysis_with_noise` (mit echten Vorhersagefehlern gemessen) oder `no_weather` |

Für eine kleine Grafik „So gut trifft die Vorhersage“ reichen die Zeilen mit `region_id = 'all'` und
`target = 'big_fire_day'`. Gewinn je Vorlauf, mit Wetter:

| Tag 1 | Tag 3 | Tag 5 | Tag 7 | Tag 10 |
|---|---|---|---|---|
| 0,25 | 0,15 | 0,11 | 0,08 | 0,05 |

### 3.4 `status.json`: Wie aktuell?

```json
{"last_run_utc": "2026-11-15T08:24:56+00:00", "ok": true, "issue_date": "2026-11-15", "issue_date_age_days": 0,
 "model_version": "0.2-weather", "weather_used": true, "weather_provider": "meteomatics", "warnings": []}
```

Anzeige im Frontend:
- Ist `issue_date_age_days` > 2 oder `warnings` nicht leer, einen Hinweis zeigen, z. B. „Stand vom 13.11.“ oder
  „Vorhersage ohne Wetter“.
- `weather_provider` wechselt am 23.11. von `meteomatics` auf `open-meteo`.

---

## 4. Datenbank und Laden

### 4.1 `db/init/003_forecast.sql` (neu)

Nach dem Muster von `001_schema.sql` und `002_areas.sql`:
- Gespeichert werden die Läufe der letzten 14 Tage.
- Das Backend liest das neueste `issue_date`.

```sql
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
```

`region_id` bekommt absichtlich keinen Fremdschlüssel auf `regions`. `load_to_db.py` ersetzt `regions` bei jedem
Lauf, und die Forecast-Tabellen sollen davon unabhängig bleiben.

### 4.2 `pipeline/load_forecast_to_db.py` (neu)

Aufgebaut wie `load_to_db.py`, aber ein eigenes Skript, weil der Forecast einen anderen Rhythmus hat:

- `data/forecast/manifest.json` und `status.json` lesen. Nur laden, wenn `status.ok` wahr ist. Sonst bleiben die
  letzten gültigen Zeilen in der Datenbank.
- Die Spalten der Parquet-Dateien genau mit den Datenbank-Spalten vergleichen. NaN abweisen, leere Werte als NULL
  schreiben.
- In **einer Transaktion**:
  - `forecast_daily` und `forecast_weekly`: die Zeilen desselben `issue_date` löschen und neu einfügen, Läufe
    älter als 14 Tage löschen.
  - `forecast_skill`: komplett ersetzen.
  - `forecast_status`: die eine Zeile überschreiben.
- `--dry-run` wie in `load_to_db.py`.
- **Einbindung:** In `pipeline/update_daily.py` wird es nach dem Forecast-Schritt aufgerufen, bei `--load-db`, also
  wie `load_to_db.py` heute. `pipeline/requirements.txt` braucht nichts Neues (psycopg und pyarrow sind da).

---

## 5. Backend

Das folgt dem Aufbau auf dem Branch `app`: `routes/data.py`, `services/`, `dtos.py`, `errors.py`, Pfade unter
`/api/...`.

### 5.1 `dtos.py`

```python
RiskClass = Literal["low", "normal", "elevated", "high", "very_high"]
ForecastSource = Literal["model", "climatology"]


class ForecastDay(ResponseModel):
    region_id: str
    target_date: dt.date
    lead_days: int
    p_big_fire_day: float
    p_big_fire_day_lo: float
    p_big_fire_day_hi: float
    p_fire_day: float
    p_clim_big_fire_day: float
    p_clim_fire_day: float
    risk_ratio: float
    risk_class: RiskClass
    source: ForecastSource
    model_version: str


class ForecastDailyResponse(ResponseModel):
    issue_date: dt.date
    days: list[ForecastDay]


class ForecastWeek(ResponseModel):
    region_id: str
    week_start: dt.date
    week_ahead: int
    p_below: float
    p_normal: float
    p_above: float
    expected_big_fire_days: float
    clim_big_fire_days: float
    source: ForecastSource
    model_version: str


class ForecastWeeklyResponse(ResponseModel):
    issue_date: dt.date
    weeks: list[ForecastWeek]


class ForecastSkillRow(ResponseModel):
    product: Literal["daily", "weekly"]
    target: str
    lead: int
    region_id: str
    bss_vs_climatology: float | None
    ci_lo: float | None
    ci_hi: float | None
    auc: float | None
    hit_rate: float | None
    false_alarm_ratio: float | None
    use_model: bool
    skill_basis: str


class ForecastSkillResponse(ResponseModel):
    rows: list[ForecastSkillRow]


class ForecastStatusResponse(ResponseModel):
    last_run_utc: dt.datetime
    ok: bool
    issue_date: dt.date
    issue_date_age_days: int
    model_version: str
    weather_used: bool
    weather_provider: str | None
    warnings: list[str]
```

`model_version` steht je Zeile, weil einzelne Vorläufe auf die Stufe ohne Wetter zurückfallen können.

Außerdem kommt in `Features` das Feld `forecast: bool` dazu. Es wird erst `true`, wenn `forecast_daily` Zeilen hat,
nach der Regel dort: „Only set to true once real data is returned“.

### 5.2 `services/forecast.py` (neu)

Nur Abfragen, keine Rechnungen:

| Funktion | Inhalt |
|---|---|
| `latest_issue_date(conn)` | `SELECT max(issue_date) FROM forecast_daily` |
| `build_forecast_daily(conn, region_id, target_date)` | Zeilen des neuesten `issue_date`, nur ES- und PT-Regionen (Join auf `regions`, `country = ANY(API_COUNTRIES)`), sortiert nach Region und `lead_days` |
| `build_forecast_weekly(conn, region_id)` | dasselbe für die Wochen |
| `build_forecast_skill(conn)` | alle Zeilen; französische Regionen weglassen, `all` behalten |
| `build_forecast_status(conn)` | die Zeile aus `forecast_status`, dazu `issue_date_age_days` = heute (UTC) − `issue_date` |

Gibt es noch keinen Lauf, kommt ein neuer Fehler `FORECAST_NOT_AVAILABLE` (HTTP 503), eingetragen in `errors.py` und
`errors.md` wie die anderen. Eine unbekannte `region_id` gibt denselben Fehlercode wie bei den bestehenden
Endpoints.

### 5.3 `routes/data.py`

```python
@router.get("/forecast/daily", response_model=ForecastDailyResponse, responses=ERRORS_DOC, tags=["Kann"])
def forecast_daily(region_id: str | None = None, target_date: dt.date | None = None):
    with connect() as conn:
        return build_forecast_daily(conn, region_id, target_date)


@router.get("/forecast/weekly", response_model=ForecastWeeklyResponse, responses=ERRORS_DOC, tags=["Kann"])
def forecast_weekly(region_id: str | None = None):
    with connect() as conn:
        return build_forecast_weekly(conn, region_id)


@router.get("/forecast/skill", response_model=ForecastSkillResponse, responses=ERRORS_DOC, tags=["Kann"])
def forecast_skill():
    with connect() as conn:
        body = build_forecast_skill(conn)
    return JSONResponse(jsonable_encoder(body), headers={"Cache-Control": "public, max-age=86400"})


@router.get("/forecast/status", response_model=ForecastStatusResponse, responses=ERRORS_DOC, tags=["Kann"])
def forecast_status():
    with connect() as conn:
        return build_forecast_status(conn)
```

| Aufruf | Zweck | Zeilen |
|---|---|---|
| `GET /api/forecast/daily?region_id=PT11` | Kalender und Tooltip einer Region | 10 |
| `GET /api/forecast/daily?target_date=2026-11-18` | Karte für einen Tag | 20 (ES + PT) |
| `GET /api/forecast/daily` | alles auf einmal (klein genug) | 200 |
| `GET /api/forecast/weekly?region_id=PT11` | Wochenausblick | 3 |
| `GET /api/forecast/skill` | Güte je Vorlauf | ~420 |
| `GET /api/forecast/status` | Stand und Hinweise | 1 |

Die Antworten von `daily` und `weekly` dürfen bis zum nächsten Lauf zwischengespeichert werden, z. B. mit
`Cache-Control: max-age=3600`.

### 5.4 `services/meta.py` und Tests

- In `features` kommt `"forecast": <forecast_daily hat Zeilen>` dazu.
- Tests nach dem Muster von `backend/tests/test_api.py`: Die erwarteten Werte werden mit pandas aus
  `data/forecast/*.parquet` berechnet.
  - `region_id=PT11` liefert 10 Tage, `lead_days` 1–10 ohne Lücke, lo ≤ p ≤ hi.
  - `target_date` liefert nur ES- und PT-Regionen.
  - `p_below + p_normal + p_above ≈ 1`.
  - Ohne Daten kommt `FORECAST_NOT_AVAILABLE`.

---

## 6. Frontend

1. **Typen:** Läuft das Backend lokal, `npm run gen:types` ausführen. Dann in `services/api/types.ts` die kurzen
   Namen ergänzen (`ForecastDailyResponse`, `ForecastDay`, …).
2. **`services/api/fireApi.ts`:**
   ```ts
   forecastDaily: (query: { region_id?: string; target_date?: string }, signal?: AbortSignal) =>
     apiRequest<ForecastDailyResponse>("GET", "/api/forecast/daily", { query, signal }),
   forecastWeekly: (query: { region_id?: string }, signal?: AbortSignal) =>
     apiRequest<ForecastWeeklyResponse>("GET", "/api/forecast/weekly", { query, signal }),
   forecastSkill: (signal?: AbortSignal) => apiRequest<ForecastSkillResponse>("GET", "/api/forecast/skill", { signal }),
   forecastStatus: (signal?: AbortSignal) => apiRequest<ForecastStatusResponse>("GET", "/api/forecast/status", { signal }),
   ```
3. **Mock** (`services/mock/handlers.ts`): Ohne `VITE_API_MODE=live` beantwortet der Mock alle Anfragen, er braucht
   also auch Antworten für die neuen Pfade.
   - Am einfachsten eine kleine JSON-Kopie aus `data/forecast/csv/` in `services/mock/` ablegen.
   - Im Mock `features.forecast: true` setzen. Mit `VITE_MOCK_DISABLE=forecast` lässt sich „kein Forecast“ testen.
4. **Farben** (`lib/colors.ts`):
   - `RISK_COLOR` und `RISK_LABEL` für die fünf Klassen, nach dem Muster von `AGE_COLOR`/`AGE_LABEL`.
   - Eine sequenzielle Skala von hell bis dunkelrot, auch für Farbenblinde unterscheidbar.
   - Beschriftungen z. B. „gering“, „normal“, „erhöht“, „hoch“, „sehr hoch“.
5. **Anzeige:**
   - **Karte** (`components/map/FireMap.tsx`): Regler „heute + n Tage“ (1–10), Regionen gefärbt nach
     `risk_class`.
   - **Kalender** (`RingCalendar.tsx` / `YearHeatmap.tsx`): hinter dem letzten gemessenen Tag die 10
     Vorhersagetage, sichtbar anders gezeichnet (z. B. schraffiert) und mit „Vorhersage“ beschriftet.
   - **Tooltip:** z. B. „Großfeuer-Wahrscheinlichkeit 2,5 % (Spanne 1–4 %, üblich 0,5 %). Vorhersage vom 15.11.,
     4 Tage voraus.“
   - **Wochen 2–4:** dreigeteilter Balken, bei unklarer Lage „keine klare Tendenz“.
   - **`source = climatology`:** „nur Saisonwert“. **`model_version = 0.1-noweather`:** „ohne Wetter“.
   - **Stand** aus `/forecast/status`. Ist er alt oder gibt es Warnungen, einen Hinweis zeigen.
6. **Nur anzeigen, wenn `meta.features.forecast === true`.**

### 6.1 Pflichttexte

- **Quellenangabe** (Lizenz CC BY 4.0, Pflicht):
  „Feuerdaten: NASA FIRMS. Wetterdaten: Open-Meteo.com (ECMWF IFS, ERA5), bis 22.11.2026 auch Meteomatics.“
- **Was vorhergesagt wird:** erkannte Feueraktivität je Region, keine einzelnen Brände, keine Entstehung und keine
  verbrannte Fläche. Die meisten Brände legen Menschen. Die Vorhersage sagt, wie günstig die Bedingungen sind.
- **Wie weit man trauen kann:** Tage 1–3 stützen sich vor allem auf laufende Feuer, Tage 4–10 auf die
  Wettervorhersage. Die Wochen 2–4 sind nur eine Tendenz.
- **Vorläufige Daten:** Die letzten Tage beruhen auf vorläufigen NRT-Daten, `day_status.is_provisional`.

---

## 7. Reihenfolge

**Minimalweg für die Demo:**
1. Merge (Abschnitt 1).
2. `003_forecast.sql` und `load_forecast_to_db.py`, einmal lokal laden.
3. `GET /api/forecast/daily` und `/status` sowie `features.forecast`.
4. Im Frontend: Kartenfärbung mit Tagesregler, Tooltip, Quellenangabe, eine Mock-Antwort.

**Danach:** Wochenausblick, Güte-Grafik, Kalender, Einhängen des Laders in `update_daily.py`.

## 8. Offene Entscheidungen

| Frage | Vorschlag | Betrifft |
|---|---|---|
| Forecast in der API-Spezifikation v3, mit welchem Tag? | `Kann`, Feature-Flag `forecast` | `docs/Fire-API_Spezifikation_v3.md`, `dtos.py` |
| Grenzen der Risikoklassen | wie in `forecast/config.yaml` | nur Werte |
| Ziel des Wochenausblicks | vorerst `frp_harm` | nur Werte |
| Rückfall je Region (Regel 3.5) | Rückfall erst bei Gewinn ≤ 0 | nur Werte |
| Open-Meteo: ist die App nicht-kommerziell? | ja, sonst bezahlter Zugang | Betrieb |

## 9. Checkliste

- [ ] `weather_prediction` gemergt, `data/harmonised/` vorher gesichert
- [ ] `db/init/003_forecast.sql`
- [ ] `pipeline/load_forecast_to_db.py`, eingehängt in `update_daily.py` (`--load-db`)
- [ ] `backend/dtos.py`: Forecast-Modelle, `Features.forecast`
- [ ] `backend/services/forecast.py`, `backend/routes/data.py`: 4 Endpoints
- [ ] `backend/errors.py`, `errors.md`: `FORECAST_NOT_AVAILABLE`
- [ ] Backend-Tests
- [ ] Frontend: `gen:types`, `types.ts`, `fireApi.ts`, Mock
- [ ] Frontend: Farben, Karte, Kalender, Tooltip, Wochenbalken, Stand-Hinweis
- [ ] Frontend: Quellenangabe und Pflichttexte (6.1)
