"""Baut docs/viirs_extension.html: wie NOAA-20 und NOAA-21 in die Harmonisierung kamen (Analyse, Entscheidungen, Pruefung).

Aufruf: .venv/bin/python docs/build_viirs_extension.py
Liest nur Ergebnisse: data_analysis/results/viirs_satellites.json (Voranalyse 09), data/harmonised/kpi_report.json,
pipeline_state.json, activity_daily_harmonised.parquet und day_status.parquet. Die Seite ist eigenstaendig
(Diagramme als Inline-SVG, Schriften mit Ersatz aus dem System), hell und dunkel, und passt auf ein Handy.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "docs"))

from build_docs import de, format_kpi_value, pct, table  # noqa: E402
from pipeline.config import load_config, path_of  # noqa: E402
from pipeline.io_utils import read_json, read_parquet  # noqa: E402

import doc_text as text  # noqa: E402

SERIES_COLORS = {"N20": "var(--accent)", "N21": "#b7791f", "mean": "var(--ink)"}
EXTRA_STYLE = """<style>
figure{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
figure svg{width:100%;height:auto;max-width:100%;display:block}
figcaption{font-size:.86rem;color:var(--ink2)}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.82rem;color:var(--ink2)}
.legend span::before{content:"";display:inline-block;width:14px;height:3px;margin-right:6px;vertical-align:middle;background:var(--c)}
.chart text{fill:var(--ink2);font:11px var(--body)}
.chart .grid{stroke:var(--line)} .chart .band{fill:var(--wash)}
.steps{counter-reset:s;list-style:none;padding:0}
.steps li{counter-increment:s;padding-left:2.1em;position:relative}
.steps li::before{content:counter(s);position:absolute;left:0;top:0;width:1.5em;height:1.5em;border-radius:50%;background:var(--wash);
  color:var(--accent);font:600 .8rem/1.5em var(--display);text-align:center}
