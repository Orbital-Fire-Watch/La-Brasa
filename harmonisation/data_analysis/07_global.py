"""Schritt 7: Gegenprobe mit den weltweiten Daten (17.10.2025 - 31.07.2026, Archivteil).

Fragen:
  a) Wie gut stimmen ZWEI VIIRS-Instrumente ueberein (SNPP, NOAA-20, NOAA-21)?
     -> Untergrenze des Fehlers, den keine MODIS-Harmonisierung unterbieten kann,
        und Antwort auf die Frage, ob die VIIRS-Nachfolger eine eigene Umrechnung brauchen.
  b) Ist der Faktor VIIRS/MODIS weltweit gleich? -> Uebertragbarkeit auf andere Regionen
  c) Lokale Ueberflugzeiten aller fuenf Satelliten heute

Nur type = 0. Achtung: In diesem Zeitraum driften Aqua und Terra bereits.
"""
import numpy as np
import pandas as pd

from common import GLOBAL, con, save

c = con()
c.execute(f"""CREATE VIEW g AS SELECT * FROM '{GLOBAL}'
              WHERE source='archive' AND type=0 AND acq_date BETWEEN '2025-10-17' AND '2026-07-31'""")
out = {}

# c) Ueberflugzeiten -----------------------------------------------------------------
out["lst"] = c.execute("""SELECT sat, daynight dn, COUNT(*) n,
    median(CASE WHEN daynight='N' AND lst>12 THEN lst-24 ELSE lst END) lst
    FROM g WHERE abs(latitude) < 45 GROUP BY ALL ORDER BY ALL""").df().to_dict("records")
out["totals"] = c.execute("""SELECT sat, daynight dn, COUNT(*) n, SUM(frp) frp FROM g
    GROUP BY ALL ORDER BY ALL""").df().to_dict("records")

# a) VIIRS gegen VIIRS, MODIS gegen VIIRS: 1-Grad-Zelle x Monat --------------------------
cm = c.execute("""SELECT floor(latitude) la, floor(longitude) lo, month(acq_date) m, sat,
    COUNT(*) n, SUM(frp) frp FROM g GROUP BY ALL""").df()
w = cm.pivot_table(index=["la", "lo", "m"], columns="sat", values=["n", "frp"], fill_value=0)
w.columns = [f"{a}_{b}" for a, b in w.columns]
w = w.reset_index()
w["n_MODIS"] = w.n_Aqua + w.n_Terra


def pair(d, a, b, k=None):
    """b aus a vorhersagen mit einem einzigen Faktor (Summe b / Summe a)."""
    x, y = d[a].values.astype(float), d[b].values.astype(float)
    k = y.sum() / x.sum() if k is None else k
    le = np.abs(np.log((k * x + 1) / (y + 1)))
    return dict(a=a, b=b, n_units=len(d), factor=float(k), factor_err=float(np.exp(np.median(le))),
                factor_err_p90=float(np.exp(np.quantile(le, .9))),
                r2_log=float(np.corrcoef(np.log1p(x), np.log1p(y))[0, 1] ** 2))


act = w[(w.n_SNPP + w.n_N20) >= 20]          # Zell-Monate mit nennenswerter Aktivitaet
out["pairs_global"] = [pair(act, "n_N20", "n_SNPP"), pair(act, "n_N21", "n_SNPP"),
                       pair(act, "n_N21", "n_N20"), pair(act, "n_Aqua", "n_SNPP"),
                       pair(act, "n_MODIS", "n_SNPP"),
                       pair(act, "frp_N20", "frp_SNPP"), pair(act, "frp_Aqua", "frp_SNPP")]
ib = act[(act.la.between(36, 43)) & (act.lo.between(-10, 3))]
out["pairs_iberia_box"] = [pair(ib, "n_N20", "n_SNPP"), pair(ib, "n_N21", "n_SNPP"),
                           pair(ib, "n_Aqua", "n_SNPP"), pair(ib, "n_MODIS", "n_SNPP")]

