# Konzept: Interaktives Tutorial

Stand: 15.11.2026. Dieses Dokument beschreibt, wie das geführte Tutorial gebaut werden soll. Inhaltliche Grundlage sind
die Schritte in [tutorial.md](tutorial.md).

## 1. Was der Nutzer erlebt

- **Beim ersten Besuch** startet das Tutorial automatisch, sobald die Startseite geladen ist und die Karte steht.
- **Danach** startet es nur noch über den Knopf **Tutorial** oben rechts in der Startansicht, neben Sync, Sprache,
  Info und Accessibility.
- **Die ganze Seite ist abgedunkelt.** Nur das Element, über das das Tutorial gerade spricht, bleibt hell
  („Spotlight“) und ist blau umrandet.
- **Neben dem hellen Element steht ein Popup** mit Titel, kurzem Text, Fortschritt und drei Knöpfen:
  **Zurück**, **Weiter** und **Überspringen**.
- **Das Tutorial nutzt ein Testgebiet** (Galicia, 15.08.2025). Was in einem Schritt zu sehen sein soll, stellt das
  Tutorial selbst ein: Gebiet wählen, zoomen, Ansicht umschalten, Seite wechseln.
- **Am Ende oder nach „Überspringen“** kommt der Nutzer genau dorthin zurück, wo er vorher war (gleiche Adresse, gleiche
  Ansicht).

```
┌──────────────────────────────────────────────────────────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│░░┏━━━━━━━━━━━━━┓░░░░░┌────────────────────────────────────┐░░░░░░░░░░░░░░│
│░░┃ Settings    ┃◀────│ Stichtag und Methode         3 / 14│░░░░░░░░░░░░░░│
│░░┃ Reference   ┃░░░░░│                                    │░░░░░░░░░░░░░░│
│░░┃ date  [..]  ┃░░░░░│ Hier legst du fest, auf welchen    │░░░░░░░░░░░░░░│
│░░┃ Confidence  ┃░░░░░│ Tag sich alles bezieht. Wir haben  │░░░░░░░░░░░░░░│
│░░┃ Method      ┃░░░░░│ den 15.08.2025 eingestellt …       │░░░░░░░░░░░░░░│
│░░┗━━━━━━━━━━━━━┛░░░░░│                                    │░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░░░░░░░░│ ● ● ◉ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○        │░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░░░░░░░░│ Überspringen       [Zurück][Weiter]│░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░░░░░░░░└────────────────────────────────────┘░░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
└──────────────────────────────────────────────────────────────────────────┘
 ░ = abgedunkelt   ┏┓ = heller Ausschnitt mit blauem Rahmen   ◀ = Pfeil zum Element
```

Erster und letzter Schritt haben kein Element. Ihr Popup steht in der Bildschirmmitte über der ganz abgedunkelten
Seite:

- **Schritt 1:** „Willkommen bei La Brasa. In 2 Minuten zeigen wir dir die wichtigsten Funktionen an einem Beispiel.“
  Knöpfe: **Los geht's** und **Überspringen**.
- **Letzter Schritt:** „Fertig! Du kannst das Tutorial jederzeit oben rechts über *Tutorial* wieder öffnen.“
  Knöpfe: **Zurück** und **Fertig**.

## 2. Bedienung

| Aktion | Maus | Tastatur |
|---|---|---|
| Weiter | **Weiter** | → oder Enter |
| Zurück | **Zurück** (im ersten Schritt ausgeblendet) | ← |
| Überspringen | **Überspringen** oder ✕ oben im Popup | Esc |
| Fertig | **Fertig** im letzten Schritt | Enter |

- **Klicks auf die abgedunkelte Fläche** bewirken nichts. Sie beenden das Tutorial nicht, damit niemand es aus
  Versehen verliert.
- **Das helle Element ist nicht bedienbar.** Das Tutorial führt die Aktionen selbst aus. So kann der Nutzer nichts in
  einen Zustand bringen, den der nächste Schritt nicht erwartet. Ein späterer Ausbau mit „Probier es selbst“-Schritten
  ist möglich (siehe Abschnitt 8).
