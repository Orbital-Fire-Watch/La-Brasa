/** Date helpers. All dates are UTC days as "YYYY-MM-DD" strings (spec §2). */

export const DAY_MS = 86_400_000;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const toMs = (date: string): number => Date.parse(`${date}T00:00:00Z`);
export const toIso = (ms: number): string => new Date(ms).toISOString().slice(0, 10);
export const addDays = (date: string, days: number): string => toIso(toMs(date) + days * DAY_MS);

/** Whole days from `a` to `b` (positive when b is later). */
export const daysBetween = (a: string, b: string): number => Math.round((toMs(b) - toMs(a)) / DAY_MS);

export const yearOf = (date: string): number => Number(date.slice(0, 4));
export const monthOf = (date: string): number => Number(date.slice(5, 7));

export function isIsoDate(value: string | null | undefined): value is string {
  return !!value && ISO_DATE.test(value) && !Number.isNaN(toMs(value)) && toIso(toMs(value)) === value;
}

export function clampDate(date: string, min: string, max: string): string {
  if (date < min) return min;
  if (date > max) return max;
  return date;
}

export const isLeapYear = (y: number): boolean => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
export const daysInMonth = (y: number, m: number): number => new Date(Date.UTC(y, m, 0)).getUTCDate();

export const pad2 = (n: number): string => String(n).padStart(2, "0");
export const isoFromParts = (y: number, m: number, d: number): string => `${y}-${pad2(m)}-${pad2(d)}`;

/** Shifts a date by whole years; Feb 29 becomes Feb 28 in non-leap years (spec §7.2). */
export function shiftYears(date: string, years: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return isoFromParts(y + years, m, Math.min(d, daysInMonth(y + years, m)));
}

/** Day of year 1..365; in leap years shifted by one from March so calendar days line up (spec §7.3). */
export function dayOfYear(date: string): number {
  const [y, m, d] = date.split("-").map(Number);
  const n = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(y, 0, 1)) / DAY_MS) + 1;
  return isLeapYear(y) && m > 2 ? n - 1 : n;
}

/** Date for a 1..365 day of year (inverse of dayOfYear; never returns Feb 29). */
export function dateFromDayOfYear(year: number, doy: number): string {
  const offset = isLeapYear(year) && doy >= 60 ? doy : doy - 1;
  return toIso(Date.UTC(year, 0, 1) + offset * DAY_MS);
}
