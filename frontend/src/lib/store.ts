// Client-owned state in localStorage: the single-flight client id, and the sparse overlay of
// user edits persisted per preset. The overlay is always the diff against the preset default,
// so it survives schema bumps and picks up improved defaults; a `specHash` mismatch (paths,
// units, or kinds changed) drops the stored edits wholesale rather than reinterpreting a value.

import type { ComponentSpec } from "./api-types";

const CLIENT_ID_KEY = "technoeconomics.clientId";
const editsKey = (preset: string) => `technoeconomics.edits.${preset}`;

/** A stable per-browser id (minted once), sent as `X-Client-Id` for solve single-flight. */
export function clientId(): string {
  let id = localStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

/** A hash of the spec's shape (paths, units, kinds) — changes invalidate stored edits. */
export function specHash(form: ComponentSpec[]): string {
  const shape = form.flatMap((c) =>
    c.params.map((f) => `${f.path}|${f.unit ?? ""}|${f.kind}`),
  );
  let h = 2166136261; // FNV-1a
  for (const ch of shape.join("\n")) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(36);
}

export interface StoredEdits {
  overlay: Record<string, number>;
  enabled: Record<string, boolean>;
}

/** Restore stored edits for `preset` if the spec still matches; otherwise nothing. */
export function loadEdits(preset: string, hash: string): StoredEdits | null {
  const raw = localStorage.getItem(editsKey(preset));
  if (!raw) return null;
  try {
    const stored = JSON.parse(raw) as { specHash?: string } & StoredEdits;
    if (stored.specHash !== hash) return null; // reinterpretation guard: drop wholesale
    return { overlay: stored.overlay ?? {}, enabled: stored.enabled ?? {} };
  } catch {
    return null;
  }
}

/** Persist the current edits (as diffs) for `preset`, tagged with the spec hash. */
export function saveEdits(preset: string, hash: string, edits: StoredEdits): void {
  localStorage.setItem(editsKey(preset), JSON.stringify({ specHash: hash, ...edits }));
}
