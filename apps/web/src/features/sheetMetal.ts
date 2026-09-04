/**
 * Sheet-metal feature view logic — the pure functions the BaseFlangeEditor,
 * EdgeFlangeEditor, and PartPage share, kept out of the components so they can
 * be unit-tested without a DOM (the extrude/fillet twins). Every param shape
 * comes from the generated client (CLAUDE.md DRY rule); the builders live in
 * `../api/parts`.
 *
 * A base flange is the sheet-metal part's FIRST body — a profile sketch
 * thickened to a fixed gauge (sheet-metal.md §4.1), anchoring the part's
 * sheet-metal defaults (gauge, inner bend radius, K-factor). An edge flange
 * MODIFIES that sheet body: it folds a leg off one picked STRAIGHT edge
 * (§4.2), inheriting the base flange's radius / K unless overridden per-bend.
 */
import { formatLength, type LengthUnit } from "@loft/design";

import type { Vec3 } from "../api/measure";
import type {
  EdgeSignature,
  FeatureResponse,
  SheetMetalBaseFlangeParams,
  SheetMetalCornerReliefParams,
  SheetMetalEdgeFlangeParams,
  SheetMetalHemParams,
} from "../api/parts";
import {
  lengthInputValue,
  parsePositiveLengthMm,
  parseSignedLengthMm,
} from "../units/length";
import { edgeSubshapeRef } from "./edge";
import { fieldBlocker } from "./submitBlocker";

/** The v1 pinned default neutral-axis fraction (air-bent mild steel, §1). */
export const SHEET_METAL_DEFAULT_K_FACTOR = 0.44;

/** Which side of the sketch plane the gauge grows (the extrude idiom). */
export type FlangeDirection = SheetMetalBaseFlangeParams["direction"];

// ---------------------------------------------------------------------------
// Base flange
// ---------------------------------------------------------------------------
/**
 * The editable base-flange form. Lengths (gauge, bend radius) stay raw text —
 * unit inputs; K-factor is a bare fraction. The profile is an EARLIER sketch.
 */
export interface BaseFlangeForm {
  profileFeatureId: string;
  thicknessInput: string;
  bendRadiusInput: string;
  kFactorInput: string;
  direction: FlangeDirection;
}

/**
 * The default new-base-flange form: 1.5 mm gauge, a 3 mm inner bend radius, the
 * v1 0.44 K-factor, grown along the sketch-plane normal — a common light-gauge
 * bracket start. `bend_radius_mm` has no universal default (tooling-dependent),
 * so we seed a sensible starting value the engineer confirms or edits.
 */
export function defaultBaseFlangeForm(
  profileFeatureId: string,
): BaseFlangeForm {
  return {
    profileFeatureId,
    thicknessInput: "1.5",
    bendRadiusInput: "3",
    kFactorInput: String(SHEET_METAL_DEFAULT_K_FACTOR),
    direction: "normal",
  };
}

/** Seed the form from an existing base-flange feature for editing (in `unit`). */
export function formFromBaseFlangeParams(
  params: SheetMetalBaseFlangeParams,
  unit: LengthUnit,
): BaseFlangeForm {
  return {
    profileFeatureId: params.profile.feature_id,
    thicknessInput: lengthInputValue(params.thickness_mm, unit),
    bendRadiusInput: lengthInputValue(params.bend_radius_mm, unit),
    kFactorInput: String(params.k_factor ?? SHEET_METAL_DEFAULT_K_FACTOR),
    direction: params.direction ?? "normal",
  };
}

/**
 * Parse the K-factor field to a fraction in [0, 1], or null when empty,
 * non-numeric, or out of range (K is a neutral-axis position, §1).
 */
export function parseKFactor(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0 || value > 1) return null;
  return value;
}

/** Field-level gauge message, or null when valid (empty is pending). */
export function thicknessError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Gauge must be a positive length."
    : null;
}

/** Field-level bend-radius message, or null when valid (empty is pending). */
export function bendRadiusError(
  input: string,
  unit: LengthUnit,
): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Bend radius must be a positive length."
    : null;
}

/** Field-level K-factor message, or null when valid (empty is pending). */
export function kFactorError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseKFactor(input) === null
    ? "K-factor must be between 0 and 1."
    : null;
}

/**
 * Build `SheetMetalBaseFlangeParamsV1` from the form, or null when the profile
 * or any numeric field is invalid. `merge` is left at the wire default (true —
 * a base flange starts the first body); the editor does not expose it in v1.
 */
export function buildBaseFlangeParams(
  form: BaseFlangeForm,
  unit: LengthUnit,
): SheetMetalBaseFlangeParams | null {
  const thickness = parsePositiveLengthMm(form.thicknessInput, unit);
  const bendRadius = parsePositiveLengthMm(form.bendRadiusInput, unit);
  const kFactor = parseKFactor(form.kFactorInput);
  if (thickness === null || bendRadius === null || kFactor === null) {
    return null;
  }
  if (form.profileFeatureId === "") return null;
  return {
    profile: { kind: "feature", feature_id: form.profileFeatureId },
    thickness_mm: thickness,
    bend_radius_mm: bendRadius,
    k_factor: kFactor,
    direction: form.direction,
    merge: true,
  };
}

/**
 * WHY the base flange cannot be created yet, or null when it can (REASON-GATE-1
 * — see `submitBlocker.ts` for the rule and the 48-character budget).
 *
 * The profile is asked for FIRST even though `buildBaseFlangeParams` checks it
 * last: it is the reference the whole feature hangs on, and a card that says
 * "check the gauge" while no profile is chosen is answering the second question.
 */