- **„Überspringen“ fragt nicht nach.** Wer es abbricht, findet es oben rechts wieder. Der letzte Schritt nennt den Ort.
- **Esc ist während des Tutorials reserviert.** Der Exit-Knopf und das Zeichenwerkzeug reagieren dann nicht darauf.

## 3. Die Schritte

Die 18 Schritte aus `tutorial.md` werden zu **16 Popups** zusammengefasst. Jeder Schritt legt fest:

- welches Element hell ist (das *Ziel*),
- welchen App-Zustand er braucht,
- was im Popup steht.

| # | Seite | Ziel (hell) | Zustand, den der Schritt herstellt | Inhalt des Popups |
|---|---|---|---|---|
| 1 | Start | keins (Mitte) | ganz Spanien und Portugal, letzter Tag | Willkommen, Dauer, was gezeigt wird |
| 2 | Start | Karte + Legende | wie 1 | Sechsecke = Hotspots der letzten 30 Tage, Farbe = Menge |
| 3 | Start | Info-Boxen | wie 1, Info-Boxen sichtbar | Die drei Kennzahlen und ihr Vergleich |
| 4 | Start | Kachel *Settings* | Stichtag 15.08.2025 | Stichtag, *Latest*, Confidence, Methode |
| 5 | Start | Kachel *Area* | Region Galicia | Suche, Baum, Pfad; Klick in die Karte geht auch |
| 6 | Start | *Selected area* + *Exit Galicia* | wie 5 | Zurück zum Land, Auswahl aufheben, Esc |
| 7 | Start | Karte (Ausschnitt Ourense) | Galicia bleibt gewählt, Karte zoomt auf einen festen Ausschnitt um Ourense (Stufe ≥ 11) | Einzelne Hotspots, Farbe = Alter, Klick öffnet Details; Map/Satellite |
| 8 | Start | Kachel *Calendar* | wie 5 | Jahre × Monate, Klick setzt den Stichtag |
| 9 | Start | Leiste *Select area* | wie 5 | Rechteck, Kreis, Polygon, Freihand; Umriss nur in diesem Tab |
| 10 | Start | Umschalter *Data view* + Vergleichskarten | `display=compare` | Harmonisiert und roh, gleiche Farbskala |
| 11 | Start | Knopf *Analysis* | `display=harmonised` | „Hier geht es zur Auswertung“ |
| 12 | Auswertung | Blöcke seit Jahresbeginn | `page=analysis`, Galicia, 15.08.2025 | Vergleich mit Vorjahr und Rekord |
| 13 | Auswertung | Kachel *Short-term analysis* | wie 12 | Die vier Karten in einem Satz je Karte |
| 14 | Auswertung | Karte + Feuerliste | stärkstes Feuer ausgewählt (`event=…`) | Look-back, Events/Zellen, Liste, Sortierung, *Unusual* |
| 15 | Auswertung | Zeitregler | wie 14, `event` entfernt | ±60 Tage, alles folgt dem Regler |
| 16 | Auswertung | Saisonkurve + Jahresübersicht, dann Mitte | wie 15 | Vergleichsjahre, Heatmap/Ring, Klick setzt Stichtag; danach „Fertig“ |

### Echte Daten

Das Tutorial zeigt **die echten Daten aus dem Backend** (`VITE_API_MODE=live`), nicht die Mock-Daten. Daraus folgt:

- **Testgebiet:** Galicia ist im Backend die NUTS-2-Region **`ES11`**. Die ID steht fest in `lib/tourSteps.ts`. Zur
  Sicherheit prüft das Tutorial beim Start, ob `ES11` in `/api/regions` vorkommt. Fehlt sie, sucht es nach dem Namen
  „Galicia“.
- **Provinzen gibt es im Backend nicht.** Für den Zoom in Schritt 7 nutzt das Tutorial deshalb einen festen Ausschnitt
  um Ourense. Die Koordinaten stehen im Schritt, z. B. `[-8.2, 42.0, -6.9, 42.6]`. Ein Gebiet wird dafür nicht gewählt.
- **Stichtag 15.08.2025:** Das Datum liegt im Archiv. Im August 2025 gab es in Ourense große Brände, deshalb sind dort
  Hotspots, Ereignisse und ein deutliches „mehr als üblich“ zu sehen. **Vor der Umsetzung prüfe ich das einmal mit
  den echten Daten**, auch die Hotspots ab Zoomstufe 11 im gewählten Ausschnitt. Liegt das Datum außerhalb der Daten,
  wird es auf den gültigen Bereich begrenzt (`clampDate`).
