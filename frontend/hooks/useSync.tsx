/**
 * State of the sync button and the data_version the whole app queries with.
 * Every query key contains meta.data_version, so a new effective version requests all data again while the
 * components (and the map) stay mounted. A sync with new rows gives a new data_version in /api/meta; without new
 * rows a local revision suffix (#rN) still makes every view load again. A server that cannot fetch (no FIRMS key,
 * no pipeline) is reported as "unavailable" and nothing is reloaded.
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { clearQueryCache } from "./useApiQuery";
import type { MetaResponse } from "../services/api/types";
import { runSync } from "../services/api/sync";

export type SyncState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; at: string; result: "completed" | "up_to_date"; newHotspots: number }
  | { status: "failed"; at: string; reason: "unavailable" | "error"; error: unknown; message?: string };

interface SyncValue {
  state: SyncState;
  run: () => void;
  dataVersion: string;
}

const SyncContext = createContext<SyncValue | null>(null);
export const SyncContextProvider = SyncContext.Provider;

export function useSync(): SyncValue {
  const ctx = useContext(SyncContext);
  if (!ctx) throw new Error("useSync must be used inside the sync provider");
  return ctx;
}

interface Override {
  /** meta.data_version when the override was made; a different version from /api/meta wins again */
  base: string;
  version: string;
}

/** Runs syncs and returns the meta the app should use (with the version after the last sync). */
export function useSyncController(meta: MetaResponse | null, reloadMeta: () => void) {
  const [state, setState] = useState<SyncState>({ status: "idle" });
  const [override, setOverride] = useState<Override | null>(null);
  const running = useRef(false);
  const revision = useRef(0);

  const effectiveMeta = useMemo<MetaResponse | null>(() => {
    if (!meta) return null;
    if (!override || override.base !== meta.data_version) return meta;
    return { ...meta, data_version: override.version };
  }, [meta, override]);

  const run = useCallback(() => {
    if (!meta || !effectiveMeta || running.current) return;
    running.current = true;
    setState({ status: "running" });
    const current = effectiveMeta.data_version;
    runSync()
      .then((outcome) => {
        const at = new Date().toISOString();
        if (outcome.kind === "unavailable") {
          setState({ status: "failed", at, reason: "unavailable", error: null, message: outcome.message });
          return;
        }
        if (outcome.status.state === "failed") {
          setState({ status: "failed", at, reason: "error", error: null, message: outcome.status.message ?? undefined });
          return;
        }
        // The fetch succeeded: request the data again, also when nothing is new.
        revision.current += 1;
        const newRows = outcome.status.new_rows ?? 0;
        clearQueryCache();
        setOverride({ base: meta.data_version, version: `${current.replace(/#r\d+$/, "")}#r${revision.current}` });
        reloadMeta();
        setState({
          status: "done",
          at,
          result: newRows > 0 ? "completed" : "up_to_date",
          newHotspots: newRows,
        });
      })
      .catch((error: unknown) => setState({
        status: "failed", at: new Date().toISOString(), reason: "error", error,
        message: error instanceof Error ? error.message : undefined,
      }))
      .finally(() => {
        running.current = false;
      });
  }, [meta, effectiveMeta, reloadMeta]);

  const value = useMemo<SyncValue | null>(
    () => (effectiveMeta ? { state, run, dataVersion: effectiveMeta.data_version } : null),
    [state, run, effectiveMeta],
  );
  return { effectiveMeta, value };
}
