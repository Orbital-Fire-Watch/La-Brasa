"""Baut den HTML-Bericht aus den Ergebnisdateien in results/.

Aufruf:  .venv/bin/python build_report.py [--fragment PFAD]
Ergebnis: harmonisierung_bericht.html (eigenstaendige Datei, ohne Internet lesbar)
--fragment schreibt zusaetzlich eine Variante ohne <html>/<head>-Geruest (zum Veroeffentlichen).

Alle Zahlen im Text kommen aus results/*.json, nichts ist von Hand eingetragen.
"""
import html
import json
import math
import sys

import report_text as T
from common import ROOT, load

R = {k: load(k) for k in ["columns", "matchup", "scales", "static", "strategies",
                          "filters_aggregation", "global", "series", "nuts"]}


# ---------- Zahlenformat (deutsch) ----------
def de(v, d=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "\u2212")


def pct(v, d=0):
    return de(100 * v, d) + "\u00a0%"


def esc(s):
    return html.escape(str(s), quote=True)


def tip(head, rows):
    return esc(json.dumps({"h": head, "r": rows}, ensure_ascii=False))


# ---------- SVG-Liniendiagramm ----------
def linechart(series, *, xlab, ylab, xticks, yticks, xfmt=lambda v: de(v, 0), yfmt=lambda v: de(v, 1),
              xlog=False, ylog=False, w=680, h=310, crosshair=True, bands=(), hrefs=(), diag=False,
              xtickfmt=None, ytickfmt=None, caption="", table_x="x"):
    L, Rm, Tm, B = 56, 18, 30, 44
    x0, x1 = xticks[0], xticks[-1]
    y0, y1 = yticks[0], yticks[-1]
    fx = (lambda v: math.log10(v)) if xlog else (lambda v: v)
    fy = (lambda v: math.log10(v)) if ylog else (lambda v: v)
    sx = lambda v: L + (fx(v) - fx(x0)) / (fx(x1) - fx(x0)) * (w - L - Rm)
    sy = lambda v: h - B - (fy(v) - fy(y0)) / (fy(y1) - fy(y0)) * (h - Tm - B)
    xtickfmt = xtickfmt or xfmt
    ytickfmt = ytickfmt or yfmt
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(caption)}">']
    o.append(f'<text x="0" y="14" class="axt">{esc(ylab)}</text>')
    for t in yticks:
        o.append(f'<line x1="{L}" x2="{w - Rm}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" class="grid"/>')
        o.append(f'<text x="{L - 8}" y="{sy(t) + 4:.1f}" text-anchor="end" class="tick">{ytickfmt(t)}</text>')
    o.append(f'<line x1="{L}" x2="{w - Rm}" y1="{h - B}" y2="{h - B}" class="axis"/>')
    for t in xticks:
        o.append(f'<text x="{sx(t):.1f}" y="{h - B + 17}" text-anchor="middle" class="tick">{xtickfmt(t)}</text>')
    o.append(f'<text x="{(L + w - Rm) / 2:.0f}" y="{h - 6}" text-anchor="middle" class="axt">{esc(xlab)}</text>')
    for yv, lab in hrefs:
        o.append(f'<line x1="{L}" x2="{w - Rm}" y1="{sy(yv):.1f}" y2="{sy(yv):.1f}" class="ref"/>')
        o.append(f'<text x="{w - Rm - 4}" y="{sy(yv) - 5:.1f}" text-anchor="end" class="tick">{esc(lab)}</text>')
    if diag:
        a, b = max(x0, y0), min(x1, y1)
        o.append(f'<line x1="{sx(a):.1f}" y1="{sy(a):.1f}" x2="{sx(b):.1f}" y2="{sy(b):.1f}" class="ref"/>')
        o.append(f'<text x="{sx(b) - 6:.1f}" y="{sy(b) + 16:.1f}" text-anchor="end" class="tick">gleiche FRP (1:1)</text>')
    for bd in bands:
        up = " ".join(f"{sx(x):.1f},{sy(hi):.1f}" for x, lo, hi in bd["pts"])
        dn = " ".join(f"{sx(x):.1f},{sy(lo):.1f}" for x, lo, hi in reversed(bd["pts"]))
        o.append(f'<polygon points="{up} {dn}" fill="var({bd["color"]})" opacity="0.14"/>')
    for s in series:
        pts = [(x, y) for x, y in s["pts"] if y is not None]
        if s.get("line", True):
            d = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(pts))
            o.append(f'<path d="{d}" fill="none" stroke="var({s["color"]})" stroke-width="2" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        if s.get("markers", True):
            for x, y in pts:
                o.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4" fill="var({s["color"]})" class="dot"/>')
        if s.get("endlabel"):
            x, y = pts[-1]
            o.append(f'<text x="{sx(x) - 6:.1f}" y="{sy(y) - 9:.1f}" text-anchor="end" class="lab">{esc(s["endlabel"])}</text>')
    tips = [s for s in series if s.get("tips", True)]
    if crosshair:
        xs = sorted({x for s in tips for x, y in s["pts"]})
        o.append(f'<line class="xh" x1="0" x2="0" y1="{Tm}" y2="{h - B}"/>')
        for i, x in enumerate(xs):
            lo = L if i == 0 else (sx(xs[i - 1]) + sx(x)) / 2
            hi = w - Rm if i == len(xs) - 1 else (sx(x) + sx(xs[i + 1])) / 2
            rows = [[s["name"], yfmt(dict(s["pts"])[x]), s["color"]] for s in tips
                    if dict(s["pts"]).get(x) is not None]
            o.append(f'<rect x="{lo:.1f}" y="{Tm}" width="{hi - lo:.1f}" height="{h - Tm - B}" fill="transparent" '
                     f'data-cx="{sx(x):.1f}" data-tip="{tip(xfmt(x), rows)}"/>')
    else:
        for s in tips:
            for x, y in s["pts"]:
                if y is None:
                    continue
                o.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="13" fill="transparent" '
                         f'data-tip="{tip(s["name"], [[xlab, xfmt(x), ""], [ylab, yfmt(y), s["color"]]])}"/>')
    o.append("</svg>")
    leg = ""
    named = [s for s in series if s.get("legend", True)]
    if len(named) >= 2:
        leg = '<div class="legend">' + "".join(
            f'<span><i class="key" style="background:var({s["color"]})"></i>{esc(s["name"])}</span>' for s in named) + "</div>"
    # Tabellenansicht
    xs = sorted({x for s in tips for x, y in s["pts"]})
    head = "".join(f"<th>{esc(s['name'])}</th>" for s in tips)
    body = "".join("<tr><td>" + xfmt(x) + "</td>" + "".join(
        f"<td>{yfmt(dict(s['pts'])[x]) if dict(s['pts']).get(x) is not None else '–'}</td>" for s in tips) + "</tr>" for x in xs)
    tab = (f'<details class="tv"><summary>Werte als Tabelle</summary><div class="scroll"><table class="num">'
           f"<thead><tr><th>{esc(table_x)}</th>{head}</tr></thead><tbody>{body}</tbody></table></div></details>")
    return f'<figure class="chart">{leg}<div class="scroll">{"".join(o)}</div><figcaption>{caption}</figcaption>{tab}</figure>'


