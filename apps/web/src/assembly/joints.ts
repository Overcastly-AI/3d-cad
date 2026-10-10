/**
 * Joints, the Fusion 360 / Onshape way of mating: a frame on each component
 * (a face centre, a hole centre, a point on an edge) and the motion left free
 * between them. This module is the pure half of the joint dialog: the motion
 * catalogue, the dialog's editable draft and its reducer, the mate / PATCH
 * bodies built from it, the "Revolute 1" names, and where each origin sits on
 * its part. Every wire shape comes from the generated client; nothing here
 * touches the DOM, so it unit-tests in node.
 */
import { formatLength, type LengthUnit, parseLength } from "@loft/design";

import type {
  JointMate,
  Mate,
  MateResponse,
  MateUpdate,
} from "../api/assemblies";
import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import { lengthInputValue } from "../units/length";
import type { Vec3 } from "./placement";

export type JointMotion = JointMate["motion"];
export type JointOrigin = JointMate["a"];
export type JointOriginKind = JointOrigin["kind"];
export type JointEdgeAt = NonNullable<JointOrigin["at"]>;
export type JointLimits = NonNullable<JointMate["limits"]>;
export type JointValue = NonNullable<JointMate["value"]>;

/** One motion on the dialog's picker. */
export interface JointMotionOption {
  motion: JointMotion;
  label: string;
  /** The solver handles it today; the rest are offered but disabled. */
  supported: boolean;
}

/**
 * Fusion's order. Cylindrical, planar and ball are shown so the vocabulary is
 * learnable, but disabled: the solver returns `mate_unsupported` for them.
 */
export const JOINT_MOTIONS: readonly JointMotionOption[] = [
  { motion: "rigid", label: "Rigid", supported: true },
  { motion: "revolute", label: "Revolute", supported: true },
  { motion: "slider", label: "Slider", supported: true },
  { motion: "cylindrical", label: "Cylindrical", supported: false },
  { motion: "planar", label: "Planar", supported: false },
  { motion: "ball", label: "Ball", supported: false },
];

const MOTION_LABEL = new Map(JOINT_MOTIONS.map((m) => [m.motion, m.label]));

/** Motions with one rotation value about the joint Z (the wire's rule). */
export function rotates(motion: JointMotion): boolean {
  return (
    motion === "revolute" || motion === "cylindrical" || motion === "planar"
  );
}

/** Motions with one translation value along the joint Z (the wire's rule). */
export function slides(motion: JointMotion): boolean {
  return motion === "slider" || motion === "cylindrical";
}

export function isJoint(mate: Mate): mate is JointMate {
  return mate.type === "joint";
}

// ——— names ————————————————————————————————————————————————————————————————

/**
 * Each joint's display name, "Revolute 1": its motion and its 1-based ordinal
 * among the joints of that motion, in mate order. The SAME derivation as the
 * documents service's `joint_label`, so the tree row and a refusal message
 * ("Revolute 1: 200° exceeds max 180°") name the joint identically.
 */
export function jointLabels(
  mates: readonly Pick<MateResponse, "id" | "mate">[],
): Map<string, string> {
  const counts = new Map<JointMotion, number>();
  const labels = new Map<string, string>();
  for (const row of mates) {
    if (!isJoint(row.mate)) continue;
    const n = (counts.get(row.mate.motion) ?? 0) + 1;
    counts.set(row.mate.motion, n);
    labels.set(row.id, `${MOTION_LABEL.get(row.mate.motion) ?? "Joint"} ${n}`);
  }
  return labels;
}

/** A degree reading without float dust or a signed zero. */
export function formatDegrees(deg: number): string {
  const rounded = Number.parseFloat(deg.toFixed(3));
  return `${rounded === 0 ? 0 : rounded}°`;
}

/** The value echo on a joint's tree row, or null while it is undriven. */
export function jointDetail(joint: JointMate, unit: LengthUnit): string | null {
  const value = joint.value;
  if (value === undefined) return null;
  if (rotates(joint.motion) && value.rot_deg != null) {
    return formatDegrees(value.rot_deg);
  }
  if (slides(joint.motion) && value.lin_mm != null) {
    return formatLength(value.lin_mm, unit);
  }
  return null;
}

