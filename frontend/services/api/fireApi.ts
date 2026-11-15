/** One small typed function per endpoint of the Fire-API v3 (spec §3). */
import { apiPost, apiRequest, apiUrl } from "./client";
import type {
  AreaRequest, CalendarRequest, DailyRequest, EventDetailResponse, EventsRequest, ExportQuery, GridRequest, HiddenFiresRequest,
  HotspotsRequest, MetaResponse, RegionsResponse,
} from "./types";

export const fireApi = {
  meta: (signal?: AbortSignal) => apiRequest<MetaResponse>("GET", "/api/meta", { signal }),
  regions: (signal?: AbortSignal) => apiRequest<RegionsResponse>("GET", "/api/regions", { signal }),
  calendar: (body: CalendarRequest, signal?: AbortSignal) => apiPost("/api/calendar", body, signal),
  daily: (body: DailyRequest, signal?: AbortSignal) => apiPost("/api/daily", body, signal),
  grid: (body: GridRequest, signal?: AbortSignal) => apiPost("/api/grid", body, signal),
  hotspots: (body: HotspotsRequest, signal?: AbortSignal) => apiPost("/api/hotspots", body, signal),
  areas: (body: AreaRequest, signal?: AbortSignal) => apiPost("/api/areas", body, signal),
  events: (body: EventsRequest, signal?: AbortSignal) => apiPost("/api/events", body, signal),
  hiddenFires: (body: HiddenFiresRequest, signal?: AbortSignal) => apiPost("/api/events/hidden", body, signal),
  eventDetail: (id: string, date: string, signal?: AbortSignal) =>
    apiRequest<EventDetailResponse>("GET", `/api/events/${encodeURIComponent(id)}`, { query: { date }, signal }),
};

/** Link for <a href> (spec §6.8). */
export function exportCsvUrl(params: ExportQuery): string {
  return apiUrl("/api/export.csv", params);
}
