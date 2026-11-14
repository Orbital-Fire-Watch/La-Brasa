"""Text, Layout und Stil des Berichts. Zahlen kommen als Platzhalter {{name}} aus build_report.py."""
import re

HEAD = r"""<title>FIRMS-Harmonisierung MODIS–VIIRS</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap">
<style>
/* Layout: eine Lesespalte (max. 880px), Fazit zuerst, Grafiken und Tabellen als abgesetzte Flaechen */
:root{
  --bg:#f4f5f7; --surface:#ffffff; --ink:#10161d; --ink2:#46505c; --muted:#77818d;
  --grid:#e6e9ed; --axis:#c2c8d0; --line:#dde1e6; --accent:#1d5a66; --wash:#e7eff1;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --day:#eda100; --night:#6250d6; --ctx:#898781;
  --body:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;
  --display:"Space Grotesk","Inter",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0e1114; --surface:#171b20; --ink:#eef1f4; --ink2:#b9c1ca; --muted:#8a939e;
    --grid:#262c33; --axis:#3a424b; --line:#2a3038; --accent:#7fc4d1; --wash:#16262b;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70; --day:#c98500; --night:#9085e9; --ctx:#898781;
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#0e1114; --surface:#171b20; --ink:#eef1f4; --ink2:#b9c1ca; --muted:#8a939e;
  --grid:#262c33; --axis:#3a424b; --line:#2a3038; --accent:#7fc4d1; --wash:#16262b;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --day:#c98500; --night:#9085e9; --ctx:#898781;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--body);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:40px 80px;-webkit-text-size-adjust:100%}
main{max-width:880px;margin:0 auto;display:flex;flex-direction:column;gap:20px;min-width:0}
main>*{margin:0;min-width:0}
p,li{max-width:70ch}
h1,h2,h3{font-family:var(--display);font-weight:600;text-wrap:balance;line-height:1.2;letter-spacing:-0.01em}
h1{font-size:clamp(1.9rem,5vw,2.7rem)}
h2{font-size:1.55rem;margin-top:36px;padding-top:28px;border-top:1px solid var(--line)}
h3{font-size:1.12rem;margin-top:12px}
.eyebrow{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:500}
.lede{font-size:1.14rem;color:var(--ink2);max-width:62ch}
a{color:var(--accent);text-underline-offset:2px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
code{font-family:var(--mono);font-size:.9em;background:var(--wash);padding:.08em .32em;border-radius:3px}
pre{font-family:var(--mono);font-size:.86rem;background:var(--surface);border:1px solid var(--line);border-radius:6px;
  padding:14px 16px;overflow-x:auto;line-height:1.5}
ul,ol{padding-left:1.3em;display:flex;flex-direction:column;gap:8px}
.answer{background:var(--wash);border-radius:8px;padding:20px 22px;display:flex;flex-direction:column;gap:10px}
.answer p{margin:0;max-width:68ch}
.answer .big{font-family:var(--display);font-size:1.22rem;font-weight:500;line-height:1.4}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 16px 14px;display:flex;flex-direction:column;gap:4px}
.tile b{font-family:var(--display);font-size:1.9rem;font-weight:600;line-height:1.1}
.tile span{font-size:.88rem;color:var(--ink2);line-height:1.4}
nav.toc{font-size:.92rem;color:var(--ink2)}
nav.toc ol{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:4px 24px;margin:0}
.findings{list-style:none;padding:0;gap:14px}
.findings li{padding-left:16px;border-left:2px solid var(--axis)}
.findings strong{display:block}
figure.chart{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 16px 12px;
  display:flex;flex-direction:column;gap:10px;min-width:0}
figure.chart svg{display:block;width:100%;min-width:540px;height:auto;font-family:var(--body)}
figcaption{font-size:.84rem;color:var(--ink2);line-height:1.45;max-width:78ch}
.scroll{overflow-x:auto;max-width:100%}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.86rem;color:var(--ink2)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.key{display:inline-block;width:16px;height:3px;border-radius:2px}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--axis);stroke-width:1}
svg .ref{stroke:var(--muted);stroke-width:1}
svg .tick{fill:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}
svg .axt{fill:var(--ink2);font-size:12px}
svg .lab{fill:var(--ink2);font-size:12px}
svg .dot{stroke:var(--surface);stroke-width:2}
svg .xh{stroke:var(--muted);stroke-width:1;opacity:0;pointer-events:none}
details.tv{font-size:.86rem;color:var(--ink2)}
details.tv summary{cursor:pointer;width:fit-content}
table{border-collapse:collapse;font-size:.88rem;width:100%;background:var(--surface)}
.scroll>table{border:1px solid var(--line)}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--ink2);font-size:.8rem;line-height:1.3;background:var(--surface)}
table.num td:not(:first-child),table.num th:not(:first-child){text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.hl td{background:var(--wash);font-weight:500}
table.wide{min-width:760px}
table.wide td{line-height:1.45}
.bars{display:flex;flex-direction:column;gap:7px}
.brow{display:grid;grid-template-columns:minmax(120px,230px) 1fr 62px;gap:10px;align-items:center;font-size:.86rem}
.brow:hover .bf{filter:brightness(1.12)}
.bl{color:var(--ink2);overflow-wrap:anywhere;line-height:1.25}
.bt{position:relative;height:14px}
.bf{display:block;height:14px;border-radius:0 4px 4px 0;min-width:2px}
.bv{text-align:right;font-variant-numeric:tabular-nums}
ol.steps{list-style:none;padding:0;counter-reset:s;gap:0}
ol.steps>li{counter-increment:s;display:grid;grid-template-columns:34px 1fr;gap:14px;padding:14px 0;border-bottom:1px solid var(--line);max-width:none}
ol.steps>li::before{content:counter(s);font-family:var(--display);font-weight:600;color:var(--accent);
  width:30px;height:30px;border:1.5px solid var(--accent);border-radius:50%;display:grid;place-items:center;font-size:.9rem}
ol.steps strong{display:block;margin-bottom:2px}
ol.steps div{min-width:0}
.formula{font-family:var(--mono);font-size:.9rem;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:10px 14px;overflow-x:auto;white-space:nowrap}
.note{font-size:.9rem;color:var(--ink2)}
#tip{position:fixed;z-index:20;pointer-events:none;background:var(--ink);color:var(--bg);border-radius:6px;padding:8px 10px;
  font-size:.8rem;line-height:1.35;max-width:260px;box-shadow:0 4px 14px rgba(0,0,0,.22)}
#tip .th{opacity:.75;margin-bottom:3px}
#tip .tr{display:flex;align-items:center;gap:6px}
#tip .tr i{width:10px;height:3px;border-radius:2px;flex:none}
#tip .tr b{font-variant-numeric:tabular-nums}
#tip .tr span{opacity:.75}
@media (max-width:520px){ .brow{grid-template-columns:104px 1fr 54px} h2{font-size:1.35rem} }
@media (prefers-reduced-motion:no-preference){ .bf{transition:filter .12s} }
</style>
"""

