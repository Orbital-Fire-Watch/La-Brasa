# Forecast mit Wetter: Dateien und Berechnung (Schritte 2–4 und 6)

Stand: 14.11.2026. Modellversion `0.2-weather` (Stufe mit Wetter), `0.1-noweather` (Stufe ohne Wetter).

> **Aktualisiert am 15.11.2026:** Schritt 5 (ehrliche Güte mit echten Vorhersagefehlern) und mehrere Verbesserungen
> stehen in [honest_evaluation.md](honest_evaluation.md). **Die Gewinne mit Wetter in den Abschnitten 4.3 und 5 hier sind
> überholt.** Sie galten für das tatsächliche Wetter des Zieltags, also eine Obergrenze. Ehrlich gemessen sind es an
> Tag 5 0,109 statt 0,158 und an Tag 10 0,053 statt 0,134.
>
> Außerdem geändert:
> - Merkmale nur noch aus den Grundvariablen, Fosberg selbst berechnet, ohne die Meteomatics-Indizes,
> - eine glattere Saisonkurve,
> - eine Bias-Korrektur,
> - eine Ensemble-Spanne,
> - Open-Meteo als Wetterquelle nach dem 22.11.

Dieses Dokument erklärt, was in den Schritten 2–4 dazugekommen ist:

- **Schritt 2:** Wetterdaten prüfen.
- **Schritt 3:** eigenes kanadisches FWI-System.
- **Schritt 4:** Tages- und Wochenmodelle mit Wetter.

Für jeden Schritt steht hier, welche Datei was macht und wie gerechnet wird. Schritt 1 (Modell ohne Wetter) steht in
`forecast/README.md`, Abschnitt 1.5.

## Kurzfassung

- **Die Wetterdaten sind vollständig und plausibel** (KPIs A5 und A6 bestanden). Dafür musste die Historie aber neu
  geladen werden. Die Meteomatics-Quelle `mix` hat für die Vergangenheit **falsche Niederschläge**, z. B.
  in Galicien 2023 nur 42 mm im Jahr statt etwa 1400 mm. Jetzt kommt die Historie aus **ERA5**, der Reanalyse von
  ECMWF.
- **Das eigene FWI-System trifft die veröffentlichte Testtabelle auf ≤ 0,005 genau** (KPI A7, Schwelle < 0,1).
- **Mit Wetter wird das Tagesmodell deutlich besser**, vor allem an den Tagen 4–10:

  | Vorlauf | Gewinn ohne Wetter | Gewinn mit Wetter |
  |---|---|---|
  | Tag 5 | 0,04 | 0,16 |
  | Tag 10 | 0,01 | 0,13 |

  Gewinn heißt hier: um wie viel besser als die Saisonkurve.

  **Wichtig:** Im Test steckt das *tatsächliche* Wetter des Zieltags. Mit einer echten Wettervorhersage wird es
  schlechter, besonders an den späten Tagen. Die Zahlen sind deshalb eine **Obergrenze**. Wie weit sie sinken, misst
  Schritt 5.
- **Der Wochenausblick wird durch das Wetter nicht besser.** Er bleibt bei der Stufe ohne Wetter.
- **Seit Schritt 6 nutzt die Ausgabe vom 13.11. das Wetter**, mit einer IFS-Vorhersage für den 14.–24.11. (Abschnitt 7).
  Fehlt die Wettervorhersage, liefert die Pipeline automatisch die Stufe ohne Wetter aus.
- **KPIs:** Alle Pflicht-KPIs außer D3 sind bestanden. D3 (Kalibrierung des Wochenausblicks) war schon in Schritt 1
  verfehlt.

---

## 1. Dateien

### Neu

| Datei | Aufgabe |
|---|---|
| `features/weather.py` | Lädt die Wetterpunkte und fügt Historie, `recent` und Vorhersage zusammen. Rechnet den FWI je Punkt und mittelt danach je Region, gewichtet nach Feuern. Leitet Merkmale ab (VPD, Regen davor, Abweichungen vom Üblichen). Enthält außerdem die Prüfungen A5/A6 und die Signalprüfung. |
| `features/fwi.py` | Kanadisches FWI-System: FFMC, DMC, DC, ISI, BUI, FWI. Rechnet Tag für Tag, für alle Punkte gleichzeitig. |
| `tests/test_fwi.py` | Prüft gegen die Testtabelle von Van Wagner & Pickett (1985) (KPI A7), dazu Eigenschaften: Regen macht feucht, Trockenheit macht trocken, fehlende Tage. |
| `tests/test_weather_features.py` | Prüft gewichtete Mittel, die Merkmale, dass kein Blick in die Zukunft möglich ist, und die Prüfungen A5/A6. Alles auf erfundenen Daten. |
| `tests/data/fwi_reference_vanwagner1985.csv` | Die Testtabelle mit Quellenangabe im Kopf. |
| `docs/weather_model.md` | Dieses Dokument. |