</style>
"""


def line_chart(series: dict[str, list[tuple[int, float]]], y_range: tuple[float, float], band: tuple[float, float], label_of: dict[str, str]) -> str:
    """Liniendiagramm Jahr x Verhaeltnis mit Toleranzband und Bezugslinie 1, Beschriftung am Linienende."""
    width, height, left, right, top, bottom = 640, 260, 44, 110, 12, 28
    years = sorted({year for points in series.values() for year, _ in points})
    sx = lambda year: left + (year - years[0]) / max(years[-1] - years[0], 1) * (width - left - right)
    sy = lambda value: top + (y_range[1] - value) / (y_range[1] - y_range[0]) * (height - top - bottom)
    parts = [f'<rect class="band" x="{left}" y="{sy(band[1]):.1f}" width="{width - left - right}" height="{sy(band[0]) - sy(band[1]):.1f}"/>']
    for tick in [round(y_range[0] + i * 0.1, 2) for i in range(int(round((y_range[1] - y_range[0]) / 0.1)) + 1)]:
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{sy(tick):.1f}" y2="{sy(tick):.1f}" stroke-width="{1.4 if tick == 1 else 0.6}"/>'
                     f'<text x="{left - 6}" y="{sy(tick) + 4:.1f}" text-anchor="end">{de(tick, 1)}</text>')
    for year in years:
        parts.append(f'<text x="{sx(year):.1f}" y="{height - 8}" text-anchor="middle">{year}</text>')
    label_y, previous = {}, None
    for name in sorted(series, key=lambda key: sy(series[key][-1][1])):      # von oben nach unten, mindestens 14 px Abstand
        wanted = sy(series[name][-1][1]) + 4
        label_y[name] = wanted if previous is None else max(wanted, previous + 14)
        previous = label_y[name]
    for name, points in series.items():
        path = " ".join(f"{'M' if i == 0 else 'L'}{sx(y):.1f},{sy(v):.1f}" for i, (y, v) in enumerate(points))
        dots = "".join(f'<circle cx="{sx(y):.1f}" cy="{sy(v):.1f}" r="3.2" fill="{SERIES_COLORS[name]}"/>' for y, v in points)
        parts.append(f'<path d="{path}" fill="none" stroke="{SERIES_COLORS[name]}" stroke-width="2"/>{dots}'
                     f'<text x="{sx(points[-1][0]) + 8:.1f}" y="{label_y[name]:.1f}" style="fill:{SERIES_COLORS[name]};font-weight:600">{label_of[name]}</text>')
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Verhältnis zu SNPP je Jahr">{"".join(parts)}</svg>'


def bar_chart(rows: list[tuple[str, float, float]], max_value: float) -> str:
    """Horizontale Paare: typischer Fehler eines einzelnen Satelliten gegen das Mittel, je zurueckgehaltenem Satelliten."""
    width, row_h, left, right = 640, 46, 150, 60
    height = len(rows) * row_h + 10
    scale = lambda value: (value - 1) / (max_value - 1) * (width - left - right)
    parts = []
    for index, (label, single, mean) in enumerate(rows):
        y = 6 + index * row_h
        parts.append(f'<text x="{left - 8}" y="{y + 22}" text-anchor="end">{html.escape(label)}</text>')
        for offset, value, color, name in ((0, single, "var(--muted)", "einzeln"), (18, mean, "var(--accent)", "Mittel")):
            parts.append(f'<rect x="{left}" y="{y + offset}" width="{max(scale(value), 2):.1f}" height="14" rx="2" fill="{color}"/>'
                         f'<text x="{left + scale(value) + 6:.1f}" y="{y + offset + 11}">× {de(value)} {name}</text>')
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Fehler einzeln gegen Mittel">{"".join(parts)}</svg>'


def yearly_level(daily: pd.DataFrame) -> list[tuple[int, float]]:
    """Summe n_viirs / Summe n_snpp je Jahr an Tagen, an denen SNPP und mindestens ein NOAA-Satellit liefern."""
    rows = daily[daily["n_snpp"].notna() & daily[["n_noaa20", "n_noaa21"]].notna().any(axis=1)]
    sums = rows.assign(year=pd.to_datetime(rows["date"]).dt.year).groupby("year")[["n_viirs", "n_snpp"]].sum()
    return [(int(year), float(row.n_viirs / row.n_snpp)) for year, row in sums.iterrows()]


def analysis_rules(result: dict[str, Any]) -> str:
    """Tabelle der vorab festgelegten Regeln R1 bis R5 mit Messwert und Entscheidung."""
    ratios, noise, cal, mask = result["ratios"], result["noise"], result["calibration"], result["static"]["mask_holdout"]
    day = [row for row in noise["rows"] if row["grain"] == "day"]
    drift = max(abs(row["deviation_minutes"]) for row in result["overpass"]["rows"] if row["daynight"] == "D")
    ok = lambda flag: '<span class="ok">erfüllt</span>' if flag else '<span class="fail">verfehlt</span>'
    rows = [
        ["R1", "Median NOAA / SNPP je Region und Jahr in 0,85–1,15", f"N20 {de(ratios['N20']['count_median'], 3)}, N21 {de(ratios['N21']['count_median'], 3)} "
         f"(FRP {de(ratios['N20']['frp_median'], 2)} / {de(ratios['N21']['frp_median'], 2)})", ok(result["decision"]["r1"])],
        ["R2", "Überflugzeit am Tag driftet höchstens 15 min", f"größte Abweichung {de(drift, 0)} min", ok(result["decision"]["r2"])],
        ["R3", "Faktor auf das Mittel weicht höchstens 3 % von SNPP ab", f"{pct(cal['relative_shift'], 1)} ({de(cal['k_pair_overall_snpp'], 3)} → {de(cal['k_pair_overall_mean'], 3)})", ok(result["decision"]["r3"])],
        ["R4", "Mittel trifft den zurückgehaltenen Satelliten besser (alle 3 Rotationen, Tag)",
         f"× {de(day[0]['error_mean'], 2)} statt × {de(min(v for k, v in day[0].items() if k.startswith('error_') and k != 'error_mean'), 2)}, {noise['day_rotations_won']} von 3", ok(result["decision"]["r4"])],
        ["R5", "Ortsmaske je NOAA-Satellit: Recall ≥ 90 %, Fehlentfernung ≤ 2 %",
         f"N20 {pct(mask['N20']['recall'])} / {pct(mask['N20']['false_removal'], 2)}, N21 {pct(mask['N21']['recall'])} / {pct(mask['N21']['false_removal'], 2)}", ok(result["decision"]["r5"])],
    ]
    return table(["#", "Regel (vor der Messung festgelegt)", "gemessen", "Stand"], rows, "wide")


def region_table(result: dict[str, Any]) -> str:
    """Verhaeltnis NOAA / SNPP je Region (Anzahl, alle gemeinsamen Jahre)."""
    n20 = {row["region_id"]: row["count_ratio"] for row in result["ratios"]["N20"]["by_region"]}
    n21 = {row["region_id"]: row["count_ratio"] for row in result["ratios"]["N21"]["by_region"]}
    rows = [[f"<code>{region}</code>", de(n20[region]), de(n21[region]) if region in n21 else "–"] for region in sorted(n20, key=n20.get)]
    return table(["Region", "NOAA-20 / SNPP", "NOAA-21 / SNPP"], rows, "num")


def kpi_rows(report: dict[str, Any]) -> str:
    """Die neuen Pruefungen N1 bis N5 als Tabelle."""
    rows = []
    for kpi in report["kpis"]:
        if kpi["id"].startswith("N"):
            rule = {"<=": "höchstens ", ">=": "mindestens ", "==": ""}[kpi["rule"]]
            status = '<span class="ok">erfüllt</span>' if kpi["passed"] else '<span class="fail">verfehlt</span>'
            rows.append([kpi["id"], html.escape(text.KPI_NAMES.get(kpi["name"], kpi["name"])), rule + format_kpi_value(kpi["id"], kpi["threshold"]),
                         format_kpi_value(kpi["id"], kpi["value"]), status])
    return table(["#", "Kennzahl", "Schwelle", "gemessen", "Stand"], rows, "num kpi")


def collect(config: dict[str, Any]) -> dict[str, Any]:
    """Alle Eingaben der Seite."""
    daily = read_parquet(path_of(config, "harmonised", "activity_daily_harmonised.parquet"))
    status = read_parquet(path_of(config, "harmonised", "day_status.parquet"))
    return {"result": read_json(PROJECT_ROOT / "data_analysis" / "results" / "viirs_satellites.json"),
            "report": read_json(path_of(config, "harmonised", "kpi_report.json")),
            "state": read_json(path_of(config, "harmonised", "pipeline_state.json")), "daily": daily, "status": status}


def build_body(data: dict[str, Any], config: dict[str, Any]) -> str:
    """Setzt die Seite zusammen."""
    result, report, state, daily, status = data["result"], data["report"], data["state"], data["daily"], data["status"]
    level, noise, balance = report["measured"]["viirs"]["level"], report["measured"]["viirs"]["noise"], state["clean"]["report"]
    by_year = {sat: [(row["year"], row["count_ratio"]) for row in result["ratios"][sat]["by_year"]] for sat in ("N20", "N21")}
    chart = line_chart({**by_year, "mean": yearly_level(daily)}, (0.7, 1.3), (0.85, 1.15),
                       {"N20": "NOAA-20 / SNPP", "N21": "NOAA-21 / SNPP", "mean": "Mittel / SNPP"})
    labels = {"snpp": "SNPP", "noaa20": "NOAA-20", "noaa21": "NOAA-21"}
    noise_rows = [(f"{labels[row['held_out']]} zurückgehalten", min(row["error_single"].values()), row["error_mean"]) for row in noise["rotations"]]
    month = [row for row in result["noise"]["rows"] if row["grain"] == "month"]
    k_days = (status[["snpp_operating", "noaa20_operating", "noaa21_operating"]].sum(axis=1)).value_counts().sort_index()
    passed = sum(kpi["passed"] for kpi in report["kpis"])
    values = {"passed": str(passed), "total": str(len(report["kpis"])), "median": de(level["median"], 3), "p10": de(level["p10"]), "p90": de(level["p90"]),
              "region_min": de(level["region_min"]), "region_min_id": level["region_min_id"], "rows_read": de(balance["rows_read"], 0),
              "rows_kept": de(balance["rows_kept"], 0), "outside": de(balance["rejected_by_reason"].get("outside_common_area", 0), 0),
              "k1": de(k_days.get(1, 0), 0), "k2": de(k_days.get(2, 0), 0), "k3": de(k_days.get(3, 0), 0),
              "single": de(noise_rows[0][1], 1), "mean_err": de(noise_rows[0][2], 1), "month_mean": de(month[0]["error_mean"]),
              "last_date": str(pd.to_datetime(daily["date"]).max().date()), "schema": str(config["schema_version"]),
              "h3": str(config["grid"]["h3_resolution"])}
    blocks = {"rules": analysis_rules(result), "chart": chart, "noise_chart": bar_chart(noise_rows, 2.2), "regions": region_table(result),
              "kpis": kpi_rows(report)}
    return text.fill(BODY, values, blocks)


BODY = r"""
<main>
<p class="eyebrow">NASA Space Apps 2026 · FIRMS · Iberien · Schema-Version {{schema}}</p>
<h1>VIIRS-Erweiterung: NOAA-20 und NOAA-21</h1>
<p class="lede">Seit dieser Version misst die Harmonisierung VIIRS nicht mehr nur mit SNPP, sondern mit drei baugleichen Satelliten. Diese Seite zeigt, wie das gebaut und geprüft wurde: was die Daten verlangten, welche Entscheidung warum fiel und woran sich zeigt, dass die Reihe nicht schlechter, sondern genauer wurde. Die Kurzfassung für das Team steht in <code>docs/viirs_extension.md</code>.</p>
<p class="status">{{passed}} von {{total}} Prüfungen erfüllt, keine Schwelle gesenkt. Die Reihe reicht jetzt bis {{last_date}}.</p>