export function baseFlangeSubmitBlocker(
  form: BaseFlangeForm,
  unit: LengthUnit,
): string | null {
  if (form.profileFeatureId === "") return "Choose a closed sketch profile.";
  return (
    fieldBlocker(
      form.thicknessInput,
      parsePositiveLengthMm(form.thicknessInput, unit),
      "gauge",
    ) ??
    fieldBlocker(
      form.bendRadiusInput,
      parsePositiveLengthMm(form.bendRadiusInput, unit),
      "bend radius",
    ) ??
    fieldBlocker(form.kFactorInput, parseKFactor(form.kFactorInput), "K-factor")
  );
}

/** True when the base-flange form can be submitted. */
export function canSubmitBaseFlange(
  form: BaseFlangeForm,
  unit: LengthUnit,
): boolean {
  return baseFlangeSubmitBlocker(form, unit) === null;
}

// ---------------------------------------------------------------------------
// Edge flange
// ---------------------------------------------------------------------------
/**
 * The editable edge-flange form. `flange_length_mm` (the developed leg length)
 * is the parametric handle; `bend_angle_deg` defaults to 90 (a right angle).
 * The bend radius and K-factor INHERIT the part's base-flange defaults unless
 * their override toggle is on. The picked edge lives in the edge-pick store
 * (shared with the viewport overlay), so the form stays serialisable.
 */
export interface EdgeFlangeForm {
  flangeLengthInput: string;
  bendAngleInput: string;
  /** How the flange spans the picked edge (§4.5.1) — see `WidthExtent`. */
  widthExtent: WidthExtent;
  /** Flange width along the edge (centered / offset extents). */
  widthInput: string;
  /** Span offset from the edge's canonical start (offset extent only). */
  offsetInput: string;
  overrideBendRadius: boolean;
  bendRadiusInput: string;
  overrideKFactor: boolean;
  kFactorInput: string;
}

/**
 * How an edge flange spans its picked edge (Fusion-style width extents, §4.5.1):
 * - `full` — the flange covers the whole edge (sends NEITHER width nor offset,
 *   the verbatim legacy path — every existing feature stays byte-identical).
 * - `centered` — a `width`-wide flange centered on the edge; the offset is
 *   computed as `(edge_length − width) / 2` and BOTH params are sent.
 * - `offset` — an explicit `width` starting `offset` from the edge's canonical
 *   start (its `EdgeSignature.end_a`, the lexicographically smaller endpoint).
 */
export type WidthExtent = "full" | "centered" | "offset";

/** The default new-edge-flange form: a 20 mm leg folded to 90°, full width, defaults inherited. */
export function defaultEdgeFlangeForm(): EdgeFlangeForm {
  return {
    flangeLengthInput: "20",
    bendAngleInput: "90",
    widthExtent: "full",
    widthInput: "",
    offsetInput: "0",
    overrideBendRadius: false,
    bendRadiusInput: "",
    overrideKFactor: false,
    kFactorInput: "",
  };
}

/** Seed the form from an existing edge-flange feature for editing (in `unit`). */
export function formFromEdgeFlangeParams(
  params: SheetMetalEdgeFlangeParams,
  unit: LengthUnit,
): EdgeFlangeForm {
  const overrideBendRadius =
    params.bend_radius_mm !== null && params.bend_radius_mm !== undefined;
  const overrideKFactor =
    params.k_factor !== null && params.k_factor !== undefined;
  // Width extents (§4.5.1): both absent ⇒ Full width (legacy features round-trip
  // absent). A width and/or offset ⇒ the explicit offset extent, seeded from the
  // stored values (a stored `centered` is indistinguishable from its equivalent
  // offset, so it shows the resolved offset — honest, and rebuilds identically).
  const hasWidth = params.width_mm !== null && params.width_mm !== undefined;
  const hasOffset = params.offset_mm !== null && params.offset_mm !== undefined;
  const widthExtent: WidthExtent = hasWidth || hasOffset ? "offset" : "full";
  return {
    flangeLengthInput: lengthInputValue(params.flange_length_mm, unit),
    bendAngleInput: String(params.bend_angle_deg),
    widthExtent,
    widthInput: hasWidth
      ? lengthInputValue(params.width_mm as number, unit)
      : "",
    offsetInput: hasOffset
      ? lengthInputValue(params.offset_mm as number, unit)
      : "0",
    overrideBendRadius,
    bendRadiusInput: overrideBendRadius
      ? lengthInputValue(params.bend_radius_mm as number, unit)
      : "",
    overrideKFactor,
    kFactorInput: overrideKFactor ? String(params.k_factor) : "",
  };
}

/** The picked-edge signature of a persisted edge flange (its one folded edge). */
export function pickedFromEdgeFlangeParams(
  params: SheetMetalEdgeFlangeParams,
): EdgeSignature[] {
  return [params.edge.selector.signature];
}

/**
 * Parse the bend angle to degrees in (0, 180], or null when empty, non-numeric,
 * or out of range (0 is no fold; the wire caps at 180°).
 */
export function parseBendAngleDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0 || value > 180) return null;
  return value;
}

/** Field-level flange-length message, or null when valid (empty is pending). */
export function flangeLengthError(
  input: string,
  unit: LengthUnit,
): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Flange length must be a positive length."
    : null;
}

/** Field-level bend-angle message, or null when valid (empty is pending). */
export function bendAngleError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseBendAngleDeg(input) === null
    ? "Bend angle must be more than 0 and at most 180 degrees."
    : null;
}

