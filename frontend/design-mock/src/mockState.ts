/**
 * URL state of the mock. Same shape as the app's useAppState, so useSelection can be reused, but the page
 * is a query parameter (?page=analysis): the mock must stay under /design-mock/ instead of switching to / or /analysis.
 */
import { useCallback, useMemo, useSyncExternalStore } from "react";
import type { AppState } from "../../hooks/useAppState";
import { isIsoDate } from "../../lib/dates";
import { LOOKBACKS, METHODS, type Lookback, type Method } from "../../lib/methods";

const DEFAULTS = { lookback: 7, metric: "fires", conf: "nominal", view: "events", compare: "all" } as const;

/** How fire data is shown: harmonised (default), raw MODIS, raw VIIRS, or both side by side. */
export type DisplayMode = "harmonised" | "modis" | "viirs" | "compare";
export const DISPLAY_MODES: readonly DisplayMode[] = ["harmonised", "modis", "viirs", "compare"];

/** The app state plus the mock's own `display` parameter. */
export type MockState = AppState & { display: DisplayMode };
export type SetMockState = (patch: Partial<MockState>, opts?: { push?: boolean }) => void;

function parse(href: string): MockState {
  const q = new URL(href).searchParams;
  const lookback = Number(q.get("lookback"));
  const metric = q.get("metric") as Method | null;
  const compare = q.get("compare");
  const display = q.get("display") as DisplayMode | null;
  return {
    page: q.get("page") === "analysis" ? "analysis" : "select",
    region: q.get("region"),
    area: q.get("area"),
    date: isIsoDate(q.get("date")) ? q.get("date") : null,
    d: isIsoDate(q.get("d")) ? q.get("d") : null,
    lookback: (LOOKBACKS as readonly number[]).includes(lookback) ? (lookback as Lookback) : DEFAULTS.lookback,
    metric: metric && METHODS.includes(metric) ? metric : DEFAULTS.metric,
    conf: q.get("conf") === "high" ? "high" : DEFAULTS.conf,
    view: q.get("view") === "cells" ? "cells" : DEFAULTS.view,
    anomaly: q.get("anomaly") === "1",
    compare: compare === "5" ? 5 : compare === "10" ? 10 : "all",
    event: q.get("event"),
    display: display && DISPLAY_MODES.includes(display) ? display : "harmonised",
  };
}

function toUrl(s: MockState): string {
  const q = new URLSearchParams();
  if (s.page === "analysis") q.set("page", "analysis");
  if (s.region) q.set("region", s.region);
  if (s.area) q.set("area", s.area);
  if (s.date) q.set("date", s.date);
  if (s.page === "analysis" && s.d && s.d !== s.date) q.set("d", s.d);
  if (s.lookback !== DEFAULTS.lookback) q.set("lookback", String(s.lookback));
  if (s.metric !== DEFAULTS.metric) q.set("metric", s.metric);
  if (s.conf !== DEFAULTS.conf) q.set("conf", s.conf);
  if (s.display !== "harmonised") q.set("display", s.display);
  if (s.page === "analysis") {
    if (s.view !== DEFAULTS.view) q.set("view", s.view);
    if (s.anomaly) q.set("anomaly", "1");
    if (s.compare !== DEFAULTS.compare) q.set("compare", String(s.compare));
    if (s.event) q.set("event", s.event);
  }
  const query = q.toString();
  return `${window.location.pathname}${query ? `?${query}` : ""}`;
}

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

const getHref = () => window.location.href;

export function useMockState(): [MockState, SetMockState] {
  const href = useSyncExternalStore(subscribe, getHref);
  const state = useMemo(() => parse(href), [href]);
  const set = useCallback<SetMockState>((patch, opts) => {
    const prev = parse(window.location.href);
    const next = { ...prev, ...patch };
    const url = toUrl(next);
    if (opts?.push || next.page !== prev.page) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    if (opts?.push || patch.page) window.scrollTo({ top: 0 });
    emit();
  }, []);
  return [state, set];
}