### Geändert

| Datei | Was |
|---|---|
| `config.yaml` | `meteomatics.models`: die Quelle je Zweck und Gruppe, also ERA5 für die Historie von `core` und ECMWF IFS für die letzten Tage und die Vorhersage. `model.version` 0.2-weather, `model.weather.selection_leads`. |
| `fetch_weather.py` | Nutzt die Quelle je Gruppe aus der Konfiguration. Neuer Befehl `recent` für die Tage nach dem Ende von ERA5. |
| `models/daily.py`, `models/weekly.py` | Nehmen zusätzliche Merkmale (`extra`) an. Ohne sie ist es das Modell aus Schritt 1. |
| `run_forecast.py` | Befehle `train` (schwer, Arbeitsrechner) und `predict` (leicht, Server, lädt `models/bundle.pkl`), 1 BLAS-Thread als Standard. Zwei Stufen (`noweather`, `weather`), Auswahl der Wettermerkmale auf der Validierung, Befehl `weather-qc`, KPIs A5, A6, A7, B3 und B4, Zukunfts-Prüfung auch für das Wetter, Rückfall je Vorlauf. |

### Daten in `data/forecast/` (von Git ignoriert)

| Datei | Inhalt |
|---|---|
| `weather_points_history_core.parquet` | ERA5, 182 Punkte, 20.01.2012–08.11.2026 |
| `weather_points_recent_core.parquet` | ECMWF IFS, 09.–13.11.2026 (ERA5 endet etwa 5 Tage vor heute) |
| `weather_points_history_fire.parquet` | `mix`: Fosberg, Waldbrandwarnung, Dürreindex, 20.01.2012–13.11.2026 |
| `weather_region_*.parquet` | dieselben Werte je Region gemittelt (nur zur Ansicht, das Modell rechnet aus den Punkten) |
| `backup_mix_core/` | die erste, verworfene `core`-Historie aus `mix` |
| `weather_qc.json` | Ergebnis von Schritt 2 (A5, A6, Lücken, Ausreißer, Signal) |

---

## 2. Schritt 2: Wetterdaten prüfen

### 2.1 Das Problem mit `mix`

`mix` ist die Voreinstellung von Meteomatics: Der Dienst wählt je Ort und Zeit selbst eine Quelle. Beim Prüfen
der Jahressummen fiel auf, dass Niederschlag und Böen sich über die Jahre sprunghaft ändern. Temperatur,
Luftfeuchte und Wind waren dagegen gleichmäßig.

| Punkt | Jahr | `mix` | ERA5 |
|---|---|---|---|
| Galicien (42,125 N, −7,125 E) | 2016 | 1293 mm, 35 % Regentage | 1349 mm, 37 % |
| Galicien | 2023 | **42 mm, 4 % Regentage** | 1396 mm, 36 % |
| Aragón (41,625 N, −0,875 E) | 2016 | **6 mm, 0 % Regentage** | 407 mm, 18 % |
| Aragón | 2023 | 200 mm | 266 mm |

Auch die Böen von `mix` springen: 2014–2019 liegen sie etwa 10 km/h niedriger als 2012–2013 und ab 2020. Mit diesen
Daten hätte das Modell vor allem die Wechsel der Quelle gelernt, ähnlich wie beim Satelliten-Effekt in Schritt 1.

**Lösung** (`config.yaml`, `meteomatics.models`):

| Zweck | `core` (Temperatur, Feuchte, Wind, Regen, Böen, Taupunkt) | `fire` (Fosberg, Waldbrandwarnung, Dürreindex) |
|---|---|---|
| Historie | `ecmwf-era5` (bis 5 Tage vor heute) | `mix` |
| `recent`, Lücke bis zum Ausgabetag | `ecmwf-ifs` | `mix` |
| Vorhersage | `ecmwf-ifs` | `mix` |

ECMWF IFS ist das Vorhersagemodell zu ERA5. Damit passen Training und Vorhersage physikalisch am besten zusammen. Die
drei Indizes der Gruppe `fire` zeigen keine Sprünge und bleiben deshalb bei `mix`.

Die Neuladung kostete 60 Anfragen für die Historie und 4 für `recent`. Die ERA5-Anfragen waren nach wenigen Minuten
fertig.

### 2.2 Prüfungen (`wx.quality_report`, Befehl `run_forecast.py weather-qc`)

