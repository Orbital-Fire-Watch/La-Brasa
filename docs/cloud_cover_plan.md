# Plan: Bewölkung anzeigen

| | |
|---|---|
| Branch | `cloud-error` |
| Stand | 15.11.2026 |
| Ziel | Für jeden Tag und jede Auswahl (Region oder gezeichnete Fläche) anzeigen, ob es zur Überflugzeit bewölkt war. |

## Warum

FIRMS listet nur Erkennungen. Liegt ein Feuer unter Wolken, fehlt es in den Daten, und der Tag erscheint als „0 Feuer“.
Unsere Voranalyse (0,25°-Zellen mit ≥ 100 MW am Vor- und Folgetag, VIIRS ab 2012): An 6,6 % der Tage dazwischen meldet
VIIRS nichts, im Juli/August 3–5 %, von Januar bis April 9–22 %. Die Challenge nennt Wolken ausdrücklich als offenes Problem.

## Grundsätze

- **Nur anzeigen.** Feuerzahlen (`n_harm`, `frp_harm`, Bänder, Events) bleiben unverändert. Keine Hochrechnung.
- **Bewölkung je 0,25°-Zelle × Tag.** `cell_id` steckt schon in jedem Hotspot, so passt die Bewölkung zu jeder Auswahl.
- **Zwei Werte je Tag:** `cloud_day` (≈ 13 UTC) und `cloud_night` (≈ 02 UTC), passend zu den VIIRS-Überflügen. Anteil 0–1.
- **Die Schwelle „bewölkt“ ist ein Parameter**, keine fest eingebaute Zahl. Daten und API liefern nur die Anteile.

## Umsetzung

| Teil | Datei | Was |
|---|---|---|
| Download | `pipeline/ingestion/fetch_clouds.py` | `effective_cloud_cover` von Meteomatics um 13:45 und 01:45 UTC für die 1.107 Zellen, die eine App-Region berühren. Monatsweise ab 20.01.2012, schreibt `data/raw/clouds/cloud_daily.parquet` (`cell_id, date, cloud_day, cloud_night`, Anteil 0–1). Holt die letzten 2 Tage neu (für die neuesten Tage kann Meteomatics eine Vorhersage geliefert haben). |
| Sync | `pipeline/sync_data.py` | Schritt 1 holt nach FIRMS auch die neuen Wolkentage. Scheitert das, wird nur gewarnt. |
| Datenbank | `db/init/003_clouds.sql`, `pipeline/load_to_db.py` | Tabelle `cloud_daily`. Voller Lauf: ersetzt alles. `--incremental`: ersetzt die letzten 2 Tage und neuere. Ohne Datei wird nichts geladen. |
| Backend | `backend/services/clouds.py`, `POST /api/daily` | `cloud_day`, `cloud_night` je Tag: Mittel über die Zellen, die die Auswahl berühren (Region, Land, gezeichnete Fläche, ganz Iberien). `null` = kein Wert. `POST /api/events`: für Feuer, die am Vortag zuletzt gesehen wurden, `cloud_day`/`cloud_night` an ihrem Ort (0,25°-Zelle des Mittelpunkts) und `seen_next_day` (Punkt am Folgetag in denselben oder direkt benachbarten H3-Zellen, wie die Ereignis-Regel). |
| Frontend | `lib/clouds.ts`, `lib/uiConfig.ts` (`CLOUDY_THRESHOLD = 0.5`) | Nur auf der Analyseseite. Unter dem Zeitschieberegler: Wolkenstreifen, ein Kästchen je Tag passend zu den Feuerbalken (schwach = klar, voll = Tag- und Nacht-Überflug je ≥ Schwelle, gelb gestrichelt = an diesem Tag mindestens ein Feuer vermutlich verdeckt, aus `POST /api/events/hidden`), und ein Hinweis zum gewählten Tag mit ⓘ-Erklärung. Auf der Karte: Feuer, die am Vortag und am Folgetag erkannt wurden, am Tag selbst nicht, und an ihrem Ort bewölkt waren, werden gelb gestrichelt gezeichnet („vermutlich unter Wolken verdeckt“, auch in Liste und Kartenlegende). Keine geschätzten Feuerzahlen. |

