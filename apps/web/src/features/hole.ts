/**
 * Hole-feature view logic — the pure functions the HoleEditor and PartPage
 * share, kept out of the components so they can be unit-tested without a DOM or
 * a WebGL context. Param shapes come from the generated client (CLAUDE.md DRY
 * rule); the builders live in `../api/parts`.
 *
 * A hole (design §7.6, the shell/draft sibling) drills a straight cylinder of
 * `diameter_mm` into the current body at a `position` on a picked planar
 * `face`, through-all or blind. The placement face is authored by clicking the
 * highlighted face in the viewport (`FacePickOverlay`) — the SAME stage-1
 * `PlanarFaceSignature` the sketch-on-face / on_face datum flows echo, reduced
 * to a `SubshapeRef` by {@link faceSubshapeRef} (one enumeration, pick side and
 * resolve side). The position is a WORLD-space point ON that face, picked from
 * the same DOM-in-canvas point affordance the measure overlay uses; the geometry
 * service projects it onto the face plane to fix the drill axis, so the only
 * shape the client guards is "a face, a point, a positive diameter, and — when
 * blind — a positive depth". Off-body / too-deep / unresolved-face are per-
 * feature REBUILD errors surfaced in the tree (see `./featureErrors`).
 */
import { formatLength, type LengthUnit } from "@loft/design";

import type { HoleParams, PlanarFaceSignature, Vec3 } from "../api/parts";
import { faceSubshapeRef } from "./face";
import { lengthInputValue, parsePositiveLengthMm } from "../units/length";
import {
  boreFitsThread,
  coarsePitchFor,
  DEFAULT_THREAD_NOMINAL_MM,
  DEFAULT_THREAD_PITCH_MM,
  formatDesignation,
  formatThreadNumber,
  isSupportedDesignation,
  pitchesFor,
  tapDrillMm,
} from "./thread";

/** Through-all cuts fully through; blind drills a finite pocket depth. */
export type HoleDepthMode = "through_all" | "blind";

/**
 * The recess at the mouth of the bore: a plain bore (`simple`), a larger coaxial
 * CYLINDER (`counterbore`, seats a socket-head cap screw), or a coaxial CONE
 * (`countersink`, seats a flat-head screw). Discriminates the generated
 * `HoleParamsV1.type` (`kind`), which defaults to `simple` when omitted — so a
 * slice-1 hole with no `type` still edits as a simple hole (backward-compatible).
 */
export type HoleTypeKind = "simple" | "counterbore" | "countersink";

/**
 * The flat-head fastener included-angle standards the countersink offers as
 * one-click presets. The angle is otherwise free within the open interval the
 * kernel accepts (0, 180); 82° (imperial) and 90° (metric) cover the everyday
 * screws, so the editor surfaces them as chips beside the free angle field.
 */
export const CSINK_STANDARD_ANGLES = [82, 90] as const;

/** Open interval the backend accepts for the countersink included angle. */
const CSINK_ANGLE_MIN_DEG = 0;
const CSINK_ANGLE_MAX_DEG = 180;

/**
 * A picked planar model face, as the hole editor carries it: the full-precision
 * stage-1 `signature` (the resolve identity — never quantized) plus the id of
 * the body-affecting feature whose body owns the face (the `SubshapeRef` anchor,
 * the strict-backward dependency the write records). Mirrors the datum editor's
 * `DatumFace`. The face's own `signature.centroid` is a world point guaranteed
 * ON the face, so it seeds the drill position (the everyday "hole in the middle"
 * default) the point pick then refines.
 */
export interface HoleFace {
  signature: PlanarFaceSignature;
  anchorId: string;
}

/** Which viewport pick the hole editor has armed: the face, or a point on it. */
export type HolePickTarget = "face" | "point";

/**
 * A face delivered from the viewport pick into the editor, tagged with a
 * monotonic `nonce` so the editor folds each pick EXACTLY once (the same
 * nonce-guard the datum face pick + the sketch edit/offset effects use).
 */
