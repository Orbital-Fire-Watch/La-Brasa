"""Schritt 1: jedem Hotspot eine NUTS-2-Region zuordnen (lokal, ohne API).

Quelle: Eurostat GISCO, NUTS 2021, 1:10 Mio, EPSG:4326
        geo/NUTS_RG_10M_2021_4326_LEVL_2.geojson
Vorgehen: Point-in-Polygon mit shapely STRtree. Punkte ohne Treffer, die hoechstens
0,05 Grad (~5 km) von einer Region entfernt liegen (Kueste, vereinfachte Grenzen),
bekommen die naechste Region. Alles andere (Meer, Marokko, Andorra) bleibt NULL.

Schreibt region_id und country in cache/iberia.parquet zurueck.
"""
import json

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

from common import IBERIA, ROOT, save

gj = json.loads((ROOT / "geo" / "NUTS_RG_10M_2021_4326_LEVL_2.geojson").read_text())
ids = np.array([f["properties"]["NUTS_ID"] for f in gj["features"]])
names = {f["properties"]["NUTS_ID"]: f["properties"]["NAME_LATN"] for f in gj["features"]}
geoms = np.array([shape(f["geometry"]) for f in gj["features"]])
tree = shapely.STRtree(geoms)

df = pd.read_parquet(IBERIA).drop(columns=["region_id", "country"], errors="ignore")
pts = shapely.points(df.longitude.values, df.latitude.values)

region = np.full(len(df), None, dtype=object)
pi, gi = tree.query(pts, predicate="within")
region[pi] = ids[gi]
inside = len(pi)

miss = np.flatnonzero(pd.isna(region))
near_p, near_g = tree.query_nearest(pts[miss], max_distance=0.05, all_matches=False)
region[miss[near_p]] = ids[near_g]

df["region_id"] = region
df["country"] = df.region_id.str[:2]
df.to_parquet(IBERIA, compression="zstd")

tab = (df.groupby(["region_id", "sat"], dropna=False).size().unstack(fill_value=0)
       .assign(total=lambda d: d.sum(axis=1)).sort_values("total", ascending=False))
tab.insert(0, "name", [names.get(i, "ohne Region") for i in tab.index])
print(tab.to_string())
print("innerhalb:", inside, "| ueber Naehe ergaenzt:", len(near_p),
      "| ohne Region:", int(df.region_id.isna().sum()), "von", len(df))
save("nuts", {
    "n_total": len(df), "n_within": inside, "n_nearest": int(len(near_p)),
    "n_null": int(df.region_id.isna().sum()),
    "by_country": df.groupby("country", dropna=False).size().rename(index=lambda x: x if isinstance(x, str) else "NULL").to_dict(),
    "regions": [{"region_id": (i if isinstance(i, str) else None), "name": r["name"],
                 "Terra": int(r.get("Terra", 0)), "Aqua": int(r.get("Aqua", 0)),
                 "SNPP": int(r.get("SNPP", 0))} for i, r in tab.iterrows()],
})
