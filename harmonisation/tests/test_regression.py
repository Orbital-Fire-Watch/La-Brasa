"""Regressionstests gegen Version 1 und die Voranalyse. Laufen nur, wenn deren Ergebnisse und ein echter Lauf vorliegen."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from aggregation.roll_up import roll_up_daily
from pipeline.config import path_of
from pipeline.io_utils import read_json, read_parquet

RELATIVE_TOLERANCE = 0.01
EXACT = 1e-9


@pytest.fixture(scope="module")
def daily(config: dict[str, Any]) -> pd.DataFrame:
    """Der echte Tagesdatensatz (nicht der Test-Ausschnitt)."""
    path = path_of(config, "harmonised", "activity_daily_harmonised.parquet")
    if not path.exists() or config["daily"]["date_assignment"] != "utc":
        pytest.skip("kein echter Lauf vorhanden oder andere Tageszuordnung als in Version 1")
    return read_parquet(path)


def test_overall_factors_match_analysis(config: dict[str, Any], daily: pd.DataFrame) -> None:
    """Die Faktoren stimmen auf 1 % mit der Voranalyse ueberein.

    Kalibriert wird gegen SNPP allein (calibration.reference_satellites, Iteration 1). Massstab ist
    darum 08_series.py. Zusaetzlich: Der Gesamtfaktor liegt hoechstens 3 % (Regel R3) neben dem
    Faktor, den eine Kalibrierung auf das VIIRS-Mittel ergaebe (09_viirs_satellites.py).
    """
    results = Path(config["paths"]["reference_results_dir"])
    if not (results / "viirs_satellites.json").exists() or not (results / "series.json").exists():
        pytest.skip("Analyseergebnisse fehlen")
    reference, mean_calibration = read_json(results / "series.json"), read_json(results / "viirs_satellites.json")["calibration"]
    summary = read_json(path_of(config, "harmonised", "calib_summary.json"))["overall_factors"]
    assert summary["k_count_pair"] == pytest.approx(reference["k_global"], rel=RELATIVE_TOLERANCE)
    assert summary["k_count_terra"] == pytest.approx(reference["kt_global"], rel=RELATIVE_TOLERANCE)
    assert summary["k_count_pair"] == pytest.approx(mean_calibration["k_pair_overall_mean"], rel=0.03)
    factors = read_parquet(path_of(config, "harmonised", "calib_factors.parquet")).set_index("region_id")
    for region_id, expected in reference["k_region"].items():
        assert factors.loc[region_id, "k_count_pair"] == pytest.approx(expected, rel=RELATIVE_TOLERANCE), region_id


def test_monthly_values_match_version_one(config: dict[str, Any], daily: pd.DataFrame) -> None:
    """Die aus Tagen abgeleiteten Monatswerte entsprechen Version 1, wo beide dieselbe Basis haben.

    Verglichen werden Monate, die in beiden Versionen ganz gemessen oder ganz mit dem Paar bzw. mit
    Terra umgerechnet sind. Uebergangsmonate (Juli 2002, Januar 2012) rechnet die Tagesversion
    bewusst anders (tagesgenaue Basis). Juli 2026 ist ausgenommen, weil dort eine Zeile der
    Quelldatei unlesbar sein kann.
    """
    version_one_path = Path(config["paths"]["reference_v1_harmonised"])
    if not version_one_path.exists():
        pytest.skip("Version 1 fehlt")
    old = read_parquet(version_one_path).rename(columns={"n_harm": "n_old", "frp_harm": "frp_old"})
    new = roll_up_daily(daily, "month")
    new = new[new["is_complete_period"] & new["basis_mix"].ne("mixed")]
    merged = new.merge(old[["region_id", "period_start", "n_old", "frp_old", "basis"]], on=["region_id", "period_start"])
    comparable = merged[~merged["period_start"].isin(pd.to_datetime(["2002-07-01", "2012-01-01", "2026-07-01"]))]
    assert len(comparable) > 6000
    assert ((comparable["n_harm"] - comparable["n_old"]).abs() <= EXACT * comparable["n_old"].abs().clip(lower=1)).all()
    measured = comparable[comparable["basis"] == "viirs_measured"]
    assert ((measured["frp_harm"] - measured["frp_old"]).abs() <= 1e-6 * measured["frp_old"].abs().clip(lower=1)).all()
