"""The 'Muss' endpoints of Fire-API v3: meta, regions, calendar, daily, grid, hotspots, export.csv."""
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from core.db import connect
from dtos import (
    CalendarRequest, CalendarResponse, DailyRequest, DailyResponse, ExportQuery, GridAnomalyResponse,
    GridByDayResponse, GridCountResponse, GridRequest, HotspotsRequest, HotspotsResponse, MetaResponse,
    RegionsResponse,
)
from errors import ERRORS_DOC
from services.grid import build_grid_count
from services.hotspots import build_hotspots, export_rows
from services.meta import build_meta
from services.regions import build_regions
from services.scope import build_scope
from services.series import build_calendar, build_daily

router = APIRouter(prefix="/api")


@router.get("/meta", response_model=MetaResponse, responses=ERRORS_DOC, tags=["Muss"])
def meta():
    with connect() as conn:
        return build_meta(conn)


@router.get("/regions", response_model=RegionsResponse, responses=ERRORS_DOC, tags=["Muss"])
def regions():
    with connect() as conn:
        body = build_regions(conn)
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=86400"})


@router.post("/calendar", response_model=CalendarResponse, responses=ERRORS_DOC, tags=["Muss"])
def calendar(body: CalendarRequest):
    with connect() as conn:
        return build_calendar(conn, build_scope(conn, body))


@router.post("/daily", response_model=DailyResponse, responses=ERRORS_DOC, tags=["Muss"])
def daily(body: DailyRequest):
    with connect() as conn:
        return build_daily(conn, build_scope(conn, body))


@router.post("/grid", response_model=GridAnomalyResponse | GridByDayResponse | GridCountResponse,
             responses=ERRORS_DOC, tags=["Muss"])
def grid(body: GridRequest):
    with connect() as conn:
        return build_grid_count(conn, build_scope(conn, body), body)


@router.post("/hotspots", response_model=HotspotsResponse, responses=ERRORS_DOC, tags=["Muss"])
def hotspots(body: HotspotsRequest):
    with connect() as conn:
        return build_hotspots(conn, build_scope(conn, body), body)


@router.get("/export.csv", responses={**ERRORS_DOC, 200: {"content": {"text/csv": {}}}}, tags=["Muss"])
def export_csv(q: Annotated[ExportQuery, Query()]):
    # The stream outlives this function, so the connection is closed by the generator.
    ctx = connect()
    conn = ctx.__enter__()
    try:
        scope = build_scope(conn, q)
        meta_row = build_meta(conn)
    except Exception:
        ctx.__exit__(None, None, None)
        raise

    def stream():
        try:
            yield from export_rows(conn, scope, q.start, q.end)
        finally:
            ctx.__exit__(None, None, None)

    name = q.region_id or "ES-PT"
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="hotspots_{name}_{q.start}_{q.end}.csv"',
        "X-Data-Version": meta_row["data_version"], "X-Weight-Version": meta_row["weight_version"]})
