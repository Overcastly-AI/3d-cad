/**
 * Draft view logic — the pure functions the DraftEditor + PartPage share, kept
 * out of the components so they unit-test without a DOM or a WebGL context (the
 * shell/datum twin; see `./shell`, `./datum`). Every shape comes from the
 * generated client (CLAUDE.md DRY rule); this module only assembles the request
 * from the form + the picked faces.
 *
 * A draft TAPERS the picked faces of the current body by a constant angle about
 * their intersection with a neutral (parting) plane — the mold-release
 * primitive. Two halves compose the params:
 *
 *  - the picked faces, reusing the SAME `{kind:"faces"}` `SubshapeRef` selector
 *    shell + sketch-on-face use, anchored on the prior body-affecting feature;
 *    unlike shell, an EMPTY pick has nothing to taper (`no_draft_faces`), so it
 *    is a submit-guard, never a valid selection;
 *  - the neutral plane, which reuses the datum offset-plane idiom exactly
 *    (base + signed offset + flip → `DraftNeutralPlaneV1`), so the pull
 *    direction is a deterministic function of its params (no picked geometry).
 *
 * SIGN CONVENTION (from the backend, measured against OCCT): a POSITIVE angle
 * tapers each face INWARD toward the pull — the top narrows (standard release);
 * a NEGATIVE angle tapers outward. Zero is a no-op, so the editor rejects it.
 */
import type {
  DraftNeutralPlane,
  DraftParams,
  PlanarFaceSignature,
} from "../api/parts";
import type { LengthUnit } from "@loft/design";

import { lengthInputValue } from "../units/length";
import type { DatumPlaneName } from "../sketch/plane";
import { parseOffsetMm } from "./datum";
import { faceSubshapeRef } from "./face";

/** The three origin datums the neutral plane can parallel, in a stable order. */
export const DRAFT_NEUTRAL_BASES: readonly {
  id: DatumPlaneName;
  label: string;
}[] = [
  { id: "XY", label: "XY" },
  { id: "XZ", label: "XZ" },
  { id: "YZ", label: "YZ" },
];

/** The editable neutral-plane sub-form (offset kept as raw text — a unit input). */
export interface DraftNeutralForm {
  base: DatumPlaneName;
  /** Signed offset along the base normal (mm), as typed. */
  offsetInput: string;
  /** Reverse the pull direction (negate the plane normal — the other mold half). */
  flip: boolean;
}

/**
 * The editable draft form. The angle is the parametric handle (kept as raw
 * text — a signed unit input); the picked faces live in the shared face-pick
 * store (the viewport overlay writes them), not here, so the form stays
 * serialisable (the shell pattern).
 */
export interface DraftForm {
  /** Signed draft angle in degrees, as typed (＋ inward toward pull). */
  angleInput: string;
  neutral: DraftNeutralForm;
}

/** The exclusive bound the backend enforces: -90 < angle < 90 (open interval). */
const ANGLE_LIMIT_DEG = 90;

/** Trim trailing zeros so 3 shows as "3", not "3.0"; -0 renders as "0". */
function formatNumber(value: number): string {
  return String(Object.is(value, -0) ? 0 : value);
}

/** The default new-draft form: a 3° taper about XY — the everyday release angle. */
export function defaultDraftForm(): DraftForm {
  return {
    angleInput: "3",
    neutral: { base: "XY", offsetInput: "0", flip: false },
  };
}

/** Seed the neutral sub-form from a persisted neutral plane (offset in `unit`). */
function neutralFormFrom(
  plane: DraftNeutralPlane,
  unit: LengthUnit,
): DraftNeutralForm {
  return {
    base: plane.base,
    offsetInput: lengthInputValue(plane.offset_mm, unit),
    flip: plane.flip,
  };
}

/** Seed the whole form from an existing draft feature for editing (in `unit`). */
export function formFromDraftParams(
  params: DraftParams,
  unit: LengthUnit,
): DraftForm {
  return {
    angleInput: formatNumber(params.angle_deg),
    neutral: neutralFormFrom(params.neutral_plane, unit),
  };
}

/** The picked-to-taper face signatures of a persisted draft (never empty). */
export function pickedFacesFromDraftParams(
  params: DraftParams,
): PlanarFaceSignature[] {
  return (params.faces.refs ?? []).map((ref) => ref.selector.signature);
}

/**
 * Parse the signed draft angle, or null when empty, non-numeric, or outside the
 * open interval (-90, 90) the kernel accepts. Zero parses (it is in range) but
 * is caught separately as a no-op — see `angleError`.
 */
export function parseAngleDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  if (value <= -ANGLE_LIMIT_DEG || value >= ANGLE_LIMIT_DEG) return null;
  return value;
}

/** Field-level angle message, or null when valid (empty is pending). */
export function angleError(input: string): string | null {
  if (input.trim() === "") return null;
  const value = parseAngleDeg(input);
  if (value === null) {
    return "Angle must be between −90 and 90 degrees.";
  }
  if (value === 0) return "A draft needs a non-zero angle to taper by.";
  return null;
}

/** Field-level neutral-plane offset message (any finite value is valid). */
export function neutralOffsetError(
  input: string,
  unit: LengthUnit,
): string | null {
  if (input.trim() === "") return null;
  return parseOffsetMm(input, unit) === null
    ? "Enter a distance (0, negative, or positive)."
    : null;
}

/**
 * Build the neutral plane from the sub-form, or null when the offset is
 * missing/invalid. Reuses the datum offset parser (DRY) — any finite offset is
 * a valid plane, so this only guards the shape.
 */
export function buildNeutralPlane(
  form: DraftNeutralForm,
  unit: LengthUnit,
): DraftNeutralPlane | null {
  const offset = parseOffsetMm(form.offsetInput, unit);
  if (offset === null) return null;
  return {
    kind: "datum",
    base: form.base,
    offset_mm: offset,
    flip: form.flip,
  };
}

/**
 * Build the `DraftParamsV1` from the form + the picked faces + the body anchor,
 * or null when any half is not yet valid: a missing/out-of-range/zero angle, an
 * invalid neutral offset, NO picked faces (a draft has nothing to taper —
 * `no_draft_faces`), or no body anchor to reference the faces from. Every picked
 * face becomes the SAME stage-1 `SubshapeRef` shell/on_face echo.
 */
export function buildDraftParams(
  form: DraftForm,
  pickedFaces: readonly PlanarFaceSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): DraftParams | null {
  const angle = parseAngleDeg(form.angleInput);
  if (angle === null || angle === 0) return null;
  if (pickedFaces.length === 0) return null;
  if (bodyFeatureId === null) return null;
  const neutral = buildNeutralPlane(form.neutral, unit);
  if (neutral === null) return null;
  return {
    angle_deg: angle,
    faces: {
      kind: "faces",
      refs: pickedFaces.map((signature) =>
        faceSubshapeRef(bodyFeatureId, signature),
      ),
    },
    neutral_plane: neutral,
  };
}

/** True when the draft form can be submitted (valid angle + faces + neutral). */
export function canSubmitDraft(
  form: DraftForm,
  pickedFaces: readonly PlanarFaceSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return buildDraftParams(form, pickedFaces, bodyFeatureId, unit) !== null;
}
