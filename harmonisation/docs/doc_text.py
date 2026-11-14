"""Texte, Kataloge und Stil der Dokumentation. Zahlen kommen als {{platzhalter}} aus build_docs.py."""
from __future__ import annotations

import re

DOCUMENT_HEAD = ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
                 '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')

STYLE = r"""<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap">
<style>
/* Layout: eine Lesespalte (max. 940px), Stand zuerst, danach Tabellen als abgesetzte Flaechen */
:root{
  --bg:#f4f5f7; --surface:#ffffff; --ink:#10161d; --ink2:#46505c; --muted:#77818d;
  --line:#dde1e6; --accent:#1d5a66; --wash:#e7eff1; --ok:#1c6b3c; --fail:#b3261e;
  --raw:#eef0f3; --proc:#e7eff1; --harm:#dcebe2; --agg:#efe9dc;
  --body:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;
  --display:"Space Grotesk","Inter",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0e1114; --surface:#171b20; --ink:#eef1f4; --ink2:#b9c1ca; --muted:#8a939e;
    --line:#2a3038; --accent:#7fc4d1; --wash:#16262b; --ok:#6fcf97; --fail:#ff8a80;
    --raw:#1b2026; --proc:#16262b; --harm:#16291f; --agg:#2a2518; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#0e1114; --surface:#171b20; --ink:#eef1f4; --ink2:#b9c1ca; --muted:#8a939e;
  --line:#2a3038; --accent:#7fc4d1; --wash:#16262b; --ok:#6fcf97; --fail:#ff8a80;
  --raw:#1b2026; --proc:#16262b; --harm:#16291f; --agg:#2a2518; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--body);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:40px 80px;-webkit-text-size-adjust:100%}
main{max-width:940px;margin:0 auto;display:flex;flex-direction:column;gap:18px;min-width:0}
main>*{margin:0;min-width:0}
p,li{max-width:74ch}
h1,h2,h3{font-family:var(--display);font-weight:600;text-wrap:balance;line-height:1.2;letter-spacing:-0.01em}
h1{font-size:clamp(1.8rem,5vw,2.5rem)}
h2{font-size:1.45rem;margin-top:30px;padding-top:26px;border-top:1px solid var(--line)}
h3{font-size:1.05rem;margin-top:10px}
h3 .file{font-family:var(--mono);font-size:.8rem;font-weight:400;color:var(--muted);margin-left:6px;letter-spacing:0}
.eyebrow{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:500}
.lede{font-size:1.1rem;color:var(--ink2);max-width:66ch}
a{color:var(--accent)}
code{font-family:var(--mono);font-size:.88em;background:var(--wash);padding:.06em .3em;border-radius:3px}
pre{font-family:var(--mono);font-size:.84rem;background:var(--surface);border:1px solid var(--line);border-radius:6px;
  padding:12px 14px;overflow-x:auto;line-height:1.5}
pre code{background:none;padding:0}
ul{padding-left:1.25em;display:flex;flex-direction:column;gap:7px}
.status{background:var(--wash);border-radius:8px;padding:16px 20px;font-family:var(--display);font-size:1.12rem;font-weight:500;line-height:1.4;max-width:none}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:flex;flex-direction:column;gap:4px}
.tile b{font-family:var(--display);font-size:1.55rem;font-weight:600;line-height:1.15}
.tile span{font-size:.86rem;color:var(--ink2);line-height:1.4}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.layer{border-radius:8px;padding:12px 14px;display:flex;flex-direction:column;gap:5px;min-width:0;border:1px solid var(--line)}
.layer b{font-family:var(--display);font-size:.96rem}
.layer span{font-size:.8rem;color:var(--ink2);line-height:1.4;overflow-wrap:anywhere}
.layer i{font-style:normal;font-size:.74rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.l-src{background:var(--surface)} .l-raw{background:var(--raw)} .l-proc{background:var(--proc)} .l-harm{background:var(--harm)} .l-agg{background:var(--agg)}
.scroll{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;font-size:.86rem;width:100%;background:var(--surface);border:1px solid var(--line)}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.45}
th{font-weight:600;color:var(--ink2);font-size:.79rem}
table.wide{min-width:760px}
table code{white-space:nowrap}
table.num td:not(:first-child),table.num th:not(:first-child){text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.kpi td:nth-child(2),table.kpi th:nth-child(2){text-align:left;white-space:normal}
table.cols td:nth-child(2){color:var(--ink2);white-space:nowrap}
.meta{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.88rem;color:var(--ink2)}
.meta b{color:var(--ink);font-weight:600}
.ok{color:var(--ok);font-weight:600} .fail{color:var(--fail);font-weight:600}
nav.toc{font-size:.92rem;color:var(--ink2)}
nav.toc ul{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:4px 24px;margin:0;list-style:none;padding:0}
details{font-size:.92rem} summary{cursor:pointer;width:fit-content;color:var(--ink2)}
details>div{margin-top:10px}
summary:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.note{font-size:.9rem;color:var(--ink2)}
@media (max-width:760px){ .flow{grid-template-columns:1fr 1fr} h2{font-size:1.3rem} }
</style>
"""

STAGES = [
    ("ingest", "<code>data_loading/ingest_csv_to_parquet.py</code>", "8 FIRMS-CSVs (MODIS, SNPP, NOAA-20, NOAA-21)", "<code>raw/*.parquet</code>"),
    ("clean", "<code>data_loading/clean_hotspots.py</code> mit <code>common_area.py</code>, <code>static_source_mask.py</code>, <code>assign_region.py</code>, "
     "<code>classify_hotspots.py</code>, <code>derive_hotspot_columns.py</code>", "<code>raw</code>, NUTS-2-Grenzen",
     "<code>processed/hotspots_clean</code>, <code>rejected_hotspots</code>, <code>static_mask</code>"),
    ("daily_grid", "<code>algorithms/daily_grid.py</code>", "<code>hotspots_clean</code>, <code>raw</code>",
     "<code>harmonised/day_status</code>, <code>processed/daily_grid</code>, <code>activity_daily_raw</code>"),
    ("calibrate", "<code>algorithms/calibration_factors.py</code>, <code>drift_monitor.py</code>", "<code>daily_grid</code>",
     "<code>harmonised/calib_factors</code>, <code>calib_summary.json</code>"),
    ("quantify_uncertainty", "<code>algorithms/uncertainty_model.py</code>, <code>event_quality.py</code>", "<code>daily_grid</code>, <code>hotspots_clean</code>",
     "<code>harmonised/quality_by_scale</code>, <code>strength_confusion</code>, <code>big_fire_day_quality</code>"),
    ("harmonise_daily", "<code>algorithms/harmonise_daily.py</code>", "<code>daily_grid</code>, <code>calib_factors</code>, <code>quality_by_scale</code>",
     "<code>harmonised/activity_daily_harmonised</code>"),
    ("weight_hotspots", "<code>algorithms/hotspot_weights.py</code>", "<code>hotspots_clean</code>, <code>day_status</code>, <code>calib_factors</code>",
     "<code>harmonised/hotspots_harmonised</code>"),
    ("export_csv", "<code>pipeline/csv_export.py</code>", "alle Tabellen in <code>harmonised</code>", "<code>harmonised/csv/*.csv</code> (Kopien für das Frontend)"),
    ("test", "<code>tests/</code>, <code>aggregation/tests/</code>", "Ausschnitt in <code>../data/raw/fixtures</code>", "–"),
    ("validate", "<code>algorithms/validation_kpis.py</code>, <code>viirs_kpis.py</code>", "Einheiten der Kreuzvalidierung, alle Ausgaben", "<code>harmonised/kpi_report.json</code>, <code>manifest.json</code>"),
]

