"""Schritt 3: Direkter Paarvergleich Aqua (MODIS) gegen SNPP (VIIRS).

Beide ueberfliegen Iberien zur aehnlichen Ortszeit. Verglichen wird am selben Datum
und in derselben Tageshaelfte (daynight), nur echte Feuer (type = 0), Archivdaten.

Fragen:
  a) Wie weit liegen zusammengehoerende Erkennungen raeumlich/zeitlich auseinander?
     -> bestimmt die kleinste sinnvolle Gitterzelle
  b) Welchen Anteil der Aqua-Erkennungen bestaetigt SNPP, und umgekehrt?
  c) Erkennungswahrscheinlichkeit von Aqua als Funktion der Feuerstaerke (VIIRS-FRP)
     -> die eigentliche Verknuepfungsfunktion fuer Anzahlen
  d) Bei Feuern, die beide sehen: Wie haengen Anzahl und FRP zusammen?
"""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import statsmodels.api as sm

from common import IBERIA, OVERLAP_END, OVERLAP_START, con, save

c = con()
df = c.execute(f"""SELECT sat, acq_date, daynight dn, latitude lat, longitude lon, utc_h, frp,
        scan, track, scan*track area, confidence
    FROM '{IBERIA}' WHERE source='archive' AND type=0 AND sat IN ('Aqua','SNPP')
      AND acq_date BETWEEN '{OVERLAP_START}' AND '{OVERLAP_END}'""").df()
df["x"] = df.lon * 111.32 * np.cos(np.radians(40.0))     # km, lokale Projektion
df["y"] = df.lat * 110.57
df["year"] = pd.to_datetime(df.acq_date).dt.year
out = {"n_aqua": int((df.sat == "Aqua").sum()), "n_snpp": int((df.sat == "SNPP").sum())}

# a/b) naechster Nachbar im anderen Sensor --------------------------------
parts = []
for (d, dn), g in df.groupby(["acq_date", "dn"], sort=False):
    a, s = g[g.sat == "Aqua"], g[g.sat == "SNPP"]
    for own, other in ((a, s), (s, a)):
        if len(own) == 0:
            continue
        o = own[["sat", "dn", "year", "frp", "area", "utc_h", "confidence"]].copy()
        if len(other):
            dist, idx = cKDTree(other[["x", "y"]].values).query(own[["x", "y"]].values)
            o["dist"] = dist
            o["dt"] = own.utc_h.values - other.utc_h.values[idx]
            o["frp_other"] = other.frp.values[idx]
        else:
            o["dist"], o["dt"], o["frp_other"] = np.inf, np.nan, np.nan
        parts.append(o)
nn = pd.concat(parts, ignore_index=True)

radii = [0.5, 1, 2, 3, 5, 10, 25]
out["confirm"] = [
    dict(sat=sat, dn=dn, n=len(g), **{f"r{r}": float((g.dist <= r).mean()) for r in radii})
    for (sat, dn), g in nn.groupby(["sat", "dn"])]
out["confirm_all"] = [
    dict(sat=sat, n=len(g), **{f"r{r}": float((g.dist <= r).mean()) for r in radii})
    for sat, g in nn.groupby("sat")]
# Verteilung der Distanzen (fuer die Grafik), Aqua -> naechster SNPP-Punkt
bins = np.array([0, .25, .5, .75, 1, 1.5, 2, 3, 4, 5, 7.5, 10, 15, 25, 50, 1e9])
a = nn[nn.sat == "Aqua"]
h = np.histogram(a.dist.replace(np.inf, 1e8), bins=bins)[0]
out["dist_hist_aqua"] = dict(edges=bins[:-1].tolist(), share=(h / h.sum()).tolist())
m = a[a.dist <= 3]
out["dist_quantiles_matched"] = dict(zip(["p50", "p75", "p90"], m.dist.quantile([.5, .75, .9]).tolist()))
out["dt_quantiles_matched_h"] = dict(zip(["p05", "p25", "p50", "p75", "p95"],
                                         m["dt"].quantile([.05, .25, .5, .75, .95]).tolist()))
# Aqua-Bestaetigung nach MODIS-Konfidenzklasse und nach Pixelflaeche
a = a.assign(k=pd.cut(a.confidence.astype(int), [-1, 29, 79, 100], labels=["low", "nominal", "high"]),
             ab=pd.cut(a.area, [0, 1.2, 2, 4, 20], labels=["<1.2", "1.2-2", "2-4", ">4"]))
