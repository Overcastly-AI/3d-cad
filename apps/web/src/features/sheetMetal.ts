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

import type {
  EdgeSignature,
  FeatureResponse,
  SheetMetalBaseFlangeParams,
  SheetMetalCornerReliefParams,
  SheetMetalEdgeFlangeParams,
  SheetMetalHemParams,
} from "../api/parts";
import { lengthInputValue, parsePositiveLengthMm } from "../units/length";
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
  overrideBendRadius: boolean;
  bendRadiusInput: string;
  overrideKFactor: boolean;
  kFactorInput: string;
}

/** The default new-edge-flange form: a 20 mm leg folded to 90°, defaults inherited. */
export function defaultEdgeFlangeForm(): EdgeFlangeForm {
  return {
    flangeLengthInput: "20",
    bendAngleInput: "90",
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
  return {
    flangeLengthInput: lengthInputValue(params.flange_length_mm, unit),
    bendAngleInput: String(params.bend_angle_deg),
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

/**
 * Build `SheetMetalEdgeFlangeParamsV1` from the form + the ONE picked edge, or
 * null when a field is invalid, exactly one straight edge is not picked, an
 * enabled override is blank/invalid, or there is no sheet-body anchor.
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
  // Omit inherited defaults (null) so the wire falls back to the base flange's.
  if (bendRadius !== null) params.bend_radius_mm = bendRadius;
  if (kFactor !== null) params.k_factor = kFactor;
  return params;
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
