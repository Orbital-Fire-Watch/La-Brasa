"""Settings from the environment (docker-compose sets DATABASE_URL for the backend)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user, password, db = (os.environ.get(k) for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"))
    host = os.environ.get("POSTGRES_HOST", "localhost")
    if not (user and password and db):
        raise RuntimeError("Set DATABASE_URL or POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB.")
    return f"postgresql://{user}:{password}@{host}:5432/{db}"


REGIONS_GEOJSON = Path(os.environ.get("REGIONS_GEOJSON", BACKEND_DIR / "assets" / "nuts2_iberia.geojson"))
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(",") if o]
STATEMENT_TIMEOUT_MS = int(os.environ.get("STATEMENT_TIMEOUT_MS", "10000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# API scope: Spain and Portugal only. The harmonisation keeps only these regions (nuts.study_regions); the filter stays as a guard.
API_COUNTRIES = ("ES", "PT")
WEIGHT_VERSION = "w1"            # bump when the harmonisation method or its factors change
MAP_BBOX = (-9.6, 35.9, 4.4, 43.9)

# Data sync (POST /api/sync) runs pipeline/sync_data.py. It needs the FIRMS key and the pipeline code next to the
# backend (repository layout; the backend image copies it, see backend/Dockerfile).
PIPELINE_DIR = Path(os.environ.get("PIPELINE_DIR", BACKEND_DIR.parent / "pipeline"))
SYNC_AVAILABLE = bool(os.environ.get("FIRMS_MAP_KEY", "").strip()) and (PIPELINE_DIR / "sync_data.py").is_file()
ATTRIBUTION = ("Fire data: NASA FIRMS (MODIS, VIIRS), harmonised by La Brasa. "
               "Boundaries: Eurostat GISCO NUTS-2 2021, (C) EuroGeographics.")
