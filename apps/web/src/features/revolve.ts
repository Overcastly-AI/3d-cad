/**
 * Revolve-feature view logic — the pure functions the RevolveEditor and the
 * PartPage share, kept out of the component so they can be unit-tested without
 * a DOM (the extrude module's twin). Param shapes come from the generated
 * client (CLAUDE.md DRY rule); the builders live in `../api/parts`.
 *
 * The revolve's parametric handle is the sweep ANGLE (wearing brass, like
 * extrude's distance). Its one new field over extrude is the AXIS. We offer the
 * axes as a native ruled select rather than a viewport pick: keyboard-first,
 * deterministically testable, and it reuses the title-block vocabulary the
 * profile picker already speaks — no new selection layer.
 *
 * TWO KINDS OF AXIS SHARE THAT SELECT (REACH-1), because the wire type has two
 * (`RevolveAxis` = `SketchLineAxis | OriginAxis`) and only one of them was ever
 * offered here:
 *
 * * a LINE entity of the profile's own sketch — a construction centerline is
 *   the natural axis, and it is the only axis that can also close a
 *   half-profile; and
 * * a WORLD ORIGIN axis (X / Y / Z), which needs nothing drawn. This is the one
 *   that makes a plain closed rectangle turnable: before it, a sketch with no
 *   centerline defaulted to a PROFILE EDGE and quietly built a disc.
 *
 * An origin axis must LIE IN the profile's sketch plane or the kernel refuses
 * it by name (`axis_not_in_sketch_plane`), so {@link axisOptions} runs the same
 * two tests the kernel runs (`geometry.kernel.revolve._world_axis_to_sketch_line`)
 * against the client's own copy of the plane math, at the same documented
 * tolerance: the axis POINT must be in the plane, and the axis DIRECTION must
 * have no component along the plane normal. An axis that fails either is still
 * LISTED — disabled, with the reason in its own label — because a choice that
 * vanishes teaches nobody why. One plane-math source, two renderers.
 *
 * ORDERING IS THE PROPOSAL. The list is ranked by how likely each axis is to be
 * the turn the user meant, and {@link defaultAxisId} is simply "the first one
 * that is choosable" — so the ranking cannot drift away from the default:
 *
 *   1. a construction centerline  (drawn intent — an axis is what it IS)
 *   2. an in-plane origin axis    (rebuild-stable; nothing upstream can move it)
 *   3. a profile edge             (legal, but rarely what was meant)
 *   4. an out-of-plane origin axis (disabled — shown with its refusal)
 */
import type {
  DatumParams,
  FeatureResponse,
  RevolveParams,
  SketchEntity,
} from "../api/parts";
import {
  PLANE_BASES,
  resolveDatumBasis,
  type PlaneBasis,
  type Vec3Tuple,
} from "../sketch/plane";
import {
  defaultProfileId,
  profileOptions,
  type ProfileOption,
} from "./extrude";
import { fieldBlocker } from "./submitBlocker";

export { defaultProfileId, profileOptions };
export type { ProfileOption };

export type RevolveOperation = RevolveParams["operation"];
export type RevolveDirection = RevolveParams["direction"];
/**
 * The axis-of-revolution union exactly as the wire declares it — derived from
 * the generated params rather than restated, so a new axis variant is a type
 * error here rather than a silently unhandled case (CLAUDE.md DRY rule).
 */
export type RevolveAxisRef = RevolveParams["axis"];
/** The world origin axis names (X / Y / Z), from the same generated union. */
export type OriginAxisName = Extract<
  RevolveAxisRef,
  { kind: "origin_axis" }
>["axis"];

/** A LINE entity narrowed out of the sketch-entity union. */
type LineEntity = Extract<SketchEntity, { kind: "line" }>;

/** The editable revolve form state (angle kept as raw text — unit input). */
export interface RevolveForm {
  profileFeatureId: string;
  /**
   * The chosen {@link AxisOption}'s `id` — a sketch entity id for a line axis,
   * or `origin:X|Y|Z` for a world origin axis. It is an OPTION key, not a wire
   * value: {@link axisRef} turns it back into the persisted `RevolveAxis`.
   */
  axisId: string;
  angleInput: string;
  operation: RevolveOperation;
  direction: RevolveDirection;
  /** "Merge result" (multi-body §MB-1) — see `ExtrudeForm.merge`. */
  merge: boolean;
}