FUNCTION_CATALOGUE = [
    ("pipeline.data_loading.ingest_csv_to_parquet", "Einlesen", [
        ("convert_csv_to_raw_parquet", "Schreibt eine CSV unverändert als typisiertes Parquet. Fehlt <code>type</code> (NRT), wird die Spalte leer angelegt.",
         "Alle Spalten werden als Text gelesen und gezielt umgewandelt. Ein unlesbarer Wert wird leer, statt den Lauf abzubrechen. Die Zeile wird später mit Grund verworfen."),
    ]),
    ("pipeline.data_loading.clean_hotspots", "Bereinigen", [
        ("reject_invalid_rows", "Verwirft Zeilen mit fehlenden Pflichtwerten, unmöglichen Koordinaten oder unbekanntem Satelliten.",
         "Solche Zeilen liefen sonst still in falsche Summen. Jede steht mit Grund in <code>rejected_hotspots</code>."),
        ("deduplicate_hotspots", "Entfernt doppelte Messungen (gleicher Satellit, Ort, Datum, Uhrzeit). Das Archiv gewinnt vor dem NRT.",
         "Duplikate entstehen nur bei überlappenden Downloads. Verschiedene Uhrzeiten bleiben: Überlappende Bildstreifen sind echte Einzelbeobachtungen."),
        ("restrict_to_common_area", "Verwirft Erkennungen außerhalb des Gebiets, das die MODIS- und SNPP-Downloads abdecken.",
         "Die NOAA-Downloads reichen weiter (bis 44,8° N, 4,9° O). Ohne Angleichung zählte NOAA-20/21 in Randregionen Feuer, die SNPP und MODIS nicht sehen können."),
        ("filter_static_sources", "Behält nur Vegetationsfeuer. Archiv: <code>type</code> = 0. NRT: alles außerhalb der Ortsmaske seines Sensors.",
         "Statische Quellen sind keine Feueraktivität (32 % der SNPP-Nacht-Erkennungen). Zeilen mit und ohne <code>type</code> werden getrennt behandelt, sonst fiele das NRT weg."),
        ("enrich_hotspots", "Ruft Region, Klassen und abgeleitete Spalten auf und droppt die vereinbarten Spalten.",
         "Eine feste Reihenfolge an einer Stelle. Das Ergebnis hat genau das Schema des Spaltenkatalogs."),
    ]),
    ("pipeline.data_loading.common_area", "Gemeinsames Gebiet", [
        ("learn_common_area", "Lernt das Gebiet der Referenz-Downloads: alle 0,25°-Zellen mit mindestens einer Erkennung von Terra, Aqua oder SNPP seit 2000.",
         "FIRMS liefert genau das gewählte Download-Gebiet, und das ist für MODIS/SNPP kein Rechteck. Eine Zelle im Gebiet ohne jede Erkennung in 26 Jahren gibt es praktisch nicht."),
    ]),
    ("pipeline.data_loading.static_source_mask", "Ortsmaske für das NRT", [
        ("learn_static_mask", "Lernt aus dem Archiv Zellen von 0,005° mit mindestens 3 statischen Erkennungen und statischer Mehrheit, plus Nachbarzellen.",
         "Fabriken stehen immer am selben Ort, Feuer nicht. Gelernt wird nur aus Zeilen mit bekanntem <code>type</code>, nie aus dem NRT."),
        ("learn_static_masks", "Lernt je Sensor eine Maske: für VIIRS nur aus VIIRS, für MODIS aus allen Satelliten.",
         "MODIS-Pixel (1 km) verschmieren den Ort einer Anlage. Eine gemeinsame Maske entfernte zu viele VIIRS-Feuer neben Industrie (NOAA-20: 2,2 %)."),
        ("evaluate_mask_on_holdout", "Lernt die Masken bis 2022 und prüft sie an 2023 bis 2026, gesamt, je Sensor und je Satellit.",
         "Nur so zeigt sich, ob sie neue Daten trifft: {{mask_recall}} erkannt, {{mask_false}} der echten Feuer fälschlich entfernt."),
    ]),
    ("pipeline.data_loading.assign_region", "Region", [
        ("assign_nuts2_region", "Ordnet jeden Punkt per Punkt-in-Polygon einer NUTS-2-Region zu. Küstenpunkte bis 0,05° bekommen die nächste Region.",
         "Lokal und ohne API. <code>country</code> sind die ersten zwei Zeichen, Land und Region können sich nicht widersprechen."),
    ]),
    ("pipeline.data_loading.classify_hotspots", "Klassen je Punkt", [
        ("add_frp_class", "Teilt die Pixel-FRP in low (unter 10 MW), mid (10 bis 50) und high (ab 50).",
         "Feste Megawatt-Grenzen. Nur für Punktkarte und Filter: Vor 2012 fehlen die schwachen Feuer, die Anteile sind nicht vergleichbar."),
        ("add_confidence_class", "Vereinheitlicht zu low / nominal / high, der Originalwert bleibt als <code>confidence_raw</code>.",
         "Zwischen den Sensoren nicht vergleichbar: VIIRS-„h“ heißt nur „Kanal bei 367 K gesättigt“."),
        ("add_local_solar_hour", "Lokale Sonnenzeit: UTC-Stunde + Länge / 15.",
         "Macht Überflugzeiten vergleichbar und die Bahndrift sichtbar."),
    ]),
    ("pipeline.data_loading.derive_hotspot_columns", "Abgeleitete Spalten je Punkt", [
        ("add_hotspot_id", "Stabiler Hash aus Satellit, Koordinaten, Datum und Uhrzeit.",
         "Hängt nur von der Messung ab. Ein Punkt behält seine ID über Läufe und neue Daten hinweg."),
        ("add_acquisition_datetime", "Echter Zeitstempel aus <code>acq_date</code> und <code>acq_time</code>.",
         "<code>acq_time</code> ist ein Text wie „0114“, mit dem sich nicht rechnen lässt."),
        ("assign_observation_date", "Bestimmt den Tag, zu dem ein Punkt zählt: UTC-Datum oder Sonnendatum mit Tageswechsel um 6 Uhr.",
         "Mit dem Sonnendatum landet eine Nacht auf einem Tag. Im Test waren die Anzahlen damit etwas besser, die Stärke aber schlechter. Es gilt das UTC-Datum (H2)."),
        ("add_cell_id", "Rasterzelle von 0,25° als „Breitenindex_Längenindex“.", "Für Kacheln auf der Karte und schnelle Flächenfilter."),
        ("add_h3_cell", "H3-Zelle der Pixelmitte (Auflösung {{h3_resolution}}, etwa 0,74 km²).",
         "Sechsecke haben gleich weite Nachbarn und eignen sich für Heatmaps. Gröbere Zellen ergeben sich mit <code>h3.cell_to_parent</code> ohne Neuberechnung."),
        ("add_pixel_area", "Pixelfläche = scan × track.", "Am Bildrand sind Pixel größer. Die Karte kann den echten Fußabdruck zeichnen."),
    ]),
    ("pipeline.algorithms.daily_grid", "Tagesraster und Status", [
        ("sum_hotspots_by_day", "Summiert je Region, Tag und Satellit Anzahl und FRP.",
         "Die FRP-Summe des Tages ist das Maß für die Stärke. Tag und Nacht zählen zusammen (H5: nur Tag war nicht besser)."),
        ("find_satellite_coverage", "Bestimmt je Satellit die Zeitfenster, in denen das Produkt Daten liefert.",
         "Gemessen am Dateifenster, nicht an Erkennungen: Ein Tag ohne Zeile heißt „kein Feuer“, nicht „keine Daten“."),
        ("choose_basis_per_day", "Legt je Tag die Quelle fest: VIIRS gemessen (mindestens ein VIIRS-Satellit), sonst MODIS umgerechnet (bis 2021), sonst kein Wert.",
         "Eine Messung ist besser als eine Umrechnung. Ab 2022 driften Terra und Aqua ({{drift_aqua}} und {{drift_terra}} Minuten), der Faktor gilt nicht mehr. Die Sensoren werden nie addiert."),
        ("flag_possible_gaps", "Markiert Tage, an denen ein Satellit laut Fenster arbeitet, aber auffällig nichts meldet.",
         "Ausfälle innerhalb eines Dateifensters wären sonst unsichtbar. Es wird nur markiert, nicht entfernt."),
        ("build_day_status", "Baut die Statustabelle je Tag: Betrieb, Basis, Vollständigkeit, Vorläufigkeit.",
         "Die Punktdaten kennen keine leeren Tage. Erst diese Tabelle trennt „kein Feuer“ von „keine Daten“."),
        ("build_daily_grid", "Baut das lückenlose Raster Region × Tag: Zahl, 0 oder leer (Satellit nicht in Betrieb).",
         "Ohne die ergänzten Nullen rechnet jede Statistik nur mit Brandtagen. Vor 2012 wäre eine 0 für VIIRS dagegen falsch."),
        ("add_viirs_reference", "Bildet <code>n_viirs</code> und <code>frp_viirs</code>: das Mittel der an diesem Tag aktiven VIIRS-Satelliten (SNPP, NOAA-20, NOAA-21).",
         "Die Satelliten sehen dasselbe Feuer zu anderer Uhrzeit, eine Summe verdoppelte die Reihe ab 2018. Das Mittel bleibt auf SNPP-Niveau ({{n1_median}}) und ist genauer (× {{n3_single}} → × {{n3_mean}} gegen einen zurückgehaltenen Satelliten)."),
    ]),
    ("pipeline.algorithms.calibration_factors", "Kalibrierung", [
        ("select_calibration_days", "Wählt die Tage 02/2012 bis 12/2021, an denen SNPP, Aqua und Terra in Betrieb sind. Die Referenz ist dort SNPP allein.",
         "Nur dort messen MODIS und VIIRS gleichzeitig und zur festen Tageszeit. SNPP allein, damit das Rauschen der Referenz im ganzen Fenster gleich bleibt (Iteration 1 der Erweiterung)."),
        ("estimate_ratio_per_region", "Faktor je Region = Summe VIIRS / Summe MODIS. Unter 300 MODIS-Erkennungen gilt der Gesamtfaktor.",
         "Ein Verhältnis von Summen verträgt Tage mit 0 und erhält die Gesamtsumme exakt."),
        ("estimate_calibration_factors", "Berechnet die Faktoren für Aqua + Terra, nur Aqua und nur Terra, je für Anzahl und FRP.",
         "MODIS übersieht kleine Feuer, wie viele hängt von der Region ab. Die Varianten braucht es, weil die Basis vom Tag abhängt."),
        ("predict_viirs_equivalent", "Rechnet um: MODIS-Summe × Faktor.",
         "Proportional, ein Tag ohne MODIS-Erkennung ergibt 0. Dass diese 0 oft falsch ist, zeigen die Fehlerbänder."),
    ]),
    ("pipeline.algorithms.harmonise_daily", "Harmonisierung", [
        ("harmonise_daily_activity", "Erzeugt je Region und Tag <code>n_harm</code> und <code>frp_harm</code> mit Basis und Faktor.",
         "Die ganze Reihe steht auf einer Skala. Ein umgerechneter Tageswert ist ein Erwartungswert, keine Messung."),
        ("add_strength_columns", "Ergänzt Stärkeklasse und Großfeuer-Tag aus der FRP-Summe.",
         "Die Summe ist zwischen den Sensoren vergleichbar, das stärkste Einzelpixel nicht. Umgerechnete Tage haben die Schwelle {{h3_threshold}} MW (H3)."),
    ]),
    ("pipeline.algorithms.hotspot_weights", "Gewichte je Punkt", [
        ("weight_hotspots", "Legt den Faktor auf jeden Punkt: 1/k bei VIIRS (k aktive VIIRS-Satelliten), Regionsfaktor bei MODIS, 0 außerhalb der Reihe.",
         "Umrechnung und Mittel sind linear, darum ist die Zahl jeder Fläche einfach SUM(weight_n). Die Regel gilt je Satellit, sonst stünde ab 2012 jedes Feuer doppelt da."),
    ]),
    ("pipeline.algorithms.uncertainty_model", "Fehlermodell", [
        ("predict_leave_one_year_out", "Rechnet jedes Jahr mit Faktoren aus den übrigen Jahren um.",
         "So wird kein Tag mit einem Faktor bewertet, in den er selbst eingegangen ist."),
        ("predict_cell_units", "Dasselbe je 0,25°-Zelle und Tag, lückenlos über alle Zellen.",
         "Liefert die Fehler für kleine Flächen. Ruhige Zell-Tage gehören dazu, sonst wäre das Modell zu pessimistisch."),
        ("summarise_error_classes", "Typischer Fehler und 90-%-Fehler je Größenklasse der umgerechneten Zahl.",
         "Der Fehler hängt stark von der Größe ab. Für die Klasse 0 gilt statt eines Faktors eine absolute Obergrenze."),
        ("evaluate_holdout_directions", "Bestimmt die Bänder auf einer Hälfte der Jahre und prüft sie auf der anderen, in beide Richtungen.",
         "Die Richtungen bleiben getrennt. Zusammengezählt höben sich eine zu enge und eine zu weite Hälfte gegenseitig auf."),
        ("build_quality_by_scale", "Baut das Fehlermodell über Fläche, Zeitschritt, Größe, Basis und Größenklasse.",
         "Je mehr Erkennungen zusammenkommen, desto stärker gleicht sich der Zufall aus. Ein einziger Fehlerwert wäre falsch."),
        ("attach_uncertainty_bands", "Ergänzt je Tageszeile die vier Bandgrenzen und <code>reliability</code>.",
         "Jede Zahl trägt ihre Unsicherheit mit sich. Gemessene Tage bekommen Zählrauschen mit Mindestfaktor."),
    ]),
    ("pipeline.algorithms.event_quality", "Qualität der Tagesereignisse", [
        ("build_strength_confusion", "Vergleicht die Stärkeklasse der Messung mit der der Umrechnung.",
         "Zeigt, welcher Klasse man vor 2012 trauen kann: „extreme“ wird zu {{d7}} richtig eingestuft."),
        ("build_big_fire_day_quality", "Recall, Precision und Kappa der Großfeuer-Tage je Basis und Flächenskala.",
         "Nicht addierbare Größen brauchen eine eigene Prüfung, sie lassen sich nicht skalieren."),
    ]),
    ("aggregation.roll_up", "Aggregation (nicht Teil des Orchestrators)", [
        ("roll_up_daily", "Leitet Woche, Monat, Quartal oder Jahr aus den Tagen ab.",
         "Die Summe der umgerechneten Tage ist exakt die umgerechnete Summe. Unvollständige Zeiträume bekommen keinen Wert."),
        ("add_uncertainty_to_periods", "Schlägt die Unsicherheit je Zeitschritt im Fehlermodell nach.",
         "Fehler lassen sich nicht aufsummieren: Tag etwa × 2, Monat × 1,5, Jahr × 1,1."),
    ]),
    ("aggregation.uncertainty", "Aggregation: Unsicherheit", [
        ("lookup_error_factors", "Findet zu jeder Zahl die Fehlerfaktoren ihrer Größenklasse.", "Die Klasse richtet sich nach der umgerechneten Zahl, weil nur sie beim Anzeigen bekannt ist."),
        ("uncertainty_bands", "Berechnet die vier Bandgrenzen für gemessene und umgerechnete Zahlen.", "Das 50-%-Band enthält die Messung in etwa der Hälfte der Fälle, das 90-%-Band in neun von zehn."),
        ("estimate_uncertainty", "Liefert Bänder und Zuverlässigkeit für ein beliebiges Aggregat.", "Für frei gewählte Flächen und Zeiträume. Sobald ein Teil umgerechnet ist, gilt vorsichtshalber das Fehlermodell der Umrechnung."),
    ]),
    ("aggregation.hotspot_queries", "Aggregation: Flächen", [
        ("select_hotspots", "Wählt Punkte nach Rechteck, Polygon, Umkreis, Region oder Zelle und Zeitraum.", "Grundlage für frei gezeichnete Flächen und den CSV-Download."),
        ("aggregate_hotspots", "Summiert die Gewichte über Fläche und Zeitraum.", "Über eine Region ergibt das exakt den Wert der Tagestabelle, über jede andere Fläche eine konsistente Zahl."),
    ]),
    ("aggregation.climatology", "Aggregation: Klimaprofil", [
        ("build_day_of_year_climatology", "Typischer Jahresverlauf je Region, ±7 Tage geglättet.",
         "Wahrscheinlichkeiten kommen nur aus VIIRS-Jahren, weil MODIS an etwa 60 % der Feuertage nichts meldet."),
    ]),
    ("aggregation.month_to_date", "Aggregation: laufender Monat", [
        ("month_to_date_vs_history", "Vergleicht den laufenden Monat bis heute mit denselben Tagen früherer Jahre.",
         "Ein halber Monat liegt immer unter dem Median ganzer Monate, und Hochrechnen wäre falsch."),
    ]),
]