out["aqua_confirm_by_conf"] = [dict(k=str(k), n=len(g), share=float((g.dist <= 3).mean()))
                               for k, g in a.groupby("k", observed=True)]
out["aqua_confirm_by_area"] = [dict(area=str(k), n=len(g), share=float((g.dist <= 3).mean()))
                               for k, g in a.groupby("ab", observed=True)]
# SNPP -> Aqua nach FRP des einzelnen VIIRS-Pixels
s = nn[(nn.sat == "SNPP") & (nn.frp > 0)].copy()
s["fb"] = pd.qcut(s.frp, 12, duplicates="drop")
out["snpp_pixel_seen_by_aqua"] = [
    dict(dn=dn, frp=float(g.frp.median()), n=len(g), share=float((g.dist <= 3).mean()))
    for (dn, fb), g in s.groupby(["dn", "fb"], observed=True)]

# c) Feuer-Ebene: VIIRS-Cluster je Zelle 0,05 Grad x Datum x Tag/Nacht --------
G = 0.05
df["i"] = np.floor(df.lat / G).astype(int)
df["j"] = np.floor(df.lon / G).astype(int)
cl = (df.groupby(["sat", "acq_date", "dn", "i", "j"])
        .agg(n=("frp", "size"), frp=("frp", "sum"), utc=("utc_h", "mean"), year=("year", "first"))
        .reset_index())
A = cl[cl.sat == "Aqua"].drop(columns="sat")
S = cl[cl.sat == "SNPP"].drop(columns="sat")
# Aqua "sieht" einen VIIRS-Cluster, wenn es in der Zelle oder einer der 8 Nachbarzellen erkennt
keys = set(zip(A.acq_date, A.dn, A.i, A.j))
S["seen"] = [any((d, dn, i + di, j + dj) in keys for di in (-1, 0, 1) for dj in (-1, 0, 1))
             for d, dn, i, j in zip(S.acq_date, S.dn, S.i, S.j)]
skeys = set(zip(S.acq_date, S.dn, S.i, S.j))
A["seen"] = [any((d, dn, i + di, j + dj) in skeys for di in (-1, 0, 1) for dj in (-1, 0, 1))
             for d, dn, i, j in zip(A.acq_date, A.dn, A.i, A.j)]
out["cluster"] = dict(
    n_snpp=len(S), n_aqua=len(A),
    snpp_seen_by_aqua=float(S.seen.mean()), aqua_seen_by_snpp=float(A.seen.mean()),
    snpp_frp_share_seen=float(S.frp[S.seen].sum() / S.frp.sum()),
    by_dn=[dict(dn=dn, n=len(g), seen=float(g.seen.mean()),
                frp_share_seen=float(g.frp[g.seen].sum() / g.frp.sum()))
           for dn, g in S.groupby("dn")])

# Erkennungskurve: P(Aqua sieht Cluster) ~ logit(a + b*log10(FRP_VIIRS)), getrennt Tag/Nacht
curves, fits = [], []
S = S[S.frp > 0].copy()
S["lf"] = np.log10(S.frp)
for dn, g in S.groupby("dn"):
    g = g.assign(fb=pd.qcut(g.lf, 15, duplicates="drop"))
    for fb, b in g.groupby("fb", observed=True):
        curves.append(dict(dn=dn, frp=float(10 ** b.lf.median()), n=len(b), p=float(b.seen.mean())))
    for label, sub in (("alle", g), ("2012-2021", g[g.year <= 2021]), ("2023-2026", g[g.year >= 2023])):
        res = sm.Logit(sub.seen.astype(float), sm.add_constant(sub.lf)).fit(disp=0)
        a0, b1 = res.params
        fits.append(dict(dn=dn, period=label, n=len(sub), a=float(a0), b=float(b1),
                         frp50=float(10 ** (-a0 / b1)), frp90=float(10 ** ((np.log(9) - a0) / b1))))
out["detect_curve"] = curves
out["detect_fit"] = fits
# Verteilung der VIIRS-Cluster nach Staerke: wie viel liegt unter der MODIS-Schwelle?
edges = [0, 1, 2, 5, 10, 20, 50, 100, 500, 1e9]
S["fc"] = pd.cut(S.frp, edges)
out["cluster_size_dist"] = [dict(dn=dn, cls=str(fc), n=len(g), share_n=len(g) / (S.dn == dn).sum(),
                                 share_frp=float(g.frp.sum() / S.frp[S.dn == dn].sum()),
                                 seen=float(g.seen.mean()))
                            for (dn, fc), g in S.groupby(["dn", "fc"], observed=True)]

