"""Weather of the forecast days with realistic forecast errors (honest evaluation, step 5) and with alternative
weather paths (ensemble members), plus the bias correction of the IFS forecast.

Why: the evaluation of steps 2-4 fed the model the *analysed* weather (ERA5) of the target day, an upper bound.
In production the target day's weather is a forecast made L days earlier, and the FWI codes of the target day are
carried through L forecast days. Here, for a forecast issued on t0 for t0 + L:

1. the analysed weather a_k of the days t0 + k (k = 1..L) gets an error e_k drawn from real IFS - ERA5 errors of
   the same region, a month within +-1 and the same lead day (k - 1), separately for days with and without rain
   in ERA5 (features/forecast_errors.py). Errors of one day are drawn jointly for all variables, so their
   correlation is kept. Lead days above 7 scale the day-7 errors with the measured growth of the spread.
2. optionally the bias correction that production applies to IFS is applied to a_k + e_k.
3. the FWI codes are carried from the analysed codes of t0 through both paths (analysed and perturbed); the
   difference is added to the point-based target-day features. The regional recursion differs a little from the
   point-based one, the difference of two regional paths does not.
4. dryness (rain over 30 / 90 days, days since rain) and the anomalies change by the perturbed forecast days only.

The errors come from one point per region; a regional mean of several points has somewhat smaller errors, so the
perturbation is on the conservative side.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from features import fwi as F
from features.weather import DAYS_SINCE_RAIN_CAP, RAIN_DAY_MM, fosberg_index, saturation_vapour_pressure

BASE = ["t2m", "rh", "wind", "precip", "tmax", "gust", "td"]
ADDITIVE = ["t2m", "rh", "wind", "tmax", "gust", "td"]
MAX_LEAD_DAY = 7


@dataclass
class ErrorModel:
    """Pools of real forecast errors per (region, lead day 0..7, ERA5 wet day, month)."""
    err: pd.DataFrame
    growth: dict
    _pools: dict | None = None

    def __post_init__(self):
        self._pools = {}
        e = self.err.reset_index(drop=True)
        self.E = {v: e[f"e_{v}"].to_numpy(float) for v in BASE}
        self.regions = sorted(e["region_id"].unique())
        key = e.groupby(["region_id", "lead_day", "era5_wet", "month"]).indices
        for (r, ld, wet, m), ix in key.items():
            self._pools[(r, int(ld), bool(wet), int(m))] = ix
        self.by_r_ld_wet = e.groupby(["region_id", "lead_day", "era5_wet"]).indices
        self.by_ld_wet = e.groupby(["lead_day", "era5_wet"]).indices

    def candidates(self, region: str, lead_day: int, wet: bool, month: int) -> np.ndarray:
        ix = [self._pools.get((region, lead_day, wet, (month - 1 + d) % 12 + 1)) for d in (-1, 0, 1)]
        ix = [a for a in ix if a is not None]
        if ix and sum(len(a) for a in ix) >= 10:
            return np.concatenate(ix)
        a = self.by_r_ld_wet.get((region, lead_day, wet))
        if a is not None and len(a) >= 10:
            return a
        return self.by_ld_wet[(lead_day, wet)]

    def draw(self, regions: np.ndarray, lead_day: int, wet: np.ndarray, months: np.ndarray,
             rng: np.random.Generator) -> dict[str, np.ndarray]:
        """One joint error vector per request; lead days above 7 are scaled day-7 errors."""
        ld = min(lead_day, MAX_LEAD_DAY)
        pick = np.empty(len(regions), dtype=int)
        keys = pd.DataFrame({"r": regions, "w": wet.astype(bool), "m": months})
        for (r, w, m), ix in keys.groupby(["r", "w", "m"]).indices.items():
            cand = self.candidates(r, ld, bool(w), int(m))
            pick[ix] = cand[rng.integers(0, len(cand), size=len(ix))]
        out = {v: self.E[v][pick].copy() for v in BASE}
        if lead_day > MAX_LEAD_DAY:
            for v in BASE:
                g = self.growth.get(v, 1.0) ** (lead_day - MAX_LEAD_DAY)
                mu = float(np.mean(self.E[v]))
                out[v] = mu + (out[v] - mu) * g
        return out


@dataclass
class BiasCorrection:
    """Mean IFS - ERA5 error per region, month and lead day; precipitation as a ratio (clipped to 0.5-2)."""
    add: dict           # (region, month, lead_day) -> {var: bias}
    ratio: dict         # (region, month, lead_day) -> precip ratio IFS / ERA5

    @classmethod
    def fit(cls, err: pd.DataFrame, era5_precip_mean: pd.DataFrame | None = None) -> "BiasCorrection":
        add, ratio = {}, {}
        g = err.groupby(["region_id", "month", "lead_day"])
        means = g[[f"e_{v}" for v in ADDITIVE]].mean()
        for key, row in means.iterrows():
            add[(key[0], int(key[1]), int(key[2]))] = {v: float(row[f"e_{v}"]) for v in ADDITIVE}
        if "precip_era5" in err.columns:
            pr = g.apply(lambda x: (x["precip_era5"] + x["e_precip"]).mean() / max(x["precip_era5"].mean(), 0.05),
                         include_groups=False)
            for key, v in pr.items():
                ratio[(key[0], int(key[1]), int(key[2]))] = float(np.clip(v, 0.5, 2.0))
        return cls(add, ratio)

    def apply(self, values: dict[str, np.ndarray], regions: np.ndarray, months: np.ndarray, lead_day: int) -> dict:
        ld = min(lead_day, MAX_LEAD_DAY)
        out = {v: np.asarray(x, float).copy() for v, x in values.items()}
        keys = pd.DataFrame({"r": regions, "m": months})
        for (r, m), ix in keys.groupby(["r", "m"]).indices.items():
            b = self.add.get((r, int(m), ld))
            if b:
                for v in ADDITIVE:
                    if v in out:
                        out[v][ix] -= b[v]
            q = self.ratio.get((r, int(m), ld))
            if q and "precip" in out:
                out["precip"][ix] /= q
        return out


def clip_weather(q: dict) -> dict:
    q["rh"] = np.clip(q["rh"], 1.0, 100.0)
    q["wind"] = np.maximum(q["wind"], 0.0)
    q["precip"] = np.maximum(q["precip"], 0.0)
    q["tmax"] = np.maximum(q["tmax"], q["t2m"])
    q["gust"] = np.maximum(q["gust"], q["wind"])
    q["td"] = np.minimum(q["td"], q["t2m"])
    return q


def regional_codes(w: pd.DataFrame) -> pd.DataFrame:
    """FWI moisture codes from the regional mean weather (used only as the start of the perturbed paths).
    All regions at once (days x regions matrices), consecutive days per region."""
    days = pd.date_range(w["date"].min(), w["date"].max(), freq="D")
    wide = {c: w.pivot(index="date", columns="region_id", values=c).reindex(days) for c in ("t2m", "rh", "wind", "precip")}
    regs = wide["t2m"].columns
    comp = F.fwi_series(wide["t2m"].to_numpy(), wide["rh"][regs].to_numpy(), wide["wind"][regs].to_numpy(),
                        np.clip(wide["precip"][regs].to_numpy(), 0, None), days.month.to_numpy())
    return pd.DataFrame({"region_id": np.tile(regs.to_numpy(), len(days)), "date": np.repeat(days.to_numpy(), len(regs)),
                         "ffmc_r": comp["ffmc"].reshape(-1), "dmc_r": comp["dmc"].reshape(-1),
                         "dc_r": comp["dc"].reshape(-1)})


class Perturber:
    """Target-day weather features for (region, issue date, lead) rows with alternative forecast-day weather."""

    def __init__(self, w: pd.DataFrame, codes: pd.DataFrame | None = None, since: pd.Timestamp | None = None):
        """since: keep only days from then on for the lookups (the codes are still carried from the first day)."""
        c = codes if codes is not None else regional_codes(w)
        if since is not None:
            w = w[w["date"] >= since]
        self.w = w.sort_values(["region_id", "date"]).reset_index(drop=True)
        self.key = pd.MultiIndex.from_arrays([self.w["region_id"], self.w["date"]])
        c = c.set_index(["region_id", "date"]).reindex(self.key)
        self.codes = {k: c[k].to_numpy() for k in ("ffmc_r", "dmc_r", "dc_r")}
        self.cols = {v: self.w[v].to_numpy(float) for v in self.w.columns if v not in ("region_id", "date")}

    def _pos(self, regions, dates) -> np.ndarray:
        return self.key.get_indexer(pd.MultiIndex.from_arrays([regions, dates]))

    def features(self, regions: np.ndarray, issue_dates: pd.Series, lead: int, paths: list[dict]) -> pd.DataFrame:
        """paths[k-1]: dict var -> array (one value per row) of the weather on day t0 + k (k = 1..lead).
        Returns the target-day features; rows whose days are missing in the weather table give NaN."""
        issue_dates = pd.to_datetime(pd.Series(np.asarray(issue_dates)))
        p0 = self._pos(regions, issue_dates)
        pk = [self._pos(regions, issue_dates + pd.Timedelta(days=k)) for k in range(1, lead + 1)]
        ok = (p0 >= 0) & np.all([p >= 0 for p in pk], axis=0)
        n = len(regions)
        cv = self.cols

        def at(col, pos):
            out = np.full(n, np.nan)
            out[ok] = cv[col][pos[ok]]
            return out

        f0, d0, c0 = (np.where(ok, self.codes[k][np.maximum(p0, 0)], np.nan) for k in ("ffmc_r", "dmc_r", "dc_r"))
        fa, da, ca = f0.copy(), d0.copy(), c0.copy()
        fq, dq, cq = f0.copy(), d0.copy(), c0.copy()
        dp_sum = np.zeros(n)
        last_wet = np.full(n, -1)
        for k in range(1, lead + 1):
            pos = pk[k - 1]
            a = {v: at(v, pos) for v in BASE}
            q = {v: np.asarray(paths[k - 1][v], float) for v in BASE}
            month = (issue_dates + pd.Timedelta(days=k)).dt.month.to_numpy()
            fa = F.ffmc_step(fa, a["t2m"], a["rh"], a["wind"], np.maximum(a["precip"], 0))
            da = F.dmc_step(da, a["t2m"], a["rh"], np.maximum(a["precip"], 0), month)
            ca = F.dc_step(ca, a["t2m"], np.maximum(a["precip"], 0), month)
            fq = F.ffmc_step(fq, q["t2m"], q["rh"], q["wind"], q["precip"])
            dq = F.dmc_step(dq, q["t2m"], q["rh"], q["precip"], month)
            cq = F.dc_step(cq, q["t2m"], q["precip"], month)
            dp_sum += q["precip"] - a["precip"]
            last_wet = np.where(q["precip"] >= RAIN_DAY_MM, k, last_wet)
        tgt = pk[-1]
        a, q = {v: at(v, tgt) for v in BASE}, {v: np.asarray(paths[-1][v], float) for v in BASE}
        isi_a, isi_q = F.isi(fa, a["wind"]), F.isi(fq, q["wind"])
        bui_a, bui_q = F.bui(da, ca), F.bui(dq, cq)
        fwi_a, fwi_q = F.fwi(isi_a, bui_a), F.fwi(isi_q, bui_q)
        out = pd.DataFrame(index=range(n))
        base = {c: at(c, tgt) for c in ("ffmc", "dmc", "dc", "isi", "bui", "fwi", "rain30", "rain90", "fwi_anom",
                                       "dc_anom", "tmax_anom", "vpd_anom", "rain90_anom", "vpd")}
        out["ffmc"] = np.clip(base["ffmc"] + (fq - fa), 0, 101)
        out["dmc"] = np.maximum(base["dmc"] + (dq - da), 0)
        out["dc"] = np.maximum(base["dc"] + (cq - ca), 0)
        out["bui"] = np.maximum(base["bui"] + (bui_q - bui_a), 0)
        isi_new = np.maximum(base["isi"] + (isi_q - isi_a), 0)
        fwi_new = np.maximum(base["fwi"] + (fwi_q - fwi_a), 0)
        out["log_isi"], out["log_fwi"] = np.log1p(isi_new), np.log1p(fwi_new)
        for v in ("t2m", "rh", "wind", "precip", "tmax", "gust", "td"):
            out[v] = q[v]
        vpd_new = np.maximum(saturation_vapour_pressure(q["t2m"]) - saturation_vapour_pressure(q["td"]), 0.0)
        out["vpd"] = vpd_new
        out["rain30"] = np.maximum(base["rain30"] + dp_sum, 0)
        out["rain90"] = np.maximum(base["rain90"] + dp_sum, 0)
        out["rain90_anom"] = base["rain90_anom"] + dp_sum
        dsr0 = np.expm1(at("log_days_since_rain", p0))
        dsr = np.where(last_wet > 0, lead - last_wet, np.minimum(dsr0 + lead, DAYS_SINCE_RAIN_CAP))
        out["log_days_since_rain"] = np.log1p(dsr)
        out["fwi_anom"] = base["fwi_anom"] + (fwi_new - base["fwi"])
        out["dc_anom"] = base["dc_anom"] + (out["dc"].to_numpy() - base["dc"])
        out["tmax_anom"] = base["tmax_anom"] + (q["tmax"] - a["tmax"])
        out["vpd_anom"] = base["vpd_anom"] + (vpd_new - base["vpd"])
        out["fosberg_own"] = fosberg_index(q["t2m"], q["rh"], q["wind"])
        out.loc[~ok, :] = np.nan
        return out

    def analysed_paths(self, regions: np.ndarray, issue_dates: pd.Series, lead: int) -> list[dict]:
        issue_dates = pd.to_datetime(pd.Series(np.asarray(issue_dates)))
        paths = []
        for k in range(1, lead + 1):
            pos = self._pos(regions, issue_dates + pd.Timedelta(days=k))
            paths.append({v: np.where(pos >= 0, self.cols[v][np.maximum(pos, 0)], np.nan) for v in BASE})
        return paths

    def noisy(self, regions: np.ndarray, issue_dates: pd.Series, lead: int, errors: ErrorModel,
              rng: np.random.Generator, correction: BiasCorrection | None = None) -> pd.DataFrame:
        """Target-day features with real forecast errors on each forecast day (and the production bias correction)."""
        issue_dates = pd.to_datetime(pd.Series(np.asarray(issue_dates)))
        paths = []
        for k, a in enumerate(self.analysed_paths(regions, issue_dates, lead), start=1):
            month = (issue_dates + pd.Timedelta(days=k)).dt.month.to_numpy()
            wet = np.nan_to_num(a["precip"]) >= RAIN_DAY_MM
            e = errors.draw(np.asarray(regions), k - 1, wet, month, rng)
            q = {v: a[v] + e[v] for v in BASE}
            if correction is not None:
                q = correction.apply(q, np.asarray(regions), month, k - 1)
            paths.append(clip_weather(q))
        return self.features(regions, issue_dates, lead, paths)