/** Field-level flange-width message, or null when valid (empty is pending). */
export function flangeWidthError(
  input: string,
  unit: LengthUnit,
): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Flange width must be a positive length."
    : null;
}

/** Field-level span-offset message, or null when valid (empty/0 is fine). */
export function flangeOffsetError(
  input: string,
  unit: LengthUnit,
): string | null {
  if (input.trim() === "") return null;
  const mm = parseSignedLengthMm(input, unit);
  return mm === null || mm < 0 ? "Offset can't be negative." : null;
}

/**
 * The wire width/offset for the chosen extent, resolved against the picked
 * edge's length (§4.5.1), or null when the extent's fields are invalid. `full`
 * sends NEITHER param (both null — the verbatim legacy path); `centered`
 * computes the offset that centers `width` on the edge; `offset` reads both
 * fields. An offset that pushes the span off the START of the edge (negative)
 * is rejected here; the `offset + width ≤ edge_length` overflow is the kernel's
 * typed `edge_flange_failed` (it needs the RESOLVED edge, §4.5.1).
 */
export function resolveEdgeFlangeExtent(
  form: EdgeFlangeForm,
  edgeLengthMm: number,
  unit: LengthUnit,
): { widthMm: number | null; offsetMm: number | null } | null {
  if (form.widthExtent === "full") return { widthMm: null, offsetMm: null };
  const width = parsePositiveLengthMm(form.widthInput, unit);
  if (width === null) return null;
  if (form.widthExtent === "centered") {
    const offset = (edgeLengthMm - width) / 2;
    if (offset < 0) return null;
    return { widthMm: width, offsetMm: offset };
  }
  // offset extent: an explicit start offset from the canonical edge start.
  const offset = parseSignedLengthMm(form.offsetInput, unit);
  if (offset === null || offset < 0) return null;
  return { widthMm: width, offsetMm: offset };
}

/**
 * Build `SheetMetalEdgeFlangeParamsV1` from the form + the ONE picked edge, or
 * null when a field is invalid, exactly one straight edge is not picked, an
 * enabled override is blank/invalid, a width extent's fields are invalid, or
 * there is no sheet-body anchor.
 */
export function buildEdgeFlangeParams(
  form: EdgeFlangeForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): SheetMetalEdgeFlangeParams | null {
  const flangeLength = parsePositiveLengthMm(form.flangeLengthInput, unit);
  const bendAngle = parseBendAngleDeg(form.bendAngleInput);
  if (flangeLength === null || bendAngle === null) return null;
  // Exactly ONE straight edge folds a flange; the wire `edge` is a single ref.
  if (picked.length !== 1 || bodyFeatureId === null) return null;
  const signature = picked[0];
  if (signature === undefined) return null;

  const extent = resolveEdgeFlangeExtent(form, signature.length_mm, unit);
  if (extent === null) return null;

  let bendRadius: number | null = null;
  if (form.overrideBendRadius) {
    bendRadius = parsePositiveLengthMm(form.bendRadiusInput, unit);
    if (bendRadius === null) return null;
  }
  let kFactor: number | null = null;
  if (form.overrideKFactor) {
    kFactor = parseKFactor(form.kFactorInput);
    if (kFactor === null) return null;
  }

  const params: SheetMetalEdgeFlangeParams = {
    edge: edgeSubshapeRef(bodyFeatureId, signature),
    flange_length_mm: flangeLength,
    bend_angle_deg: bendAngle,
  };
  // Absent width/offset (Full width) fall through to the base flange's verbatim
  // legacy path; a 0 offset reads the same as absent so it stays off the wire.
  if (extent.widthMm !== null) params.width_mm = extent.widthMm;
  if (extent.offsetMm !== null && extent.offsetMm > 0) {
    params.offset_mm = extent.offsetMm;
  }
  // Omit inherited defaults (null) so the wire falls back to the base flange's.
  if (bendRadius !== null) params.bend_radius_mm = bendRadius;
  if (kFactor !== null) params.k_factor = kFactor;
  return params;
}

/**
 * The chosen span drawn ON the picked edge in the viewport (§4.5.1) — the
 * `[offset, offset + width]` segment measured from the edge's canonical start
 * (`end_a`), in OCCT world-mm. Null until exactly one edge is picked or when the
 * extent's fields are invalid (nothing to preview). `full` previews the whole
 * edge; `centered`/`offset` preview the sub-span so the notched extent is
 * legible before commit.
 */
export interface EdgeFlangeSpanPreview {
  /** Span start (OCCT world-mm) — `end_a + offset·dir`. */
  start: Vec3;
  /** Span end (OCCT world-mm) — `start + width·dir`. */
  end: Vec3;
  /** The span width (mm) — the caption numeral. */
  spanMm: number;
}

export function edgeFlangeSpanPreview(
  form: EdgeFlangeForm,
  picked: readonly EdgeSignature[],
  unit: LengthUnit,
): EdgeFlangeSpanPreview | null {
  if (picked.length !== 1) return null;
  const sig = picked[0];
  if (sig === undefined) return null;
  const length = sig.length_mm;
  if (!(length > 0)) return null;
  const extent = resolveEdgeFlangeExtent(form, length, unit);
  if (extent === null) return null;
  const offset = extent.offsetMm ?? 0;
  const width = extent.widthMm ?? length - offset;
  const { end_a: a, end_b: b } = sig;
  const dir = {
    x: (b.x - a.x) / length,
    y: (b.y - a.y) / length,
    z: (b.z - a.z) / length,
  };
  const start = {
    x: a.x + dir.x * offset,
    y: a.y + dir.y * offset,
    z: a.z + dir.z * offset,
  };
  const end = {
    x: start.x + dir.x * width,
    y: start.y + dir.y * width,
    z: start.z + dir.z * width,
  };
  return { start, end, spanMm: width };
}

