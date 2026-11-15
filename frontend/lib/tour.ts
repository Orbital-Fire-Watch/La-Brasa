/**
 * Guided tutorial (docs/tutorial-konzept.md): the steps as data plus the pure helpers the overlay needs.
 * Every step describes the complete app state it shows, so "Back" only has to apply the previous step again.
 */
import type { AppState, DisplayMode } from "../hooks/useAppState";
import type { BBox, Position } from "./geo";

/** Test area: Galicia (NUTS-2 ES11 in the backend); found by name if the id is missing. */
export const TOUR_REGION_ID = "ES11";
export const TOUR_REGION_NAME = "Galicia";
/** Reference date of the test area: big fires around Ourense in August 2025. */
export const TOUR_DATE = "2025-08-15";
/** Look-back of the fire query, the same as the analysis page default. */
export const TOUR_LOOKBACK = 7;

export const TOUR_STORAGE_KEY = "la-brasa:tour";
/** Raise this when the tutorial changes a lot: everybody sees it once more. */
export const TOUR_VERSION = 1;

/** Elements marked with data-tour="…" that a step can highlight. "map" is the free map area of the start page. */
export type TourTarget =
  | "map" | "legend" | "infoboxes" | "settings" | "area" | "selection" | "exit" | "calendar" | "drawbar"
  | "compare" | "display" | "analysis" | "hero" | "short" | "maptile" | "slider" | "season" | "year";

export type TourStepId =
  | "welcome" | "map" | "info" | "settings" | "area" | "selection" | "zoom" | "calendar" | "draw" | "compare"
  | "analysis" | "hero" | "short" | "maptile" | "slider" | "charts";

export interface TourStep {
  /** also the i18n key: tour.<id>.title, tour.<id>.text */
  id: TourStepId;
  /** highlighted elements; empty = popup in the middle of the darkened page */
  targets: TourTarget[];
  page: AppState["page"];
  /** false = all of Spain and Portugal */
  region: boolean;
  /** "latest" = last day with data, "test" = TOUR_DATE */
  date: "latest" | "test";
  display?: DisplayMode;
  /** "zoom": close-up of the strongest fire (single hotspots), "fire": its outline */
  fit?: "zoom" | "fire";
  /** select the strongest fire on the analysis page */
  event?: boolean;
}

export const TOUR_STEPS: readonly TourStep[] = [
  { id: "welcome", targets: [], page: "select", region: false, date: "latest" },
  { id: "map", targets: ["map", "legend"], page: "select", region: false, date: "latest" },
  { id: "info", targets: ["infoboxes"], page: "select", region: false, date: "latest" },
  { id: "settings", targets: ["settings"], page: "select", region: false, date: "test" },
  { id: "area", targets: ["area"], page: "select", region: true, date: "test" },
  { id: "selection", targets: ["selection", "exit"], page: "select", region: true, date: "test" },
  { id: "zoom", targets: ["map", "legend"], page: "select", region: true, date: "test", fit: "zoom" },
  { id: "calendar", targets: ["calendar"], page: "select", region: true, date: "test" },
  { id: "draw", targets: ["drawbar"], page: "select", region: true, date: "test" },
  { id: "compare", targets: ["compare", "display"], page: "select", region: true, date: "test", display: "compare" },
  { id: "analysis", targets: ["analysis"], page: "select", region: true, date: "test" },
  { id: "hero", targets: ["hero"], page: "analysis", region: true, date: "test" },
  { id: "short", targets: ["short"], page: "analysis", region: true, date: "test" },
  { id: "maptile", targets: ["maptile"], page: "analysis", region: true, date: "test", fit: "fire", event: true },
  { id: "slider", targets: ["slider"], page: "analysis", region: true, date: "test", fit: "fire", event: true },
  { id: "charts", targets: ["season", "year"], page: "analysis", region: true, date: "test" },
];

export interface TourContextData {
  regionId: string | null;
  /** TOUR_DATE limited to the available data */
  date: string;
  eventId: string | null;
}

