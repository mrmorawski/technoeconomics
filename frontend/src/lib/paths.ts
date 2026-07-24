// Id-rooted path resolution against a plant dict, and the overlay diff. The first path segment
// is a component id (looked up in the plant's `components` list); the rest are mapping keys.
// `grid.price.mean` ⇒ components[id=="grid"]["price"]["mean"]. This mirrors the server's rule
// so the client's overlay paths line up with the spec exactly.

import type { ComponentSpec } from "./api-types";

/** The serialised plant is an opaque document addressed by spec paths, not a typed structure. */
export type PlantDict = Record<string, unknown>;

function components(plant: PlantDict): Record<string, unknown>[] {
  const list = plant["components"];
  if (!Array.isArray(list)) return [];
  return list.filter((c): c is Record<string, unknown> => typeof c === "object" && c !== null);
}

/** Read the number at an id-rooted `path`, or `undefined` if it does not resolve to one. */
export function resolveNumber(plant: PlantDict, path: string): number | undefined {
  const [cid, ...rest] = path.split(".");
  let node: unknown = components(plant).find((c) => c["id"] === cid);
  for (const key of rest) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return typeof node === "number" ? node : undefined;
}

/** The default value at every spec path, read out of the preset's default plant dict. */
export function defaultValues(plant: PlantDict, form: ComponentSpec[]): Record<string, number> {
  const values: Record<string, number> = {};
  for (const component of form) {
    for (const field of component.params) {
      const v = resolveNumber(plant, field.path);
      if (v !== undefined) values[field.path] = v;
    }
  }
  return values;
}

/** The default enabled flag per component, from the spec. */
export function defaultEnabled(form: ComponentSpec[]): Record<string, boolean> {
  return Object.fromEntries(form.map((c) => [c.id, c.enabled]));
}

/** Only the values that differ from their defaults — the sparse overlay sent to the server. */
export function overlayDiff(
  values: Record<string, number>,
  defaults: Record<string, number>,
): Record<string, number> {
  const overlay: Record<string, number> = {};
  for (const [path, value] of Object.entries(values)) {
    if (value !== defaults[path]) overlay[path] = value;
  }
  return overlay;
}

/** Only the toggles that differ from their defaults. */
export function enabledDiff(
  enabled: Record<string, boolean>,
  defaults: Record<string, boolean>,
): Record<string, boolean> {
  const diff: Record<string, boolean> = {};
  for (const [id, value] of Object.entries(enabled)) {
    if (value !== defaults[id]) diff[id] = value;
  }
  return diff;
}
