# La Brasa lokal starten (Website + API + Datenbank)

Voraussetzungen: Docker, Python 3, Node.js 22 (z. B. `nvm install 22 && nvm use`, siehe `frontend/.nvmrc`), Git.

## 1. Stand holen

```bash
git fetch
git switch app
git pull
```

Auf `app` liegt der Integrationsstand mit `backend/` und `frontend/`.

## 2. Datenbank und API starten

```bash
cp .env.example .env              # nur beim ersten Mal, .env nie committen
docker compose up -d --build db backend
docker compose ps                 # db "healthy", backend "Up"
```

## 3. Daten in die Datenbank laden

Nur beim ersten Mal oder wenn sich die Parquet-Dateien in `data/harmonised/` geändert haben.

```bash
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r pipeline/requirements.txt
python pipeline/load_to_db.py
```

Kontrolle:

```bash
curl http://localhost:8000/api/meta
```

Das muss JSON mit `first_date` und `last_date` liefern.

Bestehende Datenbank, die älter ist als die Tabelle für gezeichnete Gebiete: einmal ausführen (legt nur die Tabelle `areas` an, Daten bleiben):

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/002_areas.sql'
```

Hat sich das Datenbankschema geändert (`db/init/001_schema.sql`), läuft es nur auf einem leeren Volume. Dann einmal:

```bash
docker compose down -v            # löscht die lokale Datenbank, keine Dateien
docker compose up -d --build db backend
python pipeline/load_to_db.py
```

## 4. Website im Live-Modus starten

```bash
cd frontend
npm install
printf 'VITE_API_MODE=live\n' > .env.local
npm run dev
```

Die Adresse steht im Terminal, meist `http://localhost:5173`. Das Terminal muss offen bleiben.

- Ohne `VITE_API_MODE=live` läuft der Mock mit erfundenen Daten.
- `.env.local` nicht committen (in `.gitignore` eintragen).
- Der Vite-Proxy leitet `/api` an `localhost:8000` weiter, CORS ist im Dev-Betrieb nicht nötig.
- Die Ereignisse berechnet das Backend beim Start (einige Sekunden, siehe `docker compose logs backend`: „Event index …“). Bis dahin warten die ersten Ereignis-Anfragen.

## Nützliche Adressen und Befehle

| Was | Wie |
|---|---|
| API-Dokumentation | `http://localhost:8000/docs` |
| Backend-Logs | `docker compose logs --tail 30 backend` |
| Backend-Tests | `cd backend && pip install -r requirements-dev.txt && DATABASE_URL=postgresql://USER:PASS@localhost:5432/DB pytest tests -q` (lesen `data/harmonised/*.parquet`) |
| Frontend prüfen | `cd frontend && npm run lint && npm test && npm run build` (Node 22) |
| Alles stoppen | `docker compose down` (Daten bleiben), Vite mit `Strg+C` |

## Was sich gegenüber dem Mock unterscheidet

- Die API kennt **NUTS-2-Regionen** (`ES11`, `PT16`), keine Provinzen. Das Frontend nimmt automatisch die feinste vorhandene Ebene für Kartengrenzen und „Gebiete, in denen es oft brennt“.
- Die **Balearen** sind nicht in den Daten. Die Gebietsangabe lautet deshalb „Festland“.
- **Ereignisse** bündeln Hotspots, deren H3-Zellen (Auflösung 8) gleich oder benachbart sind und höchstens 2 Tage auseinanderliegen. Am Stichtag D zählen nur Punkte bis D. Wachsen zwei Brände später zusammen, verschwindet die ID des jüngeren danach (`EVENT_NOT_FOUND`), das Frontend lädt die Liste neu.
- **Nur Regionen, keine Provinzen:** Ereignisse heißen „Feuer in Galicia“ statt „Feuer bei Ourense“, und `/api/by-region` kennt nur `level: "region"`.
- `last_date` ist der letzte Tag mit Daten und kann ein unvollständiger Tag sein. Das Harmonisierungsteam klärt das noch.
- `fires` ist die Hauptzahl. Ein Feuer kann seit 2018 bis zu dreimal als Hotspot erscheinen (Gewicht 0,333), `hotspots` ist deshalb größer als `fires`.

## Häufige Fehler

| Meldung | Ursache und Lösung |
|---|---|
| Seite lädt nicht | Vite läuft nicht: im Ordner `frontend` `npm run dev` starten und die angezeigte Adresse nutzen |
| `vite: not found` | `npm install` im Ordner `frontend` |
| `EADDRINUSE` | Port belegt, alten Vite-Prozess beenden oder die neue Adresse nutzen |
| Seite zeigt Daten, im Netzwerk-Reiter aber keine `/api`-Aufrufe | `.env.local` fehlt oder enthält nicht `VITE_API_MODE=live`, danach Vite neu starten |
| `INTERNAL_ERROR` von der API | Datenbank leer oder altes Schema: Schritt 3 mit `down -v` wiederholen |
| `ModuleNotFoundError: pandas` | venv nicht aktiv: `source .venv/bin/activate` und `pip install -r pipeline/requirements.txt` |
| `501 NOT_IMPLEMENTED` | Funktion existiert in der API noch nicht (derzeit nur `grid` mit `group_by: "day"` und `by-region` mit Provinzen), kein Fehler im Setup |
| Gezeichnetes Gebiet zeigt „Umriss nicht mehr verfügbar“ | Link mit `area=` in einem anderen Browser geöffnet: Den Umriss kennt nur der Browser, der ihn gezeichnet hat. Gebiet neu zeichnen |