/**
 * WHY the edge flange cannot be created yet, or null when it can (REASON-GATE-1
 * — see `submitBlocker.ts` for the rule and the 48-character budget).
 *
 * The width extent is the one gate here that is not a single field: a centered
 * span WIDER than the edge parses fine in its own box and is refused by the
 * arithmetic, so it gets a sentence naming the relationship rather than the box.
 * Overrides follow `hemSubmitBlocker`'s wording — a blank override is a state
 * with two exits, and naming both is what stops it reading as a dead end.
 */
export function edgeFlangeSubmitBlocker(
  form: EdgeFlangeForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): string | null {
  if (bodyFeatureId === null) return "Add a base flange to fold from.";
  const signature = picked.length === 1 ? picked[0] : undefined;
  if (signature === undefined) {
    return picked.length === 0
      ? "Pick one straight edge to fold."
      : "Press Clear, then pick one edge.";
  }
  const length = fieldBlocker(
    form.flangeLengthInput,
    parsePositiveLengthMm(form.flangeLengthInput, unit),
    "flange length",
  );
  if (length !== null) return length;
  const angle = fieldBlocker(
    form.bendAngleInput,
    parseBendAngleDeg(form.bendAngleInput),
    "bend angle",
  );
  if (angle !== null) return angle;

  if (form.widthExtent !== "full") {
    const width = fieldBlocker(
      form.widthInput,
      parsePositiveLengthMm(form.widthInput, unit),
      "flange width",
    );
    if (width !== null) return width;
    if (form.widthExtent === "offset") {
      const offsetMm = parseSignedLengthMm(form.offsetInput, unit);
      if (offsetMm === null || offsetMm < 0) {
        return fieldBlocker(form.offsetInput, null, "offset from edge start");
      }
    }
    // Reached only when every field parses — so the span itself is the problem.
    if (resolveEdgeFlangeExtent(form, signature.length_mm, unit) === null) {
      return "The span runs off the end of the edge.";
    }
  }

  if (form.overrideBendRadius) {
    const radius = parsePositiveLengthMm(form.bendRadiusInput, unit);
    if (radius === null) return "Type a radius, or uncheck the override.";
  }
  if (form.overrideKFactor && parseKFactor(form.kFactorInput) === null) {
    return "Type a K-factor, or uncheck the override.";
  }
  return null;
}

/** True when the edge-flange form can be submitted (valid fields + one edge). */
export function canSubmitEdgeFlange(
  form: EdgeFlangeForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return edgeFlangeSubmitBlocker(form, picked, bodyFeatureId, unit) === null;
}

// ---------------------------------------------------------------------------
// Hem (closed / open) — parity §2
// ---------------------------------------------------------------------------
/**
 * Which hem the fold makes. The wire Literal is the source (`teardrop`/`rolled`
 * wrap past 180° and this fold cannot build them, so they are deliberately not
 * members) — naming a shape here that the schema does not admit would be the
 * defect HEM-1 removed, in the other direction.
 */
export type HemType = SheetMetalHemParams["hem_type"];

/**
 * THE HEM RADIUS RULE (HEM-1), mirrored from `py_kit.schemas.features`:
 * `HEM_CLOSED_RADIUS_RATIO` / `HEM_CLOSED_MAX_RADIUS_RATIO` /
 * `HEM_OPEN_RADIUS_RATIO` and `resolve_hem_bend_radius_mm`.
 *
 * A hem's inner radius is a function of its TYPE and the part's GAUGE, never of
 * the base flange's general bend radius (that describes a free-standing die
 * bend — what an edge flange IS and a hem is not). The fold's cross-section puts
 * the two layers exactly `2 × radius` apart, so the radius IS the hem's defining
 * dimension.
 *
 * WHY A MIRROR AND NOT AN IMPORT. The ratios are module constants behind
 * `resolve_hem_bend_radius_mm`, not schema FIELDS, so nothing in the generated
 * client carries them — there is no wire value to read. The editor still has to
 * state the number BEFORE the user types (that is the whole of HEM-1C: it used
 * to state `0.5 × gauge` for a closed hem, i.e. the one value the evaluator
 * refuses by name). So the rule is written once HERE, for every hem string and
 * readout the UI shows, and `sheetMetal.test.ts` pins these three constants
 * against the py-kit source itself — a hand-maintained number that agrees with
 * the server today is the same defect with a later date on it.
 *
 * The client ADVISES; the evaluator DECIDES. `hemRadiusConflict` is stated in
 * the form rather than enforced by it (see `canSubmitHem`), so a mirror that
 * ever drifts costs a wrong sentence, never a lockout on a legal value.
 */
export const HEM_CLOSED_RADIUS_RATIO = 0.05;

/** The closed/open boundary as a multiple of gauge; it belongs to BOTH types. */
export const HEM_CLOSED_MAX_RADIUS_RATIO = 0.125;

/** An open hem's inner radius: 0.5 × gauge puts the inside DIAMETER at one gauge. */
export const HEM_OPEN_RADIUS_RATIO = 0.5;