# d) Gemeinsam gesehene Cluster: Anzahl und FRP --------------------------------
J = S.merge(A, on=["acq_date", "dn", "i", "j"], suffixes=("_s", "_a"))
J["dt"] = J.utc_a - J.utc_s
co = []
for dn, g in list(J.groupby("dn")) + [("alle", J)]:
    lx, ly = np.log10(g.frp_a.clip(lower=0.1)), np.log10(g.frp_s.clip(lower=0.1))
    sl, ic = np.polyfit(lx, ly, 1)
    lnx, lny = np.log10(g.n_a), np.log10(g.n_s)
    sln, icn = np.polyfit(lnx, lny, 1)
    co.append(dict(dn=dn, n=len(g),
                   frp_ratio_median=float((g.frp_s / g.frp_a.clip(lower=0.1)).median()),
                   frp_sum_ratio=float(g.frp_s.sum() / g.frp_a.sum()),
                   frp_loglog_slope=float(sl), frp_loglog_icpt=float(ic),
                   frp_r2=float(np.corrcoef(lx, ly)[0, 1] ** 2),
                   n_ratio_median=float((g.n_s / g.n_a).median()),
                   n_sum_ratio=float(g.n_s.sum() / g.n_a.sum()),
                   n_loglog_slope=float(sln), n_loglog_icpt=float(icn),
                   n_r2=float(np.corrcoef(lnx, lny)[0, 1] ** 2)))
out["codetected"] = co
# binned fuer Grafik: FRP_SNPP gegen FRP_Aqua (Median + Quartile je Klasse)
J["ab"] = pd.qcut(np.log10(J.frp_a.clip(lower=0.1)), 14, duplicates="drop")
out["codetected_frp_binned"] = [
    dict(frp_a=float(g.frp_a.median()), q25=float(g.frp_s.quantile(.25)),
         q50=float(g.frp_s.median()), q75=float(g.frp_s.quantile(.75)), n=len(g))
    for _, g in J.groupby("ab", observed=True)]
J["nb"] = pd.cut(J.n_a, [0, 1, 2, 3, 5, 8, 12, 20, 1000])
out["codetected_n_binned"] = [
    dict(n_a=float(g.n_a.median()), q25=float(g.n_s.quantile(.25)),
         q50=float(g.n_s.median()), q75=float(g.n_s.quantile(.75)), n=len(g))
    for _, g in J.groupby("nb", observed=True)]
# FRP-Verhaeltnis gegen Zeitabstand der Ueberfluege (Tagesgang)
J["dtb"] = pd.cut(J["dt"], [-3, -1, -.5, -.17, .17, .5, 1, 3])
out["codetected_by_dt"] = [
    dict(dn=dn, dt=float(g["dt"].median()), n=len(g),
         frp_ratio=float((g.frp_s / g.frp_a.clip(lower=0.1)).median()),
         n_ratio=float((g.n_s / g.n_a).median()))
    for (dn, _), g in J.groupby(["dn", "dtb"], observed=True) if len(g) >= 50]

# Gesamtbilanz: wie setzt sich der VIIRS-Ueberschuss zusammen? -------------------
tot = dict(
    n_ratio_all=float(len(df[df.sat == "SNPP"]) / len(df[df.sat == "Aqua"])),
    frp_ratio_all=float(df.frp[df.sat == "SNPP"].sum() / df.frp[df.sat == "Aqua"].sum()),
    snpp_det_share_in_seen_clusters=float(S.n[S.seen].sum() / S.n.sum()),
    snpp_det_share_in_unseen_clusters=float(S.n[~S.seen].sum() / S.n.sum()))
out["balance"] = tot
save("matchup", out)
for k in ["confirm", "aqua_confirm_by_conf", "aqua_confirm_by_area", "detect_fit", "cluster_size_dist",
          "codetected", "codetected_by_dt"]:
    print("\n", k, "\n", pd.DataFrame(out[k]).round(3).to_string(index=False))
print(out["cluster"], "\n", out["balance"], "\n", out["dist_quantiles_matched"], out["dt_quantiles_matched_h"])