def bars(rows, *, vmax, fmt=lambda v: de(v, 1), color="--s1", caption="", ref=None):
    """rows: [(Beschriftung, Wert, Zusatz fuer Tooltip)]"""
    o = ['<div class="bars">']
    for lab, v, extra in rows:
        o.append(f'<div class="brow" data-tip="{tip(lab, [["", fmt(v), color]] + extra)}"><span class="bl">{esc(lab)}</span>'
                 f'<span class="bt"><span class="bf" style="width:{100 * v / vmax:.1f}%;background:var({color})"></span>'
                 + (f'<span class="bref" style="left:{100 * ref / vmax:.1f}%"></span>' if ref else "")
                 + f'</span><span class="bv">{fmt(v)}</span></div>')
    o.append("</div>")
    return f'<figure class="chart">{"".join(o)}<figcaption>{caption}</figcaption></figure>'


def table(head, rows, cls="num", hl=()):
    th = "".join(f"<th>{h_}</th>" for h_ in head)
    tr = "".join(f'<tr{" class=hl" if i in hl else ""}>' + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                 for i, r in enumerate(rows))
    return f'<div class="scroll"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


# ---------- Zahlen einsammeln ----------
C, M, S, ST, G, SE, FA, SG, NU = (R["columns"], R["matchup"], R["scales"], R["static"], R["global"],
                                  R["series"], R["filters_aggregation"], R["strategies"], R["nuts"])
names = {r["region_id"]: r["name"] for r in NU["regions"] if r["region_id"]}
V = {}
bal, clu = M["balance"], M["cluster"]
V["n_ratio"] = de(bal["n_ratio_all"], 1)
V["frp_ratio"] = de(bal["frp_ratio_all"], 2)
V["seen"] = pct(clu["snpp_seen_by_aqua"])
V["seen_frp"] = pct(clu["snpp_frp_share_seen"])
V["aqua_seen"] = pct(clu["aqua_seen_by_snpp"])
V["unseen_det"] = pct(bal["snpp_det_share_in_unseen_clusters"])
fit = {(f["dn"], f["period"]): f for f in M["detect_fit"]}
for dn in "DN":
    f = fit[(dn, "alle")]
    V[f"a_{dn}"], V[f"b_{dn}"] = de(f["a"], 2), de(f["b"], 2)
    V[f"frp50_{dn}"], V[f"frp90_{dn}"] = de(f["frp50"], 0), de(f["frp90"], 0)
co = {c["dn"]: c for c in M["codetected"]}
for dn in "DN":
    V[f"co_frp_{dn}"] = de(co[dn]["frp_ratio_median"], 2)
    V[f"co_n_{dn}"] = de(co[dn]["n_ratio_median"], 1)
