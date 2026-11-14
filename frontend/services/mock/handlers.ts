/**
 * Mock implementation of every Fire-API v3 endpoint on top of the synthetic world.
 * Validation and error codes follow spec §8, so the frontend error handling can be tested too.
 */
import { cellsToMultiPolygon, latLngToCell } from "h3-js";
import type {
  AreaResponse, CalendarMonth, CalendarResponse, Confidence, DailyResponse, ErrorCode, EventDetailResponse,
  EventFeature, EventProperties, EventSort, EventsResponse, ExportQuery, Features, Geometry, GridAnomalyResponse,
  GridByDayResponse, GridCountResponse, GridRequest, HotspotFeature, HotspotsResponse, Limits, MetaResponse, Metric,
  RegionsResponse, Sensor,
} from "../api/types";
import { addDays, daysBetween, daysInMonth, isIsoDate, isoFromParts, shiftYears, yearOf } from "../../lib/dates";
import {
  bboxIntersects, bboxOf, countVertices, geometryAreaKm2, pointInBbox, pointInGeometry, polygonsOf, toMultiPolygon,
  type BBox, type Position,
} from "../../lib/geo";
import { hex12 } from "./rng";
import { hotspotsOf, SENSORS, type MockEvent, type MockEventDay, type MockHotspot, type World } from "./world";

export class MockApiError extends Error {
  constructor(public status: number, public code: ErrorCode, message: string) {
    super(message);
  }
}

const fail = (status: number, code: ErrorCode, message: string): never => {
  throw new MockApiError(status, code, message);
};

export const LIMITS: Limits = {
  hotspots_default: 5000,
  hotspots_max: 20000,
  events_default: 500,
  events_max: 2000,
  lookback_days_max: 60,
  geometry_max_vertices: 1000,
  h3_resolution_min: 3,
  h3_resolution_max: 8,
  anomaly_resolution_max: 5,
  anomaly_window_max_days: 366,
  grid_by_day_max_days: 150,
};

/** Above this window length the grid is built from event-day centres instead of single points. */
const POINT_WINDOW_MAX_DAYS = 120;
/** Coarse cells (≥ 250 km²) are built from event-day centres – precise enough and much faster. */
const POINT_MIN_RESOLUTION = 6;
const H3_R8_AREA_KM2 = 0.737;

const r1 = (v: number) => Math.round(v * 10) / 10;
const r3 = (v: number) => Math.round(v * 1000) / 1000;
const r4 = (v: number) => Math.round(v * 1e4) / 1e4;

type Filter =
  | { kind: "all" }
  | { kind: "region"; level: "country" | "region" | "province"; id: string }
  | { kind: "geom"; geometry: Geometry; bbox: BBox };

interface AreaFields {
  region_id?: string | null;
  area_id?: string | null;
  geometry?: Geometry | null;
}

export class MockApi {
  private areas = new Map<string, Geometry>();
  private pointCache = new Map<number, MockHotspot[]>();
  private dailyCache = new Map<string, DailyResponse>();
  private eventStateCache = new Map<string, EventState | null>();
  private cellCache = new Map<number, string[]>();

  constructor(private world: World, private features: Features) {}

  // ---------------------------------------------------------------- helpers

  private dayIndex = (date: string) => daysBetween(this.world.firstDate, date);
  private dateOf = (day: number) => addDays(this.world.firstDate, day);

  private points(ed: MockEventDay): MockHotspot[] {
    let pts = this.pointCache.get(ed.idx);
    if (!pts) {
      pts = hotspotsOf(this.world, ed);
      if (this.pointCache.size > 6000) this.pointCache.delete(this.pointCache.keys().next().value as number);
      this.pointCache.set(ed.idx, pts);
    }
    return pts;
  }

  private checkDate(value: unknown, field: string): string {
    if (typeof value !== "string" || !isIsoDate(value)) fail(400, "INVALID_REQUEST", `${field}: Input should be a valid date`);
    return value as string;
  }

  private checkRange(start: string, end: string, maxDays?: number, what = "The period") {
    if (start > end) fail(400, "INVALID_DATE_RANGE", "start is after end.");
    if (start < this.world.firstDate || end > this.world.lastDate) {
      fail(400, "INVALID_DATE_RANGE", `The period must lie within ${this.world.firstDate} … ${this.world.lastDate}.`);
    }
    if (maxDays !== undefined && daysBetween(start, end) + 1 > maxDays) {
      fail(400, "INVALID_DATE_RANGE", `${what} must not be longer than ${maxDays} days.`);
    }
  }

