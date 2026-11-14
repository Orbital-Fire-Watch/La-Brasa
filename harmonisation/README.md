# harmonisation

Taegliche Harmonisierung der FIRMS-Hotspots (MODIS Terra/Aqua -> VIIRS) fuer Iberien, mit Punktgewichten, Fehlermodell
und einem getrennten Aggregationsmodul. Die VIIRS-Referenz ist seit Schema-Version 2 das Mittel aus SNPP, NOAA-20 und NOAA-21.
Datengrundlage fuer ein spaeteres Frontend (Karte, Kalender).

- Aufbau, Funktionen, KPIs: `docs/pipeline_overview.html`
- Alle Spalten und ihre Nutzung im Frontend: `docs/column_guide.html` (und `docs/data_dictionary.md`)
- Iterationen und Hypothesen: `docs/iteration_log.md`, `data_analysis/experiments/hypothesis_results.json`
- NOAA-20/21-Erweiterung: `docs/viirs_extension.md` (kurz) und `docs/viirs_extension.html` (Entstehung mit Zahlen)
- Rohdaten, Herkunft, Pruefsummen: `docs/raw_sources.md`
- Fachliche Begruendung: `docs/harmonisierung_bericht.html`

## Ausfuehren

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python run_pipeline.py              # alle Stufen, Unveraendertes wird uebersprungen
    .venv/bin/python run_pipeline.py --force      # alles neu, prueft den Determinismus
    .venv/bin/python -m pytest -q tests aggregation/tests
    .venv/bin/python data_analysis/experiments/evaluate_hypotheses.py
    .venv/bin/python docs/build_docs.py

Rueckgabewert 1, wenn eine KPI-Schwelle verfehlt wird.

## Aufbau

    run_pipeline.py          Orchestrator: ingest, clean, daily_grid, calibrate, quantify_uncertainty,
                             harmonise_daily, weight_hotspots, test, validate
    pipeline_config.yaml     alle Parameter, Schwellen und KPI-Grenzen
    pipeline/data_loading/   Einlesen, Bereinigen, Region und Untersuchungsgebiet, Ortsmaske, Klassen, abgeleitete Spalten (inkl. H3)
    pipeline/algorithms/     Tagesraster (VIIRS-Mittel), Kalibrierung, Harmonisierung, Gewichte, Fehlermodell, KPIs (viirs_kpis.py: N1-N4), Drift
    pipeline/column_catalogue.py   eine Quelle fuer Schema und Dokumentation
    aggregation/             Roll-up, Unsicherheit, Flaechenabfragen, Klimaprofil, laufender Monat (nicht im Orchestrator)
    ../data/raw/<produkt>/   FIRMS-CSVs, ein Ordner je Produkt: modis, viirs_snpp, viirs_noaa20, viirs_noaa21
    ../data/processed, harmonised   gemeinsamer Datenordner des Repositorys (nicht in Git)
    ../data/harmonised/csv/  CSV-Kopien aller Ausgabetabellen, nur zum Ansehen (Stufe export_csv, bei jedem Lauf neu).
                             Das Produkt nutzt sie nicht: Postgres wird aus den Parquet-Dateien geladen.
    tests/, aggregation/tests/, data_analysis/experiments/, docs/

Herkunft: `config.py`, `io_utils.py`, `ingest_csv_to_parquet.py`, `static_source_mask.py`, `assign_region.py`,
`classify_hotspots.py`, `drift_monitor.py` und Teile von `clean_hotspots.py` sind aus `../harmonisation_pipeline` (Version 1)
kopiert und angepasst. Es gibt keine Importe aus Version 1. `../data/processed` und `../data/harmonised` sind neu erzeugbar und nicht fuer Git gedacht.
