# Datenwörterbuch

Erzeugt aus `pipeline/column_catalogue.py`. Dieselbe Quelle prüft das Schema der Dateien.

## activity_daily_harmonised

- Zeile: eine Zeile je Region und Tag
- Ablage: `data/harmonised/activity_daily_harmonised.parquet`
- Zweck: Der kanonische Datensatz. Aus ihm entstehen Verlauf, Kalender und alle gröberen Zeitschritte.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `region_id` | string | – | NUTS-2-Region (Stand 2021). | nie leer | Auswahl der Region, Schlüssel zusammen mit date. |
| `country` | string | – | Land (ES, PT, FR). | nie leer | Filter und Gruppierung nach Land. |
| `region_name` | string | – | Klarname der Region, z. B. „Comunidad de Madrid“. | nie leer | Beschriftung in Auswahlliste, Karte und Diagramm. |
| `date` | date | – | Tag (Zuordnung wie obs_date der Hotspots). | nie leer, lückenlos ab 2001-01-01 | Zeitachse von Kalender und Verlauf. |
| `n_aqua` | double | Erkennungen | Rohzahl Aqua (MODIS) an diesem Tag. | 0 = kein Feuer, leer = Aqua nicht in Betrieb | Nur Tooltip „Rohdaten“ und Nachrechnen. |
| `n_terra` | double | Erkennungen | Rohzahl Terra (MODIS) an diesem Tag. | 0 = kein Feuer, leer = Terra nicht in Betrieb | Nur Tooltip „Rohdaten“ und Nachrechnen. |
| `n_snpp` | double | Erkennungen | Rohzahl SNPP (VIIRS) an diesem Tag. | 0 = kein Feuer, leer = SNPP nicht in Betrieb (vor 20.01.2012) | Nur Tooltip „Rohdaten“ und Nachrechnen. |
| `n_noaa20` | double | Erkennungen | Rohzahl NOAA-20 (VIIRS) an diesem Tag. | 0 = kein Feuer, leer = NOAA-20 nicht in Betrieb (vor 01.04.2018) | Nur Tooltip „Rohdaten“ und Nachrechnen. |
| `n_noaa21` | double | Erkennungen | Rohzahl NOAA-21 (VIIRS) an diesem Tag. | 0 = kein Feuer, leer = NOAA-21 nicht in Betrieb (vor 01.03.2023) | Nur Tooltip „Rohdaten“ und Nachrechnen. |
| `n_viirs` | double | Erkennungen | VIIRS-Referenz: Mittel der Rohzahlen der an diesem Tag aktiven VIIRS-Satelliten (SNPP, NOAA-20, NOAA-21). An gemessenen Tagen gleich n_harm. | 0 = kein Feuer, leer = kein VIIRS-Satellit in Betrieb (vor 20.01.2012) | Nur Tooltip „gemessen, Mittel aus k Satelliten“. |
| `frp_aqua` | double | MW | FRP-Summe Aqua an diesem Tag. | wie n_aqua | Nur Tooltip und Nachrechnen. |
| `frp_terra` | double | MW | FRP-Summe Terra an diesem Tag. | wie n_terra | Nur Tooltip und Nachrechnen. |
| `frp_snpp` | double | MW | FRP-Summe SNPP an diesem Tag. | wie n_snpp | Nur Tooltip und Nachrechnen. |
| `frp_noaa20` | double | MW | FRP-Summe NOAA-20 an diesem Tag. | wie n_noaa20 | Nur Tooltip und Nachrechnen. |
| `frp_noaa21` | double | MW | FRP-Summe NOAA-21 an diesem Tag. | wie n_noaa21 | Nur Tooltip und Nachrechnen. |
| `frp_viirs` | double | MW | VIIRS-Referenz der Stärke: Mittel der FRP-Summen der aktiven VIIRS-Satelliten. An gemessenen Tagen gleich frp_harm. | wie n_viirs | Nur Tooltip und Nachrechnen. |
| `basis_count` | string | – | Quelle von n_harm: viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled oder none (keine zulässige Quelle). | none = kein Wert | Kennzeichnung „gemessen“ gegen „umgerechnet“, z. B. als Schraffur. |
| `basis_frp` | string | – | Quelle von frp_harm: viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled oder none (keine zulässige Quelle). | none = kein Wert | Wie basis_count, für die Stärke. |
| `n_harm` | double | VIIRS-Äquivalente | Harmonisierte Anzahl der Erkennungen: gemessen (n_viirs) oder MODIS × Regionsfaktor. | 0 = keine Erkennung (vor 2012 oft nur „MODIS sah nichts“), leer = Tag ohne Basis | Hauptwert für Verlauf und Kalender. Vor 2012 immer mit Band zeigen. |
| `frp_harm` | double | MW (VIIRS-Äquivalente) | Harmonisierte FRP-Summe des Tages, das Maß für die Stärke. | wie n_harm | Stärke eines Tages als Zahl, Höhe eines Balkens, Farbintensität im Kalender. |
| `factor_count` | double | Faktor | Auf die Anzahl angewandter Faktor (1 bei Messung). | leer, wenn kein Wert | Tooltip „umgerechnet mit × 2,7“. |
| `factor_frp` | double | Faktor | Auf die FRP angewandter Faktor (1 bei Messung). | leer, wenn kein Wert | Tooltip zur Stärke. |
| `strength_class` | string | – | Stärkeklasse aus frp_harm: minor (unter 10 MW), moderate (10–100), strong (100–500), extreme (ab 500). | leer, wenn kein Wert | Farbe des Kalendertags. Vor 2012 ist nur „extreme“ verlässlich (siehe strength_confusion). |
| `big_fire_day` | boolean | – | Wahr an Tagen mit frp_harm ab 100 MW. | leer, wenn kein Wert | Markierung im Kalender, Zählung „Großfeuer-Tage“. Vor 2012 werden nicht alle erkannt. |
| `n_harm_lo50` | double | VIIRS-Äquivalente | Anzahl: Untergrenze des typischen Bereichs (enthält die Messung in etwa der Hälfte der Fälle). | leer, wenn der Wert leer ist | Dunkles Fehlerband um den Wert. |
| `n_harm_hi50` | double | VIIRS-Äquivalente | Anzahl: Obergrenze des typischen Bereichs. | leer, wenn der Wert leer ist | Dunkles Fehlerband um den Wert. |
| `n_harm_lo90` | double | VIIRS-Äquivalente | Anzahl: Untergrenze des weiten Bereichs (enthält die Messung in etwa neun von zehn Fällen). | leer, wenn der Wert leer ist | Helles Fehlerband, Fehlerbalken. |
| `n_harm_hi90` | double | VIIRS-Äquivalente | Anzahl: Obergrenze des weiten Bereichs. Bei umgerechneter 0: so viel misst VIIRS in 90 % solcher Fälle höchstens. | leer, wenn der Wert leer ist | Helles Fehlerband, Fehlerbalken, Text „0, bis etwa …“. |
| `frp_harm_lo50` | double | MW | FRP-Summe: Untergrenze des typischen Bereichs (enthält die Messung in etwa der Hälfte der Fälle). | leer, wenn der Wert leer ist | Dunkles Fehlerband um den Wert. |
| `frp_harm_hi50` | double | MW | FRP-Summe: Obergrenze des typischen Bereichs. | leer, wenn der Wert leer ist | Dunkles Fehlerband um den Wert. |
| `frp_harm_lo90` | double | MW | FRP-Summe: Untergrenze des weiten Bereichs (enthält die Messung in etwa neun von zehn Fällen). | leer, wenn der Wert leer ist | Helles Fehlerband, Fehlerbalken. |
| `frp_harm_hi90` | double | MW | FRP-Summe: Obergrenze des weiten Bereichs. Bei umgerechneter 0: so viel misst VIIRS in 90 % solcher Fälle höchstens. | leer, wenn der Wert leer ist | Helles Fehlerband, Fehlerbalken, Text „0, bis etwa …“. |
| `reliability` | string | – | Zuverlässigkeitsstufe: measured (gemessen), converted_solid (umgerechnet, ab 100 Erkennungen), converted_rough (umgerechnet, kleine Zahl). | leer, wenn kein Wert | Ampel oder Symbol neben dem Wert, Filter „nur gemessene Tage“. |
| `is_complete_day` | boolean | – | Wahr, wenn der Tag für Anzahl und FRP eine Basis hat. | nie leer | Tage ohne Daten grau statt als 0 zeigen. |
| `possible_gap` | boolean | – | Wahr, wenn der Basis-Satellit im ganzen Gebiet nichts meldet, obwohl die Nachbartage viel melden. | nie leer | Warnhinweis „möglicher Datenausfall“ statt „ruhiger Tag“. |

