/**
 * THE AXIS OF REVOLUTION, DRAWN — the prerequisite the angular gauge owns
 * (CRAFT-10, direction §9).
 *
 * MEASURED before this: the revolve axis was chosen from a dropdown reading
 * *"Y axis · through the origin"* and **the scene showed nothing**. The user
 * picked the single most consequential property of a turned part — what it
 * turns about — and got no confirmation anywhere on the model. An arc gauge
 * hung in that scene would be an arc around nothing.
 *
 * So: a brass **chain line** (ISO 128 long-dash / short-dash), the drawing
 * convention for an axis of revolution, drawn through the profile and
 * overrunning it at both ends. `axisAnchor.ts` holds the reasoning for the
 * pattern and computes the dashes; this file is the twelve lines of r3f that
 * put them on screen.
 *
 * ## Why it is line-work and not a rod
 *
 * The chain line is un-tonemapped `Segments` — a 1 px GL line — where the gauge
 * is a solid tube. That is deliberate and it is the read the whole idiom rests
 * on: a hairline is an ANNOTATION (a thing that describes), a tube is a
 * MANIPULATOR (a thing you pull). The axis is not draggable and must not look
 * as though it is; giving it the gauge's own body would promise a grip that is
 * not there, which is the decorative-chrome defect wearing the opposite
 * costume.
 *
 * It draws with `depthTest: false`, like the rest of idiom D: the axis of a
 * turned part runs THROUGH the material by definition, and an axis that
 * disappeared inside the solid it belongs to would vanish at exactly the angles
 * where the user most needs it.
 *
 * ## Test surface
 *
 * The line is GL, so it has no DOM node to query. It is named
 * `revolve-axis-line` in the scene graph and, more usefully, it is the ONLY
 * brass ink on the axis's projected run before a gauge is armed — which is what
 * the e2e probe samples for. Naming the object is for the r3f devtools; the
 * pixel census is the assertion.
 */
import { useMemo } from "react";

import { viewport } from "@loft/design/tokens";

import type { AxisAnchor } from "./axisAnchor";
import { chainLineSegments } from "./axisAnchor";
import { Segments } from "./overlaySegments";

export interface RevolveAxisLineProps {
  /**
   * The axis to draw, in scene coordinates. **A PROP, never read from a pick
   * store** — W4's persistent selection store will feed this from a different
   * source and a component that reached into today's editor state would have to
   * be rewritten rather than re-wired.
   */
  anchor: AxisAnchor;
  /**
   * The point the chain pattern is mirrored about — the middle of the geometry
   * the axis belongs to, so the line reads as an axis OF something.
   */
  centre: readonly [number, number, number];
  /** How far the drawn line reaches either side of `centre`, scene mm. */
  reachMm: number;
  /**
   * Brightened while the gauge that hangs on this axis is being addressed, so
   * the anchor and the instrument light up as one thing. Same two tokens the
   * gauge itself switches between — one palette, one state.
   */
  active?: boolean;
}

/**
 * Axis opacity at rest.
 *
 * A step under the gauge's own `axisOpacity` (0.92). The axis is the QUIETER
 * half of the pair by design — it is the thing being measured about, not the
 * thing being pulled — and holding it back is what keeps the arc the loudest
 * brass on screen. Boldness is spent in one place, and the ladder is where.
 */
const AXIS_REST_OPACITY = 0.6;

/** Opacity while the gauge is grabbed, hovered or focused. */
const AXIS_ACTIVE_OPACITY = 0.85;

export function RevolveAxisLine({
  anchor,
  centre,
  reachMm,
  active = false,
}: RevolveAxisLineProps) {
  const positions = useMemo(
    () => chainLineSegments(anchor, centre, { reach: reachMm }),
    [anchor, centre, reachMm],
  );
  if (positions.length === 0) return null;
  return (
    <group name="revolve-axis-line">
      <Segments
        positions={positions}
        color={active ? viewport.manipulator.active : viewport.manipulator.axis}
        opacity={active ? AXIS_ACTIVE_OPACITY : AXIS_REST_OPACITY}
        depthTest={false}
        renderOrder={11}
      />
    </group>
  );
}
