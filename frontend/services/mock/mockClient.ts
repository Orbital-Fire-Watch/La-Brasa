import { ApiError } from "../api/errors";
import type { MockRequestMessage, MockResponseMessage } from "./worker";

/** Simulated network latency so loading states are visible during development. */
const LATENCY_MS = [120, 320] as const;

let worker: Worker | null = null;
let seq = 0;
const pending = new Map<number, (msg: MockResponseMessage) => void>();

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (e: MessageEvent<MockResponseMessage>) => {
      pending.get(e.data.id)?.(e.data);
      pending.delete(e.data.id);
    };
  }
  return worker;
}

const abortError = () => new DOMException("The request was aborted.", "AbortError");

export function mockRequest<T>(
  method: "GET" | "POST",
  path: string,
  opts: { query?: Record<string, string>; body?: unknown; signal?: AbortSignal },
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (opts.signal?.aborted) return reject(abortError());
    const id = ++seq;
    const delay = LATENCY_MS[0] + Math.random() * (LATENCY_MS[1] - LATENCY_MS[0]);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onAbort = () => {
      pending.delete(id);
      clearTimeout(timer);
      reject(abortError());
    };
    opts.signal?.addEventListener("abort", onAbort, { once: true });
    pending.set(id, (msg) => {
      timer = setTimeout(() => {
        opts.signal?.removeEventListener("abort", onAbort);
        if (msg.ok) resolve(msg.data as T);
        else reject(new ApiError(msg.status, msg.code, msg.message));
      }, delay);
    });
    const message: MockRequestMessage = { id, method, path, query: opts.query, body: opts.body };
    getWorker().postMessage(message);
  });
}