  private validateGeometry(g: unknown): Geometry {
    const geom = g as Geometry | null;
    if (!geom || (geom.type !== "Polygon" && geom.type !== "MultiPolygon") || !Array.isArray(geom.coordinates)) {
      return fail(400, "GEOMETRY_INVALID", "The area is not a valid Polygon or MultiPolygon.");
    }
    const ok = polygonsOf(geom).every((p) => p.length > 0 && p.every((r) => Array.isArray(r) && r.length >= 4));
    if (!ok) fail(400, "GEOMETRY_INVALID", "The area is not a valid Polygon or MultiPolygon.");
    const n = countVertices(geom);
    if (n > LIMITS.geometry_max_vertices) {
      fail(413, "GEOMETRY_TOO_COMPLEX", `The area has ${n} vertices, the maximum is ${LIMITS.geometry_max_vertices}.`);
    }
    return geom;
  }

  private resolveArea(body: AreaFields): Filter {
    const given = [body.region_id, body.area_id, body.geometry].filter((v) => v !== undefined && v !== null);
    if (given.length > 1) fail(400, "AREA_CONFLICT", "Please provide only one of region_id, area_id and geometry.");
    if (body.region_id) {
      const f = this.world.regionById.get(body.region_id);
      if (!f) return fail(404, "REGION_NOT_FOUND", `Unknown region '${body.region_id}'.`);
      return { kind: "region", level: f.properties.level, id: f.properties.id };
    }
    if (body.area_id) {
      const g = this.areas.get(body.area_id);
      if (!g) return fail(404, "AREA_NOT_FOUND", `Area ${body.area_id} is unknown.`);
      return { kind: "geom", geometry: g, bbox: bboxOf(g) };
    }
    if (body.geometry) {
      const g = this.validateGeometry(body.geometry);
      return { kind: "geom", geometry: g, bbox: bboxOf(g) };
    }
    return { kind: "all" };
  }

  private static eventMatches(ev: MockEvent, f: Filter): boolean {
    if (f.kind !== "region") return true;
    if (f.level === "country") return ev.countryId === f.id;
    if (f.level === "region") return ev.regionId === f.id;
    return ev.provinceId === f.id;
  }

  private static dayMatches(ed: MockEventDay, f: Filter): boolean {
    return f.kind !== "geom" || (bboxIntersects(ed.bbox, f.bbox) && pointInGeometry(ed.center, f.geometry));
  }

  private static pointMatches(h: MockHotspot, f: Filter): boolean {
    return f.kind !== "geom" || pointInGeometry([h.lon, h.lat], f.geometry);
  }

  private static filterKey(f: Filter): string {
    if (f.kind === "all") return "all";
    if (f.kind === "region") return `r:${f.id}`;
    return `g:${JSON.stringify(f.geometry.coordinates)}`;
  }

  /** Event-days of a window that may match area and bbox (cheap pre-filter before generating points). */
  private *candidateDays(s: number, e: number, f: Filter, bbox?: BBox | null): Generator<[MockEventDay, MockEvent]> {
    const { byDay, eventDays, events } = this.world;
    for (let d = Math.max(0, s); d <= Math.min(e, byDay.length - 1); d++) {
      for (const idx of byDay[d]) {
        const ed = eventDays[idx];
        const ev = events[ed.event];
        if (!MockApi.eventMatches(ev, f)) continue;
        if (f.kind === "geom" && !bboxIntersects(ed.bbox, f.bbox)) continue;
        if (bbox && !bboxIntersects(ed.bbox, bbox)) continue;
        yield [ed, ev];
      }
    }
  }

  // ---------------------------------------------------------------- 6.1 / 6.2

  meta(): MetaResponse {
    const last = this.world.lastDate;
    return {
      api_version: "3.0",
      data_version: `${last}.mock`,
      weight_version: "w1",
      first_date: this.world.firstDate,
      last_date: last,
      last_update: `${addDays(last, 1)}T03:00:00Z`,
      region: "Spain + Portugal (mainland and Balearic Islands)",
      bbox: [-9.6, 35.9, 4.4, 43.9],
      sensors: SENSORS.map((s) => ({ id: s.id, from: s.from, to: s.to !== null && s.to < last ? s.to : null })),
      confidence_levels: ["nominal", "high"],
      features: this.features,
      limits: LIMITS,
      attribution: "Fire data: NASA FIRMS (MODIS, VIIRS 375 m) – MOCK DATA · Boundaries: © EuroGeographics",
    };
  }

  regions(): RegionsResponse {
    return this.world.regions;
  }

  // ---------------------------------------------------------------- 6.3