## hotspots_harmonised

- Zeile: eine Zeile je Erkennung (Pixel und Überflug)
- Ablage: `data/harmonised/hotspots_harmonised.parquet`
- Zweck: Die Punktdaten für Karte, frei gezeichnete Flächen und CSV-Download. Die Gewichte machen jede Fläche summierbar.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `hotspot_id` | string | – | Stabile Kennung der Erkennung: Hash aus Satellit, Koordinaten, Datum und Uhrzeit. | nie leer, eindeutig | Schlüssel für Auswahl auf der Karte, Deep-Links und Wiedererkennen beim Nachladen. |
| `latitude` | double | Grad | Geografische Breite der Pixelmitte (WGS84). | nie leer | Position des Punkts auf der Karte, räumliche Filter. |
| `longitude` | double | Grad | Geografische Länge der Pixelmitte (WGS84). | nie leer | Position des Punkts auf der Karte, räumliche Filter. |
| `cell_id` | string | – | Rasterzelle von 0,25° als „Breitenindex_Längenindex“ (Index = floor(Koordinate / 0,25)). | nie leer | Kacheln auf der Karte einfärben, schnelle Vorfilterung großer Flächen. |
| `h3_cell` | string | – | H3-Zelle der Pixelmitte (Sechseck-Raster, Auflösung 8, etwa 0,74 km²), z. B. „88390ca343fffff“. | nie leer | Sechseck-Heatmap, Nachbarschaftsabfragen. Gröbere Zellen per h3.cell_to_parent (z. B. Auflösung 5 oder 6 für ganz Iberien). |
| `acq_date` | date | UTC | Datum der Messung in UTC, wie von FIRMS geliefert. | nie leer | Anzeige im Popup und im CSV. Für Zeitfilter und Summen besser obs_date nehmen. |
| `acq_time` | string | UTC, HHMM | Uhrzeit der Messung als vierstelliger Text, z. B. „0114“. | nie leer | Nur fürs CSV (Originalformat). Zum Rechnen acq_datetime_utc verwenden. |
| `acq_datetime_utc` | timestamp | UTC | Datum und Uhrzeit der Messung als echter Zeitstempel. | nie leer | Zeitachse, Sortierung, Animation des Tagesverlaufs, Anzeige der Überflugzeit. |
| `obs_date` | date | – | Tag, zu dem der Punkt in allen Summen zählt (Zuordnung laut Konfiguration: UTC-Datum oder Sonnendatum). | nie leer | Der Zeitfilter der Karte und der Schlüssel zu day_status und zur Tagestabelle. |
| `local_solar_hour` | double | Stunden 0–24 | Lokale Sonnenzeit des Überflugs: UTC-Stunde + Länge / 15. | nie leer | Tageszeit im Popup („erkannt um 13:20 Ortszeit“), Auswertung nach Tageszeit. |
| `satellite` | string | – | Satellit: Terra, Aqua (MODIS), SNPP, N20 (NOAA-20) oder N21 (NOAA-21) (VIIRS). | nie leer | Herkunft im Popup und im CSV. Nicht zum Vergleichen von Zahlen zwischen Satelliten. |
| `sensor` | string | – | Instrument: MODIS (Terra, Aqua, 1-km-Pixel) oder VIIRS (SNPP, NOAA-20, NOAA-21, 375-m-Pixel). | nie leer | Symbol oder Legende auf der Karte. Pflichtbegleiter für frp_class und confidence_class. |
| `source` | string | – | archive (endgültig, geprüft) oder nrt (vorläufig, wird später durch Archivdaten ersetzt). | nie leer | Vorläufige Punkte kennzeichnen, z. B. gestrichelt oder mit Hinweis „vorläufig“. |
| `daynight` | string | – | D (Tag-Überflug) oder N (Nacht-Überflug). | nie leer | Filter Tag/Nacht, Symbol im Popup. |
| `frp` | double | MW | Strahlungsleistung des Feuers in diesem Pixel (Fire Radiative Power). | 0 möglich, nie leer | Größe oder Farbe des Punkts. Nur innerhalb eines Sensors vergleichen: ein VIIRS-Pixel ist kleiner und zeigt weniger MW für dasselbe Feuer. |
| `frp_class` | string | – | Klasse der Pixel-FRP: low (unter 10 MW), mid (10–50 MW), high (ab 50 MW). | nie leer | Farbstufen der Punkte, Filter auf der Karte und im CSV. Nicht für Summen über die Jahre: vor 2012 fehlen die schwachen Feuer. |
| `confidence_class` | string | – | Güte der einzelnen Erkennung laut FIRMS: low, nominal, high. | leer, wenn der Originalwert unlesbar ist | Filter „unsichere Erkennungen ausblenden“. Nur zusammen mit sensor: VIIRS-„high“ bedeutet nur „Kanal gesättigt“. |
| `confidence_raw` | string | – | Originalwert von FIRMS: Zahl 0–100 bei MODIS, l / n / h bei VIIRS. | nie leer | Nur fürs CSV für Fachleute. Im UI nicht nötig. |
| `scan` | double | km | Pixelbreite quer zur Flugrichtung. | nie leer | Fußabdruck des Pixels zeichnen (zusammen mit track). |
| `track` | double | km | Pixelbreite in Flugrichtung. | nie leer | Fußabdruck des Pixels zeichnen (zusammen mit scan). |
| `pixel_area_km2` | double | km² | Fläche des Pixels am Boden: scan × track. | nie leer | Punkt in echter Größe darstellen. Große Werte heißen Bildrand und damit gröbere Ortsangabe. |
| `region_id` | string | – | NUTS-2-Region des Punkts (Stand 2021), z. B. ES30. | leer bei Punkten im offenen Meer | Schneller Filter „Region wählen“, Verknüpfung zur Tagestabelle. |
| `country` | string | – | Land: die ersten zwei Zeichen von region_id (ES, PT, FR). | leer wie region_id | Filter nach Land. |
| `in_series_n` | boolean | – | Wahr, wenn der Satellit des Punkts an diesem Tag zur Basis der Anzahl gehört und in Betrieb ist. | nie leer | Karte ohne Sensor-Doppelte: nur Punkte mit in_series_n = wahr zeigen (ab 2012 nur VIIRS, davor MODIS). Ab 2018 kann dasselbe Feuer als Punkt von SNPP und von NOAA-20/21 erscheinen (andere Überflugzeit), Filter nach satellite möglich. |
| `in_series_frp` | boolean | – | Wahr, wenn der Punkt in die harmonisierte FRP-Summe eingeht. | nie leer | Wie in_series_n, für Darstellungen der Stärke. |
| `weight_n` | double | VIIRS-Äquivalente | Beitrag des Punkts zur harmonisierten Anzahl: 1/k bei VIIRS (k = an dem Tag aktive VIIRS-Satelliten, 1 bis 3), Regionsfaktor bei MODIS, 0 außerhalb der Reihe. | 0 = zählt nicht mit | Harmonisierte Anzahl einer beliebigen Fläche: SUM(weight_n). Nicht als Eigenschaft des Punkts anzeigen. |
| `weight_frp` | double | Faktor | Faktor, mit dem die FRP des Punkts in die harmonisierte Summe eingeht. | 0 = zählt nicht mit | Harmonisierte Stärke einer beliebigen Fläche: SUM(frp × weight_frp). |
| `basis_count` | string | – | Quelle der Anzahl an diesem Tag: viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled oder none (keine zulässige Quelle). | none = Tag ohne Wert | Nachvollziehen im CSV, Hinweis „gemessen“ oder „umgerechnet“. |
| `basis_frp` | string | – | Quelle der FRP-Summe an diesem Tag: viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled oder none (keine zulässige Quelle). | none = Tag ohne Wert | Wie basis_count, für die Stärke. |