- **Keine festen Zahlen in den Texten.** Nach jedem Sync oder neuen Archiv ändern sich die Werte. Die Popups sagen
  deshalb „Hier siehst du …“ und nennen keine Zahl. Die Zahlen stehen in der App selbst, unter dem Spotlight.
- **Ereignisse** berechnet das Backend beim Start (einige Sekunden, „Event index …“). Schritt 14 wartet auf die
  Ereignisliste und zeigt solange den Ladezustand der Kachel. Kommt keine Antwort, nennt das Popup kein Feuer und
  die Liste bleibt sichtbar.
- **Mock-Modus:** Läuft die App ohne Backend (Hinweis „Mock data“ oben rechts), startet das Tutorial **nicht
  automatisch** und der Knopf *Tutorial* ist ausgeblendet. Andere IDs und erfundene Zahlen würden nicht zu den Texten
  passen. Für die Entwicklung lässt es sich mit `?tour=1` trotzdem öffnen.
- **Ladezeiten:** Echte Abfragen dauern länger als der Mock. Jeder Schritt stellt zuerst den Zustand her, dann erscheint
  das Popup. Der Ausschnitt passt sich an, sobald die Kachel ihre Daten hat (siehe „Daten laden noch“ in Abschnitt 4).

## 4. Technischer Aufbau

**Ohne neue Bibliothek.** Fertige Tour-Bibliotheken (z. B. Shepherd, driver.js) kennen weder den URL-Zustand noch die
MapLibre-Karte noch die Themes. Die nötigen Bausteine gibt es schon im Code:

- `Tip` berechnet Positionen, die im Viewport bleiben,
- `useAppState` setzt den Zustand,
- `usePrefs` liefert das Motion-Setting.

Das entspricht `frontend/AGENTS.md` („keine Bibliotheken, die die App noch nicht braucht“).

### Neue Dateien

| Datei | Inhalt |
|---|---|
| `lib/tourSteps.ts` | Liste der Schritte als Daten: `id`, `target`, `page`, `state`, `placement`, `before?` |
| `hooks/useTour.tsx` | Kontext: läuft das Tutorial, aktueller Schritt, `next`, `back`, `skip`, `start`; merkt sich den Zustand vor dem Start |
| `components/tour/TourOverlay.tsx` | Abdunklung, heller Ausschnitt, Popup, Tastatur und Fokus |
| `i18n/messages/*.ts` | neue Schlüssel `tour.*` (Titel und Text je Schritt, Knöpfe) in EN, ES, PT |
| `styles/design.css` | Klassen `ow-tour*`, Farben als Tokens je Theme |

### Ziele markieren

Die Elemente bekommen ein Attribut, z. B. `<aside data-tour="settings">`. Der Schritt nennt nur `target: "settings"`.
CSS-Klassen werden nicht angefasst, Umbauen im Design bricht das Tutorial nicht. Betroffen sind:

- `StartPage`: Karte, Info-Boxen, Kacheln, Zeichenleiste, Datenansicht, Auswahl, Knopf *Analysis*
- `AnalysisPage`: Blöcke, Kacheln, Zeitregler
- `Header`: neuer Knopf *Tutorial*

### Zustand pro Schritt statt Schrittfolge

Jeder Schritt beschreibt den **vollständigen** Zustand, den er braucht, z. B.
`{ page: "select", region: GALICIA, date: "2025-08-15", display: "harmonised" }`, und setzt ihn mit
`setState(..., { replace })`. Er baut nicht auf dem vorherigen Schritt auf. Daraus folgt:

- **Zurück** ist trivial und immer korrekt: Es setzt einfach den Zustand des vorherigen Schritts.
- Jeder Schritt lässt sich zum Testen direkt anspringen.
- Die Browser-Historie bekommt keine 16 Einträge, weil alles mit `replaceState` läuft.

Dinge, die nicht in der URL stehen, erledigt ein optionales `before(ctx)` im Schritt:

