"""Fixtures der Aggregations-Tests."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pipeline.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def config() -> dict[str, Any]:
    """Die echte Konfiguration des Projekts."""
    return load_config()