Bewusst ohne eigene Harmonisierungsstufe: Die Wolkendaten werden nicht umgerechnet, eine Stufe hätte nur kopiert.

Meteomatics-Account (Stand 15.11.2026): 1.000 Abrufe pro Tag, 250 pro Minute, historische Daten ab 1900.
**Läuft am 22.11.2026 ab.** Danach holt der Sync keine neuen Wolkentage mehr (nur eine Warnung im Log), die bereits
geladenen Tage bleiben.

## Nachweis: `harmonisation/data_analysis/10_clouds.py`
Einmalige Auswertung, `--threshold` als Parameter, Ergebnis in `results/clouds.json`.
- **C1:** Tage, an denen ein Großbrand am Vor- und Folgetag brennt und VIIRS dazwischen nichts meldet, sind deutlich öfter
  bewölkt als solche Tage mit Messung. Erwartung vorab: mindestens doppelt so oft.
- **C2:** Anteil bewölkter Region-Tage je Monat bei der gewählten Schwelle. Wird berichtet, nicht als fester Grenzwert geprüft.
- **C3:** Wie viele „0“-Tage als bewölkt markiert werden.

Die Zahlen dienen auch der Wahl der Schwelle und der Präsentation.

### Ergebnisse (15.11.2026, Wolkendaten 20.01.2012 bis 14.11.2026, VIIRS gemessen)

„Bewölkt“ = Tag- und Nacht-Überflug je ≥ Schwelle, gemittelt über die Region.

| | Schwelle 0,7 | Schwelle 0,5 |
|---|---|---|
| Tag zwischen zwei Feuertagen (Region): **klar → leer** | 22,9 % von 23.243 | 20,9 % |
| Tag zwischen zwei Feuertagen (Region): **bewölkt → leer** | **74,3 %** von 790 | 57,5 % |
| Leere Tage zwischen zwei Feuertagen, davon bewölkt (Region, 5.912 Fälle) | 9,9 % (Sommer 3 %, sonst 12–14 %) | 25,2 % |
| C1 Großbrand-Lücken (Zelle, ≥ 100 MW, 55 leere von 837): bewölkt leer / mit Meldung | 1,8 % / 0,8 % (× 2,4) | 9,1 % / 2,2 % (× 4,2) |
| C2 bewölkte Region-Tage, Jahresmittel (Juli/August, Januar) | 15 % (3 %, 25 %) | 30 % |
| C3 gemessene „0 Feuer“-Region-Tage, davon bewölkt (72.067 Fälle) | 22 % | 41 % |

Lesart: Wolken verstecken messbar Feuer (zwischen zwei Feuertagen bleibt ein bewölkter Tag dreimal so oft leer wie ein
klarer), vor allem außerhalb des Sommers. Sie erklären aber nur einen kleinen Teil der Lücken: Die meisten leeren Tage
zwischen Feuertagen sind klar. C1 ist formal erfüllt, stützt sich aber auf wenige Fälle (1 bzw. 5 bewölkte leere Tage).

Lücken aus den Nachbartagen schätzen (geprüft, nicht umgesetzt): bei Schwelle 0,7 kämen 566 Region-Tage in Frage,
zusammen +0,3 % Feuer (+0,9 % bei 0,5), typisch 1 Feuer je Tag. An klaren Tagen getestet liegt die Schätzung im Median
richtig, aber nur in 55 % der Fälle innerhalb von Faktor 2. Für Summen vernachlässigbar, für den einzelnen Tag zu ungenau.

## Bewusst nicht enthalten

Hochrechnung der Feuerzahlen, breitere Fehlerbänder an bewölkten Tagen, Änderung der Event-Logik, neue Spalten in
`activity_daily_harmonised`, Markierung in Kalender und Jahres-Heatmap (zeigen Wochen und Monate, keine Tage),
NASA-Wolkenmasken (VNP14A1 / MOD14A1).
