"""Exploratory data analysis for the no-weather forecast models.

Reads only data/harmonised/. Writes
  forecast/docs/data_analysis.html          the report (figures embedded)
  forecast/docs/data_analysis_results.json  all numbers shown in the report

Run from La-Brasa/forecast:  .venv/bin/python analysis/data_analysis.py
Interpretation texts live in analysis/data_analysis_text.py (written after looking at the numbers).
Feature analyses (sections 8-11) use the training years 2012-2021 only, so that model choices
made from this report do not look at the test years 2022-2026.
"""
from __future__ import annotations

import base64
import html
import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
FORECAST = HERE.parent
REPO = FORECAST.parent
HARM = REPO / "data" / "harmonised"
DOCS = FORECAST / "docs"
TRAIN_END = pd.Timestamp("2021-12-31")
VIIRS_START = pd.Timestamp("2012-01-20")
N20, N21 = pd.Timestamp("2018-04-01"), pd.Timestamp("2023-03-01")

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})
C1, C2, C3, C4 = "#2b6cb0", "#c05621", "#2f855a", "#805ad5"

R: dict = {}        # results for JSON
FIG: dict = {}      # section -> list of base64 PNGs
TAB: dict = {}      # section -> list of HTML tables


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def add_fig(section: str, fig) -> None:
    FIG.setdefault(section, []).append(fig_to_b64(fig))


def add_table(section: str, df: pd.DataFrame, caption: str, fmt: dict | None = None) -> None:
    fmt = fmt or {}
    d = df.copy()
    for col, f in fmt.items():
        if col in d.columns:
            d[col] = d[col].map(lambda v, f=f: "" if pd.isna(v) else f.format(v))
    TAB.setdefault(section, []).append(
        f"<figure class='tbl'><figcaption>{html.escape(caption)}</figcaption>"
        + d.to_html(index=False, border=0, classes="t", escape=True) + "</figure>")


def auc(y: np.ndarray, s: np.ndarray) -> float:
    ok = ~np.isnan(s)
    y, s = y[ok], s[ok]
    pos = y == 1
    if pos.sum() == 0 or (~pos).sum() == 0:
        return float("nan")
    ranks = pd.Series(s).rank().to_numpy()
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))


def pr_auc(y: np.ndarray, s: np.ndarray) -> float:
    ok = ~np.isnan(s)
    y, s = y[ok], s[ok]
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    precision = tp / np.arange(1, len(y) + 1)
    return float((precision * y).sum() / max(y.sum(), 1))  # average precision


# ---------------------------------------------------------------------------------------------
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_parquet(HARM / "activity_daily_harmonised.parquet")
    d["date"] = pd.to_datetime(d["date"])
    ds = pd.read_parquet(HARM / "day_status.parquet")
    ds["date"] = pd.to_datetime(ds["date"])
    d = d.merge(ds[["date", "snpp_operating", "is_provisional"]], on="date", how="left")
    d = d.sort_values(["region_id", "date"]).reset_index(drop=True)
    d["year"] = d["date"].dt.year
    d["month"] = d["date"].dt.month
    d["doy"] = d["date"].dt.day_of_year.clip(upper=365)
    d["weekday"] = d["date"].dt.weekday
    d["measured"] = (d["basis_count"] == "viirs_measured") & d["is_complete_day"] & ~d["possible_gap"]
    d["big"] = d["big_fire_day"].astype("float")
    d.loc[~d["measured"], "big"] = np.nan
    d["fire_snpp"] = np.where(d["measured"] & d["n_snpp"].notna(), (d["n_snpp"] > 0).astype(float), np.nan)
    d["fire_any"] = np.where(d["measured"], (d["n_harm"] > 0).astype(float), np.nan)
    d["logfrp"] = np.where(d["measured"], np.log1p(d["frp_harm"].fillna(0)), np.nan)
    d["train"] = (d["date"] >= VIIRS_START) & (d["date"] <= TRAIN_END)
    d["test"] = d["date"] > TRAIN_END
    return d, ds


def climatology(d: pd.DataFrame, col: str, window: int = 7) -> pd.Series:
    """Region x day-of-year mean from training years, circularly smoothed; mapped onto all rows."""
    t = d[d["train"] & d[col].notna()].groupby(["region_id", "doy"])[col].mean().unstack()
    t = t.reindex(columns=range(1, 366)).fillna(0)
    k = np.ones(2 * window + 1) / (2 * window + 1)
    sm = np.array([np.convolve(np.r_[r[-window:], r, r[:window]], k, mode="valid") for r in t.to_numpy()])
    s = pd.DataFrame(sm, index=t.index, columns=t.columns).stack().rename(f"clim_{col}")
    return d[["region_id", "doy"]].join(s, on=["region_id", "doy"])[f"clim_{col}"]