V["co_slope"] = de(co["alle"]["frp_loglog_slope"], 2)
V["co_n"] = de(co["alle"]["n"], 0)
V["dist50"], V["dist90"] = de(M["dist_quantiles_matched"]["p50"], 2), de(M["dist_quantiles_matched"]["p90"], 2)
dt = M["dt_quantiles_matched_h"]
V["dt50"], V["dt05"], V["dt95"] = de(dt["p50"], 1), de(dt["p05"], 1), de(dt["p95"], 1)
conf = {(c["sat"], c["dn"]): c for c in M["confirm"]}
V["aq_r3_D"], V["aq_r3_N"] = pct(conf[("Aqua", "D")]["r3"]), pct(conf[("Aqua", "N")]["r3"])
eff = {e["dn"]: e for e in ST["effect_on_ratio"]}
V["static_snpp_N"], V["static_snpp_D"] = pct(eff["N"]["static_share_snpp"]), pct(eff["D"]["static_share_snpp"])
V["static_aqua"] = pct(eff["alle"]["static_share_aqua"])
V["static_snpp"] = pct(eff["alle"]["static_share_snpp"])
V["ratio_unf_N"], V["ratio_t0_N"] = de(eff["N"]["ratio_unfiltered"], 1), de(eff["N"]["ratio_type0"], 1)
V["ratio_t0_D"] = de(eff["D"]["ratio_type0"], 1)
mb = {m["sat"]: m for m in ST["mask_best_both"]}
V["mask_recall"], V["mask_false"] = pct(mb["SNPP"]["recall"], 1), pct(mb["SNPP"]["false_removal"], 1)
V["mask_recall_modis"] = pct(mb["MODIS"]["recall"])
V["mask_cells"] = de(mb["SNPP"]["mask_cells"], 0)
V["mask_grid"] = de(ST["mask_best"]["grid"], 3)
V["mask_kmin"] = de(ST["mask_best"]["kmin"], 0)
nm = {(n["sat"], n["dn"]): n for n in ST["nrt_masked"]}
V["nrt_removed_N"] = pct(nm[("SNPP", "N")]["removed"])
V["arch_static_N"] = pct({(a["sat"], a["dn"]): a for a in ST["archive_static_same_season"]}[("SNPP", "N")]["static"])
mo = {(m["sat"], m["dn"]): m for m in C["multi_overpass"]}
V["multi_snpp_D"], V["multi_snpp_N"] = pct(mo[("SNPP", "D")]["share_det_in_multi"]), pct(mo[("SNPP", "N")]["share_det_in_multi"])
V["multi_aqua_D"], V["multi_aqua_N"] = pct(mo[("Aqua", "D")]["share_det_in_multi"]), pct(mo[("Aqua", "N")]["share_det_in_multi"])
fl = {(f["sat"], f["dn"]): f for f in C["frp_link"]}
V["phys_modis_lo"] = de(min(fl[k]["phys_r2"] for k in fl if k[0] != "SNPP"), 2)
V["phys_modis_hi"] = de(max(fl[k]["phys_r2"] for k in fl if k[0] != "SNPP"), 3)
V["phys_viirs_D"], V["phys_viirs_N"] = de(fl[("SNPP", "D")]["phys_r2"], 2), de(fl[("SNPP", "N")]["phys_r2"], 2)
vs = {v["dn"]: v for v in C["viirs_saturation"]}
V["sat367_D"], V["sat367_N"] = pct(vs["D"]["share_367"]), pct(vs["N"]["share_367"])
thr = {(t["sat"], t["dn"], t["g"]): t for t in C["frp_threshold"]}
V["thr_aqua_lo"], V["thr_aqua_hi"] = de(thr[("Aqua", "D", 1)]["p05"], 1), de(thr[("Aqua", "D", 12)]["p05"], 0)
V["thr_aqua_area_hi"] = de(thr[("Aqua", "D", 12)]["area"], 1)
V["thr_snpp_lo"], V["thr_snpp_hi"] = de(thr[("SNPP", "D", 1)]["p05"], 1), de(thr[("SNPP", "D", 12)]["p05"], 1)
V["thr_snpp_N_lo"] = de(thr[("SNPP", "N", 1)]["p05"], 2)
drift = {(d["sat"], d["dn"], d["y"]): d["lst"] for d in C["lst_drift"]}


def hhmm(v):
    v = v % 24
    return f"{int(v)}:{int(round((v - int(v)) * 60)):02d}"


V["aqua_2012"], V["aqua_2026"] = hhmm(drift[("Aqua", "D", 2012)]), hhmm(drift[("Aqua", "D", 2026)])
V["terra_2012"], V["terra_2026"] = hhmm(drift[("Terra", "D", 2012)]), hhmm(drift[("Terra", "D", 2026)])
V["snpp_2012"], V["snpp_2026"] = hhmm(drift[("SNPP", "D", 2012)]), hhmm(drift[("SNPP", "D", 2026)])
sc = {(s["grid"], s["time"]): s for s in S["scales"]}
V["r2_025_m"], V["r2_nuts_m"], V["r2_nuts_y"] = (de(sc[("0.25", "Monat")]["r2_log"], 2),
                                                de(sc[("nuts2", "Monat")]["r2_log"], 2), de(sc[("nuts2", "Jahr")]["r2_log"], 2))
