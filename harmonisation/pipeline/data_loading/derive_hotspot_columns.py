"""Abgeleitete Spalten je Hotspot: ID, Zeitstempel, Beobachtungstag, Zelle, Pixelflaeche."""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

DEGREES_PER_HOUR = 15.0      # die Erde dreht sich 15 Grad pro Stunde
ID_LENGTH = 16
COORDINATE_DECIMALS = 5      # FIRMS liefert Koordinaten mit 5 Nachkommastellen


def add_hotspot_id(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt `hotspot_id`: einen stabilen Hash aus Satellit, Koordinaten, Datum und Uhrzeit.

    Dieselben Felder bilden den Dedup-Schluessel, die ID ist also je Zeile eindeutig. Sie haengt nur
    von der Messung ab und nicht von Reihenfolge oder Lauf. Ein Punkt behaelt seine ID auch dann,
    wenn spaeter neue Daten dazukommen. Das Frontend kann damit Punkte auswaehlen, verlinken und
    beim Nachladen wiedererkennen.
    """
    key = (hotspots["satellite"].astype(str) + "|" + hotspots["latitude"].round(COORDINATE_DECIMALS).astype(str) + "|"
           + hotspots["longitude"].round(COORDINATE_DECIMALS).astype(str) + "|" + pd.to_datetime(hotspots["acq_date"]).dt.strftime("%Y-%m-%d") + "|"
           + hotspots["acq_time"].astype(str))
    ids = [hashlib.sha1(text.encode("utf-8")).hexdigest()[:ID_LENGTH] for text in key]
    return hotspots.assign(hotspot_id=pd.array(ids, dtype="string"))


def add_acquisition_datetime(hotspots: pd.DataFrame) -> pd.DataFrame:
    """Ergaenzt `acq_datetime_utc` als echten Zeitstempel aus `acq_date` und `acq_time` (HHMM)."""
    acq_time = hotspots["acq_time"].astype(str).str.zfill(4)
    minutes = acq_time.str[:2].astype(int) * 60 + acq_time.str[2:].astype(int)
    timestamp = pd.to_datetime(hotspots["acq_date"]) + pd.to_timedelta(minutes, unit="m")
    return hotspots.assign(acq_datetime_utc=timestamp)


def assign_observation_date(hotspots: pd.DataFrame, mode: str, shift_hours: float) -> pd.Series:
    """Bestimmt den Tag, zu dem ein Hotspot zaehlt (`obs_date`).

    `utc`: das UTC-Datum der Messung.
    `solar`: das Datum der lokalen Sonnenzeit, mit Tageswechsel um `shift_hours` Uhr statt um
    Mitternacht. Hintergrund: Terra ueberfliegt abends (etwa 22:30 Sonnenzeit), Aqua und SNPP nach
    Mitternacht (etwa 1:30). Mit dem Wechsel um 6 Uhr landen beide Ueberfluege derselben Nacht auf
    demselben Tag, zusammen mit dem Nachmittag davor. Welche Variante gilt, entscheidet die
    Kreuzvalidierung (Hypothese H2), die Einstellung steht in der Konfiguration.
    """
    if mode == "utc":
        return pd.to_datetime(hotspots["acq_date"]).dt.normalize()
    if mode != "solar":
        raise ValueError(f"Unbekannte Tageszuordnung: {mode}")
    solar_offset = pd.to_timedelta(hotspots["longitude"] / DEGREES_PER_HOUR - shift_hours, unit="h")
    return (hotspots["acq_datetime_utc"] + solar_offset).dt.normalize()


def add_observation_date(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt `obs_date` nach der in der Konfiguration gewaehlten Tageszuordnung."""
    params = config["daily"]
    obs_date = assign_observation_date(hotspots, params["date_assignment"], params["solar_day_shift_hours"])
    return hotspots.assign(obs_date=obs_date)


def add_cell_id(hotspots: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Ergaenzt `cell_id` der Rasterzelle (Standard 0,25 Grad) als Text "Breitenindex_Laengenindex".

    Der Index ist floor(Koordinate / Zellgroesse). Die suedwestliche Ecke einer Zelle ist also
    Index x Zellgroesse. Die Zelle dient der Karte (Kacheln einfaerben) und schnellen Flaechenabfragen.
    """
    size = config["grid"]["cell_deg"]
    lat_index = np.floor(hotspots["latitude"] / size).astype("int64").astype(str)
    lon_index = np.floor(hotspots["longitude"] / size).astype("int64").astype(str)
    return hotspots.assign(cell_id=pd.array(lat_index + "_" + lon_index, dtype="string"))


def add_pixel_area(hotspots: pd.DataFrame) -> pd.DataFrame:
    """Ergaenzt `pixel_area_km2` = scan x track, die Flaeche des Pixels am Boden.

    Am Bildrand sind Pixel groesser als in der Bildmitte (MODIS 1 bis 9,6 km^2, VIIRS 0,13 bis
    0,6 km^2). Die Karte kann damit den echten Fussabdruck einer Erkennung zeichnen.
    """
    return hotspots.assign(pixel_area_km2=(hotspots["scan"] * hotspots["track"]).round(4))
