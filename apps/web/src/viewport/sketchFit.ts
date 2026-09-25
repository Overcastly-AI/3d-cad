/**
 * WHAT "FIT" FRAMES WHILE YOU ARE DRAWING — the world box of the open sketch's
 * own entities (product audit F-11).
 *
 * The part rig's Fit frames the MODEL. That is the right subject in the part
 * workspace and the wrong one in the sketcher, where the thing you lose is the
 * profile: the audit found an 80 mm dimension glyph at x = 1856 on a 1600 px
 * frame after one dimension edit, with no control on screen to get it back. So
 * while a sketch is open, Fit frames what the modeler drew.
 *
 * The box is built from the SAME polylines the ink is drawn from
 * (`entitySegmentPositions`), so a circle contributes its rim rather than its
 * centre and a spline its sampled curve — a fit that framed defining points
 * only would crop every arc it was asked to show. Lone points have no
 * polyline, so the defining points are folded in as well.
 *
 * Pure and allocation-light (one call per Fit, never per frame): the caller
 * owns the `Box3` so the viewport can reuse one.
 */
import { Box3, Vector3 } from "three";

import { withoutDatums } from "../sketch/datum";
import {
  definingPointPositions,
  entitySegmentPositions,
} from "../sketch/geometry";
import type { PlaneBasis } from "../sketch/plane";
import type { SketchEntity } from "../sketch/tools";

/**
 * The smallest box a sketch Fit will frame, as a diagonal in mm. A sketch of
 * one point, or of one very short line, has a box of (nearly) zero size, and
 * framing zero size solves a camera distance of zero — the eye inside the
 * plane. 10 mm is a readable neighbourhood around a single mark without being
 * so large that a small real profile is framed as a speck.
 */
export const MIN_SKETCH_FIT_MM = 10;

const scratch = new Vector3();

function expandBy(box: Box3, positions: Float32Array): void {
  for (let i = 0; i + 2 < positions.length; i += 3) {
    box.expandByPoint(
      scratch.set(
        positions[i] as number,
        positions[i + 1] as number,
        positions[i + 2] as number,
      ),
    );
  }
}

/**
 * The world (scene) box of everything the modeler drew on `basis`, written
 * into `into`, or null when nothing is drawn. The plane's datum frame (origin
 * point and axes, materialised once something is grounded to them) is the
 * plane's own furniture rather than the modeler's ink, so it never counts.
 */
export function sketchWorldBox(
  entities: readonly SketchEntity[],
  basis: PlaneBasis,
  into: Box3,
): Box3 | null {
  into.makeEmpty();
  const drawn = withoutDatums(entities);
  if (drawn.length === 0) return null;
  expandBy(into, entitySegmentPositions(drawn, basis));
  expandBy(into, definingPointPositions(drawn, basis));
  if (into.isEmpty()) return null;
  const diagonal = into.getSize(scratch).length();
  if (diagonal < MIN_SKETCH_FIT_MM) {
    // Grow evenly about the centre until the diagonal reaches the floor. A box
    // grown by `s` on every side gains 2s on each axis, i.e. 2s·√3 of diagonal.
    into.expandByScalar((MIN_SKETCH_FIT_MM - diagonal) / (2 * Math.sqrt(3)));
  }
  return into;
}