V["only_snpp_025_m"] = pct(sc[("0.25", "Monat")]["only_snpp"])
by = {(r["dn"], r["y"]): r for r in S["ratio_by_year"]}
stab = [by[("D", y)]["n_snpp_aqua"] for y in range(2012, 2022)]
stabN = [by[("N", y)]["n_snpp_aqua"] for y in range(2012, 2022)]
V["yr_D_lo"], V["yr_D_hi"] = de(min(stab), 1), de(max(stab), 1)
V["yr_N_lo"], V["yr_N_hi"] = de(min(stabN), 0), de(max(stabN), 0)
fr_st = [by[("D", y)]["frp_snpp_aqua"] for y in range(2012, 2022)]
fr_dr = [by[("D", y)]["frp_snpp_aqua"] for y in range(2022, 2027)]
V["frpD_st_lo"], V["frpD_st_hi"] = de(min(fr_st), 2), de(max(fr_st), 2)
V["frpD_dr_lo"], V["frpD_dr_hi"] = de(min(fr_dr), 2), de(max(fr_dr), 2)
tD_st = [by[("D", y)]["n_snpp_terra"] for y in range(2012, 2022)]
V["terraD_st_lo"], V["terraD_st_hi"] = de(min(tD_st), 1), de(max(tD_st), 1)
V["terraD_2025"], V["terraD_2026"] = de(by[("D", 2025)]["n_snpp_terra"], 1), de(by[("D", 2026)]["n_snpp_terra"], 1)
mod_st = [by[("alle", y)]["n_snpp_modis"] for y in range(2012, 2022)]
mod_dr = [by[("alle", y)]["n_snpp_modis"] for y in range(2022, 2027)]
V["mod_st_lo"], V["mod_st_hi"] = de(min(mod_st), 2), de(max(mod_st), 2)
V["mod_dr_lo"], V["mod_dr_hi"] = de(min(mod_dr), 2), de(max(mod_dr), 2)
bm = {(r["dn"], r["m"]): r for r in S["ratio_by_month"]}
V["mon_D_lo"], V["mon_D_hi"] = de(min(bm[("D", m)]["n_ratio"] for m in range(1, 13)), 1), de(max(bm[("D", m)]["n_ratio"] for m in range(1, 13)), 1)
V["mon_N_lo"], V["mon_N_hi"] = de(min(bm[("N", m)]["n_ratio"] for m in range(1, 13)), 0), de(max(bm[("N", m)]["n_ratio"] for m in range(1, 13)), 0)
rv = S["region_ratio_vs_small"]
V["reg_lo"], V["reg_hi"], V["reg_rho"] = de(rv["n_ratio_min"], 1), de(rv["n_ratio_max"], 1), de(rv["spearman"], 2)
V["reg_frp_lo"], V["reg_frp_hi"] = de(rv["frp_ratio_min"], 1), de(rv["frp_ratio_max"], 1)
ta = S["terra_aqua_by_year"]
V["ta_D_lo"], V["ta_D_hi"] = de(min(t["n_D"] for t in ta if t["y"] <= 2021), 2), de(max(t["n_D"] for t in ta if t["y"] <= 2021), 2)
V["ta_N_lo"], V["ta_N_hi"] = de(min(t["n_N"] for t in ta if t["y"] <= 2021), 1), de(max(t["n_N"] for t in ta if t["y"] <= 2021), 1)
V["ta_all"] = de(S["terra_vs_aqua_monthly"]["ratio_sum"], 2)
tp = {t["src"]: t for t in S["terra_vs_aqua_as_predictor"]}
V["pred_aqua"], V["pred_terra"], V["pred_both"] = de(tp["Aqua"]["r2_log"], 2), de(tp["Terra"]["r2_log"], 2), de(tp["Aqua+Terra"]["r2_log"], 2)
cand = {c["method"].split(" ")[0]: c for c in SG["candidates"]}
for k in ["M0", "M1", "M2", "M3", "M9", "M12", "A1", "T1"]:
    V[f"{k}_fe"], V[f"{k}_acc"] = de(cand[k]["cv_factor_err"], 2), pct(cand[k]["cv_class_acc"])
