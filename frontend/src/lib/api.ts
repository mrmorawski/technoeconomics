// Typed fetch wrappers for the JSON API. Same-origin `/api` in both dev (Vite proxy) and prod
// (FastAPI serves the built frontend). Solve and the run resource live in 3b.

import type { Envelope, PresetDetail, PresetSummary } from "./api-types";

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
