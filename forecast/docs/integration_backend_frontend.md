# Forecast im Frontend: Was noch geändert werden muss

Stand: 14.11.2026, Modellversion `0.1-noweather`.

Der Forecast rechnet einmal am Tag und schreibt fertige Tabellen. Diese Tabellen gibt es schon.
Das Frontend spricht aber nur mit dem Backend, und das Backend kennt die Tabellen noch nicht.
Dieses Dokument zählt auf, **welche Dateien** dafür geändert oder neu angelegt werden müssen, in sinnvoller Reihenfolge.

Nichts davon ist bisher umgesetzt. `backend/`, `frontend/`, `db/` und `pipeline/` wurden für den Forecast bewusst
nicht angefasst.

---

## 1. Ausgangslage

| Was | Wo | Status |
|---|---|---|
| Forecast-Code | `forecast/` auf Branch `weather_prediction` | fertig (Schritt 1, ohne Wetter) |
| Ausgabetabellen | `data/forecast/forecast_daily.parquet`, `forecast_weekly.parquet`, `forecast_skill.parquet` (+ `csv/`) | vorhanden, nur lokal, von git ignoriert |
| Spalten der Tabellen | `forecast/contract.py`, `forecast/README.md` Abschnitt 4 | festgelegt |
| Datenbank-Tabellen | `db/init/` | **fehlen** |
| Laden in Postgres | `pipeline/` | **fehlt** |
| API-Endpoints | `backend/` | **fehlen** |
| Anzeige | `frontend/` | **fehlt** |

Inhalt der aktuellen Ausgabe:

- `forecast_daily`: 23 Regionen × 10 Tage = 230 Zeilen. Darunter sind 3 französische Regionen, die die API
  nicht ausliefert (`API_COUNTRIES = ("ES", "PT")`).
- `forecast_weekly`: 23 Regionen × Wochen 2–4 = 69 Zeilen.
- `forecast_skill`: die Güte je Produkt, Ziel, Vorlauf und Region. Sie ändert sich nur, wenn das Modell neu
  ausgewertet wird.

## 2. Datenfluss (Ziel)

```
einmal täglich
  harmonisation/run_pipeline.py      -> data/harmonised/*.parquet      (gibt es)
  pipeline/load_to_db.py             -> Postgres: activity_daily_...   (gibt es)
  forecast/fetch_weather.py forecast -> data/forecast/weather_*.parquet (gibt es, ab Schritt 4 gebraucht)
  forecast/run_forecast.py predict   -> data/forecast/forecast_*.parquet (gibt es; ~8 s, 1 Kern, 0,9 GB)
  pipeline/load_forecast_to_db.py    -> Postgres: forecast_*           (NEU)

bei jeder Anfrage
  Frontend -> GET /api/forecast/... -> Backend liest forecast_* aus Postgres (NEU), rechnet nichts
```

Das Backend rechnet keine Vorhersagen. Es liest nur die neueste fertige Ausgabe. Dadurch bleibt die API schnell,
und die Meteomatics-Zugangsdaten werden nur im täglichen Lauf gebraucht, nie im Backend.

---

## 3. Änderungen je Datei

### 3.1 Zuerst: Branch zusammenführen und `.gitignore`

`weather_prediction` muss in den Arbeits-Branch (z. B. `app`) gemergt werden. Damit kommen `forecast/` und die
`.gitignore`-Einträge mit:

```gitignore
data/forecast/
*[Pp][Rr][Oo][Mm][Pp][Tt]*.md
*[Pp][Rr][Oo][Mm][Pp][Tt]*.txt
```

> **Achtung, solange nicht gemergt ist:** Auf `app` fehlen diese Einträge. `git status` zeigt dort
> `data/forecast/` als neue Dateien an, darunter etwa 27 MB Wetterdaten. Ein `git add .` würde sie mitnehmen.

### 3.2 `db/init/003_forecast.sql` (neu)

