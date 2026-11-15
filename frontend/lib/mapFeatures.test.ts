import { describe, expect, it } from "vitest";
import { AGE_COLOR } from "./colors";
import type { FireUnit } from "./fireUnits";
import { eventShapes } from "./mapFeatures";
import type { AreaGeometry } from "./geo";

const square = (x: number): AreaGeometry => ({ type: "Polygon", coordinates: [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]]] });

const unit = (extra: Partial<FireUnit>): FireUnit => ({
  id: "e_1", kind: "event", geometry: square(0), coreGeometry: null, extensionGeometry: null, bbox: [0, 0, 1, 1],
  first_seen: "2025-08-01", last_seen: "2025-08-02", duration_days: 2, days_since_last: 0, active: true, isNew: false,
  hotspots: 5, fires: 5, frp_sum: 50, area_km2: 1, trend: null, province_id: null, centroid: [0.5, 0.5], cloud: null, seenNextDay: null, ...extra,
});

describe("eventShapes", () => {
  it("draws an event without extension as one core shape", () => {
    const { polygons } = eventShapes([unit({})], AGE_COLOR);
    expect(polygons.features.map((f) => f.properties?.part)).toEqual(["core"]);
  });

  it("draws the extension as a second, paler shape with the same id and colour", () => {
    const u = unit({ geometry: square(0), coreGeometry: square(0), extensionGeometry: square(2) });
    const [core, ext] = eventShapes([u], AGE_COLOR).polygons.features;
    expect(core.geometry).toEqual(square(0));
    expect(ext.geometry).toEqual(square(2));
    expect(ext.properties).toMatchObject({ id: "e_1", part: "extension", color: core.properties?.color });
    expect(ext.properties?.opacity).toBeLessThan(core.properties?.opacity);
  });
});