export interface HoleFacePick {
  nonce: number;
  face: HoleFace;
}

/** A point delivered from the viewport pick into the editor (nonce-guarded). */
export interface HolePointPick {
  nonce: number;
  position: Vec3;
}

/** The editor's live face + position, mirrored up so the parent can draw the
 * point-pick overlay ON the chosen face (the edge-flange span / relief-bend
 * mirror-up pattern). */
export interface HolePreview {
  signature: PlanarFaceSignature | null;
  position: Vec3 | null;
}

/**
 * The editable hole form (diameter/depth kept as raw text — unit inputs). The
 * face + world position are picked in the viewport; both null until chosen.
 */
export interface HoleForm {
  /** The picked planar placement face, or null until one is picked. */
  face: HoleFace | null;
  /** The world-space drill point ON the face (mm), or null until a face is picked. */
  position: Vec3 | null;
  /** Hole diameter (mm), as typed. */
  diameterInput: string;
  /** Through-all, or a blind pocket. */
  depthMode: HoleDepthMode;
  /** Blind pocket depth (mm), as typed — only read when `depthMode === "blind"`. */
  depthInput: string;
  /** Plain bore, counterbore, or countersink — the recess at the face. */
  typeKind: HoleTypeKind;
  /** Counterbore recess diameter (mm), as typed — read when `typeKind === "counterbore"`. */
  cboreDiameterInput: string;
  /** Counterbore recess depth (mm), as typed — read when `typeKind === "counterbore"`. */
  cboreDepthInput: string;
  /** Countersink mouth diameter (mm), as typed — read when `typeKind === "countersink"`. */
  csinkDiameterInput: string;
  /** Countersink included angle (deg), as typed — read when `typeKind === "countersink"`. */
  csinkAngleInput: string;
  /**
   * The hole is TAPPED — it carries a thread callout. ORTHOGONAL to `typeKind`
   * (a counterbored tapped hole is one feature, and the wire says so: `thread`
   * is a sibling of `type`, not a fourth member of it), so this is a toggle, not
   * a segment.
   */
  tapped: boolean;
  /**
   * Nominal (major) thread diameter (mm) — the `M` number. Chosen from the ISO
   * 261 series, so it is a number, not typed text: there is no parse to fail.
   * Metric BY DEFINITION — never converted to the document unit, because an
   * M10x1.5 in an inch drawing is still an M10x1.5.
   */
  threadNominalMm: number;
  /** Thread pitch (mm) — one of that nominal's standard pitches, coarse first. */
  threadPitchMm: number;
}

/**
 * The default new-hole form: a Ø6 through-all simple hole — the common first
 * bolt hole. The recess fields carry ready M6-scale defaults (an ~Ø11 cbore, an
 * ~Ø12 90° csink) so switching type is one click, not four fields to fill.
 */
export function defaultHoleForm(): HoleForm {
  return {
    face: null,
    position: null,
    diameterInput: "6",
    depthMode: "through_all",
    depthInput: "10",
    typeKind: "simple",
    cboreDiameterInput: "11",
    cboreDepthInput: "6",
    csinkDiameterInput: "12",
    csinkAngleInput: "90",
    tapped: false,
    threadNominalMm: DEFAULT_THREAD_NOMINAL_MM,
    threadPitchMm: DEFAULT_THREAD_PITCH_MM,
  };
}