## day_status

- Zeile: eine Zeile je Tag
- Ablage: `data/harmonised/day_status.parquet`
- Zweck: Sagt für jeden Tag, ob er gemessen, umgerechnet oder gar nicht abgedeckt ist. Unterscheidet „kein Feuer“ von „keine Daten“.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `date` | date | – | Tag. | nie leer, lückenlos | Zeitachse. Jeder Tag kommt genau einmal vor. |
| `viirs_operating` | boolean | – | Mindestens ein VIIRS-Satellit (SNPP, NOAA-20, NOAA-21) liefert an diesem Tag Daten. Dann ist der Tag gemessen. | nie leer | Erklärung, warum ein Tag gemessen oder umgerechnet ist. |
| `snpp_operating` | boolean | – | SNPP (VIIRS) liefert an diesem Tag Daten. | nie leer | Tooltip „gemessen mit …“ (welche Satelliten im Mittel stecken). |
| `noaa20_operating` | boolean | – | NOAA-20 (VIIRS) liefert an diesem Tag Daten. | nie leer | Wie snpp_operating. |
| `noaa21_operating` | boolean | – | NOAA-21 (VIIRS) liefert an diesem Tag Daten. | nie leer | Wie snpp_operating. |
| `aqua_operating` | boolean | – | Aqua (MODIS) liefert an diesem Tag Daten. | nie leer | Wie snpp_operating. |
| `terra_operating` | boolean | – | Terra (MODIS) liefert an diesem Tag Daten. | nie leer | Wie snpp_operating. |
| `basis_count` | string | – | Quelle der Anzahl an diesem Tag: viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled oder none (keine zulässige Quelle). | none = Tag ohne Wert | Abschnitte der Zeitachse einfärben (gemessen, umgerechnet, keine Daten). |
| `basis_frp` | string | – | Quelle der FRP-Summe an diesem Tag: viirs_measured (VIIRS gemessen, Mittel der aktiven VIIRS-Satelliten), modis_pair_scaled (Aqua + Terra umgerechnet), aqua_scaled, terra_scaled oder none (keine zulässige Quelle). | none = Tag ohne Wert | Wie basis_count. |
| `is_complete_day` | boolean | – | Wahr, wenn der Tag einen harmonisierten Wert hat. | nie leer | Die Kernfrage der Punktkarte: keine Punkte an einem vollständigen Tag = kein Feuer, an einem unvollständigen = keine Daten. |
| `is_provisional` | boolean | – | Wahr, wenn der Tag auf vorläufigen NRT-Daten beruht. | nie leer | Hinweis „vorläufig, kann sich ändern“. |
| `possible_gap` | boolean | – | Verdacht auf Datenausfall an diesem Tag. | nie leer | Warnsymbol auf der Zeitachse. |

