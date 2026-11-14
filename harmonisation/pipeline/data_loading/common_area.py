"""Gemeinsames Gebiet: alle Satelliten zaehlen nur dort, wo auch die Referenz-Downloads (MODIS, SNPP) Daten haben."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

CELL_COLUMNS = ["area_lat", "area_lon"]


def area_cells_of(hotspots: pd.DataFrame, cell_deg: float) -> pd.MultiIndex:
    """Zellindizes (floor(Koordinate / Zellgroesse)) je Hotspot."""
    lat = np.floor(hotspots["latitude"].to_numpy() / cell_deg).astype("int64")
    lon = np.floor(hotspots["longitude"].to_numpy() / cell_deg).astype("int64")
    return pd.MultiIndex.from_arrays([lat, lon], names=CELL_COLUMNS)


def learn_common_area(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Lernt das Gebiet der Referenz-Downloads: alle Rasterzellen mit mindestens einer Erkennung von Terra, Aqua oder SNPP.

    Warum: FIRMS liefert genau das Gebiet, das beim Download gewaehlt wurde. Die MODIS- und
    SNPP-Dateien decken Spanien, Portugal und einen Rand in Suedwestfrankreich ab, aber kein
    Rechteck (in Frankreich nordlich von etwa 43,5 Grad fehlen sie). Die NOAA-Downloads sind ein
    groesseres Rechteck. Ohne Angleichung meldeten NOAA-20/21 in den Randregionen Feuer, die SNPP und
    MODIS gar nicht sehen koennen, und das VIIRS-Mittel stiege dort an (Voranalyse 09).
    Gelernt wird aus allen Erkennungen der Referenzsatelliten ueber 26 Jahre, auch statischen und
    NRT: Eine Zelle innerhalb des Gebiets ohne jede Erkennung in dieser Zeit ist praktisch
    ausgeschlossen. Ausgang: eine Zeile je Zelle des Gebiets.
    """
    params = config["common_area"]
    reference = hotspots[hotspots["satellite"].isin(params["reference_satellites"])]
    cells = area_cells_of(reference, params["cell_deg"]).unique()
    return cells.to_frame(index=False).sort_values(CELL_COLUMNS).reset_index(drop=True)


def is_inside_common_area(hotspots: pd.DataFrame, area: pd.DataFrame, config: dict[str, Any]) -> np.ndarray:
    """Wahr je Hotspot, wenn er in einer Zelle des gemeinsamen Gebiets liegt."""
    return area_cells_of(hotspots, config["common_area"]["cell_deg"]).isin(pd.MultiIndex.from_frame(area[CELL_COLUMNS]))