/** One choosable axis of revolution — a sketch line, or a world origin axis. */
export interface AxisOption {
  /**
   * Select value: the sketch-local entity id for a line, or `origin:X|Y|Z` for
   * a world axis. Unique within one option list ({@link axisOptions} drops an
   * origin entry whose synthetic id an entity has somehow taken).
   */
  id: string;
  /** Human descriptor, in the select's `A · B · C` grammar. */
  label: string;
  /** Construction lines — centerlines — are the natural axis; ranked first. */
  construction: boolean;
  /** Which half of the `RevolveAxis` union this option persists. */
  kind: RevolveAxisRef["kind"];
  /** The exact wire value this option means — the editor never rebuilds it. */
  ref: RevolveAxisRef;
  /**
   * Why this axis cannot be chosen, or null when it can. Set only for an origin
   * axis the kernel would refuse (`axis_not_in_sketch_plane`); it is shown, not
   * hidden, so the refusal is legible before the round-trip rather than after.
   */
  reason: string | null;
}

/** A line counts as axis-aligned within this fraction of its length. */
const COLLINEAR_EPS = 1e-3;

/**
 * Clearance for "the axis lies in the sketch plane", mirroring the kernel's
 * `AXIS_CLEARANCE_TOL` (1e-7) so the client offers exactly what the server
 * accepts. Both halves use it: the point test in mm, the direction test on a
 * unit vector's normal component (a sine, already dimensionless).
 */
const AXIS_CLEARANCE_TOL = 1e-7;

/** Prefix of an origin axis's synthetic option id (`origin:Z`). */
const ORIGIN_AXIS_PREFIX = "origin:";

/**
 * The three world origin axes in SPINDLE order — the order the group is ranked
 * and listed in, and therefore which one a plain profile is proposed to turn
 * about. Z first is the lathe convention (the spindle is Z in every CAM post
 * and on every turned-part drawing), not alphabetical order; both of a sketch's
 * two in-plane origin axes make a legal solid, so the tie is broken by what a
 * machinist means by "turned", never by the alphabet.
 */
const ORIGIN_AXES: readonly OriginAxisName[] = ["Z", "Y", "X"];

/**
 * World direction of each origin axis — the client's copy of the kernel's
 * `ORIGIN_AXIS_DIRECTIONS`. The axes pass through the world origin, so a
 * direction fully determines each line.
 */
const ORIGIN_AXIS_DIRECTIONS: Record<OriginAxisName, Vec3Tuple> = {
  X: [1, 0, 0],
  Y: [0, 1, 0],
  Z: [0, 0, 1],
};

/** The option id an origin axis is selected by. */
export function originAxisId(axis: OriginAxisName): string {
  return `${ORIGIN_AXIS_PREFIX}${axis}`;
}

/** The default new-revolve form: 360° full solid, add, normal — the common turn. */
export function defaultRevolveForm(
  profileFeatureId: string,
  axisId: string,
): RevolveForm {
  return {
    profileFeatureId,
    axisId,
    angleInput: "360",
    operation: "add",
    direction: "normal",
    merge: true,
  };
}

/**
 * Seed the form from an existing revolve feature for editing.
 *
 * Both halves of the `RevolveAxis` union round-trip (REACH-1). Until the origin
 * axes were offered, the `origin_axis` half seeded BLANK — deliberate
 * degradation, documented as such — which meant a revolve authored through the
 * API could be opened but not saved. The union is total here now, so opening a
 * revolve shows the axis it actually has.
 */
export function formFromRevolveParams(params: RevolveParams): RevolveForm {
  return {
    profileFeatureId: params.profile.feature_id,
    axisId:
      params.axis.kind === "sketch_line"
        ? params.axis.entity
        : originAxisId(params.axis.axis),
    angleInput: formatAngleInput(params.angle_deg),
    operation: params.operation,
    direction: params.direction,
    merge: params.merge,
  };
}

