"""Schritt 6: Harmonisierungsfunktionen im Vergleich (MODIS -> VIIRS-Aequivalent).

Zielgroesse: monatliche Zahl der SNPP-Erkennungen (type = 0) je NUTS-2-Region.
Eingang:     monatliche MODIS-Erkennungen derselben Region (Aqua/Terra, Tag/Nacht).

Bewertung ehrlich ausserhalb der Trainingsdaten:
  * Kreuzvalidierung "ein Jahr auslassen" ueber die stabilen Jahre 2012-2021
  * Drift-Test: Training 2012-2021, Test 2022-2026 (Aqua/Terra driften)

Kennzahlen:
  factor_err  typischer multiplikativer Fehler = exp(Median |log((pred+1)/(wahr+1))|)
  bias        Summe(pred) / Summe(wahr)
  r2_log      R^2 auf log1p-Skala
  class_acc   Trefferquote der 3 Klassen (unter / normal / ueber), Schwellen = Terzile der
              VIIRS-Werte je Region und Kalendermonat
  kappa       Cohens Kappa der Klassen (0 = Zufall, 1 = perfekt)

Zusaetzlich "Rang-Weg": gar nicht umrechnen, sondern jede Reihe an ihrer EIGENEN
Klimatologie messen (Terzile je Sensor) und nur die Klassen vergleichen.
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import nnls
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import cohen_kappa_score

from common import IBERIA, con, save

warnings.filterwarnings("ignore")
c = con()
raw = c.execute(f"""SELECT region_id r, year(acq_date) y, month(acq_date) m, sat, daynight dn,
        COUNT(*) n, SUM(frp) frp,
        COUNT(*) FILTER (frp < 10) n_lo, COUNT(*) FILTER (frp >= 10 AND frp < 50) n_mid,
        COUNT(*) FILTER (frp >= 50) n_hi
    FROM '{IBERIA}' WHERE source='archive' AND type=0 AND region_id IS NOT NULL
      AND acq_date BETWEEN '2012-02-01' AND '2026-07-31' GROUP BY ALL""").df()
keep = raw[raw.sat == "SNPP"].groupby("r").n.sum()
regions = sorted(keep[keep >= 2000].index)        # Regionen mit genug Daten
# vollstaendiges Gitter Region x Monat (auch Monate ohne Feuer zaehlen als 0)
months = [(y, m) for y in range(2012, 2027) for m in range(1, 13) if (y, m) >= (2012, 2) and (y, m) <= (2026, 7)]
idx = pd.MultiIndex.from_tuples([(r, y, m) for r in regions for y, m in months], names=["r", "y", "m"])
W = pd.DataFrame(index=idx)
for sat in ["Aqua", "Terra", "SNPP"]:
    for dn in ["D", "N"]:
        s = raw[(raw.sat == sat) & (raw.dn == dn)].set_index(["r", "y", "m"])
        W[f"n_{sat}_{dn}"] = s.n.reindex(idx).fillna(0)
        W[f"frp_{sat}_{dn}"] = s.frp.reindex(idx).fillna(0)
# MODIS-Pixel (Aqua+Terra) nach Staerke: schwach < 10 MW, mittel 10-50 MW, stark >= 50 MW
mod = raw[raw.sat.isin(["Aqua", "Terra"])].groupby(["r", "y", "m", "dn"])[["n_lo", "n_mid", "n_hi"]].sum()
for dn in ["D", "N"]:
    s = mod.xs(dn, level="dn")
    for k in ["lo", "mid", "hi"]:
        W[f"x{dn}_{k}"] = s[f"n_{k}"].reindex(idx).fillna(0)
W = W.reset_index()
W["y_true"] = W.n_SNPP_D + W.n_SNPP_N
W["frp_true"] = W.frp_SNPP_D + W.frp_SNPP_N
W["xD"] = W.n_Aqua_D + W.n_Terra_D
W["xN"] = W.n_Aqua_N + W.n_Terra_N
W["x"] = W.xD + W.xN
W["xA"] = W.n_Aqua_D + W.n_Aqua_N
W["xT"] = W.n_Terra_D + W.n_Terra_N
W["frp_x"] = W.frp_Aqua_D + W.frp_Aqua_N + W.frp_Terra_D + W.frp_Terra_N
W["frp_xA"] = W.frp_Aqua_D + W.frp_Aqua_N
W["season"] = np.where(W.m.isin([6, 7, 8, 9]), "Sommer", "Rest")

# Klassenschwellen: Terzile je Region x Kalendermonat
def terciles(d, col):
    q = d.groupby(["r", "m"])[col].quantile([1 / 3, 2 / 3]).unstack()
    q.columns = ["lo", "hi"]
    return q


def classify(d, col, q):
    t = d[["r", "m"]].merge(q, left_on=["r", "m"], right_index=True, how="left")
    v = d[col].values
    return np.where(v <= t.lo.values, 0, np.where(v <= t.hi.values, 1, 2))


Q_VIIRS = terciles(W, "y_true")
W["cls_true"] = classify(W, "y_true", Q_VIIRS)


# --- Kandidaten: fit(train) -> predict(df) --------------------------------------
def ratio(cols_by=None, xcols=("x",)):
    """Verhaeltnisfaktor(en): pred = sum_k  k_g * x_k, optional je Gruppe g."""
    def fit(tr):
        if cols_by is None:
            ks = {xc: tr.y_part[xc].sum() / max(tr[xc].sum(), 1) for xc in xcols}
            return lambda d: sum(ks[xc] * d[xc] for xc in xcols)
        glob = {xc: tr.y_part[xc].sum() / max(tr[xc].sum(), 1) for xc in xcols}
        tabs = {}
        for xc in xcols:
            g = pd.DataFrame({"y": tr.y_part[xc], "x": tr[xc], **{b: tr[b] for b in cols_by}}).groupby(list(cols_by)).sum()
            tabs[xc] = (g.y / g.x.where(g.x >= 30)).rename("k")      # zu wenig Daten -> globaler Faktor
        def pred(d):
            tot = 0
            for xc in xcols:
                k = d[list(cols_by)].merge(tabs[xc], left_on=list(cols_by), right_index=True, how="left").k
                tot = tot + k.fillna(glob[xc]).values * d[xc].values
            return tot
        return pred
    return fit


class YPart:
    """Ordnet jedem Eingang den passenden Teil des Ziels zu (Tag->Tag, Nacht->Nacht)."""
    def __init__(self, d):
        self.d = d
    def __getitem__(self, xc):
        return {"xD": self.d.n_SNPP_D, "xN": self.d.n_SNPP_N}.get(xc, self.d.y_true)


def glm(formula_cols, cat=()):
    def design(d, cols=None):
        X = pd.DataFrame({c0: np.log1p(d[c0].values) for c0 in formula_cols}, index=d.index)
        for cc in cat:
            X = X.join(pd.get_dummies(d[cc].astype(str), prefix=cc, drop_first=True, dtype=float))
        X = sm.add_constant(X, has_constant="add")
        return X if cols is None else X.reindex(columns=cols, fill_value=0.0)
    def fit(tr):
        X = design(tr)
        res = sm.GLM(tr.y_true, X, family=sm.families.Poisson()).fit()
        return lambda d: res.predict(design(d, X.columns))
    return fit


def gbm(tr):
    feats = ["n_Aqua_D", "n_Aqua_N", "n_Terra_D", "n_Terra_N", "frp_xA", "frp_x", "m", "rcode"]
    mdl = HistGradientBoostingRegressor(loss="poisson", max_iter=300, learning_rate=0.05,
                                        max_depth=4, random_state=0, categorical_features=[7])
    mdl.fit(tr[feats], tr.y_true)
    return lambda d: mdl.predict(d[feats])


def qmap(tr):
    """Quantil-Mapping je Region: MODIS-Wert -> VIIRS-Wert gleichen Rangs."""
    maps = {r: (np.sort(g.x.values), np.sort(g.y_true.values)) for r, g in tr.groupby("r")}
    def pred(d):
        o = np.zeros(len(d))
        for r, g in d.groupby("r"):
            xs, ys = maps[r]
            p = np.searchsorted(xs, g.x.values, side="right") / len(xs)
            o[d.index.get_indexer(g.index)] = np.quantile(ys, np.clip(p, 0, 1))
        return o
    return pred


def additive(xcols):
    """pred = sum_k c_k * x_k mit c_k >= 0 (nicht-negative kleinste Quadrate,
    Zeilen mit 1/sqrt(y+1) gewichtet = Poisson-artige Streuung)."""
    def fit(tr):
        w = 1 / np.sqrt(tr.y_true.values + 1)
        coef, _ = nnls(tr[list(xcols)].values * w[:, None], tr.y_true.values * w)
        fit.coef = dict(zip(xcols, coef))
        return lambda d: d[list(xcols)].values @ coef
    return fit


W["rcode"] = W.r.astype("category").cat.codes
CAND = {
    "M0 keine Umrechnung (MODIS roh)": lambda tr: (lambda d: d.x.values.astype(float)),
    "M1 ein globaler Faktor": ratio(),
    "M2 Faktor je Kalendermonat": ratio(("m",)),
    "M3 Faktor je Region": ratio(("r",)),
    "M4 Faktor getrennt Tag / Nacht": ratio(None, ("xD", "xN")),
    "M5 Faktor Tag/Nacht x Kalendermonat": ratio(("m",), ("xD", "xN")),
    "M6 Faktor Tag/Nacht x Region": ratio(("r",), ("xD", "xN")),
    "M7 Potenzgesetz (Poisson, log x)": glm(["x"]),
    "M8 Poisson: Tag/Nacht + Monat": glm(["xD", "xN"], ("m",)),
    "M9 Poisson: Aqua/Terra x Tag/Nacht + Monat": glm(["n_Aqua_D", "n_Aqua_N", "n_Terra_D", "n_Terra_N"], ("m",)),
    "M10 wie M9 + Region": glm(["n_Aqua_D", "n_Aqua_N", "n_Terra_D", "n_Terra_N"], ("m", "r")),
    "M11 Quantil-Mapping je Region": qmap,
    "M12 Gradient Boosting (alle Merkmale)": gbm,
    "M13 additiv: Gewicht je Satellit x Tag/Nacht": additive(["n_Aqua_D", "n_Aqua_N", "n_Terra_D", "n_Terra_N"]),
    "M14 additiv: Gewicht je Tag/Nacht x FRP-Klasse": additive(["xD_lo", "xD_mid", "xD_hi", "xN_lo", "xN_mid", "xN_hi"]),
    # Varianten fuer Zeitraeume mit nur einem Satelliten
    "A1 nur Aqua: Faktor je Region": ratio(("r",), ("xA",)),
    "T1 nur Terra: Faktor je Region": ratio(("r",), ("xT",)),
}


def run(fit, tr, te):
    tr = tr.copy()
    tr.y_part = YPart(tr)
    return np.clip(np.asarray(fit(tr)(te), dtype=float), 0, None)


def score(d, p):
    le = np.abs(np.log((p + 1) / (d.y_true.values + 1)))
    cls = classify(d.assign(p=p), "p", Q_VIIRS)
    return dict(factor_err=float(np.exp(np.median(le))), factor_err_p90=float(np.exp(np.quantile(le, .9))),
                bias=float(p.sum() / d.y_true.sum()),
                r2_log=float(np.corrcoef(np.log1p(p), np.log1p(d.y_true))[0, 1] ** 2),
                class_acc=float((cls == d.cls_true.values).mean()),
                kappa=float(cohen_kappa_score(cls, d.cls_true.values)))


stable = W[W.y <= 2021].reset_index(drop=True)
drift = W[W.y >= 2022].reset_index(drop=True)
rows, preds_cv = [], {}
for name, fit in CAND.items():
    p = np.zeros(len(stable))
    for yr in sorted(stable.y.unique()):
        te = stable[stable.y == yr]
        p[te.index] = run(fit, stable[stable.y != yr].reset_index(drop=True), te)
    preds_cv[name] = p
    r = dict(method=name, **{f"cv_{k}": v for k, v in score(stable, p).items()})
    pdr = run(fit, stable, drift)
    r.update({f"drift_{k}": v for k, v in score(drift, pdr).items()})
    for yr in sorted(drift.y.unique()):
        mk = (drift.y == yr).values
        r[f"drift_bias_{yr}"] = float(pdr[mk].sum() / drift.y_true[mk].sum())
    rows.append(r)
out = {"regions": regions, "n_region_months_cv": len(stable), "n_region_months_drift": len(drift),
       "candidates": rows}

# Monate ohne jede MODIS-Erkennung: hier unterscheiden sich proportionale und Log-Modelle
z = (stable.x == 0).values
zm = []
for name in ["M3 Faktor je Region", "M7 Potenzgesetz (Poisson, log x)",
             "M9 Poisson: Aqua/Terra x Tag/Nacht + Monat", "M12 Gradient Boosting (alle Merkmale)"]:
    ok = classify(stable.assign(p=preds_cv[name]), "p", Q_VIIRS) == stable.cls_true.values
    zm.append(dict(method=name, acc_zero=float(ok[z].mean()), acc_nonzero=float(ok[~z].mean()),
                   mean_pred_zero=float(preds_cv[name][z].mean())))
out["zero_months"] = dict(share=float(z.mean()), mean_true=float(stable.y_true[z].mean()), methods=zm)

# Sommer / Rest getrennt fuer drei Schluessel-Kandidaten
sub = []
for name in ["M1 ein globaler Faktor", "M2 Faktor je Kalendermonat", "M5 Faktor Tag/Nacht x Kalendermonat",
             "M9 Poisson: Aqua/Terra x Tag/Nacht + Monat", "M10 wie M9 + Region"]:
    for s in ["Sommer", "Rest"]:
        mk = (stable.season == s).values
        sub.append(dict(method=name, season=s, **score(stable[mk], preds_cv[name][mk])))
out["by_season"] = sub

# --- Rang-Weg: Klassen aus der jeweils eigenen Klimatologie ---------------------------
def rank_way(d, xcol, label, qsrc=None):
    q = terciles(d if qsrc is None else qsrc, xcol)
    cls = classify(d, xcol, q)
    return dict(variant=label, class_acc=float((cls == d.cls_true.values).mean()),
                kappa=float(cohen_kappa_score(cls, d.cls_true.values)))


rk = [rank_way(stable, "x", "MODIS (Aqua+Terra) Anzahl, eigene Terzile 2012-2021"),
      rank_way(stable, "xA", "nur Aqua Anzahl, eigene Terzile 2012-2021"),
      rank_way(stable, "xT", "nur Terra Anzahl, eigene Terzile 2012-2021"),
      rank_way(stable, "frp_x", "MODIS FRP-Summe, eigene Terzile 2012-2021"),
      rank_way(drift, "x", "Driftjahre 2022-2026: MODIS Anzahl, Terzile aus 2012-2021", stable),
      rank_way(W, "x", "alle Jahre 2012-2026: MODIS Anzahl, eigene Terzile")]
# Obergrenze: wie gut stimmt VIIRS mit sich selbst ueberein, wenn man FRP statt Anzahl nimmt?
rk.append(rank_way(stable, "frp_true", "Referenz: VIIRS FRP-Summe gegen VIIRS Anzahl (gleicher Sensor)"))
out["rank_way"] = rk
# Binaere Variante: ueber / unter Median
def median_way(d, xcol):
    a = d[xcol].values > d[["r", "m"]].merge(d.groupby(["r", "m"])[xcol].median().rename("q"), left_on=["r", "m"], right_index=True).q.values
    b = d.y_true.values > d[["r", "m"]].merge(d.groupby(["r", "m"]).y_true.median().rename("q"), left_on=["r", "m"], right_index=True).q.values
    return dict(acc=float((a == b).mean()), kappa=float(cohen_kappa_score(a, b)))
out["median_way"] = {"MODIS Anzahl": median_way(stable, "x"), "MODIS FRP": median_way(stable, "frp_x")}

# --- FRP: braucht es eine Umrechnung? -------------------------------------------------
def frp_score(d, p):
    le = np.abs(np.log((p + 10) / (d.frp_true.values + 10)))
    return dict(factor_err=float(np.exp(np.median(le))), bias=float(p.sum() / d.frp_true.sum()),
                r2_log=float(np.corrcoef(np.log1p(p), np.log1p(d.frp_true))[0, 1] ** 2))
fr = []
for label, col in [("Aqua FRP roh", "frp_xA"), ("Aqua+Terra FRP roh", "frp_x")]:
    fr.append(dict(variant=label, period="2012-2021", **frp_score(stable, stable[col].values.astype(float))))
    fr.append(dict(variant=label, period="2022-2026", **frp_score(drift, drift[col].values.astype(float))))
k = stable.frp_true.sum() / stable.frp_x.sum()
fr.append(dict(variant=f"Aqua+Terra FRP x {k:.2f}", period="2012-2021", **frp_score(stable, k * stable.frp_x.values)))
fr.append(dict(variant=f"Aqua+Terra FRP x {k:.2f}", period="2022-2026", **frp_score(drift, k * drift.frp_x.values)))
out["frp"] = fr

# Streudiagramm-Daten fuer den Report: wahr gegen vorhergesagt (CV), drei Kandidaten
sc = {}
for name in ["M1 ein globaler Faktor", "M9 Poisson: Aqua/Terra x Tag/Nacht + Monat"]:
    sc[name] = dict(true=stable.y_true.tolist(), pred=[round(float(v), 2) for v in preds_cv[name]])
out["scatter"] = sc
# Koeffizienten des empfohlenen Modells (auf allen stabilen Jahren)
X = pd.DataFrame({c0: np.log1p(stable[c0]) for c0 in ["n_Aqua_D", "n_Aqua_N", "n_Terra_D", "n_Terra_N"]})
X = sm.add_constant(X.join(pd.get_dummies(stable.m.astype(str), prefix="m", drop_first=True, dtype=float)))
res = sm.GLM(stable.y_true, X, family=sm.families.Poisson()).fit()
out["m9_coef"] = {k: float(v) for k, v in res.params.items()}
for nm in ["M13 additiv: Gewicht je Satellit x Tag/Nacht", "M14 additiv: Gewicht je Tag/Nacht x FRP-Klasse"]:
    f = CAND[nm]; run(f, stable, stable)
    out.setdefault("additive_coef", {})[nm] = {k: float(v) for k, v in f.coef.items()}
# Faktoren der einfachen Wege (auf allen stabilen Jahren), zum Nachrechnen
out["factors"] = dict(
    global_modis=float(stable.y_true.sum() / stable.x.sum()),
    global_aqua=float(stable.y_true.sum() / stable.xA.sum()),
    global_terra=float(stable.y_true.sum() / stable.xT.sum()),
    day=float(stable.n_SNPP_D.sum() / stable.xD.sum()), night=float(stable.n_SNPP_N.sum() / stable.xN.sum()),
    by_region={r: float(g.y_true.sum() / g.x.sum()) for r, g in stable.groupby("r")})
save("strategies", out)
print(out["additive_coef"]); print(out["factors"])

pd.set_option("display.width", 250)
t = pd.DataFrame(rows)
print(t[["method"] + [c0 for c0 in t.columns if c0.startswith("cv_")]].round(3).to_string(index=False))
print(t[["method"] + [c0 for c0 in t.columns if c0.startswith("drift_")]].round(3).to_string(index=False))
print(pd.DataFrame(sub).round(3).to_string(index=False))
print(pd.DataFrame(rk).round(3).to_string(index=False))
print(out["median_way"])
print(pd.DataFrame(fr).round(3).to_string(index=False))
print({k: round(v, 3) for k, v in out["m9_coef"].items()})