| Was | Wie |
|---|---|
| Zoom der Karte (Schritt 7) | Über das vorhandene `fitTo` mit der Bounding Box von Ourense |
| Aufgeklappte Kachel | `Tile` bekommt ein optionales `forceOpen`, das der Tour-Kontext für die Ziel-Kachel setzt; danach gilt wieder der Zustand des Nutzers |
| Info-Boxen sichtbar | `useIdleReveal` bekommt ein `forceVisible` |
| Stärkstes Feuer (Schritt 14) | Der Schritt wartet auf die Ereignisliste und setzt dann `event` auf das erste Ergebnis |

### Abdunklung und heller Ausschnitt

- **Eine Ebene** mit `position: fixed` über der ganzen Seite, darin ein SVG mit einer `mask`: ein Rechteck in voller
  Größe, das Loch als abgerundetes Rechteck mit 8 px Rand um das Ziel. Füllung je Theme halbtransparent
  (`--ow-tour-dim`, z. B. `rgba(5, 8, 15, 0.65)`). Im High-Contrast-Theme ist sie deckend schwarz, mit gelbem Rahmen.
- **Position des Ausschnitts:** `getBoundingClientRect()` des Ziels. Neu berechnet wird
  - bei `resize`,
  - bei `scroll` (Auswertungsseite),
  - über einen `ResizeObserver` am Ziel (Kacheln laden nach und wachsen),
  - gebündelt in `requestAnimationFrame`.
- **Ist das Ziel außerhalb des Bildschirms,** scrollt es vorher mit `scrollIntoView({ block: "center" })` ins Bild.
- **Klicks:** Die Ebene fängt alle Klicks ab, auch über dem Loch (`pointer-events: auto`). Siehe Abschnitt 2.
- **Wechsel zwischen Schritten:** Der Ausschnitt gleitet in 200 ms zur neuen Stelle. Bei *Reduce motion* (oder der
  entsprechenden Systemeinstellung) springt er ohne Animation (`motionOff` aus `usePrefs`).

### Popup

- **Position:** Es sitzt neben dem Ziel, auf der Seite mit dem meisten Platz (`placement: "auto"`, oder fest je
  Schritt). Es bleibt mindestens 8 px im Viewport und klappt um, wenn kein Platz ist, nach derselben Logik wie `Tip`.
  Ein kleiner Pfeil zeigt auf das Ziel.
- **Inhalt:**
  - Titel, Text (2–4 Sätze) und „3 / 16“,
  - Fortschrittspunkte, nur zur Anzeige,
  - links **Überspringen**, rechts **Zurück** und **Weiter**,
  - ✕ oben rechts.
- **Schmale Bildschirme** (unter 640 px): Das Popup wird zur Leiste am unteren Rand, der Ausschnitt bleibt.
- **Daten laden noch:** Das Popup erscheint trotzdem sofort. Der Ausschnitt wächst mit, sobald das Element da ist.
  Fehlt das Ziel nach 3 Sekunden ganz (z. B. weil eine Funktion im Backend aus ist), steht das Popup in der Mitte und
  der Text bleibt gleich.

### Barrierefreiheit

- Das Popup ist `role="dialog"` mit `aria-modal="true"`, `aria-labelledby` (Titel) und `aria-describedby` (Text).
- Beim Öffnen und bei jedem Schritt geht der Fokus auf **Weiter**. Tab bleibt innerhalb des Popups (Fokusfalle).
- Der Rest der Seite bekommt solange `inert`, damit Screenreader und Tab nicht hineinlaufen.
- „Schritt 3 von 16“ steht als Text im Popup, nicht nur als Punkte.
- Textgröße und Theme aus *Accessibility* gelten auch für das Popup.

## 5. Erster Besuch und Zurücksetzen

- **Merken:** In `localStorage` unter `la-brasa:tour` steht `{ "version": 1, "status": "done" | "skipped" }`, mit
  try/catch wie bei `usePrefs`. Ist der Speicher blockiert, startet das Tutorial bei jedem Besuch. Das ist besser, als
  es nie zu zeigen.
