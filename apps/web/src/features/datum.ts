/**
 * Datum-plane view logic — the pure functions the datum authoring surfaces
 * (the standalone DatumEditor and the inline "+ Offset plane" affordance in
 * the plane picker) share, kept out of the components so they can be
 * unit-tested without a DOM. Param shapes come from the generated client
 * (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * A v1 datum plane is offset-from-an-origin-datum by a SIGNED distance, plus an
 * optional normal flip (docs/design/datum-planes.md §3). `base` is one of the
 * three origin datums; `offset_mm` slides the plane along that datum's normal
 * (0 coincides with the origin datum, +/- selects the side); `flip` reverses
 * the normal. Any FINITE offset is a valid plane (the feature is total), so the
 * only invalid input is a non-numeric field.
 */
import type { DatumParams } from "../api/parts";
import type { DatumPlaneName } from "../sketch/plane";

/** The three origin datums a plane can parallel, in a stable order. */
export const DATUM_BASES: readonly { id: DatumPlaneName; label: string }[] = [
  { id: "XY", label: "XY" },
  { id: "XZ", label: "XZ" },
  { id: "YZ", label: "YZ" },
];

/** The editable datum form (offset kept as raw text — a unit input). */
export interface DatumForm {
  base: DatumPlaneName;
  /** Signed offset along the base normal (mm), as typed. */
  offsetInput: string;
  /** Reverse the plane normal (negate z_dir; +u unchanged, +v flips). */
  flip: boolean;
}

/** The default new-datum form: 30 mm above XY (the everyday "sketch up" case). */
export function defaultDatumForm(): DatumForm {
  return { base: "XY", offsetInput: "30", flip: false };
}

/** Trim trailing zeros so 30 shows as "30"; -0 renders as "0". */
function formatMm(mm: number): string {
  return String(Object.is(mm, -0) ? 0 : mm);
}

/** Seed the form from an existing datum feature for editing. */
export function formFromDatumParams(params: DatumParams): DatumForm {
  return {
    base: params.base,
    offsetInput: formatMm(params.offset_mm),
    flip: params.flip,
  };
}

/**
 * Parse the offset field. Any FINITE millimetre value is valid (0 coincides
 * with the origin datum; negatives select the other side) — only an empty or
 * non-numeric field is not-yet-valid.
 */
export function parseOffsetMm(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** Field-level offset message, or null when valid (empty is pending). */
export function offsetError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseOffsetMm(input) === null
    ? "Enter a distance in millimetres (0, negative, or positive)."
    : null;
}

/**
 * Build the `DatumParamsV1` from the form, or null when the offset is
 * missing/invalid (the submit gate). Server-side rebuild is total for any
 * finite offset — this only guards the shape.
 */
export function buildDatumParams(form: DatumForm): DatumParams | null {
  const offset = parseOffsetMm(form.offsetInput);
  if (offset === null) return null;
  return { base: form.base, offset_mm: offset, flip: form.flip };
}

/** True when the form can be submitted (offset present + finite). */
export function canSubmitDatum(form: DatumForm): boolean {
  return buildDatumParams(form) !== null;
}