DROPPED_COLUMNS = [
    ("drop_not_comparable_columns", "<code>brightness</code>, <code>bright_t31</code>", "Zwischen den Sensoren nicht vergleichbar. Alle Intensitätsaussagen kommen aus <code>frp</code>.",
     "VIIRS sättigt bei 367 K (14 % der Tag-Erkennungen). Bei MODIS folgt die FRP fast exakt aus der Helligkeit (R² 0,97)."),
    ("drop_redundant_columns", "<code>instrument</code>, <code>version</code>", "Ersetzt durch <code>sensor</code> und <code>source</code>.",
     "<code>instrument</code> ist uneinheitlich befüllt („SNPP“ statt „VIIRS“)."),
    ("drop_type_after_filter", "<code>type</code>", "Nach dem Filter in jeder Archivzeile 0 und im NRT leer.",
     "Welche Regel gegriffen hat, folgt aus <code>source</code> (archive: type, nrt: Ortsmaske)."),
]

KPI_AS_FACTOR = {"D1a", "D1b", "D3a", "D8b"}
KPI_AS_SHARE = {"D2", "D3b", "D5b", "D5c", "D7", "U1a", "U1b", "U2a", "U2b", "U3", "M1a", "M1b", "M2", "N4a", "N4b"}
KPI_SCIENTIFIC = {"D10", "D11", "N2"}
KPI_NAMES = {
    "Anzahl je Region x Tag: typischer Fehler": "Anzahl je Region und Tag (aktive Tage): typischer Fehler",
    "Anzahl je Region x Tag: 90-%-Fehler": "Anzahl je Region und Tag: 90-%-Fehler",
    "Gesamtverzerrung (Tag, Woche, Monat)": "Abweichung der Gesamtsumme (Tag, Woche, Monat)",
    "Monat: typischer Fehler": "Monat wie Version 1: typischer Fehler",
    "Monat: Klasse getroffen": "Monat wie Version 1: Klasse getroffen",
    "Monat: Kappa": "Monat wie Version 1: Kappa",
    "FRP je Region x Tag: R2": "FRP-Summe je Region und Tag: R²",
    "FRP je Region x Tag: Median-Verhaeltnis (untere Grenze)": "FRP-Summe: Median-Verhältnis Messung / Umrechnung",
    "FRP je Region x Tag: Median-Verhaeltnis (obere Grenze)": "FRP-Summe: Median-Verhältnis Messung / Umrechnung",
    "Grossfeuer-Tag je Region: Kappa": "Großfeuer-Tag je Region: Kappa",
    "Grossfeuer-Tag je Region: Recall": "Großfeuer-Tag je Region: gefunden (Recall)",
    "Grossfeuer-Tag je Region: Precision": "Großfeuer-Tag je Region: zutreffend (Precision)",
    "Grossfeuer-Tag je Zelle: Kappa": "Großfeuer-Tag je 0,25°-Zelle: Kappa",
    "Staerkeklasse extreme exakt getroffen": "Stärkeklasse „extreme“ exakt getroffen",
    "Klimaprofil: R2": "Klimaprofil ±7 Tage: R²",
    "Klimaprofil: typischer Fehler": "Klimaprofil: typischer Fehler",
    "Klimaprofil: Korrelation je Region (Median)": "Klimaprofil: Korrelation je Region (Median)",
    "Klimaprofil: Korrelation je Region (Minimum)": "Klimaprofil: Korrelation je Region (Minimum)",
    "Kein Trend im Verhaeltnis (kleinster p-Wert)": "Kein Trend im Verhältnis Umrechnung / Messung (kleinster p-Wert)",
    "Roll-up: groesste Abweichung zur Summe der Tage": "Roll-up: größte Abweichung zur Summe der Tage",
    "Gewichte: groesste Abweichung zu n_harm / frp_harm": "Gewichte: größte Abweichung zu n_harm und frp_harm",
    "50-%-Band: kleinste Abdeckung je Groessenklasse": "50-%-Band: kleinste Abdeckung je Größenklasse",
    "50-%-Band: groesste Abdeckung je Groessenklasse": "50-%-Band: größte Abdeckung je Größenklasse",
    "90-%-Band: kleinste Abdeckung gesamt": "90-%-Band: kleinste Abdeckung gesamt",
    "90-%-Band: groesste Abdeckung gesamt": "90-%-Band: größte Abdeckung gesamt",
    "Stabilitaet der Fehlerfaktoren (groesste Abweichung)": "Stabilität der Fehlerfaktoren zwischen den Jahreshälften",
    "Ortsmaske: erkannte statische Quellen": "Ortsmaske: erkannte statische Quellen",
    "Ortsmaske: faelschlich entfernte Feuer": "Ortsmaske: fälschlich entfernte Feuer",
    "Hotspots mit Region": "Hotspots mit Region",
    "day_status lueckenlos, 0 gegen NA korrekt, Datumsfelder als DATE": "day_status lückenlos, 0 gegen leer korrekt, Datumsfelder als DATE",
    "Zeilenbilanz geht auf": "Zeilenbilanz geht auf",
    "Zwei Laeufe ergeben dieselben Dateien": "Zwei Läufe ergeben dieselben Dateien",
    "Alle Tests bestanden": "Alle Tests bestanden",
    "Schema gleich Dokumentation": "Schema gleich Dokumentation",
    "VIIRS-Mittel / SNPP je Region x Jahr: Median (untere Grenze)": "VIIRS-Mittel / SNPP je Region und Jahr: Median",
    "VIIRS-Mittel / SNPP je Region x Jahr: Median (obere Grenze)": "VIIRS-Mittel / SNPP je Region und Jahr: Median",
    "VIIRS-Mittel / SNPP: kleinstes Verhaeltnis je Region": "VIIRS-Mittel / SNPP: kleinstes Verhältnis je Region (Abdeckung)",
    "Gewichte 1/k: Abweichung zu n_viirs / frp_viirs": "Gewichte 1/k: größte Abweichung zu n_viirs und frp_viirs",
    "Mittel genauer als ein Satellit (gewonnene Rotationen)": "Mittel genauer als ein einzelner Satellit (gewonnene Rotationen von 3)",
    "Ortsmaske je VIIRS-Satellit: kleinster Recall": "Ortsmaske je VIIRS-Satellit: kleinster Recall",
    "Ortsmaske je VIIRS-Satellit: hoechste Fehlentfernung": "Ortsmaske je VIIRS-Satellit: höchste Fehlentfernung",
    "Schema gleich in Parquet, CSV, Katalog und data_dictionary.md": "Schema gleich in Parquet, CSV, Katalog und data_dictionary.md",
}

