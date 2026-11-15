"""Canadian FWI System (features/fwi.py) against the published test table (KPI A7) and basic properties."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from features.fwi import COMPONENTS, bui, dc_step, dmc_step, ffmc_step, fwi, fwi_series, isi

REF = Path(__file__).parent / "data" / "fwi_reference_vanwagner1985.csv"


@pytest.fixture(scope="module")
def ref():
    return pd.read_csv(REF, comment="#")


def test_reference_table_all_components_within_0_1(ref):
    """A7: 49 consecutive days, start values 85 / 6 / 15; every component within 0.1 of the table."""
    out = fwi_series(ref["TEMP"].to_numpy(), ref["RH"].to_numpy(), ref["WS"].to_numpy(), ref["PREC"].to_numpy(),
                     ref["MON"].to_numpy())
    for c in COMPONENTS:
        dev = np.abs(out[c][:, 0] - ref[c.upper()].to_numpy())
        assert dev.max() < 0.1, (c, dev.max(), int(dev.argmax()))


def test_vectorised_over_points_equals_single_point(ref):
    n = len(ref)
    t = np.column_stack([ref["TEMP"], ref["TEMP"] + 5])
    rh = np.column_stack([ref["RH"], ref["RH"]])
    ws = np.column_stack([ref["WS"], ref["WS"]])
    pr = np.column_stack([ref["PREC"], ref["PREC"]])
    both = fwi_series(t, rh, ws, pr, ref["MON"].to_numpy())
    one = fwi_series(ref["TEMP"].to_numpy(), ref["RH"].to_numpy(), ref["WS"].to_numpy(), ref["PREC"].to_numpy(),
                     ref["MON"].to_numpy())
    assert both["fwi"].shape == (n, 2)
    for c in COMPONENTS:
        np.testing.assert_allclose(both[c][:, 0], one[c][:, 0])
    assert (both["dc"][:, 1] >= both["dc"][:, 0] - 1e-9).all()       # warmer -> drier deep layer


def test_rain_wets_and_dry_weather_dries():
    wet = dict(t=20.0, rh=40.0, wind=10.0, rain=20.0)
    dry = dict(t=30.0, rh=20.0, wind=10.0, rain=0.0)
    assert ffmc_step(85.0, **wet) < 85.0 < ffmc_step(85.0, **dry)
    assert dmc_step(40.0, wet["t"], wet["rh"], wet["rain"], 7) < 40.0 < dmc_step(40.0, dry["t"], dry["rh"], 0.0, 7)
    assert dc_step(400.0, wet["t"], wet["rain"], 7) < 400.0 < dc_step(400.0, dry["t"], 0.0, 7)
    # small rain is intercepted: below the thresholds the codes are not wetted
    assert dmc_step(40.0, 20.0, 40.0, 1.5, 7) >= 40.0
    assert dc_step(400.0, 20.0, 2.8, 7) >= 400.0


def test_indices_monotone_and_bounded():
    assert isi(90.0, 30.0) > isi(90.0, 10.0) > isi(80.0, 10.0) >= 0
    assert bui(0.0, 0.0) == 0.0
    assert bui(50.0, 400.0) > bui(20.0, 400.0)
    assert fwi(10.0, 80.0) > fwi(5.0, 80.0) > 0
    assert 0.0 <= ffmc_step(100.0, 45.0, 1.0, 60.0, 0.0) <= 101.0


def test_missing_day_keeps_codes_and_gives_nan():
    t, rh, ws, pr = (np.array(v, float) for v in ([25, np.nan, 25], [30, 30, 30], [10, 10, 10], [0, 0, 0]))
    out = fwi_series(t, rh, ws, pr, np.array([7, 7, 7]))
    assert np.isnan(out["fwi"][1, 0]) and np.isfinite(out["fwi"][2, 0])
    # day 3 continues from day 1 (day 2 skipped): equal to two dry days in a row
    ref = fwi_series(np.array([25.0, 25.0]), np.array([30.0, 30.0]), np.array([10.0, 10.0]), np.zeros(2), np.array([7, 7]))
    np.testing.assert_allclose(out["dc"][2, 0], ref["dc"][1, 0])