| Prüfung | Ergebnis |
|---|---|
| **A5** vollständig, Region × Tag, 20.01.2012–13.11.2026 (23 × 5412) | `core` 100 %, `fire` 100 % (Schwellen 99,5 % / 95 %) → bestanden |
| **A6** Wertebereiche je Region und je Punkt | 0 Verstöße → bestanden |
| Lücken je Region und Jahr | keine |
| Punkte mit Lücken | `core`: keine. `fire`: 21 von 182 Küstenpunkten zeitweise leer, 4 immer leer. Die Indizes gibt es nur über Land, das Gewicht wird dann auf die anderen Punkte verteilt. |
| Taupunkt über Temperatur (+0,5 °C) | 14 von 124.476 Region-Tagen, Nebellagen |
| Sprung der Temperatur > 15 °C von Tag zu Tag | 5 |
| Niederschlag > 100 mm/24 h | 2 |
| längste Folge gleicher Werte (Hinweis auf festhängende Werte) | 2 Tage |

Wertebereiche für A6:

- `t_2m` −25…50 °C, RH 0–100 %, Niederschlag 0–300 mm, Wind und Böen ≥ 0. Diese Bereiche stehen so im Prompt.
- Dazu habe ich ergänzt:
  - Tagesminimum −40…50 °C. Eine ERA5-Zelle in den östlichen Pyrenäen hatte am 09.02.2018 −26,2 °C, das ist echt.
  - Taupunkt −45…40 °C, Waldbrandwarnung 0–1, Dürreindex −4…4.
  - Fosberg ≥ 0, ohne Obergrenze: Die Formel gibt über 100, wenn der Wind stärker als 30 mph ist.

### 2.3 Gibt das Wetter überhaupt Information? (`wx.signal_check`)

Diese Prüfung fragt: Wie gut trennt ein einzelnes Merkmal Großfeuer-Tage von anderen Tagen?

- **Datenbasis:** nur Trainingsjahre 2012–2021, nur Juni–September, 28.037 Region-Tage, darunter 1248 Großfeuer-Tage.
- **Maß:** ROC-AUC. 0,5 heißt kein Signal, unter 0,5 heißt umgekehrt (je kleiner der Wert, desto mehr Feuer).
- **„In Region und Monat“:** Hier wird der Mittelwert der Region in diesem Monat abgezogen. So zählt nicht, dass
  heiße Regionen öfter brennen.

| Merkmal | AUC | AUC in Region und Monat |
|---|---|---|
| FWI-Abweichung vom Üblichen | 0,75 | **0,76** |
| ISI (log) | 0,73 | 0,72 |
| FWI (log) | 0,74 | 0,72 |
| Dampfdruckdefizit (VPD) | 0,71 | 0,71 |
| Tageshöchsttemperatur | 0,69 | 0,70 |
| Waldbrandwarnung (Meteomatics) | 0,66 | 0,67 |
| FFMC / BUI / Tage seit Regen | 0,75 / 0,71 / 0,71 | 0,65 / 0,66 / 0,66 |
| Fosberg (Meteomatics) | 0,61 | 0,63 |
| Luftfeuchte | 0,27 | 0,29 (umgekehrt: 0,71) |
| Regen der letzten 30 Tage | 0,29 | 0,40 |
| Böen | 0,51 | 0,53 (kaum Signal) |

Das eigene FWI-System trennt besser als die fertigen Indizes von Meteomatics.

---

## 3. Schritt 3: Kanadisches FWI-System (`features/fwi.py`)

### 3.1 Eingaben und Ablauf

Je Tag und Punkt gehen vier Werte ein:

- Temperatur `t_2m` (°C), relative Luftfeuchte (%) und Wind in 10 m Höhe (km/h), jeweils um 12:00 UTC,
- Niederschlag der 24 Stunden bis 12:00 UTC (mm).

Gerechnet wird **je Wetterpunkt** und erst danach je Region gemittelt, gewichtet nach Feuern (Gewichte aus
`weather_points.parquet`). Der FWI ist nichtlinear. Ein FWI aus dem Regionsmittel wäre deshalb etwas anderes als das
Mittel der FWI-Werte.

Die drei **Feuchte-Codes** werden jeden Tag aus dem Vortag fortgeschrieben, sie haben ein Gedächtnis:

| Code | Schicht | Gedächtnis | Wird nass ab | Trocknet durch |
|---|---|---|---|---|
| FFMC | Streu, Nadeln | Stunden bis Tage | > 0,5 mm | Temperatur, niedrige Feuchte, Wind |
| DMC | lockere Humusschicht | Wochen | > 1,5 mm | Temperatur, niedrige Feuchte, Tageslänge |
| DC | tiefe, verdichtete Schicht | Monate | > 2,8 mm | Temperatur, Tageslänge |

Aus den Codes entstehen die Indizes:

