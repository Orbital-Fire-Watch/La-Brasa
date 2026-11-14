"""Schritt 5: Statische Waermequellen (type != 0) und das fehlende `type` im NRT.

type: 0 = Vegetationsfeuer, 1 = Vulkan, 2 = sonstige statische Landquelle, 3 = Offshore.
Im NRT fehlt die Spalte. Idee: aus dem Archiv eine Orts-Maske lernen und auf NRT anwenden.

Fragen:
  a) Wie stark verfaelschen statische Quellen das Verhaeltnis VIIRS/MODIS?
  b) Wie gut trifft eine Orts-Maske (gelernt bis 2022) die type-Angabe 2023-2026?
  c) Was wuerde die Maske im NRT entfernen?
"""
import numpy as np
import pandas as pd

from common import IBERIA, con, save

c = con()
df = c.execute(f"""SELECT sensor, sat, source, acq_date, year(acq_date) y, month(acq_date) m,
    daynight dn, latitude lat, longitude lon, type, frp FROM '{IBERIA}'
    WHERE acq_date >= '2012-02-01'""").df()
out = {}
arc = df[df.source == "archive"]

# a) Einfluss auf das Verhaeltnis ------------------------------------------------
rows = []
for dn in ["D", "N", "alle"]:
    s = arc if dn == "alle" else arc[arc.dn == dn]
    nS, nA = (s.sat == "SNPP").sum(), (s.sat == "Aqua").sum()
    nS0, nA0 = ((s.sat == "SNPP") & (s.type == 0)).sum(), ((s.sat == "Aqua") & (s.type == 0)).sum()
    rows.append(dict(dn=dn, static_share_snpp=1 - nS0 / nS, static_share_aqua=1 - nA0 / nA,
                     ratio_unfiltered=nS / nA, ratio_type0=nS0 / nA0))
out["effect_on_ratio"] = rows
st = arc[arc.type != 0]
g = st.groupby(["sat", "m"]).size().unstack("sat", fill_value=0)
out["static_by_month"] = [dict(m=int(m), **{k: int(v) for k, v in r.items()}) for m, r in g.iterrows()]
g = arc[arc.sat == "SNPP"].assign(static=lambda d: d.type != 0).groupby("y").static.mean()
out["static_share_snpp_by_year"] = [dict(y=int(y), share=float(v)) for y, v in g.items()]

# b) Orts-Maske lernen (<= 2022) und pruefen (2023 - 07/2026) ----------------------
train, test = arc[arc.y <= 2022], arc[arc.y >= 2023]


def cells(d, g):
    return (np.floor(d.lat / g).astype("int64") * 1000000 + np.floor(d.lon / g).astype("int64"))


rows = []
for g in [0.005, 0.01, 0.02]:
    tr = train.assign(cell=cells(train, g), static=train.type != 0)
    stat = tr.groupby("cell").static.agg(["sum", "mean", "size"])
    for kmin in [1, 3, 5, 10]:
        for share in [0.5, 0.8]:
            mask = set(stat.index[(stat["sum"] >= kmin) & (stat["mean"] >= share)])
            for buf in [0, 1]:
                m = mask
                if buf:
                    m = {c0 + di * 1000000 + dj for c0 in mask for di in (-1, 0, 1) for dj in (-1, 0, 1)}
                for sat in ["SNPP", "MODIS"]:
                    te = test[test.sat == "SNPP"] if sat == "SNPP" else test[test.sensor == "MODIS"]
                    hit = cells(te, g).isin(m).values
                    is_static = (te.type != 0).values
                    rows.append(dict(grid=g, kmin=kmin, share=share, buffer=buf, sat=sat,
                                     mask_cells=len(mask),
                                     recall=float(hit[is_static].mean()),
                                     false_removal=float(hit[~is_static].mean()),
                                     precision=float(is_static[hit].mean()) if hit.any() else np.nan,
                                     residual_static_share=float((is_static & ~hit).sum() / (~hit).sum())))
res = pd.DataFrame(rows)
out["mask_eval"] = rows
# Auswahl: hoechster Recall bei hoechstens 2 % faelschlich entfernten echten Feuern (VIIRS)
ok = res[(res.sat == "SNPP") & (res.false_removal <= 0.02)].sort_values("recall", ascending=False)
best = ok.iloc[0]
out["mask_best"] = {k: (float(v) if not isinstance(v, str) else v) for k, v in best.items()}
bm = res[(res.grid == best.grid) & (res.kmin == best.kmin) & (res["share"] == best["share"])
         & (res.buffer == best.buffer)]
out["mask_best_both"] = bm.to_dict("records")

# c) Anwendung auf NRT (Maske aus dem gesamten Archiv) -----------------------------
g = best.grid
tr = arc.assign(cell=cells(arc, g), static=arc.type != 0)
stat = tr.groupby("cell").static.agg(["sum", "mean"])
mask = set(stat.index[(stat["sum"] >= best.kmin) & (stat["mean"] >= best["share"])])
if best.buffer:
    mask = {c0 + di * 1000000 + dj for c0 in mask for di in (-1, 0, 1) for dj in (-1, 0, 1)}
nrt = df[df.source == "nrt"]
hit = cells(nrt, g).isin(mask)
out["nrt_masked"] = [dict(sat=s, dn=dn, n=len(x), removed=float(hit[x.index].mean()))
                     for (s, dn), x in nrt.groupby(["sat", "dn"])]
# Vergleich: Anteil type != 0 im Archiv in denselben Kalendermonaten (Aug-Okt) der Vorjahre
ref = arc[(arc.m.isin([8, 9, 10])) & (arc.y >= 2020)]
out["archive_static_same_season"] = [dict(sat=s, dn=dn, n=len(x), static=float((x.type != 0).mean()))
                                     for (s, dn), x in ref.groupby(["sat", "dn"])]
save("static", out)
pd.set_option("display.width", 220)
print(pd.DataFrame(out["effect_on_ratio"]).round(3).to_string(index=False))
print(ok.head(8).round(4).to_string(index=False))
print(pd.DataFrame(out["mask_best_both"]).round(4).to_string(index=False))
print(pd.DataFrame(out["nrt_masked"]).round(3).to_string(index=False))
print(pd.DataFrame(out["archive_static_same_season"]).round(3).to_string(index=False))
print(pd.DataFrame(out["static_by_month"]).to_string(index=False))
