/**
 * Dragging a jointed part along its free DOF: the pointer is projected onto
 * the joint's axis, never moved freely. A revolute turns about the axis by the
 * angle the pointer sweeps on the plane through the axis point normal to it; a
 * slider runs along the axis by the pointer ray's closest approach to it.
 *
 * Everything here is in the KERNEL world frame (Z up, mm): `axis_world` from
 * the solve is in it, and so are the placements. The viewport's rays are
 * converted at the boundary (`sceneRayToKernel`). Pure: three's maths types run
 * headless, so this is unit-tested in node.
 */
import { Quaternion, Vector3 } from "three";

import { type Placement, scenePointToOcct, type Vec3 } from "./placement";

/** A line in the kernel world frame: a point on it and its unit direction. */
export interface JointAxis {
  point: Vec3;
  dir: Vec3;
}

export interface Ray {
  origin: Vec3;
  dir: Vec3;
}

const v = (p: Vec3) => new Vector3(p.x, p.y, p.z);
const plain = (p: Vector3): Vec3 => ({ x: p.x, y: p.y, z: p.z });

/** A part-local point placed in the world by a placement. */
export function worldPoint(placement: Placement, local: Vec3): Vec3 {
  const q = placement.orientation;
  const rotated = v(local).applyQuaternion(
    new Quaternion(q.x, q.y, q.z, q.w).normalize(),
  );
  return plain(rotated.add(v(placement.position)));
}

/** A scene-frame (Y-up) ray as a kernel-frame (Z-up) one. */
export function sceneRayToKernel(
  origin: readonly [number, number, number],
  dir: readonly [number, number, number],
): Ray {
  const d = scenePointToOcct(dir);
  const length = Math.hypot(d.x, d.y, d.z) || 1;
  return {
    origin: scenePointToOcct(origin),
    dir: { x: d.x / length, y: d.y / length, z: d.z / length },
  };
}

/** Two unit vectors spanning the plane normal to `n`, with e1 × e2 = n. */
function planeBasis(n: Vector3): [Vector3, Vector3] {
  const ax = Math.abs(n.x);
  const ay = Math.abs(n.y);
  const az = Math.abs(n.z);
  // The world axis least aligned with n, so the cross product is well-sized.
  const seed =
    ax <= ay && ax <= az
      ? new Vector3(1, 0, 0)
      : ay <= az
        ? new Vector3(0, 1, 0)
        : new Vector3(0, 0, 1);
  const e1 = seed.sub(n.clone().multiplyScalar(seed.dot(n))).normalize();
  const e2 = n.clone().cross(e1).normalize();
  return [e1, e2];
}

/** Below this |ray · normal| the plane is edge-on and the angle is unreliable. */
const EDGE_ON = 1e-3;

/**
 * The angle (radians, right-handed about the axis) of where the ray meets the
 * plane through the axis point normal to the axis — or null when the plane is
 * edge-on to the ray, or the hit is behind the eye or on the axis itself.
 */
export function rayAngleAbout(axis: JointAxis, ray: Ray): number | null {
  const n = v(axis.dir).normalize();
  const d = v(ray.dir);
  const denom = d.dot(n);
  if (Math.abs(denom) < EDGE_ON) return null;
  const t = v(axis.point).sub(v(ray.origin)).dot(n) / denom;
  if (t < 0) return null;
  const hit = v(ray.origin).addScaledVector(d, t).sub(v(axis.point));
  if (hit.lengthSq() < 1e-12) return null;
  const [e1, e2] = planeBasis(n);
  return Math.atan2(hit.dot(e2), hit.dot(e1));
}

/**
 * How far along the axis (mm, from its point) the ray passes closest — or null
 * when the ray runs along the axis and there is no single closest point.
 */
export function rayParamAlong(axis: JointAxis, ray: Ray): number | null {
  const a = v(axis.dir).normalize();
  const d = v(ray.dir).normalize();
  const w = v(axis.point).sub(v(ray.origin));
  const b = a.dot(d);
  const denom = 1 - b * b;
  if (denom < 1e-6) return null;
  // Closest points of two lines p + s·a and o + t·d: s = (b·(w·d) − (w·a)) / (1 − b²).
  return (b * w.dot(d) - w.dot(a)) / denom;
}

