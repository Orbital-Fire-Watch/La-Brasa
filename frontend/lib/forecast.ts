/**
 * Forecast helpers (docs/forecast_backend_frontend.md): when the warning box is shown and for which regions.
 * The forecast exists only per NUTS-2 region; nothing here computes a probability.
 */
import type { ForecastDay, RegionFeature, RiskClass } from "../services/api/types";
import { bboxOf, pointInGeometry, type AreaGeometry, type Position } from "./geo";
import { daysBetween } from "./dates";
import { regionAt } from "./regions";

/** The box is shown only when the selected day lies at most this many days before the last data day. */
export const FORECAST_MAX_DAYS_BEFORE_LAST = 10;
/** From this lead on the day is drawn paler: it rests mostly on the weather forecast. */
export const FORECAST_PALE_FROM_LEAD = 7;
const AREA_SAMPLES_PER_SIDE = 24;

export const RISK_ORDER: RiskClass[] = ["low", "normal", "elevated", "high", "very_high"];

export function forecastVisible(date: string, lastDate: string): boolean {
  return daysBetween(date, lastDate) <= FORECAST_MAX_DAYS_BEFORE_LAST;
}

export function worstClass(days: ForecastDay[]): RiskClass {
  return days.reduce<RiskClass>((w, d) => (RISK_ORDER.indexOf(d.risk_class) > RISK_ORDER.indexOf(w) ? d.risk_class : w), "low");
}

/** First day with at least `elevated`, or null. */
export function firstElevated(days: ForecastDay[]): ForecastDay | null {
  return days.find((d) => RISK_ORDER.indexOf(d.risk_class) >= RISK_ORDER.indexOf("elevated")) ?? null;
}

export type ForecastScope =
  | { kind: "region"; ids: string[] }
  | { kind: "province"; ids: string[] }
  | { kind: "country"; ids: string[] }
  | { kind: "area"; ids: string[] }
  | { kind: "all"; ids: string[] };

/** NUTS-2 regions of the selection: the region itself, the region of a province, all regions of a country, or the
 * regions a drawn area touches (sampled on a grid inside the area). */
export function forecastScope(
  selected: RegionFeature | null, area: AreaGeometry | null, regions: RegionFeature[],
): ForecastScope {
  const level2 = regions.filter((r) => r.properties.level === "region");
  if (area) {
    const [w, s, e, n] = bboxOf(area);
    const ids = new Set<string>();
    for (let i = 0; i <= AREA_SAMPLES_PER_SIDE; i++) {
      for (let j = 0; j <= AREA_SAMPLES_PER_SIDE; j++) {
        const p: Position = [w + ((e - w) * i) / AREA_SAMPLES_PER_SIDE, s + ((n - s) * j) / AREA_SAMPLES_PER_SIDE];
        if (!pointInGeometry(p, area)) continue;
        const r = regionAt(p, level2);
        if (r) ids.add(r.properties.id);
      }
    }
    return { kind: "area", ids: [...ids].sort() };
  }
  if (!selected) return { kind: "all", ids: level2.map((r) => r.properties.id) };
  const p = selected.properties;
  if (p.level === "region") return { kind: "region", ids: [p.id] };
  if (p.level === "province") return { kind: "province", ids: p.parent ? [p.parent] : [] };
  return { kind: "country", ids: level2.filter((r) => r.properties.country === p.id).map((r) => r.properties.id) };
}
