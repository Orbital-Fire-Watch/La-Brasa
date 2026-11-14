# VIIRS-Erweiterung: NOAA-20 und NOAA-21 (Schema-Version 2)

Stand: 14.11.2026. Ab dieser Version besteht die VIIRS-Referenz der Harmonisierung aus drei Satelliten: SNPP (ab 20.01.2012),
NOAA-20 (ab 01.04.2018) und NOAA-21 (ab 01.03.2023). Dateien, Zeilen und Format bleiben gleich. Die Ausnahmen stehen unten.
Alle 42 Prüfungen sind erfüllt, keine Schwelle wurde gesenkt. Ausführlich mit Zahlen und Diagrammen: [`viirs_extension.html`](viirs_extension.html).

## Was sich ändert und warum

| Entscheidung | Warum |
|---|---|
| **Mittel statt Summe:** Ein gemessener Tag ist das Mittel der an diesem Tag aktiven VIIRS-Satelliten (`n_viirs`, `frp_viirs`). Aktiv ohne Feuer zählt 0, nicht aktiv zählt nicht. | Die drei Satelliten sehen dasselbe Feuer etwa 50 Minuten versetzt. Das sind keine Doppelte desselben Pixels, sie lassen sich also nicht entdoppeln. Eine Summe würde die Reihe ab 2018 etwa verdoppeln. Das Mittel bleibt auf SNPP-Niveau (Median 1,006) und ist genauer: Gegen einen zurückgehaltenen Satelliten liegt der typische Tagesfehler bei × 2,0 für einen einzelnen und bei × 1,5 für das Mittel. |
| **Gewicht 1/k je VIIRS-Punkt** (k = aktive VIIRS-Satelliten, 1 bis 3) | So bleibt `SUM(weight_n)` über jede Fläche exakt gleich `n_viirs` bzw. `n_harm` (KPI D11, N2: Abweichung 4·10⁻¹⁶). |
| **Umbenennung** `n_snpp` → `n_viirs` usw. (Tabelle unten) | Die Referenz ist nicht mehr SNPP allein. `n_snpp` als Referenzname wäre irreführend. |
| **Rohzahlen je Satellit bleiben** (`n_snpp`, `n_noaa20`, `n_noaa21`, …) | Zum Nachrechnen und für den Tooltip „gemessen mit …“. |
| **Satellitenliste in der Config** (`satellites.viirs`, `satellites.column_key`) | Ein weiterer Satellit braucht keine Codeänderung, nur Config und Spaltenkatalog. |
| **Untersuchungsregionen** (`nuts.study_regions`): Alle Satelliten zählen nur in den 21 NUTS-2-Regionen der App (Festland-Spanien mit Balearen, Portugal). | Die NOAA-Downloads reichen weiter als MODIS/SNPP (bis 44,8° N, 4,9° O). Sonst zählte NOAA in Randregionen Feuer, die die anderen nicht sehen. Die französischen Randregionen wären bei MODIS/SNPP abgeschnitten. 88.155 Zeilen fallen heraus (`outside_study_regions`). |
| **Kalibrierung und Fehlermodell gegen SNPP allein** (`calibration.reference_satellites`) | Das Fehlermodell prüft Bänder auf 2012–2016 gegen 2017–2021. Mit dem ruhigeren Mittel ab 2018 hätten die Hälften verschieden viel Rauschen (U1b verfehlt). Der Faktor ändert sich dadurch kaum: Mit dem Mittel als Referenz wäre er +0,1 % größer. |
| **Ortsmaske je Sensor** (`static_sources.mask_training_sensors`): VIIRS-Maske nur aus VIIRS, MODIS-Maske aus allen | MODIS-Pixel (1 km) verschmieren den Ort einer Anlage. Mit gemeinsamer Maske verlor NOAA-20 2,2 % echte Feuer, jetzt 1,9 %. |
| **H3-Zelle je Hotspot** (`h3_cell`, Auflösung 8 ≈ 0,74 km², `grid.h3_resolution`) | Für Sechseck-Heatmaps und Nachbarschaftsabfragen. Gröbere Zellen ergeben sich mit `h3.cell_to_parent`. |
| **`schema_version: 2`** in Config und `manifest.json` | `pipeline/load_to_db.py` prüft die Version und meldet sich, wenn Daten und Datenbankschema nicht zusammenpassen. |

## Spalten: alt → neu

