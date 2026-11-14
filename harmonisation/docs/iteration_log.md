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
