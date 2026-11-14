/**
 * Sync: ask the backend to fetch the latest FIRMS data, then reload everything in the frontend.
 *
 * ── For the backend ──────────────────────────────────────────────────────────────────────────────────────────
 * This file is the contract the frontend already uses. Please implement it and add it to the OpenAPI spec;
 * after `npm run gen:types` replace these hand-written types with the generated ones (spec §6 style).
 *
 *   POST /api/sync            body SyncRequest  → 200 SyncResponse (finished) or 202 SyncResponse (status "running")
 *   GET  /api/sync/{job_id}                     → 200 SyncResponse (the frontend polls every 2 s while "running")
 *
 *   Errors use the usual ErrorResponse: 409 SYNC_IN_PROGRESS (another sync is running; return its job_id in
 *   `message` or start polling it), 501 NOT_IMPLEMENTED, 500 INTERNAL_ERROR.
 *
 *   After a successful import the backend assigns a NEW data_version, which /api/meta then also returns.
 *   Every query key in the frontend contains the data_version, so a new version reloads all views (spec §6.1).
 * ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
 */
import { CONFIG } from "../../../lib/config";
import { apiRequest } from "../../../services/api/client";
import { ApiError } from "../../../services/api/errors";
import type { Sensor } from "../../../services/api/types";

/** Body of POST /api/sync. */
export interface SyncRequest {
  /**
   * "recent": only new acquisitions since the last import (normal case, a few minutes).
   * "full": re-import everything from `since` on (e.g. after a change of the harmonisation weights).
   */
  scope: "recent" | "full";
  /** Only with scope "full": first day to re-import, "YYYY-MM-DD". Default: first_date from /api/meta. */
  since?: string;
  /** Restrict the import to some sensors. Default: all sensors that still deliver data. */
  sensors?: Sensor[];
}

/** Per-sensor result of an import. */
export interface SyncSourceResult {
  sensor: Sensor;
  /** Time of the newest acquisition now in the database, ISO 8601 UTC, e.g. "2025-08-14T13:42:00Z". */
  last_acquisition: string;
  /** Hotspots added by this sync for this sensor. */
  new_hotspots: number;
}

/** Response of POST /api/sync and GET /api/sync/{job_id}. */
export interface SyncResponse {
  /** Id of the import job, e.g. "sync-2025-08-14T13:45:10Z". */
  job_id: string;
  /**
   * "completed": done, data_version is the new version.
   * "running": still importing (HTTP 202); poll GET /api/sync/{job_id}.
   * "up_to_date": nothing new; data_version is unchanged.
   * "failed": import failed; see `message`, previous data stays valid.
   */
  status: "completed" | "running" | "up_to_date" | "failed";
  /** data_version before the sync. */
  previous_data_version: string;
  /** data_version after the sync (equal to previous_data_version while "running", for "up_to_date" and "failed"). */
  data_version: string;
  /** Last day with data after the sync, "YYYY-MM-DD" (the new meta.last_date). */
  last_date: string;
  /** ISO 8601 UTC. */
  started_at: string;
  /** ISO 8601 UTC, null while "running". */
  finished_at: string | null;
  /** Hotspots added over all sensors. */
  new_hotspots: number;
  sources: SyncSourceResult[];
  /** Optional English text for the user, e.g. why a sync failed. */
  message?: string;
}

/** What the frontend got: a real sync, or (backend without the endpoint yet) only a reload of all data. */
export type SyncOutcome = { kind: "synced"; response: SyncResponse } | { kind: "reload_only" };

export const SYNC_POLL_MS = 2000;
const SYNC_POLL_MAX = 150; // 5 minutes

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

let mockCount = 0;

/** Mock mode: the mock worker has no /api/sync, so the sync is simulated here with a new data_version. */
async function mockSync(currentVersion: string, lastDate: string): Promise<SyncResponse> {
  const started = new Date();
  await wait(900);
  mockCount += 1;
  const base = currentVersion.replace(/\+sync\d+$/, "");
  return {
    job_id: `mock-sync-${mockCount}`,
    status: "completed",
    previous_data_version: currentVersion,
    data_version: `${base}+sync${mockCount}`,
    last_date: lastDate,
    started_at: started.toISOString(),
    finished_at: new Date().toISOString(),
    new_hotspots: 0,
    sources: [],
  };
}

/** Starts a sync and waits for its end (polling while "running"). */
export async function runSync(req: SyncRequest, current: { dataVersion: string; lastDate: string }): Promise<SyncOutcome> {
  if (CONFIG.apiMode === "mock") return { kind: "synced", response: await mockSync(current.dataVersion, current.lastDate) };
  let res: SyncResponse;
  try {
    res = await apiRequest<SyncResponse>("POST", "/api/sync", { body: req });
  } catch (e) {
    // Backend without the endpoint yet: still request all data again.
    if (e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501)) return { kind: "reload_only" };
    throw e;
  }
  for (let i = 0; res.status === "running" && i < SYNC_POLL_MAX; i++) {
    await wait(SYNC_POLL_MS);
    res = await apiRequest<SyncResponse>("GET", `/api/sync/${encodeURIComponent(res.job_id)}`);
  }
  return { kind: "synced", response: res };
}
