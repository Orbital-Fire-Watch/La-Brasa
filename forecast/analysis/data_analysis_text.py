"""Interpretation texts for data_analysis.html (written after reading the numbers of the run on 14.11.2026).

If the data change, rerun data_analysis.py and check that the texts still match the numbers.
"""

TEXTS = {
    "intro": (
        "Grundlage für die Modelle der Tage 1–10 und der Wochen 2–4, die <strong>ohne Wetterdaten</strong> auskommen. "
        "Quelle: <code>data/harmonised/activity_daily_harmonised.parquet</code>, nur VIIRS-gemessene Tage "
        "(ab 20.01.2012), ohne Tage mit Verdacht auf Datenausfall. Ab Abschnitt 7 nutzen alle Merkmals-Analysen "
        "<strong>nur die Trainingsjahre 2012–2021</strong>. So sieht die Modellwahl die Testjahre 2022–2026 nicht. "
        "Erzeugt mit <code>forecast/analysis/data_analysis.py</code>, alle Zahlen stehen in "
        "<code>data_analysis_results.json</code>."
    ),

    "s1": (
        "<p>124.108 Region-Tage in 23 Regionen sind gemessen und nutzbar (2012-01-20 bis 2026-11-13). Davon sind "
        "83.490 Training (bis 2021) und 40.618 Test. 368 gemessene Tage fallen wegen <code>possible_gap</code> heraus. "
        "An 253 gemessenen Tagen fehlt SNPP, dort gibt es keinen SNPP-Feuertag. 105 Tage sind vorläufig (NRT).</p>"
        "<p><strong>Für die Modelle:</strong> Die Datenmenge reicht für einfache und mittlere Modelle. Die Einheit, die "
        "wirklich unabhängig ist, sind aber Jahre: Es gibt nur 10 Trainingsjahre. Jede Aufteilung muss deshalb nach "
        "ganzen Jahren schneiden.</p>"),

    "s2": (
        "<p>Großfeuer-Tage (FRP ≥ 100 MW) sind <strong>selten: 2,9 % der Region-Tage</strong>, 3.566 Stück, davon 2.385 "
        "im Training und 1.181 im Test. Sie tragen aber <strong>91 % der gesamten Strahlungsleistung</strong>. Sie sind "
        "also das, was zählt. Feuertage nach SNPP gibt es an 27,8 % der Region-Tage.</p>"
        "<p>Die Verteilung ist extrem ungleich: PT11 Norte hat 657 Großfeuer-Tage (12 % seiner Tage), ES21 País Vasco 5. "
        "<strong>8 Regionen haben im Training weniger als 30 Großfeuer-Tage</strong> (ES24, PT15, ES30, PT17, FRJ1, ES62, "
        "ES23, ES21), drei davon unter 10. Für diese Regionen lässt sich kein eigenes Modell schätzen. Sie brauchen ein "
        "gemeinsames Modell mit Regionseffekt, der zum Mittel hin gezogen wird (partial pooling). Ihre Güte lässt sich "
        "nur grob angeben.</p>"
        "<p><strong>Folge für die Metrik:</strong> Eine Trefferquote (Accuracy) ist hier wertlos. „Nie Großfeuer“ hätte "
        "97,1 % Accuracy. Es braucht Maße für Wahrscheinlichkeiten seltener Ereignisse: Brier Score, Log Loss, PR-AUC.</p>"),

    "s3": (
        "<p>Bestätigt: <code>n_harm &gt; 0</code> springt mit NOAA-20 (2018) und NOAA-21 (2023) nach oben "
        "(2017: 0,33 → 2019: 0,42; 2024: 0,39 gegenüber 0,23 mit SNPP allein). Die SNPP-Rate bleibt dagegen zwischen "
        "0,23 und 0,33, ohne Sprung an den Startterminen. Die Großfeuer-Rate zeigt ebenfalls keinen Sprung. 2018 ist "
        "mit 0,012 ein echtes ruhiges Jahr, kein Messeffekt: Das Jahr begann vor dem Start von NOAA-20, und die "
        "SNPP-Rate ist ebenfalls niedrig.</p>"
        "<p>Auffällig: Auch die SNPP-Rate liegt im Test etwas tiefer (siehe Abschnitt 12), 2023/2024 bei 0,25/0,23. "
        "Ob das am Altern von SNPP liegt oder an echten ruhigeren Jahren, lässt sich hier nicht trennen.</p>"
        "<p><strong>Für die Modelle:</strong> Hauptziel <code>big_fire_day</code>, zweites Ziel <code>n_snpp &gt; 0</code>. "
        "Beim zweiten Ziel die Kalibrierung im Test genau prüfen (Mittelwert vorhergesagt gegen beobachtet).</p>"),

    "s4": (
        "<p>65 % der Region-Tage haben FRP = 0. An Feuertagen liegt der Median der Tagessumme bei 4,9 MW, das 99-%-Quantil "
        "bei 1.766 MW, das 99,9-%-Quantil bei 16.332 MW und das Maximum bei 116.216 MW. Die Kurve im log-log-Diagramm "
        "fällt fast gerade ab: ein <strong>schwerer Rand, ähnlich einem Potenzgesetz</strong>. Das stärkste 1 % der "
        "Region-Tage trägt 81 % aller FRP, das stärkste 0,1 % allein 46 %.</p>"
        "<p>Die Zahl der Erkennungen ist extrem überstreut: Varianz/Mittel = 286. Für Poisson müsste das 1 sein.</p>"
        "<p><strong>Für die Modelle:</strong> FRP nie roh als Merkmal verwenden, sondern <code>log1p</code>. "
        "Poisson-Modelle sind ungeeignet, für Mengen nur negativ-binomiale oder Tweedie-Modelle oder Hurdle-Modelle. "
        "Für die Wahrscheinlichkeit eines Großfeuer-Tags ist eine Ja/Nein-Klassifikation passend. Eine ordinale "
        "Variante über die Stärkeklassen (0 / minor / moderate / strong / extreme) nutzt zusätzlich die Information "
        "aus mittleren Tagen.</p>"),

    "s5": (
        "<p>64 % der Großfeuer-Tage liegen von Juni bis Oktober, mit Spitze im August (PT11, PT16, ES41, ES61, ES11, ES43). "
        "<strong>Sechs Regionen haben ihre Spitze aber im Februar oder März</strong>: ES12 Asturias, ES13 Cantabria, "
        "ES21 País Vasco, ES22 Navarra, FRI1 Aquitaine, FRJ2 Midi-Pyrénées. Das passt zu den bekannten Winter- und "
        "Frühjahrsbränden im kantabrischen Raum (Abbrennen von Weiden und Gestrüpp). Die gemeinsame Kurve aller "
        "Regionen hat deshalb zwei Gipfel.</p>"
        "<p><strong>Für die Modelle:</strong> Die Saisonkurve muss <strong>je Region</strong> geschätzt werden. Eine "
        "gemeinsame Saison mit Regionsfaktor wäre für den Norden falsch. Die geglättete Saisonkurve je Region und "
        "Kalendertag ist damit die natürliche <strong>Baseline</strong>.</p>"),

    "s6": (
        "<p>Die Zahl der Großfeuer-Tage je Jahr schwankt stark, zwischen 100 (2018) und 415 (2017). Der "
        "Variationskoeffizient über volle Jahre liegt bei 0,39. 2026 hat bis zum 13.11. schon 324 und ist damit das "
        "dritthöchste Jahr. Spanien und Portugal hängen im Jahresverlauf mittelmäßig zusammen (r = 0,61), Portugal "
        "und Frankreich kaum (0,14).</p>"
        "<p><strong>Für die Modelle:</strong> Ein großer Teil der Varianz ist der „Jahrescharakter“ (Dürre, Hitzewellen). "
        "Die Saisonkurve kennt ihn nicht. Ohne Wetter lässt er sich nur über die <strong>Aktivität der letzten Wochen</strong> "
        "erfassen (30-Tage-Merkmale). Darum gewinnt das Modell auch nach 14–30 Tagen noch etwas, siehe Abschnitt 7. "
        "Für die Auswertung heißt das: Ergebnisse schwanken von Jahr zu Jahr, Unsicherheiten also per Bootstrap über "
        "Jahre angeben.</p>"),

    "s7": (
        "<p>Folgt auf einen Großfeuer-Tag ein weiterer? Ja, deutlich, aber kurz. Am Folgetag ist die Rate "
        "<strong>3,1× so hoch</strong> wie die Saison für dieselben Tage erwarten lässt (0,40 gegenüber 0,13). Nach "
        "3 Tagen ist sie 2,1×, nach 7 Tagen 1,6×, nach 10 Tagen 1,2×. Danach bleibt ein Rest von 1,2–1,5×, das ist "
        "der Jahrescharakter aus Abschnitt 6. Die Autokorrelation der log-FRP-Abweichung von der Saison fällt genauso, "
        "von 0,40 (1 Tag) über 0,12 (7 Tage) auf 0,045 (30 Tage).</p>"
        "<p><strong>71 % der Großfeuer-Episoden dauern nur einen Tag</strong> (Mittel 1,66 Tage, 90 % höchstens 3 Tage). "
        "Die meisten Großfeuer-Tage kommen also ohne Vorwarnung durch einen Großfeuer-Tag davor.</p>"
        "<p><strong>Für die Modelle:</strong> Persistenz trägt die Tage 1–3, ab Tag 7 fast nur noch die Saison. Das "
        "erklärt den Abfall im Machbarkeitstest. Ohne Wetter ist schon für Tag 1 eine harte Grenze eingebaut: Die "
        "Einzeltage lassen sich aus der Feuerhistorie nicht ankündigen. Realistisches Ziel ohne Wetter: klar besser "
        "als die Saison an den Tagen 1–3, kleiner Gewinn bis Tag 7–10.</p>"),

    "s8": (
        "<p>Von Tag zu Tag hängen die Regionen nur schwach zusammen: Die mittlere Korrelation der log-FRP-Abweichung "
        "liegt bei 0,13. Die erste Hauptkomponente erklärt nur 18,6 % der Varianz. Sie lädt vor allem auf den "
        "Nordwesten (PT11 0,32, ES41 0,31, ES12 0,29, PT16 0,28, ES11 0,28, FRI1 0,28), also auf gemeinsame Feuerwetter-"
        "Lagen am Atlantik. Die zweite Komponente (9,3 %) trennt den Norden (FRJ2, FRI1, ES13, ES12 positiv) vom Süden "
        "(ES43, PT18, ES61, PT16 negativ). Das ist der Gegensatz zwischen Winter- und Sommer-Feuerregime aus "
        "Abschnitt 5. Für 90 % der Varianz bräuchte man viele Komponenten. Eine Verdichtung über Regionen per PCA "
        "lohnt sich also nicht.</p>"
        "<p>Seltene Großereignisse betreffen dagegen oft mehrere Regionen. Hat mindestens eine der 3 nächsten Regionen "
        "einen Großfeuer-Tag, liegt die Rate in der Region selbst bei 0,19 am selben Tag (6,6× die Grundrate) und bei "
        "0,16 am Folgetag (5,7×). Ein Teil davon ist Saison, beide Regionen sind dann im Hochsommer.</p>"
        "<p><strong>Für die Modelle:</strong> Die Aktivität der Nachbarregionen am letzten bekannten Tag ist ein "
        "eigenständiges Merkmal. Sie hängt mit den eigenen Merkmalen kaum zusammen (VIF 1,8, Abschnitt 11). Ein gemeinsames "
        "Modell über alle Regionen ist sinnvoll, ein eigenes Modell je Region nicht.</p>"),

    "s9": (
        "<p>Jedes Merkmal einzeln gegen den Großfeuer-Tag, im Training. Zum Vergleich: PR-AUC = 0,029 hieße "
        "„nicht besser als Zufall“. <strong>Achtung bei <code>clim</code></strong>: Die Saisonkurve ist aus denselben "
        "Trainingsjahren geschätzt, ihre AUC von 0,89 ist darum zu gut. Im Machbarkeitstest lag sie auf den Testjahren "
        "bei 0,83.</p>"
        "<p><strong>Vorlauf 1:</strong> Am besten für die seltenen Treffer (PR-AUC) ist die <strong>Feuerstärke der "
        "letzten Tage</strong>: <code>logfrp_last</code> 0,353, <code>logfrp_mean3</code> 0,351, <code>logfrp_mean7</code> "
        "0,299. Das ist fast doppelt so viel wie die Saison (0,200). Merkmale, die nur „Feuer ja/nein“ zählen "
        "(<code>fire_last</code> 0,079, <code>fire_frac3</code> 0,132), sind deutlich schwächer. Die Stärke trägt die "
        "Information, nicht das bloße Vorkommen. <code>big_last</code> hat eine niedrige AUC (0,69), weil es nur zwei "
        "Werte hat, aber eine ordentliche PR-AUC (0,19). Die Nachbarn (<code>nbr_logfrp_last</code>) liegen bei 0,20.</p>"
        "<p><strong>Vorlauf 7:</strong> Kurze Fenster verlieren stark (<code>logfrp_mean3</code> 0,351 → 0,130). "
        "Längere halten sich besser (<code>logfrp_mean30</code> 0,143, <code>days_since_big</code> 0,107). Keines erreicht "
        "die Saison (0,200). Das Modell muss also die Saison als Grundlage nehmen und die Aktivität als Korrektur "
        "darauf setzen.</p>"
        "<p>Die Dezil-Kurven zeigen: Die Rate steigt mit der Aktivität viel steiler als die Saisonerwartung im selben "
        "Dezil. Die Aktivität bringt also Information über die Saison hinaus, und der Zusammenhang ist nicht linear, "
        "vor allem im obersten Dezil.</p>"),

    "s10": (
        "<p>Großfeuer-Tage zeigen <strong>keinen klaren Wochentag-Effekt</strong>. Gegenüber der Saison liegt das "
        "Verhältnis zwischen 0,94 (Mi) und 1,11 (Do), ohne Muster, im Rahmen des Zufalls bei etwa 340 Ereignissen je "
        "Wochentag. Feuertage nach SNPP sind am Wochenende seltener (Sa 0,96, So 0,91 gegenüber dem Mittel, Mi/Do 1,04). "
        "Das passt zu kleinen landwirtschaftlichen Feuern an Werktagen.</p>"
        "<p><strong>Für die Modelle:</strong> Den Wochentag nur beim Ziel Feuertag mitnehmen, beim Großfeuer-Tag "
        "höchstens als Test. Feiertage bleiben eine offene Frage (Paket <code>holidays</code>), ihr Effekt ist wohl "
        "ebenfalls klein.</p>"),

    "s11": (
        "<p>Die Merkmale sind stark redundant. „Feuer ja/nein“ und Feuerstärke im selben Fenster hängen mit ρ = 0,92–0,95 "
        "zusammen, 3- und 7-Tage-Fenster mit 0,83, <code>days_since_fire</code> mit den kurzen Fenstern mit −0,82. Der "
        "Varianzinflationsfaktor (VIF) liegt bei <code>logfrp_mean7</code> bei 31, bei <code>logfrp_mean30</code> bei 26, "
        "bei <code>fire_frac30</code> bei 15. Die erste Hauptkomponente erklärt allein 49 %, das ist ein Faktor "
        "„aktuelle Aktivität“. Für 90 % braucht es 8 von 16 Komponenten.</p>"
        "<p><strong>Für die Modelle:</strong> Für die logistische Regression reicht ein schlanker Satz, wenig redundant: "
        "Saison (logit), <code>logfrp_last</code>, <code>logfrp_mean7</code>, <code>logfrp_mean30</code>, "
        "<code>days_since_big</code> (log), <code>nbr_logfrp_last</code>, dazu L2-Regularisierung. PCA als "
        "Modell-Eingabe ist nicht nötig. Sie würde nur die Erklärbarkeit kosten, und Regularisierung löst das Problem "
        "ebenso. Gradient Boosting kommt mit dem vollen Satz zurecht.</p>"),

    "s12": (
        "<p>Im Mittel ist der Test dem Training ähnlich: Die Großfeuer-Rate liegt bei 0,0291 gegenüber 0,0286, die "
        "Saisonkurve sagt für den Test im Mittel 0,0291 vorher, beobachtet sind 0,0291. Beim Großfeuer-Tag ist die "
        "Kalibrierung im Mittel also kein Problem. Die SNPP-Feuertage sind im Test seltener (0,254 gegenüber 0,290, "
        "−12 %). Dort wird ein Modell ohne Korrektur leicht zu hoch liegen.</p>"
        "<p>Je Region verschiebt sich viel: ES23 ×4,1, ES24 ×2,35, ES42 ×1,86, PT16 ×0,63, PT18 ×0,65. Bei Regionen mit "
        "wenigen Ereignissen ist das vor allem Zufall, bei großen Regionen sind es echte Jahresunterschiede.</p>"
        "<p><strong>Für die Auswertung:</strong> Die Güte je Region nur mit Konfidenzintervall und Ereigniszahl "
        "berichten. Für die Modellwahl nur die gepoolte Güte und eine Validierung über mehrere Jahre nehmen, nicht "
        "einzelne Regionen.</p>"),

    "s13": (
        "<ol>"
        "<li><strong>Baseline:</strong> Saisonkurve je Region × Kalendertag, ±7 Tage zirkulär geglättet, nur aus "
        "Trainingsjahren. Einfach, ehrlich und schon stark (AUC 0,83 im Test).</li>"
        "<li><strong>Loss und Hauptmetrik:</strong> Brier Score, berichtet als Brier Skill Score gegenüber der Baseline. "
        "Er bewertet Wahrscheinlichkeiten korrekt und lässt sich in Kalibrierung und Trennschärfe zerlegen. Daneben "
        "Log Loss, PR-AUC (für das seltene Ziel), ROC-AUC, Kalibrierung, Trefferquote und Fehlalarme an einer "
        "Warnschwelle. Keine Accuracy (Abschnitt 2).</li>"
        "<li><strong>Merkmale:</strong> Feuerstärke (log1p-FRP) statt nur „Feuer ja/nein“; Fenster 1, 3, 7 und 30 Tage; "
        "Tage seit dem letzten Großfeuer; Aktivität der Nachbarregionen; Saison als Grundlage. Wochentag nur für den "
        "Feuertag.</li>"
        "<li><strong>Struktur:</strong> ein gemeinsames Modell über alle Regionen mit Regionseffekt, der zum Mittel "
        "hin gezogen wird; keine Modelle je Region (8 Regionen mit weniger als 30 Ereignissen).</li>"
        "<li><strong>Nichtlinearität:</strong> Der Zusammenhang Aktivität → Risiko ist im obersten Dezil steil und hängt "
        "von der Saison ab. Dafür kommen Splines oder Wechselwirkungen in Frage, oder baumbasierte Modelle.</li>"
        "<li><strong>Erwartung:</strong> deutlicher Gewinn an den Tagen 1–3, kleiner Gewinn bis Tag 10, ab Tag 14 fast "
        "nur noch Saison. 71 % der Großfeuer-Tage kommen ohne Großfeuer-Tag davor und bleiben ohne Wetter schwer "
        "vorhersagbar.</li>"
        "<li><strong>Auswertung:</strong> Aufteilung nach ganzen Jahren; Testjahre 2022–2026 erst ganz am Ende "
        "anfassen; Unsicherheit per Bootstrap über Jahre.</li>"
        "</ol>"),
}

METHODS = {}
