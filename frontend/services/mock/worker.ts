/// <reference lib="webworker" />
/**
 * Runs the mock API off the main thread: building the synthetic world takes a moment and
 * the map must stay responsive.
 */
import type { ErrorCode, ExportQuery, Features } from "../api/types";
import { CONFIG } from "../../lib/config";
import { addDays, utcToday } from "../../lib/dates";
import { MockApi, MockApiError } from "./handlers";
import { buildWorld } from "./world";

export interface MockRequestMessage {
  id: number;
  method: "GET" | "POST";
  path: string;
  query?: Record<string, string>;
  body?: unknown;
}

export type MockResponseMessage =
  | { id: number; ok: true; data: unknown }
  | { id: number; ok: false; status: number; code: ErrorCode; message: string };

const FEATURES: Features = {
  areas: true,
  daily: true,
  events: true,
  anomaly: true,
  anomaly_window: true,
  grid_by_day: true,
  landcover: false,
  forecast: true,
};
for (const key of Object.keys(FEATURES) as (keyof Features)[]) if (CONFIG.mockDisabledFeatures.includes(key)) FEATURES[key] = false;

let api: Promise<MockApi> | null = null;

function getApi(): Promise<MockApi> {
  api ??= (async () => {
    const res = await fetch(`${import.meta.env.BASE_URL}mock/regions.json`);
    if (!res.ok) throw new Error(`mock regions: HTTP ${res.status}`);
    const world = buildWorld(await res.json(), addDays(utcToday(), -1));
    return new MockApi(world, FEATURES);
  })();
  return api;
}

type Body = Record<string, unknown>;

function route(a: MockApi, { method, path, query = {}, body = {} }: MockRequestMessage): unknown {
  const b = body as Body;
  if (method === "GET") {
    if (path === "/api/meta") return a.meta();
    if (path === "/api/regions") return a.regions();
    if (path === "/api/sync") return a.syncStatus();
    if (path === "/api/forecast/daily") return a.forecastDaily(query);
    if (path === "/api/forecast/status") return a.forecastStatus();
    if (path === "/api/export.csv") return a.exportCsv(query as unknown as ExportQuery);
    const m = /^\/api\/events\/([^/]+)$/.exec(path);
    if (m) return a.eventDetail(decodeURIComponent(m[1]), query.date ?? null);
  } else {
    switch (path) {
      case "/api/calendar": return a.calendar(b);
      case "/api/daily": return a.daily(b);
      case "/api/daily/sensors": return a.sensorDaily(b);
      case "/api/grid": return a.grid(b as never);
      case "/api/hotspots": return a.hotspots(b);
      case "/api/areas": return a.registerArea(b);
      case "/api/events": return a.events(b);
      case "/api/sync": return a.startSync();
      case "/api/by-region": throw new MockApiError(501, "NOT_IMPLEMENTED", "by-region is not part of the mock.");
    }
  }
  throw new MockApiError(404, "INVALID_REQUEST", `Unknown endpoint ${method} ${path}`);
}

self.onmessage = async (e: MessageEvent<MockRequestMessage>) => {
  const msg = e.data;
  let reply: MockResponseMessage;
  try {
    reply = { id: msg.id, ok: true, data: route(await getApi(), msg) };
  } catch (err) {
    reply =
      err instanceof MockApiError
        ? { id: msg.id, ok: false, status: err.status, code: err.code, message: err.message }
        : { id: msg.id, ok: false, status: 500, code: "INTERNAL_ERROR", message: String(err) };
    if (!(err instanceof MockApiError)) console.error(err);
  }
  self.postMessage(reply);
};