<div class="tiles">
<div class="tile"><b>{{median}}</b><span>VIIRS-Mittel / SNPP je Region und Jahr (Median). Kein Sprung beim Start von NOAA-20 und NOAA-21.</span></div>
<div class="tile"><b>× {{single}} → × {{mean_err}}</b><span>typischer Tagesfehler gegen einen zurückgehaltenen Satelliten: einzeln gegen gemittelt</span></div>
<div class="tile"><b>{{k3}}</b><span>Tage mit drei VIIRS-Satelliten, {{k2}} mit zwei, {{k1}} mit einem</span></div>
<div class="tile"><b>{{rows_kept}}</b><span>Hotspots von {{rows_read}} gelesenen Zeilen, {{outside}} NOAA-Zeilen außerhalb des gemeinsamen Gebiets</span></div>
</div>

<h2>Wie es entstand</h2>
<ol class="steps">
<li><strong>Analyse vor dem Umbau</strong> (<code>data_analysis/09_viirs_satellites.py</code>): fünf Regeln R1–R5 und die Prüfungen N1–N5 vorab festgelegt, dann gemessen.</li>
<li><strong>Erster NOAA-Download angehalten:</strong> Im Nordosten fehlten die NOAA-Daten (Katalonien 0,44, Midi-Pyrénées 0,00, Aquitaine 0,01 der SNPP-Erkennungen). Ein Mittel hätte diese Regionen ab 2018 halbiert. Das Team hat neu heruntergeladen.</li>
<li><strong>Zweiter Download zu groß:</strong> ein Rechteck bis 44,8° N und 4,9° O, MODIS und SNPP decken aber Frankreich nördlich von etwa 43,5° nicht ab. Lösung: ein gemeinsames Gebiet aus den Zellen, in denen MODIS oder SNPP je gemessen haben.</li>
<li><strong>Umbau der Pipeline:</strong> Satellitenliste in der Config, Mittel der aktiven Satelliten, Gewicht 1/k, neue und umbenannte Spalten, H3-Zelle, Datenbankschema Version {{schema}}.</li>
<li><strong>Iteration 1:</strong> zwei Prüfungen verfehlt (U1b, N4b), Ursache gefunden, zwei Einstellungen geändert, danach alles erfüllt. Stopp laut Regel.</li>
</ol>