# ---------------------------------------------------------------------------------------------
def s1_overview(d, ds):
    m = d[d["measured"]]
    R["s1"] = dict(
        rows_total=int(len(d)), regions=int(d["region_id"].nunique()),
        period=[str(d["date"].min().date()), str(d["date"].max().date())],
        measured_rows=int(len(m)), measured_period=[str(m["date"].min().date()), str(m["date"].max().date())],
        excluded_possible_gap=int((d["basis_count"].eq("viirs_measured") & d["possible_gap"]).sum()),
        excluded_incomplete=int((d["basis_count"].eq("viirs_measured") & ~d["is_complete_day"]).sum()),
        provisional_days=int(ds["is_provisional"].sum()),
        snpp_missing_on_measured=int(m["n_snpp"].isna().sum()),
        train_rows=int((m["train"]).sum()), test_rows=int((m["test"]).sum()),
    )
    basis = d.groupby("basis_count").agg(rows=("date", "size"), first=("date", "min"), last=("date", "max")).reset_index()
    basis["first"] = basis["first"].dt.date.astype(str)
    basis["last"] = basis["last"].dt.date.astype(str)
    add_table("s1", basis, "Zeilen je Datenbasis (activity_daily_harmonised)")


def s2_targets(d):
    m = d[d["measured"]]
    reg = m.groupby(["region_id", "region_name"]).agg(
        days=("big", "size"), fire_snpp=("fire_snpp", "mean"), fire_any=("fire_any", "mean"),
        big_rate=("big", "mean"), big_days=("big", "sum"), frp_total=("frp_harm", "sum")).reset_index()
    big_frp = m[m["big"] == 1].groupby("region_id")["frp_harm"].sum()
    reg["frp_share_on_big_days"] = reg["region_id"].map(big_frp) / reg["frp_total"]
    reg["big_days_train"] = reg["region_id"].map(m[m["train"]].groupby("region_id")["big"].sum())
    reg = reg.sort_values("big_days", ascending=False)
    R["s2"] = dict(
        fire_snpp_rate=float(m["fire_snpp"].mean()), fire_any_rate=float(m["fire_any"].mean()),
        big_rate=float(m["big"].mean()), big_days=int(m["big"].sum()),
        big_days_train=int(m.loc[m["train"], "big"].sum()), big_days_test=int(m.loc[m["test"], "big"].sum()),
        frp_share_on_big_days=float(m.loc[m["big"] == 1, "frp_harm"].sum() / m["frp_harm"].sum()),
        regions_lt30_train=reg.loc[reg["big_days_train"] < 30, "region_id"].tolist(),
        per_region=reg.drop(columns=["frp_total"]).round(4).to_dict("records"),
    )
    add_table("s2", reg.drop(columns=["frp_total"]),
              "Ziele je Region (gemessene Tage 2012-01-20 bis heute), sortiert nach Großfeuer-Tagen",
              {"fire_snpp": "{:.3f}", "fire_any": "{:.3f}", "big_rate": "{:.4f}", "big_days": "{:.0f}",
               "frp_share_on_big_days": "{:.2f}", "big_days_train": "{:.0f}"})
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.bar(reg["region_id"], reg["big_days"], color=C2)
    ax.set_ylabel("Großfeuer-Tage"); ax.set_title("Großfeuer-Tage (FRP ≥ 100 MW) je Region, 2012–2026")
    plt.xticks(rotation=60)
    add_fig("s2", fig)