- **ISI** (Ausbreitung) = 0,208 · f(Wind) · f(FFMC), mit f(Wind) = e^(0,05039 · Wind).
- **BUI** (verfügbarer Brennstoff) aus DMC und DC.
- **FWI** (Feuerintensität) aus ISI und BUI.

### 3.2 Formeln

Die Formeln folgen Van Wagner & Pickett (1985), Forestry Technical Report 33, und Van Wagner (1987), Technical
Report 35. Gegengeprüft habe ich sie mit dem Code des kanadischen Forstdienstes (Paket `cffdrs`).

- **FFMC:**
  - Der Code wird in eine Feuchte umgerechnet: m = 147,28 · (101 − FFMC) / (59,5 + FFMC).
  - Regen über 0,5 mm erhöht m.
  - m nähert sich der Gleichgewichtsfeuchte, je nachdem ob das Material trocknet oder feucht wird. Die
    Geschwindigkeit hängt von Feuchte, Wind und Temperatur ab.
  - Zum Schluss wird m wieder in FFMC zurückgerechnet.
- **DMC:**
  - Täglicher Zuwachs: 1,894 · (T + 1,1) · (100 − RH) · Le · 10⁻⁴.
  - Le ist die effektive Tageslänge je Monat.
  - Regen über 1,5 mm senkt den Code über die Feuchte der Humusschicht.
- **DC:**
  - Täglicher Zuwachs: (0,36 · (T + 2,8) + Lf) / 2.
  - Lf ist die Tageslängen-Korrektur je Monat.
  - Regen über 2,8 mm senkt den Code über den Wasservorrat Q = 800 · e^(−DC/400).
- **BUI:**
  - Bei DMC ≤ 0,4 · DC gilt BUI = 0,8 · DMC · DC / (DMC + 0,4 · DC).
  - Sonst gibt es eine Korrektur, damit BUI stetig bleibt.
- **FWI:**
  - B = 0,1 · ISI · f(BUI).
  - Bei B > 1 gilt FWI = e^(2,72 · (0,434 · ln B)^0,647), sonst FWI = B.

Tageslängen-Faktoren für 30–60 °N (alle Regionen liegen bei 36–44 °N):

| Monat | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Le (DMC) | 6,5 | 7,5 | 9,0 | 12,8 | 13,9 | 13,9 | 12,4 | 10,9 | 9,4 | 8,0 | 7,0 | 6,0 |
| Lf (DC) | −1,6 | −1,6 | −1,6 | 0,9 | 3,8 | 5,8 | 6,4 | 5,0 | 2,4 | 0,4 | −1,6 | −1,6 |

### 3.3 Festlegungen

- **Startwerte:** FFMC 85, DMC 6, DC 15 am 20.01.2012, so wie im Standardverfahren. Weil der Start im nassen Winter
  liegt, erreichen die Codes nach wenigen Wochen (DC nach wenigen Monaten) ihre wetterbedingten Werte.
- **Kein Überwintern:** Gerechnet wird das ganze Jahr durch, wie bei EFFIS für Südeuropa. Schnee spielt dort, wo es
  brennt, kaum eine Rolle.
- **Fehlender Tag:** Die Codes bleiben stehen, die Indizes sind an diesem Tag leer.
- **Zwei Konstanten**, die zunächst falsch waren: Die Abweichung lag bei FFMC bei 0,12 und bei ISI bei 0,25.
  - Statt der gerundeten 147,2 aus der Veröffentlichung von 1987 wird 250 · 59,5 / 101 = 147,277 benutzt, wie im
    FORTRAN-Programm von 1985.
  - Die DMC-Regenformel steht in der Form des Programms: 20 + 280 / e^(0,023 · DMC).
- **Zeitpunkt:** 12:00 UTC entspricht 12–13 Uhr Ortszeit statt genau Mittag. Das ist üblich und nur eine kleine
  Abweichung.

### 3.4 Prüfung (KPI A7)

Die Testtabelle umfasst 49 aufeinanderfolgende Tage (13.04.–30.05.1985) mit veröffentlichten Werten aller sechs
Komponenten. Quelle ist Van Wagner & Pickett (1985), die genauen Werte stammen aus den Testdaten von `cffdrs`.

Größte Abweichung: **0,005**, das ist reiner Rundungsfehler der Tabelle. Die Schwelle liegt bei 0,1.

Im Ergebnis: DC liegt im Sommer bei 600–1300, in Galicien bei etwa 600–750, im Süden und in Aragón bis etwa 1300. Das
passt zu den bekannten Werten für Iberien.

---

## 4. Schritt 4: Modelle mit Wetter

### 4.1 Merkmale (`features/weather.py`, `add_derived`)

