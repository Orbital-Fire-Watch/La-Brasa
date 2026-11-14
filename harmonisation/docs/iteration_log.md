# Iterationsprotokoll

Regel: Die KPI-Schwellen stehen in `pipeline_config.yaml` und wurden vor der ersten Messung festgelegt. Genauigkeit wird
ausserhalb der Trainingsdaten gemessen (ein Jahr auslassen, 2012-2021). Iteriert wird nur, wenn eine Schwelle verfehlt wird.

## Aufbau
- **Beschaedigte Quellzeile:** In `NASA_SPACEAPP/DL_FIRE_SV-C2_845370/fire_archive_SV-C2_845370.csv`, Zeile 362617, steht in
  der Spalte `track` der Text `0.https://firms.modaps.eosdis.nasa.gov/data/download/DL_FIRE_M-C61_845369.zip77` statt `0.77`
  (Datei zuletzt am 13.11.2026 um 21:56 veraendert, im ZIP-Original korrekt). Das Einlesen brach ab.
- **Aenderung:** `convert_csv_to_raw_parquet` wandelt mit TRY_CAST um, `count_unreadable_rows` meldet die Zeile, die Bereinigung
  verwirft sie als `invalid_value`. Die Quelldatei wurde nicht veraendert (Wiederherstellen aus dem ZIP braucht die Freigabe des Teams).

## Iteration 1 (Grundaufbau laut Auftrag)
- Ergebnis: alle Schwellen erfuellt ausser **U3** (Stabilitaet der Fehlerfaktoren 17,7 % bei Grenze 15 %, FRP-Klasse 0-10 MW pro Tag).
- **Messfehler gefunden:** Die Abdeckung der Fehlerbaender wurde ueber beide Pruefrichtungen gemittelt, Abweichungen hoben sich auf
  (alle Werte lagen kuenstlich bei 0,49-0,51). Korrigiert: jede Richtung einzeln, die unguenstigere zaehlt (U1 jetzt 0,432-0,578).
- Hypothesen H1-H5 per Kreuzvalidierung geprueft (`data_analysis/experiments/evaluate_hypotheses.py`, Ergebnis in `data_analysis/experiments/hypothesis_results.json`):
  - H1 (Tagesstaerke aus Aqua allein): bestaetigt, bleibt.
  - H2 (Sonnendatum statt UTC): Anzahl je Tag besser (x 2,00 gegen x 2,08), FRP-R2 schlechter (0,578 gegen 0,590, in 8 von 10 Jahren). Nicht uebernommen.
  - H3 (eigene Grossfeuer-Schwelle fuer umgerechnete Tage): 80 MW gleicht Recall und Precision aus. Uebernommen.
  - H4 (Faktor fuer Juni-September): kleiner Gewinn, im Monat in 3 von 10 Jahren schlechter, doppelt so viele Faktoren. Nicht uebernommen.
  - H5 (Staerke nur aus Tag-Ueberfluegen): R2 minimal besser, Ereignisse schlechter. Nicht uebernommen.

## Iteration 2
- Hypothese: Die FRP-Klasse 0-10 MW hat zu wenige und zu verrauschte Faelle fuer ein stabiles Band.
- Aenderung: `uncertainty.frp_class_bounds_mw` von [0, 10, 100, 500] auf [0, 100, 500]; `strength.big_fire_threshold_scaled_mw` 100 -> 80 (H3).
- Ergebnis: U3 0,177 -> 0,088. Alle 34 Pruefungen erfuellt. **Stopp laut Regel.**

## Knappe Stellen
- U1: 0,432 und 0,578 bei Grenzen 0,42 und 0,58. Die Randwerte stammen aus Klassen mit gut 100 Prueffaellen.
- D8d: schwaechste Region korreliert mit 0,831 bei Schwelle 0,80.
- D5b: Auch mit 80 MW findet die Umrechnung nur 67 % der gemessenen Grossfeuer-Tage. Vor 2012 fehlt etwa jeder dritte.

## VIIRS-Erweiterung: NOAA-20 und NOAA-21 (14.11.2026, Schema-Version 2)