V["M3_p90"] = de(cand["M3"]["cv_factor_err_p90"], 1)
V["M3_fe_drift"] = de(cand["M3"]["drift_factor_err"], 2)
V["M3_bias_lo"] = de(min(cand["M3"][f"drift_bias_{y}"] for y in range(2022, 2027)), 2)
V["M3_bias_hi"] = de(max(cand["M3"][f"drift_bias_{y}"] for y in range(2022, 2027)), 2)
rk = SG["rank_way"]
V["rank_acc"], V["rank_kappa"] = pct(rk[0]["class_acc"]), de(rk[0]["kappa"], 2)
V["rank_ref"] = pct(rk[-1]["class_acc"])
V["median_acc"] = pct(SG["median_way"]["MODIS Anzahl"]["acc"])
fac = SG["factors"]
V["k_modis"], V["k_aqua"], V["k_terra"] = de(fac["global_modis"], 2), de(fac["global_aqua"], 2), de(fac["global_terra"], 2)
V["k_day"], V["k_night"] = de(fac["day"], 1), de(fac["night"], 1)
V["k_reg_lo"], V["k_reg_hi"] = de(min(fac["by_region"].values()), 1), de(max(fac["by_region"].values()), 1)
V["n_cand"] = str(len(SG["candidates"]))
zm = {m["method"].split(" ")[0]: m for m in SG["zero_months"]["methods"]}
V["zero_share"] = pct(SG["zero_months"]["share"])
V["zero_true"] = de(SG["zero_months"]["mean_true"], 1)
V["zero_M3"], V["zero_M9"], V["zero_M12"] = pct(zm["M3"]["acc_zero"]), pct(zm["M9"]["acc_zero"]), pct(zm["M12"]["acc_zero"])
V["zero_M9_pred"] = de(zm["M9"]["mean_pred_zero"], 1)
V["nz_M3"], V["nz_M12"] = pct(zm["M3"]["acc_nonzero"]), pct(zm["M12"]["acc_nonzero"])
V["n_rm"] = de(SG["n_region_months_cv"], 0)
V["n_regions"] = str(len(SG["regions"]))
ag = {a["level"]: a for a in FA["aggregation"]}
V["ag_m"], V["ag_q"], V["ag_y"] = de(ag["NUTS-2 x Monat"]["factor_err"], 2), de(ag["NUTS-2 x Quartal"]["factor_err"], 2), de(ag["NUTS-2 x Jahr"]["factor_err"], 2)
V["ag_cm"] = de(ag["Land x Monat"]["factor_err"], 2)
ft = {f["filter"]: f for f in FA["filters"]}
V["f_none_r2"], V["f_t0_r2"] = de(ft["kein Filter (alle type, alle Konfidenzen)"]["r2_log"], 2), de(ft["nur type = 0"]["r2_log"], 2)
V["f_night_fe"], V["f_day_fe"] = de(ft["type = 0, nur Nacht"]["factor_err"], 1), de(ft["type = 0, nur Tag"]["factor_err"], 2)
oc, jp = SE["overlap_check"], SE["jump"]
V["oc_med"], V["oc_max"], V["oc_r"] = de(oc["median_factor_err"], 2), de(oc["max_factor_err"], 2), de(oc["corr"], 3)
V["jump_naive"], V["jump_harm"], V["jump_modis"] = de(jp["naive_post_over_pre"], 1), de(jp["harmonised_post_over_pre"], 2), de(jp["modis_only_post_over_pre"], 2)
V["med_shift"] = pct(SE["median_shift"]["share_changed_gt25pct"])
gp = {(p["a"], p["b"]): p for p in G["pairs_global"]}
gi = {(p["a"], p["b"]): p for p in G["pairs_iberia_box"]}
V["vv_glob"], V["vv_ib"] = de(gp[("n_N20", "n_SNPP")]["factor_err"], 2), de(gi[("n_N20", "n_SNPP")]["factor_err"], 2)
V["mv_glob"], V["mv_ib"] = de(gp[("n_MODIS", "n_SNPP")]["factor_err"], 2), de(gi[("n_MODIS", "n_SNPP")]["factor_err"], 2)
V["n20_dev"] = pct(max(abs(1 - gp[("n_N20", "n_SNPP")]["factor"]), abs(1 - gp[("n_N21", "n_SNPP")]["factor"])))
V["n20_reg_max"] = pct(max(abs(m["n20_vs_snpp"] - 1) for m in G["macro_regions"]))
V["n20_lo"] = de(min(gp[("n_N20", "n_SNPP")]["factor"], gp[("n_N21", "n_SNPP")]["factor"]), 2)
V["n20_hi"] = de(max(1 / gp[("n_N20", "n_SNPP")]["factor"], 1 / gp[("n_N21", "n_SNPP")]["factor"]), 2)
tl = G["tiles"]
V["tile_n_lo"], V["tile_n_hi"] = de(tl["n_ratio"]["p05"], 1), de(tl["n_ratio"]["p95"], 1)
V["tile_frp_lo"], V["tile_frp_hi"], V["tile_frp_med"] = de(tl["frp_ratio"]["p05"], 1), de(tl["frp_ratio"]["p95"], 1), de(tl["frp_ratio"]["p50"], 1)
V["n_tiles"] = str(tl["n_tiles"])
glst = {(l["sat"], l["dn"]): l["lst"] for l in G["lst"]}
V["g_aqua_lst"], V["g_snpp_lst"], V["g_terra_lst"] = hhmm(glst[("Aqua", "D")]), hhmm(glst[("SNPP", "D")]), hhmm(glst[("Terra", "D")])
V["n_iberia"] = de(NU["n_total"], 0)
V["n_null"] = str(NU["n_null"])
V["n_near"] = de(NU["n_nearest"], 0)
cc = {c["dn"] + c["k"]: c for c in C["conf_viirs"]}
V["conf_n_share_N"] = pct(cc["Nn"]["n"] / (cc["Nn"]["n"] + cc["Nh"]["n"]))

# ---------- Grafiken ----------
F = {}
# Erkennungsschwelle gegen Pixelflaeche
ser = []
for sat, col, nm_ in [("Aqua", "--s2", "MODIS Aqua (Tag)"), ("SNPP", "--s1", "VIIRS SNPP (Tag)")]:
    ser.append(dict(name=nm_, color=col, pts=[(thr[(sat, "D", g)]["area"], thr[(sat, "D", g)]["p05"]) for g in range(1, 13)]))
F["threshold"] = linechart(ser, xlab="Pixelfläche scan × track (km²)", ylab="schwächste 5 % der Erkennungen: FRP (MW)",
                           xticks=[0.1, 0.3, 1, 3, 10], yticks=[1, 3, 10, 30, 60], xlog=True, ylog=True, crosshair=False,
                           xfmt=lambda v: de(v, 2), yfmt=lambda v: de(v, 1),
                           xtickfmt=lambda v: de(v, 1), ytickfmt=lambda v: de(v, 0), table_x="Pixelfläche (km²)",
                           caption="Je größer das Pixel, desto stärker muss ein Feuer sein, um erkannt zu werden. Beide Achsen logarithmisch. Quelle: 02_columns.py")
# Erkennungskurve
ser = []
for dn, col, nm_ in [("D", "--day", "Tag"), ("N", "--night", "Nacht")]:
    pts = [(c["frp"], c["p"]) for c in M["detect_curve"] if c["dn"] == dn]
    f = fit[(dn, "alle")]
    xs = [10 ** (i / 20) for i in range(-6, 67)]
    ser.append(dict(name=f"{nm_}: Modellkurve", color=col, markers=False, legend=False, tips=False,
                    pts=[(x, 1 / (1 + math.exp(-(f["a"] + f["b"] * math.log10(x))))) for x in xs]))
    ser.append(dict(name=nm_, color=col, line=False, pts=pts))
