"""Schritt 8: Probe der empfohlenen Harmonisierung als durchgehende Reihe 2001-2026.

Empfohlener Weg (siehe Report):
  * ab 2012: VIIRS SNPP direkt (Referenz)
  * 2003-2011: (Aqua + Terra) x Faktor je Region
  * 11/2000-2002: nur Terra x Terra-Faktor je Region (Aqua startet 07/2002)
  Faktoren aus den stabilen Ueberlappungsjahren 2012-2021, nur type = 0.
  Gebiet wie in der Pipeline: nur die Untersuchungsregionen (`nuts.study_regions` in pipeline_config.yaml).

Geprueft wird:
  a) Sieht die Reihe am Uebergang 2011/2012 plausibel aus (kein Sprung)?
  b) Wie gut haette die umgerechnete MODIS-Reihe 2012-2026 VIIRS getroffen (Jahreswerte)?
  c) Was passiert OHNE Harmonisierung (MODIS roh + VIIRS roh aneinandergehaengt)?
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import IBERIA, con, save

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import load_config  # noqa: E402

STUDY_REGIONS = ", ".join(f"'{region}'" for region in load_config()["nuts"]["study_regions"])

c = con()
d = c.execute(f"""SELECT region_id r, year(acq_date) y, month(acq_date) m,
        COUNT(*) FILTER (sat='Aqua') aqua, COUNT(*) FILTER (sat='Terra') terra,
        COUNT(*) FILTER (sat='SNPP') snpp,
        SUM(frp) FILTER (sat='Aqua') frp_aqua, SUM(frp) FILTER (sat='SNPP') frp_snpp
    FROM '{IBERIA}' WHERE source='archive' AND type=0 AND region_id IN ({STUDY_REGIONS})
      AND acq_date BETWEEN '2001-01-01' AND '2025-12-31' GROUP BY ALL""").df().fillna(0)
d["modis"] = d.aqua + d.terra
cal = d[(d.y >= 2012) & (d.y <= 2021) & ((d.y > 2012) | (d.m >= 2))]
g = cal.groupby("r")[["modis", "terra", "snpp"]].sum()
k_glob, kt_glob = g.snpp.sum() / g.modis.sum(), g.snpp.sum() / g.terra.sum()
k = (g.snpp / g.modis.where(g.modis >= 300)).fillna(k_glob)       # Faktor je Region
kt = (g.snpp / g.terra.where(g.terra >= 300)).fillna(kt_glob)
d["k"], d["kt"] = d.r.map(k).fillna(k_glob), d.r.map(kt).fillna(kt_glob)
d["modis_scaled"] = np.where((d.y < 2002) | ((d.y == 2002) & (d.m < 7)), d.terra * d.kt, d.modis * d.k)

yr = d.groupby("y").agg(modis_raw=("modis", "sum"), modis_scaled=("modis_scaled", "sum"),
                        snpp=("snpp", "sum"), frp_aqua=("frp_aqua", "sum"), frp_snpp=("frp_snpp", "sum"))
yr["harmonised"] = np.where(yr.index >= 2012, yr.snpp, yr.modis_scaled)
yr["naive"] = np.where(yr.index >= 2012, yr.snpp, yr.modis_raw)
out = {"k_global": float(k_glob), "kt_global": float(kt_glob),
       "k_region": {r: float(v) for r, v in k.items()}, "kt_region": {r: float(v) for r, v in kt.items()},
       "yearly": [dict(y=int(y), **{cn: float(v) for cn, v in r.items()}) for y, r in yr.iterrows()]}
ov = yr[(yr.index >= 2013)]
le = np.abs(np.log(ov.modis_scaled / ov.snpp))
out["overlap_check"] = dict(median_factor_err=float(np.exp(le.median())), max_factor_err=float(np.exp(le.max())),
                            corr=float(np.corrcoef(ov.modis_scaled, ov.snpp)[0, 1]))
# Mittelwert vor/nach dem Wechsel: naive Reihe vs. harmonisierte Reihe
pre, post = yr[(yr.index >= 2003) & (yr.index <= 2011)], yr[(yr.index >= 2012)]
out["jump"] = dict(naive_post_over_pre=float(post.naive.mean() / pre.naive.mean()),
                   harmonised_post_over_pre=float(post.harmonised.mean() / pre.harmonised.mean()),
                   modis_only_post_over_pre=float(post.modis_raw.mean() / pre.modis_raw.mean()))
# Wie verschiebt sich der "historische Median" je Region x Monat mit der langen Reihe?
d["harm"] = np.where(d.y >= 2012, d.snpp, d.modis_scaled)
full = d[d.y >= 2003].groupby(["r", "m"]).harm.median()
short = d[d.y >= 2012].groupby(["r", "m"]).harm.median()
both = pd.concat([full.rename("long"), short.rename("short")], axis=1).dropna()
both = both[(both.long > 20) | (both.short > 20)]
out["median_shift"] = dict(n=len(both), median_ratio_long_over_short=float((both.long / both.short.clip(lower=1)).median()),
                           share_changed_gt25pct=float((np.abs(np.log((both.long + 1) / (both.short + 1))) > np.log(1.25)).mean()))
save("series", out)
print(yr.round(0).to_string())
print({kk: out[kk] for kk in ["k_global", "kt_global", "overlap_check", "jump", "median_shift"]})
