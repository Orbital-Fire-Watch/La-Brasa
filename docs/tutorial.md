# La Brasa: Tutorial

La Brasa zeigt, wo Satelliten in Spanien und Portugal aktive Feuer erkannt haben. Die App vergleicht die aktuelle Lage
mit früheren Jahren und zeigt, wie sich die Feuersaison entwickelt. Die Daten stammen von NASA FIRMS, gemessen mit
den Instrumenten MODIS (Terra, Aqua) und VIIRS (Suomi NPP, NOAA-20, NOAA-21).

Das Tutorial führt einmal mit einem **Testgebiet** durch alle Funktionen: **Galicia** zum Stichtag **15.08.2025**.
Jeder Schritt sagt, was zu tun ist (**Tun**) und worauf zu achten ist (**Sehen**).

> Die Oberfläche gibt es auf Englisch, Spanisch und Portugiesisch. Die Bezeichnungen der Knöpfe stehen hier so, wie sie
> in der englischen Fassung heißen, z. B. „Analysis“.

---

## 0. Begriffe in einer Minute

| Begriff | Bedeutung |
|---|---|
| **Hotspot** | Ein Satellitenpixel, in dem beim Überflug ein aktives Feuer erkannt wurde. Ein Hotspot ist **keine** verbrannte Fläche. |
| **Harmonisiert** | Die Satellitenflotte hat sich über die Jahre verändert (ab 2012 kam VIIRS mit viel kleineren Pixeln dazu). Deshalb wird jede Erkennung gewichtet und in „MODIS-Aqua-Äquivalente“ umgerechnet. So bleiben 2005 und 2025 vergleichbar. Das ist die Standardansicht. |
| **Roh (raw)** | Die unkorrigierten Erkennungen einer Instrumentenfamilie (MODIS oder VIIRS). Roh-Zahlen von MODIS und VIIRS lassen sich nicht direkt vergleichen (1 km gegen 375 m Pixel). |
| **FRP** | Fire Radiative Power in Megawatt (MW), also wie stark ein Feuer strahlt. |
| **Feuerereignis (Event)** | Hotspots, die räumlich nah beieinander liegen (H3-Zellen höchstens 2 Zellen, ca. 1,8 km, auseinander) und höchstens 2 Tage auseinanderliegen, mindestens 2 Hotspots. Das ist wahrscheinlich derselbe Brand. Ein einzelner Hotspot ohne Nachbarn ist kein Ereignis. Auf der Karte ist der Kern (direkt benachbarte Zellen) kräftig gefüllt, Ausläufer im zweiten Ring blass und gestrichelt. |
| **H3-Zelle** | Ein Sechseck aus einem weltweiten Raster. Je weiter man hineinzoomt, desto kleiner werden die Zellen. |
| **Confidence** | Wie sicher sich das Satellitenprodukt ist, dass es ein Feuer ist. „Standard“ zählt nominale und hohe Sicherheit, „High only“ nur hohe. Werte aus beiden Einstellungen nicht miteinander vergleichen. |
| **Stichtag (Reference date)** | Der Tag, auf den sich alles bezieht. Voreingestellt ist der letzte Tag mit Daten. |

---

## Teil 1: Die Startseite

### Aufbau auf einen Blick

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Logo La Brasa        [Exit …]     Fetch · Tutorial · Sprache · Info · Access.│
│┌─────────────┐                                       Map|Satellite  [+][−][⛶]│
││ Settings    │        Info-Boxen (erscheinen nach 2 s)                       │
││ Area        │                                                               │
││ Calendar    │               Vollbild-Karte                ┌───────────────┐ │
││ Fire-prone  │                                             │ Legende       │ │
││ areas       │                                             │ Selected area │ │
│└─────────────┘                                             │ [ Analysis ]  │ │
│ Maßstab     Data view: Harmonised|MODIS|VIIRS|Compare      └───────────────┘ │
│             Select area: Rectangle|Circle|Polygon|Freehand                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Links** schweben die Kacheln. Ein Klick auf die Überschrift klappt eine Kachel auf oder zu.
- **Oben rechts in der Karte** liegen der Umschalter **Map / Satellite**, die Zoom-Knöpfe und der Vollbild-Knopf.
- **Unten in der Mitte** liegen die Datenansicht und die Zeichenwerkzeuge.
- **Unten rechts** stehen Legende, aktuelle Auswahl und der Knopf **Analysis**.

