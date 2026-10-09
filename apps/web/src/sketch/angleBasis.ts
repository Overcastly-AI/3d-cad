/**
 * The plane-at-an-angle datum (`kind: "angle"`, DATUM-PLANE-ANGLE) on the
 * client: the exact port of the kernel's
 * `geometry.kernel.datum_angle.plane_at_angle` (RESEARCH §18), so a sketch on
 * an angled plane draws where the server builds it.
 *
 * Fusion 360's Plane at Angle / SolidWorks' Plane "At angle": the plane through
 * a line, turned about it from a reference plane. Normal = the reference normal
 * turned `angleDeg` RIGHT-HANDED about the line direction (Rodrigues with
 * d·n = 0), re-orthogonalised against d; `flip` negates it. Basis: u = the line
 * direction, origin = the line's point nearest the world origin, v = n × u.
 * The line must be parallel to the reference (|d·n| ≤ 1e-9, the kernel's
 * bound); otherwise there is no plane, and the server says
 * `datum_line_not_parallel`.
 *
 * Every vector here is in the KERNEL frame (Z-up), like the rest of the datum
 * algebra in `./plane`; the scene rotation is applied once, at its boundary.
 */
import {
  addScaled,
  cross,
  dot,
  negate,
  scale,
  sub,
  unit,
  type Vec3,
} from "@loft/design";
import type { components } from "@loft/ts-client/gateway";

import type { PlaneBasis } from "./plane";

export type DatumAngleParams = components["schemas"]["DatumAngleParams"];
/** The line slot of a plane at an angle (sketch line, model edge, axis). */
export type DatumAngleLine = DatumAngleParams["line"];

/** The kernel's `DATUM_LINE_PARALLEL_TOLERANCE`. */
export const DATUM_LINE_PARALLEL_TOLERANCE = 1e-9;

/** A resolved line: a point on it and its direction (any length). */
export interface AngleLine {
  point: Vec3;
  direction: Vec3;
}

/** World direction of each origin axis. */
export const ORIGIN_AXIS_DIRECTIONS: Record<"X" | "Y" | "Z", Vec3> = {
  X: [1, 0, 0],
  Y: [0, 1, 0],
  Z: [0, 0, 1],
};

/**
 * The plane through `line` at `angleDeg` from a reference whose normal is
 * `referenceNormal`, or null when the line has no direction or is not
 * parallel to the reference (the server refuses those; the client draws
 * nothing rather than a plane the server will not build).
 */
export function angleBasis(
  line: AngleLine,
  referenceNormal: Vec3,
  angleDeg: number,
  flip: boolean,
): PlaneBasis | null {
  const d = unit(line.direction);
  const n = unit(referenceNormal);
  if (d === null || n === null) return null;
  if (Math.abs(dot(d, n)) > DATUM_LINE_PARALLEL_TOLERANCE) return null;
  const radians = (angleDeg * Math.PI) / 180;
  const turned = addScaled(
    scale(n, Math.cos(radians)),
    cross(d, n),
    Math.sin(radians),
  );
  const normalized = unit(sub(turned, scale(d, dot(turned, d))));
  if (normalized === null) return null;
  const normal = flip ? negate(normalized) : normalized;
  const origin = sub(line.point, scale(d, dot(line.point, d)));
  return { u: d, v: cross(normal, d), normal, origin };
}

/** A line from an origin axis (through the world origin). */
export function originAxisLine(axis: "X" | "Y" | "Z"): AngleLine {
  return { point: [0, 0, 0], direction: ORIGIN_AXIS_DIRECTIONS[axis] };
}

/**
 * A line from a picked edge's stored signature, `end_a` → `end_b` (the
 * kernel's sense). Null for a curved edge. Like an `on_face` datum's face, it
 * reads the signature as picked; the server re-finds the edge on rebuild.
 */
export function edgeLine(
  line: Extract<DatumAngleLine, { kind: "subshape" }>,
): AngleLine | null {
  const s = line.selector.signature;
  if (s.curve !== "line") return null;
  const a: Vec3 = [s.end_a.x, s.end_a.y, s.end_a.z];
  const b: Vec3 = [s.end_b.x, s.end_b.y, s.end_b.z];
  return { point: a, direction: sub(b, a) };
}
