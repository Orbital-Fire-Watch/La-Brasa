/**
 * Raw MODIS and VIIRS data from /api/hotspots, summed up in the browser (the API has no sensor filter yet).
 * MODIS = Terra + Aqua (about 1 km pixels), VIIRS = Suomi NPP + NOAA-20 + NOAA-21 (about 375 m pixels).
 */
import { latLngToCell } from "h3-js";
import { addDays, daysBetween } from "../../lib/dates";
import type { HotspotFeature, MetaResponse, Sensor } from "../../services/api/types";

export type SensorFamily = "modis" | "viirs";
export const FAMILIES: readonly SensorFamily[] = ["modis", "viirs"];

export const familyOf = (s: Sensor): SensorFamily => (s.startsWith("MODIS") ? "modis" : "viirs");

/** Okabe–Ito orange and sky blue: distinguishable with colour-vision deficiencies; always shown with a label. */
export const FAMILY_COLOR: Record<SensorFamily, string> = { modis: "#E69F00", viirs: "#56B4E9" };
export const FAMILY_NAME: Record<SensorFamily, string> = { modis: "MODIS", viirs: "VIIRS" };
export const PIXEL_SIZE: Record<SensorFamily, string> = { modis: "1 km", viirs: "375 m" };

export const SENSOR_NAME: Record<Sensor, string> = {
  MODIS_TERRA: "Terra",
  MODIS_AQUA: "Aqua",
  VIIRS_SNPP: "Suomi NPP",
  VIIRS_NOAA20: "NOAA-20",
  VIIRS_NOAA21: "NOAA-21",
};

export interface FamilyStats {
  detections: number;
  frpSum: number;
  /** mean FRP per detection with an FRP value, null without any */
  meanFrp: number | null;
  /** days in the window with at least one detection */
  activeDays: number;
  bySensor: Partial<Record<Sensor, number>>;
  /** satellites of this family that delivered data at some point in the window (from /api/meta) */
  satellites: Sensor[];
}

export interface SensorComparison {
  start: string;
  end: string;
  stats: Record<SensorFamily, FamilyStats>;
  /** one entry per day from start to end */
  daily: { date: string; modis: number; viirs: number }[];
  returned: number;
  total: number;
  truncated: boolean;
}

function emptyStats(): FamilyStats {
  return { detections: 0, frpSum: 0, meanFrp: null, activeDays: 0, bySensor: {}, satellites: [] };
}

export function compareSensors(
  features: HotspotFeature[], start: string, end: string, meta: Pick<MetaResponse, "sensors">,
  counts: { returned: number; total: number; truncated: boolean },
): SensorComparison {
  const stats: Record<SensorFamily, FamilyStats> = { modis: emptyStats(), viirs: emptyStats() };
  const n = Math.max(0, daysBetween(start, end) + 1);
  const daily = Array.from({ length: n }, (_, i) => ({ date: addDays(start, i), modis: 0, viirs: 0 }));
  const frpCount: Record<SensorFamily, number> = { modis: 0, viirs: 0 };

  for (const h of features) {
    const fam = familyOf(h.properties.sensor);
    const s = stats[fam];
    s.detections += 1;
    s.bySensor[h.properties.sensor] = (s.bySensor[h.properties.sensor] ?? 0) + 1;
    if (h.properties.frp != null) {
      s.frpSum += h.properties.frp;
      frpCount[fam] += 1;
    }
    const i = daysBetween(start, h.properties.time.slice(0, 10));
    if (i >= 0 && i < n) daily[i][fam] += 1;
  }
  for (const fam of FAMILIES) {
    const s = stats[fam];
    s.meanFrp = frpCount[fam] > 0 ? s.frpSum / frpCount[fam] : null;
    s.activeDays = daily.filter((d) => d[fam] > 0).length;
    s.satellites = meta.sensors
      .filter((x) => familyOf(x.id) === fam && x.from <= end && (x.to === null || x.to >= start))
      .map((x) => x.id);
  }
  return { start, end, stats, daily, ...counts };
}

export interface RawCell {
  cell: string;
  count: number;
  frpSum: number;
}

/** Raw detections of one family per H3 cell. */
export function familyCells(features: HotspotFeature[], family: SensorFamily, resolution: number): RawCell[] {
  const cells = new Map<string, RawCell>();
  for (const h of features) {
    if (familyOf(h.properties.sensor) !== family) continue;
    const [lon, lat] = h.geometry.coordinates;
    const id = latLngToCell(lat, lon, resolution);
    const c = cells.get(id) ?? { cell: id, count: 0, frpSum: 0 };
    c.count += 1;
    c.frpSum += h.properties.frp ?? 0;
    cells.set(id, c);
  }
  return [...cells.values()];
}

export const familyFeatures = (features: HotspotFeature[], family: SensorFamily) =>
  features.filter((h) => familyOf(h.properties.sensor) === family);
