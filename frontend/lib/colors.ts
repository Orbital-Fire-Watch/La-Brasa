/** Colour scales (colour-blind-safe, see spec §7.7). Every map and chart also has a legend. */
import { interpolateRdBu, interpolateYlOrRd } from "d3-scale-chromatic";

/**
 * Sequential log-like scale – extreme months must not flatten everything else (spec §7.7).
 * The symlog constant at 1 % of the maximum spreads the colours over two orders of magnitude.
 */
export function sequentialScale(max: number): (v: number) => string {
  const m = Math.max(max, 1e-6);
  const c = m / 100;
  return (v: number) => interpolateYlOrRd(0.08 + 0.92 * Math.min(1, Math.log1p(Math.max(0, v) / c) / Math.log1p(m / c)));
}

/** Diverging scale with 0 in the middle (blue = less than usual, red = more). */
export function divergingScale(maxAbs: number): (v: number) => string {
  const m = Math.max(maxAbs, 1e-6);
  const c = m / 50;
  return (v: number) => {
    const t = Math.min(1, Math.log1p(Math.abs(v) / c) / Math.log1p(m / c));
    return interpolateRdBu(0.5 - 0.5 * Math.sign(v) * t);
  };
}

export type AgeClass = "today" | "recent" | "older" | "ended";

/** Age relative to the reference day D (spec §7.7). */
export function ageClass(daysSinceLast: number): AgeClass {
  if (daysSinceLast <= 0) return "today";
  if (daysSinceLast <= 2) return "recent";
  return "older";
}

export const AGE_COLOR: Record<AgeClass, string> = {
  today: "#b2182b",
  recent: "#ef6c2f",
  older: "#f4b56a",
  ended: "#9e9e9e",
};

export const AGE_LABEL: Record<AgeClass, string> = {
  today: "heute aktiv",
  recent: "letzte 2 Tage",
  older: "älter",
  ended: "erloschen",
};

/** Okabe–Ito palette for comparison lines. */
export const COMPARE_COLORS = ["#0072B2", "#009E73", "#CC79A7", "#56B4E9", "#E69F00", "#000000", "#F0E442"];

export const SELECTED_LINE_COLOR = "#d9480f";
