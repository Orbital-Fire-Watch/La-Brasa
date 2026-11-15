/**
 * Sync: ask the backend to fetch the latest FIRMS data (fetch → harmonise → load), then reload everything.
 *
 *   POST /api/sync  → 202 SyncStatus: starts a sync, or returns the one already running
 *   GET  /api/sync  → 200 SyncStatus: the frontend polls it every 2 s while state is "running"
 *
 * 404/405/501 (e.g. NOT_IMPLEMENTED: no FIRMS key or no pipeline): fetching is unavailable; nothing is reloaded,
 * because no new data can have arrived.
 * After a successful load the backend reports a new data_version in /api/meta; every query key contains it,
 * so reloading /api/meta reloads all views (spec §6.1).
 */
import { apiRequest } from "./client";
import { ApiError } from "./errors";
import type { SyncStatus } from "./types";

/** What the frontend got: a finished sync, or a server that cannot fetch at all. */
export type SyncOutcome = { kind: "synced"; status: SyncStatus } | { kind: "unavailable"; message?: string };

export const SYNC_POLL_MS = 2000;
/** Fetch, harmonisation and load can take several minutes; stop waiting after 30. */
const SYNC_POLL_MAX = 900;

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Starts a sync (or joins the running one) and waits until it succeeded or failed. */
export async function runSync(): Promise<SyncOutcome> {
  let status: SyncStatus;
  try {
    status = await apiRequest<SyncStatus>("POST", "/api/sync");
  } catch (e) {
    // Server without sync: report it, do not pretend anything was fetched.
    if (e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501)) return { kind: "unavailable", message: e.message };
    throw e;
  }
  for (let i = 0; status.state === "running"; i++) {
    if (i >= SYNC_POLL_MAX) throw new ApiError(504, "QUERY_TIMEOUT", "The data sync is still running. Try again later.");
    await wait(SYNC_POLL_MS);
    status = await apiRequest<SyncStatus>("GET", "/api/sync");
  }
  return { kind: "synced", status };
}