## quality_by_scale

- Zeile: eine Zeile je Fläche, Zeitschritt, Größe, Basis und Größenklasse
- Ablage: `data/harmonised/quality_by_scale.parquet`
- Zweck: Das Fehlermodell. Hier schlägt das Frontend nach, wie unsicher eine umgerechnete Zahl ist.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `area_scale` | string | – | Flächenskala: cell (0,25°), nuts2, country, all (ganzes Gebiet). | nie leer | Nachschlagen: Skala passend zur gewählten Fläche. |
| `grain` | string | – | Zeitschritt: day, week, month, quarter, year. | nie leer | Nachschlagen: passend zum gewählten Zeitraum. |
| `quantity` | string | – | count (Anzahl) oder frp (FRP-Summe). | nie leer | Nachschlagen. |
| `basis` | string | – | Basis der Umrechnung, für die die Zeile gilt. | nie leer | Nachschlagen. |
| `size_class` | string | – | Größenklasse der umgerechneten Zahl, z. B. „0“, „5-20“, „>500“. „all“ = alle Klassen über 0. | nie leer | Nachschlagen nach der angezeigten Zahl. |
| `class_upper` | double | wie quantity | Obergrenze der Klasse (einschließlich). | unendlich bei der obersten Klasse | Nachschlagen. |
| `n_units` | double | Fälle | Zahl der Vergleichsfälle in der Kreuzvalidierung. | nie leer | Bei kleinen Werten den Fehler als „unsicher“ kennzeichnen. |
| `median_factor_error` | double | Faktor | Typischer Fehler: die Hälfte der Fälle liegt näher am Messwert als dieser Faktor. | nie leer | Breite des dunklen Fehlerbands. |
| `p90_factor_error` | double | Faktor | 90-%-Fehler: neun von zehn Fällen liegen näher. | nie leer | Breite des hellen Fehlerbands. |
| `abs_upper_p50` | double | wie quantity | Median der VIIRS-Messung in dieser Klasse. | nie leer | Für die Klasse 0: typischer wahrer Wert. |
| `abs_upper_p90` | double | wie quantity | 90-%-Quantil der VIIRS-Messung in dieser Klasse. | nie leer | Für die Klasse 0: Text „0, bis etwa …“. |
| `coverage50_holdout_low` | double | Anteil | Geprüfte Trefferquote des 50-%-Bands auf zurückgehaltenen Jahren, ungünstigere Prüfrichtung. | leer, wenn nicht prüfbar | Nicht nötig (Nachweis der Ehrlichkeit). |
| `coverage50_holdout_high` | double | Anteil | Wie zuvor, günstigere Prüfrichtung. | leer, wenn nicht prüfbar | Nicht nötig (Nachweis). |
| `coverage90_holdout_low` | double | Anteil | Geprüfte Trefferquote des 90-%-Bands, ungünstigere Prüfrichtung. | leer, wenn nicht prüfbar | Nicht nötig (Nachweis). |
| `coverage90_holdout_high` | double | Anteil | Wie zuvor, günstigere Prüfrichtung. | leer, wenn nicht prüfbar | Nicht nötig (Nachweis). |
| `factor_shift` | double | Anteil | Unterschied des typischen Fehlers zwischen den beiden Jahreshälften. | leer, wenn nicht prüfbar | Nicht nötig (Nachweis). |
| `n_test` | double | Fälle | Zahl der Prüffälle (kleinere der beiden Prüfhälften). | leer, wenn nicht prüfbar | Nicht nötig. |

