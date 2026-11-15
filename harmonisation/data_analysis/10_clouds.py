"""Schritt 10: Erklaeren Wolken, warum VIIRS an manchen Tagen kein Feuer sieht?

Daten: hotspots_harmonised (VIIRS), Bewoelkung je 0,25-Grad-Zelle und Tag zu den VIIRS-Ueberfluegen
(data/raw/clouds/cloud_daily.parquet, pipeline/ingestion/fetch_clouds.py, Meteomatics).
Ein Tag gilt als bewoelkt, wenn Tag- UND Nacht-Ueberflug mindestens `--threshold` bedeckt sind
(wie CLOUDY_THRESHOLD im Frontend, frontend/lib/uiConfig.ts).

Festgelegt am 15.11.2026 VOR der Messung:
  C1  Bruecken: Zelle mit >= 100 MW (VIIRS) am Vor- und am Folgetag. Tage dazwischen, an denen VIIRS
      in der Zelle nichts meldet, sind mindestens doppelt so oft bewoelkt wie Tage dazwischen mit Meldung.
  C2  Anteil bewoelkter Region-Tage je Monat bei der gewaehlten Schwelle. Wird nur berichtet, keine Grenze.
  C3  Anteil der gemessenen Region-Tage mit 0 Feuern, die bewoelkt sind. Wird nur berichtet.

Aufruf:  .venv/bin/python data_analysis/10_clouds.py [--threshold 0.5]
Schreibt results/clouds.json.
"""
import argparse
import json
import math

import pandas as pd
from shapely.geometry import box, shape

from common import RAW, ROOT, save

HARMONISED = ROOT.parent.parent / "data" / "harmonised"
REGIONS = ROOT.parent.parent / "backend" / "assets" / "nuts2_iberia.geojson"
CELL_DEG = 0.25
BRIDGE_MW = 100.0
C1_MIN_RATIO = 2.0


def cloudy(clouds: pd.DataFrame, threshold: float) -> pd.Series:
    """Wahr, wenn beide Ueberfluege bekannt und mindestens `threshold` bedeckt sind."""
    return (clouds["cloud_day"] >= threshold) & (clouds["cloud_night"] >= threshold)


def bridges(hotspots: pd.DataFrame) -> pd.DataFrame:
    """Zelle x Tag d, an dem d-1 und d+1 je >= BRIDGE_MW haben; `empty` = VIIRS meldet an d nichts."""
    frp = hotspots.groupby(["cell_id", "date"])["frp"].sum()
    strong = set(frp[frp >= BRIDGE_MW].index)
    one = pd.Timedelta(days=1)
    rows = [(cell, day + one) for cell, day in strong if (cell, day + 2 * one) in strong]
    out = pd.DataFrame(rows, columns=["cell_id", "date"])
    out["empty"] = [(c, d) not in frp.index for c, d in rows]
    return out


def measure_c1(hotspots: pd.DataFrame, clouds: pd.DataFrame, threshold: float) -> dict:
    merged = bridges(hotspots).merge(clouds.assign(cloudy=cloudy(clouds, threshold)), on=["cell_id", "date"])
    share = merged.groupby("empty")["cloudy"].mean()
    empty, filled = float(share.get(True, float("nan"))), float(share.get(False, float("nan")))
    ratio = empty / filled if filled > 0 else float("inf")
    return {"n_bridges": len(merged), "n_empty": int(merged["empty"].sum()), "cloudy_share_empty": empty,
            "cloudy_share_filled": filled, "ratio": ratio, "min_ratio": C1_MIN_RATIO, "passed": bool(ratio >= C1_MIN_RATIO)}


def region_cells() -> pd.DataFrame:
    """region_id x cell_id: jede Zelle, die die Region beruehrt (wie das Backend, services/clouds.py)."""
    rows = []
    for feature in json.loads(REGIONS.read_text(encoding="utf-8"))["features"]:
        geom = shape(feature["geometry"])
        west, south, east, north = geom.bounds
        for i in range(math.floor(south / CELL_DEG), math.floor(north / CELL_DEG) + 1):
            for j in range(math.floor(west / CELL_DEG), math.floor(east / CELL_DEG) + 1):
                if geom.intersects(box(j * CELL_DEG, i * CELL_DEG, (j + 1) * CELL_DEG, (i + 1) * CELL_DEG)):
                    rows.append((feature["properties"]["NUTS_ID"], f"{i}_{j}"))
    return pd.DataFrame(rows, columns=["region_id", "cell_id"])


def region_days(clouds: pd.DataFrame, threshold: float) -> pd.DataFrame:
    means = clouds.merge(region_cells(), on="cell_id").groupby(["region_id", "date"])[["cloud_day", "cloud_night"]].mean()
    return means.assign(cloudy=cloudy(means, threshold)).reset_index()


def measure_c2_c3(clouds: pd.DataFrame, threshold: float) -> dict:
    days = region_days(clouds, threshold)
    by_month = days.groupby(days["date"].dt.month)["cloudy"].mean()
    daily = pd.read_parquet(HARMONISED / "activity_daily_harmonised.parquet", columns=["region_id", "date", "n_harm", "reliability"])
    daily["date"] = pd.to_datetime(daily["date"])
    zero = daily[(daily["reliability"] == "measured") & (daily["n_harm"] == 0)].merge(days, on=["region_id", "date"])
    return {"c2_cloudy_share_by_month": {int(m): float(v) for m, v in by_month.items()},
            "c2_cloudy_share_all": float(days["cloudy"].mean()),
            "c3_zero_days": len(zero), "c3_zero_days_cloudy_share": float(zero["cloudy"].mean()) if len(zero) else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threshold", type=float, default=0.5)
    threshold = parser.parse_args().threshold
    clouds = pd.read_parquet(RAW / "clouds" / "cloud_daily.parquet")
    clouds["date"] = pd.to_datetime(clouds["date"])
    hotspots = pd.read_parquet(HARMONISED / "hotspots_harmonised.parquet", columns=["cell_id", "obs_date", "sensor", "frp"])
    hotspots = hotspots[hotspots["sensor"] == "VIIRS"].rename(columns={"obs_date": "date"})
    hotspots["date"] = pd.to_datetime(hotspots["date"])
    result = {"threshold": threshold, "cloud_days": [str(clouds["date"].min().date()), str(clouds["date"].max().date())],
              "c1": measure_c1(hotspots, clouds, threshold), **measure_c2_c3(clouds, threshold)}
    print(json.dumps(result, indent=1))
    save("clouds", result)


if __name__ == "__main__":
    main()
