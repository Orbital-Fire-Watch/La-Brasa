/** Loads raw counts per sensor family (services/api/sensorDaily.ts) once per key and keeps them while views switch. */
import { useEffect, useRef, useState } from "react";
import { isAbortError } from "../services/api/errors";
import type { Progress, SensorDailyResult } from "../services/api/sensorDaily";

const cache = new Map<string, SensorDailyResult>();

type Run = { key: string; attempt: number; progress: Progress; error: unknown };

export type SensorDailyState =
  | { status: "idle" }
  | { status: "loading"; progress: Progress }
  | { status: "error"; error: unknown; retry: () => void }
  | { status: "success"; result: SensorDailyResult };

/** Loads once per key (key must contain data_version, area and confidence); switching views reuses the cache. */
export function useSensorDaily(
  key: string | null,
  load: (signal: AbortSignal, onProgress: (p: Progress) => void) => Promise<SensorDailyResult>,
): SensorDailyState {
  const [run, setRun] = useState<Run | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [, setDone] = useState(0);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    if (!key || cache.has(key)) return;
    const ctrl = new AbortController();
    loadRef.current(ctrl.signal, (progress) => {
      if (!ctrl.signal.aborted) setRun({ key, attempt, progress, error: null });
    })
      .then((result) => {
        cache.set(key, result);
        setDone((d) => d + 1);
      })
      .catch((error: unknown) => {
        if (!isAbortError(error) && !ctrl.signal.aborted) setRun({ key, attempt, progress: { done: 0, total: 0 }, error });
      });
    return () => ctrl.abort();
  }, [key, attempt]);

  if (!key) return { status: "idle" };
  const cached = cache.get(key);
  if (cached) return { status: "success", result: cached };
  const current = run && run.key === key && run.attempt === attempt ? run : null;
  if (current?.error) return { status: "error", error: current.error, retry: () => setAttempt((a) => a + 1) };
  return { status: "loading", progress: current?.progress ?? { done: 0, total: 0 } };
}
