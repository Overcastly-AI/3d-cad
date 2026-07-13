/**
 * Shell view logic — the pure functions the ShellEditor + PartPage share, kept
 * out of the components so they unit-test without a DOM or a WebGL context (the
 * fillet/chamfer twin; see `./modify`). Every shape comes from the generated
 * client (CLAUDE.md DRY rule); this module only assembles the request from the
 * form + the picked-open face set.
 *
 * A shell hollows the current body chain to a uniform inward wall of
 * `thickness_mm` and REMOVES the picked faces, leaving those sides open. Unlike
 * a picked-edge fillet, an EMPTY face set is a valid, meaningful selection — a
 * fully sealed hollow (a closed cavity, no opening) — so the editor submits with
 * zero picks. Each picked face becomes the SAME stage-1 `SubshapeRef` the
 * sketch-on-face pick echoes, anchored on the prior body-affecting feature.
 */
import type {
  FaceSelector,
  PlanarFaceSignature,
  ShellParams,
} from "../api/parts";
import { faceSubshapeRef } from "./face";

/**
 * The editable shell form — the thickness kept as raw text (a unit input). The
 * picked-open face signatures live in the face-pick store (the viewport overlay
 * writes them), not here, so the form stays serialisable (the fillet pattern).
 */
export interface ShellForm {
  thicknessInput: string;
}

/** Trim trailing zeros so 2 shows as "2", not "2.000"; -0 renders as "0". */
function formatMm(mm: number): string {
  return String(Object.is(mm, -0) ? 0 : mm);
}

/**
 * Parse a positive-millimetre thickness field, or null when empty, non-numeric,
 * or non-positive (a zero-thickness shell is no wall).
 */
export function parseThicknessMm(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

/** The default new-shell form: a 2 mm wall — the common enclosure thickness. */
export function defaultShellForm(): ShellForm {
  return { thicknessInput: "2" };
}

/** Seed the form from an existing shell feature for editing. */
export function formFromShellParams(params: ShellParams): ShellForm {
  return { thicknessInput: formatMm(params.thickness_mm) };
}

/** The picked-open face signatures of a persisted shell (empty = a sealed hollow). */
export function pickedFacesFromShellParams(
  params: ShellParams,
): PlanarFaceSignature[] {
  return (params.faces.refs ?? []).map((ref) => ref.selector.signature);
}

/** Field-level thickness message, or null when valid (empty is pending). */
export function thicknessError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseThicknessMm(input) === null
    ? "Thickness must be a positive number of millimetres."
    : null;
}

/**
 * The `{kind:"faces"}` open-face selector from the anchor feature + the chosen
 * signatures. An empty set is VALID (a sealed hollow, no opening) so it never
 * returns null for zero picks — unlike the picked-EDGE selector. Returns null
 * ONLY when faces are picked but there is no body anchor to reference them from
 * (a shell always follows a body, so this is the defensive guard, not a path).
 */
export function facesSelector(
  featureId: string | null,
  signatures: readonly PlanarFaceSignature[],
): FaceSelector | null {
  if (signatures.length === 0) return { kind: "faces", refs: [] };
  if (featureId === null) return null;
  return {
    kind: "faces",
    refs: signatures.map((signature) => faceSubshapeRef(featureId, signature)),
  };
}

/**
 * Build the `ShellParamsV1` from the form + the picked-open signatures, or null
 * when the thickness is invalid OR faces are picked without a body anchor. An
 * empty face set builds a valid sealed-hollow shell.
 */
export function buildShellParams(
  form: ShellForm,
  pickedFaces: readonly PlanarFaceSignature[],
  bodyFeatureId: string | null,
): ShellParams | null {
  const thickness = parseThicknessMm(form.thicknessInput);
  if (thickness === null) return null;
  const faces = facesSelector(bodyFeatureId, pickedFaces);
  if (faces === null) return null;
  return { thickness_mm: thickness, faces };
}

/** True when the shell form can be submitted (valid thickness + resolvable faces). */
export function canSubmitShell(
  form: ShellForm,
  pickedFaces: readonly PlanarFaceSignature[],
  bodyFeatureId: string | null,
): boolean {
  return buildShellParams(form, pickedFaces, bodyFeatureId) !== null;
}