def s3_satellites(d):
    m = d[d["measured"]]
    y = m.groupby("year").agg(fire_any=("fire_any", "mean"), fire_snpp=("fire_snpp", "mean"), big=("big", "mean"),
                              mean_logfrp=("logfrp", "mean")).reset_index()
    R["s3"] = y.round(4).to_dict("records")
    add_table("s3", y, "Jahresraten der Ziele (Anteil Region-Tage)",
              {"fire_any": "{:.3f}", "fire_snpp": "{:.3f}", "big": "{:.4f}", "mean_logfrp": "{:.3f}"})
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(y["year"], y["fire_any"], "o-", color=C1, label="n_harm > 0 (alle VIIRS)")
    ax.plot(y["year"], y["fire_snpp"], "o-", color=C3, label="n_snpp > 0 (nur SNPP)")
    ax2 = ax.twinx()
    ax2.plot(y["year"], y["big"], "s--", color=C2, label="big_fire_day (rechts)")
    ax2.set_ylabel("Großfeuer-Rate"); ax2.grid(False)
    for t, lab in [(2018.25, "NOAA-20"), (2023.17, "NOAA-21")]:
        ax.axvline(t, color="grey", ls=":"); ax.text(t, ax.get_ylim()[1] * 0.98, lab, fontsize=7, ha="center")
    ax.set_ylabel("Anteil Feuertage"); ax.set_title("Satelliten-Effekt: Feuertage je Definition")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="lower left")
    add_fig("s3", fig)


def s4_distributions(d):
    m = d[d["measured"]]
    frp = m["frp_harm"].fillna(0)
    pos = frp[frp > 0]
    q = pos.quantile([0.5, 0.75, 0.9, 0.95, 0.99, 0.999])
    s = np.sort(frp.to_numpy())[::-1]
    cum = np.cumsum(s) / s.sum()
    top = {p: float(cum[int(len(s) * p) - 1]) for p in (0.001, 0.01, 0.05)}
    nz = m["n_harm"].fillna(0)
    R["s4"] = dict(share_zero_frp=float((frp == 0).mean()), frp_quantiles_on_fire_days={str(k): float(v) for k, v in q.items()},
                   frp_share_top_days=top, n_harm_mean=float(nz.mean()), n_harm_var=float(nz.var()),
                   dispersion_index=float(nz.var() / nz.mean()), frp_max=float(frp.max()))
    qt = pd.DataFrame({"Quantil (Tage mit FRP > 0)": [f"{k:.1%}" for k in q.index], "FRP-Summe MW": q.values})
    add_table("s4", qt, "Verteilung der Tages-FRP (Region × Tag) an Tagen mit Feuer", {"FRP-Summe MW": "{:.1f}"})
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
    axes[0].hist(np.log10(pos), bins=60, color=C1)
    axes[0].axvline(2, color=C2, ls="--"); axes[0].text(2.05, axes[0].get_ylim()[1] * 0.9, "100 MW", color=C2, fontsize=7)
    axes[0].set_xlabel("log10(FRP-Summe MW)"); axes[0].set_title("Tages-FRP an Feuertagen")
    ccdf_x = np.sort(pos.to_numpy())
    ccdf_y = 1 - np.arange(len(ccdf_x)) / len(ccdf_x)
    axes[1].loglog(ccdf_x, ccdf_y, color=C2)
    axes[1].set_xlabel("FRP-Summe MW"); axes[1].set_ylabel("P(X ≥ x)"); axes[1].set_title("Rand der Verteilung (log-log)")
    axes[2].plot(np.arange(1, len(cum) + 1) / len(cum) * 100, cum * 100, color=C3)
    axes[2].set_xscale("log"); axes[2].set_xlabel("stärkste x % der Region-Tage"); axes[2].set_ylabel("% der gesamten FRP")
    axes[2].set_title("Konzentration der FRP")
    add_fig("s4", fig)


