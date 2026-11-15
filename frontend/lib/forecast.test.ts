/// <reference types="node" />
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { en } from "../i18n/messages/en";
import { es } from "../i18n/messages/es";
import { pt } from "../i18n/messages/pt";
import { MockApi } from "../services/mock/handlers";
import { buildWorld } from "../services/mock/world";
import type { RegionsResponse } from "../services/api/types";
import { RISK_COLOR } from "./colors";
import { forecastScope, forecastVisible, RISK_ORDER, worstClass } from "./forecast";
import { rectanglePolygon } from "./geo";

const regions = JSON.parse(readFileSync(new URL("../public/mock/regions.json", import.meta.url), "utf8")) as RegionsResponse;
const byId = new Map(regions.features.map((f) => [f.properties.id, f]));
const features = { areas: true, daily: true, events: true, anomaly: true, anomaly_window: true, grid_by_day: true, landcover: false };

describe("forecast box", () => {
  it("is shown only up to 10 days before the last data day", () => {
    expect(forecastVisible("2026-11-13", "2026-11-13")).toBe(true);
    expect(forecastVisible("2026-11-03", "2026-11-13")).toBe(true);
    expect(forecastVisible("2026-11-02", "2026-11-13")).toBe(false);
    expect(forecastVisible("2023-08-01", "2026-11-13")).toBe(false);
  });

  it("maps region, province, country and drawn area to NUTS-2 regions", () => {
    const f = regions.features;
    expect(forecastScope(byId.get("PT11") ?? null, null, f)).toEqual({ kind: "region", ids: ["PT11"] });
    expect(forecastScope(byId.get("ES-C") ?? null, null, f)).toEqual({ kind: "province", ids: ["ES-GA"] });
    expect(forecastScope(byId.get("PT") ?? null, null, f).ids.sort()).toEqual(["PT11", "PT15", "PT16", "PT17", "PT18"]);
    // a box across the Galicia / Asturias border touches both, nothing in the south
    const area = forecastScope(null, rectanglePolygon([-7.6, 42.9], [-6.4, 43.4]), f);
    expect(area.kind).toBe("area");
    expect(area.ids).toEqual(expect.arrayContaining(["ES-AS", "ES-GA"]));
    expect(area.ids).not.toContain("ES-AN");
  });

  it("mock: 10 days per region after the last mock day, lo <= p <= hi, 503 when switched off", () => {
    const api = new MockApi(buildWorld(regions, "2026-11-13"), { ...features, forecast: true });
    const r = api.forecastDaily({ region_id: "PT11" });
    expect(r.issue_date).toBe("2026-11-13");
    expect(r.days.map((d) => d.lead_days)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(r.days[0].target_date).toBe("2026-11-14");
    expect(r.days.every((d) => d.p_big_fire_day_lo <= d.p_big_fire_day && d.p_big_fire_day <= d.p_big_fire_day_hi)).toBe(true);
    expect(api.forecastDaily({}).days).toHaveLength(200);
    expect(api.forecastDaily({ region_id: "ES-GA" }).days).toHaveLength(10);
    const off = new MockApi(buildWorld(regions, "2026-11-13"), { ...features, forecast: false });
    expect(() => off.forecastDaily({})).toThrow();
  });

  it("colours by class, lightness strictly falling from low to very_high", () => {
    const lum = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const l = RISK_ORDER.map((c) => lum(RISK_COLOR[c]));
    for (let i = 1; i < l.length; i++) expect(l[i]).toBeLessThan(l[i - 1]);
    expect(worstClass([{ risk_class: "normal" }, { risk_class: "high" }] as never)).toBe("high");
  });

  it("every forecast text exists in EN, ES and PT", () => {
    const keys = (m: object) => Object.keys(m).filter((k) => k.startsWith("fc.")).sort();
    expect(keys(es)).toEqual(keys(en));
    expect(keys(pt)).toEqual(keys(en));
    expect(keys(en).length).toBeGreaterThan(15);
  });
});
