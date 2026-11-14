import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "../services/api/errors";

/** UI state of one request. While loading, `data` holds the previous result (keeps maps and lists stable). */
export type QueryState<T> =
  | { status: "idle"; data?: undefined }
  | { status: "loading"; data?: T }
  | { status: "error"; error: unknown; data?: T }
  | { status: "success"; data: T };

const CACHE_LIMIT = 400;
const cache = new Map<string, unknown>();

function remember(key: string, value: unknown) {
  if (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
  cache.set(key, value);
}

/** Clears all cached responses, e.g. when meta.data_version changes after an import. */
export function clearQueryCache() {
  cache.clear();
}

/**
 * Loads data for `key` (null = nothing to load). A new key aborts the running request (AbortController);
 * `debounceMs` delays the request for high-frequency input such as the time slider or map moves.
 * Results are cached by key, so the key must contain every request parameter and the data_version.
 */
export function useApiQuery<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  { debounceMs = 0 }: { debounceMs?: number } = {},
): QueryState<T> & { reload: () => void } {
  const [entry, setEntry] = useState<{ key: string | null; state: QueryState<T> }>(() => ({
    key,
    state: initialState<T>(key, undefined),
  }));
  const [attempt, setAttempt] = useState(0);
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    if (key === null) {
      setEntry({ key, state: { status: "idle" } });
      return;
    }
    if (cache.has(key)) {
      setEntry({ key, state: { status: "success", data: cache.get(key) as T } });
      return;
    }
    setEntry((prev) => ({ key, state: { status: "loading", data: prev.state.data } }));
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      fetcherRef
        .current(ctrl.signal)
        .then((data) => {
          remember(key, data);
          setEntry({ key, state: { status: "success", data } });
        })
        .catch((error: unknown) => {
          if (isAbortError(error) || ctrl.signal.aborted) return;
          setEntry((prev) => ({ key, state: { status: "error", error, data: prev.state.data } }));
        });
    }, debounceMs);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [key, attempt, debounceMs]);

  const reload = useCallback(() => {
    if (key) cache.delete(key);
    setAttempt((a) => a + 1);
  }, [key]);

  // Derive the state for a key the effect has not handled yet, so one render never shows data of another key as "success".
  const state = entry.key === key ? entry.state : initialState<T>(key, entry.state.data);
  return { ...state, reload } as QueryState<T> & { reload: () => void };
}

function initialState<T>(key: string | null, previous: T | undefined): QueryState<T> {
  if (key === null) return { status: "idle" };
  if (cache.has(key)) return { status: "success", data: cache.get(key) as T };
  return { status: "loading", data: previous };
}