/** Seed the form from an existing hole feature for editing (lengths in `unit`). */
export function formFromHoleParams(
  params: HoleParams,
  unit: LengthUnit,
): HoleForm {
  const depth = params.depth;
  const type = params.type;
  const thread = params.thread;
  const base = defaultHoleForm();
  return {
    face: {
      signature: params.face.selector.signature,
      anchorId: params.face.feature_id,
    },
    position: params.position,
    diameterInput: lengthInputValue(params.diameter_mm, unit),
    depthMode: depth.kind === "blind" ? "blind" : "through_all",
    depthInput:
      depth.kind === "blind" ? lengthInputValue(depth.depth_mm, unit) : "10",
    // `type` is optional on the wire and DEFAULTS to simple — a slice-1 hole
    // with no `type` seeds a simple form (backward-compatible).
    typeKind: type?.kind ?? "simple",
    cboreDiameterInput:
      type?.kind === "counterbore"
        ? lengthInputValue(type.cbore_diameter_mm, unit)
        : base.cboreDiameterInput,
    cboreDepthInput:
      type?.kind === "counterbore"
        ? lengthInputValue(type.cbore_depth_mm, unit)
        : base.cboreDepthInput,
    csinkDiameterInput:
      type?.kind === "countersink"
        ? lengthInputValue(type.csink_diameter_mm, unit)
        : base.csinkDiameterInput,
    csinkAngleInput:
      type?.kind === "countersink"
        ? formatAngle(type.csink_angle_deg)
        : base.csinkAngleInput,
    // `thread` is optional AND nullable on the wire; absent/null = untapped, so
    // an existing untapped hole seeds the default (unticked) M6x1 designation
    // and edits byte-identically. A stored designation is adopted VERBATIM —
    // including one this client's table doesn't list — so a hole authored
    // through the API is shown honestly and can be repaired, not silently
    // rewritten to something the user never chose.
    tapped: thread != null,
    threadNominalMm: thread?.nominal_diameter_mm ?? base.threadNominalMm,
    threadPitchMm: thread?.pitch_mm ?? base.threadPitchMm,
  };
}

/** A countersink angle rendered without a unit suffix (the cell shows `°`). */
function formatAngle(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

/**
 * Fold a picked face into the form: adopt the face AND seed the drill position
 * to its centroid (a point guaranteed on the face), so the form is immediately
 * submittable and the point pick only REFINES the placement.
 */
export function applyHoleFace(form: HoleForm, face: HoleFace): HoleForm {
  return { ...form, face, position: face.signature.centroid };
}

/** Fold a picked world point into the form as the drill position. */
export function applyHolePosition(form: HoleForm, position: Vec3): HoleForm {
  return { ...form, position };
}

/** Field-level diameter message, or null when valid (empty is pending). */
export function diameterError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Diameter must be a positive length."
    : null;
}

/** Field-level blind-depth message, or null when valid (empty is pending). */
export function depthError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Depth must be a positive length."
    : null;
}

/**
 * Field-level recess-diameter message, or null when valid (empty is pending).
 * The recess (counterbore / countersink) mouth must be a positive length AND
 * strictly exceed the bore — a recess no wider than the hole is no recess (the
 * backend's `hole_cbore_invalid` / `hole_csink_invalid` precondition, guarded
 * client-side so the modeler gets it before a round-trip).
 */
export function recessDiameterError(
  recessInput: string,
  boreInput: string,
  unit: LengthUnit,
): string | null {
  if (recessInput.trim() === "") return null;
  const recess = parsePositiveLengthMm(recessInput, unit);
  if (recess === null) return "Diameter must be a positive length.";
  const bore = parsePositiveLengthMm(boreInput, unit);
  if (bore !== null && recess <= bore) {
    return `Must be wider than the Ø${formatLength(bore, unit)} bore.`;
  }
  return null;
}

/** Parse the countersink included angle → degrees, or null when empty/out of (0, 180). */
export function parseCsinkAngleDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  if (value <= CSINK_ANGLE_MIN_DEG || value >= CSINK_ANGLE_MAX_DEG) return null;
  return value;
}

/** Field-level countersink-angle message, or null when valid (empty is pending). */
export function csinkAngleError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseCsinkAngleDeg(input) === null
    ? "Angle must be between 0 and 180 degrees."
    : null;
}

// ---------------------------------------------------------------------------
// Tapped hole — the thread callout (`thread`, a SIBLING of `type` on the wire).
//
// The kernel cuts the tap-drill bore and nothing else, so the drilled diameter
// and the callout must agree or the part is silently wrong. The editor DERIVES
// the bore from the chosen designation (`D - P`, the published tap drill) rather
// than locking it: a shop's rounded stock drill (6.8 for M8x1.25) is a real tap
// drill, and the kernel accepts the whole band `[minor, nominal)`.
// ---------------------------------------------------------------------------