  registerArea(body: { geometry?: unknown }): AreaResponse {
    if (!this.features.areas) fail(501, "NOT_IMPLEMENTED", "Areas are not available yet.");
    const g = this.validateGeometry(body.geometry);
    const bbox = bboxOf(g);
    if (!bboxIntersects(bbox, [-9.6, 35.9, 4.4, 43.9]) || !this.touchesLand(g, bbox)) {
      fail(400, "AREA_OUTSIDE_REGION", "The area lies completely outside Spain and Portugal.");
    }
    const multi = toMultiPolygon(g);
    const coords = multi.coordinates.map((p) => p.map((r) => r.map(([x, y]) => [r4(x), r4(y)] as [number, number])));
    const id = `a_${hex12(JSON.stringify(coords))}`;
    const geometry = { type: "MultiPolygon" as const, coordinates: coords };
    this.areas.set(id, geometry);
    return {
      area_id: id,
      geometry,
      bbox: bbox.map(r4) as BBox,
      area_km2: r1(geometryAreaKm2(geometry)),
      vertices: countVertices(geometry),
    };
  }

  private touchesLand(g: Geometry, bbox: BBox): boolean {
    const steps = 12;
    for (let i = 0; i <= steps; i++) {
      for (let j = 0; j <= steps; j++) {
        const p: Position = [bbox[0] + ((bbox[2] - bbox[0]) * i) / steps, bbox[1] + ((bbox[3] - bbox[1]) * j) / steps];
        if (pointInGeometry(p, g) && this.world.locate(p)) return true;
      }
    }
    return polygonsOf(g).some((poly) => poly[0].some((p) => this.world.locate(p) !== null));
  }

  // ---------------------------------------------------------------- 6.5 / 6.4

  daily(body: AreaFields & { min_confidence?: Confidence }): DailyResponse {
    if (!this.features.daily) fail(501, "NOT_IMPLEMENTED", "Daily values are not available yet.");
    const f = this.resolveArea(body);
    const conf = body.min_confidence ?? "nominal";
    const key = `${MockApi.filterKey(f)}|${conf}`;
    const cached = this.dailyCache.get(key);
    if (cached) return cached;

    const { nDays, nActive, events, eventDays } = this.world;
    const fires = new Float64Array(nDays);
    const hotspots = new Int32Array(nDays);
    const frp = new Float64Array(nDays);
    const active = new Int32Array(nDays);
    const fresh = new Int32Array(nDays);
    for (const ev of events) {
      if (!MockApi.eventMatches(ev, f)) continue;
      ev.days.forEach((idx, i) => {
        const ed = eventDays[idx];
        if (!MockApi.dayMatches(ed, f)) return;
        const agg = conf === "high" ? ed.high : ed.all;
        if (agg.hotspots === 0) return;
        fires[ed.day] += agg.fires;
        hotspots[ed.day] += agg.hotspots;
        frp[ed.day] += agg.frp;
        active[ed.day]++;
        if (i === 0) fresh[ed.day]++;
      });
    }
    const col = <T>(fn: (i: number) => T): (T | null)[] =>
      Array.from({ length: nDays }, (_, i) => (nActive[i] === 0 ? null : fn(i)));
    const res: DailyResponse = {
      start: this.world.firstDate,
      end: this.world.lastDate,
      fires: col((i) => r1(fires[i])),
      hotspots: col((i) => hotspots[i]),
      frp_sum: col((i) => r1(frp[i])),
      n_sensors: Array.from(nActive),
      ...(this.features.events ? { events_active: col((i) => active[i]), events_new: col((i) => fresh[i]) } : {}),
    };
    if (this.dailyCache.size > 40) this.dailyCache.clear();
    this.dailyCache.set(key, res);
    return res;
  }

  calendar(body: AreaFields & { min_confidence?: Confidence }): CalendarResponse {
    const daily = this.daily(body);
    const last = this.world.lastDate;
    const sum = (col: (number | null)[], from: string, to: string) => {
      let s = 0;
      let missing = false;
      for (let i = Math.max(0, this.dayIndex(from)); i <= Math.min(col.length - 1, this.dayIndex(to)); i++) {
        const v = col[i];
        if (v === null) missing = true;
        else s += v;
      }
      return { s, missing };
    };
    const data: CalendarMonth[] = [];
    const max = { fires: 0, hotspots: 0, frp_sum: 0 };
    for (let y = yearOf(this.world.firstDate); y <= yearOf(last); y++) {
      for (let m = 1; m <= 12; m++) {
        const from = isoFromParts(y, m, 1);
        const to = isoFromParts(y, m, daysInMonth(y, m));
        if (to < this.world.firstDate || from > last) continue;
        const fi = sum(daily.fires, from, to);
        const ho = sum(daily.hotspots, from, to);
        const fr = sum(daily.frp_sum, from, to);
        const status = to > last ? "running" : fi.missing ? "incomplete" : "complete";
        data.push({ year: y, month: m, fires: r1(fi.s), hotspots: ho.s, frp_sum: r1(fr.s), status });
        if (status === "complete") {
          max.fires = Math.max(max.fires, r1(fi.s));
          max.hotspots = Math.max(max.hotspots, ho.s);
          max.frp_sum = Math.max(max.frp_sum, r1(fr.s));
        }
      }
    }
    const [ly, lm, ld] = last.split("-").map(Number);
    const running = ld !== daysInMonth(ly, lm);
    return {
      data,
      max,
      running_month: running
        ? {
            month: last.slice(0, 7),
            through: last,
            same_period: Array.from({ length: ly - yearOf(this.world.firstDate) }, (_, k) => yearOf(this.world.firstDate) + k)
              .filter((y) => isoFromParts(y, lm, 1) >= this.world.firstDate)
              .map((y) => ({
                year: y,
                fires: r1(sum(daily.fires, isoFromParts(y, lm, 1), isoFromParts(y, lm, ld)).s),
                frp_sum: r1(sum(daily.frp_sum, isoFromParts(y, lm, 1), isoFromParts(y, lm, ld)).s),
              })),
          }
        : null,
    };
  }

