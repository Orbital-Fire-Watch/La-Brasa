# pipeline/: tägliche Datenaktualisierung

Hier liegt der tägliche Ablauf, der die Feuerdaten aktuell hält und danach die Vorhersage rechnet. Dazu kommt der
Lader für Postgres (`load_to_db.py`, siehe README im Hauptordner).

```
cron, täglich
  python3 pipeline/update_daily.py
    1. ingestion/fetch_firms.py      neue FIRMS-Erkennungen -> data/raw/<produkt>/fire_{archive,nrt}_*.csv
    2. harmonisation/run_pipeline.py data/raw -> data/harmonised   (unveränderte Stufen werden übersprungen)
    3. load_to_db.py                 nur mit --load-db (Datenbank wird später angebunden)
    4. forecast/daily.py             Wetter + Vorhersage ab dem neuen letzten Tag
```

## 1. Einmalig einrichten

1. **FIRMS-Schlüssel** (kostenlos): Ihn gibt es unter <https://firms.modaps.eosdis.nasa.gov/api/map_key/>. In
   `La-Brasa/.env` eintragen:
   ```
   FIRMS_MAP_KEY=...
   ```
   Der Schlüssel steht nur im Pfad der Anfrage und wird nie ausgegeben. Ein Schlüssel erlaubt 5000 Anfragen in 10
   Minuten, ein täglicher Lauf braucht etwa 8–12. Erster Test am 15.11.2026: Schlüssel und Satellitenkennungen
   funktionieren, 250 neue Erkennungen bis zum 15.11. SNPP liefert seit dem 02.11. keine Daten.
2. **Umgebungen:** `harmonisation/.venv` (`pip install -r harmonisation/requirements.txt`) und `forecast/.venv` (siehe
   `forecast/README.md`). `fetch_firms.py` läuft mit der Umgebung der Harmonisierung, weil es deren Konfiguration
   liest.
3. **Test von Hand:**
   ```bash
   harmonisation/.venv/bin/python pipeline/ingestion/fetch_firms.py --dry-run   # holt und berichtet, ändert nichts
   python3 pipeline/update_daily.py                                              # ganzer Ablauf
   cat data/logs/update_status.json
   ```

## 2. Was `fetch_firms.py` macht

Für jedes FIRMS-Produkt aus `harmonisation/pipeline_config.yaml` (`sources`: MODIS, SNPP, NOAA-20, NOAA-21):

1. **Archiv (SP, endgültige Daten):**
   - Es fragt die Tage nach dem letzten Archivtag ab, 5 Tage je Anfrage (Grenze der API), bis eine Antwort leer
     ist. FIRMS
     veröffentlicht das Archiv mit etwa 2–3 Monaten Verzögerung, meist kommt also nichts.
   - Neue Archivtage kommen in die Archivdatei.
   - Die NRT-Zeilen dieser Tage werden aus der NRT-Datei entfernt, damit Archiv und NRT sich nie überlappen, wie
     in den ursprünglichen Downloads.
2. **NRT (Echtzeit):** ab dem letzten Tag in der NRT-Datei bis heute, mindestens die letzten 5 Tage (`--days`),
   höchstens 60 Tage zurück, 5 Tage je Anfrage. Fällt der tägliche Lauf einmal aus, wird die Lücke beim nächsten
   Lauf geschlossen. Neue Zeilen nach dem letzten Archivtag kommen in die NRT-Datei.
3. **Umrechnung ins Format der Download-Dateien:**
   - VIIRS: `bright_ti4` → `brightness`, `bright_ti5` → `bright_t31`.
   - Satellitenkennung: `N` → `SNPP`, `T`/`A` → `Terra`/`Aqua`.
   - `acq_time` wird vierstellig.
   - Eine unbekannte Satellitenkennung bricht ab und wird nicht still durchgelassen.
4. **Doppelte Zeilen** (gleicher Satellit, Ort, Datum und Uhrzeit) bleiben nur einmal.
5. **Gebiet:**
   - **MODIS- und SNPP-Zeilen** werden auf die 0,25°-Zellen beschränkt, die ihre bisherigen Dateien schon
     abdecken. Sonst würde sich das „gemeinsame Gebiet“ der Harmonisierung (`common_area.py`) verschieben, und die
     ganze Historie würde anders gezählt.
   - **NOAA-20/21** werden im Rechteck ihres ursprünglichen Downloads abgefragt; die Harmonisierung beschränkt
     sie dann wie bisher selbst.
6. **Sicherheit der Dateien:**
   - Jede CSV, die sich ändert, wird vorher nach `<datei>.bak` kopiert (eine Generation) und dann in einem Schritt
     ersetzt.
   - Aus den Archivdateien wird nie etwas gelöscht.
   - Schlägt das Archiv eines Produkts fehl, z. B. weil es für NOAA-21 noch kein Archiv gibt, läuft NRT trotzdem
     weiter.