Die Karte zeigt immer die **30 Tage bis zum Stichtag**.

### Schritt 1: Erster Blick auf die Karte

**Tun:** Nichts. Die Seite nach dem Laden zwei Sekunden in Ruhe lassen.

**Sehen:**
- Spanien und Portugal sind hell, alles außerhalb ist abgedunkelt.
- Farbige Sechsecke (H3-Zellen) zeigen die harmonisierten Hotspots der letzten 30 Tage, von gelb (wenig) bis rot (viel).
  Die Legende unten rechts nennt den Höchstwert.
- Nach 2 Sekunden gleiten **drei Info-Boxen** herein:
  1. Hotspots in den letzten 30 Tagen, mit „… × the usual for this time of year“ (Vergleich mit der gleichen Jahreszeit
     in anderen Jahren),
  2. FRP in den letzten 30 Tagen, ebenfalls mit Vergleich,
  3. Hotspots seit dem 1. Januar, verglichen mit dem Vorjahr zum gleichen Datum.
- Sobald man die Karte bewegt, verschwinden die Boxen. Zwei Sekunden nach dem Anhalten kommen sie wieder.

### Schritt 2: Stichtag, Confidence und Methode einstellen (Kachel „Settings“)

**Tun:** In **Reference date** den **15.08.2025** eintragen.

**Sehen:** Karte, Info-Boxen und Kalender rechnen neu. Mit **Latest** kommt man jederzeit zum letzten Tag mit Daten
zurück.

Die beiden anderen Felder zum Ausprobieren:
- **Confidence:** *Standard* oder *High only*. Das **i** daneben erklärt den Unterschied.
- **Method** legt fest, was gezählt wird:
  - *Hotspots*: harmonisierte Hotspots (Standard),
  - *FRP*: harmonisierte Strahlungsleistung in MW,
  - *Events*: neue Feuerereignisse. Ihre Zahl hängt von der Satellitenflotte ab, deshalb sind sie erst ab 2012 sinnvoll
    vergleichbar. Die Karte zeigt in dieser Methode weiterhin Hotspots, weil Zellen keine Ereignisse kennen.

**Tun:** Method wieder auf **Hotspots** stellen.

### Schritt 3: Das Testgebiet wählen (Kachel „Area“)

Es gibt drei Wege zu einem Gebiet:

1. **Suche:** In **Search area** mindestens zwei Buchstaben tippen, z. B. „gali“, dann **Galicia** anklicken.
2. **Baum:** Neben **Spain** auf den Pfeil klicken, um die Regionen aufzuklappen, dann **Galicia** wählen.
3. **Karte:** Direkt auf Galicia in der Karte klicken. Beim Darüberfahren wird die Region blau hervorgehoben.

**Tun:** Galicia auf einem der drei Wege wählen.

**Sehen:**
- Die Karte zoomt auf Galicia, alles außerhalb wird abgedunkelt, die Grenze ist umrandet.
- Oben in der Kachel steht der Pfad **Spain and Portugal › Spain › Galicia**. Jeder Teil ist anklickbar, das **×**
  hebt die Auswahl auf.
- Unten rechts unter **Selected area** stehen „Galicia, Region“ und die Knöpfe **Show all of Spain** und
  **Clear selection**.
- Oben auf der Karte erscheint **Exit Galicia**. Der Knopf oder **Esc** geht eine Ebene hoch (Region → Land → ganz
  Spanien und Portugal) und zoomt dabei heraus.
- Info-Boxen und Kalender gelten jetzt nur noch für Galicia.

> Die App kennt Länder und Regionen (NUTS-2, Galicia ist `ES11`), aber keine Provinzen. Die Balearen sind nicht in den
> Daten, deshalb steht bei „ganz Spanien und Portugal“ der Zusatz „Mainland“.

### Schritt 4: In die Karte zoomen

**Tun:** In Galicia hineinzoomen (Mausrad oder **+**), bis einzelne Punkte erscheinen.

**Sehen:**
- Je näher man kommt, desto **kleiner werden die Sechsecke**. Das **i** in der Legende nennt die aktuelle
  H3-Auflösung.
- Ab **Zoomstufe 11** zeigt die Karte **einzelne Hotspots** statt Zellen. Ihre Farbe gibt das Alter an: dunkelrot =
  am Stichtag aktiv, orange = in den letzten 2 Tagen, hell = älter.