/** The signed change from `previous` to `next`, wrapped into (−π, π]. */
export function wrapDelta(previous: number, next: number): number {
  let delta = next - previous;
  while (delta > Math.PI) delta -= 2 * Math.PI;
  while (delta <= -Math.PI) delta += 2 * Math.PI;
  return delta;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export interface JointDragStart {
  motion: "revolute" | "slider";
  axis: JointAxis;
  /** The joint's value at the press (degrees or mm). */
  value: number;
  /** The drag stops here (`driveLimits`). */
  min: number;
  max: number;
  /** The pointer ray at the press. */
  ray: Ray;
  /** The point pressed on the part (kernel frame), when there is one. */
  grab?: Vec3;
}

export interface JointDrag {
  /** The value for the pointer's ray now, or null while it cannot be read. */
  move: (ray: Ray) => number | null;
}

/** Below this the value is float noise, not a turn (degrees or mm). */
const VALUE_STEP = 1e-4;
const snapValue = (n: number) => {
  const r = Math.round(n / VALUE_STEP) * VALUE_STEP;
  return Number.parseFloat(r.toFixed(4)) || 0;
};

/**
 * Begin a drag: returns a reader turning each later ray into the joint value,
 * clamped to the limits. A revolute accumulates the swept angle frame to frame
 * (so a drag can wind past ±180° up to its limits); a slider reads the closest
 * approach afresh each time. Null from the press means the press itself could
 * not be read (an edge-on plane): there is nothing to drag from.
 */
export function beginJointDrag(start: JointDragStart): JointDrag | null {
  if (start.motion === "revolute") {
    // The sweep is read on the plane through the GRABBED point, so the point
    // pressed stays under the cursor as the part turns — the plane through the
    // axis origin would let it drift on a part that stands proud of it.
    const dir = v(start.axis.dir).normalize();
    const lift =
      start.grab === undefined
        ? 0
        : v(start.grab).sub(v(start.axis.point)).dot(dir);
    const plane: JointAxis = {
      point: plain(v(start.axis.point).addScaledVector(dir, lift)),
      dir: start.axis.dir,
    };
    let previous = rayAngleAbout(plane, start.ray);
    if (previous === null) return null;
    let swept = 0;
    return {
      move: (ray) => {
        const angle = rayAngleAbout(plane, ray);
        if (angle === null || previous === null) return null;
        swept += wrapDelta(previous, angle);
        previous = angle;
        const degrees = start.value + (swept * 180) / Math.PI;
        return snapValue(clamp(degrees, start.min, start.max));
      },
    };
  }
  const origin = rayParamAlong(start.axis, start.ray);
  if (origin === null) return null;
  return {
    move: (ray) => {
      const s = rayParamAlong(start.axis, ray);
      if (s === null) return null;
      return snapValue(clamp(start.value + (s - origin), start.min, start.max));
    },
  };
}

/**
 * The placement a part takes when its joint moves by `delta` from `base`: a
 * turn of `delta` degrees about the axis, or a run of `delta` mm along it. The
 * local preview; the server's solve has the last word on release.
 */
export function placementAfterDrive(
  base: Placement,
  motion: "revolute" | "slider",
  axis: JointAxis,
  delta: number,
): Placement {
  const dir = v(axis.dir).normalize();
  const position = v(base.position);
  const q = base.orientation;
  let orientation = new Quaternion(q.x, q.y, q.z, q.w).normalize();
  if (motion === "slider") {
    position.addScaledVector(dir, delta);
  } else {
    const turn = new Quaternion().setFromAxisAngle(
      dir,
      (delta * Math.PI) / 180,
    );
    const pivot = v(axis.point);
    position.sub(pivot).applyQuaternion(turn).add(pivot);
    orientation = turn.multiply(orientation).normalize();
  }
  const sign = orientation.w < 0 ? -1 : 1;
  return {
    position: plain(position),
    orientation: {
      w: sign * orientation.w,
      x: sign * orientation.x,
      y: sign * orientation.y,
      z: sign * orientation.z,
    },
  };
}
