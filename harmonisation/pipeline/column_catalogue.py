"""Spaltenkatalog: die eine Quelle fuer Schema, Datenwoerterbuch und Spaltenbericht.

Jede Ausgabetabelle steht hier mit ihren Spalten in fester Reihenfolge. Die Schemapruefung liest
daraus die erwarteten Spalten, die Dokumentation (docs/data_dictionary.md, docs/column_guide.html)
wird daraus erzeugt. Eine Spalte kann also nicht existieren, ohne beschrieben zu sein.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    """Eine Spalte: Name, Typ, Einheit, Bedeutung, Lesart von 0 und leer, Nutzung im Frontend."""
    name: str
    dtype: str
    unit: str
    meaning: str
    empty: str
    frontend: str


@dataclass(frozen=True)
class Table:
    """Eine Tabelle: Titel, Zeilenschluessel, Ablage, Zweck, Spalten. `stored` ist falsch fuer Funktionsergebnisse."""
    title: str
    grain: str
    location: str
    purpose: str
    columns: tuple[Column, ...]
    stored: bool = True


C = Column
BASIS_TEXT = ("viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled "
              "oder none (keine zulässige Quelle)")

HOTSPOT_BASE = (
    C("hotspot_id", "string", "–", "Stabile Kennung der Erkennung: Hash aus Satellit, Koordinaten, Datum und Uhrzeit.",
      "nie leer, eindeutig", "Schlüssel für Auswahl auf der Karte, Deep-Links und Wiedererkennen beim Nachladen."),
    C("latitude", "double", "Grad", "Geografische Breite der Pixelmitte (WGS84).", "nie leer",
      "Position des Punkts auf der Karte, räumliche Filter."),
    C("longitude", "double", "Grad", "Geografische Länge der Pixelmitte (WGS84).", "nie leer",
      "Position des Punkts auf der Karte, räumliche Filter."),
    C("cell_id", "string", "–", "Rasterzelle von 0,25° als „Breitenindex_Längenindex“ (Index = floor(Koordinate / 0,25)).",
      "nie leer", "Kacheln auf der Karte einfärben, schnelle Vorfilterung großer Flächen."),
    C("h3_cell", "string", "–", "H3-Zelle der Pixelmitte (Sechseck-Raster, Auflösung 8, etwa 0,74 km²), z. B. „88390ca343fffff“.",
      "nie leer", "Sechseck-Heatmap, Nachbarschaftsabfragen. Gröbere Zellen per h3.cell_to_parent (z. B. Auflösung 5 oder 6 für ganz Iberien)."),
    C("acq_date", "date", "UTC", "Datum der Messung in UTC, wie von FIRMS geliefert.", "nie leer",
      "Anzeige im Popup und im CSV. Für Zeitfilter und Summen besser obs_date nehmen."),
    C("acq_time", "string", "UTC, HHMM", "Uhrzeit der Messung als vierstelliger Text, z. B. „0114“.", "nie leer",
      "Nur fürs CSV (Originalformat). Zum Rechnen acq_datetime_utc verwenden."),
    C("acq_datetime_utc", "timestamp", "UTC", "Datum und Uhrzeit der Messung als echter Zeitstempel.", "nie leer",
      "Zeitachse, Sortierung, Animation des Tagesverlaufs, Anzeige der Überflugzeit."),
    C("obs_date", "date", "–", "Tag, zu dem der Punkt in allen Summen zählt (Zuordnung laut Konfiguration: UTC-Datum oder Sonnendatum).",
      "nie leer", "Der Zeitfilter der Karte und der Schlüssel zu day_status und zur Tagestabelle."),
    C("local_solar_hour", "double", "Stunden 0–24", "Lokale Sonnenzeit des Überflugs: UTC-Stunde + Länge / 15.", "nie leer",
      "Tageszeit im Popup („erkannt um 13:20 Ortszeit“), Auswertung nach Tageszeit."),
    C("satellite", "string", "–", "Satellit: Terra, Aqua (MODIS), SNPP, N20 (NOAA-20) oder N21 (NOAA-21) (VIIRS).", "nie leer",
      "Herkunft im Popup und im CSV. Nicht zum Vergleichen von Zahlen zwischen Satelliten."),
    C("sensor", "string", "–", "Instrument: MODIS (Terra, Aqua, 1-km-Pixel) oder VIIRS (SNPP, NOAA-20, NOAA-21, 375-m-Pixel).", "nie leer",
      "Symbol oder Legende auf der Karte. Pflichtbegleiter für frp_class und confidence_class."),
    C("source", "string", "–", "archive (endgültig, geprüft) oder nrt (vorläufig, wird später durch Archivdaten ersetzt).", "nie leer",
      "Vorläufige Punkte kennzeichnen, z. B. gestrichelt oder mit Hinweis „vorläufig“."),
    C("daynight", "string", "–", "D (Tag-Überflug) oder N (Nacht-Überflug).", "nie leer", "Filter Tag/Nacht, Symbol im Popup."),
    C("frp", "double", "MW", "Strahlungsleistung des Feuers in diesem Pixel (Fire Radiative Power).", "0 möglich, nie leer",
      "Größe oder Farbe des Punkts. Nur innerhalb eines Sensors vergleichen: ein VIIRS-Pixel ist kleiner und zeigt weniger MW für dasselbe Feuer."),
    C("frp_class", "string", "–", "Klasse der Pixel-FRP: low (unter 10 MW), mid (10–50 MW), high (ab 50 MW).", "nie leer",
      "Farbstufen der Punkte, Filter auf der Karte und im CSV. Nicht für Summen über die Jahre: vor 2012 fehlen die schwachen Feuer."),
    C("confidence_class", "string", "–", "Güte der einzelnen Erkennung laut FIRMS: low, nominal, high.", "leer, wenn der Originalwert unlesbar ist",
      "Filter „unsichere Erkennungen ausblenden“. Nur zusammen mit sensor: VIIRS-„high“ bedeutet nur „Kanal gesättigt“."),
    C("confidence_raw", "string", "–", "Originalwert von FIRMS: Zahl 0–100 bei MODIS, l / n / h bei VIIRS.", "nie leer",
      "Nur fürs CSV für Fachleute. Im UI nicht nötig."),
    C("scan", "double", "km", "Pixelbreite quer zur Flugrichtung.", "nie leer", "Fußabdruck des Pixels zeichnen (zusammen mit track)."),
    C("track", "double", "km", "Pixelbreite in Flugrichtung.", "nie leer", "Fußabdruck des Pixels zeichnen (zusammen mit scan)."),
    C("pixel_area_km2", "double", "km²", "Fläche des Pixels am Boden: scan × track.", "nie leer",
      "Punkt in echter Größe darstellen. Große Werte heißen Bildrand und damit gröbere Ortsangabe."),
    C("region_id", "string", "–", "NUTS-2-Region des Punkts (Stand 2021), z. B. ES30. Nur Untersuchungsregionen (nuts.study_regions).", "nie leer",
      "Schneller Filter „Region wählen“, Verknüpfung zur Tagestabelle."),
    C("country", "string", "–", "Land: die ersten zwei Zeichen von region_id (ES, PT).", "nie leer", "Filter nach Land."),
)

HOTSPOT_WEIGHTS = (
    C("in_series_n", "boolean", "–", "Wahr, wenn der Satellit des Punkts an diesem Tag zur Basis der Anzahl gehört und in Betrieb ist.", "nie leer",
      "Karte ohne Sensor-Doppelte: nur Punkte mit in_series_n = wahr zeigen (ab 2012 nur VIIRS, davor MODIS). Ab 2018 kann dasselbe Feuer "
      "als Punkt von SNPP und von NOAA-20/21 erscheinen (andere Überflugzeit), Filter nach satellite möglich."),
    C("in_series_frp", "boolean", "–", "Wahr, wenn der Punkt in die harmonisierte FRP-Summe eingeht.", "nie leer",
      "Wie in_series_n, für Darstellungen der Stärke."),
    C("weight_n", "double", "VIIRS-Äquivalente", "Beitrag des Punkts zur harmonisierten Anzahl: 1/k bei VIIRS (k = an dem Tag aktive VIIRS-Satelliten, 1 bis 3), "
      "Regionsfaktor bei MODIS, 0 außerhalb der Reihe.",
      "0 = zählt nicht mit", "Harmonisierte Anzahl einer beliebigen Fläche: SUM(weight_n). Nicht als Eigenschaft des Punkts anzeigen."),
    C("weight_frp", "double", "Faktor", "Faktor, mit dem die FRP des Punkts in die harmonisierte Summe eingeht.", "0 = zählt nicht mit",
      "Harmonisierte Stärke einer beliebigen Fläche: SUM(frp × weight_frp)."),
    C("basis_count", "string", "–", f"Quelle der Anzahl an diesem Tag: {BASIS_TEXT}.", "none = Tag ohne Wert",
      "Nachvollziehen im CSV, Hinweis „gemessen“ oder „umgerechnet“."),
    C("basis_frp", "string", "–", f"Quelle der FRP-Summe an diesem Tag: {BASIS_TEXT}.", "none = Tag ohne Wert",
      "Wie basis_count, für die Stärke."),
)


def band_columns(value: str, unit: str, noun: str) -> tuple[Column, ...]:
    """Die vier Fehlerband-Spalten einer Groesse."""
    texts = (("lo50", "Untergrenze des typischen Bereichs (enthält die Messung in etwa der Hälfte der Fälle)."),
             ("hi50", "Obergrenze des typischen Bereichs."),
             ("lo90", "Untergrenze des weiten Bereichs (enthält die Messung in etwa neun von zehn Fällen)."),
             ("hi90", "Obergrenze des weiten Bereichs. Bei umgerechneter 0: so viel misst VIIRS in 90 % solcher Fälle höchstens."))
    use = {"lo50": "Dunkles Fehlerband um den Wert.", "hi50": "Dunkles Fehlerband um den Wert.",
           "lo90": "Helles Fehlerband, Fehlerbalken.", "hi90": "Helles Fehlerband, Fehlerbalken, Text „0, bis etwa …“."}
    return tuple(C(f"{value}_{key}", "double", unit, f"{noun}: {text}", "leer, wenn der Wert leer ist", use[key]) for key, text in texts)


DAILY = (
    C("region_id", "string", "–", "NUTS-2-Region (Stand 2021).", "nie leer", "Auswahl der Region, Schlüssel zusammen mit date."),
    C("country", "string", "–", "Land (ES, PT).", "nie leer", "Filter und Gruppierung nach Land."),
    C("region_name", "string", "–", "Klarname der Region, z. B. „Comunidad de Madrid“.", "nie leer", "Beschriftung in Auswahlliste, Karte und Diagramm."),
    C("date", "date", "–", "Tag (Zuordnung wie obs_date der Hotspots).", "nie leer, lückenlos ab 2001-01-01", "Zeitachse von Kalender und Verlauf."),
    C("n_aqua", "double", "Erkennungen", "Rohzahl Aqua (MODIS) an diesem Tag.", "0 = kein Feuer, leer = Aqua nicht in Betrieb", "Nur Tooltip „Rohdaten“ und Nachrechnen."),
    C("n_terra", "double", "Erkennungen", "Rohzahl Terra (MODIS) an diesem Tag.", "0 = kein Feuer, leer = Terra nicht in Betrieb", "Nur Tooltip „Rohdaten“ und Nachrechnen."),
    C("n_snpp", "double", "Erkennungen", "Rohzahl SNPP (VIIRS) an diesem Tag.", "0 = kein Feuer, leer = SNPP nicht in Betrieb (vor 20.01.2012)", "Nur Tooltip „Rohdaten“ und Nachrechnen."),
    C("n_noaa20", "double", "Erkennungen", "Rohzahl NOAA-20 (VIIRS) an diesem Tag.", "0 = kein Feuer, leer = NOAA-20 nicht in Betrieb (vor 01.04.2018)", "Nur Tooltip „Rohdaten“ und Nachrechnen."),
    C("n_noaa21", "double", "Erkennungen", "Rohzahl NOAA-21 (VIIRS) an diesem Tag.", "0 = kein Feuer, leer = NOAA-21 nicht in Betrieb (vor 01.03.2023)", "Nur Tooltip „Rohdaten“ und Nachrechnen."),
    C("n_viirs", "double", "Erkennungen", "VIIRS-Referenz: Mittel der Rohzahlen der an diesem Tag aktiven VIIRS-Satelliten (SNPP, NOAA-20, NOAA-21). "
      "An gemessenen Tagen gleich n_harm.", "0 = kein Feuer, leer = kein VIIRS-Satellit in Betrieb (vor 20.01.2012)", "Nur Tooltip „gemessen, Mittel aus k Satelliten“."),
    C("frp_aqua", "double", "MW", "FRP-Summe Aqua an diesem Tag.", "wie n_aqua", "Nur Tooltip und Nachrechnen."),
    C("frp_terra", "double", "MW", "FRP-Summe Terra an diesem Tag.", "wie n_terra", "Nur Tooltip und Nachrechnen."),
    C("frp_snpp", "double", "MW", "FRP-Summe SNPP an diesem Tag.", "wie n_snpp", "Nur Tooltip und Nachrechnen."),
    C("frp_noaa20", "double", "MW", "FRP-Summe NOAA-20 an diesem Tag.", "wie n_noaa20", "Nur Tooltip und Nachrechnen."),
    C("frp_noaa21", "double", "MW", "FRP-Summe NOAA-21 an diesem Tag.", "wie n_noaa21", "Nur Tooltip und Nachrechnen."),
    C("frp_viirs", "double", "MW", "VIIRS-Referenz der Stärke: Mittel der FRP-Summen der aktiven VIIRS-Satelliten. An gemessenen Tagen gleich frp_harm.",
      "wie n_viirs", "Nur Tooltip und Nachrechnen."),
    C("basis_count", "string", "–", f"Quelle von n_harm: {BASIS_TEXT}.", "none = kein Wert", "Kennzeichnung „gemessen“ gegen „umgerechnet“, z. B. als Schraffur."),
    C("basis_frp", "string", "–", f"Quelle von frp_harm: {BASIS_TEXT}.", "none = kein Wert", "Wie basis_count, für die Stärke."),
    C("n_harm", "double", "VIIRS-Äquivalente", "Harmonisierte Anzahl der Erkennungen: gemessen (n_viirs) oder MODIS × Regionsfaktor.",
      "0 = keine Erkennung (vor 2012 oft nur „MODIS sah nichts“), leer = Tag ohne Basis", "Hauptwert für Verlauf und Kalender. Vor 2012 immer mit Band zeigen."),
    C("frp_harm", "double", "MW (VIIRS-Äquivalente)", "Harmonisierte FRP-Summe des Tages, das Maß für die Stärke.", "wie n_harm",
      "Stärke eines Tages als Zahl, Höhe eines Balkens, Farbintensität im Kalender."),
    C("factor_count", "double", "Faktor", "Auf die Anzahl angewandter Faktor (1 bei Messung).", "leer, wenn kein Wert", "Tooltip „umgerechnet mit × 2,7“."),
    C("factor_frp", "double", "Faktor", "Auf die FRP angewandter Faktor (1 bei Messung).", "leer, wenn kein Wert", "Tooltip zur Stärke."),
    C("strength_class", "string", "–", "Stärkeklasse aus frp_harm: minor (unter 10 MW), moderate (10–100), strong (100–500), extreme (ab 500).",
      "leer, wenn kein Wert", "Farbe des Kalendertags. Vor 2012 ist nur „extreme“ verlässlich (siehe strength_confusion)."),
    C("big_fire_day", "boolean", "–", "Wahr an Tagen mit frp_harm ab 100 MW.", "leer, wenn kein Wert", "Markierung im Kalender, Zählung „Großfeuer-Tage“. Vor 2012 werden nicht alle erkannt."),
) + band_columns("n_harm", "VIIRS-Äquivalente", "Anzahl") + band_columns("frp_harm", "MW", "FRP-Summe") + (
    C("reliability", "string", "–", "Zuverlässigkeitsstufe: measured (gemessen), converted_solid (umgerechnet, ab 100 Erkennungen), converted_rough (umgerechnet, kleine Zahl).",
      "leer, wenn kein Wert", "Ampel oder Symbol neben dem Wert, Filter „nur gemessene Tage“."),
    C("is_complete_day", "boolean", "–", "Wahr, wenn der Tag für Anzahl und FRP eine Basis hat.", "nie leer", "Tage ohne Daten grau statt als 0 zeigen."),
    C("possible_gap", "boolean", "–", "Wahr, wenn der Basis-Satellit im ganzen Gebiet nichts meldet, obwohl die Nachbartage viel melden.", "nie leer",
      "Warnhinweis „möglicher Datenausfall“ statt „ruhiger Tag“."),
)

DAY_STATUS = (
    C("date", "date", "–", "Tag.", "nie leer, lückenlos", "Zeitachse. Jeder Tag kommt genau einmal vor."),
    C("viirs_operating", "boolean", "–", "Mindestens ein VIIRS-Satellit (SNPP, NOAA-20, NOAA-21) liefert an diesem Tag Daten. Dann ist der Tag gemessen.",
      "nie leer", "Erklärung, warum ein Tag gemessen oder umgerechnet ist."),
    C("snpp_operating", "boolean", "–", "SNPP (VIIRS) liefert an diesem Tag Daten.", "nie leer", "Tooltip „gemessen mit …“ (welche Satelliten im Mittel stecken)."),
    C("noaa20_operating", "boolean", "–", "NOAA-20 (VIIRS) liefert an diesem Tag Daten.", "nie leer", "Wie snpp_operating."),
    C("noaa21_operating", "boolean", "–", "NOAA-21 (VIIRS) liefert an diesem Tag Daten.", "nie leer", "Wie snpp_operating."),
    C("aqua_operating", "boolean", "–", "Aqua (MODIS) liefert an diesem Tag Daten.", "nie leer", "Wie snpp_operating."),
    C("terra_operating", "boolean", "–", "Terra (MODIS) liefert an diesem Tag Daten.", "nie leer", "Wie snpp_operating."),
    C("basis_count", "string", "–", f"Quelle der Anzahl an diesem Tag: {BASIS_TEXT}.", "none = Tag ohne Wert", "Abschnitte der Zeitachse einfärben (gemessen, umgerechnet, keine Daten)."),
    C("basis_frp", "string", "–", f"Quelle der FRP-Summe an diesem Tag: {BASIS_TEXT}.", "none = Tag ohne Wert", "Wie basis_count."),
    C("is_complete_day", "boolean", "–", "Wahr, wenn der Tag einen harmonisierten Wert hat.", "nie leer",
      "Die Kernfrage der Punktkarte: keine Punkte an einem vollständigen Tag = kein Feuer, an einem unvollständigen = keine Daten."),
    C("is_provisional", "boolean", "–", "Wahr, wenn der Tag auf vorläufigen NRT-Daten beruht.", "nie leer", "Hinweis „vorläufig, kann sich ändern“."),
    C("possible_gap", "boolean", "–", "Verdacht auf Datenausfall an diesem Tag.", "nie leer", "Warnsymbol auf der Zeitachse."),
)

CALIB = (
    C("region_id", "string", "–", "NUTS-2-Region.", "nie leer", "Schlüssel."),
    C("k_count_pair", "double", "Faktor", "VIIRS-Erkennungen je (Aqua + Terra)-Erkennung.", "nie leer", "Infotext „So wurde umgerechnet“."),
    C("k_count_aqua", "double", "Faktor", "VIIRS-Erkennungen je Aqua-Erkennung.", "nie leer", "Infotext."),
    C("k_count_terra", "double", "Faktor", "VIIRS-Erkennungen je Terra-Erkennung (für die Zeit vor Aqua).", "nie leer", "Infotext."),
    C("k_frp_pair", "double", "Faktor", "VIIRS-FRP je (Aqua + Terra)-FRP, ein Wert für alle Regionen.", "nie leer", "Infotext."),
    C("k_frp_aqua", "double", "Faktor", "VIIRS-FRP je Aqua-FRP, ein Wert für alle Regionen.", "nie leer", "Infotext."),
    C("k_frp_terra", "double", "Faktor", "VIIRS-FRP je Terra-FRP, ein Wert für alle Regionen.", "nie leer", "Infotext."),
    C("used_fallback_pair", "boolean", "–", "Wahr, wenn die Region zu wenige Daten hat und den Gesamtfaktor bekommt.", "nie leer", "Hinweis „Region mit wenig Daten“."),
    C("used_fallback_aqua", "boolean", "–", "Wie used_fallback_pair, für den Aqua-Faktor.", "nie leer", "Hinweis."),
    C("used_fallback_terra", "boolean", "–", "Wie used_fallback_pair, für den Terra-Faktor.", "nie leer", "Hinweis."),
    C("n_viirs_calib", "double", "Erkennungen", "VIIRS-Referenz (Mittel der aktiven VIIRS-Satelliten) der Region im Kalibrierfenster, summiert.", "nie leer", "Nicht nötig (Diagnose)."),
    C("n_pair_calib", "double", "Erkennungen", "Aqua + Terra-Erkennungen im Kalibrierfenster.", "nie leer", "Nicht nötig (Diagnose)."),
    C("n_aqua_calib", "double", "Erkennungen", "Aqua-Erkennungen im Kalibrierfenster.", "nie leer", "Nicht nötig (Diagnose)."),
    C("n_terra_calib", "double", "Erkennungen", "Terra-Erkennungen im Kalibrierfenster.", "nie leer", "Nicht nötig (Diagnose)."),
    C("k_count_pair_overall", "double", "Faktor", "Gesamtfaktor über alle Regionen (Aqua + Terra).", "nie leer", "Nicht nötig (Diagnose)."),
    C("k_count_aqua_overall", "double", "Faktor", "Gesamtfaktor über alle Regionen (Aqua).", "nie leer", "Nicht nötig (Diagnose)."),
    C("k_count_terra_overall", "double", "Faktor", "Gesamtfaktor über alle Regionen (Terra).", "nie leer", "Nicht nötig (Diagnose)."),
    C("calib_start", "string", "Datum", "Beginn des Kalibrierfensters.", "nie leer", "Infotext."),
    C("calib_end", "string", "Datum", "Ende des Kalibrierfensters.", "nie leer", "Infotext."),
)

QUALITY = (
    C("area_scale", "string", "–", "Flächenskala: cell (0,25°), nuts2, country, all (ganzes Gebiet).", "nie leer", "Nachschlagen: Skala passend zur gewählten Fläche."),
    C("grain", "string", "–", "Zeitschritt: day, week, month, quarter, year.", "nie leer", "Nachschlagen: passend zum gewählten Zeitraum."),
    C("quantity", "string", "–", "count (Anzahl) oder frp (FRP-Summe).", "nie leer", "Nachschlagen."),
    C("basis", "string", "–", "Basis der Umrechnung, für die die Zeile gilt.", "nie leer", "Nachschlagen."),
    C("size_class", "string", "–", "Größenklasse der umgerechneten Zahl, z. B. „0“, „5-20“, „>500“. „all“ = alle Klassen über 0.", "nie leer", "Nachschlagen nach der angezeigten Zahl."),
    C("class_upper", "double", "wie quantity", "Obergrenze der Klasse (einschließlich).", "unendlich bei der obersten Klasse", "Nachschlagen."),
    C("n_units", "double", "Fälle", "Zahl der Vergleichsfälle in der Kreuzvalidierung.", "nie leer", "Bei kleinen Werten den Fehler als „unsicher“ kennzeichnen."),
    C("median_factor_error", "double", "Faktor", "Typischer Fehler: die Hälfte der Fälle liegt näher am Messwert als dieser Faktor.", "nie leer", "Breite des dunklen Fehlerbands."),
    C("p90_factor_error", "double", "Faktor", "90-%-Fehler: neun von zehn Fällen liegen näher.", "nie leer", "Breite des hellen Fehlerbands."),
    C("abs_upper_p50", "double", "wie quantity", "Median der VIIRS-Messung in dieser Klasse.", "nie leer", "Für die Klasse 0: typischer wahrer Wert."),
    C("abs_upper_p90", "double", "wie quantity", "90-%-Quantil der VIIRS-Messung in dieser Klasse.", "nie leer", "Für die Klasse 0: Text „0, bis etwa …“."),
    C("coverage50_holdout_low", "double", "Anteil", "Geprüfte Trefferquote des 50-%-Bands auf zurückgehaltenen Jahren, ungünstigere Prüfrichtung.", "leer, wenn nicht prüfbar", "Nicht nötig (Nachweis der Ehrlichkeit)."),
    C("coverage50_holdout_high", "double", "Anteil", "Wie zuvor, günstigere Prüfrichtung.", "leer, wenn nicht prüfbar", "Nicht nötig (Nachweis)."),
    C("coverage90_holdout_low", "double", "Anteil", "Geprüfte Trefferquote des 90-%-Bands, ungünstigere Prüfrichtung.", "leer, wenn nicht prüfbar", "Nicht nötig (Nachweis)."),
    C("coverage90_holdout_high", "double", "Anteil", "Wie zuvor, günstigere Prüfrichtung.", "leer, wenn nicht prüfbar", "Nicht nötig (Nachweis)."),
    C("factor_shift", "double", "Anteil", "Unterschied des typischen Fehlers zwischen den beiden Jahreshälften.", "leer, wenn nicht prüfbar", "Nicht nötig (Nachweis)."),
    C("n_test", "double", "Fälle", "Zahl der Prüffälle (kleinere der beiden Prüfhälften).", "leer, wenn nicht prüfbar", "Nicht nötig."),
)

CONFUSION = (
    C("basis", "string", "–", "Basis der Umrechnung.", "nie leer", "Auswahl der passenden Zeilen."),
    C("measured_class", "string", "–", "Stärkeklasse laut VIIRS-Messung.", "nie leer", "Zeile der Vergleichsmatrix."),
    C("converted_class", "string", "–", "Stärkeklasse laut Umrechnung am selben Tag.", "nie leer", "Spalte der Vergleichsmatrix."),
    C("n_days", "double", "Tage", "Zahl der Region-Tage mit dieser Kombination.", "nie leer", "Infografik „Wie verlässlich ist die Klasse vor 2012?“."),
    C("share_of_measured_class", "double", "Anteil", "Anteil an allen Tagen der gemessenen Klasse.", "nie leer", "Text wie „starke Tage werden zu 7 von 10 richtig eingestuft“."),
)

BIG_FIRE = (
    C("area_scale", "string", "–", "nuts2 oder cell (0,25°).", "nie leer", "Auswahl."),
    C("basis", "string", "–", "Basis der Umrechnung.", "nie leer", "Auswahl."),
    C("threshold_measured_mw", "double", "MW", "Schwelle für gemessene Tage.", "nie leer", "Legende."),
    C("threshold_converted_mw", "double", "MW", "Schwelle für umgerechnete Tage.", "nie leer", "Legende."),
    C("recall", "double", "Anteil", "Anteil der gemessenen Großfeuer-Tage, die die Umrechnung auch zeigt.", "nie leer", "Hinweis „vor 2012 werden etwa x von 10 Großfeuer-Tagen erkannt“."),
    C("precision", "double", "Anteil", "Anteil der umgerechneten Großfeuer-Tage, die auch gemessen wurden.", "nie leer", "Hinweis zur Verlässlichkeit einer Markierung."),
    C("kappa", "double", "–", "Übereinstimmung über den Zufall hinaus (0 bis 1).", "nie leer", "Nicht nötig (Kennzahl für Fachleute)."),
    C("n_events_measured", "double", "Tage", "Gemessene Großfeuer-Tage.", "nie leer", "Nicht nötig."),
    C("n_events_converted", "double", "Tage", "Umgerechnete Großfeuer-Tage.", "nie leer", "Nicht nötig."),
    C("n_units", "double", "Tage", "Alle verglichenen Tage.", "nie leer", "Nicht nötig."),
)

ROLL_UP = (
    C("region_id", "string", "–", "NUTS-2-Region.", "nie leer", "Schlüssel."),
    C("grain", "string", "–", "Zeitschritt des Ergebnisses: week, month, quarter, year.", "nie leer", "Umschalter der Ansicht."),
    C("period_start", "date", "–", "Erster Tag des Zeitschritts (Montag, Monats-, Quartals- oder Jahreserster).", "nie leer", "Zeitachse."),
    C("period_end", "date", "–", "Letzter Kalendertag des Zeitschritts.", "nie leer", "Beschriftung."),
    C("n_days", "double", "Tage", "Zahl der Tage im Datensatz für diesen Zeitschritt.", "nie leer", "Nicht nötig."),
    C("n_days_complete", "double", "Tage", "Zahl der Tage mit Wert.", "nie leer", "Fortschritt „bisher 12 von 30 Tagen“."),
    C("is_complete_period", "boolean", "–", "Wahr, wenn jeder Kalendertag des Zeitschritts einen Wert hat.", "nie leer", "Unvollständige Zeiträume grau zeigen und nicht in Median oder Rang nehmen."),
    C("share_measured_days", "double", "Anteil", "Anteil der Tage mit gemessenem VIIRS (mindestens ein VIIRS-Satellit).", "nie leer", "Feinere Kennzeichnung gemischter Zeiträume."),
    C("basis_mix", "string", "–", "measured, converted oder mixed.", "nie leer", "Kennzeichnung „gemessen“, „umgerechnet“, „gemischt“."),
    C("basis_count_converted", "string", "–", "Basis der umgerechneten Tage des Zeitschritts (Anzahl).", "leer, wenn alle Tage gemessen sind", "Nachschlagen der Unsicherheit, Tooltip."),
    C("basis_frp_converted", "string", "–", "Basis der umgerechneten Tage des Zeitschritts (FRP).", "leer, wenn alle Tage gemessen sind", "Nachschlagen der Unsicherheit, Tooltip."),
    C("n_harm", "double", "VIIRS-Äquivalente", "Summe der harmonisierten Anzahl.", "leer bei unvollständigem Zeitraum", "Hauptwert für Monats- und Jahresansicht."),
    C("frp_harm", "double", "MW", "Summe der harmonisierten FRP.", "leer bei unvollständigem Zeitraum", "Stärke des Zeitraums."),
    C("n_harm_mean_per_day", "double", "je Tag", "Mittel pro Tag: n_harm / Tage.", "leer bei unvollständigem Zeitraum", "Vergleich verschieden langer Zeiträume."),
    C("frp_harm_mean_per_day", "double", "MW je Tag", "Mittel pro Tag: frp_harm / Tage.", "leer bei unvollständigem Zeitraum", "Vergleich verschieden langer Zeiträume."),
    C("n_big_fire_days", "double", "Tage", "Zahl der Großfeuer-Tage.", "leer bei unvollständigem Zeitraum", "Kennzahl im Monatskopf. Vor 2012 eher zu niedrig."),
    C("n_days_with_fire", "double", "Tage", "Zahl der Tage mit mindestens einer Erkennung.", "leer, wenn nicht vollständig gemessen", "Kennzahl „Feuertage“. Nur ab 2012 verfügbar."),
    C("n_aqua", "double", "Erkennungen", "Summe der Rohzahl Aqua.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("n_terra", "double", "Erkennungen", "Summe der Rohzahl Terra.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("n_snpp", "double", "Erkennungen", "Summe der Rohzahl SNPP.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("n_noaa20", "double", "Erkennungen", "Summe der Rohzahl NOAA-20.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("n_noaa21", "double", "Erkennungen", "Summe der Rohzahl NOAA-21.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("n_viirs", "double", "Erkennungen", "Summe der VIIRS-Referenz (Mittel der aktiven VIIRS-Satelliten je Tag).", "leer, wenn nie in Betrieb", "Tooltip."),
    C("frp_aqua", "double", "MW", "Summe der FRP Aqua.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("frp_terra", "double", "MW", "Summe der FRP Terra.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("frp_snpp", "double", "MW", "Summe der FRP SNPP.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("frp_noaa20", "double", "MW", "Summe der FRP NOAA-20.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("frp_noaa21", "double", "MW", "Summe der FRP NOAA-21.", "leer, wenn nie in Betrieb", "Tooltip."),
    C("frp_viirs", "double", "MW", "Summe der VIIRS-Referenz der FRP.", "leer, wenn nie in Betrieb", "Tooltip."),
)

CLIMATOLOGY = (
    C("region_id", "string", "–", "NUTS-2-Region.", "nie leer", "Schlüssel."),
    C("day_of_year", "int", "1–365", "Tag im Jahr. Der 29. Februar zählt zum 28.", "nie leer", "x-Achse des Kalenders oder Jahresrings."),
    C("mean_n_harm_all", "double", "je Tag", "Mittlere harmonisierte Anzahl an diesem Kalendertag, alle Jahre ab 2001, ±7 Tage geglättet.", "nie leer", "Grundfarbe des Kalenders „typische Aktivität“."),
    C("mean_frp_harm_all", "double", "MW je Tag", "Mittlere harmonisierte FRP-Summe, alle Jahre.", "nie leer", "Kalender „typische Stärke“."),
    C("p25_n_harm_all", "double", "je Tag", "Unteres Viertel der Jahre.", "nie leer", "Band „übliche Spanne“."),
    C("p50_n_harm_all", "double", "je Tag", "Median der Jahre.", "nie leer", "Referenzlinie „normal“."),
    C("p75_n_harm_all", "double", "je Tag", "Oberes Viertel der Jahre.", "nie leer", "Band „übliche Spanne“."),
    C("p90_n_harm_all", "double", "je Tag", "Nur jedes zehnte Jahr liegt höher.", "nie leer", "Schwelle „außergewöhnlich“."),
    C("mean_n_harm_viirs", "double", "je Tag", "Mittlere gemessene Anzahl, nur VIIRS-Jahre.", "nie leer", "Vergleichslinie ohne Umrechnung."),
    C("mean_frp_harm_viirs", "double", "MW je Tag", "Mittlere gemessene FRP-Summe, nur VIIRS-Jahre.", "nie leer", "Vergleichslinie ohne Umrechnung."),
    C("p_fire_day_viirs", "double", "Anteil", "Wahrscheinlichkeit, dass es an einem Tag um dieses Datum brennt (nur VIIRS-Jahre).", "nie leer", "Kalender „Wie oft brennt es um diese Zeit?“."),
    C("p_big_fire_day_viirs", "double", "Anteil", "Wahrscheinlichkeit eines Großfeuer-Tags um dieses Datum (nur VIIRS-Jahre).", "nie leer", "Kalender der Gefahrenzeiten."),
    C("n_years_all", "int", "Jahre", "Zahl der Jahre hinter den *_all-Spalten.", "nie leer", "Fußnote."),
    C("n_years_viirs", "int", "Jahre", "Zahl der Jahre hinter den *_viirs-Spalten.", "nie leer", "Fußnote."),
    C("window_days", "int", "Tage", "Halbe Breite der Glättung.", "nie leer", "Fußnote."),
)

MONTH_TO_DATE = (
    C("region_id", "string", "–", "NUTS-2-Region.", "nie leer", "Schlüssel."),
    C("as_of", "date", "–", "Letzter Tag, der in den Vergleich eingeht.", "nie leer", "Text „Stand: 2. November“."),
    C("days_counted", "int", "Tage", "Zahl der verglichenen Tage (Tag 1 bis as_of).", "nie leer", "Text „bisher 2 Tage“."),
    C("n_harm_current", "double", "VIIRS-Äquivalente", "Anzahl im laufenden Monat bis as_of.", "nie leer", "Aktueller Wert."),
    C("n_harm_history_median", "double", "VIIRS-Äquivalente", "Median derselben Tage in früheren Jahren.", "leer ohne Vergleichsjahre", "Vergleichswert „üblich“."),
    C("n_harm_ratio_to_median", "double", "Faktor", "Aktueller Wert geteilt durch den Median.", "leer, wenn der Median 0 ist", "Anzeige „2,3-mal so viel wie üblich“."),
    C("n_harm_percentile", "double", "0–100", "Rang unter den früheren Jahren (100 = aktivster Zeitraum).", "leer ohne Vergleichsjahre", "Ampel oder Tachoanzeige."),
    C("frp_harm_current", "double", "MW", "FRP-Summe im laufenden Monat bis as_of.", "nie leer", "Aktuelle Stärke."),
    C("frp_harm_history_median", "double", "MW", "Median derselben Tage in früheren Jahren.", "leer ohne Vergleichsjahre", "Vergleichswert."),
    C("frp_harm_ratio_to_median", "double", "Faktor", "Aktuelle FRP geteilt durch den Median.", "leer, wenn der Median 0 ist", "Anzeige „stärker als üblich“."),
    C("frp_harm_percentile", "double", "0–100", "Rang der FRP unter den früheren Jahren.", "leer ohne Vergleichsjahre", "Ampel."),
    C("n_history_years", "double", "Jahre", "Zahl der Vergleichsjahre.", "leer ohne Vergleichsjahre", "Fußnote."),
    C("n_history_years_measured", "double", "Jahre", "Davon mit gemessenem VIIRS.", "leer ohne Vergleichsjahre", "Fußnote zur Verlässlichkeit."),
)

TABLES: dict[str, Table] = {
    "activity_daily_harmonised": Table(
        "activity_daily_harmonised", "eine Zeile je Region und Tag", "data/harmonised/activity_daily_harmonised.parquet",
        "Der kanonische Datensatz. Aus ihm entstehen Verlauf, Kalender und alle gröberen Zeitschritte.", DAILY),
    "hotspots_harmonised": Table(
        "hotspots_harmonised", "eine Zeile je Erkennung (Pixel und Überflug)", "data/harmonised/hotspots_harmonised.parquet",
        "Die Punktdaten für Karte, frei gezeichnete Flächen und CSV-Download. Die Gewichte machen jede Fläche summierbar.",
        HOTSPOT_BASE + HOTSPOT_WEIGHTS),
    "day_status": Table(
        "day_status", "eine Zeile je Tag", "data/harmonised/day_status.parquet",
        "Sagt für jeden Tag, ob er gemessen, umgerechnet oder gar nicht abgedeckt ist. Unterscheidet „kein Feuer“ von „keine Daten“.", DAY_STATUS),
    "quality_by_scale": Table(
        "quality_by_scale", "eine Zeile je Fläche, Zeitschritt, Größe, Basis und Größenklasse", "data/harmonised/quality_by_scale.parquet",
        "Das Fehlermodell. Hier schlägt das Frontend nach, wie unsicher eine umgerechnete Zahl ist.", QUALITY),
    "calib_factors": Table(
        "calib_factors", "eine Zeile je Region", "data/harmonised/calib_factors.parquet",
        "Die Umrechnungsfaktoren. Für das Frontend nur als Erklärung nötig, die Werte stecken schon in den Daten.", CALIB),
    "strength_confusion": Table(
        "strength_confusion", "eine Zeile je Basis und Klassenpaar", "data/harmonised/strength_confusion.parquet",
        "Zeigt, wie verlässlich die Stärkeklasse eines umgerechneten Tages ist.", CONFUSION),
    "big_fire_day_quality": Table(
        "big_fire_day_quality", "eine Zeile je Flächenskala und Basis", "data/harmonised/big_fire_day_quality.parquet",
        "Zeigt, wie viele Großfeuer-Tage die Umrechnung findet.", BIG_FIRE),
    "roll_up": Table(
        "Ergebnis von roll_up_daily", "eine Zeile je Region und Zeitschritt", "aggregation/roll_up.py (wird berechnet, nicht gespeichert)",
        "Woche, Monat, Quartal oder Jahr aus dem Tagesdatensatz. Mit add_uncertainty_to_periods kommen Bänder und reliability dazu.",
        ROLL_UP, stored=False),
    "climatology": Table(
        "Ergebnis von build_day_of_year_climatology", "eine Zeile je Region und Tag im Jahr", "aggregation/climatology.py (wird berechnet)",
        "Der typische Jahresverlauf für den Kalender.", CLIMATOLOGY, stored=False),
    "month_to_date": Table(
        "Ergebnis von month_to_date_vs_history", "eine Zeile je Region", "aggregation/month_to_date.py (wird berechnet)",
        "Der laufende Monat bis heute gegen dieselben Tage früherer Jahre.", MONTH_TO_DATE, stored=False),
    "hotspots_clean": Table(
        "hotspots_clean", "eine Zeile je Erkennung", "data/processed/hotspots_clean.parquet",
        "Zwischenstand vor den Gewichten (intern).", HOTSPOT_BASE),
}


def columns_of(table_name: str) -> list[str]:
    """Spaltennamen einer Tabelle in ihrer festen Reihenfolge."""
    return [column.name for column in TABLES[table_name].columns]