Alle Werte eines Tages nutzen nur Wetter bis einschließlich dieses Tages. In einer Vorhersage für den Tag t0 + L
kommen die Merkmale vom Zieltag t0 + L. Im Test ist das das analysierte Wetter (ERA5), live die Wettervorhersage.

| Merkmal | Berechnung |
|---|---|
| `ffmc`, `dmc`, `dc`, `bui` | eigenes FWI-System (Abschnitt 3) |
| `log_isi`, `log_fwi` | log(1 + ISI), log(1 + FWI). So werden die sehr schiefen Verteilungen gedämpft. |
| `tmax`, `rh`, `gust`, `precip` | Höchsttemperatur der 24 h, Luftfeuchte 12 UTC, Böen der 24 h, Niederschlag der 24 h |
| `vpd` | Dampfdruckdefizit in kPa: es(T) − es(Td), mit es(T) = 0,6108 · e^(17,27 · T / (T + 237,3)) |
| `log_days_since_rain` | log(1 + Tage seit dem letzten Tag mit ≥ 1 mm), höchstens 120 |
| `rain30` | Regen der letzten 30 Tage |
| `rain90_anom` | Regen der letzten 90 Tage minus das Übliche (siehe unten) |
| `fwi_anom`, `dc_anom`, `tmax_anom`, `vpd_anom` | Wert minus das Übliche (siehe unten) |
| `fosberg`, `ffw`, `drought` | fertige Indizes von Meteomatics |

**„Das Übliche“:** der Mittelwert je Region und Kalendertag über die **Trainingsjahre 2012–2021**, ±7 Tage zirkulär
geglättet. Die Testjahre fließen nicht ein (A3).

Feiertage sind noch nicht dabei. Das Paket `holidays` ist nicht installiert, und Schritt 4 sollte ohne neue
Abhängigkeit auskommen. Der Wochentag steckt schon im Modell für den Feuertag.

### 4.2 Zwei Stufen

- **`noweather`:** Saisonkurve, Feuerverlauf am Ausgabetag und Regionseffekt, genau wie in Schritt 1.
- **`weather`:** dasselbe plus die Wettermerkmale des Zieltags.

Beide Stufen sind dieselbe penalisierte logistische Regression mit Platt-Kalibrierung (L2 = 100), eine je Ziel und
Vorlauf. Die Merkmale werden standardisiert, und die L2-Strafe zieht stark verwandte Merkmale (z. B. DMC, BUI und FWI)
zusammen, statt dass einzelne Gewichte ausschlagen.

**Auswahl der Wettermerkmale** auf der Validierung: Training 2012–2019, Validierung 2020–2021. Die Testjahre waren
dabei nicht beteiligt. Gewinn gegenüber der Saisonkurve für Großfeuer-Tage:

| Satz | Tag 1 | Tag 3 | Tag 5 | Tag 7 | Tag 10 | Mittel |
|---|---|---|---|---|---|---|
| ohne Wetter | 0,135 | 0,057 | 0,053 | 0,051 | 0,036 | 0,067 |
| `small` (5 Merkmale: FWI, DC, Feuchte, Höchsttemperatur, Tage seit Regen) | 0,162 | 0,102 | 0,101 | 0,103 | 0,096 | 0,113 |
| `fwi` (17 Merkmale) | 0,167 | 0,115 | 0,112 | 0,113 | 0,107 | 0,123 |
| **`fwi_anom`** (21 Merkmale, `fwi` + 4 Abweichungen) | 0,170 | 0,121 | 0,120 | 0,121 | 0,116 | **0,130** → gewählt |

**Was ausgeliefert wird:**

1. **Stufe:** Je Ziel und Vorlauf wird die Stufe mit Wetter genommen, wenn sie auf den Testjahren den höheren Gewinn
   hat **und** für den Zieltag Wetter da ist. Sonst die Stufe ohne Wetter. Das ist zugleich KPI F7.
2. **Rückfall auf die Saisonkurve:** Die gewählte Stufe wird nur ausgeliefert, wenn ihr Gewinn > 0 ist und die
   untere Bootstrap-Grenze ≥ 0 (Regel 3.5). Sonst `source = climatology`.
3. **Kennzeichnung:** `model_version` je Zeile zeigt, welche Stufe ausgeliefert wurde.

### 4.3 Ergebnisse im Test

Test: 2022-01-01 bis 2026-07-31. Die Werte in Klammern sind das 90-%-Intervall über Jahre. Das Wetter ist das
**analysierte Wetter** des Zieltags, also eine Obergrenze.

**Großfeuer-Tag (`big_fire_day`):**

