# Schritt 5 und Verbesserungen: ehrliche Güte, robusteres Modell, Wetter nach dem 22.11.

Stand: 15.11.2026. Modellversion `0.2-weather`. Diese Datei ergänzt [weather_model.md](weather_model.md), die die
Schritte 2–4 und 6 beschreibt. **Die Zahlen hier ersetzen die Gewinne mit Wetter aus weather_model.md, Abschnitte
4.3 und 5.** Jene waren mit dem *tatsächlichen* Wetter des Zieltags gemessen und deshalb eine Obergrenze.

## Kurzfassung

| Großfeuer-Tag, Gewinn gegenüber der Saisonkurve | Tag 1 | Tag 3 | Tag 5 | Tag 7 | Tag 10 |
|---|---|---|---|---|---|
| ohne Wetter | 0,213 | 0,078 | 0,037 | 0,020 | 0,005 |
| **mit Wetter, mit echten Vorhersagefehlern (ehrlich)** | **0,250** | **0,147** | **0,109** | **0,077** | **0,053** |
| 90-%-Intervall über Jahre | 0,221–0,273 | 0,121–0,176 | 0,086–0,135 | 0,060–0,097 | 0,034–0,076 |
| zum Vergleich: dasselbe Modell mit tatsächlichem Wetter | 0,255 | 0,154 | 0,123 | 0,092 | 0,068 |

- **Das Wetter hilft auch mit echten Vorhersagen an jedem Tag 1–10.** Der Gewinn liegt an Tag 5 etwa beim Dreifachen
  dessen, was das Modell ohne Wetter schafft, an Tag 10 beim Zehnfachen.
- **Die wichtigste Erkenntnis:** Ein Modell, das auf perfektem Wetter trainiert wurde, **bricht mit echten Vorhersagen
  ein**. Auf der Validierung fiel es unter das Modell ohne Wetter (0,024 gegenüber 0,048). Erst das Training auf
  Wetter **mit** realistischen Vorhersagefehlern macht es robust (0,093). Es lernt dann, dem Wetter weit voraus
  weniger zu trauen.
- **Weitere Verbesserungen:**
  - eine glattere Saisonkurve; der Sprung bei Katalonien am 19./20.11. ist weg,
  - eine Bias-Korrektur der IFS-Vorhersage,
  - nichtlineare Terme,
  - eine Spanne, die auch die Unsicherheit des Wetters enthält (51 Ensemble-Mitglieder).
- **Nach dem 22.11.** übernimmt automatisch Open-Meteo als Wetterquelle. Das Modell braucht dafür nur noch die
  Grundvariablen; FWI und Fosberg rechnet es selbst.
- **Laufzeit:**
  - `train` dauert 6,4 min statt 19 min,
  - `predict` dauert 7 s mit Ensemble (1 Kern, 1,1 GB).
- **KPIs:** Alle Pflicht-KPIs außer D3 sind bestanden. D3 ist die Kalibrierung des Wochenausblicks; sie hängt an der
  Team-Entscheidung zum Wochenziel.

---

## 1. Dateien

