/** Data colours per palette: the app's standard scales, or colour-blind-safe Cividis/Viridis from the accessibility menu. */
import { interpolateCividis } from "d3-scale-chromatic";
import { AGE_COLOR, sequentialScale, type AgeClass } from "./colors";
import type { Palette } from "../hooks/usePrefs";

/** Same log-like spread as the app's sequentialScale, so both palettes show the same structure. */
function cividisScale(max: number): (v: number) => string {
  const m = Math.max(max, 1e-6);
  const c = m / 100;
  return (v: number) => interpolateCividis(0.12 + 0.88 * Math.min(1, Math.log1p(Math.max(0, v) / c) / Math.log1p(m / c)));
}

export function valueScale(palette: Palette, max: number): (v: number) => string {
  return palette === "cvd" ? cividisScale(max) : sequentialScale(max);
}

/** Viridis steps: dark → light means new → old, readable without hue. */
const AGE_CVD: Record<AgeClass, string> = {
  today: "#440154",
  recent: "#31688e",
  older: "#5ec962",
  ended: "#9e9e9e",
};

export function ageColors(palette: Palette): Record<AgeClass, string> {
  return palette === "cvd" ? AGE_CVD : AGE_COLOR;
}