/** A joint's free axes are all driven: it fixes B, though DOF still counts them. */
function drivenDof(joint: JointMate): number | null {
  const value = joint.value;
  let dof = 0;
  if (rotates(joint.motion)) {
    if (value?.rot_deg == null) return null;
    dof += 1;
  }
  if (slides(joint.motion)) {
    if (value?.lin_mm == null) return null;
    dof += 1;
  }
  return dof;
}

/**
 * "Positioned by Revolute 1" — what to say INSTEAD of "under constrained" when
 * every DOF the solver left is a joint axis the user has driven to a value.
 *
 * The solver counts hard rows only, so a driven hinge reports 1 DOF and
 * `under_constrained` (the Fusion way: you can still drag it). That is not a
 * warning, and the status must not read like one. The test is a count: the
 * remaining DOF equal the driven joint axes, and there is at least one. Null
 * whenever anything else is going on.
 */
export function positionedBy(
  status: string | null,
  remainingDof: number | null,
  mates: readonly Pick<MateResponse, "id" | "mate">[],
  failedMateIds: ReadonlySet<string>,
): string | null {
  if (status !== "under_constrained" || remainingDof === null) return null;
  const labels = jointLabels(mates);
  const names: string[] = [];
  let driven = 0;
  for (const row of mates) {
    if (!isJoint(row.mate) || failedMateIds.has(row.id)) continue;
    const dof = drivenDof(row.mate);
    if (dof === null || dof === 0) continue;
    driven += dof;
    names.push(labels.get(row.id) ?? "a joint");
  }
  if (driven === 0 || driven !== remainingDof) return null;
  return `Positioned by ${names.join(", ")}`;
}

// ——— where an origin sits ————————————————————————————————————————————————

const sub = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.x - b.x,
  y: a.y - b.y,
  z: a.z - b.z,
});
const dot = (a: Vec3, b: Vec3) => a.x * b.x + a.y * b.y + a.z * b.z;
const cross = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.y * b.z - a.z * b.y,
  y: a.z * b.x - a.x * b.z,
  z: a.x * b.y - a.y * b.x,
});

/**
 * The centre of a circular edge from its signature, part-local mm.
 *
 * A full circle's `end_a` is its seam vertex and its `midpoint` (length
 * parameter 0.5) the diametrically opposite point, so the centre is halfway
 * between them, exactly. An arc's centre is the circumcentre of its two ends
 * and its midpoint.
 */
export function circleCentre(signature: EdgeSignature): Vec3 {
  const a = signature.end_a;
  const m = signature.midpoint;
  const b = signature.end_b;
  const ab = sub(b, a);
  if (dot(ab, ab) < 1e-12) {
    return { x: (a.x + m.x) / 2, y: (a.y + m.y) / 2, z: (a.z + m.z) / 2 };
  }
  // Circumcentre of triangle (a, m, b).
  const u = sub(m, a);
  const v = sub(b, a);
  const n = cross(u, v);
  const nn = dot(n, n);
  if (nn < 1e-18) return m;
  const uu = dot(u, u);
  const vv = dot(v, v);
  const t1 = cross(n, u);
  const t2 = cross(v, n);
  const k = 1 / (2 * nn);
  return {
    x: a.x + (vv * t1.x + uu * t2.x) * k,
    y: a.y + (vv * t1.y + uu * t2.y) * k,
    z: a.z + (vv * t1.z + uu * t2.z) * k,
  };
}

/** Where an edge point sits: the solver's start is the signature's `end_a`. */
export function edgePoint(signature: EdgeSignature, at: JointEdgeAt): Vec3 {
  return at === "start"
    ? signature.end_a
    : at === "end"
      ? signature.end_b
      : signature.midpoint;
}

/** The origin's point on its part, part-local mm. */
export function originLocalPoint(origin: JointOrigin): Vec3 {
  const signature = origin.signature;
  if (origin.kind === "face_centre") {
    return (signature as PlanarFaceSignature).centroid;
  }
  const edge = signature as EdgeSignature;
  return origin.kind === "circle_centre"
    ? circleCentre(edge)
    : edgePoint(edge, origin.at ?? "mid");
}

/** One side of a joint as picked: everything but B's flip / quarter turns. */
export interface JointOriginPick {
  instanceId: string;
  kind: JointOriginKind;
  signature: PlanarFaceSignature | EdgeSignature;
  at: JointEdgeAt | null;
  /** Transient overlay key (`face-3`, `edge-5-mid`), for the selected cue. */
  key: string;
}

