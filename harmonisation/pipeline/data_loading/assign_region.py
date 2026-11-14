"""Zuordnung jedes Hotspots zu einer NUTS-2-Region (lokal, ohne externe API)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape


def load_nuts2_polygons(geojson_path: str, id_property: str) -> tuple[np.ndarray, np.ndarray]:
    """Liest die NUTS-2-Polygone und gibt (Regions-IDs, Geometrien) zurueck."""
    features = json.loads(Path(geojson_path).read_text(encoding="utf-8"))["features"]
    region_ids = np.array([feature["properties"][id_property] for feature in features])
    geometries = np.array([shape(feature["geometry"]) for feature in features])
    return region_ids, geometries


def assign_nuts2_region(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt `region_id` (NUTS-2) und `country` per Punkt-in-Polygon-Test.

    Vorgehen in zwei Schritten:
    1. Jeder Punkt bekommt die Region, in deren Polygon er liegt (raeumlicher Index STRtree,
       dadurch Sekunden statt Stunden fuer Hunderttausende Punkte).
    2. Punkte ohne Treffer, die hoechstens `coast_tolerance_deg` von einer Region entfernt
       liegen, bekommen die naechste Region. Das betrifft Kuestenpunkte: die Grenzen im
       Massstab 1:10 Mio sind vereinfacht, ein Feuer am Strand liegt rechnerisch im Meer.
    Alles Weitere (offenes Meer, Gebiete ausserhalb von NUTS) bleibt ohne Region (NULL).

    `country` sind die ersten zwei Zeichen des NUTS-Codes. So koennen sich Land und Region
    nie widersprechen, und es braucht keine zweite Quelle.
    Koordinatensystem: EPSG:4326 (Laenge/Breite), wie in den FIRMS-Daten.
    """
    region_ids, geometries = load_nuts2_polygons(config["paths"]["nuts_geojson"], config["nuts"]["id_property"])
    tree = shapely.STRtree(geometries)
    points = shapely.points(hotspots["longitude"].to_numpy(), hotspots["latitude"].to_numpy())

    region = np.full(len(hotspots), None, dtype=object)
    point_index, polygon_index = tree.query(points, predicate="within")
    region[point_index] = region_ids[polygon_index]

    missing = np.flatnonzero(pd.isna(region))
    near_point, near_polygon = tree.query_nearest(points[missing], max_distance=config["nuts"]["coast_tolerance_deg"],
                                                  all_matches=False)
    region[missing[near_point]] = region_ids[near_polygon]

    result = hotspots.copy()
    result["region_id"] = pd.array(region, dtype="string")
    result["country"] = result["region_id"].str[:2]
    return result


def load_region_names(config: dict[str, Any]) -> dict[str, str]:
    """Liest die Klarnamen der NUTS-2-Regionen (z. B. "ES30" -> "Comunidad de Madrid") aus der GeoJSON."""
    features = json.loads(Path(config["paths"]["nuts_geojson"]).read_text(encoding="utf-8"))["features"]
    nuts = config["nuts"]
    return {feature["properties"][nuts["id_property"]]: feature["properties"][nuts["name_property"]] for feature in features}
