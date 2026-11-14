/** Number and label formatting for the German UI. */

const nf = (digits: number) =>
  new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const NF0 = nf(0);
const NF1 = nf(1);

export const formatInt = (v: number): string => NF0.format(Math.round(v));
export const formatOne = (v: number): string => NF1.format(v);

/** Compact: 1234567 → "1,2 Mio.", 12345 → "12.345" */
export function formatCompact(v: number): string {
  if (Math.abs(v) >= 1e6) return `${NF1.format(v / 1e6)} Mio.`;
  if (Math.abs(v) >= 100) return NF0.format(v);
  return NF1.format(v);
}

export const formatSigned = (v: number): string => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${formatCompact(Math.abs(v))}`;

export const formatKm2 = (v: number): string => `${v < 10 ? NF1.format(v) : NF0.format(v)} km²`;

export const formatCoord = (v: number): string => v.toFixed(4);

export function plural(n: number, one: string, many: string): string {
  return `${formatInt(n)} ${n === 1 ? one : many}`;
}

/** "heute", "gestern", "vor 3 Tagen" relative to the reference day D */
export function relativeDays(days: number): string {
  if (days === 0) return "heute";
  if (days === 1) return "gestern";
  if (days === -1) return "morgen";
  return days > 0 ? `vor ${days} Tagen` : `in ${-days} Tagen`;
}
