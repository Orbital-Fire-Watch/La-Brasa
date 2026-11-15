"""
Fire-API – DTOs (Data Transfer Objects) for specification v3 of 14.11.2026.

One file = the contract between frontend and backend, in code.
- FastAPI validates every request against the *request* DTOs and every response against the *response* DTOs.
- These classes produce /openapi.json, which in turn produces the frontend's TypeScript types:
      npx openapi-typescript http://localhost:8000/openapi.json --default-non-nullable false -o src/api/schema.d.ts

Rules:
- Field names exactly as in the specification (snake_case), no aliases.
- Change only together with the specification (section 1) and a new api_version.
- Rounding happens when building the response (specification section 2), not here.
- Error messages are English, user-facing text (§8).

Section numbers (§) refer to specification v3.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

API_VERSION = "3.2"        # 3.1: data sync (/api/sync), 3.2: raw counts per sensor family (/api/daily/sensors)

# ---------------------------------------------------------------------------
# Limits (§6.1 limits) – defined once so that /meta and the validation always agree
# ---------------------------------------------------------------------------

HOTSPOTS_DEFAULT = 5000
HOTSPOTS_MAX = 20000
EVENTS_DEFAULT = 500
EVENTS_MAX = 2000
LOOKBACK_DAYS_MAX = 60
GEOMETRY_MAX_VERTICES = 1000
H3_RESOLUTION_MIN = 3
H3_RESOLUTION_MAX = 8
ANOMALY_RESOLUTION_MAX = 5
ANOMALY_WINDOW_MAX_DAYS = 366
GRID_BY_DAY_MAX_DAYS = 150


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class RequestModel(BaseModel):
    """Requests: unknown fields are an error (catches typos such as "regionId")."""
    model_config = ConfigDict(extra="forbid")


class ResponseModel(BaseModel):
    """Responses: strict as well, so the backend cannot invent fields."""
    model_config = ConfigDict(extra="forbid")


def _error(kind: str, message: str) -> PydanticCustomError:
    """Error with a custom type. errors.py maps the type to the API error code (§8)."""
    return PydanticCustomError(kind, message)


# ---------------------------------------------------------------------------
# Shared types (§2, §5.4)
# ---------------------------------------------------------------------------

Sensor = Literal["MODIS_TERRA", "MODIS_AQUA", "VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21"]
Confidence = Literal["nominal", "high"]
DayNight = Literal["D", "N"]
Metric = Literal["fires", "hotspots", "frp_sum"]
RegionLevel = Literal["country", "region", "province"]
MonthStatus = Literal["complete", "running", "incomplete"]
Trend = Literal["growing", "stable", "shrinking"]
EventSort = Literal["frp_sum", "area_km2", "duration_days", "hotspots", "start", "last_seen"]

Position = tuple[float, float]                       # [lon, lat]
BBox = tuple[float, float, float, float]             # [minLon, minLat, maxLon, maxLat]
NonNegFloat = Annotated[float, Field(ge=0)]
NonNegInt = Annotated[int, Field(ge=0)]

RegionId = Annotated[str, Field(min_length=2, max_length=10, examples=["ES-OR"])]
AreaId = Annotated[str, Field(pattern=r"^a_[0-9a-f]{12}$", examples=["a_7f3c9e2b41d0"])]
EventId = Annotated[str, Field(pattern=r"^e_[0-9a-f]{12}$", examples=["e_3b91c04a7f2e"])]
H3Cell = Annotated[str, Field(pattern=r"^[0-9a-f]{15}$", examples=["86392031fffffff"])]


# ---------------------------------------------------------------------------
# GeoJSON (only the parts the API uses)
# ---------------------------------------------------------------------------

class Point(BaseModel):
    type: Literal["Point"]
    coordinates: Position


class Polygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[Position]]


class MultiPolygon(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[Position]]]


AreaGeometry = Annotated[Union[Polygon, MultiPolygon], Field(discriminator="type")]


def _count_vertices(g: Polygon | MultiPolygon) -> int:
    rings = g.coordinates if isinstance(g, Polygon) else [r for p in g.coordinates for r in p]
    return sum(len(r) for r in rings)


# ---------------------------------------------------------------------------
# Request building blocks
# ---------------------------------------------------------------------------

class AreaSelector(RequestModel):
    """Area selection (§2): at most one of the three fields; none = all of ES + PT."""
    region_id: RegionId | None = Field(None, description="ID from /api/regions")
    area_id: AreaId | None = Field(None, description="ID from POST /api/areas")
    geometry: AreaGeometry | None = Field(None, description="Interim solution until /api/areas exists")

    @model_validator(mode="after")
    def _check_area(self):
        if sum(v is not None for v in (self.region_id, self.area_id, self.geometry)) > 1:
            raise _error("area_conflict", "Please provide only one of region_id, area_id and geometry.")
        if self.geometry is not None:
            n = _count_vertices(self.geometry)
            if n > GEOMETRY_MAX_VERTICES:
                raise _error("geometry_too_complex",
                             f"The area has {n} vertices, the maximum is {GEOMETRY_MAX_VERTICES}.")
        return self


class WithConfidence(RequestModel):
    min_confidence: Confidence = Field(
        "nominal", description="§2 Confidence: 'nominal' = nominal + high, 'high' = high only")


def _check_range(start: dt.date | None, end: dt.date | None, max_days: int | None = None, what: str = "The period"):
    """Shared date range check: start <= end and optional maximum length (both inclusive)."""
    if start is None or end is None:
        return
    if start > end:
        raise _error("invalid_date_range", "start is after end.")
    if max_days is not None and (end - start).days + 1 > max_days:
        raise _error("invalid_date_range", f"{what} must not be longer than {max_days} days.")


# ===========================================================================
# 6.1 GET /api/meta
# ===========================================================================

class SensorInfo(ResponseModel):
    id: Sensor
    # "from" is a Python keyword, so the attribute is from_ and the JSON field is "from"
    from_: dt.date = Field(alias="from", serialization_alias="from")
    to: dt.date | None = Field(description="null = still delivering data")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Features(ResponseModel):
    """What the backend can already do. Only set to true once real data is returned (§6.1)."""
    areas: bool
    daily: bool
    events: bool
    anomaly: bool
    anomaly_window: bool
    grid_by_day: bool
    landcover: bool


class Limits(ResponseModel):
    """Values come from the constants above, e.g. Limits(**LIMITS)."""
    hotspots_default: int
    hotspots_max: int
    events_default: int
    events_max: int
    lookback_days_max: int
    geometry_max_vertices: int
    h3_resolution_min: int
    h3_resolution_max: int
    anomaly_resolution_max: int
    anomaly_window_max_days: int
    grid_by_day_max_days: int


LIMITS = dict(
    hotspots_default=HOTSPOTS_DEFAULT, hotspots_max=HOTSPOTS_MAX,
    events_default=EVENTS_DEFAULT, events_max=EVENTS_MAX, lookback_days_max=LOOKBACK_DAYS_MAX,
    geometry_max_vertices=GEOMETRY_MAX_VERTICES,
    h3_resolution_min=H3_RESOLUTION_MIN, h3_resolution_max=H3_RESOLUTION_MAX,
    anomaly_resolution_max=ANOMALY_RESOLUTION_MAX, anomaly_window_max_days=ANOMALY_WINDOW_MAX_DAYS,
    grid_by_day_max_days=GRID_BY_DAY_MAX_DAYS,
)


class MetaResponse(ResponseModel):
    api_version: str = Field(examples=[API_VERSION])
    data_version: str = Field(examples=["2026-11-14.1"], description="changes on every import → clear the cache")
    weight_version: str = Field(examples=["w1"])
    first_date: dt.date
    last_date: dt.date = Field(description="'Today' in the UI")
    last_update: dt.datetime
    region: str
    bbox: BBox = Field(description="initial map view only, not a filter")
    sensors: list[SensorInfo]
    confidence_levels: list[Confidence]
    features: Features
    limits: Limits
    attribution: str


# ===========================================================================
# 6.2 GET /api/regions
# ===========================================================================

class RegionProperties(ResponseModel):
    id: RegionId
    name: str
    level: RegionLevel
    country: Literal["ES", "PT"]
    parent: RegionId | None
    bbox: BBox


class RegionFeature(ResponseModel):
    type: Literal["Feature"]
    geometry: MultiPolygon
    properties: RegionProperties


class RegionsResponse(ResponseModel):
    type: Literal["FeatureCollection"]
    features: list[RegionFeature]


# ===========================================================================
# 6.3 POST /api/areas
# ===========================================================================

class AreaRequest(RequestModel):
    geometry: AreaGeometry

    @model_validator(mode="after")
    def _check_vertices(self):
        n = _count_vertices(self.geometry)
        if n > GEOMETRY_MAX_VERTICES:
            raise _error("geometry_too_complex",
                         f"The area has {n} vertices, the maximum is {GEOMETRY_MAX_VERTICES}.")
        return self


class AreaResponse(ResponseModel):
    area_id: AreaId
    geometry: MultiPolygon = Field(description="cleaned and clipped to ES + PT – show exactly this on the map")
    bbox: BBox
    area_km2: NonNegFloat
    vertices: NonNegInt


# ===========================================================================
# 6.4 POST /api/calendar
# ===========================================================================

class CalendarRequest(AreaSelector, WithConfidence):
    pass


class MetricValues(ResponseModel):
    """One value per metric, e.g. for 'max' (colour scale)."""
    fires: NonNegFloat
    hotspots: NonNegInt
    frp_sum: NonNegFloat


class CalendarMonth(ResponseModel):
    year: int
    month: int = Field(ge=1, le=12)
    fires: NonNegFloat
    hotspots: NonNegInt
    frp_sum: NonNegFloat
    status: MonthStatus


class SamePeriodYear(ResponseModel):
    year: int
    fires: NonNegFloat
    frp_sum: NonNegFloat


class RunningMonth(ResponseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$", examples=["2026-11"])
    through: dt.date
    same_period: list[SamePeriodYear]


class CalendarResponse(ResponseModel):
    data: list[CalendarMonth] = Field(description="all months without gaps, sorted by date")
    max: MetricValues = Field(description="maximum per metric among months with status 'complete'")
    running_month: RunningMonth | None


# ===========================================================================
# 6.5 POST /api/daily
# ===========================================================================

class DailyRequest(AreaSelector, WithConfidence):
    pass


class DailyResponse(ResponseModel):
    """Column-oriented: index i = day start + i. null = no sensor delivered data on that day."""
    start: dt.date
    end: dt.date
    fires: list[NonNegFloat | None]
    hotspots: list[NonNegInt | None]
    frp_sum: list[NonNegFloat | None]
    n_sensors: list[NonNegInt] | None = Field(None, description="Could-have")
    events_active: list[NonNegInt | None] | None = Field(
        None, description="omitted while events are not available (features.events = false)")
    events_new: list[NonNegInt | None] | None = None

    @model_validator(mode="after")
    def _same_length(self):
        n = (self.end - self.start).days + 1
        for name in ("fires", "hotspots", "frp_sum", "n_sensors", "events_active", "events_new"):
            arr = getattr(self, name)
            if arr is not None and len(arr) != n:
                raise ValueError(f"{name} has {len(arr)} values, expected {n} (start to end).")
        return self


# ===========================================================================
# POST /api/daily/sensors (api_version 3.2): raw detections per day and sensor family
# ===========================================================================

class SensorDailyRequest(AreaSelector, WithConfidence):
    start: dt.date | None = Field(None, description="default first_date from /api/meta")
    end: dt.date | None = Field(None, description="default last_date from /api/meta")

    @model_validator(mode="after")
    def _check(self):
        _check_range(self.start, self.end)
        return self


class FamilyColumns(ResponseModel):
    """null = no satellite of this family operated that day (e.g. VIIRS before 2012-01-20); 0 = nothing detected."""
    detections: list[NonNegInt | None] = Field(description="raw detections (not harmonised), as in /api/hotspots")
    frp_sum: list[NonNegFloat | None] = Field(description="sum of the raw FRP in MW")


class SensorFamilies(ResponseModel):
    modis: FamilyColumns = Field(description="Terra + Aqua")
    viirs: FamilyColumns = Field(description="Suomi NPP + NOAA-20 + NOAA-21")


class SensorDailyResponse(ResponseModel):
    """Column-oriented like /api/daily: index i = day start + i."""
    start: dt.date
    end: dt.date
    families: SensorFamilies

    @model_validator(mode="after")
    def _same_length(self):
        n = (self.end - self.start).days + 1
        for fam in ("modis", "viirs"):
            cols = getattr(self.families, fam)
            for name in ("detections", "frp_sum"):
                if len(getattr(cols, name)) != n:
                    raise ValueError(f"{fam}.{name} has {len(getattr(cols, name))} values, expected {n} (start to end).")
        return self


# ===========================================================================
# 6.6 POST /api/grid
# ===========================================================================

class GridRequest(AreaSelector, WithConfidence):
    """One body for all modes. Which fields are required depends on mode/group_by (§6.6)."""
    mode: Literal["count", "anomaly"] = "count"
    start: dt.date | None = Field(None, description="required in 'count'; in 'anomaly' instead of period")
    end: dt.date | None = None
    bbox: BBox | None = Field(None, description="without bbox the whole area is used")
    resolution: int = Field(ge=H3_RESOLUTION_MIN, le=H3_RESOLUTION_MAX)
    group_by: Literal["day"] | None = Field(None, description="Could-have, only in mode 'count'")
    # anomaly mode only:
    period: str | None = Field(None, pattern=r"^\d{4}(-(0[1-9]|1[0-2]))?$",
                               description="YYYY-MM or YYYY, shorthand instead of start/end")
    compare: Literal["all"] | Annotated[int, Field(ge=1)] = Field(
        "all", description="'all' or N = the N most recent years before the window")
    metric: Metric = "fires"

    @model_validator(mode="after")
    def _check_mode(self):
        if self.mode == "count":
            if self.start is None or self.end is None:
                raise _error("invalid_request", "start and end are required in mode 'count'.")
            if self.period is not None:
                raise _error("invalid_request", "period is only allowed in mode 'anomaly'.")
            _check_range(self.start, self.end,
                         GRID_BY_DAY_MAX_DAYS if self.group_by == "day" else None, "The group_by 'day' period")
        else:
            has_window = self.start is not None or self.end is not None
            if self.period is not None and has_window:
                raise _error("invalid_request", "Provide either period or start/end, not both.")
            if self.period is None and (self.start is None or self.end is None):
                raise _error("invalid_request", "Mode 'anomaly' requires period or start and end.")
            if self.group_by is not None:
                raise _error("invalid_request", "group_by is only allowed in mode 'count'.")
            if self.resolution > ANOMALY_RESOLUTION_MAX:
                raise _error("resolution_out_of_range",
                             f"In mode 'anomaly' resolution must be at most {ANOMALY_RESOLUTION_MAX}.")
            _check_range(self.start, self.end, ANOMALY_WINDOW_MAX_DAYS, "The anomaly window")
        return self


class GridCell(ResponseModel):
    cell: H3Cell
    fires: NonNegFloat
    hotspots: NonNegInt
    frp_sum: NonNegFloat
    first_seen: dt.date | None = Field(None, description="Should-have; first day with a hotspot in the period")
    last_seen: dt.date | None = Field(None, description="Should-have; last day with a hotspot in the period")


class GridCountResponse(ResponseModel):
    mode: Literal["count"]
    resolution: int
    days: NonNegInt
    cells: list[GridCell] = Field(description="only cells with hotspots > 0")
    max: MetricValues


class AnomalyCell(ResponseModel):
    cell: H3Cell
    value: NonNegFloat
    median: NonNegFloat
    diff: float = Field(description="value − median")
    rank: int = Field(ge=1, description="1 = highest value among comparison years + selected year")


class GridAnomalyResponse(ResponseModel):
    mode: Literal["anomaly"]
    resolution: int
    metric: Metric
    start: dt.date
    end: dt.date
    years_compared: NonNegInt
    compare_years: list[int]
    cells: list[AnomalyCell]
    max_abs_diff: NonNegFloat


class GridByDayCell(ResponseModel):
    cell: H3Cell
    d: list[NonNegInt] = Field(description="day index from start, only days with fire")
    fires: list[NonNegFloat]
    hotspots: list[NonNegInt]
    frp_sum: list[NonNegFloat]

    @model_validator(mode="after")
    def _same_length(self):
        if not (len(self.d) == len(self.fires) == len(self.hotspots) == len(self.frp_sum)):
            raise ValueError("d, fires, hotspots and frp_sum must have the same length.")
        return self


class GridByDayResponse(ResponseModel):
    mode: Literal["count"]
    resolution: int
    group_by: Literal["day"]
    start: dt.date
    end: dt.date
    cells: list[GridByDayCell]


# Order matters: check ByDay before Count (both have mode = "count")
GridResponse = Union[GridAnomalyResponse, GridByDayResponse, GridCountResponse]


# ===========================================================================
# 6.7 POST /api/hotspots
# ===========================================================================

class HotspotsRequest(AreaSelector, WithConfidence):
    start: dt.date
    end: dt.date
    bbox: BBox | None = None
    limit: int = Field(HOTSPOTS_DEFAULT, ge=1, le=HOTSPOTS_MAX)
    event_id: EventId | None = Field(None, description="only points of this event up to end")
    min_frp: NonNegFloat | None = Field(None, description="Could-have; applies to the points only")
    raw: bool = Field(False, description="true = all points of both sensor families (e.g. MODIS after 2012), "
                                         "not only those of the harmonised series")

    @model_validator(mode="after")
    def _check(self):
        _check_range(self.start, self.end)
        return self


class HotspotProperties(ResponseModel):
    time: dt.datetime
    sensor: Sensor
    confidence: Confidence
    frp: NonNegFloat | None
    daynight: DayNight
    weight: NonNegFloat
    province_id: RegionId
    event_id: EventId | None


class HotspotFeature(ResponseModel):
    type: Literal["Feature"]
    id: int = Field(description="primary key, stable (for feature-state)")
    geometry: Point
    properties: HotspotProperties


class HotspotsResponse(ResponseModel):
    type: Literal["FeatureCollection"]
    features: list[HotspotFeature]
    total: NonNegInt
    returned: NonNegInt
    truncated: bool


# ===========================================================================
# 6.8 GET /api/export.csv  (query parameters; the response is CSV – no response DTO)
# ===========================================================================

class ExportQuery(WithConfidence):
    region_id: RegionId | None = None
    area_id: AreaId | None = None
    event_id: EventId | None = Field(None, description="Could-have: all points of one event up to end")
    start: dt.date | None = Field(None, description="required, except with event_id")
    end: dt.date

    @model_validator(mode="after")
    def _check(self):
        if self.region_id is not None and self.area_id is not None:
            raise _error("area_conflict", "Please provide only one of region_id and area_id.")
        if self.start is None and self.event_id is None:
            raise _error("invalid_request", "start is required (except with event_id).")
        _check_range(self.start, self.end)
        return self


EXPORT_CSV_COLUMNS = (
    "id", "time", "lat", "lon", "sensor", "confidence", "confidence_raw", "frp",
    "daynight", "weight", "n_active", "province_id", "event_id",
)


# ===========================================================================
# 6.9 POST /api/events   and   6.10 GET /api/events/{id}
# ===========================================================================

class EventsRequest(AreaSelector, WithConfidence):
    date: dt.date = Field(description="reference date D")
    lookback_days: int = Field(7, ge=1, le=LOOKBACK_DAYS_MAX)
    bbox: BBox | None = None
    sort: EventSort = "frp_sum"
    limit: int = Field(EVENTS_DEFAULT, ge=1, le=EVENTS_MAX)


class Landcover(ResponseModel):
    code: int = Field(examples=[312])
    label: str = Field(examples=["Coniferous forest"])


class EventProperties(ResponseModel):
    """All values as of reference date D, computed only from points up to and including D (§5.6)."""
    start: dt.date
    last_seen: dt.date
    duration_days: int = Field(ge=1)
    days_since_last: NonNegInt
    active: bool = Field(description="hotspot on day D")
    new: bool = Field(description="became an event on D (on D it reached 2 hotspots; usually start == D)")
    ended: bool = Field(description="days_since_last > 2")
    hotspots: NonNegInt
    fires: NonNegFloat
    frp_sum: NonNegFloat
    frp_max: NonNegFloat | None
    area_km2: NonNegFloat = Field(description="affected area (approx.), sum of H3 cells at resolution 8")
    cells: NonNegInt
    centroid: Position
    bbox: BBox
    province_id: RegionId
    sensors: list[Sensor]
    trend: Trend | None = Field(None, description="Could-have")
    landcover: Landcover | None = Field(None, description="Could-have")
    core_geometry: AreaGeometry | None = Field(
        None, description="cells of the dense core (largest group of directly neighbouring cells); null = no extension")
    extension_geometry: AreaGeometry | None = Field(
        None, description="cells joined to the core only through the wider ring (2 cells); null = no extension")


class EventFeature(ResponseModel):
    type: Literal["Feature"]
    id: EventId
    geometry: AreaGeometry
    properties: EventProperties


class EventsSummary(ResponseModel):
    active: NonNegInt
    new: NonNegInt
    active_previous_day: NonNegInt


class EventsResponse(ResponseModel):
    type: Literal["FeatureCollection"]
    date: dt.date
    lookback_days: int
    features: list[EventFeature]
    summary: EventsSummary = Field(description="counts all events in the area, regardless of limit")
    total: NonNegInt
    returned: NonNegInt
    truncated: bool


class EventDay(ResponseModel):
    date: dt.date
    hotspots: NonNegInt
    fires: NonNegFloat
    frp_sum: NonNegFloat
    new_cells: NonNegInt


class EventDetailResponse(EventFeature):
    daily: list[EventDay] = Field(description="without gaps from start to last_seen")


# ===========================================================================
# 6.11 POST /api/by-region (could-have)
# ===========================================================================

class ByRegionRequest(AreaSelector, WithConfidence):
    start: dt.date
    end: dt.date
    level: Literal["region", "province"]

    @model_validator(mode="after")
    def _check(self):
        _check_range(self.start, self.end)
        return self


class ByRegionItem(ResponseModel):
    id: RegionId
    name: str
    fires: NonNegFloat
    hotspots: NonNegInt
    frp_sum: NonNegFloat
    share: float = Field(ge=0, le=1)


class ByRegionResponse(ResponseModel):
    level: Literal["region", "province"]
    total_fires: NonNegFloat
    data: list[ByRegionItem]


# ===========================================================================
# Data sync: POST /api/sync, GET /api/sync (api_version 3.1)
# ===========================================================================

SyncState = Literal["idle", "running", "succeeded", "failed"]
SyncStep = Literal["fetch", "harmonise", "load"]


class SyncStatus(ResponseModel):
    state: SyncState = Field(description="idle = no sync since the backend started")
    step: SyncStep | None = Field(description="step of the running sync, or the step a failed sync stopped at: "
                                              "fetch FIRMS, harmonisation, loading into the database")
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    new_rows: NonNegInt | None = Field(description="new hotspot rows from FIRMS, set once the sync succeeded")
    message: str | None = Field(description="English error text, set when the sync failed")


# ===========================================================================
# 8. Errors
# ===========================================================================

ErrorCode = Literal[
    "INVALID_REQUEST", "INVALID_DATE_RANGE", "AREA_CONFLICT", "GEOMETRY_INVALID",
    "AREA_OUTSIDE_REGION", "LIMIT_TOO_HIGH", "RESOLUTION_OUT_OF_RANGE",
    "REGION_NOT_FOUND", "AREA_NOT_FOUND", "EVENT_NOT_FOUND",
    "GEOMETRY_TOO_COMPLEX", "INTERNAL_ERROR", "NOT_IMPLEMENTED", "QUERY_TIMEOUT",
]


class ErrorDetail(ResponseModel):
    code: ErrorCode
    message: str = Field(description="English text, may be shown to the user")


class ErrorResponse(ResponseModel):
    error: ErrorDetail