FRONTEND_MAP = [
    ("Karte mit einzelnen Feuerpunkten", "<code>hotspots_harmonised</code>",
     "<code>latitude</code>, <code>longitude</code>, <code>obs_date</code>, <code>frp</code>, <code>frp_class</code>, <code>satellite</code>, <code>sensor</code>, <code>source</code>. Mit <code>in_series_n</code> = wahr gibt es ab 2012 keine MODIS-Doppelten; ab 2018 kann ein Feuer als Punkt von SNPP und NOAA-20/21 erscheinen (Filter nach <code>satellite</code>)."),
    ("Sechseck-Heatmap", "<code>hotspots_harmonised</code>",
     "<code>h3_cell</code> (Auflösung 8). Gröber mit <code>h3.cell_to_parent</code>, Summe von <code>weight_n</code> je Zelle."),
    ("Stärke eines Tages je Region", "<code>activity_daily_harmonised</code>",
     "<code>frp_harm</code>, <code>strength_class</code>, <code>big_fire_day</code> mit den Bändern <code>frp_harm_lo50</code> bis <code>frp_harm_hi90</code>."),
    ("Verlauf über die Jahre", "<code>activity_daily_harmonised</code> + <code>roll_up_daily</code>",
     "<code>n_harm</code>, <code>frp_harm</code> je Woche, Monat oder Jahr. Unvollständige Zeiträume haben keinen Wert."),
    ("Kalender der typischen Gefahrenzeiten", "<code>build_day_of_year_climatology</code>",
     "<code>mean_n_harm_all</code>, <code>p_fire_day_viirs</code>, <code>p_big_fire_day_viirs</code>, Quantile als „übliche Spanne“."),
    ("Aktueller Monat gegen die Historie", "<code>month_to_date_vs_history</code>",
     "<code>n_harm_ratio_to_median</code>, <code>n_harm_percentile</code>, <code>as_of</code>."),
    ("Frei gezeichnete Fläche oder Koordinate", "<code>hotspots_harmonised</code> + <code>aggregate_hotspots</code>",
     "SUM(<code>weight_n</code>) und SUM(<code>frp</code> × <code>weight_frp</code>). Unsicherheit über <code>estimate_uncertainty</code>."),
    ("CSV-Download einer Suche", "<code>hotspots_harmonised</code> + <code>select_hotspots</code>, <code>write_hotspots_csv</code>",
     "Alle Punktspalten samt <code>confidence_raw</code>, <code>scan</code>, <code>track</code> für Fachleute."),
    ("„Kein Feuer“ oder „keine Daten“?", "<code>day_status</code>",
     "<code>is_complete_day</code>, <code>is_provisional</code>, <code>possible_gap</code>."),
    ("Fehlerangabe zu jeder Zahl", "Bandspalten, <code>reliability</code>, <code>quality_by_scale</code>",
     "Je Zeile fertig berechnet. Für eigene Aggregate schlägt <code>estimate_uncertainty</code> nach."),
]