/** The inner radius (mm) a hem of `hemType` folds at on `thicknessMm` gauge. */
export function derivedHemRadiusMm(
  hemType: HemType,
  thicknessMm: number,
): number {
  const ratio =
    hemType === "open" ? HEM_OPEN_RADIUS_RATIO : HEM_CLOSED_RADIUS_RATIO;
  return ratio * thicknessMm;
}

/** The radius (mm) that divides a closed hem from an open one on this gauge. */
export function hemRadiusBoundaryMm(thicknessMm: number): number {
  return HEM_CLOSED_MAX_RADIUS_RATIO * thicknessMm;
}

/**
 * The air gap (mm) between the hem's two layers — exactly twice the inner
 * radius, which is what makes the radius the thing worth showing.
 */
export function hemGapMm(radiusMm: number): number {
  return 2 * radiusMm;
}

/**
 * The gap in gauges — `0.1 t` closed, `1 t` open. Hem practice sizes every hem
 * feature in multiples of gauge, so this is the reading an engineer checks.
 */
export function hemGapInGauges(radiusMm: number, thicknessMm: number): number {
  return thicknessMm > 0 ? hemGapMm(radiusMm) / thicknessMm : 0;
}

/**
 * The hem's resolved inner radius (mm): the override when it is set and parses,
 * otherwise the radius the type + gauge derive. Null when the part has no gauge
 * (no sheet body) or an enabled override has not been typed yet — there is
 * nothing honest to show, so the readout says so rather than guessing.
 */
export function resolvedHemRadiusMm(
  form: HemForm,
  defaults: SheetMetalDefaults | null,
  unit: LengthUnit,
): number | null {
  if (defaults === null) return null;
  if (form.overrideBendRadius) {
    return parsePositiveLengthMm(form.bendRadiusInput, unit);
  }
  return derivedHemRadiusMm(form.hemType, defaults.thicknessMm);
}

/**
 * The conflict message for a radius that describes the OTHER hem type, or null
 * when it is consistent (or unknowable). It mirrors `resolve_hem_bend_radius_mm`'s
 * refusal so the user reads it while typing instead of after a failed rebuild,
 * and it names BOTH ways out — switch the type, or come inside the boundary.
 * The boundary belongs to both types, so the two bands partition the line.
 */
export function hemRadiusConflict(
  hemType: HemType,
  radiusMm: number,
  thicknessMm: number,
  unit: LengthUnit,
): string | null {
  const boundary = hemRadiusBoundaryMm(thicknessMm);
  const gap = (r: number): string => formatLength(hemGapMm(r), unit);
  if (hemType === "closed" && radiusMm > boundary) {
    return `A closed hem presses flat, so ${formatLength(radiusMm, unit)} is an open hem's radius — it leaves a ${gap(radiusMm)} gap. Switch the type to Open to keep that gap, or use at most ${formatLength(boundary, unit)}.`;
  }
  if (hemType === "open" && radiusMm < boundary) {
    return `An open hem keeps a deliberate gap, and ${formatLength(radiusMm, unit)} leaves only ${gap(radiusMm)} — that is a closed hem. Switch the type to Closed for a flattened fold, or use at least ${formatLength(boundary, unit)}.`;
  }
  return null;
}

/**
 * The editable hem form. A hem is mechanically an edge flange folded 180° back
 * onto the sheet, so it mirrors the edge-flange form MINUS the fold-angle field
 * (the angle is always 180°): the return `length_mm` is the parametric handle.
 * `hemType` chooses the shape — and with it the fold's radius and air gap.
 *
 * The K-factor INHERITS the base-flange default unless overridden (K is a
 * MATERIAL property — where the neutral surface sits). The bend radius does
 * NOT: it comes from the type and the gauge (HEM-1), and its override replaces
 * that derived value rather than the part's. The picked edge lives in the
 * shared edge-pick store (with the viewport overlay), so the form stays
 * serialisable — identical to the edge flange.
 */
export interface HemForm {
  lengthInput: string;
  hemType: HemType;
  overrideBendRadius: boolean;
  bendRadiusInput: string;
  overrideKFactor: boolean;
  kFactorInput: string;
}

/** The default new-hem form: a 6 mm folded-back return, closed, radius derived. */
export function defaultHemForm(): HemForm {
  return {
    lengthInput: "6",
    hemType: "closed",
    overrideBendRadius: false,
    bendRadiusInput: "",
    overrideKFactor: false,
    kFactorInput: "",
  };
}

/** Seed the form from an existing hem feature for editing (in `unit`). */
export function formFromHemParams(
  params: SheetMetalHemParams,
  unit: LengthUnit,
): HemForm {
  const overrideBendRadius =
    params.bend_radius_mm !== null && params.bend_radius_mm !== undefined;
  const overrideKFactor =
    params.k_factor !== null && params.k_factor !== undefined;
  return {
    lengthInput: lengthInputValue(params.length_mm, unit),
    // Absent reads "closed" on the wire (the schema default); a feature stored
    // before `hem_type` shipped therefore round-trips as the closed hem it is.
    hemType: params.hem_type ?? "closed",
    overrideBendRadius,
    bendRadiusInput: overrideBendRadius
      ? lengthInputValue(params.bend_radius_mm as number, unit)
      : "",
    overrideKFactor,
    kFactorInput: overrideKFactor ? String(params.k_factor) : "",
  };
}

/** The picked-edge signature of a persisted hem (its one folded edge). */
export function pickedFromHemParams(
  params: SheetMetalHemParams,
): EdgeSignature[] {
  return [params.edge.selector.signature];
}

