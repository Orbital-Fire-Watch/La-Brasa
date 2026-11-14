"""Schritt 4: Auf welcher Skala und mit welcher Kenngroesse stimmen die Sensoren ueberein?

Verglichen werden Aqua (und Terra) mit SNPP, nur type = 0, Archivdaten.
  a) Raster x Zeitschritt: Uebereinstimmung der Anzahlen (0,05 Grad ... NUTS-2 ... gesamt; Tag/Monat/Jahr)
  b) Kenngroessen im Vergleich: Anzahl, FRP-Summe, Pixelflaeche, aktive Tage, aktive Zell-Tage
  c) Verhaeltnis VIIRS/MODIS ueber die Jahre (Bahndrift!), ueber die Monate, ueber die Regionen
  d) Terra gegen Aqua (fuer die Rueckverlaengerung vor 2002 und als zweite MODIS-Quelle)
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import IBERIA, con, save

STABLE = (2012, 2021)      # Jahre ohne Bahndrift von Aqua/Terra (siehe 02_columns.py)
c = con()
df = c.execute(f"""SELECT sat, acq_date, daynight dn, latitude lat, longitude lon, frp,
        scan*track area, region_id, year(acq_date) y, month(acq_date) m
    FROM '{IBERIA}' WHERE source='archive' AND type=0
      AND acq_date BETWEEN '2000-11-01' AND '2026-07-31'""").df()
df["cd"] = (np.floor(df.lat / 0.05) * 100000 + np.floor(df.lon / 0.05)).astype("int64")  # Zelle 0,05
df["doy"] = pd.to_datetime(df.acq_date).dt.day_of_year
df["ym"] = df.y * 100 + df.m
df["day"] = df.y * 1000 + df.doy
out = {}


def unit(d, g):
    if g == "nuts2":
        return d.region_id
    if g == "all":
        return pd.Series(0, index=d.index)
    return (np.floor(d.lat / g) * 100000 + np.floor(d.lon / g)).astype("int64")


def agg(d, ucol, tcol):
    """Kenngroessen je (Einheit, Zeitschritt, Satellit) -> breit."""
    g = d.groupby([ucol, tcol, "sat"]).agg(
        n=("frp", "size"), frp=("frp", "sum"), area=("area", "sum"),
        days=("day", "nunique"), celldays=("cdday", "nunique")).unstack("sat", fill_value=0)
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    return g


df["cdday"] = df.cd * 10000000 + df.day
ov = df[(df.y >= STABLE[0]) & (df.y <= STABLE[1]) & (df.acq_date >= pd.Timestamp("2012-02-01"))].copy()

# a) Skalen ------------------------------------------------------------------
rows = []
for g in [0.05, 0.1, 0.25, 0.5, 1.0, "nuts2", "all"]:
    ov["u"] = unit(ov, g)
    for tname, tcol in [("Tag", "day"), ("Monat", "ym"), ("Jahr", "y")]:
        a = agg(ov[ov.sat.isin(["Aqua", "SNPP"])].dropna(subset=["u"]), "u", tcol)
        x, yv = a.n_Aqua.values, a.n_SNPP.values
        both, onlyS, onlyA = (x > 0) & (yv > 0), (x == 0) & (yv > 0), (x > 0) & (yv == 0)
        r = dict(grid=str(g), time=tname, n_units=len(a), both=float(both.mean()),
                 only_snpp=float(onlyS.mean()), only_aqua=float(onlyA.mean()))
        if len(a) >= 8:
            r["spearman"] = float(spearmanr(x, yv)[0])
            r["r2_log"] = float(np.corrcoef(np.log1p(x), np.log1p(yv))[0, 1] ** 2)
            if both.sum() >= 8:
                lr = np.log(yv[both] / x[both])
                r["ratio_median"] = float(np.exp(np.median(lr)))
                r["ratio_spread"] = float(np.exp(np.percentile(lr, 84)) / np.exp(np.percentile(lr, 16)))
        rows.append(r)
out["scales"] = rows

# b) Kenngroessen im Vergleich -------------------------------------------------
rows = []
for g in [0.25, "nuts2"]:
    ov["u"] = unit(ov, g)
    for dn in ["D", "N", "alle"]:
        sub = ov if dn == "alle" else ov[ov.dn == dn]
        a = agg(sub[sub.sat.isin(["Aqua", "SNPP"])].dropna(subset=["u"]), "u", "ym")
        ay = agg(sub[sub.sat.isin(["Aqua", "SNPP"])].dropna(subset=["u"]), "u", "y")
        for met in ["n", "frp", "area", "days", "celldays"]:
            x, yv = a[f"{met}_Aqua"].values, a[f"{met}_SNPP"].values
            yr = ay.groupby(level=1)[[f"{met}_Aqua", f"{met}_SNPP"]].sum()
            yratio = yr[f"{met}_SNPP"] / yr[f"{met}_Aqua"]
            rg = ay.groupby(level=0)[[f"{met}_Aqua", f"{met}_SNPP"]].sum()
            rg = rg[rg[f"{met}_Aqua"] > 0]
            rratio = rg[f"{met}_SNPP"] / rg[f"{met}_Aqua"]
            rows.append(dict(grid=str(g), dn=dn, metric=met, n_units=len(a),
                             spearman=float(spearmanr(x, yv)[0]),
                             r2_log=float(np.corrcoef(np.log1p(x), np.log1p(yv))[0, 1] ** 2),
                             ratio_sum=float(yv.sum() / x.sum()),
                             ratio_year_min=float(yratio.min()), ratio_year_max=float(yratio.max()),
                             cv_year=float(yratio.std() / yratio.mean()),
                             cv_region=float(rratio.std() / rratio.mean())))
out["metrics"] = rows

# c) Verhaeltnis ueber die Zeit -------------------------------------------------
full = df[df.acq_date >= pd.Timestamp("2012-02-01")]
rows = []
for dn in ["D", "N", "alle"]:
    sub = full if dn == "alle" else full[full.dn == dn]
    g = sub.groupby(["y", "sat"]).agg(n=("frp", "size"), frp=("frp", "sum"),
                                      celldays=("cdday", "nunique")).unstack("sat", fill_value=0)
    for y, r in g.iterrows():
        rows.append(dict(dn=dn, y=int(y),
                         n_snpp_aqua=r[("n", "SNPP")] / r[("n", "Aqua")],
                         n_snpp_terra=r[("n", "SNPP")] / r[("n", "Terra")],
                         n_snpp_modis=r[("n", "SNPP")] / (r[("n", "Aqua")] + r[("n", "Terra")]),
                         frp_snpp_aqua=r[("frp", "SNPP")] / r[("frp", "Aqua")],
                         frp_snpp_terra=r[("frp", "SNPP")] / r[("frp", "Terra")],
                         cd_snpp_aqua=r[("celldays", "SNPP")] / r[("celldays", "Aqua")],
                         n_aqua=int(r[("n", "Aqua")]), n_terra=int(r[("n", "Terra")]),
                         n_snpp=int(r[("n", "SNPP")])))
out["ratio_by_year"] = rows

rows = []
for dn in ["D", "N", "alle"]:
    sub = ov if dn == "alle" else ov[ov.dn == dn]
    g = sub.groupby(["m", "sat"]).agg(n=("frp", "size"), frp=("frp", "sum")).unstack("sat", fill_value=0)
    gy = sub.groupby(["y", "m", "sat"]).size().unstack("sat", fill_value=0)
    gy = gy[gy.Aqua >= 20]
    sp = (gy.SNPP / gy.Aqua).groupby(level="m").agg(["min", "max"])
    for mth, r in g.iterrows():
        rows.append(dict(dn=dn, m=int(mth), n_ratio=r[("n", "SNPP")] / r[("n", "Aqua")],
                         frp_ratio=r[("frp", "SNPP")] / r[("frp", "Aqua")],
                         n_ratio_min=float(sp["min"].get(mth, np.nan)), n_ratio_max=float(sp["max"].get(mth, np.nan)),
                         n_aqua=int(r[("n", "Aqua")]), n_snpp=int(r[("n", "SNPP")])))
out["ratio_by_month"] = rows

# Regionen: Verhaeltnis und Erklaerung ueber die Feuergroesse
cl = (ov[ov.sat == "SNPP"].groupby(["region_id", "cdday"]).frp.sum().reset_index())
small = cl.assign(small=cl.frp < 10).groupby("region_id").small.mean()
g = ov.groupby(["region_id", "sat"]).agg(n=("frp", "size"), frp=("frp", "sum")).unstack("sat", fill_value=0)
rows = []
for rid, r in g.iterrows():
    if r[("n", "Aqua")] < 100:
        continue
    rows.append(dict(region_id=rid, n_ratio=r[("n", "SNPP")] / r[("n", "Aqua")],
                     frp_ratio=r[("frp", "SNPP")] / r[("frp", "Aqua")],
                     share_small=float(small[rid]), n_aqua=int(r[("n", "Aqua")]), n_snpp=int(r[("n", "SNPP")])))
out["ratio_by_region"] = rows
rr = pd.DataFrame(rows)
out["region_ratio_vs_small"] = dict(spearman=float(spearmanr(rr.n_ratio, rr.share_small)[0]),
                                    n_ratio_min=float(rr.n_ratio.min()), n_ratio_max=float(rr.n_ratio.max()),
                                    frp_ratio_min=float(rr.frp_ratio.min()), frp_ratio_max=float(rr.frp_ratio.max()))

# d) Terra gegen Aqua -----------------------------------------------------------
g = df[df.sat.isin(["Terra", "Aqua"])].groupby(["y", "sat", "dn"]).agg(
    n=("frp", "size"), frp=("frp", "sum")).unstack(["sat", "dn"], fill_value=0)
rows = []
for y, r in g.iterrows():
    if y < 2003:
        continue
    rows.append(dict(y=int(y),
                     n_D=r[("n", "Terra", "D")] / r[("n", "Aqua", "D")],
                     n_N=r[("n", "Terra", "N")] / r[("n", "Aqua", "N")],
                     n_all=(r[("n", "Terra", "D")] + r[("n", "Terra", "N")]) / (r[("n", "Aqua", "D")] + r[("n", "Aqua", "N")]),
                     frp_all=(r[("frp", "Terra", "D")] + r[("frp", "Terra", "N")]) / (r[("frp", "Aqua", "D")] + r[("frp", "Aqua", "N")])))
out["terra_aqua_by_year"] = rows
# Monat x NUTS-2: wie gut sagt Terra bzw. Aqua bzw. beide SNPP vorher (stabile Jahre)?
ov["u"] = ov.region_id
a = agg(ov.dropna(subset=["u"]), "u", "ym")
ly = np.log1p(a.n_SNPP.values)
pred = {"Aqua": a.n_Aqua, "Terra": a.n_Terra, "Aqua+Terra": a.n_Aqua + a.n_Terra}
out["terra_vs_aqua_as_predictor"] = [
    dict(src=k, spearman=float(spearmanr(v, a.n_SNPP)[0]),
         r2_log=float(np.corrcoef(np.log1p(v.values), ly)[0, 1] ** 2)) for k, v in pred.items()]
tm = df[(df.y >= 2003) & (df.y <= 2021)].dropna(subset=["region_id"])
tm = tm[tm.sat.isin(["Terra", "Aqua"])].assign(u=lambda d: d.region_id)
b = agg(tm, "u", "ym")
out["terra_vs_aqua_monthly"] = dict(
    spearman=float(spearmanr(b.n_Terra, b.n_Aqua)[0]),
    r2_log=float(np.corrcoef(np.log1p(b.n_Terra), np.log1p(b.n_Aqua))[0, 1] ** 2),
    ratio_sum=float(b.n_Terra.sum() / b.n_Aqua.sum()))

save("scales", out)
pd.set_option("display.width", 250)
for k in ["scales", "metrics", "ratio_by_year", "ratio_by_month", "ratio_by_region", "terra_aqua_by_year",
          "terra_vs_aqua_as_predictor"]:
    print("\n", k, "\n", pd.DataFrame(out[k]).round(3).to_string(index=False))
print(out["region_ratio_vs_small"], out["terra_vs_aqua_monthly"])