RECIPES = r"""from aggregation.loading import load_table
from aggregation.roll_up import roll_up_daily, add_uncertainty_to_periods
from aggregation.hotspot_queries import select_hotspots, aggregate_hotspots, write_hotspots_csv, approximate_area_km2
from aggregation.uncertainty import estimate_uncertainty, area_scale_for
from aggregation.climatology import build_day_of_year_climatology
from aggregation.month_to_date import month_to_date_vs_history

daily    = load_table("data/harmonised/activity_daily_harmonised.parquet")
hotspots = load_table("data/harmonised/hotspots_harmonised.parquet")
quality  = load_table("data/harmonised/quality_by_scale.parquet")

# Monatsansicht mit Fehlerbändern
monthly = add_uncertainty_to_periods(roll_up_daily(daily, "month"), quality, config)

# Karte ohne Doppelte für einen Zeitraum
points = select_hotspots(hotspots, {"bbox": [-9.5, 36.0, 3.3, 43.8]}, ("2025-08-01", "2025-08-31"))
points = points[points["in_series_n"]]

# Frei gezeichnete Fläche: Zahl, Stärke und Unsicherheit
area  = {"polygon": [[-8.6, 41.0], [-7.4, 41.0], [-7.4, 42.0], [-8.6, 42.0]]}
total = aggregate_hotspots(hotspots, area, ("2005-08-01", "2005-08-31")).iloc[0]
band  = estimate_uncertainty(total["n_harm"], total["n_harm"], "count", area_scale_for(approximate_area_km2(area), config),
                             "month", "modis_pair_scaled", total["n_measured"] / max(total["n_points_in_series"], 1), quality, config)

# Kalender und laufender Monat
calendar = build_day_of_year_climatology(daily, config)
current  = month_to_date_vs_history(daily, "2026-11-14")

# CSV-Download
write_hotspots_csv(points, "suche.csv")"""