## 3. Was `update_daily.py` macht

- **Reihenfolge** wie oben. Ein Fehler in einem Schritt hält die folgenden nicht auf:
  - Ohne neue FIRMS-Daten bleibt die Harmonisierung beim letzten Stand.
  - Der Forecast holt trotzdem frisches Wetter.
- **Sperrdatei:** Ein zweiter Lauf, der startet, während einer läuft, endet sofort (Rückgabewert 3).
- **1 Kern:** Jeder Schritt bekommt `OPENBLAS_NUM_THREADS=1` usw. (`UPDATE_THREADS`).
- **Protokoll:**
  - `data/logs/update_daily.jsonl`: eine Zeile je Lauf mit allen Schritten und Berichten,
  - `data/logs/update_status.json`: der letzte Lauf kurz, also `ok`, der letzte harmonisierte Tag
    (`harmonised_end`), die Schritte und Warnungen.
- **Rückgabewert:** 0, wenn alle Schritte ohne Fehler durchliefen, sonst 1. Eine verfehlte KPI der Harmonisierung
  zählt auch als 1, die Ausgaben sind dann trotzdem geschrieben.
  - Ausnahme: **I1b**, „zwei Läufe ergeben dieselben Dateien“. Die Harmonisierung prüft das nur, wenn dieselben
    Eingaben zweimal gerechnet werden. Bei neuen FIRMS-Daten, also an fast jedem Tag, steht I1b auf „nicht
    geprüft“ (`None`). Das gilt nicht als Fehler und steht als Hinweis im Protokoll.
  - Geprüft wird der Determinismus mit `harmonisation/.venv/bin/python run_pipeline.py --force`, z. B. einmal pro
    Woche. Am 15.11.2026 ergab das identische Dateien.

**Gemessen** am 15.11.2026 auf dem Laptop:

| Fall | Dauer | Arbeitsspeicher (Spitze) |
|---|---|---|
| neue Feuerdaten, also alles neu harmonisieren | etwa 1:50 min | 2,05 GB |
| unveränderte Feuerdaten (nur die Tests der Harmonisierung) | etwa 1:10 min | 1,9 GB |
| Forecast (`daily.py`) | etwa 30 s | 1,1 GB |

Das passt auf den Server mit 4 vCores und höchstens 3,4 GB für diesen Teil.

## 4. Cron

```cron
# täglich 07:00 UTC: Feuerdaten, Harmonisierung, Forecast
0 7 * * *  cd /srv/La-Brasa && nice -n 10 python3 pipeline/update_daily.py >> data/logs/update_$(date -u +\%F).log 2>&1
15 6 * * *  find /srv/La-Brasa/data/logs -name 'update_*.log' -mtime +30 -delete
```

Dieser eine Eintrag **ersetzt** den Cron-Eintrag für `forecast/daily.py` aus `forecast/docs/server_setup.md`, denn
`update_daily.py` ruft `daily.py` selbst auf. FIRMS stellt die NRT-Daten einige Stunden nach dem Überflug bereit; um
07:00 UTC sind die Überflüge der Nacht und des Vortags da.

## 5. Grenzen

- **`data/harmonised/` liegt in Git** (Parquet-Dateien, `manifest.json`, `pipeline_state.json`, zusammen etwa
  27 MB). Jeder Lauf mit neuen Feuerdaten ändert diese Dateien. Auf dem Server ist das egal, solange dort niemand
  committet. Auf einem Arbeitsrechner erscheinen sie danach als geändert. Ob die Tabellen weiter versioniert werden
  oder wie `data/forecast/` in die `.gitignore` kommen, entscheidet das Team.
- **Neue Satelliten oder Produkte:** Sie müssen weiterhin in `harmonisation/pipeline_config.yaml` eingetragen werden
  (`harmonisation/docs/raw_sources.md`, „Neue Daten einspielen“). `fetch_firms.py` kennt die API-Namen der acht
  bisherigen Quellen (`API_SOURCE`).
- **Satellitenkennungen der API:** Am 15.11.2026 mit echtem Schlüssel geprüft. Meldet ein späterer Lauf
  `unknown satellite code`, gehört die neue Kennung in `SATELLITE`.
- **SNPP:** Die SNPP-NRT-Datei endet am 02.11.2026. Ob SNPP wieder Daten liefert, zeigt der erste Abruf. Die
  Harmonisierung erkennt Satelliten, die nicht in Betrieb sind, selbst (`day_status`).
- **Gebiet von MODIS/SNPP:** Zellen, in denen in 26 Jahren nie etwas erkannt wurde, bleiben ausgeschlossen. Das ist
  dieselbe Annahme wie in `common_area.py`.
