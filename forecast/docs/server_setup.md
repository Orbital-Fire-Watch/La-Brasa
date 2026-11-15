# Forecast auf dem Server einrichten

Diese Anleitung ist für die Person, die den Server einrichtet. Sie beschreibt Schritt für Schritt, was auf den Server
muss, damit die tägliche Brandgefahr-Vorhersage automatisch läuft. Was die Vorhersage rechnet, steht in
[../README.md](../README.md) und [weather_model.md](weather_model.md). Wie Backend und Frontend die Ergebnisse nutzen,
steht in [integration_backend_frontend.md](integration_backend_frontend.md).

Stand: 15.11.2026, mit Schritt 5, Ensemble und Open-Meteo nach dem 22.11. ([honest_evaluation.md](honest_evaluation.md)).

---

## 0. Überblick

```
Laptop (bei Bedarf, z. B. wöchentlich)            Server (täglich, per Cron)
  run_forecast.py train  (11 min)                    1. Feuerdaten aktualisieren   (Team-Pipeline, noch offen)
        │                                            2. forecast/daily.py          (~1 min)
        └── data/forecast/models/bundle.pkl ──────►      Wetter holen + predict
                                                     3. Ergebnis in die Datenbank  (noch offen)
```

- Auf dem Server läuft **nur `daily.py`**: 1 Kern, etwa 1,1 GB RAM, etwa 1 Minute am Tag. Davon ist das meiste
  Warten auf die Wetter-APIs, `predict` selbst braucht 7 s.
- Das schwere Training (`train`) läuft auf einem Arbeitsrechner. Danach wird nur die Datei `bundle.pkl` (1 MB)
  hochgeladen.
- Der Server hat 4 vCores und 8 GB RAM, für diesen Teil stehen höchstens 3,4 GB zur Verfügung. Das reicht mit Abstand.

| Lauf | Dauer | CPU | RAM (Spitze) | Netz |
|---|---|---|---|---|
| `daily.py` (Wetter + Ensemble + `predict`) | ~1 min | 1 Kern | 1,1 GB | bis 22.11. 16 Meteomatics-Anfragen + Ensemble (Open-Meteo), danach nur Open-Meteo (~800 gewichtete Aufrufe von 10.000 erlaubten); wenige MB |
| `run_forecast.py predict` allein | ~7 s | 1 Kern | 1,1 GB | keins |
| `run_forecast.py train` (nicht auf dem Server empfohlen) | ~6,5 min auf dem Laptop, auf vCores eher 10–15 min (nicht gemessen) | 1 Kern | 1,1 GB | keins |

---

## 1. Voraussetzungen

- Linux mit `cron`. Zum Messen ist `/usr/bin/time` nützlich, aber nicht nötig.
- **Python 3.14.** Getestet ist nur 3.14.4, die Paketversionen in `forecast/requirements.txt` sind darauf
  festgelegt. Andere Versionen auf eigenes Risiko.
- Ausgehender HTTPS-Zugang zu:
  - `api.meteomatics.com`, bis zum 22.11.2026,
  - `api.open-meteo.com`, `archive-api.open-meteo.com` und `ensemble-api.open-meteo.com`, dauerhaft, ohne Schlüssel.
- Etwa 400 MB Platz: Code, `data/harmonised/` mit 250 MB, `data/forecast/` mit 50 MB, dazu die virtuelle Umgebung.

---

## 2. Code holen

```bash
cd /srv                                   # Beispielpfad, überall unten anpassen
git clone <repo-url> La-Brasa
cd La-Brasa
git checkout <branch mit forecast/>       # derzeit weather_prediction, nach dem Merge der Hauptbranch
```

---

## 3. Python-Umgebung

```bash
cd /srv/La-Brasa/forecast
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q             # 50 Tests, ohne Internet, wenige Sekunden
```

`matplotlib` braucht nur die Datenanalyse und `pytest` nur die Tests. Wer es schlank will, kann beide weglassen, dann
fallen aber die Tests weg.

---

## 4. Daten auf den Server kopieren

`data/` ist von Git ausgeschlossen. Die Dateien müssen deshalb **einmal** von einem Rechner kopiert werden, auf dem
sie liegen.