Drei Tabellen mit denselben Spalten wie die Parquet-Dateien, nach dem Muster von `001_schema.sql`.
Es werden nur die Läufe der letzten Tage aufbewahrt: Schlüssel ist `issue_date`, das Backend liest das neueste.

```sql
-- Forecast tables (written by forecast/run_forecast.py, loaded by pipeline/load_forecast_to_db.py).
-- Column meaning: forecast/README.md section 4. Not touched by pipeline/load_to_db.py.
-- Existing database: run once with psql -f /docker-entrypoint-initdb.d/003_forecast.sql

CREATE TABLE IF NOT EXISTS forecast_daily (
  region_id           TEXT NOT NULL,
  issue_date          DATE NOT NULL,
  target_date         DATE NOT NULL,
  lead_days           SMALLINT NOT NULL CHECK (lead_days BETWEEN 1 AND 10),
  p_big_fire_day      DOUBLE PRECISION NOT NULL,
  p_fire_day          DOUBLE PRECISION NOT NULL,
  p_clim_big_fire_day DOUBLE PRECISION NOT NULL,
  p_clim_fire_day     DOUBLE PRECISION NOT NULL,
  risk_ratio          DOUBLE PRECISION NOT NULL,
  risk_class          TEXT NOT NULL CHECK (risk_class IN ('low','normal','elevated','high','very_high')),
  p_big_fire_day_lo   DOUBLE PRECISION,          -- currently always filled; nullable for later model versions
  p_big_fire_day_hi   DOUBLE PRECISION,
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
  product            TEXT NOT NULL,              -- 'daily' | 'weekly'
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
  skill_basis        TEXT,
  PRIMARY KEY (product, target, lead, region_id)
);
```

In der aktuellen Ausgabe sind nur in `forecast_skill` Werte leer: `auc`, `pr_auc` und `hit_rate` je 3-mal,
`false_alarm_ratio` 152-mal (Regionen ohne Warnung). Diese Spalten sind deshalb ohne `NOT NULL`. `load_to_db.py` weist NaN ab, und so sollte es auch der neue Loader halten (3.3).

### 3.3 `pipeline/load_forecast_to_db.py` (neu)

Ein eigenes Skript ist besser als eine Erweiterung von `load_to_db.py`. Dieses ersetzt bei jedem Lauf **alle**
harmonisierten Tabellen, und der Forecast hat einen anderen Rhythmus und eine eigene Versionsprüfung.
Aufbau wie in `load_to_db.py`:

- `data/forecast/manifest.json` lesen und prüfen, dass `model_version` und die Spaltenliste zu dieser Version passen.
- Spalten der Parquet-Dateien genau mit den Datenbank-Spalten vergleichen. NaN abweisen, leere Werte als NULL schreiben.
- In **einer Transaktion**:
  - `forecast_daily` und `forecast_weekly`: die Zeilen mit derselben `issue_date` löschen und neu einfügen.
    Läufe, die älter als 14 Tage sind, löschen.
  - `forecast_skill`: komplett ersetzen.
- Optional `--dry-run` wie in `load_to_db.py`.

Für Docker braucht `pipeline/requirements.txt` nichts Neues (psycopg und pyarrow sind schon da).

### 3.4 Täglicher Lauf: `pipeline/update_daily.py` bzw. `docker-compose.yml`

`update_daily.py` ist laut README noch nicht umgesetzt. Wenn es kommt, hängen sich nach `load_to_db.py`
diese Schritte an:

```
python forecast/daily.py                     # Wetter holen (bis 22.11.2026) + predict; ~14 s, 1 Kern, 1,1 GB
python pipeline/load_forecast_to_db.py
```

`daily.py` fällt selbst auf die Stufe ohne Wetter zurück, wenn Meteomatics nicht antwortet oder der Account
abgelaufen ist (forecast/README.md, Abschnitt 2.2).

Für Docker gibt es zwei Möglichkeiten:

