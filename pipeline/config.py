"""
config.py - shared settings for the harmonization.

harmonize.py, load_to_db.py and update_daily.py import these values,
so cutoff dates and satellites are defined in one place.
"""
from datetime import date, timedelta

import pandas as pd

# --- Periods ------------------------------------------------------------------
# MODIS enters the harmonized series only up to its end date (converted to the VIIRS scale)
MODIS_START = date(2000, 11, 1)     # first MODIS day in FIRMS (MODIS_SP)
MODIS_END = date(2012, 1, 31)       # last MODIS day of the harmonized series

# VIIRS only from here on
VIIRS_START = date(2012, 2, 1)      # first full month after the start of VIIRS S-NPP (2012-01-20)

# Overlap window used to derive the conversion
CALIBRATION_START = date(2012, 2, 1)
CALIBRATION_END = date(2022, 12, 31)

# --- Satellites ---------------------------------------------------------------
VIIRS_HISTORY_SATELLITE = "N"       # S-NPP (satellite column), history up to 2026-11-02
VIIRS_UPDATE_SOURCES = ["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]  # FIRMS API sources for new data

# --- Consistency checks on import ---------------------------------------------
assert VIIRS_START - MODIS_END == timedelta(days=1), "Gap or overlap between MODIS and VIIRS"
assert CALIBRATION_START >= VIIRS_START
assert CALIBRATION_END >= CALIBRATION_START


# --- Helpers ------------------------------------------------------------------
def period_of(day: date) -> str:
    """Return which sensor provides the harmonized series for this day."""
    if MODIS_START <= day <= MODIS_END:
        return "modis"
    if day >= VIIRS_START:
        return "viirs"
    return "none"


def _dates(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["acq_date"])  # FIRMS format: '2024-08-15'


def modis_for_series(df: pd.DataFrame) -> pd.DataFrame:
    """MODIS rows that belong to the harmonized series (to be converted)."""
    d = _dates(df)
    return df[(d >= pd.Timestamp(MODIS_START)) & (d <= pd.Timestamp(MODIS_END))]


def viirs_for_series(df: pd.DataFrame) -> pd.DataFrame:
    """VIIRS rows that belong to the harmonized series."""
    d = _dates(df)
    return df[d >= pd.Timestamp(VIIRS_START)]


def calibration_window(df: pd.DataFrame) -> pd.DataFrame:
    """Rows inside the overlap window (call separately for MODIS and VIIRS)."""
    d = _dates(df)
    return df[(d >= pd.Timestamp(CALIBRATION_START)) & (d <= pd.Timestamp(CALIBRATION_END))]