## calib_factors

- Zeile: eine Zeile je Region
- Ablage: `data/harmonised/calib_factors.parquet`
- Zweck: Die Umrechnungsfaktoren. Für das Frontend nur als Erklärung nötig, die Werte stecken schon in den Daten.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `region_id` | string | – | NUTS-2-Region. | nie leer | Schlüssel. |
| `k_count_pair` | double | Faktor | VIIRS-Erkennungen je (Aqua + Terra)-Erkennung. | nie leer | Infotext „So wurde umgerechnet“. |
| `k_count_aqua` | double | Faktor | VIIRS-Erkennungen je Aqua-Erkennung. | nie leer | Infotext. |
| `k_count_terra` | double | Faktor | VIIRS-Erkennungen je Terra-Erkennung (für die Zeit vor Aqua). | nie leer | Infotext. |
| `k_frp_pair` | double | Faktor | VIIRS-FRP je (Aqua + Terra)-FRP, ein Wert für alle Regionen. | nie leer | Infotext. |
| `k_frp_aqua` | double | Faktor | VIIRS-FRP je Aqua-FRP, ein Wert für alle Regionen. | nie leer | Infotext. |
| `k_frp_terra` | double | Faktor | VIIRS-FRP je Terra-FRP, ein Wert für alle Regionen. | nie leer | Infotext. |
| `used_fallback_pair` | boolean | – | Wahr, wenn die Region zu wenige Daten hat und den Gesamtfaktor bekommt. | nie leer | Hinweis „Region mit wenig Daten“. |
| `used_fallback_aqua` | boolean | – | Wie used_fallback_pair, für den Aqua-Faktor. | nie leer | Hinweis. |
| `used_fallback_terra` | boolean | – | Wie used_fallback_pair, für den Terra-Faktor. | nie leer | Hinweis. |
| `n_viirs_calib` | double | Erkennungen | VIIRS-Referenz (Mittel der aktiven VIIRS-Satelliten) der Region im Kalibrierfenster, summiert. | nie leer | Nicht nötig (Diagnose). |
| `n_pair_calib` | double | Erkennungen | Aqua + Terra-Erkennungen im Kalibrierfenster. | nie leer | Nicht nötig (Diagnose). |
| `n_aqua_calib` | double | Erkennungen | Aqua-Erkennungen im Kalibrierfenster. | nie leer | Nicht nötig (Diagnose). |
| `n_terra_calib` | double | Erkennungen | Terra-Erkennungen im Kalibrierfenster. | nie leer | Nicht nötig (Diagnose). |
| `k_count_pair_overall` | double | Faktor | Gesamtfaktor über alle Regionen (Aqua + Terra). | nie leer | Nicht nötig (Diagnose). |
| `k_count_aqua_overall` | double | Faktor | Gesamtfaktor über alle Regionen (Aqua). | nie leer | Nicht nötig (Diagnose). |
| `k_count_terra_overall` | double | Faktor | Gesamtfaktor über alle Regionen (Terra). | nie leer | Nicht nötig (Diagnose). |
| `calib_start` | string | Datum | Beginn des Kalibrierfensters. | nie leer | Infotext. |
| `calib_end` | string | Datum | Ende des Kalibrierfensters. | nie leer | Infotext. |

## strength_confusion

- Zeile: eine Zeile je Basis und Klassenpaar
- Ablage: `data/harmonised/strength_confusion.parquet`
- Zweck: Zeigt, wie verlässlich die Stärkeklasse eines umgerechneten Tages ist.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `basis` | string | – | Basis der Umrechnung. | nie leer | Auswahl der passenden Zeilen. |
| `measured_class` | string | – | Stärkeklasse laut VIIRS-Messung. | nie leer | Zeile der Vergleichsmatrix. |
| `converted_class` | string | – | Stärkeklasse laut Umrechnung am selben Tag. | nie leer | Spalte der Vergleichsmatrix. |
| `n_days` | double | Tage | Zahl der Region-Tage mit dieser Kombination. | nie leer | Infografik „Wie verlässlich ist die Klasse vor 2012?“. |
| `share_of_measured_class` | double | Anteil | Anteil an allen Tagen der gemessenen Klasse. | nie leer | Text wie „starke Tage werden zu 7 von 10 richtig eingestuft“. |

## big_fire_day_quality

- Zeile: eine Zeile je Flächenskala und Basis
- Ablage: `data/harmonised/big_fire_day_quality.parquet`
- Zweck: Zeigt, wie viele Großfeuer-Tage die Umrechnung findet.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `area_scale` | string | – | nuts2 oder cell (0,25°). | nie leer | Auswahl. |
| `basis` | string | – | Basis der Umrechnung. | nie leer | Auswahl. |
| `threshold_measured_mw` | double | MW | Schwelle für gemessene Tage. | nie leer | Legende. |
| `threshold_converted_mw` | double | MW | Schwelle für umgerechnete Tage. | nie leer | Legende. |
| `recall` | double | Anteil | Anteil der gemessenen Großfeuer-Tage, die die Umrechnung auch zeigt. | nie leer | Hinweis „vor 2012 werden etwa x von 10 Großfeuer-Tagen erkannt“. |
| `precision` | double | Anteil | Anteil der umgerechneten Großfeuer-Tage, die auch gemessen wurden. | nie leer | Hinweis zur Verlässlichkeit einer Markierung. |
| `kappa` | double | – | Übereinstimmung über den Zufall hinaus (0 bis 1). | nie leer | Nicht nötig (Kennzahl für Fachleute). |
| `n_events_measured` | double | Tage | Gemessene Großfeuer-Tage. | nie leer | Nicht nötig. |
| `n_events_converted` | double | Tage | Umgerechnete Großfeuer-Tage. | nie leer | Nicht nötig. |
| `n_units` | double | Tage | Alle verglichenen Tage. | nie leer | Nicht nötig. |

