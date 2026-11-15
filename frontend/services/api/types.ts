/**
 * Fire-API v3 – short names for the generated DTOs.
 *
 * Do NOT edit schema.d.ts by hand; regenerate it whenever the backend changes: `npm run gen:types`
 */
import type { components, paths } from "./schema";

type S = components["schemas"];

export type { paths };

export type MetaResponse = S["MetaResponse"];
export type Features = S["Features"];
export type Limits = S["Limits"];
export type ForecastDailyResponse = S["ForecastDailyResponse"];
export type ForecastDay = S["ForecastDay"];
export type ForecastStatusResponse = S["ForecastStatusResponse"];
export type RiskClass = ForecastDay["risk_class"];
export type RegionsResponse = S["RegionsResponse"];
export type RegionFeature = S["RegionFeature"];
export type RegionProperties = S["RegionProperties"];
export type AreaRequest = S["AreaRequest"];
export type AreaResponse = S["AreaResponse"];
export type CalendarRequest = S["CalendarRequest"];
export type CalendarResponse = S["CalendarResponse"];
export type CalendarMonth = S["CalendarMonth"];
export type DailyRequest = S["DailyRequest"];
export type DailyResponse = S["DailyResponse"];
export type GridRequest = S["GridRequest"];
export type GridCountResponse = S["GridCountResponse"];
export type GridAnomalyResponse = S["GridAnomalyResponse"];
export type GridByDayResponse = S["GridByDayResponse"];
export type GridResponse = GridCountResponse | GridAnomalyResponse | GridByDayResponse;
export type GridCell = S["GridCell"];
export type AnomalyCell = S["AnomalyCell"];
export type MetricValues = S["MetricValues"];
export type HotspotsRequest = S["HotspotsRequest"];
export type HotspotsResponse = S["HotspotsResponse"];
export type HotspotFeature = S["HotspotFeature"];
export type HotspotProperties = S["HotspotProperties"];
export type EventsRequest = S["EventsRequest"];
export type EventsResponse = S["EventsResponse"];
export type EventFeature = S["EventFeature"];
export type EventProperties = S["EventProperties"];
export type EventDetailResponse = S["EventDetailResponse"];
export type EventDay = S["EventDay"];
export type ErrorResponse = S["ErrorResponse"];
export type SyncStatus = S["SyncStatus"];
export type SensorDailyRequest = S["SensorDailyRequest"];
export type SensorDailyResponse = S["SensorDailyResponse"];
export type FamilyColumns = S["FamilyColumns"];
export type Polygon = S["Polygon"];
export type MultiPolygon = S["MultiPolygon"];
export type Geometry = Polygon | MultiPolygon;

export type Sensor = S["SensorInfo"]["id"];
export type Confidence = NonNullable<S["CalendarRequest"]["min_confidence"]>;
export type Metric = NonNullable<S["GridRequest"]["metric"]>;
export type EventSort = NonNullable<S["EventsRequest"]["sort"]>;
export type ErrorCode = S["ErrorDetail"]["code"];
export type RegionLevel = RegionProperties["level"];
export type ApiBBox = [number, number, number, number];

export type ExportQuery = NonNullable<paths["/api/export.csv"]["get"]["parameters"]["query"]>;

/** Area selection (§2): at most one of these; none = all of ES + PT */
export type AreaSelector =
  | { region_id: string; area_id?: never; geometry?: never }
  | { area_id: string; region_id?: never; geometry?: never }
  | { geometry: Geometry; region_id?: never; area_id?: never }
  | { region_id?: never; area_id?: never; geometry?: never };

// /api/grid returns one of three shapes depending on the request
export const isGridAnomaly = (r: GridResponse): r is GridAnomalyResponse => r.mode === "anomaly";
export const isGridByDay = (r: GridResponse): r is GridByDayResponse => "group_by" in r;
export const isGridCount = (r: GridResponse): r is GridCountResponse => r.mode === "count" && !("group_by" in r);