- **Klick auf eine Zelle** öffnet ein Fenster mit harmonisierten Hotspots, FRP-Summe, Roh-Hotspots und Zeitraum.
- **Klick auf einen Hotspot** zeigt Datum und Uhrzeit (UTC), Satellit, Confidence, FRP, Tag- oder Nachtüberflug und
  die Region.
- Gibt es zu viele Punkte, sagt die Legende „… of … points shown (strongest FRP)“.
- Oben rechts kann man mit **Satellite** auf ein Luftbild umschalten und mit **Map** zurück. Die Wahl merkt sich der
  Browser für beide Seiten.

### Schritt 5: Der Kalender (Kachel „Calendar“)

**Sehen:** Eine Heatmap mit **Jahren als Zeilen** (neuestes oben) und **Monaten als Spalten**, hier für Galicia. Je
dunkler das Rot, desto mehr Feuer. Beim Darüberfahren steht der Wert unter dem Raster. Laufende Monate sind markiert.
Hat ein Monat keine Daten, ist er gesperrt.

**Tun:** Auf **August 2025** klicken.

**Sehen:** Der Stichtag springt auf das Monatsende (31.08.2025) und die Karte zeigt die 30 Tage davor. Für das
Tutorial danach in **Settings** wieder den **15.08.2025** eintragen.

> Mit der Tastatur: ein Feld anwählen, mit den Pfeiltasten wandern und mit Enter auswählen.

### Schritt 6: Orte, an denen es oft brennt (Kachel „Fire-prone areas“)

**Tun:** Bei **Fire-prone areas** auf **Show** klicken.

**Sehen:** Die 8 Orte mit der meisten Feueraktivität seit Beginn der Daten (2000), jeweils mit Region, Koordinaten und
Summe. Die Liste gilt immer für ganz Spanien und Portugal, nicht nur für das gewählte Gebiet.

**Optional:** Ein Klick auf einen Ort macht dessen Sechseck zum gezeichneten Gebiet (siehe Schritt 7). Danach mit
**Remove drawn area** oder dem Pfad in der Kachel „Area“ zurück zu Galicia.

### Schritt 7: Ein eigenes Gebiet zeichnen (unten: „Select area“)

Vier Werkzeuge stehen zur Wahl. Über der Leiste steht jeweils ein kurzer Hinweis.

| Werkzeug | Bedienung |
|---|---|
| **Rectangle** | Auf der Karte ziehen |
| **Circle** | Vom Mittelpunkt nach außen ziehen |
| **Polygon** | Eckpunkte anklicken, mit Doppelklick oder Enter abschließen. Rücktaste nimmt den letzten Punkt zurück |
| **Freehand** | Maustaste halten und den Umriss fahren |

**Esc** bricht das Zeichnen ab. Ein zweiter Klick auf dasselbe Werkzeug schaltet es aus.

**Tun:** **Rectangle** wählen und ein Rechteck um den Süden Galicias (Ourense) ziehen.

**Sehen:** Kurz erscheint „Registering area“. Danach ist das Rechteck die Auswahl: Unter **Selected area** steht
„Drawn area, approx. … km²“ und die Karte zeigt nur noch dieses Gebiet. **Remove drawn area** entfernt es wieder.

> Den Umriss eines gezeichneten Gebiets kennt nur der Browser-Tab, in dem er gezeichnet wurde. Wer den Link in einem
> anderen Browser öffnet, sieht „Outline no longer available“ und muss das Gebiet neu zeichnen.

**Tun:** Für den weiteren Ablauf wieder **Galicia** wählen.

### Schritt 8: Datenansicht und MODIS/VIIRS-Vergleich (unten: „Data view“)

**Tun:** Nacheinander **MODIS raw**, **VIIRS raw** und **Compare** anklicken.

**Sehen:**
- **MODIS raw** und **VIIRS raw** zeigen auf der Karte nur die unkorrigierten Erkennungen einer Familie. Links
  erscheint oben die zusätzliche Kachel **MODIS vs VIIRS** mit einer Tabelle (Erkennungen, Anteil, FRP-Summe,
  mittlere FRP, Tage mit Erkennungen, Satelliten, Pixelgröße), Tagesbalken und dem Verhältnis („VIIRS detected … × as
  many hotspots as MODIS“).