F["detect"] = linechart(ser, xlab="FRP-Summe des VIIRS-Clusters (MW)", ylab="Anteil, den Aqua ebenfalls erkennt",
                        xticks=[0.5, 1, 3, 10, 30, 100, 300, 1000, 2000], yticks=[0, 0.25, 0.5, 0.75, 1], xlog=True, crosshair=False,
                        xfmt=lambda v: de(v, 1), yfmt=lambda v: pct(v), xtickfmt=lambda v: de(v, 0) if v >= 1 else de(v, 1),
                        table_x="FRP (MW)", hrefs=[(0.5, "50 %")],
                        caption="Punkte: gemessene Anteile in 15 gleich großen Klassen. Linien: logistische Kurve. Cluster = Zelle 0,05° × Datum × Tag/Nacht. Quelle: 03_matchup.py")
# Gemeinsam gesehene Cluster: FRP
b = M["codetected_frp_binned"]
F["cofrp"] = linechart([dict(name="Median VIIRS", color="--s1", pts=[(r["frp_a"], r["q50"]) for r in b])],
                       bands=[dict(color="--s1", pts=[(r["frp_a"], r["q25"], r["q75"]) for r in b])],
                       xlab="FRP-Summe Aqua im Cluster (MW)", ylab="FRP-Summe SNPP im selben Cluster (MW)",
                       xticks=[3, 10, 30, 100, 300, 1000, 3000], yticks=[3, 10, 30, 100, 300, 1000, 3000], xlog=True, ylog=True,
                       crosshair=False, diag=True, xfmt=lambda v: de(v, 0), yfmt=lambda v: de(v, 0), table_x="FRP Aqua (MW)",
                       caption=f"Nur Cluster, die beide Sensoren am selben Tag sehen ({V['co_n']} Fälle). Linie: Median, Fläche: mittlere 50 %. Quelle: 03_matchup.py")
# Verhaeltnis je Monat
MON = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
ser = [dict(name="Tag", color="--day", pts=[(m, bm[("D", m)]["n_ratio"]) for m in range(1, 13)]),
       dict(name="Nacht", color="--night", pts=[(m, bm[("N", m)]["n_ratio"]) for m in range(1, 13)])]
F["month"] = linechart(ser, xlab="Kalendermonat (Summe 2012–2021)", ylab="Erkennungen SNPP je Aqua-Erkennung",
                       xticks=list(range(1, 13)), yticks=[2, 4, 8, 16, 32], ylog=True, xfmt=lambda v: MON[int(v) - 1],
                       yfmt=lambda v: de(v, 1), ytickfmt=lambda v: de(v, 0), table_x="Monat",
                       caption="Der Zählfaktor ist nachts zwei- bis achtmal so groß wie tags und im Winter am höchsten. y-Achse logarithmisch. Quelle: 04_scales.py")
# Bahndrift
ser = [dict(name=nm_, color=col, pts=[(y, drift.get((sat, "D", y))) for y in range(2001, 2027) if drift.get((sat, "D", y))])
       for sat, col, nm_ in [("SNPP", "--s1", "SNPP"), ("Aqua", "--s2", "Aqua"), ("Terra", "--s3", "Terra")]]
F["drift"] = linechart(ser, xlab="Jahr", ylab="mittlere lokale Sonnenzeit der Tag-Erkennungen (Stunde)",
                       xticks=[2001, 2006, 2011, 2016, 2021, 2026], yticks=[9, 10, 11, 12, 13, 14, 15],
                       xfmt=lambda v: str(int(v)), yfmt=lambda v: hhmm(v) + " Uhr", table_x="Jahr",
                       caption="Bis 2021 fliegen alle drei zu festen Ortszeiten. Danach wandert Aqua in den Nachmittag und Terra in den Morgen, SNPP bleibt. Quelle: 02_columns.py")
# Verhaeltnis je Jahr
ser = [dict(name="Tag", color="--day", pts=[(y, by[("D", y)]["n_snpp_aqua"]) for y in range(2012, 2027)]),
       dict(name="Nacht", color="--night", pts=[(y, by[("N", y)]["n_snpp_aqua"]) for y in range(2012, 2027)])]
F["year"] = linechart(ser, xlab="Jahr", ylab="Erkennungen SNPP je Aqua-Erkennung", xticks=[2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026],
                      yticks=[2, 4, 8, 16, 32], ylog=True, xfmt=lambda v: str(int(v)), yfmt=lambda v: de(v, 1), ytickfmt=lambda v: de(v, 0), table_x="Jahr",
                      caption="Tags bleibt der Faktor über alle Jahre in einem engen Band. Nachts schwankt er stark, weil Aqua in schwachen Jahren nur wenige hundert Nacht-Erkennungen hat. Quelle: 04_scales.py")
# Regionen
rr = sorted(S["ratio_by_region"], key=lambda r: -r["n_ratio"])
F["region"] = bars([(f'{r["region_id"]} {names.get(r["region_id"], "")}', r["n_ratio"],
                     [["FRP-Verhältnis", de(r["frp_ratio"], 2), ""], ["Anteil kleiner Feuer (< 10 MW)", pct(r["share_small"]), ""],
                      ["Aqua-Erkennungen", de(r["n_aqua"], 0), ""]]) for r in rr],
                   vmax=max(r["n_ratio"] for r in rr) * 1.05, color="--s1",
                   caption="Erkennungen SNPP je Aqua-Erkennung nach NUTS-2-Region, 2012–2021, nur Regionen mit mindestens 100 Aqua-Erkennungen. Quelle: 04_scales.py")