FRONTEND_RULES = [
    ("Vor 2012 immer mit Band.", "Ein umgerechneter Wert ist ein Erwartungswert. Die Bandspalten sind fertig berechnet, <code>reliability</code> taugt als Ampel."),
    ("0 ist nicht immer „kein Feuer“.", "Vor 2012 heißt 0 oft nur, dass MODIS nichts gesehen hat. <code>n_harm_hi90</code> sagt, wie viel es höchstens gewesen sein dürfte."),
    ("Leer ist nicht 0.", "Leere Werte heißen „keine Daten“ oder „Satellit nicht in Betrieb“. Grau zeigen, nicht als ruhigen Tag."),
    ("Klassenfilter nur auf der Karte.", "Summen mit Filter auf <code>frp_class</code> oder <code>confidence_class</code> sind vor 2012 falsch skaliert."),
    ("Pixelwerte nicht zwischen Sensoren vergleichen.", "<code>frp</code> je Punkt, <code>frp_class</code> und <code>confidence_class</code> bedeuten bei MODIS und VIIRS Verschiedenes."),
    ("Gewichte sind keine Eigenschaft des Punkts.", "<code>weight_n</code> = 3 heißt nicht „drei Feuer“ und 1/3 nicht „ein drittel Feuer“. Nur als Summe verwenden, nie im Popup anzeigen."),
    ("Mehrere VIIRS-Satelliten.", "Ab 2018 messen SNPP und NOAA-20, ab 2023 auch NOAA-21. Die Tageswerte sind ihr Mittel (<code>n_viirs</code>). Punkte nicht zählen, sondern <code>weight_n</code> summieren."),
    ("Feuertage und Wahrscheinlichkeiten nur ab 2012.", "MODIS meldet an etwa 60 % der Tage mit VIIRS-Feuer nichts. <code>n_days_with_fire</code> und die <code>p_*</code>-Spalten kommen deshalb nur aus VIIRS."),
    ("Vorläufige Daten kennzeichnen.", "<code>source</code> = nrt und <code>is_provisional</code> = wahr können sich später leicht ändern."),
]


def fill(template: str, values: dict[str, str], blocks: dict[str, str]) -> str:
    """Setzt Zahlen ({{name}}) und Bausteine ([[name]]) in einen Text ein. Fehlende Namen sind ein Fehler."""
    filled = re.sub(r"\[\[(\w+)\]\]", lambda match: blocks[match.group(1)], template)
    return re.sub(r"\{\{(\w+)\}\}", lambda match: values[match.group(1)], filled)