# b) Faktor je 5-Grad-Kachel --------------------------------------------------------------
t = c.execute("""SELECT floor(latitude/5)*5 la, floor(longitude/5)*5 lo,
    COUNT(*) FILTER (sat='Aqua') n_aqua, COUNT(*) FILTER (sat='Terra') n_terra,
    COUNT(*) FILTER (sat='SNPP') n_snpp, COUNT(*) FILTER (sat='N20') n_n20,
    SUM(frp) FILTER (sat='Aqua') frp_aqua, SUM(frp) FILTER (sat='SNPP') frp_snpp,
    COUNT(*) FILTER (sat='SNPP' AND daynight='N') * 1.0 / COUNT(*) FILTER (sat='SNPP') night_share,
    median(frp) FILTER (sat='SNPP') frp_med_snpp
    FROM g GROUP BY ALL HAVING COUNT(*) FILTER (sat='Aqua') >= 500""").df()
t["n_ratio"] = t.n_snpp / t.n_aqua
t["frp_ratio"] = t.frp_snpp / t.frp_aqua
t["n20_ratio"] = t.n_n20 / t.n_snpp
q = [0.05, 0.25, 0.5, 0.75, 0.95]
out["tiles"] = dict(
    n_tiles=len(t),
    n_ratio=dict(zip(["p05", "p25", "p50", "p75", "p95"], t.n_ratio.quantile(q).tolist())),
    frp_ratio=dict(zip(["p05", "p25", "p50", "p75", "p95"], t.frp_ratio.quantile(q).tolist())),
    n20_ratio=dict(zip(["p05", "p25", "p50", "p75", "p95"], t.n20_ratio.quantile(q).tolist())),
    global_n_ratio=float(t.n_snpp.sum() / t.n_aqua.sum()),
    global_frp_ratio=float(t.frp_snpp.sum() / t.frp_aqua.sum()),
    corr_ratio_vs_frp_med=float(t[["n_ratio", "frp_med_snpp"]].corr(method="spearman").iloc[0, 1]),
    corr_ratio_vs_night=float(t[["n_ratio", "night_share"]].corr(method="spearman").iloc[0, 1]))
out["tile_list"] = t[["la", "lo", "n_aqua", "n_snpp", "n_ratio", "frp_ratio", "n20_ratio"]].round(3).to_dict("records")
# grobe Grossregionen
REG = {"Iberien-Box": (36, 44, -10, 4), "Suedamerika (Suedhaelfte)": (-40, -15, -75, -40),
       "Amazonas / Cerrado": (-15, 5, -75, -40), "Afrika suedl. Sahara Nord": (0, 15, -18, 45),
       "Afrika Sued": (-25, 0, 10, 42), "Suedostasien": (5, 28, 92, 110),
       "Australien": (-40, -10, 112, 155), "Nordamerika": (25, 60, -130, -60),
       "Sibirien / Zentralasien": (40, 70, 40, 140), "Indien": (8, 32, 68, 90)}
rows = []
for name, (la0, la1, lo0, lo1) in REG.items():
    r = c.execute(f"""SELECT COUNT(*) FILTER (sat='Aqua') a, COUNT(*) FILTER (sat='Terra') te,
        COUNT(*) FILTER (sat='SNPP') s, COUNT(*) FILTER (sat='N20') n20,
        SUM(frp) FILTER (sat='Aqua') fa, SUM(frp) FILTER (sat='SNPP') fs,
        COUNT(*) FILTER (sat='SNPP' AND daynight='D') sd, COUNT(*) FILTER (sat='Aqua' AND daynight='D') ad,
        COUNT(*) FILTER (sat='SNPP' AND daynight='N') sn, COUNT(*) FILTER (sat='Aqua' AND daynight='N') an
        FROM g WHERE latitude BETWEEN {la0} AND {la1} AND longitude BETWEEN {lo0} AND {lo1}""").fetchone()
    a, te, s, n20, fa, fs, sd, ad, sn, an = r
    rows.append(dict(region=name, n_aqua=a, n_snpp=s, n_ratio=s / a, n_ratio_day=sd / ad,
                     n_ratio_night=sn / max(an, 1), n_ratio_modis=s / (a + te), frp_ratio=fs / fa,
                     n20_vs_snpp=n20 / s))
out["macro_regions"] = rows
save("global", out)
pd.set_option("display.width", 220)
for k in ["lst", "pairs_global", "pairs_iberia_box", "macro_regions"]:
    print("\n", k, "\n", pd.DataFrame(out[k]).round(3).to_string(index=False))
print(out["tiles"])