## Ergebnis von roll_up_daily

- Zeile: eine Zeile je Region und Zeitschritt
- Ablage: `aggregation/roll_up.py (wird berechnet, nicht gespeichert)`
- Zweck: Woche, Monat, Quartal oder Jahr aus dem Tagesdatensatz. Mit add_uncertainty_to_periods kommen Bänder und reliability dazu.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `region_id` | string | – | NUTS-2-Region. | nie leer | Schlüssel. |
| `grain` | string | – | Zeitschritt des Ergebnisses: week, month, quarter, year. | nie leer | Umschalter der Ansicht. |
| `period_start` | date | – | Erster Tag des Zeitschritts (Montag, Monats-, Quartals- oder Jahreserster). | nie leer | Zeitachse. |
| `period_end` | date | – | Letzter Kalendertag des Zeitschritts. | nie leer | Beschriftung. |
| `n_days` | double | Tage | Zahl der Tage im Datensatz für diesen Zeitschritt. | nie leer | Nicht nötig. |
| `n_days_complete` | double | Tage | Zahl der Tage mit Wert. | nie leer | Fortschritt „bisher 12 von 30 Tagen“. |
| `is_complete_period` | boolean | – | Wahr, wenn jeder Kalendertag des Zeitschritts einen Wert hat. | nie leer | Unvollständige Zeiträume grau zeigen und nicht in Median oder Rang nehmen. |
| `share_measured_days` | double | Anteil | Anteil der Tage mit gemessenem VIIRS (mindestens ein VIIRS-Satellit). | nie leer | Feinere Kennzeichnung gemischter Zeiträume. |
| `basis_mix` | string | – | measured, converted oder mixed. | nie leer | Kennzeichnung „gemessen“, „umgerechnet“, „gemischt“. |
| `basis_count_converted` | string | – | Basis der umgerechneten Tage des Zeitschritts (Anzahl). | leer, wenn alle Tage gemessen sind | Nachschlagen der Unsicherheit, Tooltip. |
| `basis_frp_converted` | string | – | Basis der umgerechneten Tage des Zeitschritts (FRP). | leer, wenn alle Tage gemessen sind | Nachschlagen der Unsicherheit, Tooltip. |
| `n_harm` | double | VIIRS-Äquivalente | Summe der harmonisierten Anzahl. | leer bei unvollständigem Zeitraum | Hauptwert für Monats- und Jahresansicht. |
| `frp_harm` | double | MW | Summe der harmonisierten FRP. | leer bei unvollständigem Zeitraum | Stärke des Zeitraums. |
| `n_harm_mean_per_day` | double | je Tag | Mittel pro Tag: n_harm / Tage. | leer bei unvollständigem Zeitraum | Vergleich verschieden langer Zeiträume. |
| `frp_harm_mean_per_day` | double | MW je Tag | Mittel pro Tag: frp_harm / Tage. | leer bei unvollständigem Zeitraum | Vergleich verschieden langer Zeiträume. |
| `n_big_fire_days` | double | Tage | Zahl der Großfeuer-Tage. | leer bei unvollständigem Zeitraum | Kennzahl im Monatskopf. Vor 2012 eher zu niedrig. |
| `n_days_with_fire` | double | Tage | Zahl der Tage mit mindestens einer Erkennung. | leer, wenn nicht vollständig gemessen | Kennzahl „Feuertage“. Nur ab 2012 verfügbar. |
| `n_aqua` | double | Erkennungen | Summe der Rohzahl Aqua. | leer, wenn nie in Betrieb | Tooltip. |
| `n_terra` | double | Erkennungen | Summe der Rohzahl Terra. | leer, wenn nie in Betrieb | Tooltip. |
| `n_snpp` | double | Erkennungen | Summe der Rohzahl SNPP. | leer, wenn nie in Betrieb | Tooltip. |
| `n_noaa20` | double | Erkennungen | Summe der Rohzahl NOAA-20. | leer, wenn nie in Betrieb | Tooltip. |
| `n_noaa21` | double | Erkennungen | Summe der Rohzahl NOAA-21. | leer, wenn nie in Betrieb | Tooltip. |
| `n_viirs` | double | Erkennungen | Summe der VIIRS-Referenz (Mittel der aktiven VIIRS-Satelliten je Tag). | leer, wenn nie in Betrieb | Tooltip. |
| `frp_aqua` | double | MW | Summe der FRP Aqua. | leer, wenn nie in Betrieb | Tooltip. |
| `frp_terra` | double | MW | Summe der FRP Terra. | leer, wenn nie in Betrieb | Tooltip. |
| `frp_snpp` | double | MW | Summe der FRP SNPP. | leer, wenn nie in Betrieb | Tooltip. |
| `frp_noaa20` | double | MW | Summe der FRP NOAA-20. | leer, wenn nie in Betrieb | Tooltip. |
| `frp_noaa21` | double | MW | Summe der FRP NOAA-21. | leer, wenn nie in Betrieb | Tooltip. |
| `frp_viirs` | double | MW | Summe der VIIRS-Referenz der FRP. | leer, wenn nie in Betrieb | Tooltip. |