/** The designation a form's thread selection spells — `M10x1.5`. */
export function threadDesignation(form: HoleForm): string {
  return formatDesignation(form.threadNominalMm, form.threadPitchMm);
}

/** The ISO tap drill (mm) for a form's designation — the derived bore. */
export function threadTapDrillMm(form: HoleForm): number {
  return tapDrillMm(form.threadNominalMm, form.threadPitchMm);
}

/** The tap drill as the bore field would spell it, in the document unit. */
export function tapDrillInputValue(form: HoleForm, unit: LengthUnit): string {
  return lengthInputValue(threadTapDrillMm(form), unit);
}

/**
 * Adopt the ISO tap drill as the bore — the "Tap drill" chip's action, and the
 * fill every designation change performs so the two typed thread errors are
 * unreachable by accident.
 */
export function applyTapDrill(form: HoleForm, unit: LengthUnit): HoleForm {
  return { ...form, diameterInput: tapDrillInputValue(form, unit) };
}

/** True when the authored bore already IS the derived tap drill (chip state). */
export function boreIsTapDrill(form: HoleForm, unit: LengthUnit): boolean {
  const bore = parsePositiveLengthMm(form.diameterInput, unit);
  return bore !== null && Math.abs(bore - threadTapDrillMm(form)) <= 1e-6;
}

/**
 * Tick/untick Tapped. Ticking derives the bore from the designation (the tap
 * drill); unticking leaves the bore alone — the drilled size the user has is a
 * perfectly good plain hole, and silently resizing it would edit geometry the
 * user didn't touch.
 */
export function applyTapped(
  form: HoleForm,
  tapped: boolean,
  unit: LengthUnit,
): HoleForm {
  const next = { ...form, tapped };
  return tapped ? applyTapDrill(next, unit) : next;
}

/**
 * Choose a nominal size. The pitch resets to that size's COARSE pitch (what a
 * shop taps unless a drawing says otherwise) — which also keeps the pair a real
 * ISO combination, since a fine pitch of the old size may not exist for the new
 * one. Unknown sizes keep the current pitch so an off-series stored designation
 * survives until the user picks a listed one.
 */
export function applyThreadNominal(
  form: HoleForm,
  nominalMm: number,
  unit: LengthUnit,
): HoleForm {
  const pitch = coarsePitchFor(nominalMm) ?? form.threadPitchMm;
  return applyTapDrill(
    { ...form, threadNominalMm: nominalMm, threadPitchMm: pitch },
    unit,
  );
}

/** Choose a pitch for the current size, re-deriving the bore. */
export function applyThreadPitch(
  form: HoleForm,
  pitchMm: number,
  unit: LengthUnit,
): HoleForm {
  return applyTapDrill({ ...form, threadPitchMm: pitchMm }, unit);
}

/**
 * Field-level message when the nominal SIZE is off the ISO 261 series, or null.
 * Unreachable from the size picker (it only lists real sizes) — it fires for a
 * designation authored elsewhere (API/script/import) and opened for edit, which
 * is exactly the `hole_thread_unsupported` case, caught before the round-trip.
 */
export function threadSizeError(form: HoleForm): string | null {
  if (!form.tapped) return null;
  return pitchesFor(form.threadNominalMm).length > 0
    ? null
    : `M${formatThreadNumber(form.threadNominalMm)} isn't a standard ISO size. Choose a listed size.`;
}

/**
 * Field-level message when the PITCH isn't standard for the chosen size, or
 * null — the other half of `hole_thread_unsupported`. Names the pitches that
 * size IS standardised at, coarse first, the way the server's message does.
 */