| Datei | Größe | Wofür | Woher |
|---|---|---|---|
| `data/harmonised/activity_daily_harmonised.parquet` | 3 MB | Feuerdaten je Region und Tag | Harmonisierung (Team-Pipeline) |
| `data/harmonised/day_status.parquet` | 40 KB | Status je Tag (vorläufig, SNPP in Betrieb) | Harmonisierung |
| `data/forecast/weather_points.parquet` | 8 KB | die 182 Wetterpunkte und ihre Gewichte | Laptop |
| `data/forecast/weather_points_history_core.parquet` | 11 MB | ERA5-Historie 2012 bis 08.11.2026 (wird für den FWI gebraucht) | Laptop |
| `data/forecast/weather_points_history_fire.parquet` | 3 MB | Fosberg, Waldbrandwarnung, Dürreindex 2012 bis 13.11.2026 | Laptop |
| `data/forecast/weather_region_history_core.parquet` | 10 MB | `daily.py` liest daraus das Ende der Historie | Laptop |
| `data/forecast/weather_region_history_fire.parquet` | 3 MB | ebenso | Laptop |
| `data/forecast/models/bundle.pkl` | 1 MB | die trainierten Modelle | Laptop, nach `train` |

Die Dateien `weather_*_recent_*` und `weather_*_forecast_*` holt `daily.py` selbst. Man kann sie trotzdem mitkopieren,
dann funktioniert auch ein Lauf ohne Internet.

Nur wer `train` auf dem Server laufen lassen will, braucht zusätzlich `data/harmonised/hotspots_harmonised.parquet`
(24 MB) und `data/forecast/ifs_errors.parquet` (die gemessenen IFS-Fehler, 1,7 MB). Ohne die zweite Datei wird ohne
Vorhersagefehler ausgewählt und ausgewertet.

Beispiel vom Laptop aus:

```bash
cd ~/Projekte/La-Brasa
rsync -av data/harmonised/activity_daily_harmonised.parquet data/harmonised/day_status.parquet \
      server:/srv/La-Brasa/data/harmonised/
rsync -av data/forecast/weather_points.parquet data/forecast/weather_points_history_*.parquet \
      data/forecast/weather_region_history_*.parquet server:/srv/La-Brasa/data/forecast/
rsync -av data/forecast/models/bundle.pkl server:/srv/La-Brasa/data/forecast/models/
```

> **`bundle.pkl` ist eine Pickle-Datei.** Beim Laden kann sie Code ausführen. Deshalb nur eine Datei hochladen, die
> `run_forecast.py train` aus diesem Repository erzeugt hat, und nie eine aus fremder Quelle.

---

## 5. Zugangsdaten (nur bis 22.11.2026)

In `/srv/La-Brasa/.env` eintragen, nach dem Muster von `.env.example`:

```
METEOMATICS_USERNAME=...
METEOMATICS_PASSWORD=...
```

```bash
chmod 600 /srv/La-Brasa/.env
```

- Die Datei nie committen und die Zugangsdaten nie in Logs oder URLs schreiben. Der Code schickt sie nur per
  HTTP-Basic-Auth mit.
- Ab dem 23.11.2026 stellt `daily.py` keine Anfragen mehr und rechnet ohne Wetter
  (`config.yaml`, `daily.meteomatics_valid_until`). Die Zugangsdaten können dann aus `.env` entfernt werden.

### 5.1 Ab dem 23.11.2026: Open-Meteo

`daily.py` stellt von selbst auf Open-Meteo um (`config.yaml`, `daily.fallback_provider`). Auf dem Server ist dafür
nichts zu tun. Zu beachten sind drei Dinge:
- **Nur für nicht-kommerzielle Nutzung kostenlos.** Mit Werbung, Abos oder kommerziellem Einsatz braucht es einen
  bezahlten Zugang.
- **Lizenz CC BY 4.0:** Die App muss die Quelle nennen, z. B. im Fuß der Karte: „Wetterdaten: Open-Meteo.com (ECMWF
  IFS, ERA5)“.
- **Ganz ohne Wetter:** `daily.fallback_provider: null` setzen. Dann rechnet `daily.py` nach dem 22.11. nur noch mit
  der Stufe ohne Wetter.

---

## 6. Erster Test von Hand

```bash
cd /srv/La-Brasa/forecast
.venv/bin/python daily.py --dry-run     # zeigt nur den Plan: welche Tage angefragt würden
.venv/bin/python daily.py               # echter Lauf: ~1 min
tail -1 ../data/forecast/logs/daily_runs.jsonl
```

