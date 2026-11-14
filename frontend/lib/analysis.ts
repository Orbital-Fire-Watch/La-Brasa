/**
 * Frontend calculations from spec §7, all based on the column-oriented /api/daily response.
 * Pure functions without UI so they can be tested on their own.
 */
import { median, quantile } from "d3-array";
import { addDays, daysBetween, dayOfYear, isLeapYear, shiftYears, toIso, toMs, DAY_MS, yearOf } from "./dates";

/** Columns of /api/daily that can be analysed. */
export type SeriesKey = "fires" | "hotspots" | "frp_sum" | "events_new" | "events_active";

/** Structural subset of DailyResponse – keeps lib/ independent of the API layer. */
export interface DailySeries {
  start: string;
  end: string;
  fires: (number | null)[];
  hotspots: (number | null)[];
  frp_sum: (number | null)[];
  events_active?: (number | null)[] | null;
  events_new?: (number | null)[] | null;
}

export type Values = (number | null)[];

export function seriesValues(daily: DailySeries, key: SeriesKey): Values | null {
  return daily[key] ?? null;
}

export const indexOfDate = (daily: Pick<DailySeries, "start">, date: string): number => daysBetween(daily.start, date);

export function valueAt(daily: DailySeries, key: SeriesKey, date: string): number | null {
  const values = seriesValues(daily, key);
  const i = indexOfDate(daily, date);
  return values && i >= 0 && i < values.length ? values[i] : null;
}

/** Sum over [start, end]; null if a day is missing or outside the series (spec §7.2). */
export function windowSum(values: Values, seriesStart: string, start: string, end: string): number | null {
  const i0 = daysBetween(seriesStart, start);
  const i1 = daysBetween(seriesStart, end);
  if (i0 < 0 || i1 >= values.length || i1 < i0) return null;
  let s = 0;
  for (let i = i0; i <= i1; i++) {
    const v = values[i];
    if (v === null) return null;
    s += v;
  }
  return s;
}

export type Compare = "all" | number;

export interface WindowAnomaly {
  value: number | null;
  years_compared: number;
  median: number | null;
  p25: number | undefined;
  p75: number | undefined;
  p90: number | undefined;
  diff: number | null;
  factor: number | null;
  rank: number | null;
  rank_of: number;
  history: { year: number; value: number }[];
}

/** Anomaly of an arbitrary window against the same window in other years (spec §7.2). */
export function windowAnomaly(
  daily: DailySeries,
  key: SeriesKey,
  start: string,
  end: string,
  compare: Compare = "all",
): WindowAnomaly | null {
  const values = seriesValues(daily, key);
  if (!values) return null;
  const value = windowSum(values, daily.start, start, end);
  const y0 = yearOf(start);
  let history: { year: number; value: number }[] = [];
  for (let y = yearOf(daily.start); y <= yearOf(daily.end); y++) {
    if (y === y0) continue;
    const v = windowSum(values, daily.start, shiftYears(start, y - y0), shiftYears(end, y - y0));
    if (v !== null) history.push({ year: y, value: v });
  }
  if (compare !== "all") history = history.filter((h) => h.year < y0).slice(-compare);

  const vs = history.map((h) => h.value);
  const med = vs.length ? (median(vs) ?? null) : null;
  return {
    value,
    years_compared: vs.length,
    median: med,
    p25: quantile(vs, 0.25),
    p75: quantile(vs, 0.75),
    p90: quantile(vs, 0.9),
    diff: value !== null && med !== null ? value - med : null,
    factor: med !== null && med > 0 && value !== null ? Math.round((value / med) * 10) / 10 : null,
    rank: value === null ? null : 1 + vs.filter((v) => v > value).length,
    rank_of: vs.length + 1,
    history,
  };
}