## Ergebnis von build_day_of_year_climatology

- Zeile: eine Zeile je Region und Tag im Jahr
- Ablage: `aggregation/climatology.py (wird berechnet)`
- Zweck: Der typische Jahresverlauf für den Kalender.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `region_id` | string | – | NUTS-2-Region. | nie leer | Schlüssel. |
| `day_of_year` | int | 1–365 | Tag im Jahr. Der 29. Februar zählt zum 28. | nie leer | x-Achse des Kalenders oder Jahresrings. |
| `mean_n_harm_all` | double | je Tag | Mittlere harmonisierte Anzahl an diesem Kalendertag, alle Jahre ab 2001, ±7 Tage geglättet. | nie leer | Grundfarbe des Kalenders „typische Aktivität“. |
| `mean_frp_harm_all` | double | MW je Tag | Mittlere harmonisierte FRP-Summe, alle Jahre. | nie leer | Kalender „typische Stärke“. |
| `p25_n_harm_all` | double | je Tag | Unteres Viertel der Jahre. | nie leer | Band „übliche Spanne“. |
| `p50_n_harm_all` | double | je Tag | Median der Jahre. | nie leer | Referenzlinie „normal“. |
| `p75_n_harm_all` | double | je Tag | Oberes Viertel der Jahre. | nie leer | Band „übliche Spanne“. |
| `p90_n_harm_all` | double | je Tag | Nur jedes zehnte Jahr liegt höher. | nie leer | Schwelle „außergewöhnlich“. |
| `mean_n_harm_viirs` | double | je Tag | Mittlere gemessene Anzahl, nur VIIRS-Jahre. | nie leer | Vergleichslinie ohne Umrechnung. |
| `mean_frp_harm_viirs` | double | MW je Tag | Mittlere gemessene FRP-Summe, nur VIIRS-Jahre. | nie leer | Vergleichslinie ohne Umrechnung. |
| `p_fire_day_viirs` | double | Anteil | Wahrscheinlichkeit, dass es an einem Tag um dieses Datum brennt (nur VIIRS-Jahre). | nie leer | Kalender „Wie oft brennt es um diese Zeit?“. |
| `p_big_fire_day_viirs` | double | Anteil | Wahrscheinlichkeit eines Großfeuer-Tags um dieses Datum (nur VIIRS-Jahre). | nie leer | Kalender der Gefahrenzeiten. |
| `n_years_all` | int | Jahre | Zahl der Jahre hinter den *_all-Spalten. | nie leer | Fußnote. |
| `n_years_viirs` | int | Jahre | Zahl der Jahre hinter den *_viirs-Spalten. | nie leer | Fußnote. |
| `window_days` | int | Tage | Halbe Breite der Glättung. | nie leer | Fußnote. |

## Ergebnis von month_to_date_vs_history

- Zeile: eine Zeile je Region
- Ablage: `aggregation/month_to_date.py (wird berechnet)`
- Zweck: Der laufende Monat bis heute gegen dieselben Tage früherer Jahre.

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `region_id` | string | – | NUTS-2-Region. | nie leer | Schlüssel. |
| `as_of` | date | – | Letzter Tag, der in den Vergleich eingeht. | nie leer | Text „Stand: 2. November“. |
| `days_counted` | int | Tage | Zahl der verglichenen Tage (Tag 1 bis as_of). | nie leer | Text „bisher 2 Tage“. |
| `n_harm_current` | double | VIIRS-Äquivalente | Anzahl im laufenden Monat bis as_of. | nie leer | Aktueller Wert. |
| `n_harm_history_median` | double | VIIRS-Äquivalente | Median derselben Tage in früheren Jahren. | leer ohne Vergleichsjahre | Vergleichswert „üblich“. |
| `n_harm_ratio_to_median` | double | Faktor | Aktueller Wert geteilt durch den Median. | leer, wenn der Median 0 ist | Anzeige „2,3-mal so viel wie üblich“. |
| `n_harm_percentile` | double | 0–100 | Rang unter den früheren Jahren (100 = aktivster Zeitraum). | leer ohne Vergleichsjahre | Ampel oder Tachoanzeige. |
| `frp_harm_current` | double | MW | FRP-Summe im laufenden Monat bis as_of. | nie leer | Aktuelle Stärke. |
| `frp_harm_history_median` | double | MW | Median derselben Tage in früheren Jahren. | leer ohne Vergleichsjahre | Vergleichswert. |
| `frp_harm_ratio_to_median` | double | Faktor | Aktuelle FRP geteilt durch den Median. | leer, wenn der Median 0 ist | Anzeige „stärker als üblich“. |
| `frp_harm_percentile` | double | 0–100 | Rang der FRP unter den früheren Jahren. | leer ohne Vergleichsjahre | Ampel. |
| `n_history_years` | double | Jahre | Zahl der Vergleichsjahre. | leer ohne Vergleichsjahre | Fußnote. |
| `n_history_years_measured` | double | Jahre | Davon mit gemessenem VIIRS. | leer ohne Vergleichsjahre | Fußnote zur Verlässlichkeit. |

## hotspots_clean

- Zeile: eine Zeile je Erkennung
- Ablage: `data/processed/hotspots_clean.parquet`
- Zweck: Zwischenstand vor den Gewichten (intern).