OVERVIEW_BODY = r"""
<main>
<p class="eyebrow">NASA Space Apps 2026 · FIRMS MODIS → VIIRS · Iberien · Tagesstufe</p>
<h1>Tägliche Harmonisierungs-Pipeline</h1>
<p class="lede">Die Pipeline bringt MODIS und VIIRS je Region und Tag auf eine gemeinsame Skala, legt den Faktor auf jeden einzelnen Hotspot und liefert zu jeder Zahl ihre Unsicherheit. Diese Seite beschreibt Aufbau, Funktionen und Prüfung. Die Spalten erklärt der <a href="column_guide.html">Spaltenbericht</a>.</p>
<p class="status">{{status_text}}</p>
<p>Seit Schema-Version 2 ist die VIIRS-Referenz das Mittel aus SNPP, NOAA-20 und NOAA-21. Wie das gebaut und geprüft wurde, steht in <a href="viirs_extension.html">VIIRS-Erweiterung</a>.</p>

<div class="tiles">
<div class="tile"><b>{{rows_kept}}</b><span>Hotspots bleiben von {{rows_read}} gelesenen Zeilen, {{rows_in_series}} davon zählen in der Reihe</span></div>
<div class="tile"><b>{{daily_rows}}</b><span>Tageszeilen: {{n_regions}} Regionen × {{n_days}} Tage von {{first_date}} bis {{last_date}}</span></div>
<div class="tile"><b>× {{d1}}</b><span>typischer Fehler der Anzahl je Region und Tag, je Monat × {{d3}}</span></div>
<div class="tile"><b>{{runtime}} s</b><span>Laufzeit aller Stufen mit {{n_tests}} Tests</span></div>
</div>

<h2>Datenfluss</h2>
<div class="flow">
<div class="layer l-src"><i>Quelle</i><b>8 FIRMS-CSVs</b><span>MODIS, VIIRS SNPP, NOAA-20 und NOAA-21, je Archiv und NRT</span></div>
<div class="layer l-raw"><i>data/raw</i><b>Raw-Parquet</b><span>1:1, typisiert, alle Originalspalten</span></div>
<div class="layer l-proc"><i>data/processed</i><b>Bereinigt</b><span>hotspots_clean, daily_grid, Einheiten der Kreuzvalidierung</span></div>
<div class="layer l-harm"><i>data/harmonised</i><b>Harmonisiert</b><span>Tagesdatensatz, gewichtete Hotspots, day_status, Fehlermodell</span></div>
<div class="layer l-agg"><i>aggregation/</i><b>Abgeleitet</b><span>Woche bis Jahr, Flächen, Klimaprofil, laufender Monat. Wird berechnet, nicht gespeichert.</span></div>
</div>
<p>Einziger Einstieg ist <code>run_pipeline.py</code>, alle Parameter stehen in <code>pipeline_config.yaml</code>. Die Pipeline schreibt nur den Tagesdatensatz und die Punktdaten. Gröbere Zeitschritte und Flächen entstehen im Modul <code>aggregation/</code>, das nicht zum Orchestrator gehört und nie in <code>data/</code> schreibt. So gibt es jede Zahl nur einmal.</p>
[[stages]]

<h2>Funktionskatalog</h2>
<p>Jede Funktion, die Daten umformt, mit dem Grund, warum ihr Vorgehen gilt. Die ausführliche Fassung steht im Docstring.</p>
[[catalogue]]

<h2>Gedroppte Spalten</h2>
<p>Die Spalten fehlen in allen Tabellen ab <code>data/processed</code>. Im Raw-Parquet und in <code>rejected_hotspots</code> bleiben sie erhalten.</p>
[[dropped]]

<h2>Zeilenbilanz</h2>
<p>Gelesen {{rows_read}} = behalten {{rows_kept}} + verworfen {{rows_rejected}}.</p>
[[balance]]
<p class="note">{{unreadable_note}}</p>

<h2>Das Fehlermodell an einem Beispiel</h2>
<p>Der Fehler einer umgerechneten Zahl hängt von ihrer Größe ab. Die Tabelle zeigt die Anzahl je NUTS-2-Region, links pro Tag und rechts pro Monat (Basis Aqua + Terra, aus der Kreuzvalidierung).</p>
[[quality_example]]
<p>Lesebeispiel: Ergibt die Umrechnung für einen Monat 50 Erkennungen, liegt die VIIRS-Messung in der Hälfte der Fälle zwischen {{example_lo50}} und {{example_hi50}} und in neun von zehn Fällen zwischen {{example_lo90}} und {{example_hi90}}. Ergibt sie für einen Tag 0, misst VIIRS in 90 % der Fälle höchstens {{zero_day_p90}}, für einen Monat höchstens {{zero_month_p90}}.</p>

<h2>Prüfung gegen die Schwellen</h2>
<p>Die Schwellen standen vor der ersten Messung in der Konfiguration. Genauigkeit ist außerhalb der Trainingsdaten gemessen: Jedes Jahr 2012 bis 2021 wird mit Faktoren aus den übrigen Jahren umgerechnet. D1 bis D8 gelten für die {{n_eval_regions}} Regionen mit mindestens 2.000 VIIRS-Erkennungen.</p>
[[kpis]]
<ul>
[[kpi_notes]]
</ul>

<h2>Hypothesen</h2>
[[hypotheses]]

<h2>Iterationsprotokoll</h2>
[[iterations]]

<details><summary>Faktoren je Region</summary><div>[[factors]]</div></details>

<h2>Bekannte Grenzen</h2>
<ul>
<li><strong>Genaue Tageswerte gibt es nur ab dem 20.01.2012.</strong> Davor ist jeder Tageswert eine Schätzung: MODIS meldet an etwa 60 % der Tage mit VIIRS-Feuer nichts.</li>
<li><strong>Nur Iberien.</strong> Die Faktoren gelten nicht für andere Regionen.</li>
<li><strong>Bänder für gemessene VIIRS-Werte sind eine Annahme</strong> (Zählrauschen mit Mindestfaktor). Seit 2023 lässt sich das Instrumentenrauschen mit drei Satelliten schätzen (Prüfung N3), die Bänder nutzen das noch nicht.</li>
<li><strong>Das gemeinsame Gebiet ist aus den Daten gelernt</strong> (0,25°-Zellen mit MODIS- oder SNPP-Erkennungen). Am Rand einer Zelle können NOAA-Punkte knapp außerhalb des SNPP-Gebiets mitzählen.</li>
<li><strong>Gewichte stellen keine verpassten Feuer wieder her.</strong> Auf kleinen Flächen und kurzen Zeiträumen ist die Summe entsprechend unsicher.</li>
<li><strong>Ab 2022 gibt es ohne VIIRS keinen Wert,</strong> weil MODIS wegen der Bahndrift nicht mehr umgerechnet wird ({{none_days}} Tage ohne Wert; seit NOAA-20/21 reicht die Reihe bis zum letzten Datentag).</li>
<li><strong>Ausfälle innerhalb des Produktfensters</strong> werden nur markiert (<code>possible_gap</code>: {{gap_days}} Tage), nicht korrigiert.</li>
<li><strong>Die Ortsmaske kennt keine neuen Anlagen</strong> und trifft MODIS schlechter als VIIRS.</li>
</ul>

<h2>Ausführen</h2>
<pre>cd harmonisation
.venv/bin/python run_pipeline.py                  # alle Stufen
.venv/bin/python run_pipeline.py --force          # alles neu, prüft den Determinismus
.venv/bin/python -m pytest -q tests aggregation/tests
.venv/bin/python data_analysis/experiments/evaluate_hypotheses.py
.venv/bin/python docs/build_docs.py               # Doku neu bauen</pre>
</main>
"""