- **Compare** zeigt **zwei Karten nebeneinander**, links MODIS und rechts VIIRS, mit **derselben Farbskala**. Gleiche
  Farbe bedeutet also gleiche Zahl. Beide Karten bewegen sich gemeinsam. Info-Boxen und Zeichenwerkzeuge sind in
  dieser Ansicht ausgeblendet.
- Vor 2012 gibt es keine VIIRS-Daten.

**Tun:** Zurück auf **Harmonised**.

### Schritt 9: Zurück zum Start und neue Daten holen (Kopfzeile)

**Sehen:**
- Ein Klick auf das **Logo La Brasa** oben links führt immer zur Startseite, ohne Auswahl (ganz Spanien und Portugal,
  letzter Tag). Der Zurück-Knopf des Browsers bringt die vorherige Ansicht wieder.
- **Fetch** oben rechts fragt beim Server die neuesten Satellitendaten an und lädt danach alle Ansichten neu. Während
  der Abfrage steht dort „Fetching“, danach z. B. „Updated 14:05, 312 new hotspots“ oder „Up to date (14:05)“.
- Kann der Server keine neuen Daten holen, steht dort „Fetch not available“. Das **i** daneben nennt den Grund (auf dem
  Server fehlt der FIRMS-Schlüssel oder die Pipeline). Es wurde dann nichts geändert.

**Tun:** Nichts drücken, damit Galicia gewählt bleibt.

### Schritt 10: Zur Auswertung

**Tun:** Unten rechts auf **Analysis** klicken.

Die Auswertung übernimmt Gebiet (Galicia), Stichtag (15.08.2025), Confidence, Methode und Datenansicht.

---

## Teil 2: Die Auswertung (Analysis)

Die Seite ist von oben nach unten aufgebaut. Jede Kachel lässt sich über ihre Überschrift auf- und zuklappen, und
jedes **i** erklärt, wie der Wert berechnet wird.

### Schritt 11: Kopfzeile und Werkzeugleiste

**Sehen:**
- In der Kopfzeile: **Area** (Galicia, Region), **Reference date** (15.08.2025) und **Confidence**.
- In der Werkzeugleiste:
  - **Method** (Hotspots / FRP / Events) zum Umschalten direkt hier,
  - **Show all of Spain** wechselt von der Region auf das ganze Land,
  - **Download CSV** lädt alle Hotspots des Rückblickzeitraums bis zum Tag des Zeitreglers herunter,
  - **Edit selection** führt zurück zur Startseite, Gebiet und Einstellungen bleiben dabei erhalten.

### Schritt 12: Ausblick für die nächsten 10 Tage („Outlook for …“)

Der Ausblick steht ganz oben, über der kurzfristigen Lage. Es gibt ihn nur, wenn **eine Region** gewählt ist (nicht
für ein ganzes Land, ganz Spanien und Portugal oder ein gezeichnetes Gebiet) und der Tag höchstens **10 Tage vor dem
letzten Tag mit Daten** liegt. Am 15.08.2025 ist er deshalb nicht zu sehen.

**Tun:** In der Kopfzeile auf **Edit selection**, in **Settings** auf **Latest** und wieder auf **Analysis** klicken.

**Sehen:**
- Die Hauptzeile sagt, wie wahrscheinlich große Feuer in Galicia in den nächsten 10 Tagen sind, verglichen mit dem
  Üblichen für diese Jahreszeit, z. B. „↓ 95 % lower fire danger than usual“ oder „↑ 2.5 times the usual fire danger“.
- Darunter drei Abschnitte (Tag 1–3, 4–7 und 8–10) mit einer Stufe: *low, normal, increased, high, very high*.
- Unten stehen der Stand („As of 15 Nov“) und die Datenquellen. Ist der Ausblick älter als 2 Tage, ist der Stand
  hervorgehoben.
- Das **i** erklärt: Der Ausblick beruht auf den aktuellen Feuern und der Wettervorhersage. Er sagt nicht, wo genau ein
  Feuer ausbricht, und je weiter voraus, desto unsicherer.

**Tun:** Für die weiteren Schritte den Stichtag wieder auf den **15.08.2025** stellen (über **Edit selection** und
**Settings**).

### Schritt 13: Kurzfristige Lage („Short-term analysis“)

Vier Karten beziehen sich auf den Tag des Zeitreglers:

