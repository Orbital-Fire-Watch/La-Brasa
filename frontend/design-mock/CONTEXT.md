# CONTEXT: Design-Mock „La Brasa“

Übergabe-Dokument für alle, die am Mock weiterarbeiten (Team und KI-Assistenzen): was gebaut wurde, warum,
wie es zusammenhängt und was offen ist. Stand: 14.11.2026.

## 1. Worum es geht

`frontend/design-mock/` ist ein **eigenständiger Design-Mock** des neuen Frontends nach der Spezifikation
„Änderungsprotokoll“ (PDF mit Logo) und vier Folgerunden. Er nutzt **denselben Datensatz** wie die App
(`services/api/fireApi.ts`: Mock-API im Browser oder echtes Backend), ändert aber **keine einzige bestehende Datei**
außerhalb dieses Ordners. Die App unter `/` läuft unverändert weiter, so lassen sich beide direkt vergleichen.

```bash
cd frontend && npm install && npm run dev
# http://localhost:5173/design-mock/                      Startseite
# http://localhost:5173/design-mock/?page=analysis        Auswertung
# http://localhost:5173/design-mock/?display=compare      MODIS/VIIRS-Vergleich
# http://localhost:5173/design-mock/info.html             Infoseite
```

Prüfen: `npx tsc -p design-mock/tsconfig.json` (nur Mock, inkl. Vollständigkeit der Übersetzungen),
`npx eslint design-mock` (läuft auch in `npm run lint`), `npm test` (App-Tests, unverändert grün).
`npm run build` baut den Mock **nicht** mit; er ist nur für den Dev-Server gedacht.

## 2. Verlauf: Prompts und was daraus wurde

Jede Runde hat einen eigenen Prompt mit messbaren KPIs. Die Prompts sind die Quelle der Anforderungen.

| Prompt | Inhalt | Wichtigste Ergebnisse |
|---|---|---|
| [PROMPT.md](PROMPT.md) | Spezifikation 1: Vollbild-Karte, Kacheln, Logo-Farben, Info-Boxen, Auswertung im EFFIS-Stil | Fullscreen-Karte, einklappbare Metall-Kacheln, Info-Boxen (2 s Verzögerung, verschwinden beim Bewegen), „Map/Satellite“ über +/−, kleinere H3-Zellen, Tooltips im Viewport, A11y-Menü, Infoseite, Header-Blöcke „seit Jahresbeginn“ |
| [PROMPT-2.md](PROMPT-2.md) | Zurück zum ganzen Land, weniger KI-Look, EN/ES/PT, Logo „La Brasa“ | Pfad-Anzeige + „Show all of Spain“, ruhigeres Design (keine Glows/Versalien/Effekt-Animationen), i18n mit `Intl`, neues SVG-Logo mit „AI GENERATED“ |
| [PROMPT-3.md](PROMPT-3.md) | Sync, Exit aus der Region, MODIS/VIIRS-Rohdaten mit Vergleichsansicht | Sync-Button mit DTO, Exit-Button (Esc), Umschalter Harmonised/MODIS/VIIRS/Compare, zwei synchrone Karten mit gemeinsamer Skala, Kachel „MODIS vs VIIRS“ |
| [PROMPT-4.md](PROMPT-4.md) | MODIS/VIIRS-Vergleich auch in der Jahresübersicht | Roh-Heatmaps je Familie mit gemeinsamer Skala, Jahressummen, zweiter DTO `/api/daily/sensors` mit Ersatzweg |

## 3. Aufbau

```
design-mock/
  index.html, info.html        Einstieg des Mocks; schlichte Infoseite (EN/ES/PT, folgt der gewählten Sprache)
  tsconfig.json                erweitert ../tsconfig.json, prüft nur src/
  assets/la-brasa-logo.svg     Logo: KI-generierter Globus aus der Spezifikation + SVG-Ring „LA BRASA“ / „AI GENERATED“
  src/
    main.tsx, MockApp.tsx      Start, lädt meta/regions, Splash, Seitenwahl, Sync-Steuerung
    config.ts                  Logo-Pfad (VITE_LOGO_URL), Verzögerungen, H3-Feinheit (zoom − 1, 4–8)
    mockState.ts               URL-Zustand wie hooks/useAppState, aber ?page= und ?display= (bleibt unter /design-mock/)
    prefs.tsx                  Theme, Datenpalette, Textgröße, Bewegung, Sprache (localStorage, data-* auf <html>)
    i18n/                      t() + Intl-Formatierer; messages/en.ts ist die Referenz, es.ts/pt.ts typgeprüft vollständig
    selection.ts               englische/übersetzte Bezeichnung der Auswahl, Pfad zum Land
    palette.ts                 Standard-Farben oder farbenblind-taugliches Cividis/Viridis
    mapFeatures.ts             GeoJSON mit übersetzten Popups (Zellen, Alter, Anomalie, Hotspots, Rohzellen)
    sensors.ts                 MODIS/VIIRS: Familie, Farben (Okabe-Ito), Zusammenfassen von /api/hotspots
    ytd.ts                     Werte seit Jahresbeginn, Vorjahr, Rekordjahr (Header-Blöcke)
    hooks.ts                   Info-Boxen ein-/ausblenden
    sync.tsx                   Zustand des Sync-Buttons, „effektive“ data_version
    api/sync.ts                DTO + Client für POST /api/sync           (Anknüpfungspunkt Backend)
    api/sensorDaily.ts         DTO + Client für POST /api/daily/sensors  (Anknüpfungspunkt Backend) + Ersatzweg + Cache-Hook
    components/                OrbitalMap, Header, ui (Tile, Tip, Status, Flag), StartTiles, MonthGrid, MapTools,
                               SensorCompare, YearCompare, AnalysisParts
    pages/                     StartPage, AnalysisPage
    mock.css                   einziges Stylesheet, alle Farben als Tokens je Theme
```

