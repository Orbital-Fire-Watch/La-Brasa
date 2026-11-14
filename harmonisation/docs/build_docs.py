"""Baut die Dokumentation: data_dictionary.md, column_guide.html und pipeline_overview.html.

Aufruf: .venv/bin/python docs/build_docs.py [--fragments ORDNER]
Das Datenwoerterbuch und der Spaltenbericht entstehen aus dem Spaltenkatalog. Die Uebersicht braucht
zusaetzlich die Ergebnisse des letzten Pipeline-Laufs (data/harmonised) und der Hypothesen
(data_analysis/experiments/hypothesis_results.json). Jede im Katalog genannte Funktion wird importiert und geprueft.
--fragments schreibt die HTML-Seiten zusaetzlich ohne Seitengeruest (zum Veroeffentlichen).
"""
from __future__ import annotations

import html
import importlib
import sys
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "docs"))

from pipeline.column_catalogue import TABLES  # noqa: E402
from pipeline.config import load_config, path_of  # noqa: E402
from pipeline.io_utils import read_json, read_parquet  # noqa: E402

import doc_text as text  # noqa: E402

GUIDE_TABLES = ["activity_daily_harmonised", "hotspots_harmonised", "day_status", "quality_by_scale", "calib_factors",
                "strength_confusion", "big_fire_day_quality", "roll_up", "climatology", "month_to_date"]


def de(value: float, digits: int = 2) -> str:
    """Zahl im deutschen Format (Komma als Dezimalzeichen, Punkt als Tausendertrenner)."""
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float, digits: int = 1) -> str:
    """Anteil als Prozentangabe."""
    return de(100 * value, digits) + " %"


def table(head: list[str], rows: list[list[str]], css_class: str = "") -> str:
    """HTML-Tabelle in einem seitlich scrollbaren Rahmen."""
    head_html = "".join(f"<th>{cell}</th>" for cell in head)
    body_html = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table class="{css_class}"><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def verify_function_exists(module_name: str, function_name: str) -> None:
    """Bricht ab, wenn eine im Katalog genannte Funktion nicht im Code existiert."""
    if not callable(getattr(importlib.import_module(module_name), function_name, None)):
        raise AttributeError(f"{module_name}.{function_name} existiert nicht")


def write_data_dictionary() -> Path:
    """Schreibt docs/data_dictionary.md: jede Spalte jeder Tabelle mit Typ, Einheit, Bedeutung und Lesart von 0 und leer."""
    lines = ["# Datenwörterbuch", "", "Erzeugt aus `pipeline/column_catalogue.py`. Dieselbe Quelle prüft das Schema der Dateien.", ""]
    for table_info in TABLES.values():
        lines += [f"## {table_info.title}", "", f"- Zeile: {table_info.grain}", f"- Ablage: `{table_info.location}`",
                  f"- Zweck: {table_info.purpose}", "", "| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |",
                  "|---|---|---|---|---|---|"]
        lines += [f"| `{c.name}` | {c.dtype} | {c.unit} | {c.meaning} | {c.empty} | {c.frontend} |" for c in table_info.columns]
        lines.append("")
    target = PROJECT_ROOT / "docs" / "data_dictionary.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def build_column_tables(config: dict[str, Any]) -> tuple[str, str]:
    """Baut je Tabelle den Abschnitt des Spaltenberichts und die Eintraege des Inhaltsverzeichnisses."""
    sections, toc = [], []
    for name in GUIDE_TABLES:
        info = TABLES[name]
        rows = [[f"<code>{c.name}</code>", f"{c.dtype}<br>{c.unit}", c.meaning, c.empty, c.frontend] for c in info.columns]
        meta = [f"<span><b>Zeile:</b> {info.grain}</span>", f"<span><b>Ablage:</b> <code>{info.location}</code></span>"]
        path = path_of(config, "harmonised", f"{name}.parquet")
        if info.stored and path.exists():
            meta.append(f"<span><b>Umfang:</b> {de(pq.read_metadata(path).num_rows, 0)} Zeilen, {len(info.columns)} Spalten</span>")
        sections.append(f'<h2 id="{name}"><code>{html.escape(info.title)}</code></h2><p>{info.purpose}</p><div class="meta">{"".join(meta)}</div>'
                        + table(["Spalte", "Typ, Einheit", "Was sie enthält", "0 und leer", "Nutzung im Frontend"], rows, "wide cols"))
        toc.append(f'<li><a href="#{name}">{html.escape(info.title)}</a></li>')
    return "".join(sections), "".join(toc)