  // ---------------------------------------------------------------- 6.6

  grid(body: GridRequest): GridCountResponse | GridAnomalyResponse | GridByDayResponse {
    const res = body.resolution;
    if (!Number.isInteger(res) || res < LIMITS.h3_resolution_min || res > LIMITS.h3_resolution_max) {
      fail(400, "RESOLUTION_OUT_OF_RANGE", `resolution: must be between ${LIMITS.h3_resolution_min} and ${LIMITS.h3_resolution_max}.`);
    }
    const f = this.resolveArea(body);
    const conf = body.min_confidence ?? "nominal";
    const bbox = (body.bbox ?? null) as BBox | null;
    if ((body.mode ?? "count") === "anomaly") return this.gridAnomaly(body, f, conf, bbox);
    if (!body.start || !body.end) return fail(400, "INVALID_REQUEST", "start and end are required in mode 'count'.");
    const start = this.checkDate(body.start, "start");
    const end = this.checkDate(body.end, "end");
    if (body.group_by === "day") {
      if (!this.features.grid_by_day) fail(501, "NOT_IMPLEMENTED", "group_by 'day' is not available yet.");
      this.checkRange(start, end, LIMITS.grid_by_day_max_days, "The group_by 'day' period");
      return this.gridByDay(start, end, res, f, conf, bbox);
    }
    this.checkRange(start, end);
    return this.gridCount(start, end, res, f, conf, bbox);
  }

  private gridCount(start: string, end: string, res: number, f: Filter, conf: Confidence, bbox: BBox | null): GridCountResponse {
    const s = this.dayIndex(start);
    const e = this.dayIndex(end);
    const cells = new Map<string, { fires: number; hotspots: number; frp: number; first: number; last: number }>();
    const add = (cell: string, day: number, fires: number, hotspots: number, frp: number) => {
      const c = cells.get(cell);
      if (!c) cells.set(cell, { fires, hotspots, frp, first: day, last: day });
      else {
        c.fires += fires;
        c.hotspots += hotspots;
        c.frp += frp;
        c.first = Math.min(c.first, day);
        c.last = Math.max(c.last, day);
      }
    };
    if (e - s + 1 <= POINT_WINDOW_MAX_DAYS && res >= POINT_MIN_RESOLUTION) {
      for (const [ed] of this.candidateDays(s, e, f, bbox)) {
        for (const h of this.points(ed)) {
          if (conf === "high" && h.confidence !== "high") continue;
          if (bbox && !pointInBbox([h.lon, h.lat], bbox)) continue;
          if (!MockApi.pointMatches(h, f)) continue;
          add(latLngToCell(h.lat, h.lon, res), ed.day, h.weight, 1, h.frpH);
        }
      }
    } else {
      for (const [ed] of this.candidateDays(s, e, f, bbox)) {
        if (!MockApi.dayMatches(ed, f) || (bbox && !pointInBbox(ed.center, bbox))) continue;
        const agg = conf === "high" ? ed.high : ed.all;
        if (agg.hotspots > 0) add(latLngToCell(ed.center[1], ed.center[0], res), ed.day, agg.fires, agg.hotspots, agg.frp);
      }
    }
    const max = { fires: 0, hotspots: 0, frp_sum: 0 };
    const out = [...cells].map(([cell, c]) => {
      max.fires = Math.max(max.fires, r1(c.fires));
      max.hotspots = Math.max(max.hotspots, c.hotspots);
      max.frp_sum = Math.max(max.frp_sum, r1(c.frp));
      return {
        cell, fires: r1(c.fires), hotspots: c.hotspots, frp_sum: r1(c.frp),
        first_seen: this.dateOf(c.first), last_seen: this.dateOf(c.last),
      };
    });
    return { mode: "count", resolution: res, days: e - s + 1, cells: out, max };
  }

