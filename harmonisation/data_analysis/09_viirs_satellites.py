"""Schritt 9: Koennen NOAA-20 und NOAA-21 zusammen mit SNPP eine VIIRS-Referenzreihe bilden?

Daten: VIIRS SNPP (01/2012-), NOAA-20 (N20, 04/2018-), NOAA-21 (N21, 03/2023-), Iberien,
Archiv mit `type`, NRT ohne. Archivzeilen zaehlen nur mit type = 0.

Entscheidungsregeln, festgelegt am 14.11.2026 VOR der Messung:
  R1  Median N20/SNPP und N21/SNPP (Anzahl je Region x Jahr, nur gemeinsame Tage, Regionen mit
      >= 2000 SNPP-Erkennungen) liegt in 0,85-1,15. Sonst: anhalten, Mittelwert nicht verwenden.
  R2  Mittlere Ueberflugzeit am Tag (lokale Sonnenzeit) weicht je Jahr hoechstens 15 min von den
      ersten beiden vollen Jahren des Satelliten ab (wie der Drift-Monitor). Sonst: anhalten.
  R3  Die MODIS-Faktoren werden auf der Referenzreihe (Mittel der aktiven VIIRS-Satelliten)
      kalibriert. Weicht der Gesamtfaktor um mehr als 3 % (Schwelle D2) von dem mit SNPP allein
      ab, haette die Reihe ab 2018 einen Niveausprung: anhalten.
  R4  Rauschen (KPI N3): 2023-2026 sind drei Satelliten aktiv. Jeder wird einmal zurueckgehalten.
      Das Mittel der beiden anderen muss ihn besser treffen (kleinerer typischer Fehler je
      Region x Tag) als jeder der beiden allein, in allen drei Rotationen.
  R5  Ortsmaske (KPI N4): gelernt aus allen VIIRS-Archivzeilen bis 2022, geprueft ab 2023 je
      Satellit: Recall >= 0,90, faelschlich entfernte Feuer <= 0,02.

Schreibt results/viirs_satellites.json.
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import CACHE, IBERIA, RAW, con, save

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import load_config  # noqa: E402
from pipeline.data_loading.assign_region import assign_nuts2_region  # noqa: E402
from pipeline.data_loading.static_source_mask import flag_hotspots_in_mask, learn_static_mask  # noqa: E402

VIIRS = CACHE / "iberia_viirs.parquet"
FILES = {"SNPP": ("viirs_snpp", "SV-C2_845370"), "N20": ("viirs_noaa20", "J1V-C2_848091"), "N21": ("viirs_noaa21", "J2V-C2_848092")}
SATS = list(FILES)
MIN_REGION, OFFSET = 2000, 1.0
R1_RANGE, R2_MINUTES, R3_SHIFT = (0.85, 1.15), 15.0, 0.03
CONFIG = load_config()


def factor_error(a, b, offset=OFFSET):
    """Multiplikativer Fehler exp(|log((a+o)/(b+o))|), wie im Fehlermodell der Pipeline."""
    return np.exp(np.abs(np.log((np.asarray(a, float) + offset) / (np.asarray(b, float) + offset))))


def prepare():
    """Liest alle sechs VIIRS-CSVs (Schema wie 00_prepare.py), ordnet die Regionen zu und beschraenkt sie auf die Untersuchungsregionen.

    Gebiet wie in der Pipeline (clean_hotspots.restrict_to_study_regions): `nuts.study_regions`. Die NOAA-Downloads reichen weiter.
    """
    build = importlib.import_module("00_prepare").build
    files = [RAW / folder / f"fire_{kind}_{product}.csv" for folder, product in FILES.values() for kind in ("archive", "nrt")]
    build(files, VIIRS)
    df = pd.read_parquet(VIIRS)
    df = assign_nuts2_region(df, CONFIG)
    inside = df["region_id"].isin(CONFIG["nuts"]["study_regions"])
    print("ausserhalb der Untersuchungsregionen:", df[~inside].groupby("sat").size().to_dict())
    df = df[inside].reset_index(drop=True)
    df["region_id"] = df["region_id"].astype(object)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    df.to_parquet(VIIRS, compression="zstd")
    return df


def operating_days(df):
    """Tage, an denen ein Satellit laut Dateifenster liefert (erstes bis letztes Datum je Datei)."""
    days = {}
    for sat in SATS:
        rows = df[df.sat == sat]
        parts = [pd.date_range(g.acq_date.min(), g.acq_date.max()) for _, g in rows.groupby("source")]
        days[sat] = parts[0].union(parts[1]) if len(parts) == 2 else parts[0]
    return days


def daily_table(fires, days):
    """Region x Tag x Satellit, lueckenlos ueber die Betriebstage, 0 an Tagen ohne Feuer."""
    sums = fires.dropna(subset=["region_id"]).groupby(["region_id", "acq_date", "sat"]).agg(n=("frp", "size"), frp=("frp", "sum"))
    wide = sums.unstack("sat")
    wide.columns = [f"{m}_{s}" for m, s in wide.columns]
    all_days = days["SNPP"].union(days["N20"]).union(days["N21"])
    index = pd.MultiIndex.from_product([sorted(fires.region_id.dropna().unique()), all_days], names=["region_id", "date"])
    table = wide.reindex(index).fillna(0.0).reset_index()
    for sat in SATS:
        on = table.date.isin(days[sat])
        for m in ("n", "frp"):
            table[f"{m}_{sat}"] = table[f"{m}_{sat}"].where(on)
    return table


def ratios(table, regions):
    """R1: Verhaeltnis zu SNPP je Region x Jahr, nur Tage, an denen beide liefern."""
    out = {}
    for sat in ("N20", "N21"):
        both = table[table[f"n_{sat}"].notna() & table.n_SNPP.notna() & table.region_id.isin(regions)]
        yearly = both.assign(y=both.date.dt.year).groupby(["region_id", "y"])[[f"n_{sat}", "n_SNPP", f"frp_{sat}", "frp_SNPP"]].sum()
        yearly = yearly[yearly.n_SNPP >= 50]
        rn, rf = yearly[f"n_{sat}"] / yearly.n_SNPP, yearly[f"frp_{sat}"] / yearly.frp_SNPP
        total = both.groupby(both.date.dt.year)[[f"n_{sat}", "n_SNPP", f"frp_{sat}", "frp_SNPP"]].sum()
        out[sat] = {"count_median": float(rn.median()), "count_p10": float(rn.quantile(.1)), "count_p90": float(rn.quantile(.9)),
                    "frp_median": float(rf.median()), "frp_p10": float(rf.quantile(.1)), "frp_p90": float(rf.quantile(.9)),
                    "n_region_years": int(len(yearly)), "passes_r1": bool(R1_RANGE[0] <= rn.median() <= R1_RANGE[1]),
                    "by_year": [{"year": int(y), "count_ratio": float(r[f"n_{sat}"] / r.n_SNPP), "frp_ratio": float(r[f"frp_{sat}"] / r.frp_SNPP),
                                 "n_snpp": float(r.n_SNPP)} for y, r in total.iterrows()],
                    "by_region": [{"region_id": reg, "count_ratio": float(g[f"n_{sat}"].sum() / g.n_SNPP.sum())}
                                  for reg, g in yearly.reset_index().groupby("region_id")]}
    return out


def overpass_times(df):
    """R2: Median der lokalen Sonnenzeit je Satellit, Jahr und Tag/Nacht; Abweichung zu den ersten zwei vollen Jahren."""
    rows = df[df.daynight.isin(["D", "N"])].assign(y=df.acq_date.dt.year)
    med = rows.groupby(["sat", "daynight", "y"]).agg(lst=("lst", "median"), n=("lst", "size")).reset_index()
    med = med[med.n >= 50]
    first = rows.groupby("sat").acq_date.min().dt.year + 1          # erstes volles Jahr
    out, ok = [], True
    for (sat, dn), g in med.groupby(["sat", "daynight"]):
        base = g[g.y.isin([first[sat], first[sat] + 1])].lst.mean()
        for r in g.itertuples():
            dev = (r.lst - base) * 60
            out.append({"satellite": sat, "daynight": dn, "year": int(r.y), "median_solar_hour": float(r.lst), "deviation_minutes": float(dev)})
            ok &= (dn != "D") or abs(dev) <= R2_MINUTES
    return {"rows": out, "passes_r2": bool(ok)}


def static_and_mask(df):
    """Anteil statischer Quellen je Satellit und R5: Ortsmaske aus allen VIIRS-Archivzeilen, je Satellit geprueft."""
    typed = df[df.type.notna()].copy()
    share = typed.assign(st=typed.type != 0).groupby(["sat", "daynight"]).st.mean().unstack().to_dict("index")
    params = CONFIG["static_sources"]
    years = typed.acq_date.dt.year
    train, test = typed[years < params["holdout_first_year"]], typed[years >= params["holdout_first_year"]]
    mask = learn_static_mask(train, CONFIG)
    result = {}
    for sat in SATS:
        t = test[test.sat == sat]
        hit, st = flag_hotspots_in_mask(t, mask, params["mask_cell_deg"]), (t.type != 0).to_numpy()
        result[sat] = {"recall": float(hit[st].mean()), "false_removal": float(hit[~st].mean()), "n_static": int(st.sum()), "n_fire": int((~st).sum())}
    nrt = df[df.source == "nrt"]
    removed = {sat: float(flag_hotspots_in_mask(nrt[nrt.sat == sat], learn_static_mask(typed, CONFIG), params["mask_cell_deg"]).mean()) for sat in SATS}
    passes = all(result[s]["recall"] >= 0.90 and result[s]["false_removal"] <= 0.02 for s in ("N20", "N21"))
    return {"static_share": {s: {k: float(v) for k, v in d.items()} for s, d in share.items()}, "mask_holdout": result,
            "nrt_share_removed_by_mask": removed, "passes_r5": bool(passes)}


def noise_rotation(table, regions):
    """R4: 2023-2026, ein Satellit zurueckgehalten. Trifft das Mittel der zwei anderen ihn besser als jeder einzeln?"""
    three = table[table[[f"n_{s}" for s in SATS]].notna().all(axis=1) & table.region_id.isin(regions)]
    out, wins = [], 0
    for grain in ("day", "month"):
        t = three if grain == "day" else three.assign(date=three.date.dt.to_period("M")).groupby(["region_id", "date"])[[f"n_{s}" for s in SATS]].sum().reset_index()
        for held in SATS:
            a, b = [s for s in SATS if s != held]
            ref = t[f"n_{held}"]
            active = (t[[f"n_{s}" for s in SATS]] > 0).any(axis=1)
            e_a, e_b = np.median(factor_error(t[f"n_{a}"][active], ref[active])), np.median(factor_error(t[f"n_{b}"][active], ref[active]))
            e_mean = np.median(factor_error(((t[f"n_{a}"] + t[f"n_{b}"]) / 2)[active], ref[active]))
            better = bool(e_mean < min(e_a, e_b))
            wins += better and grain == "day"
            out.append({"grain": grain, "held_out": held, f"error_{a}": float(e_a), f"error_{b}": float(e_b), "error_mean": float(e_mean),
                        "mean_better_than_each": better, "n_units": int(active.sum())})
    return {"rows": out, "day_rotations_won": int(wins), "passes_r4": bool(wins == 3)}


def outages(table, days):
    """Tage mit Dateifenster, aber 0 Erkennungen im ganzen Gebiet, obwohl die +-3 Nachbartage viel melden."""
    out = {}
    params = CONFIG["daily"]
    for sat in SATS:
        total = table.groupby("date")[f"n_{sat}"].sum(min_count=1).reindex(days[sat]).fillna(0.0)
        med = total.rolling(2 * params["gap_neighbour_days"] + 1, center=True, min_periods=1).median()
        gap = total[(total == 0) & (med >= params["gap_min_neighbour_median"])]
        out[sat] = {"first_day": str(days[sat].min().date()), "last_day": str(days[sat].max().date()), "n_days": int(len(days[sat])),
                    "possible_outage_days": [str(d.date()) for d in gap.index]}
    return out


def calibration_shift(table, regions):
    """R3: MODIS-Faktor (Aqua + Terra) je Region mit Referenz SNPP allein gegen Referenz Mittel der aktiven VIIRS-Satelliten."""
    modis = con().execute(f"""SELECT region_id, acq_date::TIMESTAMP AS date, COUNT(*) n FROM '{IBERIA}'
        WHERE sensor = 'MODIS' AND source = 'archive' AND type = 0 AND region_id IS NOT NULL
          AND acq_date BETWEEN '{CONFIG['calibration']['window_start']}' AND '{CONFIG['calibration']['window_end']}' GROUP BY ALL""").df()
    window = table[table.date.between(CONFIG["calibration"]["window_start"], CONFIG["calibration"]["window_end"]) & table.n_SNPP.notna()]
    window = window.assign(n_mean=window[[f"n_{s}" for s in SATS]].mean(axis=1))
    merged = window.merge(modis, on=["region_id", "date"], how="left").fillna({"n": 0.0})
    g = merged.groupby("region_id")[["n_SNPP", "n_mean", "n"]].sum()
    overall_snpp, overall_mean = g.n_SNPP.sum() / g.n.sum(), g.n_mean.sum() / g.n.sum()
    per_region = (g.n_mean / g.n) / (g.n_SNPP / g.n)
    shift = overall_mean / overall_snpp - 1
    k_mean = (g.n_mean / g.n.where(g.n >= 300)).fillna(overall_mean)       # wie die Pipeline: Rueckfall unter 300 MODIS-Erkennungen
    return {"k_pair_overall_snpp": float(overall_snpp), "k_pair_overall_mean": float(overall_mean), "relative_shift": float(shift),
            "region_shift_max": float((per_region[g.n >= 300] - 1).abs().max()), "passes_r3": bool(abs(shift) <= R3_SHIFT),
            "k_pair_region_mean": {region: float(value) for region, value in k_mean.items()},
            "note": "Naeherung ohne Betriebstage-Filter der Pipeline; die Pipeline misst den Wert erneut (calib_summary.json)."}


if __name__ == "__main__":
    df = prepare()
    fires = df[(df.source == "nrt") | (df.type == 0)]
    days = operating_days(df)
    table = daily_table(fires, days)
    snpp_total = fires[fires.sat == "SNPP"].groupby("region_id").size()
    regions = sorted(snpp_total[snpp_total >= MIN_REGION].index)
    counts = df.groupby(["sat", "source"]).agg(n=("frp", "size"), first=("acq_date", "min"), last=("acq_date", "max")).reset_index()
    out = {"rows": [{"satellite": r.sat, "source": r.source, "n": int(r.n), "first": str(r.first.date()), "last": str(r.last.date())} for r in counts.itertuples()],
           "evaluation_regions": regions, "ratios": ratios(table, regions), "overpass": overpass_times(df),
           "static": static_and_mask(df), "noise": noise_rotation(table, regions), "outages": outages(table, days),
           "calibration": calibration_shift(table, regions)}
    out["decision"] = {"r1": all(out["ratios"][s]["passes_r1"] for s in ("N20", "N21")), "r2": out["overpass"]["passes_r2"],
                       "r3": out["calibration"]["passes_r3"], "r4": out["noise"]["passes_r4"], "r5": out["static"]["passes_r5"]}
    save("viirs_satellites", out)
    print(counts.to_string(index=False))
    for sat in ("N20", "N21"):
        r = out["ratios"][sat]
        print(sat, "Anzahl", round(r["count_median"], 3), (round(r["count_p10"], 2), round(r["count_p90"], 2)),
              "FRP", round(r["frp_median"], 3), "Region-Jahre", r["n_region_years"])
    print("Maske", out["static"]["mask_holdout"])
    print("Rauschen", [(r["grain"], r["held_out"], round(r["error_mean"], 3), r["mean_better_than_each"]) for r in out["noise"]["rows"]])
    print("Kalibrierung", {k: v for k, v in out["calibration"].items() if k != "note"})
    print("Ausfaelle", {s: len(v["possible_outage_days"]) for s, v in out["outages"].items()})
    print("Entscheidung", out["decision"])
