/**
 * All shareable view state lives in the URL (spec §7.1), e.g.
 *   /analysis?region=ES-OR&date=2025-08-14&lookback=7&metric=fires&conf=nominal
 * so "Bearbeiten", reload and sharing work without extra state management.
 */
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { isIsoDate } from "../lib/dates";
import { LOOKBACKS, METHODS, type ConfidenceLevel, type Lookback, type Method } from "../lib/methods";

export type Page = "select" | "analysis";
export type MapView = "events" | "cells";
export type CompareSetting = "all" | 5 | 10;

export interface AppState {
  page: Page;
  /** region_id from /api/regions */
  region: string | null;
  /** area_id from POST /api/areas, or "local" when the backend has no /areas yet */
  area: string | null;
  /** reference day D₀ chosen on page 1 */
  date: string | null;
  /** current day D of the time slider on page 2 */
  d: string | null;
  lookback: Lookback;
  metric: Method;
  conf: ConfidenceLevel;
  view: MapView;
  anomaly: boolean;
  compare: CompareSetting;
  event: string | null;
}

const PATHS: Record<Page, string> = { select: "/", analysis: "/analysis" };
const DEFAULTS = { lookback: 7, metric: "fires", conf: "nominal", view: "events", compare: "all" } as const;

function parse(href: string): AppState {
  const url = new URL(href);
  const q = url.searchParams;
  const lookback = Number(q.get("lookback"));
  const metric = q.get("metric") as Method | null;
  const compare = q.get("compare");
  return {
    page: url.pathname.replace(/\/+$/, "").endsWith("/analysis") ? "analysis" : "select",
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
  };
}

function toUrl(s: AppState): string {
  const q = new URLSearchParams();
  if (s.region) q.set("region", s.region);
  if (s.area) q.set("area", s.area);
  if (s.date) q.set("date", s.date);
  if (s.page === "analysis" && s.d && s.d !== s.date) q.set("d", s.d);
  if (s.lookback !== DEFAULTS.lookback) q.set("lookback", String(s.lookback));
  if (s.metric !== DEFAULTS.metric) q.set("metric", s.metric);
  if (s.conf !== DEFAULTS.conf) q.set("conf", s.conf);
  if (s.page === "analysis") {
    if (s.view !== DEFAULTS.view) q.set("view", s.view);
    if (s.anomaly) q.set("anomaly", "1");
    if (s.compare !== DEFAULTS.compare) q.set("compare", String(s.compare));
    if (s.event) q.set("event", s.event);
  }
  const query = q.toString();
  return `${PATHS[s.page]}${query ? `?${query}` : ""}`;
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

export type SetAppState = (patch: Partial<AppState>, opts?: { push?: boolean }) => void;

export function useAppState(): [AppState, SetAppState] {
  const href = useSyncExternalStore(subscribe, getHref);
  const state = useMemo(() => parse(href), [href]);
  const set = useCallback<SetAppState>((patch, opts) => {
    const next = { ...parse(window.location.href), ...patch };
    const url = toUrl(next);
    if (opts?.push || next.page !== parse(window.location.href).page) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
    if (opts?.push || patch.page) window.scrollTo({ top: 0 });
    emit();
  }, []);
  return [state, set];
}