  private gridByDay(start: string, end: string, res: number, f: Filter, conf: Confidence, bbox: BBox | null): GridByDayResponse {
    const s = this.dayIndex(start);
    const e = this.dayIndex(end);
    const cells = new Map<string, Map<number, { fires: number; hotspots: number; frp: number }>>();
    for (const [ed] of this.candidateDays(s, e, f, bbox)) {
      for (const h of this.points(ed)) {
        if (conf === "high" && h.confidence !== "high") continue;
        if (bbox && !pointInBbox([h.lon, h.lat], bbox)) continue;
        if (!MockApi.pointMatches(h, f)) continue;
        const cell = latLngToCell(h.lat, h.lon, res);
        const byDay = cells.get(cell) ?? new Map();
        const v = byDay.get(ed.day - s) ?? { fires: 0, hotspots: 0, frp: 0 };
        v.fires += h.weight;
        v.hotspots++;
        v.frp += h.frpH;
        byDay.set(ed.day - s, v);
        cells.set(cell, byDay);
      }
    }
    return {
      mode: "count",
      resolution: res,
      group_by: "day",
      start,
      end,
      cells: [...cells].map(([cell, byDay]) => {
        const days = [...byDay.keys()].sort((a, b) => a - b);
        return {
          cell,
          d: days,
          fires: days.map((d) => r1(byDay.get(d)?.fires ?? 0)),
          hotspots: days.map((d) => byDay.get(d)?.hotspots ?? 0),
          frp_sum: days.map((d) => r1(byDay.get(d)?.frp ?? 0)),
        };
      }),
    };
  }

  private gridAnomaly(body: GridRequest, f: Filter, conf: Confidence, bbox: BBox | null): GridAnomalyResponse {
    if (!this.features.anomaly) fail(501, "NOT_IMPLEMENTED", "Anomaly mode is not available yet.");
    if (body.resolution > LIMITS.anomaly_resolution_max) {
      fail(400, "RESOLUTION_OUT_OF_RANGE", `In mode 'anomaly' resolution must be at most ${LIMITS.anomaly_resolution_max}.`);
    }
    if (body.group_by) fail(400, "INVALID_REQUEST", "group_by is only allowed in mode 'count'.");
    const hasWindow = !!body.start || !!body.end;
    if (body.period && hasWindow) fail(400, "INVALID_REQUEST", "Provide either period or start/end, not both.");
    let start: string;
    let end: string;
    if (body.period) {
      if (!/^\d{4}(-(0[1-9]|1[0-2]))?$/.test(body.period)) fail(400, "INVALID_REQUEST", "period: must be YYYY or YYYY-MM.");
      const [y, m] = body.period.split("-").map(Number);
      start = m ? isoFromParts(y, m, 1) : `${y}-01-01`;
      end = m ? isoFromParts(y, m, daysInMonth(y, m)) : `${y}-12-31`;
      if (end > this.world.lastDate) end = this.world.lastDate;
    } else {
      if (!this.features.anomaly_window) fail(501, "NOT_IMPLEMENTED", "Anomaly with start/end is not available yet, use period.");
      if (!body.start || !body.end) return fail(400, "INVALID_REQUEST", "Mode 'anomaly' requires period or start and end.");
      start = this.checkDate(body.start, "start");
      end = this.checkDate(body.end, "end");
    }
    this.checkRange(start, end, LIMITS.anomaly_window_max_days, "The anomaly window");

    const metric: Metric = body.metric ?? "fires";
    const y0 = yearOf(start);
    const complete = (ws: string, we: string) => {
      if (ws < this.world.firstDate || we > this.world.lastDate) return false;
      for (let d = this.dayIndex(ws); d <= this.dayIndex(we); d++) if (this.world.nActive[d] === 0) return false;
      return true;
    };
    let years: number[] = [];
    for (let y = yearOf(this.world.firstDate); y <= yearOf(this.world.lastDate); y++) {
      if (y !== y0 && complete(shiftYears(start, y - y0), shiftYears(end, y - y0))) years.push(y);
    }
    const compare = body.compare ?? "all";
    if (compare !== "all") years = years.filter((y) => y < y0).slice(-compare);

    const valuesFor = (y: number) => {
      const map = new Map<string, number>();
      const s = this.dayIndex(shiftYears(start, y - y0));
      const e = this.dayIndex(shiftYears(end, y - y0));
      for (const [ed] of this.candidateDays(s, e, f, bbox)) {
        if (!MockApi.dayMatches(ed, f) || (bbox && !pointInBbox(ed.center, bbox))) continue;
        const agg = conf === "high" ? ed.high : ed.all;
        const v = metric === "fires" ? agg.fires : metric === "hotspots" ? agg.hotspots : agg.frp;
        if (v <= 0) continue;
        const cell = latLngToCell(ed.center[1], ed.center[0], body.resolution);
        map.set(cell, (map.get(cell) ?? 0) + v);
      }
      return map;
    };
    const selected = valuesFor(y0);
    const history = years.map(valuesFor);
    const all = new Set<string>([...selected.keys(), ...history.flatMap((m) => [...m.keys()])]);
    let maxAbs = 0;
    const cells = [...all].flatMap((cell) => {
      const value = selected.get(cell) ?? 0;
      const vs = history.map((m) => m.get(cell) ?? 0).sort((a, b) => a - b);
      const med = vs.length === 0 ? 0 : vs.length % 2 ? vs[(vs.length - 1) / 2] : (vs[vs.length / 2 - 1] + vs[vs.length / 2]) / 2;
      if (value === 0 && med === 0) return [];
      const diff = value - med;
      maxAbs = Math.max(maxAbs, Math.abs(diff));
      return [{ cell, value: r1(value), median: r1(med), diff: r1(diff), rank: 1 + vs.filter((v) => v > value).length }];
    });
    return {
      mode: "anomaly", resolution: body.resolution, metric, start, end,
      years_compared: years.length, compare_years: years, cells, max_abs_diff: r1(maxAbs),
    };
  }

