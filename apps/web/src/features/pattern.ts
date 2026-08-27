/**
 * Pattern-feature view logic — the pure functions the PatternEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM (the revolve module's twin). Param shapes come from the generated
 * client (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * A pattern repeats its SUBJECT into a linear row or circular ring — the whole
 * body, or the features the tree named (`./patternScope`, the `scope` field of
 * docs/design/pattern-scope.md). It carries no profile/axis reference to
 * sketch geometry — its direction/axis are WORLD-space vectors. Rather than a
 * novel three-number vector widget, we offer the six principal axes as a ruled
 * SelectField (revolve's axis idiom: keyboard-first, deterministically
 * testable, one small set) — the overwhelmingly common pattern direction is a
 * principal axis. `count` INCLUDES the seed (instance 0), so the smallest
 * pattern that adds anything is `count = 2`.
 */
import type { LengthUnit } from "@loft/design";

import type { FeatureResponse, PatternParams, Vec3 } from "../api/parts";
import {
  lengthInputValue,
  parsePositiveLengthMm,
  parseSignedLengthMm,
} from "../units/length";
// WHAT a pattern repeats is its own decision, shared verbatim with the mirror.
import {
  buildScope,
  defaultScopeMode,
  type ScopeFeature,
  type ScopeMode,
  type ScopeSeed,
  scopeFromParams,
} from "./patternScope";
// The angle field shares revolve's (0, 360] parse/validation exactly (DRY).
import { angleError, parseAngleDeg } from "./revolve";

export { angleError, parseAngleDeg };

export type PatternKind = PatternParams["pattern"]["kind"];

/** A world-space principal axis, offered in the direction/axis ruled selects. */
export type AxisPreset = "+x" | "-x" | "+y" | "-y" | "+z" | "-z";

export interface AxisPresetOption {
  id: AxisPreset;
  label: string;
}

/** The six principal axes, in a stable order (positive then negative per axis). */
export const AXIS_PRESETS: readonly AxisPresetOption[] = [
  { id: "+x", label: "+X" },
  { id: "-x", label: "-X" },
  { id: "+y", label: "+Y" },
  { id: "-y", label: "-Y" },
  { id: "+z", label: "+Z" },
  { id: "-z", label: "-Z" },
];

const PRESET_VEC: Record<AxisPreset, Vec3> = {
  "+x": { x: 1, y: 0, z: 0 },
  "-x": { x: -1, y: 0, z: 0 },
  "+y": { x: 0, y: 1, z: 0 },
  "-y": { x: 0, y: -1, z: 0 },
  "+z": { x: 0, y: 0, z: 1 },
  "-z": { x: 0, y: 0, z: -1 },
};

/** The unit vector for a principal-axis preset. */
export function presetVec(id: AxisPreset): Vec3 {
  return PRESET_VEC[id];
}

/**
 * The principal axis best aligned with an arbitrary vector — used to seed the
 * editor from an existing pattern. UI-authored patterns always store an exact
 * preset, so this is lossless in practice; a hand-authored oblique vector snaps
 * to its nearest principal axis (defaulting to +X for a zero vector).
 */
export function nearestPreset(v: Vec3): AxisPreset {
  const mag = Math.hypot(v.x, v.y, v.z);
  if (mag === 0) return "+x";
  let best: AxisPreset = "+x";
  let bestDot = -Infinity;
  for (const { id } of AXIS_PRESETS) {
    const u = PRESET_VEC[id];
    const dot = (v.x * u.x + v.y * u.y + v.z * u.z) / mag;
    if (dot > bestDot) {
      bestDot = dot;
      best = id;
    }
  }
  return best;
}

/** The editable pattern form (numeric fields kept as raw text — unit inputs). */
export interface PatternForm {
  kind: PatternKind;
  /** WHAT is repeated: the whole body, or the named features (`patternScope`). */
  scope: ScopeMode;
  /** The named subject, carried with its NAME so the row can render it. */
  scopeFeatures: readonly ScopeFeature[];
  /** TOTAL instances INCLUDING the seed; shared by both modes. */
  countInput: string;
  // Linear
  direction: AxisPreset;
  spacingInput: string;
  // Circular
  axisDirection: AxisPreset;
  axisPointXInput: string;
  axisPointYInput: string;
  axisPointZInput: string;
  angleInput: string;
}

/**
 * The default new-pattern form: a 3-up linear row 10 mm apart along +X, on the
 * subject the tree proposes (`seed` — a selected row, else the tip). Called with
 * no seed it opens on the whole body, which is what a pattern authored before
 * this scope row meant.
 */
export function defaultPatternForm(seed: ScopeSeed | null = null): PatternForm {
  return {
    kind: "linear",
    scope: defaultScopeMode(seed),
    scopeFeatures: seed === null ? [] : [seed],
    countInput: "3",
    direction: "+x",
    spacingInput: "10",
    axisDirection: "+z",
    axisPointXInput: "0",
    axisPointYInput: "0",
    axisPointZInput: "0",
    angleInput: "360",
  };
}

