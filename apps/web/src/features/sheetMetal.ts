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
import type { LengthUnit } from "@loft/design";

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

/** True when the base-flange form can be submitted. */
export function canSubmitBaseFlange(
  form: BaseFlangeForm,
  unit: LengthUnit,
): boolean {
  return buildBaseFlangeParams(form, unit) !== null;
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

/** True when the edge-flange form can be submitted (valid fields + one edge). */
export function canSubmitEdgeFlange(
  form: EdgeFlangeForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return buildEdgeFlangeParams(form, picked, bodyFeatureId, unit) !== null;
}

// ---------------------------------------------------------------------------
// Hem (closed) — parity §2
// ---------------------------------------------------------------------------
/**
 * The editable closed-hem form. A closed hem is mechanically an edge flange
 * folded 180° back onto the sheet, so it mirrors the edge-flange form MINUS the
 * fold-angle field (the angle is always 180°): the return `length_mm` is the
 * parametric handle; the bend radius and K-factor INHERIT the base-flange
 * defaults unless their override toggle is on. The picked edge lives in the
 * shared edge-pick store (with the viewport overlay), so the form stays
 * serialisable — identical to the edge flange.
 */
export interface HemForm {
  lengthInput: string;
  overrideBendRadius: boolean;
  bendRadiusInput: string;
  overrideKFactor: boolean;
  kFactorInput: string;
}

/** The default new-hem form: a 6 mm folded-back return, defaults inherited. */
export function defaultHemForm(): HemForm {
  return {
    lengthInput: "6",
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
 * angle is implicit (180°) and `hem_type` is fixed at `"closed"` in v1.
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
    hem_type: "closed",
  };
  // Omit inherited defaults (null) so the wire falls back to the base flange's.
  if (bendRadius !== null) params.bend_radius_mm = bendRadius;
  if (kFactor !== null) params.k_factor = kFactor;
  return params;
}

/** True when the hem form can be submitted (valid length + one edge). */
export function canSubmitHem(
  form: HemForm,
  picked: readonly EdgeSignature[],
  bodyFeatureId: string | null,
  unit: LengthUnit,
): boolean {
  return buildHemParams(form, picked, bodyFeatureId, unit) !== null;
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

/** True when the corner-relief form can be submitted (valid ratio + two distinct bends). */
export function canSubmitCornerRelief(
  form: CornerReliefForm,
  unit: LengthUnit,
): boolean {
  return buildCornerReliefParams(form, unit) !== null;
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
 * or null when the part is not sheet metal. Edge-flange / hem editors show the
 * radius + K as the inherited values behind their per-bend overrides; the
 * corner-relief editor uses the gauge thickness to preview the ratio-sized notch.
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
