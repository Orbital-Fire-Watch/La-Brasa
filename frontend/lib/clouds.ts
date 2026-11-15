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
 * A fire last seen the day before, seen again the day after, and cloudy at its location in between: it probably
 * burned on, hidden under the clouds. In the data (2012–2026) a day between two fire days stays empty about
 * 3 times as often under clouds as under a clear sky (docs/cloud_cover_plan.md).
 */
export const probablyHiddenFire = (u: { days_since_last: number; cloud: DayCloud | null; seenNextDay: boolean | null }, threshold: number): boolean =>
  u.days_since_last === 1 && u.seenNextDay === true && isCloudy(u.cloud, threshold);

export interface DayCloudInfo extends DayCloud {
  /** the lower of the two passes: both were covered at least this much (null if one is missing) */
  cover: number | null;
  cloudy: boolean;
  /** at least one fire in the selection was probably hidden under clouds that day (dashed on the map) */
  hiddenFire: boolean;
}

/**
 * Cloud cover of every day from start to end (null = no cloud data), for the strip under the time slider.
 * `hiddenCover`: POST /api/events/hidden, per day the cloud cover at the most covered fire seen the day before and after.
 */
export function cloudDays(series: CloudSeries, start: string, end: string, threshold: number, hiddenCover?: (number | null)[] | null): (DayCloudInfo | null)[] {
  return Array.from({ length: daysBetween(start, end) + 1 }, (_, k) => {
    const date = addDays(start, k);
    const c = cloudAt(series, date);
    if (!c) return null;
    const cover = c.day !== null && c.night !== null ? Math.min(c.day, c.night) : null;
    return { ...c, cover, cloudy: isCloudy(c, threshold), hiddenFire: (hiddenCover?.[k] ?? -1) >= threshold };
  });
}