- **a)** Im Container `pipeline` zusätzlich `forecast/requirements.txt` installieren und `./forecast` einbinden.
- **b)** Einen eigenen Dienst `forecast` mit `profiles: ["pipeline"]`, Volume `./data:/app/data` und den
  Umgebungsvariablen `METEOMATICS_USERNAME` und `METEOMATICS_PASSWORD` aus `.env` anlegen.

Empfehlung: **b)**, weil der Forecast eigene Abhängigkeiten und eigene Zugangsdaten hat.

Der Server hat 4 vCores und 8 GB RAM, für den Forecast stehen höchstens 3,4 GB zur Verfügung. `predict` braucht
gemessen 8 s, 1 Kern und 0,9 GB. Für den Dienst reicht deshalb eine Begrenzung wie diese:

```yaml
    cpus: 1
    mem_limit: 3400m
    environment:
      FORECAST_THREADS: "1"
```

`run_forecast.py train` (11 min) läuft nicht auf dem Server, sondern auf einem Arbeitsrechner, z. B. wöchentlich.
Danach wird nur `data/forecast/models/bundle.pkl` auf den Server kopiert (forecast/README.md, Abschnitt 2.1).

**Für die Demo** reicht es, `run_forecast.py train` lokal laufen zu lassen und danach `load_forecast_to_db.py`
aufzurufen.

> Der Meteomatics-Zugang des Hackathons läuft am **22.11.2026** aus. Danach geht nur noch das Modell ohne Wetter
> (`run_forecast.py predict --no-weather`). Der tägliche Lauf muss damit umgehen können.

### 3.5 `backend/dtos.py`

Neue Modelle, abgeleitet von `RequestModel`/`ResponseModel` wie die bestehenden:

```python
RiskClass = Literal["low", "normal", "elevated", "high", "very_high"]
ForecastSource = Literal["model", "climatology"]


class ForecastDay(ResponseModel):
    region_id: str
    target_date: dt.date
    lead_days: int
    p_big_fire_day: float
    p_fire_day: float
    p_clim_big_fire_day: float
    p_clim_fire_day: float
    risk_ratio: float
    risk_class: RiskClass
    p_big_fire_day_lo: float | None
    p_big_fire_day_hi: float | None
    source: ForecastSource


class ForecastDailyResponse(ResponseModel):
    issue_date: dt.date
    model_version: str
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


class ForecastWeeklyResponse(ResponseModel):
    issue_date: dt.date
    model_version: str
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


class ForecastSkillResponse(ResponseModel):
    model_version: str
    rows: list[ForecastSkillRow]
```

Außerdem in `Features` das Feld `forecast: bool` ergänzen. Nach der Regel dort („Only set to true once real data
is returned“) wird es erst `true`, wenn die Tabelle `forecast_daily` Zeilen hat.

### 3.6 `backend/services/forecast.py` (neu)

Reine Abfragen, keine Rechnungen:

- `latest_issue_date(conn)`: `SELECT max(issue_date) FROM forecast_daily`
- `build_forecast_daily(conn, region_id | None, target_date | None)`: Zeilen der neuesten `issue_date`, nur Regionen
  in `API_COUNTRIES` (Join auf `regions` und `country = ANY(...)`), sortiert nach Region und `lead_days`.
- `build_forecast_weekly(conn, region_id | None)`: dasselbe für die Wochen.
- `build_forecast_skill(conn)`: alle Zeilen aus `forecast_skill`.
- Gibt es keinen Lauf: eigener Fehler, z. B. `FORECAST_NOT_AVAILABLE` (HTTP 404 oder 503). Er wird wie die anderen
  Fehler in `errors.py` und `errors.md` eingetragen.
- Ist `issue_date` älter als 2 Tage, bleibt die Antwort gültig. Das Frontend zeigt dann „Stand: …“ deutlich an.

### 3.7 `backend/routes/data.py`