| Datei | Neu / geändert | Aufgabe |
|---|---|---|
| `features/forecast_errors.py` | neu | Holt die IFS-Vorhersagen früherer Läufe (Open-Meteo Previous Runs API). Rechnet daraus Tageswerte je Vorlauf, die Fehler gegen ERA5, die Bias-Tabelle und das Wachstum der Fehler. |
| `features/perturb.py` | neu | `ErrorModel` mit Töpfen echter Fehler, `BiasCorrection`, und `Perturber`: Er gibt den Vorhersagetagen Fehler und rechnet FWI, Regen davor und die Abweichungen bis zum Zieltag neu. Wird auch für das Ensemble genutzt. |
| `features/open_meteo.py` | neu | Zweite Wetterquelle: IFS-Vorhersage und letzte Tage, ERA5-Historie, ECMWF-Ensemble. Gleiche Spalten wie Meteomatics. |
| `features/calendar.py` | neu | Gesetzliche Feiertage ES, PT, FR, Ostern berechnet, ohne zusätzliches Paket |
| `features/climatology.py` | geändert | `doy_climatology_shrunk`: Saisonkurve mit Gauß-Kern und Zug zum Mittel |
| `features/weather.py` | geändert | eigener Fosberg-Index, Kernsätze `CORE_SETS`, nichtlineare Terme, Bias-Korrektur der Live-Zeilen, Vermerk `lead_day` je Zeile |
| `models/logistic.py`, `models/daily.py` | geändert | Warmstart; `refit_like` für schnelle Bootstrap-Modelle |
| `run_forecast.py` | geändert | Auswahl auf der Validierung mit Fehlern, ehrliche Auswertung, Training mit Fehlern, Ensemble-Spanne, neue Saisonkurve |
| `fetch_weather.py` | geändert | Befehle `errors` und `ensemble`, `--provider open-meteo` für `history --append`, `recent` und `forecast` |
| `daily.py` | geändert | nach dem 22.11. Open-Meteo samt ERA5-Verlängerung, Ensemble, `status.json` |
| `config.yaml` | geändert | `model.climatology`, `model.honest`, `daily.fallback_provider`, `daily.required_groups`, `daily.ensemble` |
| `tests/test_step5.py` | neu | 9 Tests (Verrauschen, Bias, Saisonkurve, Feiertage, Fosberg, Open-Meteo-Tageswerte) |

Neue Daten (von Git ignoriert):
- `data/forecast/ifs_errors.parquet` (1,7 MB): 67.160 Fehler, 23 Regionen × 365 Tage × 8 Vorläufe,
- `data/raw/weather/open_meteo/`: Zwischenspeicher,
- `data/forecast/weather_ensemble_<tag>.parquet`,
- `data/forecast/status.json`.

---

## 2. Schritt 5: ehrliche Güte für die Tage 1–10

### 2.1 Warum

Bisher bekam das Modell im Test das analysierte Wetter (ERA5) des Zieltags. Live kennt es nur eine Vorhersage, die am
Ausgabetag gemacht wurde. Dazu kommt: Der FWI des Zieltags hängt auch vom Wetter **aller** Tage zwischen Ausgabetag
und Zieltag ab. Auch diese Tage sind live nur vorhergesagt.

### 2.2 Gibt es archivierte Vorhersagen?

- **Meteomatics:** nein. Die Abfrage `get_init_date` liefert für vergangene Tage `0000-00-00`, und die Doku sagt zu
  Ensembles: „Historical model data is not stored, except for the control run.“
- **Open-Meteo:** ja. Die Previous Runs API liefert für jede Stunde den Wert, den ECMWF IFS 0, 1, …, 7 Tage vorher
  vorhergesagt hatte (`<variable>_previous_dayN`, ab 2024). Ich nutze das Jahr **2025**, mit je einem Punkt pro Region
  (dem mit dem höchsten Feuergewicht).

Damit gilt der Fall 1 des Prompts nur halb: Echte archivierte Vorhersagen gibt es, aber nicht für alle Testjahre
2022–2026 und nicht für alle 182 Punkte. Ich nutze sie deshalb als **Quelle der Fehlergrößen** für das Verrauschen
(Fall 2). In `skill_basis` steht `analysis_with_noise`.

### 2.3 Die gemessenen Fehler (IFS − ERA5, 2025)

Verglichen wird mit genau den ERA5-Daten, auf denen das Modell trainiert ist. Die Fehler enthalten damit auch den
Unterschied zwischen den beiden Datensätzen. Das ist der Fehler, den das Modell in der Praxis sieht.

| Vorlauf | Temp. Mittel / Streuung | Feuchte | Wind | Niederschlag | Taupunkt |
|---|---|---|---|---|---|
| 0 Tage | −0,24 / 1,49 °C | −1,9 / 8,4 % | +0,3 / 4,4 km/h | +0,37 / 3,4 mm | −0,95 / 1,64 °C |
| 1 Tag | −0,13 / 1,57 | −2,4 / 8,7 | +0,4 / 4,6 | +0,21 / 3,3 | −0,99 / 1,72 |
| 3 Tage | −0,09 / 1,81 | −2,5 / 9,9 | +0,2 / 5,1 | +0,16 / 4,0 | −1,02 / 1,98 |
| 5 Tage | −0,09 / 2,36 | −2,9 / 12,5 | +0,3 / 6,1 | +0,15 / 5,2 | −1,14 / 2,51 |
| 7 Tage | −0,03 / 2,99 | −3,5 / 14,5 | +0,2 / 7,2 | +0,06 / 5,9 | −1,28 / 3,14 |