GUIDE_BODY = r"""
<main>
<p class="eyebrow">NASA Space Apps 2026 · FIRMS harmonisiert · für das Frontend</p>
<h1>Spaltenbericht</h1>
<p class="lede">Jede Tabelle der täglichen Harmonisierung mit ihren Spalten: was die Spalte enthält, wie leere Werte und Nullen zu lesen sind und wofür sie im Frontend taugt. Tabellen und Texte kommen aus dem Spaltenkatalog, der auch das Schema prüft.</p>

<nav class="toc" aria-label="Inhalt"><ul>
<li><a href="#funktionen">Welche Daten für welche Funktion</a></li>
[[toc]]
<li><a href="#regeln">Regeln für die Darstellung</a></li>
<li><a href="#beispiele">Beispiele im Code</a></li>
</ul></nav>

<h2 id="funktionen">Welche Daten für welche Funktion</h2>
[[frontend_map]]
<p><strong>Dateiformate:</strong> Jede Tabelle liegt als Parquet in <code>data/harmonised/</code> und als CSV in <code>data/harmonised/csv/</code> (UTF-8, Komma als Trennzeichen, Punkt als Dezimalzeichen, Tage als <code>2025-08-01</code>, Zeitstempel als <code>2025-08-01T13:20:00</code> in UTC, Wahrheitswerte als <code>true</code>/<code>false</code>). Ein leeres Feld heißt „kein Wert“ und ist etwas anderes als 0. Parquet ist die Quelle, die CSVs entstehen bei jedem Lauf neu.</p>
<p>Gespeichert sind nur der Tagesdatensatz und die Punktdaten. Woche, Monat, Jahr, Klimaprofil und Flächensummen berechnet das Modul <code>aggregation/</code> daraus. Tabellen bitte mit <code>aggregation.loading.load_table</code> lesen, dann sind Datumsspalten direkt nutzbar.</p>

[[tables]]

<h2 id="regeln">Regeln für die Darstellung</h2>
[[rules]]

<h2 id="beispiele">Beispiele im Code</h2>
<p><code>config</code> ist die geladene <code>pipeline_config.yaml</code> (<code>pipeline.config.load_config()</code>).</p>
<pre><code>[[recipes]]</code></pre>
</main>
"""

REJECT_REASONS = {
    "type_2": "statisch laut type 2 (Industrie, Fackeln), Archiv",
    "type_3": "statisch laut type 3 (auf See), Archiv",
    "type_1": "statisch laut type 1 (Vulkan), Archiv",
    "static_mask": "statisch laut Ortsmaske, NRT",
    "duplicate": "Duplikat zwischen Archiv und NRT",
    "invalid_value": "ungültiger oder unlesbarer Wert",
    "outside_common_area": "außerhalb des Gebiets von MODIS und SNPP (NOAA-Downloads reichen weiter)",
}

ITERATIONS = [
    ("Aufbau", "Eine Zeile der VIIRS-Archiv-CSV enthält eingefügten Text in der Spalte <code>track</code> (Datei am 13.11. um 21:56 verändert, im ZIP-Original korrekt). Das Einlesen brach ab.",
     "Einlesen fängt unlesbare Werte ab, die Zeile wird als <code>invalid_value</code> verworfen und gemeldet. Die Quelldatei wurde nicht verändert."),
    ("Iteration 1", "Alle Schwellen gemessen. Verfehlt: U3 (Stabilität der Fehlerfaktoren, 17,7 % bei Grenze 15 %) in der FRP-Klasse 0 bis 10 MW pro Tag. Dazu ein Messfehler: Die Abdeckung der Bänder wurde über beide Prüfrichtungen gemittelt, wodurch sich Abweichungen aufhoben.",
     "Messung korrigiert (jede Richtung einzeln, die ungünstigere zählt). Hypothesen H1 bis H5 geprüft."),
    ("Iteration 2", "FRP-Größenklassen 0 bis 10 und 10 bis 100 MW zusammengelegt (zu wenige und zu verrauschte Fälle). Großfeuer-Schwelle für umgerechnete Tage von 100 auf 80 MW (H3).",
     "Alle Schwellen erfüllt. Stopp laut Regel."),
    ("VIIRS-Erweiterung, Aufbau", "NOAA-20/21 als weitere VIIRS-Satelliten. Erster Download deckte den Nordosten nicht ab (Katalonien 0,44 von SNPP), der zweite reichte weiter als MODIS/SNPP.",
     "Neuer Download; gemeinsames Gebiet aus den MODIS-/SNPP-Erkennungen. Danach alle Regionen 0,83 bis 1,23 von SNPP."),
    ("VIIRS-Erweiterung, Iteration 1", "Verfehlt: U1b (50-%-Band 0,614 bei Grenze 0,58) und N4b (Fehlentfernung NOAA-20 2,2 % bei Grenze 2 %).",
     "Kalibrierung und Fehlermodell gegen SNPP allein (gleiches Rauschen im ganzen Fenster), Ortsmaske je Sensor. Alle {{n_kpis}} Schwellen erfüllt, keine gesenkt."),
]
