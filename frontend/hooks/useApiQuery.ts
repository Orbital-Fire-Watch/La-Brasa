import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, isAbortError } from "../services/api/errors";

/** UI state of one request. While loading, `data` holds the previous result (keeps maps and lists stable). */
export type QueryState<T> =
  | { status: "idle"; data?: undefined }
  | { status: "loading"; data?: T }
  | { status: "error"; error: unknown; data?: T }
  | { status: "success"; data: T };

const CACHE_LIMIT = 400;
/** Waits before the retries of a request that failed for a passing reason (see isTransient). */
const RETRY_DELAYS_MS = [500, 1500];
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
 * Passing server or network failures are retried twice before the error is shown.
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

  // A new key: switch to its state right away (idle, cached or loading with the previous data), so one render
  // never shows data of another key as "success". This is React's pattern for state that follows a prop.
  let current = entry;
  if (entry.key !== key) {
    current = { key, state: initialState<T>(key, entry.state.data) };
    setEntry(current);
  }

  useEffect(() => {
    if (key === null || cache.has(key)) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      fetchWithRetry(() => fetcherRef.current(ctrl.signal), ctrl.signal)
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
    if (!key) return;
    cache.delete(key);
    setEntry((prev) => ({ key, state: { status: "loading", data: prev.state.data } }));
    setAttempt((a) => a + 1);
  }, [key]);

  return { ...current.state, reload } as QueryState<T> & { reload: () => void };
}

/**
 * A 5xx without a usable answer (e.g. the dev proxy losing the backend connection) or a dropped connection often
 * succeeds on a second try; a request error (4xx) or a query timeout would only fail again.
 */
function isTransient(e: unknown): boolean {
  if (e instanceof ApiError) return e.status >= 500 && e.code !== "QUERY_TIMEOUT";
  return e instanceof TypeError;      // fetch rejects with a TypeError when no response arrives
}

async function fetchWithRetry<T>(fetcher: () => Promise<T>, signal: AbortSignal): Promise<T> {
  for (let tries = 0; ; tries++) {
    try {
      return await fetcher();
    } catch (e) {
      if (tries >= RETRY_DELAYS_MS.length || signal.aborted || !isTransient(e)) throw e;
      await delay(RETRY_DELAYS_MS[tries], signal);
    }
  }
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

function initialState<T>(key: string | null, previous: T | undefined): QueryState<T> {
  if (key === null) return { status: "idle" };
  if (cache.has(key)) return { status: "success", data: cache.get(key) as T };
  return { status: "loading", data: previous };
}