SCRIPT = r"""<div id="tip" hidden></div>
<script>
(function(){
  var tipEl=document.getElementById('tip'), lastXh=null;
  function hide(){tipEl.hidden=true; if(lastXh){lastXh.style.opacity=0; lastXh=null}}
  function show(e,el){
    var d; try{d=JSON.parse(el.dataset.tip)}catch(err){return}
    tipEl.replaceChildren();
    var h=document.createElement('div'); h.className='th'; h.textContent=d.h; tipEl.append(h);
    d.r.forEach(function(r){
      var row=document.createElement('div'); row.className='tr';
      if(r[2]){var k=document.createElement('i'); k.style.background='var('+r[2]+')'; row.append(k)}
      var b=document.createElement('b'); b.textContent=r[1]; row.append(b);
      if(r[0]){var s=document.createElement('span'); s.textContent=r[0]; row.append(s)}
      tipEl.append(row);
    });
    tipEl.hidden=false;
    var w=tipEl.offsetWidth, hh=tipEl.offsetHeight, x=e.clientX+14, y=e.clientY+14;
    if(x+w>window.innerWidth-8) x=e.clientX-w-14;
    if(y+hh>window.innerHeight-8) y=e.clientY-hh-14;
    tipEl.style.left=Math.max(8,x)+'px'; tipEl.style.top=Math.max(8,y)+'px';
    if(lastXh){lastXh.style.opacity=0; lastXh=null}
    if(el.dataset.cx && el.ownerSVGElement){
      var xh=el.ownerSVGElement.querySelector('.xh');
      if(xh){xh.setAttribute('x1',el.dataset.cx); xh.setAttribute('x2',el.dataset.cx); xh.style.opacity=1; lastXh=xh}
    }
  }
  function handle(e){
    var el=e.target.closest && e.target.closest('[data-tip]');
    if(el) show(e,el); else hide();
  }
  document.addEventListener('pointermove',handle);
  document.addEventListener('pointerdown',handle);
  document.addEventListener('scroll',hide,{passive:true});
})();
</script>
"""

