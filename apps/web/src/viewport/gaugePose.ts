/**
 * THE GAUGE'S DRAWN POSE — where the shell puts its meshes, as arithmetic.
 *
 * The same seam `extrudeHandle.ts` ↔ `ExtrudeDragHandle.tsx` and
 * `extrudeGhost.ts` ↔ `ExtrudePreview.tsx` already make, for the same reason: a
 * decision buried in a `useMemo` inside a WebGL-only component is invisible
 * below a full browser run, and this one was wrong for a month without anything
 * being able to see it.
 *
 * ## THE CHORD DEFECT, which is why this file exists (CRAFT-7 item 7)
 *
 * `TrackDrawing.spine` is documented as *"two points for a straight track, a
 * POLYLINE for an arc"*, and `angularTrack.draw` duly emits one — 25 points for
 * a 90 degree sweep. The shell kept `spine[0]` and `spine[len-1]` and drew ONE
 * cylinder between them, discarding every intermediate point. MEASURED: at
 * radius 20 that chord departs from the true arc by **5.86 world units, 29 % of
 * the radius** — so the first angular gauge would have drawn a straight bar
 * across the sweep it claims to describe, and the grip would have sat somewhere
 * the arc does not pass.
 *
 * A TWO-POINT SPINE STILL YIELDS EXACTLY ONE SEGMENT, with the same centre,
 * quaternion and length the single-cylinder version produced. That is the
 * property that makes this safe for the shipped extrude gauge: the polyline is
 * a capability, not a new cost on the straight path.
 */
import { Quaternion, Vector3, type Camera } from "three";

import type { TrackDrawing, Vec3 } from "@loft/design";

/** +Y — the axis `ConeGeometry` and `CylinderGeometry` build along. */
export const BUILD_AXIS = new Vector3(0, 1, 0);

/** One drawn length of spine: a unit cylinder scaled, posed and placed. */
export interface SpineSegment {
  centre: Vector3;
  quaternion: Quaternion;
  length: number;
}

/** Where every mesh of the instrument goes, for one {@link TrackDrawing}. */
export interface GaugePose {
  /** Orientation of the arrowhead cone. */
  quaternion: Quaternion;
  /** Centre of the arrowhead cone — its BASE sits on the end of the spine. */
  headCentre: Vector3;
  /** One per spine segment, seat to tip. A straight track gives exactly one. */
  segments: SpineSegment[];
}

export function gaugePose(drawing: TrackDrawing): GaugePose {
  const headBase = new Vector3(...drawing.head.base);
  const apex = new Vector3(...drawing.head.tip);
  const headDir = apex.clone().sub(headBase).normalize();
  const segments: SpineSegment[] = [];
  for (let i = 0; i + 1 < drawing.spine.length; i += 1) {
    const from = new Vector3(...(drawing.spine[i] as Vec3));
    const to = new Vector3(...(drawing.spine[i + 1] as Vec3));
    const length = to.distanceTo(from);
    // A zero-length segment has no direction of its own; borrow the head's
    // rather than emit a NaN quaternion. It is scaled to nothing anyway, so the
    // orientation is unobservable — but a NaN in a matrix is not.
    const dir =
      length > 0 ? to.clone().sub(from).divideScalar(length) : headDir;
    segments.push({
      centre: from.clone().addScaledVector(dir, length / 2),
      quaternion: new Quaternion().setFromUnitVectors(BUILD_AXIS, dir),
      length,
    });
  }
  return {
    quaternion: new Quaternion().setFromUnitVectors(BUILD_AXIS, headDir),
    // `ConeGeometry` is centred on its own axis, so the base lands on the end
    // of the spine when the centre sits half a length along.
    headCentre: headBase
      .clone()
      .addScaledVector(headDir, drawing.head.length / 2),
    segments,
  };
}

/** Total drawn length of a posed spine, world units. */
export function spineLength(segments: readonly SpineSegment[]): number {
  let total = 0;
  for (const segment of segments) total += segment.length;
  return total;
}

/**
 * Scratch for {@link projectedSpineLength}. The frame loop calls it every
 * frame and must not allocate; nothing escapes, so two module vectors are
 * enough and the function is single-threaded by construction.
 */
const projFrom = new Vector3();
const projTo = new Vector3();

/**
 * THE DRAWN TRACK'S LENGTH ON SCREEN, CSS pixels — the projected POLYLINE,
 * vertex for vertex with the world polyline {@link spineLength} measures.
 *
 * ## THE BIAS THIS EXISTS TO END (CRAFT-7 review, blocking finding)
 *
 * The shell divided a WORLD length by a SCREEN length describing a DIFFERENT
 * SEGMENT: `spineLength` runs seat -> head BASE, while the projection it was
 * divided by ran seat -> head TIP. So the px-per-value the ladder is chosen
 * from was inflated by `(value + headLength) / value` — MEASURED 1.180 at a
 * 40 mm depth and 1.450 at 10 mm, where the arrowhead clamp holds the head at
 * 0.45 of the shaft. The floor the ladder believed it was clearing at 14 px
 * was therefore really being cleared at 14 / 1.180 = 11.9 px, sliding to
 * 9.7 px on a short feature: the ladder was NOT scale-invariant, which is
 * exactly what its docstring claims for it.
 *
 * Worse, it was unfalsifiable from inside: the commit that shipped it measured
 * the component's own `pxPerValue`, i.e. the quantity carrying the bug, so the
 * numbers agreed with themselves. A gate is only as honest as its input. This
 * function is the input, hoisted where a unit test can hold it.
 *
 * ## WHY A POLYLINE AND NOT TWO ENDPOINTS
 *
 * Both ends must describe ONE segment — and for an arc, so must everything
 * between them. A straight screen distance between the ends of a 90 degree
 * sweep is a CHORD: at radius 20 it is 0.900 of the arc it stands for, so an
 * angular gauge would inherit a second bias of the same shape from the same
 * line of code (`angularTrack` reads the identical `unitsPerPixel`). Summing
 * the projected polyline is exact for both and costs a straight track nothing:
 * its spine is two points, which is one iteration.
 */
export function projectedSpineLength(
  spine: readonly Vec3[],
  camera: Camera,
  width: number,
  height: number,
): number {
  let total = 0;
  for (let i = 0; i + 1 < spine.length; i += 1) {
    const from = spine[i] as Vec3;
    const to = spine[i + 1] as Vec3;
    projFrom.set(from[0], from[1], from[2]).project(camera);
    projTo.set(to[0], to[1], to[2]).project(camera);
    // NDC -> CSS pixels. The `+1`/`-1` offsets of the two endpoints cancel, so
    // only the halved span survives; `y` flips because NDC grows upward.
    const dx = ((projTo.x - projFrom.x) / 2) * width;
    const dy = ((projFrom.y - projTo.y) / 2) * height;
    total += Math.sqrt(dx * dx + dy * dy);
  }
  return total;
}
