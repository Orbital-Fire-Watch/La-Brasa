"""Abfragen auf Punktebene: Hotspots einer Flaeche und eines Zeitraums auswaehlen, summieren, als CSV schreiben."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Polygon

KM_PER_DEGREE_LAT = 110.57
KM_PER_DEGREE_LON_EQUATOR = 111.32
CSV_COLUMNS = ["hotspot_id", "latitude", "longitude", "acq_datetime_utc", "obs_date", "satellite", "sensor", "source",
               "daynight", "frp", "frp_class", "confidence_class", "confidence_raw", "scan", "track", "region_id", "country",
               "in_series_n", "weight_n", "weight_frp", "basis_count"]


def polygon_of(area: dict[str, Any]) -> Polygon | None:
    """Macht aus einer Flaechenangabe ein Polygon (bbox = [lon_min, lat_min, lon_max, lat_max] oder Punktliste)."""
    if "bbox" in area:
        lon_min, lat_min, lon_max, lat_max = area["bbox"]
        return Polygon([(lon_min, lat_min), (lon_max, lat_min), (lon_max, lat_max), (lon_min, lat_max)])
    if "polygon" in area:
        return Polygon(area["polygon"])
    return None


def approximate_area_km2(area: dict[str, Any]) -> float | None:
    """Naeherung der Flaeche in km^2 (Grad in Kilometer umgerechnet auf der mittleren Breite)."""
    if "point" in area:
        return float(np.pi * area["radius_km"] ** 2)
    polygon = polygon_of(area)
    if polygon is None:
        return None
    lon_km = KM_PER_DEGREE_LON_EQUATOR * np.cos(np.radians(polygon.centroid.y))
    return float(polygon.area * KM_PER_DEGREE_LAT * lon_km)


def is_inside_area(hotspots: pd.DataFrame, area: dict[str, Any]) -> np.ndarray:
    """Wahr je Hotspot, wenn er in der Flaeche liegt (Region, Zelle, Umkreis, Rechteck oder Polygon)."""
    for key in ("region_id", "cell_id", "country"):
        if key in area:
            return (hotspots[key] == area[key]).fillna(False).to_numpy()
    if "point" in area:
        lon, lat = area["point"]
        dx = (hotspots["longitude"] - lon) * KM_PER_DEGREE_LON_EQUATOR * np.cos(np.radians(lat))
        dy = (hotspots["latitude"] - lat) * KM_PER_DEGREE_LAT
        return (np.hypot(dx, dy) <= area["radius_km"]).to_numpy()
    points = shapely.points(hotspots["longitude"].to_numpy(), hotspots["latitude"].to_numpy())
    return shapely.contains(polygon_of(area), points)


def select_hotspots(hotspots: pd.DataFrame, area: dict[str, Any] | None = None,
                    period: tuple[str, str] | None = None) -> pd.DataFrame:
    """Waehlt die Hotspots einer Flaeche und eines Zeitraums aus.

    `area` ist eines von: {"bbox": [lon_min, lat_min, lon_max, lat_max]}, {"polygon": [[lon, lat], ...]},
    {"point": [lon, lat], "radius_km": r}, {"region_id": ...}, {"cell_id": ...}, {"country": ...}.
    `period` ist (erster Tag, letzter Tag) und bezieht sich auf `obs_date`, den Tag, zu dem ein
    Punkt zaehlt. Das Ergebnis enthaelt alle Sensoren. Fuer eine Karte ohne Doppelte ab 2012
    zusaetzlich auf `in_series_n` filtern.
    """
    selected = np.ones(len(hotspots), dtype=bool)
    if period is not None:
        selected &= hotspots["obs_date"].between(pd.Timestamp(period[0]), pd.Timestamp(period[1])).to_numpy()
    if area is not None:
        selected &= is_inside_area(hotspots, area)
    return hotspots[selected]


def aggregate_hotspots(hotspots: pd.DataFrame, area: dict[str, Any] | None = None, period: tuple[str, str] | None = None,
                       by_day: bool = False) -> pd.DataFrame:
    """Summiert die harmonisierten Groessen ueber eine beliebige Flaeche und einen Zeitraum.

    `n_harm` = SUM(weight_n) und `frp_harm` = SUM(frp x weight_frp). Das funktioniert, weil die
    Umrechnung linear ist und der Faktor schon auf jedem Punkt liegt. Ueber eine NUTS-2-Region
    ergibt die Summe exakt den Wert der Tagestabelle.
    Grenzen: Nur additive Groessen. Die Summe ist ein Erwartungswert. Tage ohne Punkte erscheinen
    nicht (0 oder keine Daten entscheidet `day_status`). Filter nach `frp_class` oder
    `confidence_class` sind vor 2012 falsch skaliert, weil die Faktoren nur fuer alle Feuer
    zusammen kalibriert sind. Die Unsicherheit liefert `estimate_uncertainty`.
    """
    points = select_hotspots(hotspots, area, period)
    points = points.assign(n_harm=points["weight_n"], frp_harm=points["frp"] * points["weight_frp"],
                           n_points_in_series=points["in_series_n"].astype(int), n_points_all=1,
                           n_measured=(points["in_series_n"] & (points["basis_count"] == "viirs_measured")).astype(int))
    columns = ["n_harm", "frp_harm", "n_points_in_series", "n_points_all", "n_measured"]
    if by_day:
        return points.groupby("obs_date")[columns].sum().reset_index()
    return points[columns].sum().to_frame().T


def write_hotspots_csv(hotspots: pd.DataFrame, path: Path | str, columns: list[str] | None = None) -> int:
    """Schreibt ausgewaehlte Hotspots als CSV (fuer den Download) und gibt die Zeilenzahl zurueck."""
    table = hotspots[columns or CSV_COLUMNS]
    table.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    return len(table)