- **Automatisch** startet es nur, wenn
  1. noch kein Eintrag existiert,
  2. die Startseite offen ist,
  3. die Adresse **keine Parameter** hat.

  Wer einen geteilten Link öffnet (z. B. `?page=analysis&region=ES11`), soll erst sehen, was ihm geschickt wurde, und
  nicht in ein Tutorial mit anderem Gebiet geworfen werden.
- **Version:** Ändert sich das Tutorial stark, wird `version` erhöht und alle sehen es einmal neu.
- **Vorherigen Zustand wiederherstellen:** Beim Start merkt sich `useTour` die aktuelle Adresse (`location.search`).
  Bei *Fertig* und *Überspringen* setzt es sie zurück (`replaceState`) und zoomt die Karte wieder auf das vorige
  Gebiet.

  Danach gibt es drei Möglichkeiten:
  - **(a)** Der Nutzer landet wieder auf seinem Ausgangszustand. Das ist mein Vorschlag.
  - **(b)** Er bleibt mit Galicia auf der Auswertungsseite.
  - **(c)** Er landet auf der Startseite mit Galicia.

## 6. Tests

| Was | Wie |
|---|---|
| Schrittliste | Unit-Test in `lib/`: Jede `id` ist eindeutig, jeder Schritt hat Texte in EN/ES/PT. Der Typecheck prüft das ohnehin über `en.ts` |
| Ablauf | Test für `useTour`: Weiter, Zurück und Überspringen setzen den richtigen Zustand, *Überspringen* stellt die alte URL wieder her, `localStorage` wird geschrieben |
| Erster Besuch | Startet bei leerem Speicher ohne URL-Parameter, startet nicht mit Parametern und nicht nach `done` |
| Mock-Modus | Kein automatischer Start, kein Knopf; `?tour=1` öffnet es trotzdem |
| Von Hand | Mit dem echten Backend und vollständig geladener Datenbank, alle drei Themes, Textgröße A++, Reduce motion, 375 px Breite, nur Tastatur, Screenreader (NVDA oder VoiceOver) |

## 7. Umfang und Reihenfolge

1. **Grundgerüst:** `useTour`, Overlay mit Ausschnitt, Popup, Tastatur, `localStorage`, Knopf *Tutorial*. Dazu die
   Schritte 1–6 (Startseite ohne Zoom).
2. **Restliche Startseite:** Schritte 7–11 mit Karten-Zoom, `forceOpen` und Vergleichsansicht.
3. **Auswertungsseite:** Schritte 12–16 mit Seitenwechsel, Scrollen und ausgewähltem Feuer.
4. **Übersetzung** ES/PT, Tests, Prüfung von Hand.

Geschätzt etwa 600–800 Zeilen. Am bestehenden Code ändert sich nur wenig: `data-tour`-Attribute, `forceOpen` in `Tile`,
`forceVisible` in `useIdleReveal`, der Knopf im Header und Esc in `ExitButton` und `useDrawTool`.

## 8. Bewusst nicht im ersten Schritt

- **„Probier es selbst“-Schritte**, bei denen der Nutzer z. B. selbst auf Galicia klicken muss, bevor *Weiter* geht.
  Die Schrittliste ist darauf vorbereitet (`waitFor` statt `state`), aber solche Schritte machen das Tutorial
  anfälliger.
- **Ein Tutorial-Knopf auf der Auswertungsseite.** Laut Auftrag gibt es ihn nur in der Startansicht. Er wäre leicht
  ergänzt und könnte dann direkt bei Schritt 12 beginnen.
- **Eine deutsche Oberfläche.** Die App hat EN, ES und PT. Die Popup-Texte folgen der gewählten Sprache.

## 9. Offene Fragen

1. Wohin nach *Fertig* oder *Überspringen*? Vorschlag (a) aus Abschnitt 5: zurück zum Ausgangszustand.
2. Bleibt es bei Galicia (`ES11`), 15.08.2025 und dem Zoom auf Ourense als Testgebiet? Mit den echten Daten prüfe ich
   vor der Umsetzung, ob dort genug zu sehen ist.
3. Soll das helle Element anklickbar sein, oder führt das Tutorial alle Aktionen selbst aus (Vorschlag)?
4. Reichen 16 Schritte, oder soll es eine kurze Fassung geben (nur Startseite, etwa 8 Schritte) und die Auswertung als
   eigenes Tutorial?