def build_column_guide(config: dict[str, Any]) -> str:
    """Setzt den Spaltenbericht zusammen: Zuordnung Funktion -> Daten, Tabellen, Regeln, Beispiele."""
    sections, toc = build_column_tables(config)
    frontend_map = table(["Funktion im Frontend", "Datenquelle", "Wichtige Spalten"], [list(row) for row in text.FRONTEND_MAP], "wide")
    rules = "<ul>" + "".join(f"<li><strong>{title}</strong> {body}</li>" for title, body in text.FRONTEND_RULES) + "</ul>"
    blocks = {"toc": toc, "frontend_map": frontend_map, "tables": sections, "rules": rules, "recipes": html.escape(text.RECIPES)}
    return text.fill(text.GUIDE_BODY, {}, blocks)


def format_kpi_value(kpi_id: str, value: Any) -> str:
    """Formatiert einen KPI-Wert passend zu seiner Art (Faktor, Anteil, Kennzahl, ja/nein)."""
    if isinstance(value, bool) or value is None:
        return {True: "ja", False: "nein", None: "nicht geprüft"}[value]
    if kpi_id in text.KPI_AS_FACTOR:
        return "× " + de(value)
    if kpi_id in text.KPI_AS_SHARE:
        return pct(value, 3 if value > 0.99 else 1)
    if kpi_id in text.KPI_SCIENTIFIC:
        return f"{value:.1e}".replace(".", ",")
    return de(value)


def build_kpi_table(report: dict[str, Any]) -> str:
    """KPI-Tabelle: Schwelle gegen Messwert."""
    rows = []
    for kpi in report["kpis"]:
        rule = {"<=": "höchstens ", ">=": "mindestens ", "==": ""}[kpi["rule"]]
        status = '<span class="ok">erfüllt</span>' if kpi["passed"] else '<span class="fail">verfehlt</span>'
        rows.append([kpi["id"], html.escape(text.KPI_NAMES.get(kpi["name"], kpi["name"])), rule + format_kpi_value(kpi["id"], kpi["threshold"]),
                     format_kpi_value(kpi["id"], kpi["value"]), status])
    return table(["#", "Kennzahl", "Schwelle", "gemessen", "Stand"], rows, "num kpi")


def build_function_catalogue(values: dict[str, str]) -> str:
    """Funktionskatalog je Modul. Prueft dabei, dass jede Funktion existiert."""
    parts = []
    for module_name, title, entries in text.FUNCTION_CATALOGUE:
        rows = []
        for function_name, what, why in entries:
            verify_function_exists(module_name, function_name)
            rows.append([f"<code>{function_name}</code>", what, text.fill(why, values, {})])
        file_name = module_name.replace(".", "/") + ".py"
        parts.append(f"<h3>{title} <span class='file'>{file_name}</span></h3>" + table(["Funktion", "Was sie tut", "Warum das gilt"], rows, "wide"))
    return "".join(parts)


def build_quality_example(quality: Any) -> tuple[str, dict[str, float]]:
    """Beispiel des Fehlermodells: Anzahl je NUTS-2-Region, Tag neben Monat, je Groessenklasse."""
    rows = quality[(quality["area_scale"] == "nuts2") & (quality["quantity"] == "count") & (quality["basis"] == "modis_pair_scaled")
                   & (quality["size_class"] != "all")]
    day, month = (rows[rows["grain"] == grain].set_index("size_class") for grain in ("day", "month"))
    body = []
    for label in day.index:
        cells = [f"umgerechnet {label}" if label != "0" else "umgerechnet 0"]
        for part in (day, month):
            entry = part.loc[label]
            cells += ["–" if label == "0" else "× " + de(entry["median_factor_error"]), "–" if label == "0" else "× " + de(entry["p90_factor_error"]),
                      de(entry["n_units"], 0)]
        body.append(cells)
    head = ["Größenklasse", "Tag: typischer Fehler", "Tag: 90-%-Fehler", "Tag: Fälle", "Monat: typischer Fehler", "Monat: 90-%-Fehler", "Monat: Fälle"]
    example = month.loc["20-100"]
    numbers = {"e50": float(example["median_factor_error"]), "e90": float(example["p90_factor_error"]),
               "zero_day": float(day.loc["0", "abs_upper_p90"]), "zero_month": float(month.loc["0", "abs_upper_p90"])}
    return table(head, body, "num"), numbers


