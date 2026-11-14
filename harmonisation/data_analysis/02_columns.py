"""Schritt 2: Spaltenvergleich und Zusammenhaenge INNERHALB eines Sensors.

Fragen:
  a) Wertebereiche je Spalte, Satellit, Tag/Nacht
  b) Was bedeutet `confidence` je Sensor? (MODIS Zahl, VIIRS Klasse)
  c) `type`: Anteil statischer Quellen
  d) Ueberflugzeit (lokale Sonnenzeit) und ihre Drift ueber die Jahre
  e) Scan-Geometrie: track = f(scan), Pixelflaeche, Erkennungsschwelle der FRP
  f) FRP als Funktion von brightness / bright_t31 / Pixelflaeche
  g) Mehrfach-Ueberfluege am selben Tag (ueberlappende Schwaden)
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import IBERIA, con, save

c = con()
c.execute(f"CREATE VIEW ib AS SELECT * FROM '{IBERIA}'")
out = {}

# a) Wertebereiche ---------------------------------------------------------
rows = []
for col in ["brightness", "bright_t31", "frp", "scan", "track"]:
    d = c.execute(f"""SELECT sat, daynight, COUNT(*) n, MIN({col}) mn,
        quantile_cont({col}, [0.05, 0.5, 0.95]) q, MAX({col}) mx
        FROM ib WHERE source='archive' GROUP BY ALL ORDER BY ALL""").df()
    for r in d.itertuples():
        rows.append(dict(col=col, sat=r.sat, dn=r.daynight, n=r.n, min=r.mn,
                         p05=r.q[0], p50=r.q[1], p95=r.q[2], max=r.mx))
out["ranges"] = rows
out["versions"] = c.execute("""SELECT sat, source, version, COUNT(*) n,
    MIN(acq_date)::VARCHAR d0, MAX(acq_date)::VARCHAR d1 FROM ib GROUP BY ALL ORDER BY ALL""").df().to_dict("records")

# b) Konfidenz -------------------------------------------------------------
out["conf_viirs"] = c.execute("""SELECT daynight dn, confidence k, COUNT(*) n,
    median(frp) frp, median(brightness) bright,
    AVG((brightness>=367)::INT) share_saturated, AVG((brightness<250)::INT) share_lt250
    FROM ib WHERE sensor='VIIRS' GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
