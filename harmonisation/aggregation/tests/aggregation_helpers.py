"""Test-Hilfen des Aggregationsmoduls: synthetische Tagesdaten, Hotspots und ein kleines Fehlermodell."""
from __future__ import annotations


import numpy as np
import pandas as pd




def make_daily(start: str, end: str, measured_from: str | None = None, last_value_day: str | None = None) -> pd.DataFrame:
    """Synthetischer Tagesdatensatz fuer zwei Regionen: Region A zaehlt den Tag im Monat, Region B ist halb so gross."""
    dates = pd.date_range(start, end, freq="D")
    parts = []
    for region, scale in (("A", 1.0), ("B", 0.5)):
        frame = pd.DataFrame({"region_id": region, "date": dates, "n_harm": dates.day * scale, "frp_harm": dates.day * 10.0 * scale})
        measured = dates >= pd.Timestamp(measured_from) if measured_from else np.zeros(len(dates), bool)
        frame["basis_count"] = np.where(measured, "viirs_measured", "modis_pair_scaled")
        frame["basis_frp"] = np.where(measured, "viirs_measured", "aqua_scaled")
        if last_value_day:
            late = dates > pd.Timestamp(last_value_day)
            frame.loc[late, ["basis_count", "basis_frp"]] = "none"
            frame.loc[late, ["n_harm", "frp_harm"]] = np.nan
        frame["big_fire_day"] = (frame["frp_harm"] >= 100).astype("boolean").where(frame["frp_harm"].notna())
        frame["n_snpp"] = frame["n_harm"].where(measured)
        frame["n_aqua"], frame["n_terra"] = frame["n_harm"] / 6, frame["n_harm"] / 6
        frame["frp_snpp"], frame["frp_aqua"], frame["frp_terra"] = frame["frp_harm"].where(measured), frame["frp_harm"], frame["frp_harm"] / 2
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def make_quality() -> pd.DataFrame:
    """Kleines Fehlermodell: je Skala die Klassen 0, 0-5, 5-20, >20 und die Zeile "all"."""
    rows = []
    for area_scale in ("cell", "nuts2", "country", "all"):
        for grain in ("day", "week", "month", "quarter", "year"):
            for quantity, basis in (("count", "modis_pair_scaled"), ("frp", "aqua_scaled")):
                for label, upper, e50, e90, units in (("0", 0.0, 1.0, 3.0, 500), ("0-5", 5.0, 2.0, 5.0, 200), ("5-20", 20.0, 1.6, 3.5, 200),
                                                      (">20", np.inf, 1.2, 1.8, 10), ("all", np.inf, 1.5, 4.0, 410)):
                    rows.append({"area_scale": area_scale, "grain": grain, "quantity": quantity, "basis": basis, "size_class": label,
                                 "class_upper": upper, "n_units": units, "median_factor_error": e50, "p90_factor_error": e90,
                                 "abs_upper_p50": 1.0, "abs_upper_p90": 7.0})
    return pd.DataFrame(rows)


def make_hotspots() -> pd.DataFrame:
    """Sechs Hotspots: vier VIIRS-Punkte bei Madrid, zwei MODIS-Punkte, einer davon ausserhalb der Reihe."""
    rows = [(40.40, -3.70, "2015-07-01", "SNPP", 1.0, True, 10.0), (40.42, -3.72, "2015-07-01", "SNPP", 1.0, True, 20.0),
            (40.45, -3.60, "2015-07-02", "SNPP", 1.0, True, 5.0), (41.50, -3.70, "2015-07-02", "SNPP", 1.0, True, 50.0),
            (40.41, -3.71, "2015-07-01", "Aqua", 0.0, False, 30.0), (40.41, -3.71, "2010-07-01", "Aqua", 3.0, True, 40.0)]
    frame = pd.DataFrame(rows, columns=["latitude", "longitude", "obs_date", "satellite", "weight_n", "in_series_n", "frp"])
    frame["obs_date"] = pd.to_datetime(frame["obs_date"])
    frame["acq_datetime_utc"] = frame["obs_date"] + pd.Timedelta(hours=13)
    frame["weight_frp"] = np.where(frame["in_series_n"], np.where(frame["satellite"] == "SNPP", 1.0, 1.2), 0.0)
    frame["basis_count"] = np.where(frame["obs_date"].dt.year >= 2012, "viirs_measured", "modis_pair_scaled")
    frame["region_id"], frame["country"], frame["cell_id"] = "ES30", "ES", "161_-15"
    frame["hotspot_id"] = [f"id{i}" for i in range(len(frame))]
    for column, value in (("sensor", "x"), ("source", "archive"), ("daynight", "D"), ("frp_class", "mid"), ("confidence_class", "nominal"),
                          ("confidence_raw", "n"), ("scan", 0.4), ("track", 0.4)):
        frame[column] = value
    return frame
