"""
Uniform errors according to specification v3, section 8:
    { "error": { "code": "…", "message": "…" } }

Register:   install_error_handlers(app)
Raise:      raise ApiError(404, "REGION_NOT_FOUND", "Unknown region 'ES-XX'.")

Messages are English, user-facing text.
"""

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


# Custom error types from dtos.py (_error) → (HTTP status, API code)
_CUSTOM = {
    "area_conflict": (400, "AREA_CONFLICT"),
    "invalid_date_range": (400, "INVALID_DATE_RANGE"),
    "resolution_out_of_range": (400, "RESOLUTION_OUT_OF_RANGE"),
    "geometry_too_complex": (413, "GEOMETRY_TOO_COMPLEX"),
    "invalid_request": (400, "INVALID_REQUEST"),
}


def map_validation_errors(errors: list[dict]) -> tuple[int, str, str]:
    """Maps Pydantic errors to (status, code, message). Custom error types take precedence."""
    for e in errors:
        if e["type"] in _CUSTOM:
            status, code = _CUSTOM[e["type"]]
            return status, code, e["msg"]

    e = errors[0]
    loc = [str(p) for p in e["loc"] if p not in ("body", "query", "path")]
    field = loc[0] if loc else ""
    text = f"{'.'.join(loc)}: {e['msg']}" if loc else e["msg"]

    if field == "geometry":
        return 400, "GEOMETRY_INVALID", "The area is not a valid Polygon or MultiPolygon."
    if field == "resolution":
        return 400, "RESOLUTION_OUT_OF_RANGE", text
    if field == "limit" and e["type"] == "less_than_equal":
        return 400, "LIMIT_TOO_HIGH", text
    if field == "lookback_days":
        return 400, "INVALID_DATE_RANGE", text
    return 400, "INVALID_REQUEST", text


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        status, code, message = map_validation_errors(exc.errors())
        return JSONResponse(status_code=status, content=error_body(code, message))

    @app.exception_handler(psycopg.errors.QueryCanceled)
    async def _timeout(request: Request, exc: Exception):
        return JSONResponse(status_code=504, content=error_body("QUERY_TIMEOUT", "The query took too long."))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # Handle the database driver's QueryCanceled as 504 QUERY_TIMEOUT before this point
        return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR", "Internal error"))


# Error responses for /docs and the TypeScript types (same set as in stub_app.py)
def _error_doc():
    from dtos import ErrorResponse
    return {code: {"model": ErrorResponse} for code in (400, 404, 413, 500, 501, 504)}


ERRORS_DOC = _error_doc()