| Vorlauf | Gewinn ohne Wetter | Gewinn mit Wetter | AUC ohne / mit | PR-AUC mit | ECE mit | Steigung mit |
|---|---|---|---|---|---|---|
| 1 | 0,213 | **0,269** (0,244–0,291) | 0,92 / 0,94 | 0,52 | 0,003 | 1,03 |
| 2 | 0,119 | 0,206 (0,178–0,238) | 0,89 / 0,93 | 0,45 | 0,004 | 1,05 |
| 3 | 0,081 | 0,181 (0,157–0,210) | 0,88 / 0,93 | 0,42 | 0,005 | 1,04 |
| 5 | 0,042 | **0,158** (0,136–0,184) | 0,86 / 0,92 | 0,38 | 0,005 | 0,99 |
| 7 | 0,025 | 0,143 (0,121–0,166) | 0,86 / 0,92 | 0,36 | 0,005 | 0,97 |
| 10 | 0,011 | 0,134 (0,113–0,156) | 0,85 / 0,91 | 0,35 | 0,005 | 0,95 |

Die Saisonkurve allein hat AUC 0,83.

**Feuertag (`fire_day`, SNPP):**

| Vorlauf | Gewinn ohne Wetter | Gewinn mit Wetter |
|---|---|---|
| 1 | 0,130 | 0,196 |
| 5 | 0,042 | 0,164 |
| 10 | 0,027 | 0,157 |

ECE ≤ 0,021.

**Was das heißt:**

- An Tag 1 hilft das Wetter wenig, weil laufende Feuer den größten Teil erklären. An Tag 5 vervierfacht es den Gewinn fast,
  an Tag 10 verzwölffacht es ihn. Der Gewinn fällt mit dem Vorlauf kaum noch ab, weil das Wetter des Zieltags im Test
  perfekt bekannt ist. **Mit einer echten Vorhersage wird es fallen.** Schritt 5 misst, wie stark.
- Kalibrierung: ECE ≤ 0,005 und Steigung 0,95–1,05 bei allen Vorläufen. Damit ist KPI B6 jetzt auch an den Tagen 8–9
  bestanden, die in Schritt 1 knapp verfehlt waren.
- **Leave-one-year-out (Tag 1):** Die Stufe mit Wetter gewinnt in allen 15 Jahren (0,13–0,33) und ist in jedem Jahr
  besser als die Stufe ohne Wetter.
- **Warnschwelle „oberste 10 %“, Tag 1:** Das Modell findet 79 % der Großfeuer-Tage, ohne Wetter waren es 71 %.
  78 % der Warnungen sind Fehlalarme. Das ist bei 2,9 % Ereignissen zu erwarten.

**Risikoklassen mit Wetter im Test:** Zuerst der Anteil der Region-Tage in der Klasse, dahinter, an wie vielen
davon ein Großfeuer-Tag folgte.

| Klasse | Tag 1 | Tag 5 | Tag 10 |
|---|---|---|---|
| `low` | 42 %, 0,8 % | 44 %, 0,9 % | 46 %, 0,9 % |
| `normal` | 49 %, 1,2 % | 46 %, 1,7 % | 44 %, 1,9 % |
| `elevated` | 3,2 %, 9,6 % | 4,2 %, 10 % | 4,5 %, 11 % |
| `high` | 3,1 %, 19 % | 3,9 %, 21 % | 4,0 %, 20 % |
| `very_high` | 2,2 %, 46 % | 1,5 %, 27 % | 1,4 %, 23 % |

Die Klassen sind auch an Tag 10 sauber gestaffelt, von `low` mit 0,9 % bis `very_high` mit 23 %.

### 4.4 Wochenausblick (Wochen 2–4)

Hier kommen dazu: DC, DMC, `dc_anom`, Dürreindex und `rain90_anom` am Ausgabetag. Das ist die langsame Trockenheit,
die zum Ausgabetag schon bekannt ist. Eine Wettervorhersage für die Wochen 2–4 gibt es nicht.

| Woche | RPSS ohne Wetter | RPSS mit Wetter |
|---|---|---|
| 2 | 0,020 | 0,018 |
| 3 | 0,009 | 0,008 |
| 4 | 0,002 | 0,001 |

Das Wetter bringt hier nichts. Die Trockenheit steckt offenbar schon in der Feueraktivität der letzten 30 Tage, die
das Modell ohnehin kennt. Der Wochenausblick bleibt deshalb bei der Stufe ohne Wetter.

D3 (ECE von `p_above` ≤ 0,05) bleibt verfehlt: 0,059 ohne Wetter, 0,052–0,055 mit Wetter. Die Klimatologie selbst
liegt bei 0,067. Ursache ist die Drift der Wochensumme durch die Zahl der VIIRS-Satelliten (Team-Entscheidung zum
Wochenziel, README 1.5).