def build_hypothesis_table(results: dict[str, Any], config: dict[str, Any]) -> str:
    """Tabelle der Hypothesen H1 bis H5 mit Messwerten und Entscheidung."""
    base, h1, h2, h5, h4 = (results[key] for key in ("baseline", "h1_frp_source", "h2_date_assignment", "h5_frp_daynight", "h4_season_factors"))
    h3 = {row["threshold_mw"]: row for row in results["h3_scaled_threshold"]}
    chosen, default = h3[config["strength"]["big_fire_threshold_scaled_mw"]], h3[config["strength"]["big_fire_threshold_mw"]]
    rows = [
        ["H1", "Tagesstärke vor 2012 aus Aqua allein statt aus Aqua + Terra",
         f"FRP-R² {de(base['d4_frp_r2'])} (Aqua) gegen {de(h1['d4_frp_r2'])} (Paar), Großfeuer-Kappa {de(base['d5_kappa'])} gegen {de(h1['d5_kappa'])}",
         "Bestätigt. Aqua bleibt die Quelle der Stärke, weil es wie SNPP am frühen Nachmittag misst."],
        ["H2", "Tageszuordnung nach Sonnendatum statt UTC-Datum",
         f"Anzahl je Tag × {de(h2['d1_day_error'])} gegen × {de(base['d1_day_error'])} (besser), FRP-R² {de(h2['d4_frp_r2'])} gegen {de(base['d4_frp_r2'])} (schlechter, in 8 von 10 Jahren)",
         "Nicht übernommen: Die Stärke am einzelnen Tag ist die wichtigere Anforderung, und das UTC-Datum entspricht FIRMS. Umschaltbar über <code>daily.date_assignment</code>."],
        ["H3", "Eigene Schwelle für Großfeuer-Tage aus umgerechneten Werten",
         f"100 MW: gefunden {pct(default['recall'], 0)}, zutreffend {pct(default['precision'], 0)}. {de(chosen['threshold_mw'], 0)} MW: {pct(chosen['recall'], 0)} und {pct(chosen['precision'], 0)}, Kappa {de(chosen['kappa'])}",
         f"Übernommen: {de(chosen['threshold_mw'], 0)} MW. Damit ist die Zahl der Großfeuer-Tage vor und nach 2012 vergleichbar."],
        ["H4", "Eigener Zählfaktor für Juni bis September (im Auftrag nicht näher bestimmt, so gelesen)",
         f"Anzahl je Tag × {de(h4['d1_day_error'])} gegen × {de(base['d1_day_error'])}, Monatsklasse {pct(h4['d3_month_class'], 1)} gegen {pct(base['d3_month_class'], 1)}",
         "Nicht übernommen: Der Gewinn ist klein, im Monat in 3 von 10 Jahren negativ, und die Zahl der Faktoren verdoppelt sich. Entscheidung fürs Team."],
        ["H5", "Tagesstärke nur aus Tag-Überflügen statt Tag + Nacht",
         f"FRP-R² {de(h5['d4_frp_r2'])} gegen {de(base['d4_frp_r2'])}, Großfeuer-Kappa {de(h5['d5_kappa'])} gegen {de(base['d5_kappa'])}, „extreme“ {pct(h5['d7_extreme'], 0)} gegen {pct(base['d7_extreme'], 0)}",
         "Nicht übernommen: R² minimal besser, die Ereignisse schlechter. Tag + Nacht bleibt."],
    ]
    return table(["#", "Hypothese", "Messung (Kreuzvalidierung)", "Entscheidung"], rows, "wide")


