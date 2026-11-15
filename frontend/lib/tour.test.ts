import { describe, expect, it } from "vitest";
import { en } from "../i18n/messages/en";
import { es } from "../i18n/messages/es";
import { pt } from "../i18n/messages/pt";
import {
  placePopup, returnSearch, shouldAutoStart, stepState, TOUR_DATE, TOUR_STEPS, TOUR_TEXT_VARS, tourSteps, zoomBox,
  type TourStepId,
} from "./tour";

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

const ALL = { forecast: true, anomaly: true, clouds: true };
const MESSAGES = { en, es, pt } as Record<string, Record<string, unknown>>;
const text = (lang: string, key: string) => String(MESSAGES[lang][key]);
const sentences = (s: string) => s.split(/[.!?](?:\s|$)/).filter((x) => x.trim()).length;

describe("tutorial quality (KPIs, docs/tutorial-konzept.md §6)", () => {
  it("covers every feature added after the first version", () => {
    const ids = TOUR_STEPS.map((s) => s.id);
    for (const id of ["header", "forecast", "anomaly", "playback", "clouds"] as TourStepId[]) expect(ids).toContain(id);
  });

  it("keeps the order of the first version and only adds steps", () => {
    const first: TourStepId[] = ["welcome", "map", "info", "settings", "area", "selection", "zoom", "calendar", "draw", "compare",
      "analysis", "short", "maptile", "slider", "charts"];
    expect(TOUR_STEPS.map((s) => s.id).filter((id) => first.includes(id))).toEqual(first);
  });

  it("stays short enough: at most 20 steps", () => {
    expect(TOUR_STEPS.length).toBeLessThanOrEqual(20);
  });

  it("only uses placeholders the popup fills", () => {
    const known = new Set<string>(TOUR_TEXT_VARS);
    for (const lang of Object.keys(MESSAGES)) {
      for (const s of TOUR_STEPS) {
        for (const key of [`tour.${s.id}.title`, `tour.${s.id}.text`]) {
          for (const [, name] of text(lang, key).matchAll(/\{(\w+)\}/g)) expect(known, `${lang} ${key} {${name}}`).toContain(name);
        }
      }
    }
  });

  it("has uniform popups: title up to 40 characters, text up to 340 characters and 4 sentences", () => {
    for (const lang of Object.keys(MESSAGES)) {
      for (const s of TOUR_STEPS) {
        const title = text(lang, `tour.${s.id}.title`);
        const body = text(lang, `tour.${s.id}.text`);
        expect(title.length, `${lang} ${s.id} title`).toBeLessThanOrEqual(40);
        expect(body.length, `${lang} ${s.id} text`).toBeLessThanOrEqual(340);
        expect(sentences(body), `${lang} ${s.id} sentences`).toBeLessThanOrEqual(4);
      }
    }
  });

  it("is translated: Spanish and Portuguese texts differ from English", () => {
    for (const s of TOUR_STEPS) {
      for (const lang of ["es", "pt"]) expect(text(lang, `tour.${s.id}.text`), `${lang} ${s.id}`).not.toBe(text("en", `tour.${s.id}.text`));
    }
  });
});

describe("optional parts of the app", () => {
  it("leaves out a step whose part is missing, and nothing else", () => {
    expect(tourSteps(ALL)).toHaveLength(TOUR_STEPS.length);
    const without = tourSteps({ forecast: false, anomaly: false, clouds: false }).map((s) => s.id);
    expect(without).not.toContain("forecast");
    expect(without).not.toContain("anomaly");
    expect(without).not.toContain("clouds");
    expect(without).toHaveLength(TOUR_STEPS.length - 3);
    expect(tourSteps({ ...ALL, clouds: false }).map((s) => s.id)).not.toContain("clouds");
  });

  it("marks exactly the steps of optional parts", () => {
    expect(TOUR_STEPS.filter((s) => s.requires).map((s) => [s.id, s.requires])).toEqual([
      ["forecast", "forecast"], ["anomaly", "anomaly"], ["clouds", "clouds"],
    ]);
  });
});

describe("states of the new steps", () => {
  const state = (id: TourStepId) => stepState(TOUR_STEPS.find((s) => s.id === id)!, ctx);

  it("shows the outlook on the latest day, where it exists, for the test area", () => {
    expect(state("forecast")).toMatchObject({ page: "analysis", region: "ES11", date: null, event: null });
  });

  it("switches anomalies on only in their own step", () => {
    expect(state("anomaly")).toMatchObject({ page: "analysis", anomaly: true, event: null });
    for (const s of TOUR_STEPS.filter((x) => x.id !== "anomaly")) expect(stepState(s, ctx).anomaly, s.id).toBe(false);
  });

  it("keeps the strongest fire selected while the slider and playback are shown", () => {
    expect(state("slider").event).toBe("ev1");
    expect(state("playback").event).toBe("ev1");
  });

  it("introduces the header on the start page, before the analysis", () => {
    const ids = TOUR_STEPS.map((s) => s.id);
    expect(state("header").page).toBe("select");
    expect(ids.indexOf("header")).toBeLessThan(ids.indexOf("analysis"));
  });

  it("sets the same complete set of keys in every step", () => {
    const keys = Object.keys(stepState(TOUR_STEPS[0], ctx)).sort();
    for (const s of TOUR_STEPS) expect(Object.keys(stepState(s, ctx)).sort(), s.id).toEqual(keys);
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