BODY = r"""
<main>
<p class="eyebrow">NASA Space Apps 2026 · MODIS and VIIRS Hot Spots · Stand 13.11.2026</p>
<h1>Wie wir MODIS und VIIRS harmonisieren</h1>
<p class="lede">Analyse der FIRMS-Hotspots für Iberien (11/2000 bis 11/2026, {{n_iberia}} Erkennungen) mit einer weltweiten Gegenprobe. Der Bericht begründet den Harmonisierungsweg. Die Pipeline selbst ist noch nicht gebaut.</p>

<div class="answer">
<p class="big">Empfehlung: VIIRS (SNPP) ist ab 2012 die Referenz. MODIS verlängert die Reihe nur nach hinten bis 2001 und wird dafür mit einem festen Faktor je Region auf VIIRS-Niveau gebracht.</p>
<p>Verglichen und vorhergesagt wird auf NUTS-2 pro Monat, nicht auf dem 0,25°-Raster. Gezählt werden nur Vegetationsfeuer (<code>type</code> = 0). Die Helligkeit (<code>brightness</code>) wird nicht umgerechnet, weil sie zwischen den Sensoren nicht vergleichbar ist. Aufwendigere Modelle als der Regionsfaktor haben in der Prüfung keinen Vorteil gebracht.</p>
</div>

<div class="tiles">
<div class="tile"><b>{{n_ratio}} ×</b><span>so viele Erkennungen meldet SNPP wie Aqua im selben Gebiet und Zeitraum</span></div>
<div class="tile"><b>{{frp_ratio}} ×</b><span>Verhältnis der FRP-Summen SNPP zu Aqua: die Strahlungsleistung ist fast gleich</span></div>
<div class="tile"><b>{{seen}}</b><span>der VIIRS-Feuercluster sieht Aqua. Sie enthalten {{seen_frp}} der Strahlungsleistung</span></div>
<div class="tile"><b>× {{ag_m}}</b><span>typischer Fehler der Umrechnung je Region und Monat. Je Region und Jahr: × {{ag_y}}</span></div>
</div>

<nav class="toc" aria-label="Inhalt"><ol>
<li><a href="#befunde">Die sechs Befunde</a></li>
<li><a href="#daten">Daten und Vorgehen</a></li>
<li><a href="#spalten">Spaltenvergleich</a></li>
<li><a href="#intern">Zusammenhänge innerhalb eines Sensors</a></li>
<li><a href="#paar">Was die Sensoren verbindet</a></li>
<li><a href="#faktor">Wovon der Faktor abhängt</a></li>
<li><a href="#skala">Skala und Kenngröße</a></li>
<li><a href="#wege">Harmonisierungswege im Test</a></li>
<li><a href="#probe">Probe: die durchgehende Reihe</a></li>
<li><a href="#global">Weltweite Gegenprobe</a></li>
<li><a href="#empfehlung">Empfohlener Weg, Schritt für Schritt</a></li>
<li><a href="#entscheidungen">Die zwölf offenen Entscheidungen</a></li>
<li><a href="#grenzen">Grenzen</a></li>
<li><a href="#nachrechnen">Nachrechnen</a></li>
</ol></nav>

<h2 id="befunde">Die sechs Befunde</h2>
<ul class="findings">
<li><strong>1. Die Sensoren unterscheiden sich vor allem darin, welche Feuer sie überhaupt sehen.</strong>
Aqua erkennt ein VIIRS-Feuercluster erst ab etwa {{frp50_D}} MW (tags) bzw. {{frp50_N}} MW (nachts) mit 50 % Wahrscheinlichkeit. {{unseen_det}} aller VIIRS-Erkennungen liegen in Clustern, die Aqua gar nicht meldet. Diese Feuer fehlen in MODIS vollständig und lassen sich nicht pro Pixel zurückrechnen.</li>
<li><strong>2. Einen festen Zählfaktor gibt es nicht, eine fast feste FRP-Summe schon.</strong>
SNPP meldet tags {{ratio_t0_D}}-mal und nachts {{ratio_t0_N}}-mal so viele Erkennungen wie Aqua. Je Region liegt der Faktor zwischen {{reg_lo}} und {{reg_hi}}, je Kalendermonat nachts zwischen {{mon_N_lo}} und {{mon_N_hi}}. Die FRP-Summe unterscheidet sich in Iberien dagegen nur um den Faktor {{frp_ratio}}.</li>
<li><strong>3. Auf dem 0,25°-Raster stimmen die Sensoren nicht überein.</strong>
Je Zelle und Monat erklärt MODIS nur {{r2_025_m}} der VIIRS-Streuung (R² auf Log-Skala). In {{only_snpp_025_m}} der aktiven Zell-Monate meldet nur SNPP. Auf NUTS-2 pro Monat sind es {{r2_nuts_m}}, pro Jahr {{r2_nuts_y}}.</li>
<li><strong>4. Der einfache Weg ist so gut wie jeder aufwendige.</strong>
Von {{n_cand}} getesteten Umrechnungen trifft keine die VIIRS-Klasse öfter als der Faktor je Region ({{M3_acc}}). Alle landen bei einem typischen Fehler um × 1,5 je Region und Monat. Schon zwei baugleiche VIIRS-Instrumente weichen in Iberien um × {{vv_ib}} voneinander ab (1°-Zelle pro Monat, MODIS dort × {{mv_ib}}). Ein großer Teil des Fehlers ist also Rauschen, das keine Formel entfernt.</li>
<li><strong>5. Statische Wärmequellen müssen vorher raus.</strong>
{{static_snpp_N}} der nächtlichen SNPP-Erkennungen sind Industrie und andere Dauerquellen, bei Aqua {{static_aqua}}. Im NRT fehlt die Spalte <code>type</code>. Eine Ortsmaske aus dem Archiv fängt dort {{mask_recall}} dieser Quellen ab und entfernt nur {{mask_false}} der echten Feuer.</li>
<li><strong>6. Terra und Aqua verlassen seit 2022 ihre Umlaufzeit.</strong>
Aqua überfliegt Iberien 2026 im Mittel um {{aqua_2026}} Uhr Ortszeit statt um {{aqua_2012}} Uhr, Terra um {{terra_2026}} statt {{terra_2012}} Uhr. SNPP bleibt bei etwa 13 Uhr. Kalibriert wird deshalb nur mit 2012 bis 2021. Weil ab 2012 ohnehin VIIRS verwendet wird, berührt die Drift die fertige Reihe nicht.</li>
</ul>

<h2 id="daten">Daten und Vorgehen</h2>
<p>Grundlage sind die FIRMS-Downloads im Ordner <code>Daten_Satellit</code>. Für Iberien liegen MODIS (Terra ab 11/2000, Aqua ab 07/2002) und VIIRS SNPP (ab 01/2012) als Archiv und NRT vor. Zusätzlich gibt es weltweite Daten aller fünf Satelliten für ein Jahr (17.10.2025 bis 17.10.2026).</p>
<div class="scroll"><table class="wide">
<thead><tr><th>Datensatz</th><th>Inhalt</th><th>Zeilen</th><th>Verwendung</th></tr></thead>
<tbody>
<tr><td>Iberien MODIS<br><code>DL_FIRE_M-C61_845369</code></td><td>Terra + Aqua, Archiv 11/2000–08/2026, NRT bis 11/2026</td><td>202.167</td><td>Hauptanalyse</td></tr>
<tr><td>Iberien VIIRS<br><code>DL_FIRE_SV-C2_845370</code></td><td>SNPP, Archiv 01/2012–07/2026, NRT bis 11/2026</td><td>371.295</td><td>Hauptanalyse, Referenz</td></tr>
<tr><td>Welt, vier Ordner<br><code>…_835017/18/19/29</code></td><td>Terra, Aqua, SNPP, NOAA-20, NOAA-21, ein Jahr</td><td>57 Mio.</td><td>Gegenprobe: Übertragbarkeit und Rauschgrenze</td></tr>
<tr><td>NUTS-2-Grenzen<br><code>geo/NUTS_RG_10M_2021…</code></td><td>Eurostat GISCO, NUTS 2021, 1:10 Mio.</td><td>334 Regionen</td><td>Zuordnung <code>region_id</code>, lokal ohne API</td></tr>
</tbody></table></div>
<p>Die Regionszuordnung läuft lokal als Punkt-in-Polygon-Test. {{n_near}} Küstenpunkte, die knapp neben einer vereinfachten Grenze liegen, bekommen die nächste Region innerhalb von 0,05°. Nur {{n_null}} Erkennungen bleiben ohne Region. Der Download enthält Spanien, Portugal und drei Regionen Südwestfrankreichs.</p>
<p>Wenn nichts anderes dasteht, gelten diese Festlegungen: nur Archivdaten, nur <code>type</code> = 0, Überlappungszeitraum 02/2012 bis 07/2026, als stabiler Kalibrierzeitraum 02/2012 bis 12/2021. Paarvergleiche laufen zwischen Aqua und SNPP, weil beide bis 2021 zur selben Ortszeit messen.</p>

<h2 id="spalten">Spaltenvergleich</h2>
<p>Beide Downloads haben dieselben 15 Spaltennamen (im NRT 14, ohne <code>type</code>). Gleiche Namen bedeuten aber nicht gleiche Größen. Die Tabelle zeigt, was jede Spalte je Sensor enthält und welche Rolle sie für die Harmonisierung spielt.</p>
<div class="scroll"><table class="wide">
<thead><tr><th>Spalte</th><th>MODIS (Terra, Aqua)</th><th>VIIRS (SNPP)</th><th>Direkt vergleichbar?</th><th>Rolle in der Harmonisierung</th></tr></thead>
<tbody>
<tr><td><code>latitude</code>, <code>longitude</code></td><td>Mitte eines 1-km-Pixels</td><td>Mitte eines 375-m-Pixels</td><td>Ja, ab etwa 0,05° Zellgröße. Zusammengehörige Erkennungen liegen im Median {{dist50}} km auseinander, 90 % unter {{dist90}} km.</td><td>Schlüssel: Zuordnung zur Region</td></tr>
<tr><td><code>acq_date</code>, <code>acq_time</code></td><td colspan="2">UTC. Lokale Sonnenzeit = UTC-Stunde + Länge / 15</td><td>Ja. In Iberien fällt kein Überflug über die UTC-Datumsgrenze.</td><td>Schlüssel: Monat. Daraus folgt auch die Bahndrift.</td></tr>
<tr><td><code>daynight</code></td><td colspan="2">D oder N</td><td>Ja</td><td>Wichtigster Störfaktor: Zählfaktor tags {{ratio_t0_D}}, nachts {{ratio_t0_N}}</td></tr>
<tr><td><code>satellite</code></td><td>Terra, Aqua</td><td>SNPP (weltweit auch N20, N21)</td><td>–</td><td>Bestimmt die Überflugzeit. Daraus die Spalte <code>sensor</code> ableiten.</td></tr>
<tr><td><code>instrument</code></td><td>MODIS</td><td>„SNPP“ in den SNPP-Dateien, „VIIRS“ bei NOAA-20/21</td><td>Nein, uneinheitlich befüllt</td><td>Nicht verwenden</td></tr>
<tr><td><code>brightness</code></td><td>Kanal 21/22 bei 4 µm, 300 bis 509 K</td><td>Kanal I-4 bei 3,7 µm, endet bei 367 K. {{sat367_D}} der Tag-Erkennungen stehen genau auf diesem Höchstwert, einzelne Fehlwerte bei 208 K.</td><td>Nein</td><td>Nicht umrechnen. Als Merkmal nur zusammen mit <code>sensor</code>.</td></tr>
<tr><td><code>bright_t31</code></td><td>Kanal 31 bei 11 µm</td><td>Kanal I-5 bei 11 µm</td><td>Bedingt. Die Verteilungen ähneln sich (Median tags 300 K).</td><td>Nur für Plausibilitätsprüfungen</td></tr>
<tr><td><code>frp</code></td><td>MW je Pixel, Median 24 MW (Aqua, Tag)</td><td>MW je Pixel, Median 7,7 MW (Tag)</td><td>Je Pixel nein, als Summe über ein Feuer oder eine Region ja</td><td>Zweite Zielgröße und Kontrolle</td></tr>
<tr><td><code>scan</code>, <code>track</code></td><td>Pixelgröße 1,0–4,8 km × 1,0–2,0 km</td><td>0,32–0,80 km × 0,36–0,78 km</td><td>Ja (Kilometer)</td><td>Erklärt die Erkennungsschwelle. Für die Umrechnung selbst nicht nötig.</td></tr>
<tr><td><code>confidence</code></td><td>Zahl 0–100, steigt mit der Helligkeit</td><td>l / n / h. „h“ bedeutet: Pixel gesättigt (alle h-Zeilen haben 367 K). „l“ gibt es nur tags. Nachts sind {{conf_n_share_N}} „n“.</td><td>Nein</td><td>Nicht filtern. Der Filter ändert das Ergebnis nicht messbar.</td></tr>
<tr><td><code>type</code></td><td colspan="2">0 Vegetationsfeuer, 2 statische Landquelle, 3 Offshore. Fehlt im NRT.</td><td>Ja</td><td>Pflichtfilter. Im NRT durch eine Ortsmaske ersetzen.</td></tr>
<tr><td><code>version</code></td><td>6.03 (bis 2022), 61.03 (ab 2023), 6.1NRT</td><td>2, 2.0NRT</td><td>–</td><td>Nur Herkunft. Daraus <code>source</code> = archive / nrt.</td></tr>
</tbody></table></div>
<h3>Wertebereiche</h3>
<p>Je Zelle: 5-%-Quantil / Median / 95-%-Quantil im Archiv.</p>
[[T:ranges]]

<h2 id="intern">Zusammenhänge innerhalb eines Sensors</h2>
<p>Mehrere Spalten hängen fest zusammen. Wer diese Verknüpfungen kennt, weiß, welche Spalten eigene Information tragen und welche nur eine andere wiederholen.</p>
<div class="scroll"><table class="wide">
<thead><tr><th>Verknüpfung</th><th>Funktion</th><th>Güte in den Daten</th><th>Folge</th></tr></thead>
<tbody>
<tr><td>Überflugzeit</td><td>Ortszeit = <code>acq_time</code> (UTC) + <code>longitude</code> / 15</td><td>exakt</td><td>Macht Satelliten vergleichbar und die Drift sichtbar</td></tr>
<tr><td>Pixelgeometrie</td><td><code>track</code> wächst mit <code>scan</code>, beide folgen dem Blickwinkel. Pixelfläche = <code>scan</code> × <code>track</code></td><td>MODIS: 1,0 → 2,0 km bei scan 1,0 → 4,8 km</td><td>Eine Größe (Fläche) genügt</td></tr>
<tr><td>Erkennungsschwelle</td><td>schwächste erkennbare FRP ≈ Konstante × Pixelfläche</td><td>MODIS: {{thr_aqua_lo}} MW bei 1 km², {{thr_aqua_hi}} MW bei {{thr_aqua_area_hi}} km². VIIRS: {{thr_snpp_lo}} bis {{thr_snpp_hi}} MW (tags), ab {{thr_snpp_N_lo}} MW (nachts)</td><td>Erklärt, warum MODIS kleine Feuer verpasst, am Bildrand besonders</td></tr>
<tr><td>FRP bei MODIS</td><td>FRP ∝ Fläche × (<code>brightness</code>⁸ − <code>bright_t31</code>⁸)</td><td>R² {{phys_modis_lo}} bis {{phys_modis_hi}}</td><td><code>brightness</code> trägt bei MODIS keine Information über die FRP hinaus</td></tr>
<tr><td>FRP bei VIIRS</td><td>dieselbe Formel</td><td>R² nur {{phys_viirs_D}} (Tag) und {{phys_viirs_N}} (Nacht)</td><td>Laut Produktbeschreibung stammt die VIIRS-FRP aus einem anderen Kanal (M13), und I-4 sättigt. <code>brightness</code> sagt bei starken Feuern nichts aus.</td></tr>
<tr><td>Konfidenz bei MODIS</td><td>steigt mit <code>brightness</code></td><td>Median 48 bei 300 K, 100 ab 360 K (Tag)</td><td>Konfidenz ist im Kern ein Helligkeitsmaß</td></tr>
<tr><td>Konfidenz bei VIIRS</td><td>„h“ genau dann, wenn <code>brightness</code> = 367 K</td><td>100 % der h-Zeilen</td><td>„h“ ist kein Gütesiegel und mit MODIS-„hoch“ nicht vergleichbar</td></tr>
</tbody></table></div>
[[F:threshold]]
<p>Die Grafik zeigt den Kern des Sensorunterschieds. Ein MODIS-Pixel in der Bildmitte braucht mindestens rund 4 MW, am Bildrand rund 30 MW. VIIRS kommt tags mit 2 bis 4 MW aus und nachts mit 0,5 bis 1 MW. {{multi_snpp_D}} der Tag- und {{multi_snpp_N}} der Nacht-Erkennungen von SNPP stammen außerdem von Orten, die am selben Tag von zwei Überflügen erfasst wurden, weil sich die breiten VIIRS-Bildstreifen auf dieser Breite überlappen. Bei Aqua sind es {{multi_aqua_D}} und {{multi_aqua_N}}.</p>

<h2 id="paar">Was die Sensoren verbindet</h2>
<p>Für den direkten Vergleich wurden Aqua und SNPP am selben Datum und in derselben Tageshälfte gepaart. Die Überflüge liegen im Median {{dt50}} Stunden auseinander (5 % bis 95 %: {{dt05}} bis {{dt95}} Stunden).</p>
<h3>Räumliche Übereinstimmung</h3>
[[T:confirm]]
<p>Nachts bestätigt SNPP fast jede Aqua-Erkennung im Umkreis von 3 km ({{aq_r3_N}}). Tags sind es {{aq_r3_D}}: kurze Feuer können zwischen den beiden Überflügen beginnen oder enden. Umgekehrt findet nur etwa die Hälfte der SNPP-Erkennungen einen Aqua-Partner. Die Lagegenauigkeit ist kein Hindernis, eine Zelle von 0,05° genügt für die Zuordnung.</p>
<h3>Die Erkennungskurve: von welcher Stärke an sieht MODIS ein Feuer?</h3>
[[F:detect]]
<p>Das ist die eigentliche Verknüpfungsfunktion zwischen den Sensoren:</p>
<p class="formula">P(Aqua erkennt) = 1 / (1 + exp(−(a + b · log₁₀ FRP)))  ·  Tag: a = {{a_D}}, b = {{b_D}}  ·  Nacht: a = {{a_N}}, b = {{b_N}}</p>
<p>50 % Erkennung werden tags bei {{frp50_D}} MW erreicht, 90 % erst bei {{frp90_D}} MW. Nachts liegen die Werte bei {{frp50_N}} und {{frp90_N}} MW. Die Tabelle zeigt, wie viele Cluster das betrifft.</p>
[[T:sizes]]
<p>Tags haben rund 64 % der VIIRS-Cluster weniger als 10 MW und werden von Aqua fast nie gesehen. Sie tragen aber nur etwa 5 % der Strahlungsleistung. Darum unterscheiden sich die Anzahlen stark und die FRP-Summen kaum.</p>
<h3>Feuer, die beide sehen</h3>
[[F:cofrp]]
<p>Bei gemeinsam gesehenen Clustern liegt die FRP von SNPP tags im Median beim {{co_frp_D}}-Fachen von Aqua, nachts beim {{co_frp_N}}-Fachen. Die Steigung auf der Log-Skala ist {{co_slope}}: bei schwachen Feuern misst VIIRS etwas mehr, bei sehr starken etwas weniger. Je Aqua-Pixel meldet SNPP tags {{co_n_D}} und nachts {{co_n_N}} Pixel (Median).</p>
<p>Der Zählfaktor von {{n_ratio}} setzt sich also aus drei Teilen zusammen: Feuer, die MODIS gar nicht sieht ({{unseen_det}} der VIIRS-Erkennungen), mehr Pixel je gemeinsam gesehenem Feuer, und doppelte Überflüge.</p>

<h2 id="faktor">Wovon der Faktor abhängt</h2>
<h3>Tageszeit und Jahreszeit</h3>
[[F:month]]
<p>Tags liegt der Zählfaktor je Kalendermonat zwischen {{mon_D_lo}} und {{mon_D_hi}}, nachts zwischen {{mon_N_lo}} und {{mon_N_hi}}. Im Winter brennen vor allem kleine, kühle Feuer, die nur VIIRS nachts noch erkennt.</p>
<h3>Region</h3>
[[F:region]]
<p>Zwischen den Regionen schwankt der Faktor von {{reg_lo}} bis {{reg_hi}}. Er ist dort hoch, wo kleine Feuer überwiegen: die Rangkorrelation mit dem Anteil der Cluster unter 10 MW beträgt {{reg_rho}}. Im Norden Portugals und in Aquitanien mit ihren großen Waldbränden ist er am niedrigsten, in Madrid und Katalonien am höchsten.</p>
<h3>Statische Wärmequellen</h3>
[[T:static]]
<p>Ohne den Filter läge der nächtliche Zählfaktor bei {{ratio_unf_N}} statt {{ratio_t0_N}}. VIIRS erkennt mit seinen kleinen Pixeln Fabriken und Fackeln, die MODIS meist entgehen. Diese Quellen brennen das ganze Jahr und würden jede Feuerstatistik verzerren.</p>
<p>Für das NRT ohne <code>type</code> wurde eine Ortsmaske geprüft: alle Zellen von {{mask_grid}}° (etwa 500 m), in denen bis 2022 mindestens {{mask_kmin}} statische Erkennungen lagen und diese die Mehrheit stellten, plus die acht Nachbarzellen. Das sind {{mask_cells}} Kernzellen. Angewendet auf 2023 bis 2026 trifft die Maske {{mask_recall}} der statischen SNPP-Erkennungen und entfernt {{mask_false}} der echten Feuer. Bei MODIS trifft dieselbe Maske wegen der größeren Pixel nur {{mask_recall_modis}}. Im vorliegenden SNPP-NRT (08 bis 11/2026) würde sie {{nrt_removed_N}} der Nacht-Erkennungen entfernen. Im Archiv waren in den Monaten August bis Oktober 2020 bis 2025 {{arch_static_N}} der Nacht-Erkennungen statisch.</p>
<h3>Bahndrift</h3>
[[F:drift]]
<p>Seit 2022 werden Terra und Aqua nicht mehr auf ihrer Umlaufzeit gehalten. Aqua misst jetzt später am Nachmittag, wenn Feuer am stärksten brennen, Terra früher am Morgen. Die Folgen in den Daten:</p>
<ul>
<li>FRP-Verhältnis SNPP zu Aqua (Tag): {{frpD_st_lo}} bis {{frpD_st_hi}} in den Jahren 2012 bis 2021, danach {{frpD_dr_lo}} bis {{frpD_dr_hi}}. Aqua sieht jetzt mehr Strahlungsleistung als SNPP.</li>
<li>Zählfaktor SNPP zu Terra (Tag): {{terraD_st_lo}} bis {{terraD_st_hi}} bis 2021, dann {{terraD_2025}} (2025) und {{terraD_2026}} (2026). Terra sieht morgens immer weniger.</li>
<li>Summe aus Aqua und Terra: Der Zählfaktor bleibt mit {{mod_dr_lo}} bis {{mod_dr_hi}} nahe am alten Band von {{mod_st_lo}} bis {{mod_st_hi}}, weil sich beide Effekte teilweise aufheben.</li>
</ul>
[[F:year]]
<p>2023 wechselt außerdem die MODIS-Version von 6.03 auf 61.03. Beides fällt zeitlich zusammen und lässt sich in diesen Daten nicht trennen. Für den empfohlenen Weg ist das unerheblich, weil MODIS nach 2011 nicht mehr in die Reihe eingeht.</p>
<h3>Terra gegen Aqua</h3>
<p>Terra meldet tags das {{ta_D_lo}}- bis {{ta_D_hi}}-Fache von Aqua und nachts das {{ta_N_lo}}- bis {{ta_N_hi}}-Fache (2003 bis 2021). In der Summe über Tag und Nacht sind beide fast gleich ({{ta_all}}). Als Eingang für die Umrechnung ist die Summe aus beiden besser als jeder allein: R² {{pred_both}} gegenüber {{pred_aqua}} (nur Aqua) und {{pred_terra}} (nur Terra).</p>

<h2 id="skala">Skala und Kenngröße</h2>
<h3>Auf welcher Raum- und Zeitskala stimmen Aqua und SNPP überein?</h3>
<p>R² der Anzahlen auf Log-Skala, 2012 bis 2021. Dunkler bedeutet bessere Übereinstimmung.</p>
[[T:scales]]
<p>Das vorgeschlagene 0,25°-Raster ist als Vergleichsebene zu fein. Dort entscheidet der Zufall, ob Aqua ein Feuer sieht. Erst ab NUTS-2 pro Monat wird der Zusammenhang tragfähig. Für Karten kann das feine Raster bleiben, für Kalibrierung und Vorhersage nicht.</p>
<h3>Welche Kenngröße ist am besten vergleichbar?</h3>
<p>NUTS-2 pro Monat, Aqua gegen SNPP, Tag und Nacht zusammen.</p>
[[T:metrics]]
<p>Die Anzahl der Erkennungen hat das stabilste Verhältnis über die Jahre. Die FRP-Summe liegt als einzige nahe bei 1, schwankt aber von Jahr zu Jahr stärker, weil einzelne Großfeuer sie bestimmen. „Tage mit Feuer“ und „aktive Zell-Tage“ schneiden schlechter ab. Die Anzahl ist daher die Hauptgröße, die FRP-Summe die unabhängige Kontrolle.</p>

<h2 id="wege">Harmonisierungswege im Test</h2>
<p>Geprüft wurde, wie gut sich die monatliche SNPP-Anzahl je Region aus den MODIS-Zahlen derselben Region vorhersagen lässt. Jeder Weg wurde außerhalb seiner Trainingsdaten bewertet: Kreuzvalidierung mit je einem ausgelassenen Jahr über 2012 bis 2021 ({{n_rm}} Region-Monate in {{n_regions}} Regionen), dazu ein Test auf den Driftjahren 2022 bis 2026.</p>
<ul>
<li><strong>Typischer Fehler:</strong> Median des Faktors zwischen Vorhersage und Messung. × 1,5 heißt: die Hälfte der Monate liegt näher als Faktor 1,5 am wahren Wert.</li>
<li><strong>Klasse getroffen:</strong> Anteil der Monate, in denen die umgerechnete Reihe dieselbe Klasse (unter, normal, über) ergibt wie VIIRS. Die Schwellen sind die Terzile der VIIRS-Werte je Region und Kalendermonat. Zufall wäre 33 %.</li>
</ul>
[[T:cand]]
<p>Drei Dinge fallen auf.</p>
<ul>
<li>Ohne Umrechnung (M0) geht es nicht: Summe und Klassen sind falsch.</li>
<li>Der Faktor je Region (M3) trifft die Klassen am besten und hat einen der kleinsten Fehler. Der im bisherigen Skript <code>fire_forecast.py</code> vorgesehene Faktor je Kalendermonat (M2) bringt gegenüber einem einzigen Faktor (M1) nichts.</li>
<li>Die Poisson-Modelle (M7 bis M10) und das Gradient Boosting (M12) treffen die Klassen schlechter, obwohl M12 den kleinsten mittleren Fehler hat. Der Grund liegt in den Monaten ohne jede MODIS-Erkennung ({{zero_share}} der Fälle, im Mittel {{zero_true}} SNPP-Erkennungen). Dort trifft der Regionsfaktor mit seiner Vorhersage 0 die Klasse in {{zero_M3}} der Fälle. M9 sagt im Mittel {{zero_M9_pred}} vorher und trifft nur {{zero_M9}}, M12 trifft {{zero_M12}}. Auch in den übrigen Monaten liegt M12 mit {{nz_M12}} nicht vor dem Regionsfaktor ({{nz_M3}}). Der Zusammenhang ist proportional, mehr Struktur ist in den Daten nicht zu holen.</li>
</ul>
<h3>Der Rang-Weg: gar nicht umrechnen</h3>
<p>Wenn am Ende nur die Klasse zählt, kann man jede Reihe an ihrer eigenen Klimatologie messen und die Klassen vergleichen.</p>
[[T:rank]]
<p>Das liefert {{rank_acc}} und damit praktisch dasselbe wie die Faktoren. Der Grund: Ein fester Faktor je Region ändert die Rangfolge innerhalb der MODIS-Reihe nicht. Der Faktor wird trotzdem gebraucht, sobald MODIS-Jahre und VIIRS-Jahre in einer Reihe stehen und gemeinsame Schwellen bekommen sollen. Die letzte Zeile zeigt die Obergrenze: Selbst VIIRS-FRP und VIIRS-Anzahl desselben Sensors ergeben nur in {{rank_ref}} der Monate dieselbe Klasse. Mit nur zwei Klassen (über oder unter dem Median) stimmen MODIS und VIIRS in {{median_acc}} der Monate überein.</p>
<h3>Wirkung der Filter</h3>
[[T:filters]]
<p>Der <code>type</code>-Filter verbessert die Übereinstimmung (R² {{f_none_r2}} → {{f_t0_r2}}). Der Ausschluss niedriger Konfidenz ändert nichts. Der Filter auf hohe Konfidenz vergleicht bei VIIRS nur gesättigte Pixel und ist kein fairer Vergleich. Nacht-Erkennungen allein sind mit × {{f_night_fe}} deutlich unsicherer als Tag-Erkennungen (× {{f_day_fe}}).</p>
<h3>Wirkung der Aggregation</h3>
[[F:agg]]
<p>Wer gröber zusammenfasst, bekommt eine deutlich verlässlichere Reihe: je Quartal × {{ag_q}}, je Jahr × {{ag_y}}, je Land und Monat × {{ag_cm}}.</p>

<h2 id="probe">Probe: die durchgehende Reihe</h2>
[[F:series]]
<p>Die Faktoren wurden nur aus 2012 bis 2021 bestimmt. Trotzdem trifft die umgerechnete MODIS-Reihe die VIIRS-Jahreswerte 2013 bis 2025 im Median auf × {{oc_med}} genau, im schlechtesten Jahr auf × {{oc_max}} (Korrelation {{oc_r}}).</p>
<p>Hängt man MODIS roh und VIIRS ohne Umrechnung aneinander, steigt das Mittel ab 2012 scheinbar auf das {{jump_naive}}-Fache. Das wäre der falsche Trend, vor dem die Aufgabenstellung warnt. In der harmonisierten Reihe liegt das Mittel 2012 bis 2025 beim {{jump_harm}}-Fachen von 2003 bis 2011. MODIS allein zeigt über denselben Vergleich {{jump_modis}}. Die harmonisierte Reihe gibt also den Verlauf wieder, den auch der durchgehend messende Sensor zeigt.</p>
<p>Die längere Reihe verändert die Klassenschwellen spürbar: In {{med_shift}} der Region-Monate mit nennenswerter Aktivität verschiebt sich der Median um mehr als 25 %, wenn 2003 bis 2011 dazukommt. Die Jahre vor 2012 waren im Mittel feuerreicher.</p>

<h2 id="global">Weltweite Gegenprobe</h2>
<p>Die weltweiten Daten eines Jahres beantworten zwei Fragen: Wie groß ist das unvermeidbare Rauschen, und gelten die Iberien-Faktoren anderswo? Vergleichsebene ist hier die 1°-Zelle pro Monat, jeweils mit einem einzigen Faktor.</p>
[[T:pairs]]
<p>Zwei baugleiche VIIRS-Instrumente, die zur selben Ortszeit messen, weichen weltweit um × {{vv_glob}} voneinander ab und in der Iberien-Box um × {{vv_ib}}. MODIS gegen VIIRS liegt bei × {{mv_glob}} bzw. × {{mv_ib}}. Von dem Fehler der Umrechnung ist also ein großer Teil Stichprobenrauschen (Wolken, Bildrand, Überflugminute), das keine Kalibrierung beseitigt.</p>
<p>NOAA-20 und NOAA-21 liegen weltweit im Mittel innerhalb von {{n20_dev}} bei SNPP, in einzelnen Großregionen weichen sie bis {{n20_reg_max}} ab. Gegenüber dem MODIS-Unterschied ist das klein, eine eigene Harmonisierung brauchen sie zunächst nicht. Man darf sie aber nicht addieren, sonst verdreifacht sich die Zahl.</p>
[[T:macro]]
<p>Die Faktoren sind nicht übertragbar. Über {{n_tiles}} Kacheln von 5° liegt der Zählfaktor SNPP zu Aqua zwischen {{tile_n_lo}} und {{tile_n_hi}} (5 % bis 95 %). Auch das FRP-Verhältnis, das in Iberien nahe 1 liegt, beträgt weltweit im Median {{tile_frp_med}} und reicht von {{tile_frp_lo}} bis {{tile_frp_hi}}. Für Argentinien oder jede andere Region müsste die Kalibrierung mit den dortigen Daten wiederholt werden. In diesem Jahr misst Aqua wegen der Drift bereits um {{g_aqua_lst}} Uhr Ortszeit, SNPP um {{g_snpp_lst}} Uhr und Terra um {{g_terra_lst}} Uhr.</p>

<h2 id="empfehlung">Empfohlener Weg, Schritt für Schritt</h2>
<ol class="steps">
<li><div><strong>Einlesen und vereinheitlichen</strong>Alle CSVs in ein Schema. Neue Spalten: <code>sensor</code> (aus <code>satellite</code>), <code>source</code> (archive / nrt). <code>brightness</code> bleibt eine Spalte, wird aber nie ohne <code>sensor</code> verwendet.</div></li>
<li><div><strong>Statische Quellen entfernen</strong>Archiv: <code>type</code> = 0. NRT: Ortsmaske aus dem Archiv ({{mask_grid}}°-Zellen mit mindestens {{mask_kmin}} statischen Erkennungen und statischer Mehrheit, plus Nachbarzellen). Kein Konfidenzfilter.</div></li>
<li><div><strong>Region zuordnen</strong><code>region_id</code> per Punkt-in-Polygon gegen NUTS-2 (2021), lokal. <code>country</code> = die ersten zwei Zeichen von <code>region_id</code>.</div></li>
<li><div><strong>Aggregieren</strong>Je Region, Monat, Satellit und Tageshälfte: Anzahl und FRP-Summe. Monate ohne Erkennung zählen als 0 und müssen als Zeile vorhanden sein.</div></li>
<li><div><strong>Faktoren bestimmen</strong>Je Region: k = Summe SNPP / Summe (Aqua + Terra) über 02/2012 bis 12/2021. Regionen mit weniger als 300 MODIS-Erkennungen bekommen den Gesamtfaktor {{k_modis}}. Für die Zeit vor 07/2002 ein eigener Faktor nur für Terra (gesamt {{k_terra}}).</div></li>
<li><div><strong>Reihe zusammensetzen</strong>Bis 12/2011: MODIS × k. Ab 01/2012: SNPP gemessen. Eine Spalte <code>basis</code> hält fest, welcher Abschnitt umgerechnet ist. Die Sensoren werden nie addiert.</div></li>
<li><div><strong>Zielklasse bilden</strong>Schwellen je Region und Kalendermonat aus der harmonisierten Reihe. Die Klasse des Monats ergibt sich aus dem Vergleich mit diesen Schwellen.</div></li>
<li><div><strong>Kontrollieren</strong>Jahreswerte MODIS × k gegen SNPP im Überlappungszeitraum (Soll: innerhalb × 1,25). FRP-Summe von Aqua als zweite, unabhängige Sicht auf dieselben Monate.</div></li>
</ol>
<h3>Die Faktoren</h3>
<p>Aus 02/2012 bis 12/2021, nur <code>type</code> = 0. Regionen mit zu wenig Daten zeigen den Gesamtfaktor.</p>
[[T:kreg]]
<h3>Was wir bewusst nicht tun</h3>
<ul>
<li><strong><code>brightness</code> umrechnen.</strong> Der VIIRS-Kanal sättigt bei 367 K, eine Umrechnung wäre für starke Feuer falsch.</li>
<li><strong>Einzelne Pixel kalibrieren.</strong> Was MODIS nicht sieht, lässt sich nicht aus dem Pixel daneben ableiten. Kalibriert wird nur die aggregierte Zahl.</li>
<li><strong>Auf 0,25° vergleichen.</strong> Dort ist die Übereinstimmung zu schwach.</li>
<li><strong>Faktoren je Monat oder Tag/Nacht.</strong> Im Test ohne Gewinn, dafür mehr Parameter und mehr Rauschen.</li>
<li><strong>MODIS nach 2011 einrechnen.</strong> Damit wäre die Reihe von der Bahndrift abhängig.</li>
</ul>

<h2 id="entscheidungen">Die zwölf offenen Entscheidungen</h2>
<div class="scroll"><table class="wide">
<thead><tr><th>#</th><th>Frage</th><th>Empfehlung aus der Analyse</th><th>Beleg</th></tr></thead>
<tbody>
<tr><td>1</td><td>Zielschema</td><td>Die 15 Originalspalten plus <code>sensor</code>, <code>source</code>, <code>region_id</code>, <code>country</code>. <code>instrument</code> und <code>version</code> können entfallen.</td><td>Spaltenvergleich</td></tr>
<tr><td>2</td><td>Helligkeitskanäle</td><td>Eine Spalte <code>brightness</code> plus <code>sensor</code>. Keine Umrechnung, kein sensorübergreifendes Merkmal.</td><td>Sättigung bei 367 K in {{sat367_D}} der Tag-Erkennungen</td></tr>
<tr><td>3</td><td>Konfidenz</td><td>Nicht filtern. Die Klasse nur zur Information mitführen.</td><td>Filtertabelle: kein Unterschied</td></tr>
<tr><td>4</td><td>Räumliche Auflösung</td><td>NUTS-2 für Kalibrierung und Vorhersage. 0,25° höchstens für Karten.</td><td>R² {{r2_025_m}} gegen {{r2_nuts_m}}</td></tr>
<tr><td>5</td><td>Zeit und Zeitzone</td><td>Monat, UTC-Datum. Terra-Nacht (abends) und Aqua-Nacht (nach Mitternacht) derselben Nacht tragen verschiedene Daten, auf Monatsebene spielt das keine Rolle. Für Regionen fern des Nullmeridians vorher prüfen, ob Überflüge auf den Folgetag fallen.</td><td>In Iberien kein Datumswechsel</td></tr>
<tr><td>6</td><td>Doppelerkennungen</td><td>Sensoren nie addieren. Je Zeitabschnitt genau eine Quelle.</td><td>Schritt 6</td></tr>
<tr><td>7</td><td>Filter</td><td><code>type</code> = 0 im Archiv, Ortsmaske im NRT.</td><td>{{static_snpp_N}} der SNPP-Nacht-Erkennungen statisch</td></tr>
<tr><td>8</td><td>Zeitraum</td><td>Ab 2001. MODIS bis 2011, VIIRS ab 2012. Die Monate vor 07/2002 sind unsicherer (nur Terra).</td><td>Probe der Reihe</td></tr>
<tr><td>9</td><td>Archiv und NRT</td><td>Mischen ist möglich, mit <code>source</code>-Spalte und Maske. NRT ersetzen, sobald das Archiv den Zeitraum abdeckt.</td><td>Maske trifft {{mask_recall}}</td></tr>
<tr><td>10</td><td>Datenbank</td><td>Für Iberien genügt SQLite. Mit den weltweiten Daten DuckDB und Parquet: 57 Mio. Zeilen sind in 34 Sekunden eingelesen.</td><td><code>00_prepare.py</code></td></tr>
<tr><td>11</td><td>Region</td><td>Iberien wie im Download: {{n_regions}} NUTS-2-Regionen mit genug Daten. Argentinien bräuchte eine eigene Kalibrierung.</td><td>Weltweite Gegenprobe</td></tr>
<tr><td>12</td><td>Vorhersagegröße</td><td>Klasse je NUTS-2 und Monat. Im Team klären: zwei Klassen statt drei oder Quartale statt Monate. Beides macht das Ziel deutlich verlässlicher.</td><td>Drei Klassen {{M3_acc}}, zwei Klassen {{median_acc}}. Fehler je Quartal × {{ag_q}}</td></tr>
</tbody></table></div>

<h2 id="grenzen">Grenzen</h2>
<ul>
<li><strong>Der Fehler je Region und Monat bleibt bei etwa × {{ag_m}}.</strong> In 10 % der Monate liegt die Umrechnung um mehr als Faktor {{M3_p90}} daneben. Das trifft vor allem Monate mit wenigen Feuern.</li>
<li><strong>Vor 2012 gibt es keine Prüfung.</strong> Der Faktor unterstellt, dass das Verhältnis kleiner zu großer Feuer je Region 2001 bis 2011 dasselbe war wie 2012 bis 2021. Hat sich etwa die Praxis landwirtschaftlicher Feuer geändert, stimmt er nicht.</li>
<li><strong>Nur Terra vor 07/2002.</strong> Mit einem Satelliten steigt der typische Fehler auf × {{T1_fe}}.</li>
<li><strong>Die Faktoren gelten nur für Iberien.</strong> Weltweit streuen sie um mehr als das Doppelte.</li>
<li><strong>Nacht-Erkennungen sind unsicher.</strong> Aqua hat in schwachen Jahren nur wenige hundert davon.</li>
<li><strong>Die NRT-Maske ist nicht dicht.</strong> Rund 5 % der statischen SNPP-Erkennungen kommen durch, neue Anlagen kennt sie nicht.</li>
<li><strong>Das Ende von SNPP.</strong> NOAA-20 und NOAA-21 liegen im Mittel innerhalb von {{n20_dev}}, geprüft ist das hier aber nur an einem Jahr.</li>
<li><strong>Driftjahre.</strong> Wendet man die Faktoren doch auf MODIS 2022 bis 2026 an, liegen die Jahressummen zwischen dem {{M3_bias_lo}}- und {{M3_bias_hi}}-Fachen der Messung.</li>
</ul>

<h2 id="nachrechnen">Nachrechnen</h2>
<p>Alle Skripte liegen in <code>Daten_Satellit/data_analysis</code>. Jedes schreibt seine Ergebnisse als JSON nach <code>results/</code>, der Bericht liest nur diese Dateien. Die gesamte Kette läuft in etwa zwei Minuten.</p>
<pre>cd Daten_Satellit/data_analysis
.venv/bin/python 00_prepare.py              # CSV -> Parquet (cache/)
.venv/bin/python 01_nuts.py                 # region_id und country
.venv/bin/python 02_columns.py              # Spalten, Geometrie, Überflugzeit
.venv/bin/python 03_matchup.py              # Paarvergleich Aqua / SNPP
.venv/bin/python 04_scales.py               # Skalen, Kenngrößen, Verhältnisse
.venv/bin/python 05_static.py               # statische Quellen, NRT-Maske
.venv/bin/python 06_strategies.py           # Wege im Vergleich
.venv/bin/python 06b_filters_aggregation.py # Filter und Aggregation
.venv/bin/python 07_global.py               # weltweite Gegenprobe
.venv/bin/python 08_series.py               # durchgehende Reihe
.venv/bin/python build_report.py            # dieser Bericht</pre>
<div class="scroll"><table class="wide">
<thead><tr><th>Skript</th><th>Frage</th><th>Ergebnisdatei</th></tr></thead>
<tbody>
<tr><td><code>02_columns.py</code></td><td>Was steht in den Spalten, und wie hängen sie innerhalb eines Sensors zusammen?</td><td><code>results/columns.json</code></td></tr>
<tr><td><code>03_matchup.py</code></td><td>Welche Feuer sehen beide, und wie verhalten sich Anzahl und FRP?</td><td><code>results/matchup.json</code></td></tr>
<tr><td><code>04_scales.py</code></td><td>Auf welcher Skala und mit welcher Kenngröße stimmen die Sensoren überein?</td><td><code>results/scales.json</code></td></tr>
<tr><td><code>05_static.py</code></td><td>Wie stark stören statische Quellen, und wie ersetzt man <code>type</code> im NRT?</td><td><code>results/static.json</code></td></tr>
<tr><td><code>06_strategies.py</code></td><td>Welche Umrechnung trifft VIIRS außerhalb der Trainingsdaten am besten?</td><td><code>results/strategies.json</code></td></tr>
<tr><td><code>06b_filters_aggregation.py</code></td><td>Was bringen Filter und gröbere Aggregation?</td><td><code>results/filters_aggregation.json</code></td></tr>
<tr><td><code>07_global.py</code></td><td>Wie groß ist das Rauschen, und gelten die Faktoren weltweit?</td><td><code>results/global.json</code></td></tr>
<tr><td><code>08_series.py</code></td><td>Ergibt der empfohlene Weg eine plausible Reihe 2001 bis 2025?</td><td><code>results/series.json</code></td></tr>
</tbody></table></div>
<p class="note">Quellen: FIRMS-Downloads (NASA LANCE / EOSDIS), NUTS-Grenzen von Eurostat GISCO. Zur Einordnung: Schroeder et al. 2014 (VIIRS 375 m Active Fire Product), Li et al. 2020 (MODIS und VIIRS im Vergleich).</p>
</main>
"""


def render(V, F, TB):
    def val(m):
        k = m.group(1)
        if k not in V:
            raise KeyError(f"Platzhalter {k} fehlt")
        return V[k]
    s = re.sub(r"\{\{(\w+)\}\}", val, BODY)
    s = re.sub(r"\[\[F:(\w+)\]\]", lambda m: F[m.group(1)], s)
    s = re.sub(r"\[\[T:(\w+)\]\]", lambda m: TB[m.group(1)], s)
    return s + SCRIPT