---

## 5. KPIs

Die Werte stehen in `data/forecast/forecast_kpi_report.json`. B- und C-KPIs beziehen sich auf die bessere Stufe, also
auf die mit Wetter, und zwar mit analysiertem Wetter.

| KPI | Wert | Schwelle | Ergebnis |
|---|---|---|---|
| A1–A4 | wie Schritt 1, A2 jetzt auch für das Wetter | | bestanden |
| A5 Wetter vollständig | 100 % / 100 % | 99,5 % / 95 % | bestanden |
| A6 Wetter plausibel | 0 Verstöße | 0 | bestanden |
| A7 FWI gegen die Testtabelle | 0,005 | < 0,1 | bestanden |
| A8 Determinismus | zwei Läufe nacheinander, identische Hashes aller Ausgaben | gleiche Hashes | bestanden |
| B1 Gewinn Tag 1 | 0,269 | ≥ 0,10 | bestanden |
| B2 Gewinn Tag 3 | 0,181 | ≥ 0,05 | bestanden |
| B3 Wetter hilft, Tage 2–7 (Ziel auch 8–10) | +0,06 (Tag 1) bis +0,12 (Tag 8–10), an jedem Vorlauf | > 0 | bestanden, auch das Ziel 8–10 |
| B4 Gewinn mit Wetter, Tag 5 | 0,158, untere Grenze 0,136 | > 0 und ≥ 0 (Ziel 0,05) | bestanden, Ziel erreicht |
| B5 AUC | 0,94, jeder Vorlauf > Saisonkurve | ≥ 0,87 | bestanden |
| B6 Kalibrierung | ECE ≤ 0,005, Steigung 0,95–1,05 | ≤ 0,015, 0,8–1,2 | bestanden |
| B8 Rückfall greift | 0 Verstöße | 0 | bestanden |
| C1 / C2 Feuertag | 0,196 / ECE 0,021 | > 0 / ≤ 0,03 | bestanden |
| D1 / D2 Woche | RPSS 0,020 / Summen = 1 | > 0 | bestanden |
| **D3 Woche, Kalibrierung** | 0,059 | ≤ 0,05 | **verfehlt** (wie in Schritt 1) |
| E1 Leave-one-year-out | 15 von 15 Jahren | ≥ 80 % | bestanden |
| F1–F7 | Ausgabe, 36 Tests; Laufzeit `train` 9,9 min auf 1 Kern, `predict` 8 s | ≤ 10 min / ≤ 1 min | bestanden |

---

## 6. Grenzen und offene Punkte

1. **Obergrenze statt echter Vorhersagegüte.** Die Gewinne mit Wetter gelten für *perfektes* Wetter am Zieltag.
   Schritt 5 prüft das:
   - Gibt es bei Meteomatics archivierte Vorhersagen? Dann werden diese ausgewertet.
   - Sonst wird das Wetter je Vorlauf verrauscht.

   Erst dann ist `skill_basis` der Stufe mit Wetter mehr als `analysis`.
2. **Live-Vorhersage:** seit Schritt 6 (Abschnitt 7) mit Wetter. Der Meteomatics-Account läuft am **22.11.2026** ab.
   Bis dahin muss die Vorhersage täglich neu geholt werden (etwa 16 Anfragen). Danach gibt es nur noch die Stufe ohne
   Wetter, außer das Team besorgt eine andere Wetterquelle.
3. **Training mit ERA5, Vorhersage mit IFS.** Beide stammen von ECMWF, aber kleine systematische Unterschiede sind
   möglich, z. B. regnet IFS an einem Punkt in Galicien an den Tagen 09.–13.11. deutlich mehr als `mix`. Das prüft Schritt 5 bzw. 6 mit.
4. **Die Gruppe `fire` kommt aus `mix`.** Fosberg, Waldbrandwarnung und Dürreindex zeigen keine Sprünge. Wie
   Meteomatics sie berechnet, ist aber nicht offengelegt. Sie tragen zum Modell nur wenig bei, weil das eigene FWI
   besser trennt.
5. **Feiertage fehlen** (siehe 4.1).
6. **Team-Entscheidungen aus Schritt 1** bleiben offen: das Wochenziel und die Grenzen der Risikoklassen.

---

## 7. Schritt 6: Live-Vorhersage mit Wetter (14./15.11.2026)

### 7.1 Ablauf

```bash
.venv/bin/python fetch_weather.py recent --start 2026-11-09 --end 2026-11-14 --group core   # IFS, 4 Anfragen
.venv/bin/python fetch_weather.py recent --start 2026-11-14 --end 2026-11-14 --group fire   # mix, 4 Anfragen
.venv/bin/python fetch_weather.py forecast                                                  # 14.-24.11., 8 Anfragen
.venv/bin/python run_forecast.py predict                                                    # 5 s, 1 Kern, 1,1 GB
```

