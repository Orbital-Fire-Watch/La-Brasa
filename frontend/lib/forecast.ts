/**
 * Forecast helpers (docs/forecast_backend_frontend.md): when the outlook box is shown and how its numbers read.
 * The forecast exists only per NUTS-2 region. The only derived number is the sum of the daily probabilities, which is
 * the expected number of days with a large fire (expectations add up, whatever the days have in common).
 */
import type { ForecastDay, RiskClass } from "../services/api/types";
import { daysBetween } from "./dates";

/** The box is shown only when the selected day lies at most this many days before the last data day. */
export const FORECAST_MAX_DAYS_BEFORE_LAST = 10;
/** Within ±10 % of the usual value the text says "about as usual". */
const SAME_BAND = 0.1;
/** From twice the usual value on, "2.5 times as high" reads better than "+150 %". */
const TIMES_FROM = 2;

export const RISK_ORDER: RiskClass[] = ["low", "normal", "elevated", "high", "very_high"];

/** Lead days of the three parts of the outlook. */
export const OUTLOOK_PARTS: ReadonlyArray<readonly [number, number]> = [[1, 3], [4, 7], [8, 10]];

export function forecastVisible(date: string, lastDate: string): boolean {
  return daysBetween(date, lastDate) <= FORECAST_MAX_DAYS_BEFORE_LAST;
}

export function worstClass(days: ForecastDay[]): RiskClass {
  return days.reduce<RiskClass>((w, d) => (RISK_ORDER.indexOf(d.risk_class) > RISK_ORDER.indexOf(w) ? d.risk_class : w), "low");
}

/** Comparison with the usual value for the season, as the text shows it. */
export type Change =
  | { kind: "lower"; percent: number }
  | { kind: "same" }
  | { kind: "higher"; percent: number }
  | { kind: "times"; factor: number };

/** ratio = forecast / usual. Percentages rounded to 5, so "94 %" becomes "95 %": no false precision. */
export function describeChange(ratio: number): Change {
  if (!Number.isFinite(ratio)) return { kind: "same" };
  if (Math.abs(ratio - 1) < SAME_BAND) return { kind: "same" };
  if (ratio < 1) return { kind: "lower", percent: Math.min(99, Math.max(5, Math.round(((1 - ratio) * 100) / 5) * 5)) };
  if (ratio < TIMES_FROM) return { kind: "higher", percent: Math.max(5, Math.round(((ratio - 1) * 100) / 5) * 5) };
  return { kind: "times", factor: ratio < 5 ? Math.round(ratio * 10) / 10 : Math.round(ratio) };
}

export interface OutlookPart {
  from: string;
  to: string;
  level: RiskClass;
  change: Change;
}

export interface Outlook {
  /** expected days with a large fire in the 10 days, and the usual number */
  expectedDays: number;
  usualDays: number;
  change: Change;
  parts: OutlookPart[];
}

const sum = (days: ForecastDay[], key: "p_big_fire_day" | "p_clim_big_fire_day") => days.reduce((s, d) => s + d[key], 0);

export function outlookOf(days: ForecastDay[]): Outlook | null {
  if (days.length === 0) return null;
  const expectedDays = sum(days, "p_big_fire_day");
  const usualDays = sum(days, "p_clim_big_fire_day");
  const parts = OUTLOOK_PARTS.map(([a, b]) => days.filter((d) => d.lead_days >= a && d.lead_days <= b))
    .filter((p) => p.length > 0)
    .map((p) => ({
      from: p[0].target_date, to: p[p.length - 1].target_date, level: worstClass(p),
      change: describeChange(sum(p, "p_big_fire_day") / sum(p, "p_clim_big_fire_day")),
    }));
  return { expectedDays, usualDays, change: describeChange(expectedDays / usualDays), parts };
}