/** Field-level hem-length message, or null when valid (empty is pending). */
export function hemLengthError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Return length must be a positive length."
    : null;
}

/**
 * Build `SheetMetalHemParamsV1` from the form + the ONE picked edge, or null
 * when the length is invalid, exactly one straight edge is not picked, an
 * enabled override is blank/invalid, or there is no sheet-body anchor. The fold
 * angle is implicit (180°); `hem_type` is the user's choice (HEM-1D — it was
 * hardcoded `"closed"`, so the `open` hem the API ships could not be authored).
 *
 * A radius that contradicts the type is NOT blocked here: `hemRadiusConflict`
 * states it in the form, and the evaluator — which owns the rule — refuses it
 * with a typed error. Blocking on a client-side mirror would turn any future
 * drift into a lockout on a value the server would have accepted.
 */
export function buildHemParams(
  form: HemForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): SheetMetalHemParams | null {
  const length = parsePositiveLengthMm(form.lengthInput, unit);
  if (length === null) return null;
  // Exactly ONE straight edge is hemmed; the wire `edge` is a single ref.
  if (picked.length !== 1 || bodyFeatureId === null) return null;
  const signature = picked[0];
  if (signature === undefined) return null;

  let bendRadius: number | null = null;
  if (form.overrideBendRadius) {
    bendRadius = parsePositiveLengthMm(form.bendRadiusInput, unit);
    if (bendRadius === null) return null;
  }
  let kFactor: number | null = null;
  if (form.overrideKFactor) {
    kFactor = parseKFactor(form.kFactorInput);
    if (kFactor === null) return null;
  }

  const params: SheetMetalHemParams = {
    edge: edgeSubshapeRef(bodyFeatureId, signature),
    length_mm: length,
    hem_type: form.hemType,
  };
  // Omit inherited defaults (null) so the wire falls back to the base flange's.
  if (bendRadius !== null) params.bend_radius_mm = bendRadius;
  if (kFactor !== null) params.k_factor = kFactor;
  return params;
}

/**
 * WHY the hem cannot be saved yet — one sentence naming the field AND the way
 * out — or null when it can. THE DISABLED SAVE IS THE SUBJECT HERE, not a
 * by-product: HEM-1B measured a repair path where `hem-submit` carried
 * `aria-disabled="true"` and an EMPTY `title`, with no error text and no red
 * field, which is indistinguishable from a dead end (`docs/AUDIT-PRODUCT.md`
 * S-26). An action that refuses without saying why is worse than an absent one,
 * because the user cannot tell "not yet" from "not ever" (design mandate: no
 * dead ends, no ambiguous exits).
 *
 * `canSubmitHem` is DEFINED as `hemSubmitBlocker(...) === null`, so the gate and
 * its explanation cannot drift into disagreement — the failure mode where the
 * cell is grey and the reason line says nothing is unreachable by construction.
 * `sheetMetal.test.ts` cross-checks the pair against `buildHemParams`, which is
 * an independently-written predicate: agreeing with itself would prove nothing.
 *
 * `defaults` only ENRICHES the sentence (it names the derived radius / the
 * inherited K a user would fall back to); it never changes the verdict, which is
 * why it is optional.
 *
 * WHY THESE ARE ~30 CHARACTERS. `PanelActionCell` renders the reason in the
 * footer cell it explains, which is HALF a card wide (~19 characters a line at
 * the data face) — a 74-character sentence measured five wrapped lines and ate
 * the card. So each reason names the field and the way out and stops: the FIELD
 * states the rule it broke (`kFactorError` etc. render inline, in red, on the
 * input), and the Save cell states what to do to save. One job each.
 */
export function hemSubmitBlocker(
  form: HemForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
  defaults: SheetMetalDefaults | null = null,
): string | null {
  if (bodyFeatureId === null) return "Add a base flange to hem first.";
  const signature = picked.length === 1 ? picked[0] : undefined;
  if (signature === undefined) {
    return picked.length === 0
      ? "Pick one straight edge to hem."
      : "Press Clear, then pick one edge.";
  }
  if (parsePositiveLengthMm(form.lengthInput, unit) === null) {
    // Empty is a missing answer; anything else is a wrong one, and the field is
    // already red with the rule — so the cell points at it rather than repeating.
    return form.lengthInput.trim() === ""
      ? "Enter the return length."
      : "Check the return length.";
  }
  if (
    form.overrideBendRadius &&
    parsePositiveLengthMm(form.bendRadiusInput, unit) === null
  ) {
    const derived =
      defaults === null
        ? null
        : formatLength(
            derivedHemRadiusMm(form.hemType, defaults.thicknessMm),
            unit,
          );
    return derived === null
      ? "Type a radius, or uncheck the override."
      : `Type a radius, or uncheck to fold at ${derived}.`;
  }
  if (form.overrideKFactor && parseKFactor(form.kFactorInput) === null) {
    return defaults === null
      ? "Type a K-factor, or uncheck the override."
      : `Type a K-factor, or uncheck to inherit ${defaults.kFactor}.`;
  }
  return null;
}

/** True when the hem form can be submitted — the blocker, read as a verdict. */
export function canSubmitHem(
  form: HemForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return hemSubmitBlocker(form, picked, bodyFeatureId, unit) === null;
}