/** Circular moving average over a 365-day curve. */
function smoothCircular(curve: number[], halfWindow: number): number[] {
  const n = curve.length;
  return curve.map((_, i) => {
    let s = 0;
    for (let k = -halfWindow; k <= halfWindow; k++) s += curve[(i + k + n) % n];
    return s / (2 * halfWindow + 1);
  });
}

export interface Climatology {
  /** 365 values each: median, p25 and p75 per calendar day, smoothed over 15 days (spec §7.3 steps 1–2). */
  median: number[];
  p25: number[];
  p75: number[];
}

export function climatology(daily: DailySeries, key: SeriesKey, fromYear?: number): Climatology | null {
  const values = seriesValues(daily, key);
  if (!values) return null;
  const byDoy: number[][] = Array.from({ length: 365 }, () => []);
  const t0 = toMs(daily.start);
  values.forEach((v, i) => {
    if (v === null) return;
    const ds = toIso(t0 + i * DAY_MS);
    if (ds.slice(5) === "02-29" || (fromYear !== undefined && yearOf(ds) < fromYear)) return;
    byDoy[dayOfYear(ds) - 1].push(v);
  });
  const q = (p: number) => byDoy.map((vs) => (vs.length ? (quantile(vs, p) ?? 0) : 0));
  return { median: smoothCircular(q(0.5), 7), p25: smoothCircular(q(0.25), 7), p75: smoothCircular(q(0.75), 7) };
}

export type SeasonPhaseName = "pre_season" | "rising" | "peak" | "declining" | "post_season" | "no_season";

export interface SeasonPhase {
  phase: SeasonPhaseName;
  peakDoy: number;
  startDoy: number;
  endDoy: number;
  /** positive = days until the peak, negative = days since the peak */
  daysToPeak: number;
  /** second maximum with at least 50 % of the main peak (e.g. spring fires in the north) */
  secondaryPeakDoy: number | null;
}

const MIN_PEAK_DISTANCE_DAYS = 30;

/** Season phase on day D from the smoothed climatology (spec §7.3). */
export function seasonPhase(curve: number[], date: string): SeasonPhase {
  const total = curve.reduce((a, b) => a + b, 0);
  if (total === 0) return { phase: "no_season", peakDoy: 0, startDoy: 0, endDoy: 0, daysToPeak: 0, secondaryPeakDoy: null };
  const max = Math.max(...curve);
  const peakDoy = curve.indexOf(max) + 1;
  let cum = 0;
  let startDoy = 0;
  let endDoy = 0;
  curve.forEach((v, i) => {
    cum += v;
    if (!startDoy && cum >= 0.1 * total) startDoy = i + 1;
    if (!endDoy && cum >= 0.9 * total) endDoy = i + 1;
  });
  const d = dayOfYear(date);
  const phase: SeasonPhaseName =
    d < startDoy ? "pre_season"
    : Math.abs(d - peakDoy) <= 7 ? "peak"
    : d < peakDoy ? "rising"
    : d <= endDoy ? "declining"
    : "post_season";

  let secondaryPeakDoy: number | null = null;
  let best = 0;
  const n = curve.length;
  for (let i = 0; i < n; i++) {
    const v = curve[i];
    const isLocalMax = v >= curve[(i - 1 + n) % n] && v > curve[(i + 1) % n];
    const dist = Math.min(Math.abs(i + 1 - peakDoy), n - Math.abs(i + 1 - peakDoy));
    if (isLocalMax && dist >= MIN_PEAK_DISTANCE_DAYS && v >= 0.5 * max && v > best) {
      best = v;
      secondaryPeakDoy = i + 1;
    }
  }
  return { phase, peakDoy, startDoy, endDoy, daysToPeak: peakDoy - d, secondaryPeakDoy };
}

