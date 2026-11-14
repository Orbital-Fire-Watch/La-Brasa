"""La Brasa Fire-API v3. Run from the backend folder:  uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs   Contract: dtos.py   Spec: docs/Fire-API_Spezifikation_v3.md"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi

from core.config import CORS_ORIGINS
from dtos import API_VERSION
from errors import install_error_handlers
from routes import data, pending

app = FastAPI(
    title="Fire-API", version=API_VERSION,
    description="Harmonised fire data (MODIS + VIIRS) for Spain and Portugal. Specification v3.",
)
install_error_handlers(app)
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"], expose_headers=["Content-Disposition"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(data.router)
app.include_router(pending.router)


def _openapi_without_422():
    """FastAPI adds 422 automatically. Our API answers 400 + ErrorResponse instead (spec section 8)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    for path in schema["paths"].values():
        for op in path.values():
            op.get("responses", {}).pop("422", None)
    for name in ("HTTPValidationError", "ValidationError"):
        schema.get("components", {}).get("schemas", {}).pop(name, None)
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_without_422