def s5_seasonality(d):
    m = d[d["measured"]]
    hm = m.groupby(["region_id", "month"])["big"].mean().unstack()
    order = m.groupby("region_id")["big"].sum().sort_values(ascending=False).index
    hm = hm.loc[order]
    peak = hm.idxmax(axis=1)
    summer = m[m["month"].between(6, 10)]["big"].sum() / m["big"].sum()
    R["s5"] = dict(share_big_jun_oct=float(summer), peak_month_per_region=peak.to_dict(),
                   regions_peak_outside_jun_oct=[r for r, p in peak.items() if not 6 <= p <= 10])
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(hm.to_numpy(), aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(12), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_yticks(range(len(hm)), hm.index); ax.grid(False)
    plt.colorbar(im, ax=ax, label="Anteil Großfeuer-Tage")
    ax.set_title("Saison: Großfeuer-Rate je Region und Monat")
    add_fig("s5", fig)
    pooled = m.groupby("doy")[["fire_snpp", "big"]].mean().rolling(15, center=True, min_periods=1).mean()
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(pooled.index, pooled["fire_snpp"], color=C3, label="Feuertag (SNPP)")
    ax2 = ax.twinx(); ax2.plot(pooled.index, pooled["big"], color=C2, label="Großfeuer-Tag (rechts)"); ax2.grid(False)
    ax.set_xlabel("Tag im Jahr"); ax.set_title("Jahresverlauf, alle Regionen, ±7 Tage geglättet")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    add_fig("s5", fig)


def s6_interannual(d):
    m = d[d["measured"] & (d["year"] <= d.loc[d["measured"], "year"].max())]
    yc = m.groupby(["year", "country"])["big"].sum().unstack().fillna(0)
    tot = yc.sum(axis=1)
    cv = float(tot[tot.index < tot.index.max()].std() / tot[tot.index < tot.index.max()].mean())
    corr = m.groupby(["year", "country"])["logfrp"].sum().unstack().corr()
    R["s6"] = dict(big_days_per_year=tot.astype(int).to_dict(), cv_full_years=cv,
                   top_years=tot.sort_values(ascending=False).head(4).astype(int).to_dict(),
                   country_corr_annual=corr.round(2).to_dict())
    fig, ax = plt.subplots(figsize=(8, 3.2))
    bottom = np.zeros(len(yc))
    for c, col in zip(yc.columns, [C2, C3, C1]):
        ax.bar(yc.index, yc[c], bottom=bottom, label=c, color=col); bottom += yc[c].to_numpy()
    ax.axvline(2021.5, color="black", ls="--"); ax.text(2021.6, bottom.max() * 0.95, "Test →", fontsize=7)
    ax.set_title("Großfeuer-Tage je Jahr und Land (2026 bis 13.11.)"); ax.legend(fontsize=7)
    add_fig("s6", fig)


def lag_series(d, col, lag):
    return d.groupby("region_id")[col].shift(lag)


def s7_persistence(d):
    m = d.copy()
    m["clim_big"] = climatology(m, "big")
    m["clim_logfrp"] = climatology(m, "logfrp")
    m["anom"] = m["logfrp"] - m["clim_logfrp"]
    rows = []
    for lag in [1, 2, 3, 5, 7, 10, 14, 21, 30]:
        prev = lag_series(m, "big", lag)
        sel = m["train"] & m["big"].notna() & (prev == 1)
        p_cond = m.loc[sel, "big"].mean()
        p_clim = m.loc[sel, "clim_big"].mean()
        a = m[["anom"]].assign(prev=lag_series(m, "anom", lag))
        a = a[m["train"]].dropna()
        rows.append(dict(lag_days=lag, p_big_given_big_lag=p_cond, p_clim_same_days=p_clim,
                         lift_vs_season=p_cond / p_clim, acf_logfrp_anomaly=float(np.corrcoef(a["anom"], a["prev"])[0, 1])))
    pt = pd.DataFrame(rows)
    # episodes of consecutive big-fire days
    tr = m[m["train"] & m["big"].notna()]
    runs = []
    for _, g in tr.groupby("region_id"):
        b = g["big"].to_numpy()
        n = 0
        for v in b:
            if v == 1:
                n += 1
            elif n:
                runs.append(n); n = 0
        if n:
            runs.append(n)
    runs = pd.Series(runs)
    R["s7"] = dict(table=pt.round(4).to_dict("records"), base_rate_train=float(tr["big"].mean()),
                   episodes=int(len(runs)), episode_len_mean=float(runs.mean()),
                   share_single_day=float((runs == 1).mean()), episode_len_p90=float(runs.quantile(0.9)))
    add_table("s7", pt, "Persistenz (Training): P(Großfeuer heute | Großfeuer vor L Tagen) gegenüber der Saison",
              {"p_big_given_big_lag": "{:.3f}", "p_clim_same_days": "{:.3f}", "lift_vs_season": "{:.2f}",
               "acf_logfrp_anomaly": "{:.3f}"})
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    axes[0].plot(pt["lag_days"], pt["lift_vs_season"], "o-", color=C2)
    axes[0].axhline(1, color="grey", ls=":"); axes[0].set_xlabel("Abstand L (Tage)")
    axes[0].set_ylabel("× Saisonerwartung"); axes[0].set_title("Großfeuer folgt auf Großfeuer: Faktor über Saison")
    axes[1].plot(pt["lag_days"], pt["acf_logfrp_anomaly"], "o-", color=C1)
    axes[1].set_xlabel("Abstand L (Tage)"); axes[1].set_ylabel("Korrelation")
    axes[1].set_title("Autokorrelation der log-FRP-Abweichung von der Saison")
    add_fig("s7", fig)
    fig, ax = plt.subplots(figsize=(5, 3))
    vc = runs.clip(upper=10).value_counts().sort_index()
    ax.bar(vc.index.astype(int), vc.values, color=C4); ax.set_xticks(range(1, 11), [*map(str, range(1, 10)), "10+"])
    ax.set_xlabel("Länge in Tagen"); ax.set_ylabel("Episoden"); ax.set_title("Länge von Großfeuer-Episoden (Training)")
    add_fig("s7", fig)
    return m


def region_centroids():
    h = pd.read_parquet(HARM / "hotspots_harmonised.parquet", columns=["region_id", "latitude", "longitude", "sensor", "obs_date"])
    h = h[(h["sensor"] == "VIIRS") & h["region_id"].notna() & (pd.to_datetime(h["obs_date"]) <= TRAIN_END)]
    return h.groupby("region_id")[["latitude", "longitude"]].mean()


def s8_spatial(m):
    tr = m[m["train"] & m["measured"]]
    piv = tr.pivot(index="date", columns="region_id", values="anom").dropna()
    corr = piv.corr()
    X = (piv - piv.mean()) / piv.std()
    ev = np.linalg.eigvalsh(np.cov(X.T.to_numpy()))[::-1]
    expl = ev / ev.sum()
    w, v = np.linalg.eigh(np.cov(X.T.to_numpy()))
    pc1 = pd.Series(v[:, -1], index=piv.columns)
    pc1 = pc1 * np.sign(pc1.sum())
    pc2 = pd.Series(v[:, -2], index=piv.columns)
    # nearest neighbours by centroid
    cen = region_centroids()
    lat, lon = np.radians(cen["latitude"].to_numpy()), np.radians(cen["longitude"].to_numpy())
    dist = np.arccos(np.clip(np.sin(lat[:, None]) * np.sin(lat) + np.cos(lat[:, None]) * np.cos(lat) * np.cos(lon[:, None] - lon), -1, 1)) * 6371
    np.fill_diagonal(dist, np.inf)
    nn = {r: [cen.index[j] for j in np.argsort(dist[i])[:3]] for i, r in enumerate(cen.index)}
    bigp = tr.pivot(index="date", columns="region_id", values="big")
    rows = []
    for lag in (0, 1):
        num = den = 0.0
        for r, ns in nn.items():
            if r not in bigp:
                continue
            nb = bigp[[n for n in ns if n in bigp]].max(axis=1).shift(lag)
            sel = nb == 1
            num += bigp.loc[sel, r].sum(); den += sel.sum()
        rows.append(dict(lag_days=lag, p_big_given_neighbour_big=num / den))
    base = float(tr["big"].mean())
    R["s8"] = dict(pc_explained=[float(x) for x in expl[:8]], pc1_loadings=pc1.round(3).to_dict(),
                   pc2_loadings=pc2.round(3).to_dict(), mean_pairwise_corr=float(corr.where(~np.eye(len(corr), dtype=bool)).stack().mean()),
                   neighbours=nn, neighbour_table=rows, base_rate=base)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.3, 1]})
    im = axes[0].imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    axes[0].set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=6)
    axes[0].set_yticks(range(len(corr)), corr.index, fontsize=6); axes[0].grid(False)
    plt.colorbar(im, ax=axes[0], fraction=0.04); axes[0].set_title("Korrelation der täglichen log-FRP-Abweichung")
    axes[1].bar(range(1, 9), expl[:8] * 100, color=C1)
    axes[1].plot(range(1, 9), np.cumsum(expl[:8]) * 100, "o-", color=C2, label="kumuliert")
    axes[1].set_xlabel("Hauptkomponente"); axes[1].set_ylabel("% erklärte Varianz"); axes[1].legend(fontsize=7)
    axes[1].set_title("PCA über 23 Regionen (Training)")
    add_fig("s8", fig)
    nt = pd.DataFrame(rows); nt["base_rate"] = base; nt["lift"] = nt["p_big_given_neighbour_big"] / base
    add_table("s8", nt, "Großfeuer in mindestens einer der 3 nächsten Regionen (gleicher Tag / Vortag)",
              {"p_big_given_neighbour_big": "{:.3f}", "base_rate": "{:.4f}", "lift": "{:.1f}"})
    return nn