Drei Annahmen dazu:
- **Vorlauf 8–9 Tage:** Die API reicht nur bis 7 Tage. Für 8 und 9 Tage werden die Fehler von Tag 7 mit dem
  gemessenen Wachstum der Streuung über die Tage 4–7 vergrößert, 6–14 % pro Tag je nach Variable.
- **Böen:** Die Böen früherer Läufe sind nicht archiviert. Ihr Fehler ist der Böenfehler bei Vorlauf 0 plus der
  Zuwachs des Windfehlers mal 1,27. Das ist die Steigung von Böe auf Wind in ERA5.
- **Taupunkt:** Er wird aus Temperatur und Feuchte berechnet (Magnus-Formel).

Zuordnung der Vorläufe: `daily.py` läuft am Morgen nach dem Ausgabetag t0 mit dem 00-UTC-Lauf von t0 + 1. Das
Wetter des Zieltags t0 + L ist also (L − 1) Tage und 12 Stunden voraus, das entspricht `previous_day(L − 1)`.

### 2.4 Verrauschen (`features/perturb.py`)

Für eine Vorhersage vom Ausgabetag t0 auf t0 + L:

1. Für jeden Vorhersagetag k = 1…L wird ein **echter Fehlervektor** gezogen, alle Variablen gemeinsam, damit ihre
   Zusammenhänge erhalten bleiben. Er stammt aus derselben Region, einem Monat ±1, demselben Vorlauf k − 1, und
   getrennt danach, ob ERA5 an dem Tag Regen hatte (≥ 1 mm) oder nicht. Gerechnet wird
   ã_k = clip(a_k + e_k): Feuchte 1–100 %, Wind und Regen ≥ 0, Tageshöchstwert ≥ Temperatur, Böe ≥ Wind,
   Taupunkt ≤ Temperatur.
2. Ist die Bias-Korrektur gewählt, wird sie auf ã_k angewendet, genau wie live.
3. Die **FWI-Codes** werden vom analysierten Stand am Ausgabetag über alle k Tage fortgeschrieben, einmal mit
   a_k und einmal mit ã_k. Die Differenz der beiden Wege kommt zum Merkmal des Zieltags dazu. So bleibt die
   Rechnung je Punkt erhalten, und nur der Effekt der Fehler zählt.
4. **Regen davor:** Δ = Σ_k (ã_k − a_k). Daraus folgt Regen 30 Tage + Δ und Regen 90 Tage + Δ. „Tage seit Regen“
   wird mit den verrauschten Tagen neu bestimmt.
5. **Abweichungen vom Üblichen:** Sie verschieben sich um die Änderung des Werts.

Der Test hält zwei Dinge fest. Mit Fehler 0 kommen exakt die ursprünglichen Merkmale heraus. Und zusätzlicher Regen
senkt DC und setzt „Tage seit Regen“ auf 0.

**Eher streng gerechnet:** Die Fehler stammen von einem Punkt je Region, das Modell nutzt aber das Mittel aus bis zu
8 Punkten. Mittel haben etwas kleinere Fehler. Außerdem werden die Fehler aufeinanderfolgender Tage unabhängig
gezogen.

### 2.5 Auswertung

- **Training und Test** wie gehabt: 2012–2021 und 2022 bis 31.07.2026.
- **Testdaten mit Fehlern:** 3 verrauschte Kopien je Testzeile (`model.honest.draws`), Bootstrap über Jahre.
- **Platzierung:** Die Stufe mit Wetter wird an der ehrlichen Güte gemessen und nur dann ausgeliefert, wenn sie
  dort besser ist als die Stufe ohne Wetter und als die Saisonkurve.
- **Vergleichswert mit perfektem Wetter:** steht als Obergrenze in `forecast_evaluation.json` unter
  `daily.weather_analysis`.

---

## 3. Verbesserungen

