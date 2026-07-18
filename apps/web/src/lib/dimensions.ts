/** Keyboard-first dimension entry: parsing + validation (unit: mm). */
import type { BoxParams } from "../api/tessellate";

export const AXES = ["x", "y", "z"] as const;
export type Axis = (typeof AXES)[number];

/** Upper bound keeps the first-light box in a sane envelope (mm). */
export const DIMENSION_MAX_MM = 10_000;

export type DimensionDraft = Record<Axis, string>;
export type DimensionErrors = Partial<Record<Axis, string>>;

export type DimensionParse =
  { ok: true; value: number } | { ok: false; error: string };

/** Parse one dimension entry. Positive, finite, ≤ 10 000 mm. */
export function parseDimension(raw: string): DimensionParse {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, error: "Enter a dimension" };
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value)) {
    return { ok: false, error: "Enter a number" };
  }
  if (value <= 0) {
    return { ok: false, error: "Enter a value above 0 mm" };
  }
  if (value > DIMENSION_MAX_MM) {
    return { ok: false, error: "Keep it at or under 10 000 mm" };
  }
  return { ok: true, value };
}

export type DimensionValidation =
  { ok: true; values: BoxParams } | { ok: false; errors: DimensionErrors };

/** Validate a full x/y/z draft into typed box params. */
export function validateDimensions(draft: DimensionDraft): DimensionValidation {
  const errors: DimensionErrors = {};
  const values: Partial<BoxParams> = {};
  for (const axis of AXES) {
    const parsed = parseDimension(draft[axis]);
    if (parsed.ok) {
      values[axis] = parsed.value;
    } else {
      errors[axis] = parsed.error;
    }
  }
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, values: values as BoxParams };
}