def build_features(m, nn, lead):
    """Candidate no-weather features known at issue date t-lead for target day t."""
    f = pd.DataFrame(index=m.index)
    f["clim"] = m["clim_big"]
    g = m.groupby("region_id")
    sh = lambda col, k=lead: g[col].shift(k)
    f["big_last"] = sh("big")
    f["fire_last"] = sh("fire_snpp")
    f["logfrp_last"] = sh("logfrp")
    for w in (3, 7, 30):
        f[f"fire_frac{w}"] = g["fire_snpp"].transform(lambda s, w=w: s.shift(lead).rolling(w, min_periods=max(1, w // 2)).mean())
        f[f"logfrp_mean{w}"] = g["logfrp"].transform(lambda s, w=w: s.shift(lead).rolling(w, min_periods=max(1, w // 2)).mean())
    f["big_frac30"] = g["big"].transform(lambda s: s.shift(lead).rolling(30, min_periods=15).mean())
    f["anom_mean7"] = g["anom"].transform(lambda s: s.shift(lead).rolling(7, min_periods=4).mean())

    def days_since(s):
        out, last = np.full(len(s), np.nan), None
        for i, v in enumerate(s.to_numpy()):
            out[i] = np.nan if last is None else i - last
            if v == 1:
                last = i
        return pd.Series(out, index=s.index)
    f["days_since_fire"] = g["fire_snpp"].transform(days_since)
    f["days_since_fire"] = f.groupby(m["region_id"])["days_since_fire"].shift(lead) + lead
    f["days_since_big"] = g["big"].transform(days_since)
    f["days_since_big"] = f.groupby(m["region_id"])["days_since_big"].shift(lead) + lead
    lp = m.pivot(index="date", columns="region_id", values="logfrp")
    nbr = pd.DataFrame({r: lp[ns].mean(axis=1) for r, ns in nn.items()}).shift(lead)
    iberia = lp.mean(axis=1).shift(lead)
    key = pd.MultiIndex.from_arrays([m["date"], m["region_id"]])
    f["nbr_logfrp_last"] = nbr.stack().reindex(key).to_numpy()
    f["iberia_logfrp_last"] = iberia.reindex(m["date"]).to_numpy()
    f["weekday_target"] = m["weekday"]
    return f


def s9_features(m, nn):
    out = {}
    tables = []
    for lead in (1, 7):
        f = build_features(m, nn, lead)
        sel = m["train"] & m["big"].notna()
        y = m.loc[sel, "big"].to_numpy()
        rows = []
        for c in f.columns:
            if c == "weekday_target":
                continue
            s = f.loc[sel, c].to_numpy().astype(float)
            sgn = -1 if c.startswith("days_since") else 1
            rows.append(dict(feature=c, lead=lead, auc=auc(y, sgn * s), pr_auc=pr_auc(y, sgn * s),
                             spearman_with_target=float(pd.Series(s).rank().corr(pd.Series(y).rank())),
                             missing=float(np.isnan(s).mean())))
        t = pd.DataFrame(rows).sort_values("auc", ascending=False)
        out[lead] = t
        tables.append(t)
        if lead == 1:
            feats1 = f
    R["s9"] = {f"lead_{k}": v.round(4).to_dict("records") for k, v in out.items()}
    R["s9"]["base_rate_train"] = float(m.loc[m["train"], "big"].mean())
    both = out[1][["feature", "auc", "pr_auc"]].merge(out[7][["feature", "auc", "pr_auc"]], on="feature", suffixes=("_lead1", "_lead7"))
    add_table("s9", both, f"Einzelne Merkmale gegen Großfeuer-Tag (Training), AUC und PR-AUC; Grundrate PR-AUC = {R['s9']['base_rate_train']:.3f}",
              {"auc_lead1": "{:.3f}", "pr_auc_lead1": "{:.3f}", "auc_lead7": "{:.3f}", "pr_auc_lead7": "{:.3f}"})
    # decile lift curves for top features
    sel = m["train"] & m["big"].notna()
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
    for ax, c in zip(axes, ["logfrp_mean7", "days_since_big", "nbr_logfrp_last"]):
        s = feats1.loc[sel, c]
        yy = m.loc[sel, "big"]
        ok = s.notna()
        q = pd.qcut(s[ok].rank(method="first"), 10, labels=False)
        rate = yy[ok].groupby(q).mean()
        clim = m.loc[sel, "clim_big"][ok].groupby(q).mean()
        ax.plot(range(1, 11), rate.values, "o-", color=C2, label="beobachtet")
        ax.plot(range(1, 11), clim.values, "s--", color="grey", label="Saison erwartet")
        ax.set_xlabel(f"Dezil von {c}"); ax.set_title(f"{c}, Vorlauf 1"); ax.legend(fontsize=7)
    axes[0].set_ylabel("Großfeuer-Rate")
    add_fig("s9", fig)
    return feats1


def s10_weekday(m):
    tr = m[m["train"] & m["measured"]]
    # weekday effect relative to seasonal expectation, to remove season mixing
    w = tr.groupby("weekday").agg(big=("big", "mean"), clim=("clim_big", "mean"), fire=("fire_snpp", "mean"))
    w["ratio_big_vs_season"] = w["big"] / w["clim"]
    w["ratio_fire_vs_mean"] = w["fire"] / tr["fire_snpp"].mean()
    w.index = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    R["s10"] = w.round(4).reset_index(names="weekday").to_dict("records")
    add_table("s10", w.reset_index(names="Wochentag"), "Wochentag (Training): Rate gegenüber Saisonerwartung",
              {"big": "{:.4f}", "clim": "{:.4f}", "fire": "{:.3f}", "ratio_big_vs_season": "{:.2f}", "ratio_fire_vs_mean": "{:.2f}"})


def s11_feature_structure(m, feats1):
    sel = m["train"] & m["big"].notna()
    cols = [c for c in feats1.columns if c != "weekday_target"]
    X = feats1.loc[sel, cols].dropna()
    corr = X.rank().corr()  # Spearman = Pearson on ranks (no scipy needed)
    Z = (X - X.mean()) / X.std()
    ev = np.linalg.eigvalsh(np.cov(Z.T.to_numpy()))[::-1]
    expl = ev / ev.sum()
    high = [(a, b, float(corr.loc[a, b])) for i, a in enumerate(cols) for b in cols[i + 1:] if abs(corr.loc[a, b]) >= 0.8]
    # VIF via inverse correlation matrix (Pearson on standardised)
    pc = np.corrcoef(Z.T.to_numpy())
    vif = pd.Series(np.diag(np.linalg.pinv(pc)), index=cols)
    R["s11"] = dict(pc_explained=[float(x) for x in expl], n_components_90=int(np.searchsorted(np.cumsum(expl), 0.9) + 1),
                    high_corr_pairs=high, vif=vif.round(1).to_dict(), n_rows=int(len(X)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1.3, 1]})
    im = axes[0].imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    axes[0].set_xticks(range(len(cols)), cols, rotation=90, fontsize=6); axes[0].set_yticks(range(len(cols)), cols, fontsize=6)
    axes[0].grid(False); plt.colorbar(im, ax=axes[0], fraction=0.04); axes[0].set_title("Spearman-Korrelation der Merkmale (Vorlauf 1)")
    axes[1].bar(range(1, len(expl) + 1), expl * 100, color=C1)
    axes[1].plot(range(1, len(expl) + 1), np.cumsum(expl) * 100, "o-", color=C2)
    axes[1].axhline(90, color="grey", ls=":"); axes[1].set_xlabel("Hauptkomponente"); axes[1].set_ylabel("% Varianz")
    axes[1].set_title("PCA der Merkmale")
    add_fig("s11", fig)
    vt = vif.sort_values(ascending=False).reset_index(); vt.columns = ["feature", "VIF"]
    add_table("s11", vt, "Varianzinflationsfaktor (VIF > 10 = stark redundant)", {"VIF": "{:.1f}"})


def s12_shift(m):
    mm = m[m["measured"]]
    t = mm.groupby(mm["test"].map({False: "Training 2012–2021", True: "Test 2022–2026"})).agg(
        region_days=("big", "size"), big_rate=("big", "mean"), fire_snpp=("fire_snpp", "mean"),
        fire_any=("fire_any", "mean"), mean_logfrp=("logfrp", "mean")).reset_index(names="Zeitraum")
    reg = mm.groupby(["region_id", "test"])["big"].mean().unstack()
    reg.columns = ["train", "test"]
    reg["ratio"] = reg["test"] / reg["train"]
    clim_test = mm.loc[mm["test"], ["big", "clim_big"]].mean()
    R["s12"] = dict(table=t.round(4).to_dict("records"), clim_mean_on_test=float(clim_test["clim_big"]),
                    observed_on_test=float(clim_test["big"]), region_ratio=reg["ratio"].round(2).to_dict())
    add_table("s12", t, "Training gegen Test", {"big_rate": "{:.4f}", "fire_snpp": "{:.3f}", "fire_any": "{:.3f}", "mean_logfrp": "{:.3f}"})


# ---------------------------------------------------------------------------------------------
SECTIONS = [
    ("s1", "1. Datengrundlage"),
    ("s2", "2. Die Ziele: Feuertag und Großfeuer-Tag"),
    ("s3", "3. Satelliten-Effekt auf die Ziele"),
    ("s4", "4. Verteilung der Feuerstärke"),
    ("s5", "5. Saison"),
    ("s6", "6. Schwankung zwischen den Jahren"),
    ("s7", "7. Persistenz: Wie lange trägt „gestern“?"),
    ("s8", "8. Räumlicher Zusammenhang und PCA über Regionen"),
    ("s9", "9. Kandidaten-Merkmale ohne Wetter"),
    ("s10", "10. Wochentag (menschliche Zündungen)"),
    ("s11", "11. Redundanz der Merkmale: Korrelation, VIF, PCA"),
    ("s12", "12. Unterschied Training gegen Test"),
    ("s13", "13. Folgerungen für die Modelle"),
]

CSS = """
:root{--bg:#fff;--fg:#1a202c;--muted:#4a5568;--line:#e2e8f0;--card:#f7fafc;--accent:#2b6cb0}
@media (prefers-color-scheme:dark){:root{--bg:#171923;--fg:#e2e8f0;--muted:#a0aec0;--line:#2d3748;--card:#1f2533;--accent:#90cdf4}
 img{filter:none;background:#fff;border-radius:6px}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0}
main{max-width:1080px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:1.7rem;margin:.2rem 0}h2{font-size:1.25rem;margin-top:2.4rem;border-bottom:1px solid var(--line);padding-bottom:.3rem}
.lead{color:var(--muted)}nav{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;margin:16px 0}
nav a{color:var(--accent);text-decoration:none;display:inline-block;margin:2px 12px 2px 0;font-size:.9rem}
img{max-width:100%;height:auto;display:block;margin:12px 0}
.interp{background:var(--card);border-left:4px solid var(--accent);padding:8px 14px;margin:12px 0;border-radius:4px}
.interp p{margin:.4rem 0}figure.tbl{margin:12px 0;overflow-x:auto}figcaption{font-weight:600;font-size:.9rem;margin-bottom:4px}
table.t{border-collapse:collapse;font-size:.82rem;font-variant-numeric:tabular-nums}
table.t th,table.t td{border-bottom:1px solid var(--line);padding:3px 8px;text-align:right;white-space:nowrap}
table.t th{text-align:left;background:var(--card)}table.t td:first-child{text-align:left}
code{background:var(--card);padding:0 4px;border-radius:3px}
"""


def build_html(texts: dict) -> str:
    parts = [f"<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Datenanalyse Vorhersage</title><style>{CSS}</style></head><body><main>",
             "<h1>Datenanalyse für die Vorhersage ohne Wetter</h1>",
             f"<p class='lead'>{texts.get('intro', '')}</p><nav>"
             + "".join(f"<a href='#{k}'>{html.escape(t)}</a>" for k, t in SECTIONS) + "</nav>"]
    for key, title in SECTIONS:
        parts.append(f"<section id='{key}'><h2>{html.escape(title)}</h2>")
        if texts.get(f"{key}_method"):
            parts.append(f"<p>{texts[f'{key}_method']}</p>")
        for b in FIG.get(key, []):
            parts.append(f"<img alt='{html.escape(title)}' src='data:image/png;base64,{b}'>")
        parts.extend(TAB.get(key, []))
        body = texts.get(key, "<p><em>Deutung folgt.</em></p>")
        parts.append(f"<div class='interp'><strong>Deutung</strong>{body}</div></section>")
    parts.append("</main></body></html>")
    return "".join(parts)


def main() -> int:
    d, ds = load()
    s1_overview(d, ds)
    s2_targets(d)
    s3_satellites(d)
    s4_distributions(d)
    s5_seasonality(d)
    s6_interannual(d)
    m = s7_persistence(d)
    nn = s8_spatial(m)
    feats1 = s9_features(m, nn)
    s10_weekday(m)
    s11_feature_structure(m, feats1)
    s12_shift(m)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data_analysis_results.json").write_text(json.dumps(R, indent=1, ensure_ascii=False, default=str))
    try:
        sys.path.insert(0, str(HERE))
        from data_analysis_text import TEXTS  # noqa: E402
    except ImportError:
        TEXTS = {}
    (DOCS / "data_analysis.html").write_text(build_html(TEXTS))
    print(json.dumps(R, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