In der letzten Zeile sollte stehen:

| Feld | Erwartet |
|---|---|
| `predict_exit` | `0` |
| `fetch` | alle Einträge `"ok"` (Meteomatics bis 22.11., danach `open-meteo:...`) |
| `weather_used` | `true`, bis zum 22.11. |
| `issue_date` | der letzte Tag der Feuerdaten |
| `runtime_s` | etwa 15 |

Außerdem schreibt jeder Lauf `data/forecast/status.json`:
- `ok`, `issue_date` und dessen Alter in Tagen,
- `weather_used` und `weather_provider`,
- `warnings`, z. B. „fire data end on …“ oder „no fresh weather forecast“.

Das Backend kann die Datei lesen und im Frontend „Stand vom …“ oder „Vorhersage ohne Wetter“ anzeigen.

Danach liegen in `data/forecast/` die Ergebnisse `forecast_daily.parquet`, `forecast_weekly.parquet` und
`forecast_skill.parquet` sowie CSV-Kopien unter `csv/`.

Zum Messen der Ressourcen:

```bash
/usr/bin/time -v .venv/bin/python daily.py 2>&1 | grep -E "Elapsed|Maximum resident"
```

---

## 7. Cron einrichten

> **Seit 15.11.2026:** Es gibt `pipeline/update_daily.py`. Es aktualisiert die Feuerdaten (FIRMS), harmonisiert und
> ruft danach `forecast/daily.py` auf. Auf dem Server reicht dann **ein** Cron-Eintrag für `update_daily.py` statt
> des Eintrags unten (`pipeline/README.md`, Abschnitt 4). Dafür braucht der Server zusätzlich:
> - `FIRMS_MAP_KEY` in `.env`,
> - die Umgebung `harmonisation/.venv`,
> - den Ordner `data/raw/` (etwa 120 MB, die FIRMS-CSVs),
> - und den vollen Ordner `data/harmonised/`.
>
> Gemessen: höchstens 2,05 GB RAM, etwa 2 Minuten.

`crontab -e` für den Benutzer, dem `/srv/La-Brasa` gehört. Die Zeiten sind in UTC, falls der Server auf UTC läuft:

```cron
# Forecast täglich 07:30 UTC, nach der Aktualisierung der Feuerdaten
30 7 * * *  cd /srv/La-Brasa/forecast && nice -n 10 .venv/bin/python daily.py >> ../data/forecast/logs/daily_$(date -u +\%F).log 2>&1

# Logs älter als 30 Tage löschen
15 7 * * *  find /srv/La-Brasa/data/forecast/logs -name 'daily_*.log' -mtime +30 -delete
```

- In der crontab muss `%` als `\%` geschrieben werden.
- `nice -n 10` gibt App und Datenbank Vorrang.
- Den Thread-Wert muss man nicht setzen. `FORECAST_THREADS` steht standardmäßig auf 1, und mehr wäre hier nicht
  schneller.
- Überschneidungen sind ausgeschlossen: Läuft noch ein Lauf, endet der nächste sofort mit Rückgabewert 3.

**Optional, wenn `train` doch auf dem Server laufen soll:**

```cron
0 3 * * 0   cd /srv/La-Brasa/forecast && nice -n 19 .venv/bin/python run_forecast.py train --skip-tests >> ../data/forecast/logs/train_$(date -u +\%F).log 2>&1
```

Das ist sonntags um 03:00 UTC, mit niedrigster Priorität, auf 1 Kern und mit 0,9 GB RAM. Dafür werden zusätzlich
`hotspots_harmonised.parquet` (Abschnitt 4) und eine einmalige Messung auf dem Server gebraucht. Neu trainieren lohnt
sich vor allem, wenn neue **Archiv**-Feuerdaten dazukommen. Monatlich reicht in der Regel.

---

## 8. Mit Docker statt direkt (Vorschlag)

Einen Dienst `forecast` gibt es in `docker-compose.yml` noch nicht. Das ist eine Änderung außerhalb von `forecast/` und
eine Entscheidung des Teams. Ein möglicher Aufbau:

```yaml
  forecast:
    build: ./forecast                 # Dockerfile mit python:3.14-slim, pip install -r requirements.txt
    profiles: ["pipeline"]
    working_dir: /app/forecast
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env:ro
    environment:
      FORECAST_THREADS: "1"
    cpus: 1
    mem_limit: 3400m
```

