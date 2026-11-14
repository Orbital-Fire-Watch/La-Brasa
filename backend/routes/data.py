"""Fire-API v3 endpoints: meta, regions, areas, calendar, daily, grid, hotspots, export.csv, events, by-region."""
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse, StreamingResponse

from core.db import connect
from dtos import (
    AreaRequest, AreaResponse, ByRegionRequest, ByRegionResponse, CalendarRequest, CalendarResponse, DailyRequest,
    DailyResponse, EventDetailResponse, EventId, EventsRequest, EventsResponse, ExportQuery, GridAnomalyResponse,
    GridByDayResponse, GridCountResponse, GridRequest, HotspotsRequest, HotspotsResponse, MetaResponse,
    RegionsResponse,
)
from errors import ERRORS_DOC
from services.areas import register_area
from services.events import daily_event_counts, event_detail, get_index, list_events
from services.grid import build_grid
from services.hotspots import build_hotspots, export_rows
from services.meta import build_meta
from services.regions import build_regions
from services.scope import build_scope
from services.series import build_by_region, build_calendar, build_daily

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


@router.post("/areas", response_model=AreaResponse, responses=ERRORS_DOC, tags=["Soll"])
def areas(body: AreaRequest):
    with connect() as conn:
        return register_area(conn, body.geometry.model_dump())


@router.post("/calendar", response_model=CalendarResponse, responses=ERRORS_DOC, tags=["Muss"])
def calendar(body: CalendarRequest):
    with connect() as conn:
        return build_calendar(conn, build_scope(conn, body))


@router.post("/daily", response_model=DailyResponse, responses=ERRORS_DOC, tags=["Muss"])
def daily(body: DailyRequest):
    with connect() as conn:
        out = build_daily(conn, build_scope(conn, body))
        no_data = [v is None for v in out["fires"]]
        return {**out, **daily_event_counts(conn, body, out["start"], out["end"], no_data)}


@router.post("/grid", response_model=GridAnomalyResponse | GridByDayResponse | GridCountResponse,
             responses=ERRORS_DOC, tags=["Muss"])
def grid(body: GridRequest):
    with connect() as conn:
        return build_grid(conn, build_scope(conn, body), body)


@router.post("/hotspots", response_model=HotspotsResponse, responses=ERRORS_DOC, tags=["Muss"])
def hotspots(body: HotspotsRequest):
    with connect() as conn:
        return build_hotspots(conn, build_scope(conn, body), body, get_index(conn))


@router.get("/export.csv", responses={**ERRORS_DOC, 200: {"content": {"text/csv": {}}}}, tags=["Muss"])
def export_csv(q: Annotated[ExportQuery, Query()]):
    # The stream outlives this function, so the connection is closed by the generator.
    ctx = connect()
    conn = ctx.__enter__()
    try:
        scope = build_scope(conn, q)
        meta_row = build_meta(conn)
        index = get_index(conn)
    except Exception:
        ctx.__exit__(None, None, None)
        raise

    def stream():
        try:
            yield from export_rows(conn, scope, q.start, q.end, q.event_id, index)
        finally:
            ctx.__exit__(None, None, None)

    name = q.event_id or q.region_id or q.area_id or "ES-PT"
    period = f"{q.start}_{q.end}" if q.start else f"until_{q.end}"
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="hotspots_{name}_{period}.csv"',
        "X-Data-Version": meta_row["data_version"], "X-Weight-Version": meta_row["weight_version"]})


@router.post("/events", response_model=EventsResponse, responses=ERRORS_DOC, tags=["Soll"])
def events(body: EventsRequest):
    with connect() as conn:
        return list_events(conn, body)


@router.get("/events/{event_id}", response_model=EventDetailResponse, responses=ERRORS_DOC, tags=["Soll"])
def event(event_id: Annotated[EventId, Path()], date: Annotated[dt.date, Query(description="reference date D")]):
    with connect() as conn:
        return event_detail(conn, event_id, date)


@router.post("/by-region", response_model=ByRegionResponse, responses=ERRORS_DOC, tags=["Kann"])
def by_region(body: ByRegionRequest):
    with connect() as conn:
        return build_by_region(conn, build_scope(conn, body), body)