def collect_overview_values(config: dict[str, Any]) -> dict[str, str]:
    """Sammelt alle Zahlen, die in der Uebersicht als Platzhalter vorkommen."""
    state = read_json(path_of(config, "harmonised", "pipeline_state.json"))
    report = read_json(path_of(config, "harmonised", "kpi_report.json"))
    summary = read_json(path_of(config, "harmonised", "calib_summary.json"))
    balance, accuracy, mask = state["clean"]["report"], report["measured"]["accuracy"], report["measured"]["mask"]
    failed = [kpi["id"] for kpi in report["kpis"] if not kpi["passed"]]
    status = (f"Alle {len(report['kpis'])} Prüfungen sind erfüllt. Die Iteration endete nach dem zweiten Durchlauf." if not failed
              else f"{len(report['kpis']) - len(failed)} von {len(report['kpis'])} Prüfungen sind erfüllt. Verfehlt: {', '.join(failed)}.")
    unreadable = sum(source.get("unreadable_rows", 0) for source in state["ingest"]["report"].values())
    return {
        "status_text": status, "rows_read": de(balance["rows_read"], 0), "rows_kept": de(balance["rows_kept"], 0),
        "rows_rejected": de(balance["rows_rejected"], 0), "rows_in_series": de(state["weight_hotspots"]["report"]["rows_in_series"], 0),
        "daily_rows": de(state["harmonise_daily"]["report"]["rows"], 0), "n_regions": str(state["daily_grid"]["report"]["regions"]),
        "n_days": de(state["daily_grid"]["report"]["days"], 0), "first_date": state["harmonise_daily"]["report"]["first_date"],
        "last_date": state["harmonise_daily"]["report"]["last_date"], "d1": de(accuracy["d1_daily_count"]["median_factor_error"]),
        "d3": de(accuracy["d3_monthly"]["median_factor_error"]), "d7": pct(accuracy["d7_extreme_class"]["exact_share"], 0),
        "runtime": de(sum(stage.get("seconds", 0.0) for stage in state.values() if isinstance(stage, dict) and "seconds" in stage), 0),
        "n_tests": state["test"]["report"]["summary"].split(" ")[0], "n_eval_regions": str(len(accuracy["evaluation_regions"])),
        "mask_recall": pct(mask["all"]["recall"]), "mask_false": pct(mask["all"]["false_removal"]),
        "drift_aqua": de(summary["drift"]["latest_deviation_minutes"]["Aqua"], 0),
        "drift_terra": de(abs(summary["drift"]["latest_deviation_minutes"]["Terra"]), 0),
        "h3_threshold": de(config["strength"]["big_fire_threshold_scaled_mw"], 0),
        "none_days": str(state["daily_grid"]["report"]["days_by_basis_count"].get("none", 0)),
        "gap_days": str(state["daily_grid"]["report"]["possible_gap_days"]),
        "unreadable_note": (f"{unreadable} Zeile der Quelldateien enthielt einen unlesbaren Wert (eingefügter Text in einer Zahl) und wurde als "
                            "<code>invalid_value</code> verworfen. Die Quelldatei selbst bleibt unverändert." if unreadable
                            else "Alle Zeilen der Quelldateien waren lesbar."),
    }


def build_kpi_notes(report: dict[str, Any]) -> str:
    """Hinweise zu knapp erfuellten oder einzuordnenden Kennzahlen."""
    measured = report["measured"]
    unc, mask, climate = measured["uncertainty"], measured["mask"], measured["accuracy"]["d8_climatology"]
    notes = [
        f"<strong>Knapp erfüllt, Abdeckung des 50-%-Bands:</strong> {pct(unc['coverage50_min'])} bis {pct(unc['coverage50_max'])} bei erlaubten 42 bis 58 %. "
        "Die Randwerte stammen aus einer Klasse mit nur gut 100 Prüffällen, dort ist die Messung selbst unscharf.",
        f"<strong>Knapp erfüllt, Klimaprofil:</strong> Die schwächste Region korreliert mit {de(climate['region_corr_min'])} bei Schwelle 0,80.",
        f"<strong>Ortsmaske:</strong> gesamt {pct(mask['all']['recall'])}. Bei VIIRS {pct(mask['VIIRS']['recall'])}, bei MODIS wegen der größeren Pixel nur {pct(mask['MODIS']['recall'], 0)}.",
        f"<strong>Großfeuer-Tage:</strong> Auch mit der angepassten Schwelle findet die Umrechnung nur {pct(measured['accuracy']['d5_big_fire_region']['recall'], 0)} der gemessenen Tage. "
        "Vor 2012 fehlt also etwa jeder dritte.",
    ]
    return "".join(f"<li>{note}</li>" for note in notes)


