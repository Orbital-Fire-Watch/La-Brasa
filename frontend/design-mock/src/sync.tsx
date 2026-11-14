/**
 * State of the sync button and the data_version the whole mock queries with.
 * Every query key contains meta.data_version, so a new effective version requests all data again while the
 * components (and the map) stay mounted.
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { clearQueryCache } from "../../hooks/useApiQuery";
import type { MetaResponse } from "../../services/api/types";
import { runSync } from "./api/sync";

export type SyncState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; at: string; result: "completed" | "up_to_date" | "reload_only"; newHotspots: number }
  | { status: "failed"; at: string; error: unknown; message?: string };

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
  lastDate: string;
}

/** Runs syncs and returns the meta the mock should use (with the version after the last sync). */
export function useSyncController(meta: MetaResponse | null, reloadMeta: () => void) {
  const [state, setState] = useState<SyncState>({ status: "idle" });
  const [override, setOverride] = useState<Override | null>(null);
  const running = useRef(false);
  const revision = useRef(0);

  const effectiveMeta = useMemo<MetaResponse | null>(() => {
    if (!meta) return null;
    if (!override || override.base !== meta.data_version) return meta;
    return { ...meta, data_version: override.version, last_date: override.lastDate > meta.last_date ? override.lastDate : meta.last_date };
  }, [meta, override]);

  const run = useCallback(() => {
    if (!meta || !effectiveMeta || running.current) return;
    running.current = true;
    setState({ status: "running" });
    const current = { dataVersion: effectiveMeta.data_version, lastDate: effectiveMeta.last_date };
    runSync({ scope: "recent" }, current)
      .then((outcome) => {
        const at = new Date().toISOString();
        if (outcome.kind === "synced" && outcome.response.status === "failed") {
          setState({ status: "failed", at, error: null, message: outcome.response.message });
          return;
        }
        // Always request the data again, also when nothing is new: that is what the button promises.
        revision.current += 1;
        const synced = outcome.kind === "synced" ? outcome.response : null;
        const version = synced && synced.status === "completed" ? synced.data_version : `${current.dataVersion.replace(/#r\d+$/, "")}#r${revision.current}`;
        clearQueryCache();
        setOverride({ base: meta.data_version, version, lastDate: synced?.last_date ?? current.lastDate });
        reloadMeta();
        setState({
          status: "done",
          at,
          result: synced ? (synced.status === "completed" ? "completed" : "up_to_date") : "reload_only",
          newHotspots: synced?.new_hotspots ?? 0,
        });
      })
      .catch((error: unknown) => setState({ status: "failed", at: new Date().toISOString(), error }))
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
