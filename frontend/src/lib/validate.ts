// Client-side field validation, from the same spec the server validates against.
//
// This is a *responsiveness* layer, never the authority: the server re-checks every submitted
// value in `validate_edits`. What it buys is telling the user about an empty or out-of-range
// input as they type, and refusing to POST a submission that is already known to be invalid —
// an empty number input binds to `null`, which the server can only reject as a malformed body,
// which is a poor way to learn you left a box blank.
//
// HTML `min`/`max` cannot express a strict bound, so the exclusivity carried on `Bound` is
// applied here rather than left to the browser.

import type { ComponentSpec, FieldSpec } from "./api-types";

/** The problem with `value` under `field`, or null if there is none. */
export function fieldError(
  field: FieldSpec,
  value: number | null | undefined,
): string | null {
  if (field.kind !== "number") return null; // not editable, so nothing to submit
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Enter a number.";
  }
  if (!Number.isFinite(value)) return "Enter a finite number.";
  const low = field.min;
  if (low && !(low.exclusive ? value > low.value : value >= low.value)) {
    return `Must be ${low.exclusive ? "greater than" : "at least"} ${low.value}.`;
  }
  const high = field.max;
  if (high && !(high.exclusive ? value < high.value : value <= high.value)) {
    return `Must be ${high.exclusive ? "less than" : "at most"} ${high.value}.`;
  }
  return null;
}

/**
 * Every current field problem, keyed by spec path.
 *
 * Disabled components are included: their values still travel in the overlay, so an invalid
 * one still fails the POST.
 */
export function formErrors(
  form: ComponentSpec[],
  values: Record<string, number>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const component of form) {
    for (const field of component.params) {
      const problem = fieldError(field, values[field.path]);
      if (problem) errors[field.path] = problem;
    }
  }
  return errors;
}