out["conf_modis"] = c.execute("""SELECT sat, daynight dn,
    CASE WHEN confidence::INT<30 THEN 'l' WHEN confidence::INT<80 THEN 'n' ELSE 'h' END k,
    COUNT(*) n, median(frp) frp, median(brightness) bright
    FROM ib WHERE sensor='MODIS' GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
out["conf_modis_hist"] = c.execute("""SELECT sat, daynight dn, (confidence::INT/5)*5 bin, COUNT(*) n
    FROM ib WHERE sensor='MODIS' GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
# MODIS-Konfidenz als Funktion der Helligkeit (Median je 5-K-Klasse)
out["conf_modis_vs_bright"] = c.execute("""SELECT daynight dn, floor(brightness/5)*5 b,
    median(confidence::INT) conf, COUNT(*) n FROM ib WHERE sensor='MODIS' AND brightness<400
    GROUP BY ALL HAVING COUNT(*)>=30 ORDER BY ALL""").df().to_dict("records")

# c) type ------------------------------------------------------------------
out["type"] = c.execute("""SELECT sat, daynight dn, type, COUNT(*) n FROM ib
    WHERE source='archive' GROUP BY ALL ORDER BY ALL""").df().to_dict("records")

# d) Ueberflugzeit ---------------------------------------------------------
out["lst_hist"] = c.execute("""SELECT sat, floor(lst*4)/4 h, COUNT(*) n FROM ib
    WHERE acq_date BETWEEN '2012-02-01' AND '2021-12-31' GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
out["lst_drift"] = c.execute("""SELECT year(acq_date) y, sat, daynight dn,
    median(CASE WHEN sat='Terra' AND daynight='N' AND lst<12 THEN lst+24 ELSE lst END) lst, COUNT(*) n
    FROM ib GROUP BY ALL HAVING COUNT(*)>=50 ORDER BY ALL""").df().to_dict("records")
out["utc_range"] = c.execute("""SELECT sat, daynight dn, MIN(utc_h) mn, MAX(utc_h) mx
    FROM ib GROUP BY ALL ORDER BY ALL""").df().to_dict("records")

# e) Scan-Geometrie --------------------------------------------------------
out["scan_track"] = c.execute("""SELECT sensor, round(scan, CASE WHEN sensor='MODIS' THEN 1 ELSE 2 END) scan,
    AVG(track) track, MIN(track) tmin, MAX(track) tmax, COUNT(*) n
    FROM ib GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
# Erkennungsschwelle: untere FRP-Quantile je Pixelflaeche (nur echte Feuer)
out["frp_threshold"] = c.execute("""
    WITH t AS (SELECT sat, daynight dn, scan*track area, frp FROM ib
               WHERE source='archive' AND type=0 AND frp>0),
    b AS (SELECT *, ntile(12) OVER (PARTITION BY sat, dn ORDER BY area) g FROM t)
    SELECT sat, dn, g, AVG(area) area, quantile_cont(frp,0.05) p05, quantile_cont(frp,0.5) p50,
           COUNT(*) n FROM b GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
out["scan_share"] = c.execute("""SELECT sat, AVG((scan*track > 2*amin)::INT) share_area_gt2x,
    AVG((scan*track > 4*amin)::INT) share_area_gt4x, median(scan*track) area_med, MIN(amin) area_min
    FROM (SELECT *, MIN(scan*track) OVER (PARTITION BY sat) amin FROM ib) GROUP BY ALL ORDER BY ALL""").df().to_dict("records")

# f) FRP ~ Helligkeit ------------------------------------------------------
df = c.execute("""SELECT sat, sensor, daynight dn, brightness b, bright_t31 t31, frp,
    scan*track area FROM ib WHERE source='archive' AND type=0 AND frp>0""").df()
link = []
for (sat, dn), g in df.groupby(["sat", "dn"]):
    r = dict(sat=sat, dn=dn, n=len(g))
    r["rho_frp_bright"] = spearmanr(g.frp, g.b)[0]
    r["rho_frp_dT"] = spearmanr(g.frp, g.b - g.t31)[0]
    r["rho_frp_area"] = spearmanr(g.frp, g.area)[0]
    r["rho_frp_per_area_bright"] = spearmanr(g.frp / g.area, g.b)[0]
    # Physik-Modell (Wooster/Kaufman): FRP ~ A * (T4^8 - Tbg^8); Tbg genaehert durch T31
    x = g.area * ((g.b / 100) ** 8 - (g.t31 / 100) ** 8)
    ok = (x > 0) & (g.b < 366.9 if sat == "SNPP" else True)
    lx, ly = np.log(x[ok]), np.log(g.frp[ok])
    slope, icpt = np.polyfit(lx, ly, 1)
    r["phys_share_usable"] = float(ok.mean())
    r["phys_loglog_slope"] = slope
    r["phys_r2"] = float(np.corrcoef(lx, ly)[0, 1] ** 2)
    link.append(r)
out["frp_link"] = link
# binned FRP/Flaeche gegen brightness, fuer die Grafik
df["bbin"] = (df.b // 5) * 5
g = (df[df.b.between(295, 420)].assign(fpa=lambda d: d.frp / d.area)
     .groupby(["sat", "dn", "bbin"]).fpa.agg(["median", "count"]).reset_index())
out["frp_per_area_vs_bright"] = g[g["count"] >= 30].to_dict("records")
out["viirs_saturation"] = c.execute("""SELECT daynight dn, AVG((brightness>=367)::INT) share_367,
    AVG((brightness<295)::INT) share_lt295, COUNT(*) n FROM ib WHERE sensor='VIIRS' GROUP BY ALL""").df().to_dict("records")

# g) Mehrfach-Ueberfluege --------------------------------------------------
# Zelle 0,05 Grad x Datum x Tag/Nacht: liegen Erkennungen > 30 min auseinander (= zwei Ueberfluege)?
out["multi_overpass"] = c.execute("""
    WITH cd AS (SELECT sat, daynight dn, acq_date, floor(latitude/0.05) i, floor(longitude/0.05) j,
                       MAX(utc_h) - MIN(utc_h) span_h, COUNT(*) n_det
                FROM ib WHERE source='archive' AND type=0 GROUP BY ALL)
    SELECT sat, dn, COUNT(*) cell_days, AVG((span_h>0.5)::INT) share_multi,
           SUM(n_det) FILTER (span_h>0.5) * 1.0 / SUM(n_det) share_det_in_multi
    FROM cd GROUP BY ALL ORDER BY ALL""").df().to_dict("records")

save("columns", out)
for k in ["conf_viirs", "type", "scan_share", "frp_link", "multi_overpass", "viirs_saturation"]:
    print("\n", k, "\n", pd.DataFrame(out[k]).round(3).to_string(index=False))