**Wiederverwendet (nur importiert, nie verändert):** `fireApi`, `useApiQuery`, `useSelection`, `useDrawTool`,
`useGeoJsonData`, `useBasemap`, `components/ui/Segmented`, die Berechnungen in `lib/` und die Diagramme
`SeasonChart`, `YearHeatmap`, `RingCalendar`.

## 4. Wichtige Entscheidungen

- **Kein Eingriff in bestehenden Code.** Wo bestehende Module deutsche Texte oder anderes Verhalten haben, gibt es eine
  eigene Variante im Mock (z. B. Karte, Tooltip, Formatierer, URL-Zustand).
- **Neu laden über die `data_version`.** Jeder Abfrage-Schlüssel enthält sie. Der Sync setzt eine neue
  (im Mock `…+syncN`, ohne Backend-Endpunkt `…#rN`), dadurch lädt alles neu, ohne dass die Karte neu aufgebaut wird.
- **Vergleichskarten:** Die MODIS-Karte führt (sie zoomt auch auf das Gebiet), die VIIRS-Karte folgt per `jumpTo`.
  Nutzerbewegungen auf der VIIRS-Karte werden zurückgegeben. Weil `jumpTo` kein `originalEvent` hat, gibt es keine Schleife.
- **Gemeinsame Farbskala** in jeder Vergleichsansicht, damit gleiche Farbe gleiche Zahl bedeutet.
- **Rohdaten aus `/api/hotspots`:** Die API hat keinen Sensor-Filter. Gekürzte Antworten (`truncated`) werden
  immer sichtbar gemacht; die Jahresübersicht teilt gekürzte Jahre in Monate auf und schraffiert, was trotzdem gekürzt ist.
- **Sprachen über `Intl`:** Zahlen, Daten, Monatsnamen, Ländernamen, „gestern/vor 3 Tagen“ und Plural kommen vom
  Browser. Eine weitere Sprache = eine Datei in `i18n/messages/` + eine Zeile in `i18n/locales.ts`.
- **Design-Regeln (Prompt 2):** zwei Akzentfarben (Blau = Auswahl, Orange = Hauptaktion/Feuer), Radien 2–4 px,
  keine Schatten auf Kacheln, kein Blur/Glow/Verlaufsschrift, keine Versalien, Animation nur für Info-Boxen und Spinner.
- **React Compiler (Lint):** In `AnalysisPage` werden Datums-Labels und die Export-Abfrage **vor** den `useMemo`s
  berechnet. Sonst meldet `react-hooks/preserve-manual-memoization` Fehler (siehe Kommentar dort).

## 5. Anknüpfungspunkte für das Backend

| Endpunkt | Datei | Zweck | Verhalten ohne Endpunkt |
|---|---|---|---|
| `POST /api/sync`, `GET /api/sync/{job_id}` | `src/api/sync.ts` | neuen FIRMS-Import auslösen, danach neue `data_version` | Daten werden trotzdem neu angefragt, Hinweis im Tooltip |
| `POST /api/daily/sensors` | `src/api/sensorDaily.ts` | Rohdetektionen und FRP pro Tag und Sensorfamilie (wie `/api/daily`) | Ersatz über `/api/hotspots` (pro Jahr, gekürzt → pro Monat), Kürzungen schraffiert |

Beide Dateien beschreiben jedes Feld mit Bedeutung und Beispiel. Nach Umsetzung im Backend: OpenAPI ergänzen,
`npm run gen:types`, die handgeschriebenen Typen durch die generierten ersetzen. Optional: ein `sensor`-Filter in
`/api/grid` und `/api/daily` würde auch die 30-Tage-Vergleiche vollständig machen.

## 6. Geprüft

- Typecheck, Lint und die 30 App-Tests ohne Fehler; `git status` zeigt nur `frontend/design-mock/`.
- In Firefox (headless) mit den Mock-Daten durchgeklickt: Startseite und Auswertung in EN/ES/PT; Pfad-Anzeige und
  „Show all of Spain“; Exit zoomt heraus (Maßstab 50 → 100 km); Sync läuft durch, Karte bleibt; Vergleichskarten
  zoomen gemeinsam; Jahresübersicht: Galicia ca. 5 s / 39 Anfragen, Spanien + Portugal ca. 14 s / 206 Anfragen,
  Kürzungen markiert; Umschalten der Ansichten ohne neue Anfragen.

## 7. Bekannte Grenzen und offene Punkte

- Die wiederverwendeten Diagramme (`SeasonChart`, `YearHeatmap`, `RingCalendar`) zeigen intern weiter **deutsche** Texte.
  Englisch/Spanisch/Portugiesisch nur durch Änderung dieser Komponenten in der App.
- Regionsnamen kommen aus der API (amtliche Namen) und werden nicht übersetzt; die Hintergrundkarte folgt nicht der Sprache.
- Der Koordinaten-Dialog der App fehlt im Mock. Der Ringkalender gibt es nur für harmonisierte Daten.
- Die Rohdaten-Heatmaps sind per Maus bedienbar, aber nicht per Pfeiltasten (anders als die harmonisierte Heatmap).
- `README.md` beschreibt nur den Stand nach Prompt 2 (laut Auftrag wurden bestehende Dokumente danach nicht mehr
  geändert). Aktuell ist dieses Dokument.
- **Nächster Schritt bei Übernahme in die App:** Komponenten aus `design-mock/src` nach `components/`, `hooks/`, `lib/`
  verschieben, `i18n` als App-weites Modul einführen, `styles/tokens.css` durch die Tokens aus `mock.css` ersetzen.
