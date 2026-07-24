// Typed fetch wrappers for the JSON API. Same-origin `/api` in both dev (Vite proxy) and prod
// (FastAPI serves the built frontend). Types come from the generated `api-types`.

import type {
  Envelope,
  FieldError,
  PresetDetail,
  PresetSummary,
  RunAccepted,
  RunSnapshot,
  SolveErrors,
} from "./api-types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json() as Promise<T>;
}

export function listPresets(): Promise<PresetSummary[]> {
  return getJSON<PresetSummary[]>("/api/presets");
}

export function getPreset(name: string): Promise<PresetDetail> {
  return getJSON<PresetDetail>(`/api/presets/${encodeURIComponent(name)}`);
}

/** The outcome of a solve POST, discriminated by the server's status. */
export type SolveOutcome =
  | { ok: true; runId: string }
  | { ok: false; kind: "invalid"; errors: FieldError[] }
  | { ok: false; kind: "busy"; retryAfter: number | null }
  | { ok: false; kind: "error"; message: string };

/** Launch a solve. 202 → a run id (superseding any earlier one); 422 → field errors; 429 → capped. */
export async function solve(env: Envelope, clientId: string): Promise<SolveOutcome> {
  const res = await fetch("/api/solve", {
    method: "POST",
    headers: { "content-type": "application/json", "x-client-id": clientId },
    body: JSON.stringify(env),
  });
  if (res.status === 202) {
    const body = (await res.json()) as RunAccepted;
    return { ok: true, runId: body.run_id };
  }
  if (res.status === 422) {
    const body = (await res.json()) as SolveErrors;
    return { ok: false, kind: "invalid", errors: body.errors ?? [] };
  }
  if (res.status === 429) {
    const retry = res.headers.get("retry-after");
    return { ok: false, kind: "busy", retryAfter: retry ? Number(retry) : null };
  }
  return { ok: false, kind: "error", message: `Solve failed (${res.status}).` };
}

/** A run's status and, once done, its results. */
export function getRun(runId: string): Promise<RunSnapshot> {
  return getJSON<RunSnapshot>(`/api/runs/${encodeURIComponent(runId)}`);
}

/** Encode the current envelope to a share token (server-side codec). */
export async function createShare(env: Envelope): Promise<string> {
  const res = await fetch("/api/share", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(env),
  });
  if (!res.ok) throw new Error(`/api/share → ${res.status}`);
  const body = (await res.json()) as { token: string };
  return body.token;
}

/** Decode a share token back to an envelope; throws on a malformed/stale token (422). */
export function readShare(token: string): Promise<Envelope> {
  return getJSON<Envelope>(`/api/share/${encodeURIComponent(token)}`);
}
