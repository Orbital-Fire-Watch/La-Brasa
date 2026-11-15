/**
 * Cloud cover of the /api/daily response: share of the sky covered at the VIIRS day and night pass, 0–1.
 * FIRMS only lists detections, so under clouds a fire is missing and the day looks quiet. A day counts as
 * cloudy when both passes are covered at least `threshold` (lib/uiConfig.ts CLOUDY_THRESHOLD).
 */
import { addDays, daysBetween } from "./dates";

/** Structural subset of DailyResponse. */
export interface CloudSeries {
  start: string;
  cloud_day?: (number | null)[] | null;
  cloud_night?: (number | null)[] | null;
}

export interface DayCloud {
  day: number | null;
  night: number | null;
}

/** Cloud cover on `date`; null without cloud data for that day. */
export function cloudAt(series: CloudSeries, date: string): DayCloud | null {
  const i = daysBetween(series.start, date);
  const day = series.cloud_day?.[i] ?? null;
  const night = series.cloud_night?.[i] ?? null;
  return day === null && night === null ? null : { day, night };
}

export const isCloudy = (c: DayCloud | null, threshold: number): boolean =>
  c !== null && c.day !== null && c.night !== null && c.day >= threshold && c.night >= threshold;

/**
 * Cloudy day without fires between two days with fires: the fire probably burned on, hidden under the clouds.
 * In the data (2012–2026) such a day stays empty 3 times as often as a clear one (docs/cloud_cover_plan.md).
 */
export function probablyHidden(series: CloudSeries & { fires: (number | null)[] }, date: string, threshold: number): boolean {
  const i = daysBetween(series.start, date);
  const fires = (k: number) => series.fires[k] ?? null;
  return isCloudy(cloudAt(series, date), threshold) && fires(i) === 0 && (fires(i - 1) ?? 0) > 0 && (fires(i + 1) ?? 0) > 0;
}

export interface DayCloudInfo extends DayCloud {
  /** the lower of the two passes: both were covered at least this much (null if one is missing) */
  cover: number | null;
  cloudy: boolean;
  hidden: boolean;
}

/** Cloud cover of every day from start to end (null = no cloud data), for the strip under the time slider. */
export function cloudDays(series: CloudSeries & { fires: (number | null)[] }, start: string, end: string, threshold: number): (DayCloudInfo | null)[] {
  return Array.from({ length: daysBetween(start, end) + 1 }, (_, k) => {
    const date = addDays(start, k);
    const c = cloudAt(series, date);
    if (!c) return null;
    const cover = c.day !== null && c.night !== null ? Math.min(c.day, c.night) : null;
    return { ...c, cover, cloudy: isCloudy(c, threshold), hidden: probablyHidden(series, date, threshold) };
  });
}
