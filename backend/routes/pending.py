"""Endpoints of the spec that are not built yet. They answer 501 NOT_IMPLEMENTED (spec section 11)
and are marked as false in meta.features."""
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Path, Query

from dtos import (
    AreaRequest, AreaResponse, ByRegionRequest, ByRegionResponse, EventDetailResponse, EventId,
    EventsRequest, EventsResponse,
)
from errors import ERRORS_DOC, ApiError

router = APIRouter(prefix="/api")


def _todo(what: str):
    raise ApiError(501, "NOT_IMPLEMENTED", f"{what} is not available yet.")


@router.post("/areas", response_model=AreaResponse, responses=ERRORS_DOC, tags=["Soll"])
def areas(body: AreaRequest):
    _todo("Drawn areas")


@router.post("/events", response_model=EventsResponse, responses=ERRORS_DOC, tags=["Soll"])
def events(body: EventsRequest):
    _todo("Events")


@router.get("/events/{event_id}", response_model=EventDetailResponse, responses=ERRORS_DOC, tags=["Soll"])
def event_detail(event_id: Annotated[EventId, Path()], date: Annotated[dt.date, Query(description="reference date D")]):
    _todo("Events")


@router.post("/by-region", response_model=ByRegionResponse, responses=ERRORS_DOC, tags=["Kann"])
def by_region(body: ByRegionRequest):
    _todo("By-region statistics")
