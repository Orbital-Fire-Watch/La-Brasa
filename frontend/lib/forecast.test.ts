import { describe, expect, it } from "vitest";
import { en } from "../i18n/messages/en";
import { es } from "../i18n/messages/es";
import { pt } from "../i18n/messages/pt";
import type { ForecastDay, RiskClass } from "../services/api/types";
import { RISK_COLOR } from "./colors";
import { addDays } from "./dates";
import { describeChange, forecastVisible, outlookOf, RISK_ORDER, worstClass } from "./forecast";

/** Ten days of one region after `issue`, with probability p and usual value clim per day. */
function days(issue: string, p: number[], clim: number, cls: RiskClass[] = []): ForecastDay[] {
  return p.map((v, i) => ({
    region_id: "PT11", target_date: addDays(issue, i + 1), lead_days: i + 1,
    p_big_fire_day: v, p_big_fire_day_lo: v / 2, p_big_fire_day_hi: Math.min(1, v * 2), p_fire_day: Math.min(1, v * 10),
    p_clim_big_fire_day: clim, p_clim_fire_day: clim * 10, risk_ratio: v / clim, risk_class: cls[i] ?? "low",
    source: "model", model_version: "0.2-weather",
  }));
}

describe("forecast outlook", () => {
  it("is shown only up to 10 days before the last data day", () => {
    expect(forecastVisible("2026-11-13", "2026-11-13")).toBe(true);
    expect(forecastVisible("2026-11-03", "2026-11-13")).toBe(true);
    expect(forecastVisible("2026-11-02", "2026-11-13")).toBe(false);
    expect(forecastVisible("2023-08-01", "2026-11-13")).toBe(false);
  });

  it("describes the change against the usual value in round, readable numbers", () => {
    expect(describeChange(0.06)).toEqual({ kind: "lower", percent: 95 });
    expect(describeChange(0.001)).toEqual({ kind: "lower", percent: 99 });
    expect(describeChange(0.95)).toEqual({ kind: "same" });
    expect(describeChange(1.32)).toEqual({ kind: "higher", percent: 30 });
    expect(describeChange(2.46)).toEqual({ kind: "times", factor: 2.5 });
    expect(describeChange(7.6)).toEqual({ kind: "times", factor: 8 });
    expect(describeChange(Number.NaN)).toEqual({ kind: "same" });
  });

  it("outlook: sums of the daily values and three parts (days 1-3, 4-7, 8-10)", () => {
    const d = days("2026-11-15", [0.01, 0.01, 0.01, 0.02, 0.02, 0.02, 0.02, 0.2, 0.3, 0.4], 0.05,
      ["low", "low", "low", "normal", "normal", "normal", "normal", "elevated", "high", "high"]);
    const o = outlookOf(d);
    expect(o).not.toBeNull();
    if (!o) return;
    expect(o.expectedDays).toBeCloseTo(1.01, 12);
    expect(o.usualDays).toBeCloseTo(0.5, 12);
    expect(o.change).toEqual({ kind: "times", factor: 2 });
    expect(o.parts.map((p) => [p.from, p.to, p.level, p.change.kind])).toEqual([
      ["2026-11-16", "2026-11-18", "low", "lower"],
      ["2026-11-19", "2026-11-22", "normal", "lower"],
      ["2026-11-23", "2026-11-25", "high", "times"],
    ]);
    expect(outlookOf([])).toBeNull();
  });

  it("colours by class, lightness strictly falling from low to very_high", () => {
    const lum = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const l = RISK_ORDER.map((c) => lum(RISK_COLOR[c]));
    for (let i = 1; i < l.length; i++) expect(l[i]).toBeLessThan(l[i - 1]);
    expect(worstClass(days("2026-11-15", [0.1, 0.2], 0.1, ["normal", "high"]))).toBe("high");
  });

  it("every forecast text exists in EN, ES and PT", () => {
    const keys = (m: object) => Object.keys(m).filter((k) => k.startsWith("fc.")).sort();
    expect(keys(es)).toEqual(keys(en));
    expect(keys(pt)).toEqual(keys(en));
    expect(keys(en).length).toBeGreaterThan(10);
  });
});
