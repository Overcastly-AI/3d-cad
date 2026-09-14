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
import { Quaternion, Vector3 } from "three";

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
