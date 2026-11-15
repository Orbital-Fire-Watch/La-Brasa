/**
 * Raw detections per day and sensor family (MODIS, VIIRS) over the whole period, for the year overview.
 *
 *   POST /api/daily/sensors   body SensorDailyRequest → 200 SensorDailyResponse (api_version 3.2)
 *
 * Same column layout as /api/daily: index i = day `start` + i. null = no satellite of this family was active that
 * day (e.g. VIIRS before 2012-01-20), 0 = satellites active, nothing detected. Counts are RAW detections (the
 * points of /api/hotspots, not harmonised) after the confidence filter; frp_sum in MW.
 *
 * Fallback (a backend without the endpoint: 404/405/501): sum up single points from /api/hotspots,
 * one request per year, split into months when a year is truncated; months that are still truncated are reported
 * in `incomplete`.
 */
import { addDays, daysBetween, daysInMonth, isoFromParts, yearOf } from "../../lib/dates";
import { familyOf, type SensorFamily } from "../../lib/sensors";
import { apiPost } from "./client";
import { ApiError } from "./errors";
import type { FamilyColumns, HotspotsRequest, HotspotsResponse, MetaResponse, SensorDailyRequest, SensorDailyResponse } from "./types";

/** The endpoint's answer, plus what only the fallback can fill. */
export type SensorDaily = SensorDailyResponse & {
  /** Only filled by the fallback: periods whose counts are lower bounds because of the API limit. */
  incomplete?: { start: string; end: string }[];
};

export interface SensorDailyResult {
  data: SensorDaily;
  source: "endpoint" | "hotspots";
  /** number of /api/hotspots requests of the fallback */
  requests: number;
}

export interface Progress {
  done: number;
  total: number;
}

const CONCURRENCY = 6;

type HotspotsFetcher = (body: HotspotsRequest, signal: AbortSignal) => Promise<HotspotsResponse>;

/** Fallback: one /api/hotspots request per year, split into months when truncated. */
async function viaHotspots(
  req: SensorDailyRequest & { start: string; end: string }, meta: Pick<MetaResponse, "sensors" | "limits">,
  fetchHotspots: HotspotsFetcher, signal: AbortSignal, onProgress: (p: Progress) => void,
): Promise<SensorDailyResult> {
  const { start, end, min_confidence, ...selector } = req;
  const n = daysBetween(start, end) + 1;
  const det: Record<SensorFamily, number[]> = { modis: new Array(n).fill(0), viirs: new Array(n).fill(0) };
  const frp: Record<SensorFamily, number[]> = { modis: new Array(n).fill(0), viirs: new Array(n).fill(0) };
  const incomplete: { start: string; end: string }[] = [];

  const queue: { start: string; end: string; split: boolean }[] = [];
  for (let y = yearOf(start); y <= yearOf(end); y++) {
    queue.push({ start: y === yearOf(start) ? start : `${y}-01-01`, end: y === yearOf(end) ? end : `${y}-12-31`, split: true });
  }
  const progress = { done: 0, total: queue.length };
  onProgress({ ...progress });

  const worker = async () => {
    for (let w = queue.shift(); w; w = queue.shift()) {
      const res = await fetchHotspots({ ...selector, start: w.start, end: w.end, limit: meta.limits.hotspots_max, min_confidence, raw: true }, signal);
      if (res.truncated && w.split) {
        const y = yearOf(w.start);
        const months: typeof queue = [];
        for (let m = 1; m <= 12; m++) {
          const ms = isoFromParts(y, m, 1);
          const me = isoFromParts(y, m, daysInMonth(y, m));
          if (me < w.start || ms > w.end) continue;
          months.push({ start: ms < w.start ? w.start : ms, end: me > w.end ? w.end : me, split: false });
        }
        queue.push(...months);
        progress.total += months.length;
      } else {
        if (res.truncated) incomplete.push({ start: w.start, end: w.end });
        for (const h of res.features) {
          const i = daysBetween(start, h.properties.time.slice(0, 10));
          if (i < 0 || i >= n) continue;
          const fam = familyOf(h.properties.sensor);
          det[fam][i] += 1;
          frp[fam][i] += h.properties.frp ?? 0;
        }
      }
      progress.done += 1;
      onProgress({ ...progress });
    }
  };
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));

  // Days without any active satellite of a family are null, not 0 (meta.sensors has the operating periods).
  const families = {} as Record<SensorFamily, FamilyColumns>;
  for (const fam of ["modis", "viirs"] as const) {
    const periods = meta.sensors.filter((s) => familyOf(s.id) === fam);
    const active = (day: string) => periods.some((s) => s.from <= day && (s.to === null || s.to >= day));
    families[fam] = {
      detections: det[fam].map((v, i) => (active(addDays(start, i)) ? v : null)),
      frp_sum: frp[fam].map((v, i) => (active(addDays(start, i)) ? v : null)),
    };
  }
  return { data: { start, end, families, incomplete }, source: "hotspots", requests: progress.done };
}

export async function loadSensorDaily(
  req: SensorDailyRequest & { start: string; end: string }, meta: Pick<MetaResponse, "sensors" | "limits">,
  fetchHotspots: HotspotsFetcher, signal: AbortSignal, onProgress: (p: Progress) => void,
): Promise<SensorDailyResult> {
  try {
    const data = await apiPost("/api/daily/sensors", req, signal);
    return { data, source: "endpoint", requests: 1 };
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501))) throw e;
  }
  return viaHotspots(req, meta, fetchHotspots, signal, onProgress);
}