function toOrigin(
  pick: JointOriginPick,
  flip = false,
  quarterTurns = 0,
): JointOrigin {
  return {
    instance_id: pick.instanceId,
    kind: pick.kind,
    signature: pick.signature,
    at: pick.kind === "edge_point" ? pick.at : null,
    flip,
    quarter_turns: quarterTurns,
  };
}

// ——— the dialog draft —————————————————————————————————————————————————————

/** The dialog's fields, as typed (lengths in the document unit). */
export interface JointDraft {
  motion: JointMotion;
  flip: boolean;
  /** B's quarter turns about its Z, 0-3 (the "Rotate 90°" button). */
  quarterTurns: number;
  offset: string;
  angle: string;
  rotMin: string;
  rotMax: string;
  linMin: string;
  linMax: string;
  /** The drive: degrees for a rotating motion... */
  rotValue: string;
  /** ...and a length for a sliding one. Empty leaves the axis free. */
  linValue: string;
}

export type JointDraftField = Exclude<
  keyof JointDraft,
  "motion" | "flip" | "quarterTurns"
>;

export type JointDraftAction =
  | { type: "motion"; motion: JointMotion }
  | { type: "flip" }
  | { type: "rotate" }
  | { type: "field"; field: JointDraftField; value: string };

/** A new joint: Rigid, as Fusion's dialog opens, at zero offset and angle. */
export function newJointDraft(): JointDraft {
  return {
    motion: "rigid",
    flip: false,
    quarterTurns: 0,
    offset: "0",
    angle: "0",
    rotMin: "",
    rotMax: "",
    linMin: "",
    linMax: "",
    rotValue: "",
    linValue: "",
  };
}

const deg = (n: number | null | undefined) =>
  n == null ? "" : String(Number.parseFloat(n.toFixed(6)));
const len = (n: number | null | undefined, unit: LengthUnit) =>
  n == null ? "" : lengthInputValue(n, unit);

/** The draft for editing a stored joint. */
export function draftFromJoint(joint: JointMate, unit: LengthUnit): JointDraft {
  const limits = joint.limits ?? null;
  return {
    motion: joint.motion,
    flip: joint.b.flip,
    quarterTurns: joint.b.quarter_turns,
    offset: lengthInputValue(joint.offset_mm, unit),
    angle: deg(joint.angle_deg),
    rotMin: deg(limits?.rot_min_deg),
    rotMax: deg(limits?.rot_max_deg),
    linMin: len(limits?.lin_min_mm, unit),
    linMax: len(limits?.lin_max_mm, unit),
    rotValue: deg(joint.value?.rot_deg),
    linValue: len(joint.value?.lin_mm, unit),
  };
}

export function jointDraftReducer(
  draft: JointDraft,
  action: JointDraftAction,
): JointDraft {
  switch (action.type) {
    case "motion":
      return { ...draft, motion: action.motion };
    case "flip":
      return { ...draft, flip: !draft.flip };
    case "rotate":
      return { ...draft, quarterTurns: (draft.quarterTurns + 1) % 4 };
    case "field":
      return { ...draft, [action.field]: action.value };
  }
}

/** The fields this motion shows: limits and drive per free axis. */
export function visibleFields(motion: JointMotion): Set<JointDraftField> {
  const fields = new Set<JointDraftField>(["offset", "angle"]);
  if (rotates(motion)) {
    for (const f of ["rotMin", "rotMax", "rotValue"] as const) fields.add(f);
  }
  if (slides(motion)) {
    for (const f of ["linMin", "linMax", "linValue"] as const) fields.add(f);
  }
  return fields;
}

/** The draft as wire numbers. */
export interface ParsedJointDraft {
  offset_mm: number;
  angle_deg: number;
  limits: JointLimits | null;
  /** BOTH axes, always (JOINT-VALUE-MERGE): a PATCH value replaces both. */
  value: { rot_deg: number | null; lin_mm: number | null };
}

