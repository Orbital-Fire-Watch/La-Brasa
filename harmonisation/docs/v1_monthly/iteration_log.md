# Iterationsprotokoll

Regel: Die KPI-Schwellen stehen in `pipeline_config.yaml` und wurden vor der ersten Messung festgelegt.
Bewertet wird ausserhalb der Trainingsdaten (ein Jahr auslassen, 2012-2021). Iteriert wird nur, wenn eine Schwelle verfehlt wird.

## Aufbau (vor der ersten KPI-Messung)

- **Fehler gefunden:** Der angebrochene letzte Monat (November 2026) galt als vollstaendig, weil das Ende eines
  Zeitschritts als "letzter Tag mit Daten" berechnet wurde.
- **Aenderung:** `list_periods` nutzt das kalendarische Ende des Zeitschritts (`period_end_of`).
- **Absicherung:** Test `test_incomplete_last_month_has_no_value`.
- Die KPIs waren zu diesem Zeitpunkt noch nicht gemessen.

## Iteration 1: Regionsfaktor mit Rueckfall auf den Gesamtfaktor

- **Hypothese:** Der Weg aus der Voranalyse (ein Faktor je Region, Kalibrierfenster 02/2012-12/2021) erfuellt die Schwellen.
- **Ergebnis:** Alle KPIs erfuellt (Werte in `data/harmonised/kpi_report.json` und in `pipeline_overview.html`).
- **Entscheidung:** Stopp nach Iteration 1 (Stoppregel: alle KPIs erfuellt).

Nicht getestet, weil keine Schwelle verfehlt wurde: Shrinkage der Regionsfaktoren, Extrapolation der
Groessenverteilung (abgeschnittenes Potenzgesetz), Faktoren je Tag/Nacht.

## Knappe Stellen (erfuellt, aber mit wenig Abstand)

- **K4b Kappa:** 0,44 bei Schwelle 0,40. Ueber alle 23 Regionen statt der 18 Bewertungsregionen waeren es 0,40.
- **K9 Ortsmaske:** Recall gesamt 92,6 %. Bei MODIS allein nur 71 % (groessere Pixel), bei VIIRS 94,5 %.
- **K10 FRP:** Die Streuung des Jahresverhaeltnisses ist 17 %. Einzelne Jahre weichen bis 30 % ab (Spanne 0,74 bis 1,30).