| Datei | alt | neu | Bedeutung |
|---|---|---|---|
| `activity_daily_harmonised` | `n_snpp` (Referenz) | `n_viirs` | Mittel der aktiven VIIRS-Satelliten, an gemessenen Tagen = `n_harm` |
| `activity_daily_harmonised` | `frp_snpp` (Referenz) | `frp_viirs` | wie `n_viirs`, für die FRP-Summe |
| `activity_daily_harmonised` | – | `n_snpp`, `n_noaa20`, `n_noaa21`, `frp_snpp`, `frp_noaa20`, `frp_noaa21` | Rohzahlen je Satellit (leer = nicht in Betrieb, 0 = kein Feuer) |
| `day_status` | `snpp_operating` (Referenz) | `viirs_operating` | mindestens ein VIIRS-Satellit liefert, der Tag ist gemessen |
| `day_status` | – | `snpp_operating`, `noaa20_operating`, `noaa21_operating` | Betrieb je Satellit |
| `hotspots_harmonised` | – | `h3_cell` | H3-Zelle der Pixelmitte |
| `hotspots_harmonised` | `satellite` ∈ {Terra, Aqua, SNPP} | zusätzlich `N20`, `N21` | neue Zeilen, `sensor` = VIIRS |
| `calib_factors` | `n_viirs_calib` | unverändert | Summe der Kalibrier-Referenz (SNPP) |

Unverändert bleiben `quality_by_scale`, `strength_confusion` und `big_fire_day_quality` (gleiche Spalten, gleiche Werte),
dazu alle übrigen Spalten. Die Zeilen sind weiterhin Region × Tag (217.304, jetzt bis 13.11.2026), Tag (9.448) und Erkennung (746.558).
Die Roll-up-Ergebnisse von `aggregation.roll_up_daily` enthalten dieselben neuen Rohspalten.

## Gewichte an einem Beispiel

Galicia (ES11) am 12.08.2025, alle drei Satelliten aktiv (k = 3):

| | SNPP | NOAA-20 | NOAA-21 | `n_viirs` = `n_harm` |
|---|---|---|---|---|
| Erkennungen | 206 | 185 | 199 | (206 + 185 + 199) / 3 = **196,67** |
| FRP-Summe (MW) | 4.787,6 | 2.591,2 | 4.066,8 | **3.815,2** |

Jeder dieser 590 VIIRS-Punkte hat `weight_n` = 1/3. Ihre Summe ergibt 196,67. Vor dem 01.04.2018 ist k = 1 (Gewicht 1),
bis zum 28.02.2023 ist k = 2 (Gewicht 1/2). Ab dem 03.11.2026 liefert SNPP keine NRT-Daten mehr, k ist dann 2.

## Ergebnis in Zahlen

- **Niveau:** `n_viirs` / `n_snpp` je Region und Jahr im Median 1,006 (10–90 %: 0,93–1,12), kleinstes Verhältnis je Region 0,95 (ES30).
  Je Jahr weicht die Summe der Reihe um −2,4 bis +4,6 % von SNPP allein ab (FRP −5 bis +20 %, 2023 mit NOAA-21 am stärksten).
- **Genauigkeit vor 2012:** unverändert (D1 × 2,08, D3 × 1,46, D4 R² 0,59, Großfeuer-Kappa 0,67), weil gegen SNPP geprüft wird.
- **Neue Tage:** 03.–13.11.2026 haben jetzt einen gemessenen Wert (vorher keiner).
- **Zeilenbilanz:** 940.293 gelesen = 712.097 behalten + 228.196 verworfen (type 2: 133.317, type 3: 2.450, Ortsmaske: 4.274,
  außerhalb der Untersuchungsregionen: 88.155). Das SNPP-Archiv ist jetzt die intakte Fassung aus dem ZIP, es gibt keine `invalid_value`-Zeile mehr.

## Was das Frontend beachten muss

- `n_snpp` ist **nicht mehr** die Referenz. Für Werte immer `n_harm`/`frp_harm` nehmen, für „gemessen“ `n_viirs`.
- Auf der Karte kann ab 2018 dasselbe Feuer als Punkt von SNPP und von NOAA-20/21 erscheinen (andere Überflugzeit).
  `in_series_n` filtert nur MODIS-Doppelte. Punkte nie zählen, sondern `weight_n` summieren. Bei Bedarf nach `satellite` filtern.
- `weight_n` = 1/3 ist kein „Drittel Feuer“ und darf nicht im Popup stehen.
- `h3_cell` hat Auflösung 8. Für ganz Iberien besser auf Auflösung 5 oder 6 hochrechnen.
- Die Datenbank muss neu angelegt werden: `docker compose down -v && docker compose up -d db`, dann `pipeline/load_to_db.py`.

## Offene Punkte

1. **Bänder gemessener Tage** sind weiterhin die Annahme für einen Satelliten (Zählrauschen mit Mindestfaktor). Mit drei
   Satelliten wären sie enger (N3: × 1,5 statt × 2,0), das ist noch nicht eingebaut.
2. **Ausfall eines Satelliten:** Meldet einer an einem Tag nichts (z. B. NOAA-20 am 04.02.2024), zählt er als 0 im Mittel.
   Der Tag ist nur als `possible_gap` markiert (21 Tage insgesamt). Ihn aus dem Mittel zu nehmen, wäre genauer, braucht aber eine Regel.
3. **H3-Auflösung 8** ist ein Vorschlag. Das Team kann sie in `grid.h3_resolution` ändern.
4. **NRT** von NOAA-20/21 wird später durch Archivdaten ersetzt (vorläufig: `is_provisional`).
6. Der Regressionstest gegen Version 1 wird übersprungen, weil Version 1 nicht im Repository liegt.
