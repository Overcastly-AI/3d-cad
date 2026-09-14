/**
 * WHEN THE FLOOR CANNOT CARRY THE FRAME, THE BENCH PUTS UP A WALL (CRAFT-2).
 *
 * ## The defect
 *
 * `docs/design/AUDIT-CRAFT-2026-09.md` P1-1: the front, right and top
 * orthographic views were an empty field — "a grey rectangle on an empty
 * field. No grid, no horizon, no origin axes, no body edges, no scale
 * reference." These are the three views an engineer checks a part in, and they
 * were the three with the least on screen. Mandate 3a(a) names it: a grid that
 * fades into flat void is a defect.
 *
 * ## The mechanism, which is geometric and not a tuning miss
 *
 * The audit offered a plausible cause — `AdaptiveGrid` scaling drei's
 * `fadeDistance` by the orbit radius — and asked a builder to confirm it rather
 * than take it. It is not that, and the real one is stronger: **under a
 * PARALLEL projection a plane that contains the view direction projects to a
 * LINE.** The ground plane is edge-on in a front or right view, so its image is
 * one row of pixels however the fade is tuned. Measured on the real stack, in a
 * 608x189 band below the plate, front view, projection the only variable:
 *
 *     perspective    2 815.5 coverage over 10 574 drawn pixels
 *     orthographic         0 coverage over        0 drawn pixels
 *
 * Not faint — nothing at all, which is a cleaner statement than the audit's
 * "2 396 px, and all of them are the body's own antialiasing". Under
 * PERSPECTIVE the same plane shows a receding wedge below the eye, which is why
 * only the parallel case fails and why iso-ortho (where the ground is 35 degrees
 * off edge-on) was always fine.
 *
 * ## The answer, and why this one
 *
 * The audit allowed either an edge-on rule or a face-on grid. This chooses the
 * face-on grid — the bench's floor stands up into a DRAFTING BOARD behind the
 * part, on the principal plane the camera is square to, in the same two grid
 * inks at the same 5/25 mm pitch. The reason is what the view is FOR: a front
 * view is read for elevations, heights and widths in the plane of the screen,
 * and a grid in that plane is the reference that answers the question being
 * asked. An edge-on rule answers "where is the floor", which the contact
 * shadow and the origin triad (CRAFT-3) already answer.
 *
 * The floor is not deleted: it is still drawn, edge-on, so it reads as the one
 * bright rule across the board — a wall behind a floor, which is what a bench
 * actually looks like.
 *
 * This module is the DECISION, kept pure so the hysteresis is unit-testable
 * without a GPU (the same posture `projection.ts` and `fitFraming.ts` take).
 */

/** The world axis a backdrop's normal runs along. */
export type BackdropAxis = "x" | "z";

export interface Backdrop {
  /** The sheet's normal axis — the axis the camera is looking down. */
  axis: BackdropAxis;
  /** Which side of the subject it hangs on: the far side from the camera. */
  side: -1 | 1;
}

/**
 * How close to edge-on the ground must be before the wall goes up, as |sin| of
 * the angle between the view direction and the ground plane.
 *
 * ENGAGE is ~5.7 degrees and RELEASE ~9.8. Two values, not one, because a
 * single threshold strobes the sheet on and off while the modeler orbits
 * across it — the same reason a Schmitt trigger exists. The window is narrow on
 * purpose: at 10 degrees off edge-on the ground already carries a readable band
 * and two grids at once would be noise.
 */
export const BACKDROP_ENGAGE = 0.1;
export const BACKDROP_RELEASE = 0.17;

/**
 * Which backdrop (if any) belongs behind this camera.
 *
 * `direction` points from the subject TO the camera and need not be normalised.
 * `current` is what is drawn right now — the hysteresis reads it, so a caller
 * that always passes `null` gets the ENGAGE threshold and no latch, which is
 * the right behaviour for a one-shot query.
 */
export function backdropFor(
  direction: readonly [number, number, number],
  orthographic: boolean,
  current: Backdrop | null,
): Backdrop | null {
  // Perspective keeps the ground: it shows the half-plane below the eye at any
  // attitude, so there is nothing to rescue.
  if (!orthographic) return null;
  const length = Math.hypot(direction[0], direction[1], direction[2]);
  if (length === 0) return null;
  const x = direction[0] / length;
  const y = direction[1] / length;
  const z = direction[2] / length;
  const threshold = current === null ? BACKDROP_ENGAGE : BACKDROP_RELEASE;
  if (Math.abs(y) >= threshold) return null;
  const axis: BackdropAxis = Math.abs(x) >= Math.abs(z) ? "x" : "z";
  const along = axis === "x" ? x : z;
  // Hangs on the far side: the sheet is BEHIND the subject, never between it
  // and the camera.
  return { axis, side: along >= 0 ? -1 : 1 };
}

/** A world-axis-aligned box, in the shape `Box3` reports. */
export interface SubjectBounds {
  min: readonly [number, number, number];
  max: readonly [number, number, number];
}

/**
 * Clearance behind the subject, in mm, as a fraction of its bounding diagonal
 * — so a 2 m weldment gets a sheet behind it rather than through it, and a
 * 6 mm dowel does not get one a metre away.
 */
const CLEARANCE_OF_DIAGONAL = 0.5;
/** Clearance floor (mm) for a tiny or empty subject. */
const MIN_CLEARANCE_MM = 25;

/**
 * Where the sheet hangs: its origin (world mm) and its normal.
 *
 * Behind the subject along the backdrop's own axis, never inside it. A null
 * subject (an empty part) puts the sheet through the origin, which is the only
 * place it can be and still mean something.
 */
export function backdropPose(
  backdrop: Backdrop,
  bounds: SubjectBounds | null,
): {
  position: [number, number, number];
  normal: [number, number, number];
} {
  const index = backdrop.axis === "x" ? 0 : 2;
  const normal: [number, number, number] = [0, 0, 0];
  // The sheet FACES the camera, so its normal points back toward it — the
  // opposite of the side it hangs on.
  normal[index] = -backdrop.side;
  if (bounds === null) {
    return { position: [0, 0, 0], normal };
  }
  const size = [
    bounds.max[0] - bounds.min[0],
    bounds.max[1] - bounds.min[1],
    bounds.max[2] - bounds.min[2],
  ];
  const diagonal = Math.hypot(
    size[0] as number,
    size[1] as number,
    size[2] as number,
  );
  const clearance = Math.max(
    diagonal * CLEARANCE_OF_DIAGONAL,
    MIN_CLEARANCE_MM,
  );
  const position: [number, number, number] = [0, 0, 0];
  position[index] =
    backdrop.side > 0
      ? (bounds.max[index] as number) + clearance
      : (bounds.min[index] as number) - clearance;
  return { position, normal };
}