| Karte | Aussage |
|---|---|
| **This week compared** | Summe der letzten 7 Tage im Verhältnis zum Median derselben 7 Tage in allen anderen Jahren, z. B. „3,2 ×, the usual amount“. Dazu der Rang („rank 2 of 26“, Rang 1 = höchster Wert). Rot = deutlich mehr, blau = deutlich weniger |
| **Active fire events** | Ereignisse mit mindestens einem Hotspot an diesem Tag, verglichen mit dem Vortag, und wie viele davon neu sind |
| **Season phase** | Wo der Tag in der typischen Saison liegt: *Before the season, Rising, Peak phase, Declining, After the season* oder *No clear season*. Dazu die Tage bis zum oder seit dem typischen Höhepunkt, das typische Höhepunktdatum und eine Mini-Kurve mit Markierung |
| **Strongest fire** | Das Feuerereignis mit der größten FRP-Summe im Rückblickzeitraum, mit Startdatum und Fläche. **Show on map** wählt es aus und zoomt hin |

**Tun:** Bei **Strongest fire** auf **Show on map** klicken.

### Schritt 14: Karte, Rückblick und Feuerliste

**Sehen:** Die Karte zoomt auf das stärkste Feuer. Es ist blau umrandet, seine einzelnen Hotspots sind eingeblendet,
und rechts in der Liste ist es markiert.

**Einstellungen über der Karte:**
- **Look-back:** *1 day / 7 days / 14 days*. So weit zurück zählen Karte und Liste ab dem Tag des Zeitreglers.
- **Show:** *Events* zeigt Feuerereignisse als Flächen (weit herausgezoomt als Kreise, deren Größe der FRP entspricht).
  *H3 cells* zeigt Sechsecke, deren Deckkraft die Menge angibt.
- Die Farbe gibt das Alter an: am Stichtag aktiv, letzte 2 Tage, älter, erloschen (grau).
- Blasse, gestrichelte Flächen um ein Ereignis sind seine **Ausläufer** (bis zu 2 Zellen vom Kern). Die Legende nennt
  sie „Outskirts: up to 2 cells from the core“.
- Gestrichelt umrandete Feuer sind **wahrscheinlich von Wolken verdeckt** (siehe Schritt 18).
- Ab Zoomstufe 11 erscheinen wieder einzelne Hotspots.

**Feuerliste rechts:**
- Jeder Eintrag zeigt Name („Fire in Galicia, 14 Aug“), Status („new, active today“, „active for 5 days“, „ended,
  last seen 4 days ago“), FRP in MW, Fläche, Zahl der Hotspots und den Trend (*growing / stable / shrinking*).
- **Sort by** sortiert nach Intensity (FRP), Area, Duration, Hotspots, Start oder Last seen.
- Ein Klick auf einen Eintrag wählt das Feuer aus und zoomt hin. Darüber erscheint eine Box mit **Zoom to fire** und
  **Close**. Ein Klick auf ein Feuer in der Karte wählt es ebenfalls aus.
- Bleibt ein Feuer ausgewählt, während der Zeitregler vor seinen Beginn oder nach sein Ende wandert, bleibt die Box
  stehen und sagt „Not started yet on this day …“ bzw. „Already over on this day …“.
- Es werden 40 Einträge angezeigt. **Show … more** lädt weitere nach.

**Tun:** In der Liste ein anderes Feuer anklicken, danach **Close**.

### Schritt 15: Ungewöhnliche Aktivität („Show anomalies“)

**Tun:** Über der Karte auf **Show anomalies** klicken.

**Sehen:** Die Karte färbt jetzt die **Abweichung** vom Median derselben Zeit in anderen Jahren: **rot = mehr**,
**blau = weniger** als üblich. Das Zeitfenster ist mindestens 7 Tage lang. Mit **Compare with** wählt man die
Vergleichsjahre (*all years / last 10 years / last 5 years*). Ein Klick auf eine Zelle zeigt Wert, Median, Differenz
und Rang. Anomalien sind immer H3-Zellen, deshalb ist der Umschalter **Show** (Events / H3 cells) so lange
ausgeblendet. Der Knopf heißt jetzt **Hide anomalies**.

**Tun:** Auf **Hide anomalies** klicken.

### Schritt 16: Der Zeitregler unter der Karte

**Sehen:** Der Zeitregler reicht **60 Tage vor und nach dem Stichtag**. Die kleinen Balken zeigen den Tageswert.
Der Stichtag ist markiert.