<h2>Analyse: Passen NOAA-20 und NOAA-21 zu SNPP?</h2>
<p>Die Regeln standen vor der Messung fest. Verglichen wird nur an Tagen, an denen beide Satelliten liefern, und nur im gemeinsamen Gebiet. Archivzeilen zählen nur mit <code>type</code> = 0.</p>
[[rules]]
<figure>
[[chart]]
<div class="legend"><span style="--c:var(--accent)">NOAA-20 / SNPP</span><span style="--c:#b7791f">NOAA-21 / SNPP</span><span style="--c:var(--ink)">Mittel / SNPP (Pipeline, N1)</span></div>
<figcaption>Anzahl der Erkennungen je Jahr im Verhältnis zu SNPP. Die Fläche zeigt den Bereich 0,85–1,15 aus Regel R1. Einzelne Jahre schwanken bis etwa ±10 %, das Mittel bleibt nahe 1: Die Reihe hat 2018 und 2023 keinen Sprung.</figcaption>
</figure>
<details><summary>Verhältnis je Region</summary><div>[[regions]]</div></details>

<h2>Warum das Mittel und nicht die Summe</h2>
<p>SNPP, NOAA-20 und NOAA-21 tragen dasselbe Instrument und überfliegen Iberien etwa 50 Minuten versetzt. Sie sehen dasselbe Feuer zu einer anderen Uhrzeit. Ihre Pixel liegen nicht übereinander, Doppelte lassen sich also nicht entfernen. Eine Summe würde die Reihe ab 2018 verdoppeln und ab 2023 verdreifachen. Das Mittel misst dieselbe Größe wie vorher (SNPP allein) und gleicht den Zufall aus, ob ein einzelner Überflug ein kleines Feuer gerade trifft.</p>
<figure>
[[noise_chart]]
<figcaption>Prüfung ohne „wahren“ Wert: An Tagen mit allen drei Satelliten (ab März 2023) wird jeder einmal zurückgehalten. Grau: der bessere der beiden übrigen allein. Blau: ihr Mittel. Typischer Faktorfehler je Region und Tag. Je Monat sinkt er auf × {{month_mean}}.</figcaption>
</figure>

