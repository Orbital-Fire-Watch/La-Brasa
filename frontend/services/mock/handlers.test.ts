/// <reference types="node" />
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { RegionsResponse } from "../api/types";
import { MockApi, MockApiError } from "./handlers";
import { buildWorld } from "./world";

const regions = JSON.parse(readFileSync(new URL("../../public/mock/regions.json", import.meta.url), "utf8")) as RegionsResponse;
const t0 = performance.now();
const world = buildWorld(regions, "2026-11-13");
const buildMs = performance.now() - t0;
const api = new MockApi(world, {
  areas: true, daily: true, events: true, anomaly: true, anomaly_window: true, grid_by_day: true, landcover: false,
});

function code(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    if (e instanceof MockApiError) return e.code;
    throw e;
  }
  return "OK";
}

describe("mock api", () => {
  it("builds the world quickly enough for the browser", () => {
    expect(buildMs).toBeLessThan(5000);
    expect(world.events.length).toBeGreaterThan(5000);
  });

  it("returns a daily series of equal-length columns", () => {
    const d = api.daily({ region_id: "ES-OR" });
    const n = d.fires.length;
    expect(n).toBe(world.nDays);
    expect(d.hotspots).toHaveLength(n);
    expect(d.events_new).toHaveLength(n);
    expect(d.fires.some((v) => v === null)).toBe(true);
  });

  it("returns events with summary, sorted by frp_sum", () => {
    const res = api.events({ date: "2025-08-14", lookback_days: 7 });
    expect(res.total).toBeGreaterThan(0);
    const frps = res.features.map((f) => f.properties.frp_sum);
    expect([...frps].sort((a, b) => b - a)).toEqual(frps);
    const detail = api.eventDetail(res.features[0].id, "2025-08-14");
    expect(detail.daily[0].date).toBe(detail.properties.start);
  });

  it("returns grid cells and anomalies", () => {
    const g = api.grid({ start: "2025-08-01", end: "2025-08-14", resolution: 6 });
    expect(g.mode).toBe("count");
    const a = api.grid({ mode: "anomaly", start: "2025-08-08", end: "2025-08-14", resolution: 5, compare: 10 });
    expect(a.mode === "anomaly" && a.years_compared).toBeLessThanOrEqual(10);
  });

  it("uses the error codes from §8", () => {
    expect(code(() => api.daily({ region_id: "ES-OR", area_id: "a_000000000000" }))).toBe("AREA_CONFLICT");
    expect(code(() => api.daily({ region_id: "XX" }))).toBe("REGION_NOT_FOUND");
    expect(code(() => api.grid({ start: "2025-08-14", end: "2025-08-01", resolution: 6 }))).toBe("INVALID_DATE_RANGE");
    expect(code(() => api.grid({ mode: "anomaly", period: "2025-08", resolution: 6 }))).toBe("RESOLUTION_OUT_OF_RANGE");
    expect(code(() => api.hotspots({ start: "2025-08-01", end: "2025-08-14", limit: 20001 }))).toBe("LIMIT_TOO_HIGH");
    expect(code(() => api.events({ date: "2025-08-14", lookback_days: 61 }))).toBe("INVALID_DATE_RANGE");
    expect(code(() => api.eventDetail("e_000000000000", "2025-08-14"))).toBe("EVENT_NOT_FOUND");
    expect(code(() => api.registerArea({ geometry: { type: "Polygon", coordinates: [[[-30, 10], [-29, 10], [-29, 11], [-30, 10]]] } }))).toBe("AREA_OUTSIDE_REGION");
  });

  it("registers areas and filters by them", () => {
    const area = api.registerArea({
      geometry: { type: "Polygon", coordinates: [[[-8.2, 42.0], [-6.8, 42.0], [-6.8, 42.6], [-8.2, 42.6], [-8.2, 42.0]]] },
    });
    expect(area.area_id).toMatch(/^a_[0-9a-f]{12}$/);
    const h = api.hotspots({ area_id: area.area_id, start: "2025-08-01", end: "2025-08-31", limit: 100 });
    expect(h.returned).toBeLessThanOrEqual(100);
  });
});
