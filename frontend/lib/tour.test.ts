import { describe, expect, it } from "vitest";
import { en } from "../i18n/messages/en";
import { es } from "../i18n/messages/es";
import { pt } from "../i18n/messages/pt";
import { placePopup, returnSearch, shouldAutoStart, stepState, TOUR_DATE, TOUR_STEPS, zoomBox } from "./tour";

const ctx = { regionId: "ES11", date: TOUR_DATE, eventId: "ev1" };

describe("tour steps", () => {
  it("has unique ids and texts in every language", () => {
    const ids = TOUR_STEPS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const messages of [en, es, pt] as Record<string, unknown>[]) {
      for (const id of ids) {
        expect(messages[`tour.${id}.title`]).toBeTruthy();
        expect(messages[`tour.${id}.text`]).toBeTruthy();
      }
    }
  });

  it("starts and ends on the right pages", () => {
    expect(TOUR_STEPS[0].targets).toEqual([]);
    expect(TOUR_STEPS[0].page).toBe("select");
    expect(TOUR_STEPS[TOUR_STEPS.length - 1].page).toBe("analysis");
  });

  it("sets the complete state, so going back leaves nothing over", () => {
    const compare = stepState(TOUR_STEPS.find((s) => s.id === "compare")!, ctx);
    const next = stepState(TOUR_STEPS.find((s) => s.id === "analysis")!, ctx);
    expect(compare.display).toBe("compare");
    expect(next.display).toBe("harmonised");
    expect(Object.keys(next).sort()).toEqual(Object.keys(compare).sort());
  });

  it("uses the test area and date only where the step asks for it", () => {
    const welcome = stepState(TOUR_STEPS[0], ctx);
    expect(welcome.region).toBeNull();
    expect(welcome.date).toBeNull();
    const fire = stepState(TOUR_STEPS.find((s) => s.id === "maptile")!, ctx);
    expect(fire).toMatchObject({ page: "analysis", region: "ES11", date: TOUR_DATE, event: "ev1" });
    expect(stepState(TOUR_STEPS.find((s) => s.id === "charts")!, ctx).event).toBeNull();
  });

  it("zooms close enough for single hotspots", () => {
    const [x0, y0, x1, y1] = zoomBox([-7.37, 42.23]);
    expect(x1 - x0).toBeLessThan(0.2);
    expect(y1 - y0).toBeLessThan(0.1);
  });
});

describe("returnSearch and shouldAutoStart", () => {
  it("goes back to the start page with the previous selection", () => {
    expect(returnSearch("?page=analysis&region=ES43&date=2025-07-01&event=x&d=2025-07-03&tour=1")).toBe("?region=ES43&date=2025-07-01");
    expect(returnSearch("?tour=1")).toBe("");
    expect(returnSearch("")).toBe("");
  });

  it("starts by itself only on a first visit without a shared link", () => {
    expect(shouldAutoStart({ search: "", stored: null })).toBe(true);
    expect(shouldAutoStart({ search: "?region=ES11", stored: null })).toBe(false);
    expect(shouldAutoStart({ search: "?page=analysis", stored: null })).toBe(false);
    expect(shouldAutoStart({ search: "", stored: "skipped" })).toBe(false);
  });
});

describe("placePopup", () => {
  const vp = { w: 1200, h: 800 };
  const size = { w: 320, h: 200 };

  it("centres without an anchor", () => {
    expect(placePopup(null, size, vp)).toEqual({ left: 440, top: 300, side: "center" });
  });

  it("prefers the right side, then left, below, above", () => {
    expect(placePopup({ x: 12, y: 100, w: 336, h: 200 }, size, vp).side).toBe("right");
    expect(placePopup({ x: 900, y: 500, w: 280, h: 200 }, size, vp).side).toBe("left");
    expect(placePopup({ x: 0, y: 60, w: 1200, h: 300 }, size, vp).side).toBe("bottom");
    expect(placePopup({ x: 0, y: 500, w: 1200, h: 280 }, size, vp).side).toBe("top");
  });

  it("stays inside the viewport when nothing fits", () => {
    const p = placePopup({ x: 0, y: 0, w: 1200, h: 800 }, size, vp);
    expect(p.left).toBeGreaterThanOrEqual(8);
    expect(p.top).toBeGreaterThanOrEqual(8);
    expect(p.left + size.w).toBeLessThanOrEqual(vp.w - 8);
    expect(p.top + size.h).toBeLessThanOrEqual(vp.h - 8);
  });
});