Alle Entscheidungen fallen auf der **Validierung**: Gefittet wird 2012–2019, bewertet 2020–2021, mit Vorhersagefehlern
und mit dem mittleren Gewinn für Großfeuer-Tage über die Vorläufe 1, 3, 5, 7 und 10. Die Testjahre sind nicht
beteiligt.

### 3.1 Training mit Vorhersagefehlern

| Variante, Validierung mit Fehlern | mittlerer Gewinn |
|---|---|
| ohne Wetter | 0,048 |
| 22 Merkmale, trainiert auf perfektem Wetter | **0,024** (schlechter als ohne Wetter) |
| 22 Merkmale, trainiert auf Wetter mit Fehlern | 0,093 |
| … dazu die Bias-Korrektur | **0,096** → gewählt |
| zum Vergleich: auf perfektem Wetter trainiert und bewertet | 0,115 |

Das auf perfektem Wetter trainierte Modell verlässt sich stark auf das Wetter des Zieltags. Mit Vorhersagefehlern
liegt es dann oft sicher daneben. Mit verrauschtem Training lernt jedes Vorlauf-Modell, wie viel das Wetter bei
seinem Vorlauf wirklich verrät. Produktion und Bootstrap-Modelle werden genauso trainiert.

### 3.2 Merkmale nur aus den Grundvariablen

Die Sätze `CORE_SETS` brauchen nur Temperatur, Feuchte, Wind, Niederschlag, Böen und Taupunkt. Fosberg wird selbst
berechnet (`features/weather.py`, `fosberg_index`, nach Fosberg 1978 / Goodrick 2002). Die Korrelation mit dem
Meteomatics-Index beträgt 0,84; der Unterschied liegt an den Eingangsdaten (`mix` gegenüber ERA5). Die
Meteomatics-Indizes (Waldbrandwarnung, Dürreindex) fallen weg.

- Auf der Validierung mit perfektem Wetter kostet das nichts: 0,1146 ohne die Meteomatics-Indizes, 0,1145 mit ihnen.
- Dafür funktioniert das Modell mit jeder IFS-Quelle, also auch nach dem 22.11. über Open-Meteo. Und es lässt sich
  vollständig verrauschen.

Gewählt wurde `fwi_anom_core_nl` mit 22 Merkmalen:
- FFMC, DMC, DC, ISI, BUI, FWI,
- Höchsttemperatur, Feuchte, VPD, Böen, Regen, Tage seit Regen, Regen 30 Tage, Regenabweichung 90 Tage, Fosberg,
- die Abweichungen von FWI, DC, Höchsttemperatur und VPD,
- **nichtlineare Terme:** log FWI × Saisonkurve (logit), DC × Saisonkurve und (log FWI)².

Der Term FWI × Saison lässt einen hohen FWI im Winter anders wirken als im Sommer.

### 3.3 Bias-Korrektur der IFS-Vorhersage

`BiasCorrection` speichert den mittleren Fehler je Region, Monat und Vorlauf. Abgezogen wird er für Temperatur,
Feuchte, Wind, Böen, Höchsttemperatur und Taupunkt; der Niederschlag wird durch das Verhältnis IFS / ERA5 geteilt,
begrenzt auf 0,5–2. Angewendet wird sie auf die Live-Zeilen, also die letzten Tage und die Vorhersage
(`features/weather.py`, `correct_points`), und im Test auf die verrauschten Tage. Auf der Validierung bringt sie
+0,003 und wurde deshalb gewählt.

### 3.4 Glattere Saisonkurve (`doy_climatology_shrunk`)

Statt eines harten Fensters von ±7 Tagen:

- c(d) = (S(d) + m · P(d)) / (N(d) + m),
- S, N = Zahl der Ereignisse bzw. der beobachteten Tage je Kalendertag, geglättet mit einem zirkulären Gauß-Kern
  (σ = 10 Tage),
- P = dieselbe Rate mit einem breiten Kern (σ = 30 Tage),
- m = 20 Pseudo-Tage für Großfeuer-Tage, 0 für Feuertage.