export function threadPitchError(form: HoleForm): string | null {
  if (!form.tapped) return null;
  const pitches = pitchesFor(form.threadNominalMm);
  // No pitches at all means the SIZE is wrong; that message owns the failure.
  if (pitches.length === 0) return null;
  if (isSupportedDesignation(form.threadNominalMm, form.threadPitchMm)) {
    return null;
  }
  const offered = pitches.map(formatThreadNumber).join(", ");
  return `M${formatThreadNumber(form.threadNominalMm)} is standardised at ${offered} mm. Choose a listed pitch.`;
}

/**
 * Field-level message when the bore can't be tapped to the chosen designation,
 * or null (empty is pending). Mirrors the kernel's `[minor, nominal)` band, so
 * the modeler learns before the round-trip what `hole_thread_mismatch` would
 * tell them after it. Names the direction of the miss and the fix.
 */
export function threadBoreError(
  form: HoleForm,
  unit: LengthUnit,
): string | null {
  if (!form.tapped) return null;
  if (!isSupportedDesignation(form.threadNominalMm, form.threadPitchMm)) {
    // The designation itself is the problem — the size/pitch field says so; a
    // second message on the bore would just be noise.
    return null;
  }
  const bore = parsePositiveLengthMm(form.diameterInput, unit);
  if (bore === null) return null;
  if (boreFitsThread(form.threadNominalMm, form.threadPitchMm, bore)) {
    return null;
  }
  const designation = threadDesignation(form);
  const drill = formatLength(threadTapDrillMm(form), unit);
  return bore < form.threadNominalMm
    ? `Too small to tap ${designation} — use the Ø${drill} tap drill.`
    : `Too wide to tap ${designation} — use the Ø${drill} tap drill.`;
}

/**
 * The thread designation an EXISTING hole feature carries, or null when it is
 * untapped. A tapped hole's solid is byte-identical to its bore, so this string
 * is the only place tapped-ness exists for the user: the feature tree reads it.
 */
export function holeThreadDesignation(params: HoleParams): string | null {
  const thread = params.thread;
  return thread == null
    ? null
    : formatDesignation(thread.nominal_diameter_mm, thread.pitch_mm);
}

/**
 * Build the hole params from the form, or null when a required field is
 * missing/invalid (the submit gate). Server-side rebuild resolves the face and
 * projects the point — this only guards the shape: a face, a point, a positive
 * diameter, and (when blind) a positive depth.
 */
export function buildHoleParams(
  form: HoleForm,
  unit: LengthUnit,
): HoleParams | null {
  if (form.face === null || form.position === null) return null;
  const diameter = parsePositiveLengthMm(form.diameterInput, unit);
  if (diameter === null) return null;

  let depth: HoleParams["depth"];
  if (form.depthMode === "blind") {
    const depthMm = parsePositiveLengthMm(form.depthInput, unit);
    if (depthMm === null) return null;
    depth = { kind: "blind", depth_mm: depthMm };
  } else {
    depth = { kind: "through_all" };
  }

  // The recess type. `simple` OMITS `type` on the wire (the schema default), so
  // a simple hole is byte-identical to a slice-1 hole (backward-compatible); a
  // recess whose mouth doesn't exceed the bore fails the client guard (null).
  let type: HoleParams["type"] | undefined;
  if (form.typeKind === "counterbore") {
    const cboreDia = parsePositiveLengthMm(form.cboreDiameterInput, unit);
    const cboreDepth = parsePositiveLengthMm(form.cboreDepthInput, unit);
    if (cboreDia === null || cboreDepth === null || cboreDia <= diameter) {
      return null;
    }
    type = {
      kind: "counterbore",
      cbore_diameter_mm: cboreDia,
      cbore_depth_mm: cboreDepth,
    };
  } else if (form.typeKind === "countersink") {
    const csinkDia = parsePositiveLengthMm(form.csinkDiameterInput, unit);
    const csinkAngle = parseCsinkAngleDeg(form.csinkAngleInput);
    if (csinkDia === null || csinkAngle === null || csinkDia <= diameter) {
      return null;
    }
    type = {
      kind: "countersink",
      csink_diameter_mm: csinkDia,
      csink_angle_deg: csinkAngle,
    };
  }

  // The thread callout. Untapped OMITS `thread` entirely, so an untapped hole's
  // wire is byte-identical to a pre-tapped-holes one. A designation the kernel
  // can't honour, or a bore it can't be tapped in, are both blocked here (the
  // same client-guard posture the recess uses) — they'd otherwise come back as
  // `hole_thread_unsupported` / `hole_thread_mismatch` with no body built.
  let thread: HoleParams["thread"] | undefined;
  if (form.tapped) {
    if (!isSupportedDesignation(form.threadNominalMm, form.threadPitchMm)) {
      return null;
    }
    if (!boreFitsThread(form.threadNominalMm, form.threadPitchMm, diameter)) {
      return null;
    }
    thread = {
      standard: "iso_metric",
      nominal_diameter_mm: form.threadNominalMm,
      pitch_mm: form.threadPitchMm,
    };
  }

  const params: HoleParams = {
    face: faceSubshapeRef(form.face.anchorId, form.face.signature),
    position: form.position,
    diameter_mm: diameter,
    depth,
  };
  if (type !== undefined) params.type = type;
  if (thread !== undefined) params.thread = thread;
  return params;
}