<h2>Was sich in der Pipeline ändert</h2>
<div class="scroll"><table class="wide"><thead><tr><th>Baustein</th><th>Änderung</th><th>Grund</th></tr></thead><tbody>
<tr><td>Config</td><td><code>satellites.viirs: [SNPP, N20, N21]</code>, <code>column_key</code>, acht Quellen in <code>data/raw/&lt;produkt&gt;/</code></td><td>Kein Satellitenname mehr im Code. Ein weiterer Satellit braucht nur Config und Spaltenkatalog.</td></tr>
<tr><td>Gemeinsames Gebiet</td><td><code>common_area.py</code>: nur 0,25°-Zellen mit Terra-, Aqua- oder SNPP-Erkennungen</td><td>Die Downloads decken verschiedene Gebiete ab. Ohne Angleichung stiege das Mittel in Randregionen.</td></tr>
<tr><td>Tagesraster</td><td><code>add_viirs_reference</code>: <code>n_viirs</code> = Mittel der aktiven VIIRS-Satelliten; <code>viirs_operating</code></td><td>Aktiv ohne Feuer zählt 0, nicht aktiv zählt nicht. Ab 03.11.2026 messen NOAA-20/21 allein weiter.</td></tr>
<tr><td>Gewichte</td><td><code>weight_n</code> = 1/k für VIIRS, nur wenn der Satellit an dem Tag aktiv ist</td><td>Hält SUM(<code>weight_n</code>) = <code>n_harm</code> für jede Fläche exakt (D11, N2).</td></tr>
<tr><td>Kalibrierung, Fehlermodell</td><td>gegen SNPP allein (<code>calibration.reference_satellites</code>)</td><td>Iteration 1: gleiches Rauschen der Referenz im ganzen Kalibrierfenster, sonst sind die Prüfhälften nicht vergleichbar.</td></tr>
<tr><td>Ortsmaske</td><td>je Sensor: VIIRS aus VIIRS, MODIS aus allen (<code>mask_training_sensors</code>)</td><td>Iteration 1: MODIS-Pixel (1 km) blähen die Maske für VIIRS auf.</td></tr>
<tr><td>Hotspots</td><td><code>h3_cell</code> (H3, Auflösung {{h3}})</td><td>Sechseck-Heatmaps und Nachbarschaftsabfragen; gröber per <code>h3.cell_to_parent</code>.</td></tr>
<tr><td>Spalten</td><td>neu <code>n_viirs</code>, <code>frp_viirs</code>, <code>viirs_operating</code>; Rohwerte <code>n_noaa20</code>, <code>n_noaa21</code>, <code>frp_noaa20</code>, <code>frp_noaa21</code>, <code>noaa20_operating</code>, <code>noaa21_operating</code></td><td>Die Referenz heißt nicht mehr SNPP. Die Rohzahlen bleiben zum Nachrechnen.</td></tr>
<tr><td>Datenbank</td><td><code>db/init/001_schema.sql</code>, <code>load_to_db.py</code> prüft <code>schema_version</code> = {{schema}}</td><td>Daten und Schema können nicht unbemerkt auseinanderlaufen.</td></tr>
</tbody></table></div>

