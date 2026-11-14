/** Year-to-date totals for the EFFIS-style header blocks, from the column-oriented /api/daily response. */
import { seriesValues, type DailySeries, type SeriesKey } from "./analysis";
import { daysBetween, shiftYears, yearOf } from "./dates";

export interface YearValue {
  year: number;
  value: number;
  /** same calendar day as the reference date, in that year */
  date: string;
}

export interface YtdStat {
  value: number | null;
  lastYear: YearValue | null;
  /** highest of all earlier years by the same calendar day */
  record: YearValue | null;
}

export function ytdStat(daily: DailySeries, key: SeriesKey, date: string): YtdStat {
  const values = seriesValues(daily, key);
  const y0 = yearOf(date);
  if (!values) return { value: null, lastYear: null, record: null };
  const sumFor = (y: number): YearValue | null => {
    const end = shiftYears(date, y - y0);
    const start = `${y}-01-01`;
    if (start < daily.start) return null;
    // Cumulative like EFFIS: days without data count as 0; a year without any data has no value.
    const i0 = daysBetween(daily.start, start);
    const i1 = Math.min(daysBetween(daily.start, end), values.length - 1);
    let sum = 0;
    let seen = 0;
    for (let i = i0; i <= i1; i++) {
      const v = values[i];
      if (v !== null) {
        sum += v;
        seen++;
      }
    }
    return seen === 0 ? null : { year: y, value: sum, date: end };
  };
  const earlier: YearValue[] = [];
  for (let y = yearOf(daily.start); y < y0; y++) {
    const v = sumFor(y);
    if (v) earlier.push(v);
  }
  return {
    value: sumFor(y0)?.value ?? null,
    lastYear: earlier.find((e) => e.year === y0 - 1) ?? null,
    record: earlier.reduce<YearValue | null>((best, e) => (!best || e.value > best.value ? e : best), null),
  };
}