/** Trim trailing zeros for a UNITLESS value (an angle in degrees); -0 → "0". */
function formatDeg(value: number): string {
  return String(Object.is(value, -0) ? 0 : value);
}

/**
 * Seed the form from an existing pattern feature for editing (lengths in
 * `unit`). `features` is the tree, so a persisted `features` scope can be shown
 * by NAME rather than by uuid; omit it and the scope reads as it does on the
 * wire (an absent key is `body`).
 */
export function formFromPatternParams(
  params: PatternParams,
  unit: LengthUnit,
  features: readonly FeatureResponse[] = [],
): PatternForm {
  const base = defaultPatternForm();
  const scope = scopeFromParams(params.scope, features);
  base.scope = scope.mode;
  base.scopeFeatures = scope.features;
  const p = params.pattern;
  if (p.kind === "linear") {
    return {
      ...base,
      kind: "linear",
      countInput: String(p.count),
      direction: nearestPreset(p.direction),
      spacingInput: lengthInputValue(p.spacing_mm, unit),
    };
  }
  return {
    ...base,
    kind: "circular",
    countInput: String(p.count),
    axisDirection: nearestPreset(p.axis_direction),
    axisPointXInput: lengthInputValue(p.axis_point.x, unit),
    axisPointYInput: lengthInputValue(p.axis_point.y, unit),
    axisPointZInput: lengthInputValue(p.axis_point.z, unit),
    angleInput: formatDeg(p.angle_deg),
  };
}

/**
 * Parse the count field. `count` includes the seed, so a value below 2 repeats
 * nothing — we treat non-integers and anything under 2 as not-yet-valid so the
 * form does not submit a no-op.
 */
export function parseCount(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isInteger(value) || value < 2) return null;
  return value;
}

/** Field-level count message, or null when valid (empty is pending). */
export function countError(input: string): string | null {
  if (input.trim() === "") return null;
  return parseCount(input) === null
    ? "Count includes the seed — enter a whole number of 2 or more."
    : null;
}

/** Parse the spacing field to a positive canonical-mm step in `unit`, or null. */
export function parseSpacingMm(input: string, unit: LengthUnit): number | null {
  return parsePositiveLengthMm(input, unit);
}

/** Field-level spacing message, or null when valid (empty is pending). */
export function spacingError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parseSpacingMm(input, unit) === null
    ? "Spacing must be a positive length."
    : null;
}

/** Parse an axis-point coordinate → canonical mm in `unit` (0 / negative ok). */
export function parseCoordMm(input: string, unit: LengthUnit): number | null {
  return parseSignedLengthMm(input, unit);
}

/** Field-level coordinate message, or null when valid (empty is pending). */
export function coordError(input: string, unit: LengthUnit): string | null {
  if (input.trim() === "") return null;
  return parseCoordMm(input, unit) === null ? "Enter a length." : null;
}

/**
 * Build the `PatternParamsV1` from the form for the active mode, or null when a
 * required field is missing/invalid (the submit gate). Server-side rebuild
 * still validates geometry (disjoint copies, degenerate axes) — this only
 * guards the shape.
 */
export function buildPatternParams(
  form: PatternForm,
  unit: LengthUnit,
): PatternParams | null {
  const count = parseCount(form.countInput);
  if (count === null) return null;
  // ALWAYS sent, never omitted (pattern-scope §7.1): an absent `scope` key means
  // "the whole body" forever, so a dialog that leaves it out is authoring the
  // very ambiguity this row exists to remove. Note the key is `scope` and NOT
  // `features` — params models are pydantic-default `extra="ignore"`, so the
  // wrong spelling would validate, evaluate and silently give the old reading.
  const scope = buildScope(form.scope, form.scopeFeatures);
  if (scope === null) return null;
  if (form.kind === "linear") {
    const spacing = parseSpacingMm(form.spacingInput, unit);
    if (spacing === null) return null;
    return {
      pattern: {
        kind: "linear",
        direction: presetVec(form.direction),
        spacing_mm: spacing,
        count,
      },
      scope,
    };
  }
  const angle = parseAngleDeg(form.angleInput);
  const x = parseCoordMm(form.axisPointXInput, unit);
  const y = parseCoordMm(form.axisPointYInput, unit);
  const z = parseCoordMm(form.axisPointZInput, unit);
  if (angle === null || x === null || y === null || z === null) return null;
  return {
    pattern: {
      kind: "circular",
      axis_point: { x, y, z },
      axis_direction: presetVec(form.axisDirection),
      angle_deg: angle,
      count,
    },
    scope,
  };
}

/** True when the form can be submitted (all active-mode fields valid). */
export function canSubmitPattern(form: PatternForm, unit: LengthUnit): boolean {
  return buildPatternParams(form, unit) !== null;
}