/**
 * The form after the bend-radius override is toggled. Turning it ON SEEDS the
 * blank field with the radius the hem is folding at right now, so the toggle
 * shows the value it is about to let you change instead of emptying the fold's
 * defining dimension. A typed value is never overwritten — re-ticking restores
 * what the user had.
 *
 * This is the HEM-1B hydration half, fixed at the source rather than at the
 * symptom: "override checked, value empty" is a form that says a number is
 * being overridden while naming none, and it is the state the audit found
 * holding Save hostage. The seed is the SAME `derivedHemRadiusMm` the card's
 * readouts use (HEM-1C's one rule), so it is always a radius the evaluator
 * accepts for this type.
 */
export function withHemBendRadiusOverride(
  form: HemForm,
  on: boolean,
  defaults: SheetMetalDefaults | null,
  unit: LengthUnit,
): HemForm {
  if (!on) return { ...form, overrideBendRadius: false };
  const blank = form.bendRadiusInput.trim() === "";
  return {
    ...form,
    overrideBendRadius: true,
    bendRadiusInput:
      blank && defaults !== null
        ? lengthInputValue(
            derivedHemRadiusMm(form.hemType, defaults.thicknessMm),
            unit,
          )
        : form.bendRadiusInput,
  };
}

/**
 * The form after the K-factor override is toggled — the same seeding rule, from
 * the value the card says it inherits ("Inherits 0.44 from the base flange"), so
 * the checkbox and the field can never contradict each other.
 */
export function withHemKFactorOverride(
  form: HemForm,
  on: boolean,
  defaults: SheetMetalDefaults | null,
): HemForm {
  if (!on) return { ...form, overrideKFactor: false };
  const blank = form.kFactorInput.trim() === "";
  return {
    ...form,
    overrideKFactor: true,
    kFactorInput:
      blank && defaults !== null ? String(defaults.kFactor) : form.kFactorInput,
  };
}

// ---------------------------------------------------------------------------
// Corner relief (rectangular) — parity §4.4
// ---------------------------------------------------------------------------
/**
 * The editable corner-relief form. Unlike a hem this is NOT an edge pick: it
 * names the two edge-flange FEATURES whose bends meet at the corner (`bendAId` /
 * `bendBId`, each a feature id resolved to a `FeatureRef`). The notch is sized
 * as `relief_ratio × gauge` by default; an absolute `size_mm` override wins when
 * its toggle is on (the authoring convenience the schema documents).
 */
export interface CornerReliefForm {
  bendAId: string;
  bendBId: string;
  reliefRatioInput: string;
  overrideSize: boolean;
  sizeInput: string;
}

/** The v1 default relief ratio: one gauge thickness (the tear-safe default). */
export const SHEET_METAL_DEFAULT_RELIEF_RATIO = 1;

/** The default new-corner-relief form: the two given bends, ratio 1.0, no size override. */
export function defaultCornerReliefForm(
  bendAId: string,
  bendBId: string,
): CornerReliefForm {
  return {
    bendAId,
    bendBId,
    reliefRatioInput: String(SHEET_METAL_DEFAULT_RELIEF_RATIO),
    overrideSize: false,
    sizeInput: "",
  };
}

/** Seed the form from an existing corner-relief feature for editing (in `unit`). */
export function formFromCornerReliefParams(
  params: SheetMetalCornerReliefParams,
  unit: LengthUnit,
): CornerReliefForm {
  const overrideSize = params.size_mm !== null && params.size_mm !== undefined;
  return {
    bendAId: params.bend_a.feature_id,
    bendBId: params.bend_b.feature_id,
    reliefRatioInput: String(params.relief_ratio),
    overrideSize,
    sizeInput: overrideSize
      ? lengthInputValue(params.size_mm as number, unit)
      : "",
  };
}

/** Parse the relief ratio to a positive multiple of gauge, or null when invalid. */
export function parseReliefRatio(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

/** Field-level relief-ratio message, or null when valid (empty is pending). */
export function reliefRatioError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseReliefRatio(input) === null
    ? "Relief ratio must be a positive multiple of the gauge."
    : null;
}

/** Field-level relief-size message, or null when valid (empty is pending). */
export function reliefSizeError(
  input: string,
  unit: LengthUnit,
): string | null {
  if (input.trim() === "") return null;
  return parsePositiveLengthMm(input, unit) === null
    ? "Notch size must be a positive length."
    : null;
}

/** The edge-flange features (id + name) a corner relief can reference, in tree order. */
export function edgeFlangeOptions(
  features: readonly FeatureResponse[],
): { id: string; name: string }[] {
  return features
    .filter(
      (f) => !f.rolled_back && f.feature.type === "sheet_metal_edge_flange",
    )
    .map((f) => ({ id: f.id, name: f.name }));
}

/**
 * Build `SheetMetalCornerReliefParamsV1` from the form, or null when the ratio
 * is invalid, the two bends are unset or identical, or an enabled size override
 * is blank/invalid. `relief_type` is fixed at `"rectangular"` in v1; the wire
 * still carries `relief_ratio` even under a size override (it has no null slot).
 */
export function buildCornerReliefParams(
  form: CornerReliefForm,
  unit: LengthUnit,
): SheetMetalCornerReliefParams | null {
  const ratio = parseReliefRatio(form.reliefRatioInput);
  if (ratio === null) return null;
  if (
    form.bendAId === "" ||
    form.bendBId === "" ||
    form.bendAId === form.bendBId
  ) {
    return null;
  }
  let size: number | null = null;
  if (form.overrideSize) {
    size = parsePositiveLengthMm(form.sizeInput, unit);
    if (size === null) return null;
  }
  const params: SheetMetalCornerReliefParams = {
    bend_a: { kind: "feature", feature_id: form.bendAId },
    bend_b: { kind: "feature", feature_id: form.bendBId },
    relief_ratio: ratio,
    relief_type: "rectangular",
  };
  if (size !== null) params.size_mm = size;
  return params;
}