Auf der Validierung wird die **Saisonkurve selbst** besser: für Großfeuer-Tage Brier −2,1 % und Log-Loss −5 %, für
Feuertage Brier −0,2 %. Der Anteil der Region-Tage auf dem Minimalwert sinkt von 37 % auf 6 %. Bei Katalonien sinkt
die Kurve vom 19. auf den 20.11. jetzt gleichmäßig von 0,69 % auf 0,66 %, vorher sprang sie von 0,48 % auf 0,01 %.

Weil die Saisonkurve der Vergleichsmaßstab ist, fallen die Gewinne ohne Wetter dadurch etwas kleiner aus (Tag 5:
0,037 statt 0,042). Der Maßstab ist strenger geworden, das Modell nicht schlechter.

### 3.5 Feiertage: getestet, nicht übernommen

Feiertag und Wochenende am Zieltag in der Stufe ohne Wetter: Auf der Validierung kam 0,047 heraus, ohne sie 0,048.
Die Feiertage bleiben deshalb draußen. Der Code steht für spätere Versuche bereit (`features/calendar.py`). Regionale
Feiertage sind nicht enthalten.

### 3.6 Spanne mit Wetter-Unsicherheit (Ensemble)

`fetch_weather.py ensemble` holt die ECMWF-IFS-Ensemblevorhersage: Kontrolllauf und 50 Mitglieder, 0,25°, über
Open-Meteo, für den stärksten Punkt jeder Region. Je Mitglied ergibt sich ein eigener Wetterweg: der deterministische
Weg plus die Abweichung des Mitglieds vom Ensemble-Mittel, an jedem Vorhersagetag. Darüber werden FWI und alle
Merkmale bis zum Zieltag gerechnet (wie in 2.4), dann wird das Modell angewendet.

Die Spanne `p_big_fire_day_lo` / `_hi` ist das Weitere von zwei Spannen:
- dem 5–95-%-Bereich der Ensemble-Mitglieder (Unsicherheit des Wetters),
- dem Bootstrap über Jahre (Unsicherheit der Gewichte).

Beispiel Katalonien am 19.11.: 1,6 %, Spanne 0,8–3,3 %.

### 3.7 Schnelleres Training (Vorschläge aus docs/logistic_model.md)

- **Bootstrap-Modelle** (`daily.refit_like`):
  - gleicher Merkmalsaufbau,
  - Warmstart bei den Produktionsgewichten,
  - Platt-Linie des Produktionsmodells übernommen, ohne inneren Fit.
- **Auswahl** nur auf Großfeuer-Tagen, wo auch entschieden wird.
- **FWI für alle Regionen gleichzeitig** statt Region für Region (40 s → 1 s).
- **Ensemble:** alle 51 Mitglieder in einem Durchgang je Vorlauf.

Ergebnis: `train` 19 min → **6,4 min**, `predict` mit Ensemble **7 s**.

---

## 4. Ergebnisse im Test (2022 bis 31.07.2026)

**Großfeuer-Tag, mit echten Vorhersagefehlern:**

| Vorlauf | Gewinn | 90-%-Intervall | AUC | PR-AUC | ECE | Steigung | Trefferquote / Fehlalarme (oberste 10 %) |
|---|---|---|---|---|---|---|---|
| 1 | 0,250 | 0,221–0,273 | 0,943 | 0,51 | 0,006 | 1,08 | 0,79 / 0,77 |
| 2 | 0,180 | 0,147–0,215 | 0,933 | 0,43 | 0,007 | 1,13 | 0,75 / 0,79 |
| 3 | 0,147 | 0,121–0,176 | 0,925 | 0,40 | 0,008 | 1,13 | 0,73 / 0,79 |
| 5 | 0,109 | 0,086–0,135 | 0,916 | 0,34 | 0,008 | 1,06 | 0,69 / 0,81 |
| 7 | 0,077 | 0,060–0,097 | 0,905 | 0,29 | 0,008 | 1,07 | 0,66 / 0,82 |
| 10 | 0,053 | 0,034–0,076 | 0,893 | 0,25 | 0,008 | 1,03 | 0,63 / 0,83 |

Die Saisonkurve allein erreicht AUC 0,851.

**Feuertag (SNPP), mit echten Vorhersagefehlern:**