Der Ausgabetag ist der 13.11., der letzte Tag in `data/harmonised/`. Die Zieltage sind also der 14.–23.11.
`recent` schließt die Lücke zwischen dem Ende der Historie und dem Start der Vorhersage. Beim nächsten Lauf mit
neueren Feuerdaten verschiebt sich das entsprechend.

### 7.2 Passt IFS zu ERA5?

Trainiert wurde mit ERA5, vorhergesagt wird mit IFS. Verglichen habe ich beide an den 182 Punkten für die Tage
01.10.–08.11.2026 (7098 Punkt-Tage, 4 Anfragen, nur zur Prüfung, nicht gespeichert):

| Größe | Mittel IFS | Mittel ERA5 | Abweichung | mittlerer Fehler | Korrelation |
|---|---|---|---|---|---|
| Temperatur 12 UTC | 18,7 °C | 18,9 °C | −0,3 °C | 1,0 °C | 0,97 |
| Luftfeuchte | 56,0 % | 58,0 % | −2,0 % | 6,1 % | 0,88 |
| Wind | 9,1 km/h | 8,4 km/h | +0,8 km/h | 2,6 km/h | 0,80 |
| Niederschlag | 2,0 mm | 1,7 mm | +0,25 mm | 1,1 mm | 0,80 |
| Taupunkt | 9,1 °C | 10,0 °C | −0,9 °C | 1,3 °C | 0,97 |
| Regentage ≥ 1 mm | 25 % | 23 % | | | |

IFS ist etwas trockener und windiger als ERA5. Der FWI fällt damit eher etwas zu hoch aus. Das ist klein, wird
aber nicht korrigiert, und Schritt 5 sollte es mitbewerten.

### 7.3 Ergebnis

- An allen 10 Vorläufen wird die Stufe mit Wetter ausgeliefert (`model_version 0.2-weather`). Der Wochenausblick
  bleibt ohne Wetter.
- Mitte November ist es in Iberien nass. Das Modell sieht die Gefahr deshalb meist **unter** der Saison: 135 Region-Tage
  `low`, 94 `normal`, einer `high`. Im Mittel liegt `p_big_fire_day` bei 0,1 %, die Saisonkurve bei 0,7 %.
- **Der eine `high`: Katalonien (ES51) am 19.11.**, `p_big_fire_day` 2,5 % (Spanne 1,1–4,2 %) gegenüber 0,5 % in
  der Saison.
  - **Wetter:** Am 19. und 20.11. ist es dort trocken und windig, mit Luftfeuchte 45 %, Böen 48 km/h, FFMC 87,
    FWI 10 und Fosberg 24. Das ist der gefährlichste Abschnitt der zehn Tage.
  - **Saisonkurve:** Ein Teil des Signals kommt aus ihr. In den Trainingsjahren gab es im Spätherbst in ES51 nur zwei
    Großfeuer-Tage, am 12.11.2013 und am 07.11.2021. Wegen des Fensters von ±7 Tagen wirkt das Feuer von 2013 genau
    bis zum 19.11. Ab dem 20.11. sinkt die Saisonkurve auf das Minimum von 0,01 %, und damit sinkt auch die
    Vorhersage (0,12 % am 20.11. bei ähnlichem Wetter).
  - **Offener Punkt:** In Monaten mit sehr wenigen Ereignissen sollte die Saisonkurve weicher werden, z. B. mit
    einem gleitenden Gewicht statt einer harten Fenstergrenze und einem Zug zum Mittel der Region bzw. des Monats.
    Das ändert das Modell und braucht ein neues `train` samt Auswertung.

## 8. Ausführen

```bash
cd La-Brasa/forecast
.venv/bin/python -m pytest -q                       # 36 Tests, ohne Internet
.venv/bin/python fetch_weather.py history --start 2012-01-20 --end 2026-11-08 --group core   # ERA5, 60 Anfragen
.venv/bin/python fetch_weather.py recent --start 2026-11-09 --end 2026-11-13 --group core    # IFS, 4 Anfragen
.venv/bin/python run_forecast.py weather-qc         # Schritt 2: A5/A6 -> data/forecast/weather_qc.json
.venv/bin/python run_forecast.py train              # Schritte 2-4: Auswertung beider Stufen, Modelle -> bundle.pkl (~11 min)
.venv/bin/python run_forecast.py predict            # tägliche Vorhersage ohne Training (~8 s, 1 Kern, 0,9 GB)
.venv/bin/python run_forecast.py train --no-weather # nur die Stufe ohne Wetter
```
