"""Tests der abgeleiteten Spalten: FRP-Klasse, Konfidenzklasse, Sonnenzeit, Region."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from helpers import make_raw_hotspots
from pipeline.data_loading.assign_region import assign_nuts2_region, load_region_names
from pipeline.data_loading.classify_hotspots import add_confidence_class, add_frp_class, add_local_solar_hour

APP_MAP = Path(__file__).resolve().parents[2] / "backend" / "assets" / "nuts2_iberia.geojson"   # Regionen der Karte im Frontend


def test_frp_class_boundaries(config: dict[str, Any]) -> None:
    """Die Grenzen 10 und 50 MW gehoeren jeweils zur hoeheren Klasse."""
    rows = make_raw_hotspots([{"frp": value} for value in (0.0, 9.99, 10.0, 49.99, 50.0, 800.0)], config)
    assert list(add_frp_class(rows, config)["frp_class"]) == ["low", "low", "mid", "mid", "high", "high"]


def test_confidence_class_per_sensor(config: dict[str, Any]) -> None:
    """MODIS-Zahlen und VIIRS-Buchstaben landen in denselben drei Klassen, der Originalwert bleibt."""
    modis = [{"confidence": value} for value in ("0", "29", "30", "79", "80", "100")]
    viirs = [{"satellite": "SNPP", "confidence": value} for value in ("l", "n", "h")]
    result = add_confidence_class(make_raw_hotspots(modis + viirs, config), config)
    assert list(result["confidence_class"]) == ["low", "low", "nominal", "nominal", "high", "high", "low", "nominal", "high"]
    assert list(result["confidence_raw"])[-3:] == ["l", "n", "h"] and "confidence" not in result.columns


def test_local_solar_hour(config: dict[str, Any]) -> None:
    """13:00 UTC bei 15 Grad West ist 12:00 Sonnenzeit, 23:30 UTC bei 15 Grad Ost ist 00:30."""
    rows = make_raw_hotspots([{"acq_time": "1300", "longitude": -15.0}, {"acq_time": "2330", "longitude": 15.0}], config)
    assert list(add_local_solar_hour(rows)["local_solar_hour"]) == pytest.approx([12.0, 0.5])


def test_region_assignment_at_known_points(config: dict[str, Any]) -> None:
    """Madrid, Lissabon und Barcelona bekommen ihre NUTS-2-Region, ein Punkt im Atlantik keine."""
    points = [{"latitude": 40.4168, "longitude": -3.7038}, {"latitude": 38.7223, "longitude": -9.1393},
              {"latitude": 41.3874, "longitude": 2.1686}, {"latitude": 40.0, "longitude": -12.0}]
    result = assign_nuts2_region(make_raw_hotspots(points, config), config)
    assert list(result["region_id"][:3]) == ["ES30", "PT17", "ES51"] and result["region_id"].isna()[3]
    assert list(result["country"][:3]) == ["ES", "PT", "ES"]


def test_study_regions_match_the_app_map(config: dict[str, Any]) -> None:
    """Die Untersuchungsregionen sind genau die Regionen der Karte im Frontend und stehen alle in der NUTS-Datei der Pipeline."""
    map_ids = {feature["properties"]["NUTS_ID"] for feature in json.loads(APP_MAP.read_text(encoding="utf-8"))["features"]}
    assert sorted(config["nuts"]["study_regions"]) == sorted(map_ids)
    assert set(config["nuts"]["study_regions"]) <= set(load_region_names(config))
