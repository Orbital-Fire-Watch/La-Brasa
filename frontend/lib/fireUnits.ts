/**
 * §7.6 Shared type for events and H3 cells: list, map and KPI cards only work with FireUnit,
 * so the H3 fallback works while /api/events is not available.
 */
import { cellToBoundary, cellArea } from "h3-js";
import { daysBetween } from "./dates";
import { bboxOfPoints, type AreaGeometry, type BBox, type Position } from "./geo";

export interface FireUnit {
  id: string;
  kind: "event" | "cell";
  geometry: AreaGeometry;
  /** Events only: dense core and the cells joined only through the wider ring; both null without extension. */
  coreGeometry: AreaGeometry | null;
  extensionGeometry: AreaGeometry | null;
  bbox: BBox;
  first_seen: string;
  last_seen: string;
  duration_days: number;
  days_since_last: number;
  active: boolean;
  isNew: boolean;
  hotspots: number;
  fires: number;
  frp_sum: number;
  area_km2: number | null;
  trend: "growing" | "stable" | "shrinking" | null;
  province_id: string | null;
  centroid: Position;
}

interface EventLike {
  id: string;
  geometry: AreaGeometry;
  properties: {
    start: string;
    last_seen: string;
    duration_days: number;
    days_since_last: number;
    active: boolean;
    new: boolean;
    hotspots: number;
    fires: number;
    frp_sum: number;
    area_km2: number;
    bbox: BBox;
    centroid: Position;
    province_id: string;
    trend?: "growing" | "stable" | "shrinking" | null;
    core_geometry?: AreaGeometry | null;
    extension_geometry?: AreaGeometry | null;
  };
}

export function eventsToUnits(features: EventLike[]): FireUnit[] {
  return features.map((f) => ({
    id: f.id,
    kind: "event",
    geometry: f.geometry,
    coreGeometry: f.properties.core_geometry ?? null,
    extensionGeometry: f.properties.extension_geometry ?? null,
    bbox: f.properties.bbox,
    first_seen: f.properties.start,
    last_seen: f.properties.last_seen,
    duration_days: f.properties.duration_days,
    days_since_last: f.properties.days_since_last,
    active: f.properties.active,
    isNew: f.properties.new,
    hotspots: f.properties.hotspots,
    fires: f.properties.fires,
    frp_sum: f.properties.frp_sum,
    area_km2: f.properties.area_km2,
    trend: f.properties.trend ?? null,
    province_id: f.properties.province_id,
    centroid: f.properties.centroid,
  }));
}

interface CellLike {
  cell: string;
  fires: number;
  hotspots: number;
  frp_sum: number;
  first_seen?: string | null;
  last_seen?: string | null;
}

export function cellPolygon(cell: string): AreaGeometry {
  const ring = cellToBoundary(cell, true) as Position[];
  return { type: "Polygon", coordinates: [ring] };
}

/** Fallback adapter: grid cells (window [D − L + 1, D]) as fire units. */
export function cellsToUnits(cells: CellLike[], date: string, windowStart: string): FireUnit[] {
  return cells.map((c) => {
    const ring = cellToBoundary(c.cell, true) as Position[];
    const first = c.first_seen ?? windowStart;
    const last = c.last_seen ?? date;
    const since = daysBetween(last, date);
    const lons = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    return {
      id: c.cell,
      kind: "cell",
      geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] },
      coreGeometry: null,
      extensionGeometry: null,
      bbox: bboxOfPoints(ring),
      first_seen: first,
      last_seen: last,
      duration_days: daysBetween(first, last) + 1,
      days_since_last: since,
      active: since === 0,
      isNew: first === date,
      hotspots: c.hotspots,
      fires: c.fires,
      frp_sum: c.frp_sum,
      area_km2: null,
      trend: null,
      province_id: null,
      centroid: [lons.reduce((a, b) => a + b, 0) / lons.length, lats.reduce((a, b) => a + b, 0) / lats.length],
    };
  });
}

export const cellAreaKm2 = (cell: string): number => cellArea(cell, "km2");