  // ---------------------------------------------------------------- 6.7 / 6.8

  private collectPoints(
    f: Filter, conf: Confidence, startDay: number, endDay: number, bbox: BBox | null, eventId: string | null | undefined,
  ): [MockHotspot, MockEvent][] {
    const out: [MockHotspot, MockEvent][] = [];
    const keep = (h: MockHotspot) =>
      !(conf === "high" && h.confidence !== "high") && !(bbox && !pointInBbox([h.lon, h.lat], bbox)) && MockApi.pointMatches(h, f);
    if (eventId) {
      const ev = this.world.eventById.get(eventId);
      if (!ev) return fail(404, "EVENT_NOT_FOUND", `Event ${eventId} is unknown.`);
      if (!MockApi.eventMatches(ev, f)) return out;
      for (const idx of ev.days) {
        const ed = this.world.eventDays[idx];
        if (ed.day > endDay) break;
        for (const h of this.points(ed)) if (keep(h)) out.push([h, ev]);
      }
      return out;
    }
    for (const [ed, ev] of this.candidateDays(startDay, endDay, f, bbox)) {
      for (const h of this.points(ed)) if (keep(h)) out.push([h, ev]);
    }
    return out;
  }

  hotspots(body: {
    start?: string; end?: string; limit?: number; bbox?: BBox | null; event_id?: string | null; min_frp?: number | null;
    min_confidence?: Confidence;
  } & AreaFields): HotspotsResponse {
    const start = this.checkDate(body.start, "start");
    const end = this.checkDate(body.end, "end");
    this.checkRange(start, end);
    const limit = body.limit ?? LIMITS.hotspots_default;
    if (limit > LIMITS.hotspots_max) fail(400, "LIMIT_TOO_HIGH", `limit: Input should be less than or equal to ${LIMITS.hotspots_max}`);
    const f = this.resolveArea(body);
    let pts = this.collectPoints(f, body.min_confidence ?? "nominal", this.dayIndex(start), this.dayIndex(end), body.bbox ?? null, body.event_id);
    if (body.min_frp) pts = pts.filter(([h]) => h.frp >= (body.min_frp ?? 0));
    const total = pts.length;
    if (total > limit) pts = [...pts].sort((a, b) => b[0].frp - a[0].frp).slice(0, limit);
    const features: HotspotFeature[] = pts.map(([h, ev]) => ({
      type: "Feature",
      id: h.id,
      geometry: { type: "Point", coordinates: [h.lon, h.lat] },
      properties: {
        time: h.time, sensor: h.sensor, confidence: h.confidence, frp: h.frp, daynight: h.daynight,
        weight: r3(h.weight), province_id: ev.provinceId, event_id: this.features.events ? ev.id : null,
      },
    }));
    return { type: "FeatureCollection", features, total, returned: features.length, truncated: total > limit };
  }

  exportCsv(query: ExportQuery): { filename: string; csv: string } {
    if (query.region_id && query.area_id) fail(400, "AREA_CONFLICT", "Please provide only one of region_id and area_id.");
    if (!query.start && !query.event_id) fail(400, "INVALID_REQUEST", "start is required (except with event_id).");
    const end = this.checkDate(query.end, "end");
    const start = query.start ? this.checkDate(query.start, "start") : this.world.firstDate;
    this.checkRange(start, end);
    const f = this.resolveArea({ region_id: query.region_id, area_id: query.area_id });
    const pts = this.collectPoints(f, query.min_confidence ?? "nominal", this.dayIndex(start), this.dayIndex(end), null, query.event_id)
      .sort((a, b) => (a[0].time < b[0].time ? -1 : a[0].time > b[0].time ? 1 : 0));
    const header = "id,time,lat,lon,sensor,confidence,confidence_raw,frp,daynight,weight,n_active,province_id,event_id\n";
    const rows = pts.map(([h, ev]) =>
      [h.id, h.time, h.lat, h.lon, h.sensor, h.confidence, h.confidenceRaw, h.frp, h.daynight, r3(h.weight), h.nActive, ev.provinceId, ev.id].join(","),
    );
    const name = query.region_id ?? query.area_id ?? query.event_id ?? "ES-PT";
    return { filename: `hotspots_${name}_${query.start ?? "start"}_${end}.csv`, csv: header + rows.join("\n") + "\n" };
  }