/** True when the form can be submitted (all required fields present + valid). */
export function canSubmitHole(form: HoleForm, unit: LengthUnit): boolean {
  return buildHoleParams(form, unit) !== null;
}

/**
 * A short readout for the drill placement — the point's coords in mm, rounded.
 * Names what the engineer placed (a hole at a point), never how it's stored.
 * "Centre of face" when the point still sits on the face centroid (the seed).
 */
export function positionReadout(form: HoleForm): string {
  if (form.position === null) return "No point chosen";
  const round = (n: number) => Math.round(n * 10) / 10;
  const { x, y, z } = form.position;
  const c = form.face?.signature.centroid;
  const onCentroid =
    c !== undefined &&
    Math.abs(c.x - x) < 1e-6 &&
    Math.abs(c.y - y) < 1e-6 &&
    Math.abs(c.z - z) < 1e-6;
  const coords = `${round(x)}, ${round(y)}, ${round(z)} mm`;
  return onCentroid ? `Centre of face (${coords})` : coords;
}

/**
 * A short readout for the picked face — its area centroid, rounded, in the same
 * grammar as the datum editor's `faceReadout`.
 */
export function holeFaceReadout(face: HoleFace): string {
  const round = (n: number) => Math.round(n * 10) / 10;
  const { x, y, z } = face.signature.centroid;
  return `Face at ${round(x)}, ${round(y)}, ${round(z)} mm`;
}

/**
 * Indices of the overlay vertices that lie ON the picked face's plane — the
 * snappable points the point pick offers besides the centre. A vertex is on the
 * plane when its signed distance to the face plane is within `tol` mm (B-rep
 * vertices are exact, so a generous 1e-3 mm keeps only genuine on-plane corners
 * without admitting a parallel face's vertices). The face's OWN corners are the
 * result for a convex planar face — real "points on the face".
 */
export function coplanarVertexIndices(
  signature: PlanarFaceSignature,
  vertices: readonly Vec3[],
  tol = 1e-3,
): number[] {
  const { normal: n, centroid: c } = signature;
  const nLen = Math.hypot(n.x, n.y, n.z) || 1;
  const indices: number[] = [];
  vertices.forEach((v, i) => {
    const signed =
      ((v.x - c.x) * n.x + (v.y - c.y) * n.y + (v.z - c.z) * n.z) / nLen;
    if (Math.abs(signed) <= tol) indices.push(i);
  });
  return indices;
}

/** True when two world points are the same drill placement (pick selection). */
export function samePoint(a: Vec3 | null, b: Vec3): boolean {
  return (
    a !== null &&
    Math.abs(a.x - b.x) < 1e-6 &&
    Math.abs(a.y - b.y) < 1e-6 &&
    Math.abs(a.z - b.z) < 1e-6
  );
}