/** 365 values of one year (Feb 29 dropped), null outside the series or on days without data. */
export function yearSeries(daily: DailySeries, key: SeriesKey, year: number): Values {
  const values = seriesValues(daily, key);
  const out: Values = new Array(365).fill(null);
  if (!values) return out;
  const leap = isLeapYear(year);
  const jan1 = `${year}-01-01`;
  const base = indexOfDate(daily, jan1);
  for (let doy = 1; doy <= 365; doy++) {
    const offset = leap && doy >= 60 ? doy : doy - 1;
    const i = base + offset;
    if (i >= 0 && i < values.length) out[doy - 1] = values[i];
  }
  return out;
}

/** Centered moving average; days that are null themselves stay null (drawn as gaps, spec §7.4). */
export function movingAverage(values: Values, window = 7): Values {
  const half = Math.floor(window / 2);
  return values.map((v, i) => {
    if (v === null) return null;
    let s = 0;
    let n = 0;
    for (let k = i - half; k <= i + half; k++) {
      const w = values[k];
      if (w !== null && w !== undefined) {
        s += w;
        n++;
      }
    }
    return n ? s / n : null;
  });
}

/** Totals of complete years (every day inside the series), for "strongest / weakest year". */
export function yearTotals(daily: DailySeries, key: SeriesKey, fromYear?: number): { year: number; total: number }[] {
  const values = seriesValues(daily, key);
  if (!values) return [];
  const out: { year: number; total: number }[] = [];
  for (let y = yearOf(daily.start); y <= yearOf(daily.end); y++) {
    if (fromYear !== undefined && y < fromYear) continue;
    const i0 = indexOfDate(daily, `${y}-01-01`);
    const i1 = indexOfDate(daily, `${y}-12-31`);
    if (i0 < 0 || i1 >= values.length) continue;
    let total = 0;
    for (let i = i0; i <= i1; i++) total += values[i] ?? 0;
    out.push({ year: y, total });
  }
  return out;
}

export type PeriodMode = "month" | "week";
export type CellStatus = "complete" | "incomplete" | "running" | "nodata";

export interface PeriodCell {
  year: number;
  /** month 0..11 or week 0..51 */
  col: number;
  start: string;
  end: string;
  value: number | null;
  status: CellStatus;
}

export const periodColumns = (mode: PeriodMode): number => (mode === "month" ? 12 : 52);

/** Start and end of a heatmap column. Weeks are days 1–7, 8–14, … of the year; week 52 runs to Dec 31 (spec §7.5). */
export function periodRange(year: number, col: number, mode: PeriodMode): [string, string] {
  if (mode === "month") {
    const start = `${year}-${String(col + 1).padStart(2, "0")}-01`;
    return [start, addDays(col === 11 ? `${year + 1}-01-01` : `${year}-${String(col + 2).padStart(2, "0")}-01`, -1)];
  }
  const start = addDays(`${year}-01-01`, col * 7);
  return [start, col === 51 ? `${year}-12-31` : addDays(start, 6)];
}

/** Sums per year × month/week for the year heatmap and the ring calendar. */
export function periodCells(daily: DailySeries, key: SeriesKey, mode: PeriodMode): PeriodCell[] {
  const values = seriesValues(daily, key);
  const out: PeriodCell[] = [];
  if (!values) return out;
  for (let y = yearOf(daily.start); y <= yearOf(daily.end); y++) {
    for (let col = 0; col < periodColumns(mode); col++) {
      const [start, end] = periodRange(y, col, mode);
      if (end < daily.start || start > daily.end) {
        out.push({ year: y, col, start, end, value: null, status: "nodata" });
        continue;
      }
      const i0 = Math.max(0, indexOfDate(daily, start));
      const i1 = Math.min(values.length - 1, indexOfDate(daily, end));
      let sum = 0;
      let missing = start < daily.start;
      for (let i = i0; i <= i1; i++) {
        const v = values[i];
        if (v === null) missing = true;
        else sum += v;
      }
      const status: CellStatus = end > daily.end ? "running" : missing ? "incomplete" : "complete";
      out.push({ year: y, col, start, end, value: sum, status });
    }
  }
  return out;
}
