"""Fixtures der Pipeline-Tests: echte Konfiguration und ein Lauf auf dem Test-Ausschnitt."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import make_fixture_config  # noqa: E402
from pipeline.config import load_config  # noqa: E402
import run_pipeline  # noqa: E402


@pytest.fixture(scope="session")
def config() -> dict[str, Any]:
    """Die echte Konfiguration des Projekts."""
    return load_config()


@pytest.fixture(scope="session")
def fixture_run(config: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Laesst die Datenstufen einmal auf dem Test-Ausschnitt laufen."""
    fixture_config = make_fixture_config(config, tmp_path_factory.mktemp("pipeline_data"))
    state = run_pipeline.run_pipeline(fixture_config, stages=run_pipeline.DATA_STAGES)
    return {"config": fixture_config, "state": state}