<h2>Prüfung</h2>
<p>Alle bisherigen 34 Prüfungen bleiben mit unveränderten Schwellen. D1 bis U3 messen weiterhin gegen SNPP (die Kalibrier-Referenz) und haben dieselben Werte wie ohne NOAA. Neu sind N1 bis N5:</p>
[[kpis]]
<ul>
<li><strong>N1c</strong> deckt fehlende Abdeckung auf: Mit dem ersten, unvollständigen Download lag das kleinste Verhältnis bei 0,45 (Katalonien). Jetzt {{region_min}} ({{region_min_id}}).</li>
<li><strong>N1 je Region und Jahr:</strong> 10–90 % der Werte liegen zwischen {{p10}} und {{p90}}. Die Abweichungen einzelner Jahre sind Zufall eines anderen Überflugs, kein Trend.</li>
<li><strong>N4b ist knapp:</strong> 1,90 % bei Grenze 2 % (NOAA-20).</li>
</ul>

<h2>Iterationen</h2>
<div class="scroll"><table class="wide"><thead><tr><th>Schritt</th><th>Befund</th><th>Änderung</th><th>Ergebnis</th></tr></thead><tbody>
<tr><td>Probelauf</td><td>Erster NOAA-Download: N1c 0,45, dazu U1 und N4b verfehlt</td><td>angehalten, neuer Download</td><td>–</td></tr>
<tr><td>Lauf 1</td><td>U1b 0,614 (Grenze 0,58): Bänder aus 2012–2016 treffen 2017–2021 zu oft, weil die Referenz ab 2018 aus zwei Satelliten gemittelt und ruhiger ist. N4b 2,23 % (Grenze 2 %): MODIS-Zeilen vergrößern die VIIRS-Maske.</td><td>Kalibrierung und Fehlermodell gegen SNPP allein; Ortsmaske je Sensor</td><td>U1b 0,578, N4b 1,90 %</td></tr>
<tr><td>Iteration 1</td><td>alle {{total}} Prüfungen erfüllt</td><td>–</td><td>Stopp laut Regel</td></tr>
</tbody></table></div>

<h2>Hinweise für das Frontend</h2>
<ul>
<li><strong><code>n_snpp</code> ist nicht mehr die Referenz.</strong> Werte immer aus <code>n_harm</code> und <code>frp_harm</code>, „gemessen“ aus <code>n_viirs</code>.</li>
<li><strong>Ein Feuer, mehrere Punkte:</strong> Ab 2018 erscheint ein Feuer oft als Punkt von SNPP und von NOAA-20/21. <code>in_series_n</code> filtert nur MODIS-Doppelte. Punkte nie zählen, sondern <code>weight_n</code> summieren.</li>
<li><strong><code>weight_n</code> = 1/3 ist kein drittel Feuer</strong> und gehört nicht ins Popup.</li>
<li><strong>H3:</strong> <code>h3_cell</code> hat Auflösung {{h3}} (etwa 0,74 km²). Für ganz Iberien auf Auflösung 5 oder 6 zusammenfassen.</li>
<li><strong>Datenbank neu anlegen:</strong> <code>docker compose down -v &amp;&amp; docker compose up -d db</code>, dann <code>pipeline/load_to_db.py</code>.</li>
</ul>

<h2>Offene Punkte</h2>
<ul>
<li>Bänder gemessener Tage nutzen noch die Annahme für einen Satelliten. Mit drei Satelliten wären sie enger.</li>
<li>Ein Satellit mit Ausfall zählt an dem Tag als 0 im Mittel und ist nur als <code>possible_gap</code> markiert.</li>
<li>Das gemeinsame Gebiet ist aus Daten gelernt. In Randzellen können einzelne NOAA-Punkte knapp außerhalb des SNPP-Gebiets mitzählen.</li>
<li>Die H3-Auflösung ist ein Vorschlag (<code>grid.h3_resolution</code>).</li>
</ul>
</main>
"""


def main() -> None:
    """Schreibt docs/viirs_extension.html."""
    config = load_config()
    head = "<title>VIIRS-Erweiterung</title>\n" + text.STYLE + EXTRA_STYLE
    target = PROJECT_ROOT / "docs" / "viirs_extension.html"
    target.write_text(text.DOCUMENT_HEAD + head + "</head>\n<body>\n" + build_body(collect(config), config) + "\n</body>\n</html>\n", encoding="utf-8")
    print("->", target, f"({target.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