  // ---------------------------------------------------------------- 6.9 / 6.10

  /** Cells (resolution 8) of each point of an event-day, cached – events need them on every slider step. */
  private cells8(ed: MockEventDay): string[] {
    let cells = this.cellCache.get(ed.idx);
    if (!cells) {
      cells = this.points(ed).map((h) => latLngToCell(h.lat, h.lon, 8));
      if (this.cellCache.size > 40000) this.cellCache.clear();
      this.cellCache.set(ed.idx, cells);
    }
    return cells;
  }

  /**
   * State of an event from its points up to day D. It only changes on days with activity, so the cache key is
   * the number of active days up to D – moving the time slider by one day reuses almost everything.
   */
  private eventState(ev: MockEvent, day: number): EventState | null {
    const days = ev.days.map((i) => this.world.eventDays[i]).filter((ed) => ed.day <= day);
    const key = `${ev.idx}|${days.length}`;
    if (this.eventStateCache.has(key)) return this.eventStateCache.get(key) ?? null;
    let state: EventState | null = null;
    if (days.length > 0) {
      const seen = new Set<string>();
      const sensors = new Set<Sensor>();
      const perDay: EventState["perDay"] = [];
      let sx = 0;
      let sy = 0;
      let n = 0;
      let frpMax = 0;
      let high = 0;
      for (const ed of days) {
        const row = { day: ed.day, hotspots: 0, fires: 0, frp: 0, newCells: 0 };
        const edCells = this.cells8(ed);
        for (const [i, h] of this.points(ed).entries()) {
          const cell = edCells[i];
          if (!seen.has(cell)) {
            seen.add(cell);
            row.newCells++;
          }
          sensors.add(h.sensor);
          row.hotspots++;
          row.fires += h.weight;
          row.frp += h.frpH;
          frpMax = Math.max(frpMax, h.frp);
          if (h.confidence === "high") high++;
          sx += h.lon;
          sy += h.lat;
          n++;
        }
        perDay.push(row);
      }
      const cells = [...seen];
      const geometry = cellsToMultiPolygon(cells, true).map((poly) =>
        poly.map((ring) => ring.map(([x, y]) => [r4(x), r4(y)] as [number, number])),
      );
      const flat = geometry.flatMap((p) => p[0]);
      let b: BBox = [Infinity, Infinity, -Infinity, -Infinity];
      for (const [x, y] of flat) b = [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)];
      state = {
        startDay: days[0].day,
        lastDay: days[days.length - 1].day,
        perDay,
        cells,
        geometry: { type: "MultiPolygon", coordinates: geometry },
        centroid: [r4(sx / n), r4(sy / n)],
        bbox: b.map(r4) as BBox,
        sensors: [...sensors],
        frpMax,
        high,
        dayIndices: days.map((d) => d.idx),
      };
    }
    if (this.eventStateCache.size > 20000) this.eventStateCache.clear();
    this.eventStateCache.set(key, state);
    return state;
  }

  private toFeature(ev: MockEvent, st: EventState, day: number): EventFeature {
    const sum = (k: "hotspots" | "fires" | "frp", from = -Infinity, to = Infinity) =>
      st.perDay.filter((r) => r.day >= from && r.day <= to).reduce((s, r) => s + r[k], 0);
    const duration = st.lastDay - st.startDay + 1;
    const since = day - st.lastDay;
    const ended = since > 2;
    let trend: EventProperties["trend"] = null;
    if (duration >= 4 && !ended) {
      const recent = sum("fires", day - 2, day);
      const before = sum("fires", day - 5, day - 3);
      const ratio = before === 0 ? (recent > 0 ? Infinity : 1) : recent / before;
      trend = ratio > 1.25 ? "growing" : ratio < 0.8 ? "shrinking" : "stable";
    }
    return {
      type: "Feature",
      id: ev.id,
      geometry: st.geometry,
      properties: {
        start: this.dateOf(st.startDay),
        last_seen: this.dateOf(st.lastDay),
        duration_days: duration,
        days_since_last: since,
        active: since === 0,
        new: st.startDay === day,
        ended,
        hotspots: sum("hotspots"),
        fires: r1(sum("fires")),
        frp_sum: r1(sum("frp")),
        frp_max: r1(st.frpMax),
        area_km2: r1(st.cells.length * H3_R8_AREA_KM2),
        cells: st.cells.length,
        centroid: st.centroid,
        bbox: st.bbox,
        province_id: ev.provinceId,
        sensors: st.sensors,
        trend,
        landcover: null,
      },
    };
  }

  private inArea(ev: MockEvent, st: EventState, f: Filter): boolean {
    if (!MockApi.eventMatches(ev, f)) return false;
    return f.kind !== "geom" || st.dayIndices.some((i) => MockApi.dayMatches(this.world.eventDays[i], f));
  }

  events(body: AreaFields & {
    date?: string; lookback_days?: number; bbox?: BBox | null; sort?: EventSort; limit?: number; min_confidence?: Confidence;
  }): EventsResponse {
    if (!this.features.events) fail(501, "NOT_IMPLEMENTED", "Events are not available yet.");
    const date = this.checkDate(body.date, "date");
    this.checkRange(date, date);
    const lookback = body.lookback_days ?? 7;
    if (!Number.isInteger(lookback) || lookback < 1 || lookback > LIMITS.lookback_days_max) {
      fail(400, "INVALID_DATE_RANGE", `lookback_days: must be between 1 and ${LIMITS.lookback_days_max}.`);
    }
    const limit = body.limit ?? LIMITS.events_default;
    if (limit > LIMITS.events_max) fail(400, "LIMIT_TOO_HIGH", `limit: Input should be less than or equal to ${LIMITS.events_max}`);
    const f = this.resolveArea(body);
    const conf = body.min_confidence ?? "nominal";
    const day = this.dayIndex(date);

    const collect = (d: number, from: number) => {
      const out = new Map<number, { ev: MockEvent; st: EventState }>();
      for (const [, ev] of this.candidateDays(from, d, f, null)) {
        if (out.has(ev.idx)) continue;
        const st = this.eventState(ev, d);
        if (!st || !this.inArea(ev, st, f) || (conf === "high" && st.high === 0)) continue;
        out.set(ev.idx, { ev, st });
      }
      return [...out.values()];
    };
    const candidates = collect(day, day - lookback + 1);
    const previous = collect(day - 1, day - 1);
    const bbox = (body.bbox ?? null) as BBox | null;
    let features = candidates
      .map(({ ev, st }) => this.toFeature(ev, st, day))
      .filter((feat) => !bbox || bboxIntersects(feat.properties.bbox, bbox));
    const sort = body.sort ?? "frp_sum";
    features.sort((a, b) => {
      const va = a.properties[sort];
      const vb = b.properties[sort];
      return va < vb ? 1 : va > vb ? -1 : 0;
    });
    const total = features.length;
    features = features.slice(0, limit);
    return {
      type: "FeatureCollection",
      date,
      lookback_days: lookback,
      features,
      summary: {
        active: candidates.filter(({ st }) => st.lastDay === day).length,
        new: candidates.filter(({ st }) => st.startDay === day).length,
        active_previous_day: previous.filter(({ st }) => st.lastDay === day - 1).length,
      },
      total,
      returned: features.length,
      truncated: total > limit,
    };
  }

  eventDetail(id: string, date: string | null): EventDetailResponse {
    if (!this.features.events) fail(501, "NOT_IMPLEMENTED", "Events are not available yet.");
    const d = this.checkDate(date, "date");
    const ev = this.world.eventById.get(id);
    if (!ev) return fail(404, "EVENT_NOT_FOUND", `Event ${id} is unknown.`);
    const day = this.dayIndex(d);
    const st = this.eventState(ev, day);
    if (!st) return fail(404, "EVENT_NOT_FOUND", `Event ${id} starts after ${d}.`);
    const feature = this.toFeature(ev, st, day);
    const byDay = new Map(st.perDay.map((r) => [r.day, r]));
    const daily = [];
    for (let k = st.startDay; k <= st.lastDay; k++) {
      const r = byDay.get(k);
      daily.push({
        date: this.dateOf(k),
        hotspots: r?.hotspots ?? 0,
        fires: r1(r?.fires ?? 0),
        frp_sum: r1(r?.frp ?? 0),
        new_cells: r?.newCells ?? 0,
      });
    }
    return { ...feature, daily };
  }
}

interface EventState {
  startDay: number;
  lastDay: number;
  perDay: { day: number; hotspots: number; fires: number; frp: number; newCells: number }[];
  cells: string[];
  geometry: { type: "MultiPolygon"; coordinates: [number, number][][][] };
  centroid: [number, number];
  bbox: BBox;
  sensors: Sensor[];
  frpMax: number;
  high: number;
  dayIndices: number[];
}