/** The complete URL state of a step; every key is set, so nothing from the previous step is left over. */
export function stepState(step: TourStep, ctx: TourContextData): Partial<AppState> {
  return {
    page: step.page,
    region: step.region ? ctx.regionId : null,
    area: null,
    date: step.date === "test" ? ctx.date : null,
    d: null,
    lookback: TOUR_LOOKBACK,
    metric: "fires",
    conf: "nominal",
    view: "events",
    anomaly: false,
    compare: "all",
    event: step.event ? ctx.eventId : null,
    display: step.display ?? "harmonised",
  };
}

/** Small box around a point, so fitting the map ends at the maximum zoom (single hotspots from zoom 11 on). */
export function zoomBox([lon, lat]: Position): BBox {
  return [lon - 0.06, lat - 0.04, lon + 0.06, lat + 0.04];
}

/**
 * Where the tutorial brings the user back to: the start page with the selection they had before.
 * Parameters of the analysis page and the tutorial switch are dropped.
 */
export function returnSearch(search: string): string {
  const q = new URLSearchParams(search);
  for (const key of ["tour", "page", "d", "event", "view", "anomaly", "compare"]) q.delete(key);
  const s = q.toString();
  return s ? `?${s}` : "";
}

export type TourStatus = "done" | "skipped";

/** Starts by itself only on the first visit, with the real data, and not when a shared link was opened. */
export function shouldAutoStart(opts: { live: boolean; search: string; stored: TourStatus | null }): boolean {
  return opts.live && opts.stored === null && returnSearch(opts.search) === "" && !new URLSearchParams(opts.search).has("page");
}

/** `?tour=1` opens the tutorial in any mode (also with mock data, for development). */
export const tourRequested = (search: string) => new URLSearchParams(search).has("tour");

export function readTourStatus(): TourStatus | null {
  try {
    const raw = localStorage.getItem(TOUR_STORAGE_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as { version?: number; status?: string };
    if (v.version !== TOUR_VERSION) return null;
    return v.status === "done" || v.status === "skipped" ? v.status : null;
  } catch {
    // Blocked storage: show the tutorial again rather than never.
    return null;
  }
}

export function writeTourStatus(status: TourStatus): void {
  try {
    localStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ version: TOUR_VERSION, status }));
  } catch {
    // Blocked storage: the tutorial starts again on the next visit.
  }
}

// ------------------------------------------------------------------ popup position

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Side = "right" | "left" | "bottom" | "top" | "center";

const SIDES: Exclude<Side, "center">[] = ["right", "left", "bottom", "top"];

/**
 * Popup next to the anchor: the first side (right, left, below, above) where it fits completely.
 * If none fits, the side with the most room; the popup then overlaps the anchor as little as possible.
 * Always kept `margin` px inside the viewport.
 */
export function placePopup(
  anchor: Rect | null, size: { w: number; h: number }, viewport: { w: number; h: number }, gap = 14, margin = 8,
): { left: number; top: number; side: Side } {
  const clampX = (x: number) => Math.max(margin, Math.min(x, viewport.w - size.w - margin));
  const clampY = (y: number) => Math.max(margin, Math.min(y, viewport.h - size.h - margin));
  if (!anchor) return { left: clampX((viewport.w - size.w) / 2), top: clampY((viewport.h - size.h) / 2), side: "center" };

  const room: Record<Exclude<Side, "center">, number> = {
    right: viewport.w - (anchor.x + anchor.w) - gap - margin,
    left: anchor.x - gap - margin,
    bottom: viewport.h - (anchor.y + anchor.h) - gap - margin,
    top: anchor.y - gap - margin,
  };
  const need = (s: Exclude<Side, "center">) => (s === "right" || s === "left" ? size.w : size.h);
  const side = SIDES.find((s) => room[s] >= need(s)) ?? SIDES.reduce((a, b) => (room[b] / need(b) > room[a] / need(a) ? b : a));

  const midX = anchor.x + anchor.w / 2 - size.w / 2;
  const midY = anchor.y + anchor.h / 2 - size.h / 2;
  switch (side) {
    case "right": return { left: clampX(anchor.x + anchor.w + gap), top: clampY(midY), side };
    case "left": return { left: clampX(anchor.x - gap - size.w), top: clampY(midY), side };
    case "bottom": return { left: clampX(midX), top: clampY(anchor.y + anchor.h + gap), side };
    case "top": return { left: clampX(midX), top: clampY(anchor.y - gap - size.h), side };
  }
}