Drei GET-Endpoints, im gleichen Stil wie `/meta` und `/regions`:

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
```

| Aufruf | Zweck | Zeilen |
|---|---|---|
| `GET /api/forecast/daily?region_id=PT11` | Kalender einer Region | 10 |
| `GET /api/forecast/daily?target_date=2026-11-18` | Karte für einen Tag | 20 (ES + PT) |
| `GET /api/forecast/daily` | alles auf einmal (klein genug) | 200 |
| `GET /api/forecast/weekly?region_id=PT11` | Wochenausblick | 3 |
| `GET /api/forecast/skill` | Güte je Vorlauf | ca. 480 |

Eine unbekannte `region_id` liefert denselben Fehlercode wie die anderen Endpoints.

Die Pfade folgen den bestehenden (`/api/...` ohne `v1`). `backend/AGENTS.md` empfiehlt `/api/v1/...`. Das betrifft
die ganze API und gehört nicht in diesen Schritt.

### 3.8 `backend/services/meta.py`

`"forecast": <forecast_daily hat Zeilen>` in `features` ergänzen. So blendet das Frontend den Forecast aus,
solange keine Daten geladen sind.

### 3.9 `backend/tests/test_api.py`

Nach dem Muster dort: Die erwarteten Werte werden mit pandas aus `data/forecast/*.parquet` berechnet und mit der
API verglichen. Zu prüfen sind:

- `region_id=PT11` liefert 10 Tage, `lead_days` 1–10 sind lückenlos.
- Für `target_date` kommen nur ES- und PT-Regionen zurück, keine französischen.
- `p_below + p_normal + p_above ≈ 1`.
- Ohne Daten kommt der neue Fehlercode.

### 3.10 Frontend

1. **Typen:** Läuft das Backend lokal, `npm run gen:types` ausführen. Das aktualisiert `services/api/schema.d.ts`.
   In `services/api/types.ts` dann kurze Namen ergänzen (`ForecastDailyResponse`, `ForecastDay`, …), wie für die
   anderen Typen.
2. **`services/api/fireApi.ts`:** Funktionen ergänzen:
   ```ts
   forecastDaily: (query: { region_id?: string; target_date?: string }, signal?: AbortSignal) =>
     apiRequest<ForecastDailyResponse>("GET", "/api/forecast/daily", { query, signal }),
   forecastWeekly: (query: { region_id?: string }, signal?: AbortSignal) =>
     apiRequest<ForecastWeeklyResponse>("GET", "/api/forecast/weekly", { query, signal }),
   forecastSkill: (signal?: AbortSignal) =>
     apiRequest<ForecastSkillResponse>("GET", "/api/forecast/skill", { signal }),
   ```
3. **Mock (`services/mock/handlers.ts`, `world.ts`):** Ohne `VITE_API_MODE=live` beantwortet der Mock alle Anfragen.
   Für die neuen Pfade braucht er Antworten, sonst bricht der Mock-Modus.
   - Einfachste Lösung: eine kleine JSON-Kopie aus `data/forecast/csv/` in `services/mock/` ablegen.
   - In `features` des Mock `forecast: true` setzen. Über `VITE_MOCK_DISABLE=forecast` lässt sich der Fall „kein
     Forecast“ testen.
4. **Farben (`lib/colors.ts`):** fünf Farben für `risk_class` und dazu die Beschriftung, z. B. als `RISK_COLOR` und
   `RISK_LABEL` nach dem Muster von `AGE_COLOR`/`AGE_LABEL`. Die Farben sollten für Farbenblinde unterscheidbar sein,
   z. B. eine sequenzielle Skala von hellgelb bis dunkelrot.
5. **Anzeige:** Ideen dazu stehen in `forecast/README.md` Abschnitt 4.
   - **Kalender** (`components/charts/RingCalendar.tsx` bzw. `YearHeatmap.tsx`): Hinter dem letzten gemessenen Tag
     folgen 10 Vorhersagetage, gefärbt nach `risk_class`. Sie sind sichtbar anders gezeichnet, z. B. schraffiert,
     und mit „Vorhersage“ beschriftet.
   - **Karte** (`components/map/FireMap.tsx`): ein Regler „heute + n Tage“, der die Regionen nach `risk_class` färbt.
   - **Tooltip:** z. B. „Großfeuer-Wahrscheinlichkeit 18 % (üblich 6 %). Vorhersage vom 14.11., 4 Tage voraus.“
   - **Wochen 2–4:** ein dreigeteilter Balken (weniger / üblich / mehr). Liegt `p_above` nahe 33 %, den Text
     „keine klare Tendenz“ zeigen.
   - **Bei `source = "climatology"`:** den Hinweis „nur Saisonwert, keine Vorhersage“ zeigen.
6. **Nur anzeigen, wenn `meta.features.forecast === true`.**

Wichtig für die Anzeige: Gefärbt wird nach **`risk_class`**, nicht nach `risk_ratio`. Im November ist die
Saisonkurve fast 0, deshalb ergeben sich hohe Verhältnisse bei winzigen Wahrscheinlichkeiten. Ein Beispiel ist
ES11 am 14.11.: `risk_ratio` 5,7, `p_big_fire_day` 0,06 %, `risk_class` `normal`. `risk_class` berücksichtigt das
schon.

---

## 4. Minimalweg für die Demo

Falls die Zeit knapp ist, reicht diese Reihenfolge, bis etwas sichtbar ist:

1. `weather_prediction` mergen (3.1).
2. `003_forecast.sql` und `load_forecast_to_db.py` anlegen (3.2, 3.3) und einmal lokal laden.
3. Nur den Endpoint `GET /api/forecast/daily` und `features.forecast` umsetzen (3.5–3.8).
4. Im Frontend nur die Kartenfärbung mit dem Tagesregler und einem Tooltip bauen, plus eine Mock-Antwort (3.10).

Wochenausblick, Güte-Grafik und täglicher Lauf können danach kommen.

## 5. Offene Entscheidungen fürs Team

| Frage | Vorschlag | Betrifft |
|---|---|---|
| Ist der Forecast Teil der API-Spezifikation v3, und mit welchem Tag (Muss/Soll/Kann)? | `Kann`, Feature-Flag `forecast` | `docs/`, `dtos.py` |
| Wo läuft der tägliche Lauf (eigener Container oder `pipeline`)? | eigener Dienst `forecast` | `docker-compose.yml` |
| Grenzen der Risikoklassen | wie in `forecast/config.yaml` | Werte, nicht Spalten |
| Ziel des Wochenausblicks (`frp_harm` oder SNPP) | vorerst `frp_harm` | Werte, nicht Spalten |
| Was passiert nach dem 22.11. ohne Meteomatics? | Modell ohne Wetter als Rückfall | täglicher Lauf |

Die Spalten bleiben bei allen Entscheidungen gleich. Backend und Frontend können also schon jetzt gebaut werden,
auch während das Modell mit Wetter (Schritt 2–4) noch entsteht.

## 6. Checkliste

- [ ] `weather_prediction` gemergt, `data/forecast/` wird ignoriert
- [ ] `db/init/003_forecast.sql`
- [ ] `pipeline/load_forecast_to_db.py`
- [ ] `backend/dtos.py`: Forecast-Modelle und `Features.forecast`
- [ ] `backend/services/forecast.py`
- [ ] `backend/routes/data.py`: 3 Endpoints
- [ ] `backend/services/meta.py`: `features.forecast`
- [ ] `backend/errors.py` und `errors.md`: `FORECAST_NOT_AVAILABLE`
- [ ] `backend/tests/test_api.py`
- [ ] `frontend`: `gen:types`, `types.ts`, `fireApi.ts`
- [ ] `frontend`: Mock-Antworten
- [ ] `frontend`: Farben, Karte, Kalender, Tooltip, Hinweistexte
- [ ] täglicher Lauf (`update_daily.py` oder eigener Docker-Dienst)
