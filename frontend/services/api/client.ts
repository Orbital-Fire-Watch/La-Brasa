/**
 * The one place for HTTP: base URL, timeout, JSON, and turning failures into ApiError.
 * In mock mode the same calls go to the in-browser mock API instead of the network.
 */
import { CONFIG } from "../../lib/config";
import { mockRequest } from "../mock/mockClient";
import { ApiError } from "./errors";
import type { ErrorCode, ErrorResponse, paths } from "./types";

export type Query = Record<string, string | number | boolean | null | undefined>;

function toSearchParams(query: Query | undefined): URLSearchParams {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) if (v !== null && v !== undefined) q.set(k, String(v));
  return q;
}

export function apiUrl(path: string, query?: Query): string {
  const q = toSearchParams(query).toString();
  return `${CONFIG.apiBaseUrl}${path}${q ? `?${q}` : ""}`;
}

function withTimeout(signal: AbortSignal | undefined): { signal: AbortSignal; done: () => void } {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(new DOMException("Timeout", "TimeoutError")), CONFIG.requestTimeoutMs);
  const onAbort = () => ctrl.abort(signal?.reason);
  signal?.addEventListener("abort", onAbort, { once: true });
  return {
    signal: ctrl.signal,
    done: () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    },
  };
}

export async function apiRequest<T>(
  method: "GET" | "POST",
  path: string,
  opts: { query?: Query; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  if (CONFIG.apiMode === "mock") {
    const query = Object.fromEntries(toSearchParams(opts.query));
    return mockRequest<T>(method, path, { query, body: opts.body, signal: opts.signal });
  }
  const { signal, done } = withTimeout(opts.signal);
  try {
    const res = await fetch(apiUrl(path, opts.query), {
      method,
      signal,
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
    const text = await res.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = null;
    }
    if (!res.ok) {
      const err = (body as Partial<ErrorResponse> | null)?.error;
      const code: ErrorCode = err?.code ?? (res.status === 504 ? "QUERY_TIMEOUT" : "INTERNAL_ERROR");
      throw new ApiError(res.status, code, err?.message ?? res.statusText);
    }
    return body as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError" && signal.reason instanceof DOMException && signal.reason.name === "TimeoutError") {
      throw new ApiError(504, "QUERY_TIMEOUT", "The request timed out.");
    }
    throw e;
  } finally {
    done();
  }
}

type PostPath = { [P in keyof paths]: paths[P] extends { post: object } ? P : never }[keyof paths];
export type PostBody<P extends PostPath> = paths[P] extends {
  post: { requestBody: { content: { "application/json": infer B } } };
}
  ? B
  : never;
export type PostOk<P extends PostPath> = paths[P] extends {
  post: { responses: { 200: { content: { "application/json": infer R } } } };
}
  ? R
  : never;

/** Type-checked POST: path, body and response must match the specification. */
export function apiPost<P extends PostPath>(path: P, body: PostBody<P>, signal?: AbortSignal): Promise<PostOk<P>> {
  return apiRequest<PostOk<P>>("POST", path, { body, signal });
}