**Tun:** Mit **›** (One day forward) drei Tage vorgehen, oder den Regler ziehen.

**Sehen:** Neben dem Datum steht „+3 days from the reference date“. Karte, Liste, die vier Karten und der Punkt in der
Saisonkurve folgen dem neuen Tag, der Stichtag in der Kopfzeile bleibt. **Back to reference date** springt zurück.

### Schritt 17: Die Saison abspielen (▶ am Zeitregler)

**Sehen:** Links über dem Zeitregler liegen der Knopf **▶** (Play) und die Geschwindigkeit **0.5× / 1× / 2×**.

**Tun:** Auf **▶** klicken.

**Sehen:**
- Die Karte läuft Tag für Tag durch den ganzen Bereich des Zeitreglers. Ein neuer Lauf beginnt am ersten Tag, ein
  pausierter Lauf geht dort weiter, wo er stand.
- Jeder Tag bleibt stehen, bis seine Daten geladen sind. Bei langsamer Verbindung wartet die Animation also, statt Tage
  zu überspringen.
- Die Tabelle „Raw data: MODIS and VIIRS“ bleibt währenddessen auf dem Tag, an dem Play gedrückt wurde („Stays on this
  day during playback.“).
- Die Animation hält an: am Ende des Bereichs, mit **⏸** (Pause), beim Ziehen des Reglers, bei der Auswahl eines
  Feuers, bei einem Klick in die Jahresübersicht, bei einem Fehler und wenn der Browser-Tab in den Hintergrund geht.

**Tun:** Mit **⏸** anhalten und **Back to reference date** klicken.

### Schritt 18: Wolkenbedeckung (unter dem Zeitregler)

Satelliten sehen ein Feuer nicht durch dichte Wolken. Ein ruhiger Tag ist deshalb nicht immer ein Tag ohne Feuer.

**Sehen:**
- Unter den Tagesbalken liegt ein **Streifen mit einem Feld pro Tag**: je kräftiger, desto bewölkter. Gemessen wird bei
  den VIIRS-Überflügen (etwa 13:45 und 01:45 UTC), gemittelt über das gewählte Gebiet. Ein **volles Feld** heißt: bei
  beiden Überflügen mindestens 50 % bedeckt. Beim Darüberfahren stehen die Werte für Tag und Nacht.
- Unter dem Regler steht die Bewölkung des gezeigten Tages, z. B. „5 % by day · 4 % at night“. An bewölkten Tagen
  kommt „fires may be hidden“ dazu.
- Ein Feuer, das am Vortag und am Folgetag gesehen wurde und dazwischen unter Wolken lag, hat wahrscheinlich
  weitergebrannt. Es ist auf der Karte **gestrichelt**, steht in der Liste als „probably hidden under clouds“ und in
  der Legende. Unter dem Regler steht dann „… fires probably hidden (dashed on the map)“, und das Feld des Tages im
  Streifen ist gestrichelt.

**Tun:** Mit **›** zu einem vollen Feld im Streifen gehen und den Hinweis unter dem Regler lesen. Dann zurück zum
Stichtag.

> Den Streifen gibt es nur, wenn die Datenbank Wolkendaten enthält (Tabelle `cloud_daily`). Ohne sie fehlen Streifen
> und Hinweis, alles andere funktioniert wie gewohnt.

### Schritt 19: MODIS und VIIRS roh („Raw data: MODIS and VIIRS, 30 days up to …“)

**Sehen:** Dieselbe Vergleichstabelle wie auf der Startseite, für die 30 Tage bis zum Tag des Zeitreglers. Wurden mehr
Punkte gefunden, als die API auf einmal liefert, warnt ein Hinweis, dass die Zahlen nur eine Untergrenze sind.

### Schritt 20: Saisonkurve („Season curve“)

**Sehen:**
- Die **farbige Linie** ist das gewählte Jahr (2025), über 7 Tage geglättet.
- Die **gestrichelte Linie** ist der Median aller Jahre, das **graue Band** der typische Bereich (25–75 %).
- Der **Punkt** markiert den Tag des Zeitreglers und wandert mit.
- Beim Darüberfahren erscheinen die Werte für jeden Kalendertag.

**Tun:** Über die Auswahl **+ Jahr vergleichen** ein Vergleichsjahr hinzufügen, z. B. 2017, oder auf **Stärkstes
Jahr** bzw. **Schwächstes Jahr** klicken. Ein Klick auf den Jahres-Chip mit **✕** entfernt es wieder.

