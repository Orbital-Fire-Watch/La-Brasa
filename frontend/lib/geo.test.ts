import { describe, expect, it } from "vitest";
import {
  circlePolygon, countVertices, geometryAreaKm2, parseCoordinateList, pointInGeometry, rectanglePolygon,
  ringSignedArea, simplifyToMaxVertices, worldWithout, type Position,
} from "./geo";

describe("geo", () => {
  it("builds a closed circle with the requested number of steps", () => {
    const c = circlePolygon([-7.86, 42.34], 20, 64);
    expect(c.coordinates[0]).toHaveLength(65);
    expect(c.coordinates[0][0]).toEqual(c.coordinates[0][64]);
    expect(geometryAreaKm2(c)).toBeGreaterThan(1200);
    expect(geometryAreaKm2(c)).toBeLessThan(1260);
  });

  it("tests points against polygons with holes", () => {
    const outer = rectanglePolygon([0, 0], [10, 10]).coordinates[0];
    const hole = rectanglePolygon([4, 4], [6, 6]).coordinates[0];
    const g = { type: "Polygon" as const, coordinates: [outer, hole] };
    expect(pointInGeometry([1, 1], g)).toBe(true);
    expect(pointInGeometry([5, 5], g)).toBe(false);
    expect(pointInGeometry([11, 5], g)).toBe(false);
  });

  it("simplifies freehand rings below the vertex limit", () => {
    const ring: Position[] = Array.from({ length: 3000 }, (_, i) => {
      const a = (i / 3000) * 2 * Math.PI;
      return [-4 + Math.cos(a) + Math.sin(a * 40) * 0.002, 40 + Math.sin(a)];
    });
    const out = simplifyToMaxVertices(ring, 1000);
    expect(out.length).toBeLessThanOrEqual(1000);
    expect(out[0]).toEqual(out[out.length - 1]);
    expect(countVertices({ type: "Polygon", coordinates: [out] })).toBe(out.length);
  });

  it("parses coordinate lists", () => {
    expect(parseCoordinateList("-8.2, 42.0\n-6.8 42.0; -6.8,42.6")).toEqual([[-8.2, 42], [-6.8, 42], [-6.8, 42.6]]);
    expect(parseCoordinateList("abc")).toBeNull();
    expect(parseCoordinateList("200, 10")).toBeNull();
  });

  it("cuts areas out of the world with clockwise holes", () => {
    const ccw = rectanglePolygon([0, 0], [2, 2]).coordinates[0];
    const cw = [...ccw].reverse();
    const mask = worldWithout([{ type: "MultiPolygon", coordinates: [[ccw], [cw]] }]);
    expect(ringSignedArea(mask.coordinates[0])).toBeGreaterThan(0);
    expect(mask.coordinates).toHaveLength(3);
    for (const hole of mask.coordinates.slice(1)) expect(ringSignedArea(hole)).toBeLessThan(0);
    expect(pointInGeometry([1, 1], mask)).toBe(false);
    expect(pointInGeometry([10, 10], mask)).toBe(true);
  });
});