| Vorlauf | Gewinn | ohne Wetter |
|---|---|---|
| 1 | 0,178 | 0,124 |
| 5 | 0,122 | 0,038 |
| 10 | 0,073 | 0,024 |

ECE ≤ 0,012.

**Risikoklassen** im Test, je Klasse der Anteil der Region-Tage und wie oft dann ein Großfeuer-Tag folgte:

| Klasse | Tag 1 | Tag 5 | Tag 10 |
|---|---|---|---|
| `low` | 57 %, 0,9 % | 57 %, 1,1 % | 55 %, 1,3 % |
| `normal` | 36 %, 1,6 % | 36 %, 2,7 % | 40 %, 3,2 % |
| `elevated` | 3,0 %, 11 % | 3,9 %, 11 % | 3,2 %, 11 % |
| `high` | 2,2 %, 25 % | 2,3 %, 25 % | 1,5 %, 27 % |
| `very_high` | 1,7 %, 54 % | 0,6 %, 37 % | 0,1 %, 44 % |

**Leave-one-year-out, Tag 1, mit Fehlern:** Die Stufe mit Wetter ist in allen 15 Jahren besser als die Saisonkurve
(0,12–0,31).

**Wochenausblick:** Das Wetter hilft hier weiterhin nicht (Woche 2: RPSS 0,017 mit gegenüber 0,020 ohne Wetter). Es
bleibt bei der Stufe ohne Wetter.

**Pro Region:** Für Regionen mit mindestens 30 Großfeuer-Tagen im Test entscheidet Regel 3.5 einzeln.

| Region | Ergebnis |
|---|---|
| ES30 (Madrid) | an keinem Vorlauf besser → Saisonkurve |
| ES61, ES52 | ab Tag 4 bzw. Tag 5 → Saisonkurve |
| ES51, PT18 | wechseln bei einzelnen Vorläufen hin und her (z. B. ES51 Tag 2), weil die untere Intervallgrenze knapp um 0 liegt (−0,002 / +0,004) |

---

## 5. KPIs (`data/forecast/forecast_kpi_report.json`)

| KPI | Wert | Schwelle | Ergebnis |
|---|---|---|---|
| A1–A7 | wie zuvor; A2 auch für Fosberg und die neuen Merkmale | | bestanden |
| A8 Determinismus | zwei Läufe hintereinander, identische Hashes aller Ausgaben | gleiche Hashes | bestanden |
| B1 / B2 | 0,250 / 0,147 | ≥ 0,10 / ≥ 0,05 | bestanden |
| B3 Wetter hilft, Tage 2–7 (Ziel 8–10) | +0,04 bis +0,07 an jedem Vorlauf, mit Fehlern | > 0 | bestanden, Ziel auch |
| B4 Tag 5 mit Wetter | 0,109, untere Grenze 0,086 | > 0 / ≥ 0 (Ziel 0,05) | bestanden, Ziel erreicht |
| B5 AUC | 0,943, jeder Vorlauf > Saisonkurve | ≥ 0,87 | bestanden |
| B6 Kalibrierung | ECE ≤ 0,009, Steigung 1,01–1,13 | ≤ 0,015, 0,8–1,2 | bestanden |
| B8 Rückfall | 0 Verstöße | 0 | bestanden |
| C1 / C2 | 0,178 / ECE 0,012 | > 0 / ≤ 0,03 | bestanden |
| D1 / D2 | RPSS 0,020 / Summen = 1 | | bestanden |
| **D3** Kalibrierung Woche | 0,059 (Klimatologie 0,067) | ≤ 0,05 | **verfehlt**, Team-Entscheidung zum Wochenziel |
| E1 | 15 von 15 Jahren | ≥ 80 % | bestanden |
| E4 | `analysis_with_noise` | gesetzt | bestanden |
| F5 | `train` 6,4 min, Anwenden 0,06 min | ≤ 10 / ≤ 1 | bestanden |
| F6 | 50 Tests | grün | bestanden |

---

## 6. Wetter nach dem 22.11.2026 (Open-Meteo)