/**
 * The wire axis an option id means, or null when no option carries that id.
 *
 * Resolution goes through the OPTION LIST rather than by parsing the id, so the
 * `origin:` prefix stays a display-layer key: the editor can never hand the
 * server an axis that was not on the list it drew (and cannot mint a
 * `sketch_line` reference to an entity that is gone).
 */
export function axisRef(
  options: readonly AxisOption[],
  axisId: string,
): RevolveAxisRef | null {
  return options.find((o) => o.id === axisId)?.ref ?? null;
}

/** Why the chosen axis cannot be used, or null when it can (or is unknown). */
export function axisReason(
  options: readonly AxisOption[],
  axisId: string,
): string | null {
  return options.find((o) => o.id === axisId)?.reason ?? null;
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

/**
 * True when the form can be submitted: a profile, a valid angle, and an axis
 * that is on `options` AND choosable. Passing the options makes the gate the
 * same fact the select shows — a disabled axis (an origin axis the kernel would
 * refuse) blocks Create here instead of failing the rebuild afterwards.
 */
export function canSubmitRevolve(
  form: RevolveForm,
  options: readonly AxisOption[],
): boolean {
  return revolveSubmitBlocker(form, options) === null;
}

/**
 * WHY the revolve cannot be created yet, or null when it can (REASON-GATE-1 —
 * see `submitBlocker.ts` for the rule and the 48-character budget).
 *
 * A REFUSED axis (an origin axis the kernel would reject) is a different
 * situation from an unchosen one and says so: the option itself carries the full
 * reason in its label, so the cell says what to do about it instead of repeating
 * a sentence that is already on screen two rows up.
 */
export function revolveSubmitBlocker(
  form: RevolveForm,
  options: readonly AxisOption[],
): string | null {
  if (form.profileFeatureId === "") return "Choose a sketch profile.";
  const axis = options.find((o) => o.id === form.axisId);
  if (axis === undefined) return "Choose the axis to revolve about.";
  if (axis.reason !== null) return "Choose an axis in the sketch plane.";
  return fieldBlocker(form.angleInput, parseAngleDeg(form.angleInput), "angle");
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

function dot(a: Vec3Tuple, b: Vec3Tuple): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/**
 * Where the profile sketch's plane sits, in the kernel (build123d) frame, or
 * null when the client cannot place it here.
 *
 * Null covers the `on_face` datum and the face-picked midplane side, whose
 * bases live in the scene frame the sketch-on-face flow owns. The origin group
 * is simply not offered for those sketches: an origin axis lying in a plane
 * adopted from an arbitrary model face is a coincidence, and guessing would
 * mean either hiding a legal axis or offering an illegal one.
 */
function sketchPlaneBasis(
  features: readonly FeatureResponse[],
  profile: Extract<FeatureResponse["feature"], { type: "sketch" }>,
): PlaneBasis | null {
  const plane = profile.params.plane;
  if (plane.kind === "datum_plane") return PLANE_BASES[plane.plane];
  const datums = new Map<string, DatumParams>();
  for (const feature of features) {
    if (feature.feature.type === "datum")
      datums.set(feature.id, feature.feature.params);
  }
  return resolveDatumBasis(plane.feature_id, datums);
}

/**
 * Why the world axis `direction` (through the world origin) cannot be the axis
 * of a sketch on `basis`, or null when it can.
 *
 * The two tests are the kernel's two tests, kept separate for the reason the
 * kernel keeps them separate: they fail for different reasons and the user
 * deserves to be told which. The axis POINT (the world origin) must be in the
 * plane — otherwise the axis is parallel to the plane but offset from it, and
 * the swept body's section is nothing anyone drew. The axis DIRECTION must have
 * no component along the plane normal — otherwise the axis pierces the plane
 * and the revolution self-intersects.
 */
function originAxisReason(
  basis: PlaneBasis,
  direction: Vec3Tuple,
): string | null {
  if (Math.abs(dot(basis.origin, basis.normal)) > AXIS_CLEARANCE_TOL)
    return "Not in the sketch plane — the plane is offset from the origin.";
  if (Math.abs(dot(direction, basis.normal)) > AXIS_CLEARANCE_TOL)
    return "Not in the sketch plane — it is the plane normal.";
  return null;
}

/**
 * A full-sentence reason as the second clause of an option label: the trailing
 * period goes (labels are not sentences) and the first letter drops to lower
 * case after the `·`. Derived rather than written twice, so the cell's status
 * line and the option that produced it cannot drift apart.
 */
function reasonClause(reason: string): string {
  const trimmed = reason.replace(/\.$/, "");
  return trimmed.charAt(0).toLowerCase() + trimmed.slice(1);
}

/**
 * The origin-axis options for a sketch on `basis`, in {@link ORIGIN_AXES} order.
 *
 * The label names the axis the way the VIEWPORT names it — the origin triad
 * engraves a bare `X`/`Y`/`Z` at each positive end (`viewport/OriginGeometry`),
 * so "Z axis" is a thing the user can look at, where "origin_axis: Z" is a
 * thing the wire says. One vocabulary across both renderers.
 */
function originAxisOptions(basis: PlaneBasis): AxisOption[] {
  return ORIGIN_AXES.map((axis) => {
    const reason = originAxisReason(basis, ORIGIN_AXIS_DIRECTIONS[axis]);
    return {
      id: originAxisId(axis),
      construction: false,
      kind: "origin_axis" as const,
      ref: { kind: "origin_axis" as const, axis },
      reason,
      label:
        reason === null
          ? `${axis} axis · through the origin`
          : `${axis} axis · ${reasonClause(reason)}`,
    };
  });
}

/**
 * The axes of revolution offered for the given profile sketch, ranked by how
 * likely each is to be the turn the user meant (see the module docstring):
 * construction centerlines, then in-plane origin axes, then profile edges, then
 * the origin axes the kernel would refuse — listed disabled, with the reason.
 *
 * Empty only when the profile isn't a sketch; a sketch on a placeable plane
 * always has at least the three origin axes, which is what removes the old dead
 * end ("this sketch has no line to revolve about") for a plain closed profile.
 */
export function axisOptions(
  features: readonly FeatureResponse[],
  profileFeatureId: string,
): AxisOption[] {
  const profile = features.find((f) => f.id === profileFeatureId);
  if (profile === undefined || profile.feature.type !== "sketch") return [];
  const lines: AxisOption[] = profile.feature.params.entities
    .filter((e): e is LineEntity => e.kind === "line")
    .map((line) => ({
      id: line.id,
      construction: line.construction === true,
      kind: "sketch_line" as const,
      ref: { kind: "sketch_line" as const, entity: line.id },
      reason: null,
      label: axisLabel(line),
    }))
    .sort((a, b) => a.id.localeCompare(b.id));
  const basis = sketchPlaneBasis(features, profile.feature);
  // Entity ids are free-form strings, so an entity COULD be named `origin:Z`.
  // The line wins that id (it is real geometry); the shadowed origin axis is
  // dropped rather than duplicating a select value.
  const taken = new Set(lines.map((l) => l.id));
  const origins =
    basis === null
      ? []
      : originAxisOptions(basis).filter((o) => !taken.has(o.id));
  // Stable sort by rank ONLY: within a rank the input order already carries the
  // intended order (lines by entity id, origin axes in spindle order), and a
  // second key here would silently re-alphabetize the origin group.
  return [...lines, ...origins].sort((a, b) => axisRank(a) - axisRank(b));
}

/** Rank an axis by how likely it is to be the intended turn (lower is better). */
function axisRank(option: AxisOption): number {
  if (option.reason !== null) return 3; // refused — shown last, disabled
  if (option.construction) return 0; // a drawn centerline IS an axis
  if (option.kind === "origin_axis") return 1; // rebuild-stable, needs nothing
  return 2; // a profile edge: legal, rarely meant
}

/**
 * The proposed axis: the first CHOOSABLE option, i.e. the top of the ranking
 * {@link axisOptions} already sorted by. Deriving it from the list rather than
 * re-deciding here is what keeps the proposal and the select's first row the
 * same fact. `""` only when nothing is choosable at all.
 */
export function defaultAxisId(options: readonly AxisOption[]): string {
  return options.find((o) => o.reason === null)?.id ?? "";
}