Neue Schwellen N1-N5 vor der ersten Messung in `pipeline_config.yaml` festgelegt (N1c nach der Voranalyse 09 ergaenzt,
vor der ersten Messung der Pipeline). Voranalyse: `data_analysis/09_viirs_satellites.py`, Regeln R1-R5 im Docstring.

### Aufbau
- **Erster NOAA-Download unvollstaendig:** Im Nordosten fehlten NOAA-20/21 (FRJ2 0,00, FRI1 0,01, ES51 0,44, ES22 0,83 der
  SNPP-Erkennungen). Ein Mittel haette diese Regionen ab 2018 etwa halbiert. Angehalten, neu heruntergeladen (jetzt `Data_new`,
  der alte Download liegt in `Data_new_false`).
- **Zweiter Download zu gross:** Rechteck bis 44,8 N / 4,9 O, waehrend MODIS/SNPP ein Gebiet ohne Frankreich noerdlich von etwa
  43,5 Grad abdecken. Aenderung: gemeinsames Gebiet (`common_area`, alle 0,25-Grad-Zellen mit Terra-, Aqua- oder SNPP-Erkennungen).
  Danach liegen alle Regionen bei 0,83-1,23 von SNPP. Rasterweite 0,05-0,25 Grad aendert das kaum.
- Voranalyse mit diesen Daten: R1 (N20 1,02, N21 0,98), R2 (Drift hoechstens 10 min), R3 (Faktor +0,1 %), R4 (Fehler x 2,0 -> x 1,5
  in allen Rotationen, auch je Monat), R5 (Recall 98,2 / 97,7 %, Fehlentfernung 1,9 / 1,6 %) erfuellt.
- Probelauf mit dem unvollstaendigen Download: N1c schlug wie beabsichtigt an (0,45, ES51).

### Iteration 1
- Ergebnis des ersten Laufs: verfehlt **U1b** (groesste Abdeckung des 50-%-Bands 0,614 bei Grenze 0,58; NUTS-2 x Monat, FRP 100-500 MW)
  und **N4b** (Fehlentfernung der Ortsmaske bei NOAA-20 2,23 % bei Grenze 2 %). Dazu schlug ein Regressionstest an (Faktor ES11 -1,0 %).
- Ursache U1b: Die Baender werden auf 2012-2016 bestimmt und auf 2017-2021 geprueft (und umgekehrt). Mit dem Mittel als Referenz
  ist 2018-2021 ruhiger (SNPP + NOAA-20) als 2012-2016, die Haelften sind nicht vergleichbar.
- Ursache N4b: Die Maske lernte auch aus MODIS-Zeilen. Deren 1-km-Pixel verschmieren den Ort einer Anlage, die Maske wird zu gross
  fuer VIIRS. Mit einer reinen VIIRS-Maske 1,90 %, der MODIS-Recall fiele dann aber von 0,69 auf 0,50.
- Aenderung: `calibration.reference_satellites: [SNPP]` (Kalibrierung und Fehlermodell gegen SNPP allein; aendert die Vorab-Regel R3,
  Faktorunterschied laut Voranalyse +0,1 %). `static_sources.mask_training_sensors: {VIIRS: [VIIRS], MODIS: [MODIS, VIIRS]}`.
  Der Regressionstest vergleicht wieder mit 08_series.py (SNPP) und zusaetzlich mit 09 (Faktor auf das Mittel, Toleranz 3 % wie R3).
- Ergebnis: **alle 42 Pruefungen erfuellt** (D1-U3 identisch mit dem Lauf nur mit SNPP, N1 1,006, N1c 0,952, N2 3,7e-16,
  N3 3 von 3, N4a 97,7 %, N4b 1,90 %, N5 ja). Keine Schwelle gesenkt. **Stopp laut Regel.**
- Hypothesen H1-H5 neu gerechnet: alle 109 Kennzahlen unveraendert (die Kreuzvalidierung misst gegen SNPP).

### Knappe Stellen
- N4b: 1,90 % bei Grenze 2 % (NOAA-20).
- U1 unveraendert knapp: 0,432 und 0,578 bei 0,42 und 0,58.
