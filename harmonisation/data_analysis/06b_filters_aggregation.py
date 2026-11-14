"""Schritt 6b: Zwei Stellschrauben fuer den einfachen Regions-Faktor (M3 aus Schritt 6).

  a) Filter: Wie veraendern type-Filter und Konfidenz-Filter die Uebereinstimmung?
  b) Aggregation: Wie stark sinkt der Fehler, wenn man zeitlich/raeumlich groeber wird?

Methode ueberall: Faktor je Region (Summe VIIRS / Summe MODIS), Kreuzvalidierung
"ein Jahr auslassen" ueber 2012-2021, Ziel = SNPP-Anzahl mit demselben Filter.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from common import IBERIA, con, save

c = con()
MONTHS = [(y, m) for y in range(2012, 2022) for m in range(1, 13) if (y, m) >= (2012, 2)]


REGS = None


def build(where):
    raw = c.execute(f"""SELECT region_id r, year(acq_date) y, month(acq_date) m,
            COUNT(*) FILTER (sensor='MODIS') x, COUNT(*) FILTER (sat='SNPP') yv
        FROM '{IBERIA}' WHERE source='archive' AND region_id IS NOT NULL
          AND acq_date BETWEEN '2012-02-01' AND '2021-12-31' AND {where} GROUP BY ALL""").df()
    global REGS
    if REGS is None:        # Regionen einmal mit dem Basisfilter festlegen, damit alle Filter vergleichbar sind
        REGS = sorted(raw.groupby("r").yv.sum().loc[lambda s: s >= 1500].index)
    regs = REGS
    idx = pd.MultiIndex.from_tuples([(r, y, m) for r in regs for y, m in MONTHS], names=["r", "y", "m"])
    return raw.set_index(["r", "y", "m"]).reindex(idx).fillna(0).reset_index()


def cv_region_factor(W):
    p = np.zeros(len(W))
    for yr in W.y.unique():
        tr, te = W[W.y != yr], W[W.y == yr]
        g = tr.groupby("r")[["x", "yv"]].sum()
        k = (g.yv / g.x.where(g.x >= 30)).fillna(tr.yv.sum() / tr.x.sum())
        p[te.index] = te.r.map(k).values * te.x.values
    return p


def score(true, pred, keys=None, W=None):
    le = np.abs(np.log((pred + 1) / (true + 1)))
    r = dict(factor_err=float(np.exp(np.median(le))), factor_err_p90=float(np.exp(np.quantile(le, .9))),
             r2_log=float(np.corrcoef(np.log1p(pred), np.log1p(true))[0, 1] ** 2))
    if W is not None:
        q = W.groupby(["r", "m"]).yv.quantile([1 / 3, 2 / 3]).unstack()
        t = W[["r", "m"]].merge(q, left_on=["r", "m"], right_index=True)
        cls = lambda v: np.where(v <= t.iloc[:, 2].values, 0, np.where(v <= t.iloc[:, 3].values, 1, 2))
        r["class_acc"] = float((cls(pred) == cls(true)).mean())
        r["kappa"] = float(cohen_kappa_score(cls(pred), cls(true)))
    return r


out = {}
# a) Filter ---------------------------------------------------------------------
LOWCONF = "NOT ((sensor='MODIS' AND TRY_CAST(confidence AS INT) < 30) OR (sensor='VIIRS' AND confidence='l'))"
HIGHCONF = "((sensor='MODIS' AND TRY_CAST(confidence AS INT) >= 80) OR (sensor='VIIRS' AND confidence='h'))"
FILTERS = {
    "kein Filter (alle type, alle Konfidenzen)": "TRUE",
    "nur type = 0": "type = 0",
    "type = 0 und Konfidenz nicht 'low'": f"type = 0 AND {LOWCONF}",
    "type = 0 und nur Konfidenz 'high'": f"type = 0 AND {HIGHCONF}",
    "type = 0, nur Tag": "type = 0 AND daynight = 'D'",
    "type = 0, nur Nacht": "type = 0 AND daynight = 'N'",
}
rows = []
build("type = 0")
for name, where in FILTERS.items():
    W = build(where)
    p = cv_region_factor(W)
    rows.append(dict(filter=name, n_modis=int(W.x.sum()), n_viirs=int(W.yv.sum()),
                     ratio=float(W.yv.sum() / W.x.sum()), **score(W.yv.values, p, W=W)))
out["filters"] = rows

# b) Aggregation -------------------------------------------------------------------
W = build("type = 0")
W["p"] = cv_region_factor(W)
W["q"] = (W.m - 1) // 3 + 1
W["country"] = W.r.str[:2]
levels = {
    "NUTS-2 x Monat": ["r", "y", "m"], "NUTS-2 x Quartal": ["r", "y", "q"], "NUTS-2 x Jahr": ["r", "y"],
    "Land x Monat": ["country", "y", "m"], "Land x Jahr": ["country", "y"],
    "Iberien gesamt x Monat": ["y", "m"], "Iberien gesamt x Jahr": ["y"],
}
out["aggregation"] = [dict(level=k, n=int(len(g)), **score(g.yv.values, g.p.values))
                      for k, cols in levels.items() for g in [W.groupby(cols)[["yv", "p"]].sum()]]
save("filters_aggregation", out)
pd.set_option("display.width", 220)
print(pd.DataFrame(out["filters"]).round(3).to_string(index=False))
print(pd.DataFrame(out["aggregation"]).round(3).to_string(index=False))