# Aggregation
F["agg"] = bars([(a["level"].replace(" x ", " × "), a["factor_err"], [["90 % der Fälle unter Faktor", de(a["factor_err_p90"], 2), ""],
                                                                     ["Anzahl Vergleichswerte", de(a["n"], 0), ""]]) for a in FA["aggregation"]],
                vmax=1.6, fmt=lambda v: "× " + de(v, 2), color="--s2",
                caption="Typischer Fehler der umgerechneten MODIS-Reihe gegenüber VIIRS (Faktor je Region, Kreuzvalidierung 2012–2021). × 1,00 wäre perfekt. Quelle: 06b_filters_aggregation.py")
# Harmonisierte Reihe
yy = SE["yearly"]
ser = [dict(name="MODIS roh (Aqua + Terra)", color="--ctx", pts=[(r["y"], r["modis_raw"]) for r in yy]),
       dict(name="MODIS × Faktor je Region", color="--s2", pts=[(r["y"], r["modis_scaled"]) for r in yy]),
       dict(name="VIIRS SNPP gemessen", color="--s1", pts=[(r["y"], r["snpp"]) for r in yy if r["y"] >= 2012])]
F["series"] = linechart(ser, xlab="Jahr", ylab="Erkennungen pro Jahr (type 0, alle Regionen)", xticks=[2001, 2005, 2009, 2013, 2017, 2021, 2025],
                        yticks=[0, 10000, 20000, 30000, 40000, 50000], xfmt=lambda v: str(int(v)), yfmt=lambda v: de(v, 0), h=330, table_x="Jahr",
                        caption="Die umgerechnete MODIS-Reihe (orange) trifft die VIIRS-Messung (blau) 2013–2025 fast genau. Die Faktoren stammen nur aus 2012–2021. Quelle: 08_series.py")

# ---------- Tabellen ----------
TB = {}
GR = [("0.05", "0,05°"), ("0.1", "0,1°"), ("0.25", "0,25°"), ("0.5", "0,5°"), ("1.0", "1°"), ("nuts2", "NUTS-2"), ("all", "Iberien gesamt")]


def heat(v):
    return f'<td style="background:color-mix(in srgb, var(--s1) {max(0, min(1, v)) * 62:.0f}%, transparent)">{de(v, 2)}</td>'


TB["scales"] = ('<div class="scroll"><table class="num heat"><thead><tr><th>Raster</th><th>Tag</th><th>Monat</th><th>Jahr</th>'
                '<th>nur SNPP meldet (Monat)</th></tr></thead><tbody>' + "".join(
                    f"<tr><td>{lab}</td>" + "".join(heat(sc[(g, t)]["r2_log"]) if "r2_log" in sc[(g, t)] else "<td>–</td>" for t in ["Tag", "Monat", "Jahr"])
                    + f"<td>{pct(sc[(g, 'Monat')]['only_snpp'])}</td></tr>" for g, lab in GR) + "</tbody></table></div>")
MET = {"n": "Anzahl Erkennungen", "frp": "FRP-Summe", "area": "Summe Pixelfläche", "days": "Tage mit Feuer", "celldays": "aktive Zell-Tage (0,05°)"}
mt = [m for m in S["metrics"] if m["grid"] == "nuts2" and m["dn"] == "alle"]
TB["metrics"] = table(["Kenngröße", "Rang-Korrelation", "R² (log)", "Verhältnis SNPP / Aqua", "Spanne über die Jahre", "Streuung über Jahre", "Streuung über Regionen"],
                      [[MET[m["metric"]], de(m["spearman"], 2), de(m["r2_log"], 2), de(m["ratio_sum"], 2),
                        f'{de(m["ratio_year_min"], 2)} – {de(m["ratio_year_max"], 2)}', pct(m["cv_year"]), pct(m["cv_region"])] for m in mt], hl=(0,))
order = ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "M11", "M12", "M13", "M14", "A1", "T1"]
rows = []
for k in order:
    c = cand[k]
    rows.append([esc(c["method"]), "× " + de(c["cv_factor_err"], 2), "× " + de(c["cv_factor_err_p90"], 1), de(c["cv_bias"], 2),
                 pct(c["cv_class_acc"]), de(c["cv_kappa"], 2), "× " + de(c["drift_factor_err"], 2), pct(c["drift_class_acc"])])
TB["cand"] = table(["Weg", "typischer Fehler", "90 % unter", "Summe (1 = exakt)", "Klasse getroffen", "Kappa",
                    "Fehler 2022–2026", "Klasse 2022–2026"], rows, hl=(3,))
TB["rank"] = table(["Variante (ohne jede Umrechnung)", "Klasse getroffen", "Kappa"],
                   [[esc(r["variant"]), pct(r["class_acc"]), de(r["kappa"], 2)] for r in rk])
TB["filters"] = table(["Filter", "MODIS", "VIIRS", "Verhältnis", "typischer Fehler", "R² (log)", "Klasse getroffen"],
                      [[esc(f["filter"]), de(f["n_modis"], 0), de(f["n_viirs"], 0), de(f["ratio"], 2), "× " + de(f["factor_err"], 2),
                        de(f["r2_log"], 2), pct(f["class_acc"])] for f in FA["filters"]], hl=(1,))
TB["confirm"] = table(["von → bestätigt durch", "Tageshälfte", "Erkennungen", "≤ 1 km", "≤ 3 km", "≤ 10 km"],
                      [[("Aqua → SNPP" if c["sat"] == "Aqua" else "SNPP → Aqua"), "Tag" if c["dn"] == "D" else "Nacht",
                        de(c["n"], 0), pct(c["r1"]), pct(c["r3"]), pct(c["r10"])] for c in M["confirm"]])