Cron auf dem Rechner startet dann:

```cron
30 7 * * *  cd /srv/La-Brasa && docker compose run --rm forecast python daily.py >> data/forecast/logs/daily_$(date -u +\%F).log 2>&1
```

Die Pfade im Code beziehen sich auf den Ordner über `forecast/`. Deshalb müssen `data/` und `.env` dort liegen, wie
oben eingebunden.

---

## 9. Was noch fehlt, damit es ganz rund läuft (Team)

1. **Tägliche Aktualisierung der Feuerdaten.** Die Vorhersage startet am letzten Tag in `data/harmonised/`. Solange
   dort nichts Neues ankommt, holt `daily.py` zwar täglich neues Wetter, rückt aber nicht weiter. Sind die Feuerdaten
   älter als 2 Tage, warnt es. Gebraucht wird ein täglicher Lauf „FIRMS laden, harmonisieren“ **vor** `daily.py`.
   Dafür ist `pipeline/update_daily.py` gedacht, das laut Haupt-README noch nicht umgesetzt ist.
2. **Ergebnisse in die Datenbank und eine API dafür.** `forecast_daily`, `forecast_weekly` und `forecast_skill` liegen
   bisher nur als Dateien vor. Der Vorschlag dazu (Tabellen, Lader, Endpoints) steht in
   [integration_backend_frontend.md](integration_backend_frontend.md). Der Lader läuft dann direkt nach `daily.py`.
3. **Dockerfile für `forecast/`**, falls ihr den Weg über Docker nehmt (Abschnitt 8).

---

## 10. Wenn etwas nicht läuft

| Zeichen | Ursache | Abhilfe |
|---|---|---|
| Rückgabewert 2, `no fitted models` | `bundle.pkl` fehlt | auf dem Laptop `run_forecast.py train` laufen lassen und `bundle.pkl` hochladen |
| `bundle has another format` | der Code wurde aktualisiert, `bundle.pkl` ist alt | neu trainieren und hochladen |
| Warnung `config.yaml changed since training` | `model` oder `risk_class` in der Konfiguration geändert | neu trainieren |
| `regions differ from the training data` | andere Regionen in `data/harmonised/` | neu trainieren |
| `fetch` zeigt `error: ...` oder `skipped (authentication)` | Meteomatics nicht erreichbar, Zugangsdaten falsch oder abgelaufen | `.env` prüfen. Der Lauf rechnet trotzdem, ohne Wetter. |
| `weather_used: false` | keine Wettervorhersage, die höchstens 1 Tag alt ist | normal nach dem 22.11., sonst den Abschnitt `fetch` im Log ansehen |
| Warnung `fire data end on ...` | `data/harmonised/` wird nicht aktualisiert | Abschnitt 9, Punkt 1 |
| Rückgabewert 1, `failed its checks` | die Ausgabe verletzt den Vertrag | Die alten Tabellen bleiben stehen. Log an die Forecast-Entwicklerin geben. |
| Rückgabewert 3 | ein anderer Lauf ist noch aktiv | nichts tun. Steht `logs/daily.lock` lange, prüfen, ob ein Prozess hängt (`pgrep -af daily.py`). |

`data/raw/weather/meteomatics/` speichert jede Antwort von Meteomatics zwischen, das sind wenige 100 KB am Tag. Den
Ordner darf man jederzeit leeren, `daily.py` holt ohnehin immer frisch.

---

## 11. Kurz-Checkliste

- [ ] Code geholt, Branch mit `forecast/`
- [ ] `.venv` angelegt, `pip install -r requirements.txt`, `pytest -q` grün (41 Tests)
- [ ] Daten kopiert (Abschnitt 4), `bundle.pkl` vorhanden
- [ ] `.env` mit Meteomatics-Zugang, `chmod 600` (nur bis 22.11.)
- [ ] `daily.py --dry-run` und `daily.py` von Hand erfolgreich, `predict_exit: 0`
- [ ] Cron-Einträge für `daily.py` und das Löschen der Logs
- [ ] Team: tägliche Aktualisierung der Feuerdaten vor `daily.py`
- [ ] Team: Ergebnisse in die Datenbank und Endpoints im Backend