function parseDegreesField(input: string): number | null {
  const trimmed = input.trim().replace(/°$/, "");
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/**
 * Parse the draft: the wire numbers, or the visible fields that do not parse.
 * Offset and angle must be numbers; an empty limit is no bound and an empty
 * drive leaves the axis free. Hidden fields never reach the wire, so a stale
 * limit on an axis the motion does not free cannot be refused by the server.
 */
export function parseJointDraft(
  draft: JointDraft,
  unit: LengthUnit,
):
  | { ok: true; parsed: ParsedJointDraft }
  | { ok: false; invalid: Set<JointDraftField> } {
  const shown = visibleFields(draft.motion);
  const invalid = new Set<JointDraftField>();
  const optional = (
    field: JointDraftField,
    parse: (s: string) => number | null,
  ): number | null => {
    if (!shown.has(field) || draft[field].trim() === "") return null;
    const value = parse(draft[field]);
    if (value === null) invalid.add(field);
    return value;
  };
  const asLength = (s: string) => parseLength(s, unit);
  const offset = parseLength(draft.offset, unit);
  if (offset === null) invalid.add("offset");
  const angle = parseDegreesField(draft.angle);
  if (angle === null) invalid.add("angle");
  const limits: JointLimits = {
    rot_min_deg: optional("rotMin", parseDegreesField),
    rot_max_deg: optional("rotMax", parseDegreesField),
    lin_min_mm: optional("linMin", asLength),
    lin_max_mm: optional("linMax", asLength),
  };
  const value = {
    rot_deg: optional("rotValue", parseDegreesField),
    lin_mm: optional("linValue", asLength),
  };
  if (invalid.size > 0) return { ok: false, invalid };
  const anyLimit = Object.values(limits).some((v) => v !== null);
  return {
    ok: true,
    parsed: {
      offset_mm: offset as number,
      angle_deg: angle as number,
      limits: anyLimit ? limits : null,
      value,
    },
  };
}

/** The new joint the dialog describes (POST /mates). */
export function buildJointMate(
  draft: JointDraft,
  parsed: ParsedJointDraft,
  a: JointOriginPick,
  b: JointOriginPick,
): JointMate {
  return {
    type: "joint",
    motion: draft.motion,
    a: toOrigin(a),
    b: toOrigin(b, draft.flip, draft.quarterTurns),
    offset_mm: parsed.offset_mm,
    angle_deg: parsed.angle_deg,
    limits: parsed.limits,
    value: parsed.value,
  };
}

/**
 * The PATCH for an edited joint. Every editable field is sent, limits as an
 * explicit null when cleared (absent would keep the old ones) and the value
 * with both axes. The motion cannot change in place (MateUpdate has none).
 */
export function jointUpdate(
  draft: JointDraft,
  parsed: ParsedJointDraft,
  expectedVersion: number,
): MateUpdate {
  return {
    expected_version: expectedVersion,
    offset_mm: parsed.offset_mm,
    angle_deg: parsed.angle_deg,
    flip: draft.flip,
    quarter_turns: draft.quarterTurns,
    limits: parsed.limits,
    value: parsed.value,
  };
}

/** The stored joint with an edit applied, for the server-solved preview. */
export function applyJointEdit(
  joint: JointMate,
  draft: JointDraft,
  parsed: ParsedJointDraft,
): JointMate {
  return {
    ...joint,
    offset_mm: parsed.offset_mm,
    angle_deg: parsed.angle_deg,
    limits: parsed.limits,
    value: parsed.value,
    b: { ...joint.b, flip: draft.flip, quarter_turns: draft.quarterTurns },
  };
}

/** A drive value on the joint's one free axis, the other axis explicitly null. */
export function driveValue(
  motion: JointMotion,
  value: number,
): { rot_deg: number | null; lin_mm: number | null } {
  return rotates(motion)
    ? { rot_deg: value, lin_mm: null }
    : { rot_deg: null, lin_mm: value };
}

/** The wire's own bounds on any joint angle / length (`loft_wire.joints`). */
const MAX_JOINT_ANGLE_DEG = 3600;
const MAX_JOINT_LENGTH_MM = 100_000;

/**
 * The [min, max] the drag stops at for the joint's free axis: the joint's
 * limits where it has them, the wire's outer bounds where it does not.
 */
export function driveLimits(joint: JointMate): [number, number] {
  const limits = joint.limits;
  const turning = rotates(joint.motion);
  const outer = turning ? MAX_JOINT_ANGLE_DEG : MAX_JOINT_LENGTH_MM;
  const [lo, hi] = turning
    ? [limits?.rot_min_deg, limits?.rot_max_deg]
    : [limits?.lin_min_mm, limits?.lin_max_mm];
  return [lo ?? -outer, hi ?? outer];
}
