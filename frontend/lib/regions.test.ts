import { describe, expect, it } from "vitest";
import type { RegionFeature, RegionsResponse } from "../services/api/types";
import { rectanglePolygon } from "./geo";
import { coverageDetail, finestRegions, localizeRegions, regionAt } from "./regions";

function feature(id: string, name: string, level: RegionFeature["properties"]["level"], parent: string | null, box: [number, number, number, number]): RegionFeature {
  const g = rectanglePolygon([box[0], box[1]], [box[2], box[3]]);
  return {
    type: "Feature",
    geometry: { type: "MultiPolygon", coordinates: [g.coordinates] },
    properties: { id, name, level, country: id.slice(0, 2), parent, bbox: box },
  } as RegionFeature;
}

const nuts2: RegionsResponse = {
  type: "FeatureCollection",
  features: [
    feature("ES", "Spain", "country", null, [-10, 36, 4, 44]),
    feature("ES11", "Galicia", "region", "ES", [-9, 42, -7, 44]),
    feature("ES41", "Castilla y León", "region", "ES", [-7, 40, -2, 43]),
  ],
} as RegionsResponse;

describe("regions", () => {
  it("uses regions when the API has no provinces, and provinces once it has", () => {
    expect(finestRegions(nuts2).map((f) => f.properties.id)).toEqual(["ES11", "ES41"]);
    const withProvinces = { ...nuts2, features: [...nuts2.features, feature("ES-OR", "Ourense", "province", "ES11", [-8.5, 42, -7, 42.6])] };
    expect(finestRegions(withProvinces).map((f) => f.properties.id)).toEqual(["ES-OR"]);
    expect(finestRegions(null)).toEqual([]);
  });

  it("finds the region around a point", () => {
    const regions = finestRegions(nuts2);
    expect(regionAt([-8, 43], regions)?.properties.id).toBe("ES11");
    expect(regionAt([-5, 41], regions)?.properties.id).toBe("ES41");
    expect(regionAt([-12, 40], regions)).toBeNull();
  });

  it("names the countries in German and mentions the Balearic Islands only if present", () => {
    expect(localizeRegions(nuts2).features[0].properties.name).toBe("Spanien");
    expect(coverageDetail(nuts2)).toBe("Festland");
    const withBaleares = { ...nuts2, features: [...nuts2.features, feature("ES53", "Illes Balears", "region", "ES", [1, 38.6, 4.4, 40.1])] };
    expect(coverageDetail(withBaleares)).toBe("Festland und Balearen");
  });
});
