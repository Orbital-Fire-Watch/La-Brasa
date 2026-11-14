# data_analysis: Harmonisierung MODIS / VIIRS

Analyse der FIRMS-Hotspots als Grundlage fuer die Harmonisierung. Noch keine Pipeline.

- Ergebnis: `../docs/harmonisierung_bericht.html` (im Browser oeffnen)
- Skripte `00_` bis `08_` laufen in dieser Reihenfolge, jedes schreibt nach `results/*.json`
- `build_report.py` + `report_text.py` bauen den Bericht nur aus diesen JSON-Dateien
- `cache/` (Parquet, 1,3 GB) und `.venv/` sind neu erzeugbar und nicht fuer Git gedacht
- die NUTS-2-Grenzen 2021 (Eurostat GISCO) liegen in `../geo/`, die Iberien-CSVs in `../../data/raw/`

Einrichten:

    python3 -m venv .venv
    .venv/bin/pip install numpy pandas scipy duckdb pyarrow shapely scikit-learn statsmodels matplotlib
    .venv/bin/python 00_prepare.py   # danach 01 ... 08, zuletzt build_report.py
