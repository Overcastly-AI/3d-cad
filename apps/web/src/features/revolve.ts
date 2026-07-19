/**
 * Revolve-feature view logic — the pure functions the RevolveEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM (the extrude module's twin). Param shapes come from the generated
 * client (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * The revolve's parametric handle is the sweep ANGLE (wearing brass, like
 * extrude's distance). Its one new field over extrude is the AXIS — a line
 * entity of the profile's own sketch (a construction centerline is the natural
 * axis of revolution). We offer the sketch's line entities as choices,
 * construction lines first, rather than a viewport pick: a native ruled select
 * is keyboard-first, deterministically testable, and reuses the title-block
 * vocabulary the profile picker already speaks — no new selection layer.
 */
import type {
  FeatureResponse,
  RevolveParams,
  SketchEntity,
} from "../api/parts";
import {
  defaultProfileId,
  profileOptions,
  type ProfileOption,
} from "./extrude";

export { defaultProfileId, profileOptions };
export type { ProfileOption };

export type RevolveOperation = RevolveParams["operation"];
export type RevolveDirection = RevolveParams["direction"];

/** A LINE entity narrowed out of the sketch-entity union. */
type LineEntity = Extract<SketchEntity, { kind: "line" }>;

/** The editable revolve form state (angle kept as raw text — unit input). */
export interface RevolveForm {
  profileFeatureId: string;
  axisEntityId: string;
  angleInput: string;
  operation: RevolveOperation;
  direction: RevolveDirection;
  /** "Merge result" (multi-body §MB-1) — see `ExtrudeForm.merge`. */
  merge: boolean;
}

/** One line entity of the profile sketch, offered as an axis of revolution. */
export interface AxisOption {
  /** Sketch-local entity id (the persisted `RevolveAxis.entity`). */
  id: string;
  /** Human descriptor: orientation · length · construction/edge (id). */
  label: string;
  /** Construction lines — centerlines — are the natural axis; ranked first. */
  construction: boolean;
}

/** A line counts as axis-aligned within this fraction of its length. */
const COLLINEAR_EPS = 1e-3;

/** The default new-revolve form: 360° full solid, add, normal — the common turn. */
export function defaultRevolveForm(
  profileFeatureId: string,
  axisEntityId: string,
): RevolveForm {
  return {
    profileFeatureId,
    axisEntityId,
    angleInput: "360",
    operation: "add",
    direction: "normal",
    merge: true,
  };
}

/** Seed the form from an existing revolve feature for editing. */
export function formFromRevolveParams(params: RevolveParams): RevolveForm {
  return {
    profileFeatureId: params.profile.feature_id,
    axisEntityId: params.axis.entity,
    angleInput: formatAngleInput(params.angle_deg),
    operation: params.operation,
    direction: params.direction,
    merge: params.merge,
  };
}

/** Trim trailing zeros so 360 shows as "360", not "360.000". */
export function formatAngleInput(angleDeg: number): string {
  return String(angleDeg);
}

/**
 * Parse the angle field to a sweep in (0, 360] degrees, or null when it is
 * empty, non-numeric, or out of range (0 is no sweep; >360 self-overlaps).
 */
export function parseAngleDeg(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0 || value > 360) return null;
  return value;
}

/** Field-level validation message for the angle, or null when it is valid. */
export function angleError(input: string): string | null {
  if (input.trim() === "") return null; // empty is pending, not yet wrong
  return parseAngleDeg(input) === null
    ? "Angle must be more than 0 and at most 360 degrees."
    : null;
}

/** True when the form can be submitted (a profile, an axis, a valid angle). */
export function canSubmitRevolve(form: RevolveForm): boolean {
  return (
    form.profileFeatureId !== "" &&
    form.axisEntityId !== "" &&
    parseAngleDeg(form.angleInput) !== null
  );
}

/** Round a millimetre length for a compact axis label. */
function roundLength(mm: number): string {
  return Number.isInteger(mm) ? String(mm) : mm.toFixed(1);
}

/** Describe a line by orientation, length, and construction status. */
function axisLabel(line: LineEntity): string {
  const dx = line.end.x - line.start.x;
  const dy = line.end.y - line.start.y;
  const length = Math.hypot(dx, dy);
  const orientation =
    Math.abs(dy) <= Math.abs(dx) * COLLINEAR_EPS
      ? "Horizontal"
      : Math.abs(dx) <= Math.abs(dy) * COLLINEAR_EPS
        ? "Vertical"
        : "Angled";
  const kind = line.construction ? "construction" : "profile edge";
  return `${orientation} · ${roundLength(length)} mm · ${kind} (${line.id})`;
}

/**
 * The line entities of the given profile sketch, offered as axes of revolution.
 * Construction lines (centerlines — exactly what an axis of revolution is)
 * come first; the rest follow in id order. Empty when the profile isn't a
 * sketch or has no line entities.
 */
export function axisOptions(
  features: readonly FeatureResponse[],
  profileFeatureId: string,
): AxisOption[] {
  const profile = features.find((f) => f.id === profileFeatureId);
  if (profile === undefined || profile.feature.type !== "sketch") return [];
  const lines = profile.feature.params.entities.filter(
    (e): e is LineEntity => e.kind === "line",
  );
  return lines
    .map((line) => ({
      id: line.id,
      construction: line.construction === true,
      label: axisLabel(line),
    }))
    .sort((a, b) =>
      a.construction !== b.construction
        ? a.construction
          ? -1
          : 1
        : a.id.localeCompare(b.id),
    );
}

/** Default axis: the first construction line (the centerline), else the first. */
export function defaultAxisId(options: readonly AxisOption[]): string {
  const construction = options.find((o) => o.construction);
  if (construction !== undefined) return construction.id;
  return options.length > 0 ? (options[0]?.id ?? "") : "";
}
