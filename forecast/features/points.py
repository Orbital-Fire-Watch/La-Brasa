"""Fire-weighted weather points per NUTS-2 region.

Regions are large, so a plain area mean dilutes the weather where fires actually burn.
Instead we take, per region, the 0.25° cells with the most VIIRS detections in the training
period and weight each cell by its share of those detections.

cell_id is "<lat_index>_<lon_index>" with index = floor(coordinate / 0.25) (harmonisation
data dictionary), so the cell centre is (index + 0.5) * 0.25.
"""
from __future__ import annotations

import pandas as pd

CELL_SIZE_DEG = 0.25


def cell_centre(cell_id: pd.Series) -> pd.DataFrame:
    parts = cell_id.str.split("_", expand=True).astype(int)
    return pd.DataFrame({
        "lat": (parts[0] + 0.5) * CELL_SIZE_DEG,
        "lon": (parts[1] + 0.5) * CELL_SIZE_DEG,
    }, index=cell_id.index)


def select_points(hotspots: pd.DataFrame, training_start: str, training_end: str,
                  max_cells_per_region: int, min_share_of_region: float = 0.0) -> pd.DataFrame:
    """Return one row per selected cell: region_id, cell_id, lat, lon, n_detections, weight.

    Weights sum to 1 per region. Only VIIRS detections inside the training period count,
    so the selection does not use information from the test years.
    """
    obs = pd.to_datetime(hotspots["obs_date"])
    viirs = hotspots[(hotspots["sensor"] == "VIIRS") & hotspots["region_id"].notna()
                     & (obs >= pd.Timestamp(training_start)) & (obs <= pd.Timestamp(training_end))]
    counts = (viirs.groupby(["region_id", "cell_id"]).size().rename("n_detections").reset_index())
    counts["share"] = counts["n_detections"] / counts.groupby("region_id")["n_detections"].transform("sum")
    counts = counts[counts["share"] >= min_share_of_region]
    counts = (counts.sort_values(["region_id", "n_detections", "cell_id"], ascending=[True, False, True])
              .groupby("region_id").head(max_cells_per_region).reset_index(drop=True))
    counts["weight"] = counts["n_detections"] / counts.groupby("region_id")["n_detections"].transform("sum")
    centres = cell_centre(counts["cell_id"])
    out = pd.concat([counts[["region_id", "cell_id"]], centres, counts[["n_detections", "weight"]]], axis=1)
    return out.sort_values(["region_id", "weight", "cell_id"], ascending=[True, False, True]).reset_index(drop=True)


def aggregate_to_regions(point_weather: pd.DataFrame, points: pd.DataFrame,
                         value_columns: list[str]) -> pd.DataFrame:
    """Weighted mean of point weather per region and valid time.

    point_weather needs lat, lon, validdate and the value columns. If a value is missing at some
    points, the remaining weights are renormalised; if missing everywhere, the result is empty.
    """
    key = points[["region_id", "lat", "lon", "weight"]].copy()
    key[["lat", "lon"]] = key[["lat", "lon"]].round(4)
    pw = point_weather.copy()
    pw[["lat", "lon"]] = pw[["lat", "lon"]].round(4)
    merged = pw.merge(key, on=["lat", "lon"], how="inner")
    rows = []
    for (region, valid), grp in merged.groupby(["region_id", "validdate"], sort=True):
        row = {"region_id": region, "validdate": valid}
        for col in value_columns:
            ok = grp[col].notna()
            w = grp.loc[ok, "weight"]
            row[col] = float((grp.loc[ok, col] * w).sum() / w.sum()) if w.sum() > 0 else float("nan")
        rows.append(row)
    return pd.DataFrame(rows, columns=["region_id", "validdate", *value_columns])