- `daily.py` nimmt ab dem 23.11. automatisch Open-Meteo (`daily.fallback_provider`):
  - die **ERA5-Historie** wird bis 6 Tage vor heute verlängert (`history --append`),
  - die Tage danach bis gestern kommen aus **IFS** (`recent`),
  - die **Vorhersage** aus IFS,
  - dazu das **Ensemble**.
- Bedarf: etwa 1–2 Anfragen je Schritt. Gewichtet sind das etwa 800 Aufrufe am Tag, davon das meiste fürs Ensemble.
  Das Tageslimit liegt bei 10.000.
- **Bedingungen:**
  - kostenlos nur bei **nicht-kommerzieller** Nutzung,
  - Lizenz **CC BY 4.0**: Die App muss Open-Meteo nennen, z. B. „Wetterdaten: Open-Meteo.com (ECMWF IFS, ERA5)“.
  - Bei Werbung, Abos oder kommerziellem Einsatz braucht es einen bezahlten Zugang.
- **Vergleich am 15.11.:** Meteomatics-IFS und Open-Meteo-IFS am selben Tag stimmen bei Temperatur, Feuchte, Taupunkt
  und Regen gut überein (Korrelation 0,90–0,98). Wind und Böen weichen stärker ab (0,67–0,77), wohl wegen
  unterschiedlicher Läufe und Interpolation. Die Fehlerstatistik und die Bias-Korrektur stammen von Open-Meteo,
  passen also gerade zur Zeit nach dem 22.11. gut.
- **Fosberg, Waldbrandwarnung und Dürreindex** von Meteomatics gibt es danach nicht mehr. Das Modell braucht sie
  nicht mehr.

---

## 7. Grenzen und offene Punkte

1. **Fehler aus einem Jahr (2025) und einem Punkt je Region.** Die Güte ist eher vorsichtig geschätzt (2.4). Mehr
   Jahre (ab 2024) oder mehr Punkte wären möglich, wenn Open-Meteo-Kontingent übrig ist.
2. **Fehler aufeinanderfolgender Tage sind unabhängig gezogen.** Echte Vorhersagefehler hängen zusammen, z. B. ein
   verpasstes Tief über mehrere Tage. Für die Trockenheitscodes kann das etwas optimistisch sein; für das einzelne
   Wetter des Zieltags spielt es keine Rolle.
3. **Regel 3.5 je Region** führt bei knappen Fällen zu Wechseln zwischen benachbarten Vorläufen (ES51, PT18).
   **Vorschlag zur Entscheidung:** Eine Region fällt nur dann auf die Saisonkurve zurück, wenn ihr Gewinn ≤ 0 ist, statt
   schon bei unterer Grenze < 0. Sonst folgt sie der Entscheidung über alle Regionen. Das wäre eine Änderung der Regel
   aus dem Prompt, deshalb nicht umgesetzt.
4. **Wochenausblick (D3)** wartet auf die Team-Entscheidung zum Wochenziel.
5. **Meteomatics-Wind gegenüber Open-Meteo-Wind** (6.): Bis zum 22.11. kommt die Vorhersage von Meteomatics, die
   Bias-Korrektur ist aber an Open-Meteo gemessen. Für Wind und Böen ist sie deshalb bis dahin ungenauer.

---

## 8. Ausführen

```bash
cd La-Brasa/forecast
.venv/bin/python fetch_weather.py errors --start 2025-01-01 --end 2025-12-31   # einmalig, ~12 Anfragen, ~15 min
.venv/bin/python run_forecast.py train        # Auswahl, ehrliche Auswertung, Modelle -> bundle.pkl (~6,5 min)
.venv/bin/python daily.py                     # Wetter + Ensemble + predict (~1 min, davon predict 7 s)
```

`train` braucht `data/forecast/ifs_errors.parquet`. Fehlt die Datei, wird wie vor Schritt 5 mit analysiertem Wetter
ausgewählt und ausgewertet, und `skill_basis` ist dann `analysis`.

Quellen:
- [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api)
- [Open-Meteo Bedingungen](https://open-meteo.com/en/terms)
- [Meteomatics Ensemble-Auswahl](https://www.meteomatics.com/en/api/request/optional-parameters/ensemble-member-selection)
- [Meteomatics optionale Parameter](https://www.meteomatics.com/en/api/request/optional-parameters)
