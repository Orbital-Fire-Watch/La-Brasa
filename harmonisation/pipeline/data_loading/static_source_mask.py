"""Ortsmaske fuer statische Waermequellen (Ersatz fuer die im NRT fehlende Spalte `type`)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

CELL_COLUMNS = ["cell_lat", "cell_lon"]


def add_mask_cells(hotspots: pd.DataFrame, cell_deg: float) -> pd.DataFrame:
    """Ergaenzt die ganzzahligen Zellindizes (`cell_lat`, `cell_lon`) der Ortsmaske."""
    cells = hotspots.copy()
    cells["cell_lat"] = np.floor(cells["latitude"] / cell_deg).astype("int64")
    cells["cell_lon"] = np.floor(cells["longitude"] / cell_deg).astype("int64")
    return cells


def expand_to_neighbour_cells(core_cells: pd.DataFrame, ring: int) -> pd.DataFrame:
    """Legt um jede Kernzelle einen Ring aus Nachbarzellen (ring = 1 ergibt 3 x 3 Zellen)."""
    offsets = [(dlat, dlon) for dlat in range(-ring, ring + 1) for dlon in range(-ring, ring + 1)]
    parts = [core_cells.assign(cell_lat=core_cells["cell_lat"] + dlat, cell_lon=core_cells["cell_lon"] + dlon)
             for dlat, dlon in offsets]
    return pd.concat(parts, ignore_index=True)[CELL_COLUMNS].drop_duplicates()


def learn_static_mask(typed_hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Lernt aus Archivzeilen mit bekanntem `type`, an welchen Orten statische Quellen liegen.

    Idee: Fabriken, Fackeln und Kraftwerke stehen immer am selben Ort, Vegetationsfeuer nicht.
    Eine Zelle wird Kernzelle, wenn dort mindestens `mask_min_static_detections` statische
    Erkennungen liegen und diese mindestens `mask_min_static_share` aller Erkennungen der Zelle
    ausmachen. Die zweite Bedingung schuetzt Zellen, in denen es auch oft echt brennt.
    Um jede Kernzelle kommt ein Ring aus Nachbarzellen, weil die Pixelmitte eines Satelliten
    von Ueberflug zu Ueberflug um einige hundert Meter wandert.

    Eingang: nur Zeilen mit bekanntem `type` (Archiv). Das NRT darf hier nie einfliessen,
    sonst wuerde die Maske aus den Daten lernen, die sie spaeter bewerten soll.
    Ausgang: eine Zeile je maskierter Zelle mit `is_core`, `n_static`, `static_share`.
    Beleg: data_analysis/05_static.py (Recall 94,5 %, 1,7 % faelschlich entfernte Feuer bei SNPP).
    """
    params = config["static_sources"]
    cells = add_mask_cells(typed_hotspots, params["mask_cell_deg"])
    cells["is_static"] = cells["type"] != params["vegetation_fire_type"]
    stats = cells.groupby(CELL_COLUMNS)["is_static"].agg(n_static="sum", static_share="mean").reset_index()
    core = stats[(stats["n_static"] >= params["mask_min_static_detections"])
                 & (stats["static_share"] >= params["mask_min_static_share"])]
    mask = expand_to_neighbour_cells(core, params["mask_neighbour_cells"])
    mask = mask.merge(core, on=CELL_COLUMNS, how="left")
    mask["is_core"] = mask["n_static"].notna()
    return mask.sort_values(CELL_COLUMNS).reset_index(drop=True)


def flag_hotspots_in_mask(hotspots: pd.DataFrame, mask: pd.DataFrame, cell_deg: float) -> np.ndarray:
    """Gibt je Hotspot zurueck, ob er in einer maskierten Zelle liegt."""
    cells = add_mask_cells(hotspots[["latitude", "longitude"]], cell_deg)
    masked = pd.MultiIndex.from_frame(mask[CELL_COLUMNS])
    return pd.MultiIndex.from_frame(cells[CELL_COLUMNS]).isin(masked)


def evaluate_mask_on_holdout(typed_hotspots: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """Prueft die Maske ehrlich: lernen bis zum Jahr vor `holdout_first_year`, pruefen danach.

    Recall = Anteil der statischen Erkennungen (type != 0) im Pruefzeitraum, die die Maske trifft.
    Fehlentfernung = Anteil der echten Feuer (type = 0), die die Maske faelschlich entfernt.
    Beides wird gesamt und je Sensor berichtet (MODIS trifft die Maske wegen der groesseren
    Pixel seltener).
    """
    params = config["static_sources"]
    years = pd.to_datetime(typed_hotspots["acq_date"]).dt.year
    train, test = typed_hotspots[years < params["holdout_first_year"]], typed_hotspots[years >= params["holdout_first_year"]]
    hit = flag_hotspots_in_mask(test, learn_static_mask(train, config), params["mask_cell_deg"])
    is_static = (test["type"] != params["vegetation_fire_type"]).to_numpy()

    def rates(selection: np.ndarray) -> dict[str, float]:
        """Recall und Fehlentfernung fuer eine Teilmenge der Pruefzeilen."""
        return {"recall": float(hit[selection & is_static].mean()),
                "false_removal": float(hit[selection & ~is_static].mean()),
                "n_static": int((selection & is_static).sum()), "n_fire": int((selection & ~is_static).sum())}

    result = {"all": rates(np.ones(len(test), dtype=bool))}
    for sensor in sorted(test["sensor"].unique()):
        result[sensor] = rates((test["sensor"] == sensor).to_numpy())
    return result