/**
 * WHY the corner relief cannot be created yet, or null when it can
 * (REASON-GATE-1 — see `submitBlocker.ts` for the rule and the 48-character
 * budget).
 *
 * The two bends are asked for before the ratio: a corner relief is defined by
 * WHICH corner, and the ratio has a working default, so pointing at the number
 * first would answer a question the user has not reached.
 *
 * A bend whose flange no longer resolves is NOT here — that is an edit-mode
 * fact about the tree, held by `CornerReliefEditor` alongside its own guard
 * option, and composed into the same reason line there.
 */
export function cornerReliefSubmitBlocker(
  form: CornerReliefForm,
  unit: LengthUnit,
): string | null {
  if (form.bendAId === "") return "Choose bend A.";
  if (form.bendBId === "") return "Choose bend B.";
  if (form.bendAId === form.bendBId) return "Pick two different edge flanges.";
  const ratio = fieldBlocker(
    form.reliefRatioInput,
    parseReliefRatio(form.reliefRatioInput),
    "relief ratio",
  );
  if (ratio !== null) return ratio;
  if (
    form.overrideSize &&
    parsePositiveLengthMm(form.sizeInput, unit) === null
  ) {
    return "Type a notch size, or uncheck the override.";
  }
  return null;
}

/** True when the corner-relief form can be submitted (valid ratio + two distinct bends). */
export function canSubmitCornerRelief(
  form: CornerReliefForm,
  unit: LengthUnit,
): boolean {
  return cornerReliefSubmitBlocker(form, unit) === null;
}

/** True when the part has ≥2 edge flanges to relieve a corner between (the gate). */
export function canAuthorCornerRelief(
  features: readonly FeatureResponse[],
): boolean {
  return edgeFlangeOptions(features).length >= 2;
}

/**
 * True when a stored bend ref no longer resolves to a live edge flange (the
 * flange was rolled back or removed since the relief was authored). The native
 * `<select>` would otherwise silently display the WRONG flange while the form
 * holds the stale id — the editor shows a guard instead.
 */
export function unresolvedBendRef(
  edgeFlanges: readonly { id: string }[],
  bendId: string,
): boolean {
  return bendId !== "" && !edgeFlanges.some((f) => f.id === bendId);
}

/** One highlighted bend in the viewport: its tag ("A" / "B") + its bend line. */
export interface CornerReliefBendHighlight {
  /** The select it answers for — "A", "B", or "A · B" when both name one bend. */
  tag: string;
  /** The flange's stored fold-edge signature — the physical bend line. */
  signature: EdgeSignature;
}

/**
 * The in-scene highlights for the corner-relief editor's current Bend A / B
 * selection: each id resolved to its live edge-flange feature's stored
 * fold-edge signature (the bend line the flange was folded along). Unresolved
 * or empty refs yield NO entry (the guard handles them); the same flange picked
 * twice collapses to one entry tagged "A · B" (the same-bend form error still
 * shows — the scene never draws two stacked tags).
 */
export function cornerReliefBendHighlights(
  features: readonly FeatureResponse[],
  bendAId: string,
  bendBId: string,
): CornerReliefBendHighlight[] {
  const resolve = (id: string): EdgeSignature | null => {
    if (id === "") return null;
    for (const f of features) {
      if (
        f.id === id &&
        !f.rolled_back &&
        f.feature.type === "sheet_metal_edge_flange"
      ) {
        return f.feature.params.edge.selector.signature;
      }
    }
    return null;
  };
  const a = resolve(bendAId);
  const b = resolve(bendBId);
  if (a !== null && b !== null && bendAId === bendBId) {
    return [{ tag: "A · B", signature: a }];
  }
  const out: CornerReliefBendHighlight[] = [];
  if (a !== null) out.push({ tag: "A", signature: a });
  if (b !== null) out.push({ tag: "B", signature: b });
  return out;
}

// ---------------------------------------------------------------------------
// Part-level sheet-metal state
// ---------------------------------------------------------------------------
/** The part's sheet-metal defaults, read from its base flange (edge flanges inherit). */
export interface SheetMetalDefaults {
  thicknessMm: number;
  bendRadiusMm: number;
  kFactor: number;
}

/**
 * The part's sheet-metal defaults from the FIRST non-rolled-back base flange,
 * or null when the part is not sheet metal. The edge-flange editor shows the
 * radius + K as the inherited values behind its per-bend overrides; the hem
 * editor inherits only K and derives its radius from the gauge + hem type
 * (HEM-1); the corner-relief editor uses the gauge to preview the notch.
 */
export function sheetMetalDefaults(
  features: readonly FeatureResponse[],
): SheetMetalDefaults | null {
  for (const f of features) {
    if (f.rolled_back) continue;
    if (f.feature.type === "sheet_metal_base_flange") {
      const params = f.feature.params;
      return {
        thicknessMm: params.thickness_mm,
        bendRadiusMm: params.bend_radius_mm,
        kFactor: params.k_factor ?? SHEET_METAL_DEFAULT_K_FACTOR,
      };
    }
  }
  return null;
}

/** True when the part has a sheet-metal body (a base flange in the live tree). */
export function isSheetMetalPart(
  features: readonly FeatureResponse[],
): boolean {
  return sheetMetalDefaults(features) !== null;
}