### Schritt 21: Jahresübersicht („Year overview“)

**Sehen:** Eine Heatmap mit **Jahren als Zeilen** und **Wochen** oder **Monaten** als Spalten (Umschalter
**Columns**). Schraffierte Felder sind unvollständig, ein gestrichelter Rahmen bedeutet, dass der Zeitraum noch läuft.

**Tun:**
1. Unter **Shape** auf **Ring calendar** umschalten. Dieselben Werte erscheinen als Ringe, das älteste Jahr innen. Dann
   zurück auf **Heatmap**.
2. Ein Feld anklicken.
   - Liegt das Feld in den 60 Tagen um den Stichtag, bewegt sich nur der Zeitregler.
   - Liegt es weiter weg, wird es der **neue Stichtag** und die ganze Seite rechnet neu.
3. Die Datenansicht in dieser Kachel auf **Compare** stellen. Es erscheinen zwei Roh-Heatmaps (MODIS und VIIRS) mit
   gemeinsamer Skala und darunter die Roh-Erkennungen pro Jahr als Balken. Grau heißt „kein Satellit dieser Familie“
   (VIIRS vor 2012), schraffiert heißt „durch das API-Limit unvollständig“. Beim ersten Mal lädt die Ansicht einige
   Sekunden („Loading raw data per sensor: … of …“). Der Ringkalender ist nur für harmonisierte Daten verfügbar.

**Tun:** Zurück auf **Harmonised**. Mit **Edit selection** geht es zurück zur Startseite.

**Fußzeile:** Datenstand („Data as of …“), `data_version`, `weight_version` und Quellenangabe.

---

## Teil 3: Kopfzeile und Einstellungen (auf beiden Seiten)

| Element | Funktion |
|---|---|
| **Logo** | Zurück zur Startseite ohne Auswahl (siehe Schritt 9) |
| **Fetch** | Holt die neuesten FIRMS-Daten über das Backend und lädt danach alle Ansichten neu, ohne dass die Karte neu aufgebaut wird. Danach steht dort z. B. „Updated 14:05, 312 new hotspots“ oder „Up to date (14:05)“, ohne Datenzugang auf dem Server „Fetch not available“. Der Tooltip nennt die Datenversion |
| **Tutorial** | Startet das geführte Tutorial (nur auf der Startseite). Beim ersten Besuch startet es von selbst |
| **Sprache** (Globus) | English, Español, Português. Voreingestellt ist die Sprache des Browsers |
| **Info** | Eine Infoseite zu Datenquelle, Begriffen und Grenzen, mit Links zu EFFIS, FIRMS und H3 |
| **Accessibility** | *Colour theme* (Dark, Light, High contrast), *Data colours* (Standard oder Colour-blind safe), *Text size* (A / A+ / A++), *Reduce motion*, *Reset* (die Sprache bleibt erhalten) |

Sprache, Darstellung und Hintergrundkarte merkt sich der Browser.

---

## Gut zu wissen

- **Alles steht in der Adresse.** Gebiet, Stichtag, Methode, Confidence, Rückblick, Datenansicht und ausgewähltes
  Feuer stehen in der URL, z. B. `/?page=analysis&region=ES11&date=2025-08-15`. Neu laden, Zurück-Knopf und Teilen des
  Links funktionieren deshalb. Einzige Ausnahme sind gezeichnete Gebiete (siehe Schritt 7).
- **Hotspots sind keine verbrannte Fläche.** Satelliten sehen einen Ort nur wenige Male am Tag. Kleine oder kurze Feuer
  können fehlen, Wolken und Rauch verdecken Feuer, und heiße Industrieanlagen können als Hotspot erscheinen. Bewölkte
  Tage und wahrscheinlich verdeckte Feuer markiert die App (Schritt 18).
- **Der letzte Tag** mit Daten kann unvollständig sein.
- **Ereignisse** sind erst ab 2012 sinnvoll über Jahre vergleichbar. Wachsen zwei Brände zusammen, kann die Nummer des
  jüngeren verschwinden. Die App meldet dann „This fire event no longer exists.“
- **Fehlermeldungen** erscheinen dort, wo die Daten fehlen, meist mit **Try again**. Bei „The request took too long“
  hilft ein kleineres Gebiet oder ein kürzerer Zeitraum.
