"""Abgeleitete Merkmale je Hotspot: FRP-Klasse, Konfidenzklasse, lokale Sonnenzeit."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

HOURS_PER_DAY = 24.0
DEGREES_PER_HOUR = 15.0      # die Erde dreht sich 15 Grad pro Stunde


def add_frp_class(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Teilt jeden Hotspot nach seiner Strahlungsleistung (FRP) in low / mid / high ein.

    Die Grenzen (Standard 10 und 50 MW) sind feste Megawatt-Werte, keine Quantile. Damit bedeutet
    eine Klasse bei beiden Sensoren physikalisch dasselbe. Die Klassenanteile sind trotzdem nicht
    vergleichbar: VIIRS erkennt Feuer ab unter 1 MW, MODIS erst ab 4 bis 30 MW, also hat VIIRS
    viel mehr "low".
    Die Klasse ist ein beschreibendes Merkmal fuer Frontend und Filter. In die Kalibrierung geht
    sie nicht ein: Faktoren je FRP-Klasse waren im Test nicht besser als ein Faktor je Region
    (data_analysis/06_strategies.py, M14: Fehler x 1,51 gegen x 1,49).
    """
    params = config["classification"]
    labels = np.array(params["frp_class_labels"], dtype=object)
    frp = hotspots["frp"].to_numpy(dtype=float)
    classes = labels[np.digitize(np.nan_to_num(frp), params["frp_class_bounds_mw"])]
    classes[np.isnan(frp)] = None
    return hotspots.assign(frp_class=pd.array(classes, dtype="string"))


def add_confidence_class(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Vereinheitlicht `confidence` zu low / nominal / high und behaelt den Originalwert.

    MODIS liefert eine Zahl 0-100 (Grenzen 30 und 80, die FIRMS-Schwellen), VIIRS die Buchstaben
    l / n / h. Der Originalwert bleibt als `confidence_raw` (Text) erhalten.
    Wichtig fuer die Auswertung: Die Klassen sind zwischen den Sensoren NICHT vergleichbar.
    Bei VIIRS bedeutet "h" nur, dass der Helligkeitskanal bei 367 K gesaettigt ist (alle h-Zeilen
    haben genau diesen Wert), bei MODIS steigt die Zahl mit der Helligkeit. Die Klasse darf darum
    nur zusammen mit `sensor` ausgewertet werden. Beleg: data_analysis/02_columns.py.
    """
    params = config["classification"]
    labels = np.array(params["confidence_labels"], dtype=object)
    raw = hotspots["confidence"].astype("string")
    numeric = pd.to_numeric(raw, errors="coerce")
    modis_class = pd.Series(labels[np.digitize(numeric.fillna(0), params["modis_confidence_bounds"])],
                            index=hotspots.index).where(numeric.notna())
    viirs_class = raw.str.lower().map(params["viirs_confidence_map"])
    is_modis = hotspots["sensor"] == "MODIS"
    result = hotspots.assign(confidence_class=modis_class.where(is_modis, viirs_class).astype("string"))
    return result.rename(columns={"confidence": "confidence_raw"})


def add_local_solar_hour(hotspots: pd.DataFrame) -> pd.DataFrame:
    """Ergaenzt die lokale Sonnenzeit des Ueberflugs in Dezimalstunden (0 bis 24).

    Formel: UTC-Stunde + Laenge / 15, modulo 24. Die Sonnenzeit haengt nur von der geografischen
    Laenge ab und nicht von Zeitzonen oder Sommerzeit. Damit lassen sich Satelliten vergleichen
    (Aqua und SNPP fliegen um etwa 13 Uhr, Terra um etwa 11 Uhr) und eine Bahndrift erkennen.
    """
    acq_time = hotspots["acq_time"].astype(str).str.zfill(4)
    utc_hour = acq_time.str[:2].astype(int) + acq_time.str[2:].astype(int) / 60.0
    solar = (utc_hour + hotspots["longitude"] / DEGREES_PER_HOUR) % HOURS_PER_DAY
    return hotspots.assign(local_solar_hour=solar.round(3))