cs = [c for c in M["cluster_size_dist"]]
lab = {"(0.0, 1.0]": "bis 1", "(1.0, 2.0]": "1–2", "(2.0, 5.0]": "2–5", "(5.0, 10.0]": "5–10", "(10.0, 20.0]": "10–20",
       "(20.0, 50.0]": "20–50", "(50.0, 100.0]": "50–100", "(100.0, 500.0]": "100–500", "(500.0, 1000000000.0]": "über 500"}
csd = {(c["dn"], c["cls"]): c for c in cs}
TB["sizes"] = table(["FRP des VIIRS-Clusters (MW)", "Anteil der Cluster (Tag)", "Anteil der FRP (Tag)", "von Aqua gesehen (Tag)",
                     "Anteil der Cluster (Nacht)", "von Aqua gesehen (Nacht)"],
                    [[lab[k], pct(csd[("D", k)]["share_n"], 1), pct(csd[("D", k)]["share_frp"], 1), pct(csd[("D", k)]["seen"]),
                      pct(csd[("N", k)]["share_n"], 1), pct(csd[("N", k)]["seen"])] for k in lab])
TB["static"] = table(["Tageshälfte", "statisch bei SNPP", "statisch bei Aqua", "Zählfaktor ungefiltert", "Zählfaktor mit type = 0"],
                     [[{"D": "Tag", "N": "Nacht", "alle": "gesamt"}[e["dn"]], pct(e["static_share_snpp"], 1), pct(e["static_share_aqua"], 1),
                       de(e["ratio_unfiltered"], 1), de(e["ratio_type0"], 1)] for e in ST["effect_on_ratio"]])
PN = {"n_N20": "NOAA-20", "n_N21": "NOAA-21", "n_SNPP": "SNPP", "n_Aqua": "Aqua", "n_MODIS": "Aqua + Terra", "frp_N20": "NOAA-20 (FRP)",
      "frp_SNPP": "SNPP (FRP)", "frp_Aqua": "Aqua (FRP)"}
TB["pairs"] = table(["Vorhersage von", "aus", "Gebiet", "Faktor", "typischer Fehler", "90 % unter", "R² (log)"],
                    [[PN[p["b"]], PN[p["a"]], "weltweit", de(p["factor"], 2), "× " + de(p["factor_err"], 2), "× " + de(p["factor_err_p90"], 1), de(p["r2_log"], 2)]
                     for p in G["pairs_global"]] +
                    [[PN[p["b"]], PN[p["a"]], "Iberien-Box", de(p["factor"], 2), "× " + de(p["factor_err"], 2), "× " + de(p["factor_err_p90"], 1), de(p["r2_log"], 2)]
                     for p in G["pairs_iberia_box"]])
RN = {"Iberien-Box": "Iberien-Box", "Suedamerika (Suedhaelfte)": "Südamerika, Südhälfte (mit Argentinien)", "Amazonas / Cerrado": "Amazonas / Cerrado",
      "Afrika suedl. Sahara Nord": "Afrika, Sahel bis Äquator", "Afrika Sued": "Afrika, südlich des Äquators", "Suedostasien": "Südostasien",
      "Australien": "Australien", "Nordamerika": "Nordamerika", "Sibirien / Zentralasien": "Sibirien / Zentralasien", "Indien": "Indien"}
TB["macro"] = table(["Großregion", "Aqua-Erkennungen", "Zählfaktor Tag", "Zählfaktor Nacht", "SNPP je (Aqua + Terra)", "FRP SNPP / Aqua", "NOAA-20 / SNPP"],
                    [[RN[m["region"]], de(m["n_aqua"], 0), de(m["n_ratio_day"], 1), de(m["n_ratio_night"], 0), de(m["n_ratio_modis"], 1),
                      de(m["frp_ratio"], 2), de(m["n20_vs_snpp"], 2)] for m in G["macro_regions"]])
kr = sorted(SE["k_region"].items(), key=lambda kv: -kv[1])
TB["kreg"] = table(["Region", "Name", "Faktor für (Aqua + Terra)", "Faktor nur Terra"],
                   [[r, esc(names.get(r, "")), de(v, 2), de(SE["kt_region"].get(r, SE["kt_global"]), 2)] for r, v in kr])
rg = {(r["col"], r["sat"], r["dn"]): r for r in C["ranges"]}


def rng(col, sat, dn="D", d=1):
    r = rg[(col, sat, dn)]
    return f'{de(r["p05"], d)} / {de(r["p50"], d)} / {de(r["p95"], d)}'


TB["ranges"] = table(["Spalte", "Aqua Tag", "Aqua Nacht", "Terra Tag", "SNPP Tag", "SNPP Nacht"],
                     [[f"<code>{c}</code>", rng(c, "Aqua", "D", d), rng(c, "Aqua", "N", d), rng(c, "Terra", "D", d), rng(c, "SNPP", "D", d), rng(c, "SNPP", "N", d)]
                      for c, d in [("brightness", 0), ("bright_t31", 0), ("frp", 1), ("scan", 2), ("track", 2)]])

# ---------- Zusammenbau ----------
body = T.render(V, F, TB)
doc_head = ('<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
out = ROOT.parent / "docs" / "harmonisierung_bericht.html"
out.write_text(doc_head + T.HEAD + "</head>\n<body>\n" + body + "\n</body>\n</html>\n", encoding="utf-8")
print("->", out, f"({out.stat().st_size / 1024:.0f} KB)")
if "--fragment" in sys.argv:
    p = sys.argv[sys.argv.index("--fragment") + 1]
    open(p, "w", encoding="utf-8").write(T.HEAD + body)
    print("->", p)
