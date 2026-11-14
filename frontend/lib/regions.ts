/**
 * Helpers for the predefined areas from /api/regions. The spec has countries, regions and provinces;
 * the current backend delivers only countries and NUTS-2 regions, so nothing may assume a fixed level.
 */
import type { RegionFeature, RegionLevel, RegionsResponse } from "../services/api/types";
import { bboxOf, pointInBbox, pointInGeometry, type Position } from "./geo";

const LEVEL_DEPTH: Record<RegionLevel, number> = { country: 0, region: 1, province: 2 };

/** The API names the countries in English or the local language; the app is German. */
const COUNTRY_NAME: Record<string, string> = { ES: "Spanien", PT: "Portugal" };

export function localizeRegions(regions: RegionsResponse): RegionsResponse {
  return {
    ...regions,
    features: regions.features.map((f) =>
      f.properties.level === "country" && COUNTRY_NAME[f.properties.id]
        ? { ...f, properties: { ...f.properties, name: COUNTRY_NAME[f.properties.id] } }
        : f,
    ),
  };
}

/** All areas of the most detailed level below the countries – provinces if there are any, else regions. */
export function finestRegions(regions: RegionsResponse | null): RegionFeature[] {
  if (!regions) return [];
  const depth = Math.max(0, ...regions.features.map((f) => LEVEL_DEPTH[f.properties.level]));
  return depth === 0 ? [] : regions.features.filter((f) => LEVEL_DEPTH[f.properties.level] === depth);
}

/** The area that contains the point, or null (sea, border strip, outside Spain and Portugal). */
export function regionAt(p: Position, features: RegionFeature[]): RegionFeature | null {
  return features.find((f) => pointInBbox(p, f.properties.bbox ?? bboxOf(f.geometry)) && pointInGeometry(p, f.geometry)) ?? null;
}

/** "Festland und Balearen" only if the API actually has the Balearic Islands. */
export function coverageDetail(regions: RegionsResponse | null): string {
  return regions?.features.some((f) => /balear/i.test(f.properties.name)) ? "Festland und Balearen" : "Festland";
}