| Spalte | Typ | Einheit | Bedeutung | 0 und leer | Nutzung im Frontend |
|---|---|---|---|---|---|
| `hotspot_id` | string | – | Stabile Kennung der Erkennung: Hash aus Satellit, Koordinaten, Datum und Uhrzeit. | nie leer, eindeutig | Schlüssel für Auswahl auf der Karte, Deep-Links und Wiedererkennen beim Nachladen. |
| `latitude` | double | Grad | Geografische Breite der Pixelmitte (WGS84). | nie leer | Position des Punkts auf der Karte, räumliche Filter. |
| `longitude` | double | Grad | Geografische Länge der Pixelmitte (WGS84). | nie leer | Position des Punkts auf der Karte, räumliche Filter. |
| `cell_id` | string | – | Rasterzelle von 0,25° als „Breitenindex_Längenindex“ (Index = floor(Koordinate / 0,25)). | nie leer | Kacheln auf der Karte einfärben, schnelle Vorfilterung großer Flächen. |
| `h3_cell` | string | – | H3-Zelle der Pixelmitte (Sechseck-Raster, Auflösung 8, etwa 0,74 km²), z. B. „88390ca343fffff“. | nie leer | Sechseck-Heatmap, Nachbarschaftsabfragen. Gröbere Zellen per h3.cell_to_parent (z. B. Auflösung 5 oder 6 für ganz Iberien). |
| `acq_date` | date | UTC | Datum der Messung in UTC, wie von FIRMS geliefert. | nie leer | Anzeige im Popup und im CSV. Für Zeitfilter und Summen besser obs_date nehmen. |
| `acq_time` | string | UTC, HHMM | Uhrzeit der Messung als vierstelliger Text, z. B. „0114“. | nie leer | Nur fürs CSV (Originalformat). Zum Rechnen acq_datetime_utc verwenden. |
| `acq_datetime_utc` | timestamp | UTC | Datum und Uhrzeit der Messung als echter Zeitstempel. | nie leer | Zeitachse, Sortierung, Animation des Tagesverlaufs, Anzeige der Überflugzeit. |
| `obs_date` | date | – | Tag, zu dem der Punkt in allen Summen zählt (Zuordnung laut Konfiguration: UTC-Datum oder Sonnendatum). | nie leer | Der Zeitfilter der Karte und der Schlüssel zu day_status und zur Tagestabelle. |
| `local_solar_hour` | double | Stunden 0–24 | Lokale Sonnenzeit des Überflugs: UTC-Stunde + Länge / 15. | nie leer | Tageszeit im Popup („erkannt um 13:20 Ortszeit“), Auswertung nach Tageszeit. |
| `satellite` | string | – | Satellit: Terra, Aqua (MODIS), SNPP, N20 (NOAA-20) oder N21 (NOAA-21) (VIIRS). | nie leer | Herkunft im Popup und im CSV. Nicht zum Vergleichen von Zahlen zwischen Satelliten. |
| `sensor` | string | – | Instrument: MODIS (Terra, Aqua, 1-km-Pixel) oder VIIRS (SNPP, NOAA-20, NOAA-21, 375-m-Pixel). | nie leer | Symbol oder Legende auf der Karte. Pflichtbegleiter für frp_class und confidence_class. |
| `source` | string | – | archive (endgültig, geprüft) oder nrt (vorläufig, wird später durch Archivdaten ersetzt). | nie leer | Vorläufige Punkte kennzeichnen, z. B. gestrichelt oder mit Hinweis „vorläufig“. |
| `daynight` | string | – | D (Tag-Überflug) oder N (Nacht-Überflug). | nie leer | Filter Tag/Nacht, Symbol im Popup. |
| `frp` | double | MW | Strahlungsleistung des Feuers in diesem Pixel (Fire Radiative Power). | 0 möglich, nie leer | Größe oder Farbe des Punkts. Nur innerhalb eines Sensors vergleichen: ein VIIRS-Pixel ist kleiner und zeigt weniger MW für dasselbe Feuer. |
| `frp_class` | string | – | Klasse der Pixel-FRP: low (unter 10 MW), mid (10–50 MW), high (ab 50 MW). | nie leer | Farbstufen der Punkte, Filter auf der Karte und im CSV. Nicht für Summen über die Jahre: vor 2012 fehlen die schwachen Feuer. |
| `confidence_class` | string | – | Güte der einzelnen Erkennung laut FIRMS: low, nominal, high. | leer, wenn der Originalwert unlesbar ist | Filter „unsichere Erkennungen ausblenden“. Nur zusammen mit sensor: VIIRS-„high“ bedeutet nur „Kanal gesättigt“. |
| `confidence_raw` | string | – | Originalwert von FIRMS: Zahl 0–100 bei MODIS, l / n / h bei VIIRS. | nie leer | Nur fürs CSV für Fachleute. Im UI nicht nötig. |
| `scan` | double | km | Pixelbreite quer zur Flugrichtung. | nie leer | Fußabdruck des Pixels zeichnen (zusammen mit track). |
| `track` | double | km | Pixelbreite in Flugrichtung. | nie leer | Fußabdruck des Pixels zeichnen (zusammen mit scan). |
| `pixel_area_km2` | double | km² | Fläche des Pixels am Boden: scan × track. | nie leer | Punkt in echter Größe darstellen. Große Werte heißen Bildrand und damit gröbere Ortsangabe. |
| `region_id` | string | – | NUTS-2-Region des Punkts (Stand 2021), z. B. ES30. | leer bei Punkten im offenen Meer | Schneller Filter „Region wählen“, Verknüpfung zur Tagestabelle. |
| `country` | string | – | Land: die ersten zwei Zeichen von region_id (ES, PT, FR). | leer wie region_id | Filter nach Land. |