def build_overview(config: dict[str, Any]) -> str:
    """Setzt die Pipeline-Uebersicht aus Text, Tabellen und Zahlen zusammen."""
    values = collect_overview_values(config)
    state = read_json(path_of(config, "harmonised", "pipeline_state.json"))
    report = read_json(path_of(config, "harmonised", "kpi_report.json"))
    quality_table, numbers = build_quality_example(read_parquet(path_of(config, "harmonised", "quality_by_scale.parquet")))
    values.update({"example_lo50": de(51 / numbers["e50"] - 1, 0), "example_hi50": de(51 * numbers["e50"] - 1, 0),
                   "example_lo90": de(51 / numbers["e90"] - 1, 0), "example_hi90": de(51 * numbers["e90"] - 1, 0),
                   "zero_day_p90": de(numbers["zero_day"], 0), "zero_month_p90": de(numbers["zero_month"], 0)})
    factors = read_parquet(path_of(config, "harmonised", "calib_factors.parquet"))
    reasons = state["clean"]["report"]["rejected_by_reason"]
    stages = [[f"<strong>{name}</strong>", script, reads, writes, de(state.get(name, {}).get("seconds", 0.0), 1) + " s"]
              for name, script, reads, writes in text.STAGES]
    blocks = {
        "stages": table(["Stufe", "Skript", "liest", "schreibt", "Dauer"], stages, "wide"),
        "catalogue": build_function_catalogue(values),
        "dropped": table(["Spalte", "Funktion", "Grund", "Beleg"], [[cols, f"<code>{fn}</code>", why, proof] for fn, cols, why, proof in text.DROPPED_COLUMNS], "wide"),
        "balance": table(["Grund", "Zeilen"], [[html.escape(text.REJECT_REASONS.get(reason, reason)), de(count, 0)] for reason, count in reasons.items()], "num"),
        "quality_example": quality_table, "kpis": build_kpi_table(report), "kpi_notes": build_kpi_notes(report),
        "hypotheses": build_hypothesis_table(read_json(PROJECT_ROOT / "data_analysis" / "experiments" / "hypothesis_results.json"), config),
        "iterations": table(["Schritt", "Was", "Ergebnis"], [list(row) for row in text.ITERATIONS], "wide"),
        "factors": table(["Region", "Anzahl: Aqua + Terra", "Anzahl: nur Aqua", "Anzahl: nur Terra", "Herkunft"],
                         [[row.region_id, de(row.k_count_pair), de(row.k_count_aqua), de(row.k_count_terra),
                           "Gesamtfaktor" if row.used_fallback_pair else "eigener Faktor"] for row in factors.itertuples()], "num"),
    }
    for function_name, *_ in text.DROPPED_COLUMNS:
        verify_function_exists("pipeline.data_loading.clean_hotspots", function_name)
    return text.fill(text.OVERVIEW_BODY, values, blocks)


def write_page(name: str, title: str, body: str, fragment_dir: Path | None) -> None:
    """Schreibt eine HTML-Seite als eigenstaendige Datei und optional als Fassung ohne Seitengeruest."""
    head = f"<title>{title}</title>\n" + text.STYLE
    target = PROJECT_ROOT / "docs" / name
    target.write_text(text.DOCUMENT_HEAD + head + "</head>\n<body>\n" + body + "\n</body>\n</html>\n", encoding="utf-8")
    print("->", target, f"({target.stat().st_size / 1024:.0f} KB)")
    if fragment_dir is not None:
        (fragment_dir / name).write_text(head + body, encoding="utf-8")


def main() -> None:
    """Baut das Datenwoerterbuch immer, die HTML-Seiten, sobald ein Pipeline-Lauf mit KPI-Bericht vorliegt."""
    config = load_config()
    print("->", write_data_dictionary())
    fragment_dir = Path(sys.argv[sys.argv.index("--fragments") + 1]) if "--fragments" in sys.argv else None
    write_page("column_guide.html", "FIRMS-Spaltenbericht", build_column_guide(config), fragment_dir)
    if path_of(config, "harmonised", "kpi_report.json").exists() and (PROJECT_ROOT / "data_analysis" / "experiments" / "hypothesis_results.json").exists():
        write_page("pipeline_overview.html", "Tägliche FIRMS-Harmonisierung", build_overview(config), fragment_dir)


if __name__ == "__main__":
    main()
