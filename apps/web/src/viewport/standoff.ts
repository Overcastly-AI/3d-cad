/**
 * HOW FAR BACK THE CAMERA HAS TO STAND TO SEE THE SUBJECT — one derivation,
 * both rigs.
 *
 * ## The defect this exists for (measured 2026-09-15, gearbox-11752)
 *
 * The part rig solves its fit from the subject's own projected corners
 * (`fitFraming.fitDistance`). The SKETCH rig did not: entering the plane-pick
 * step posed the camera at a hardcoded 230 mm from the world origin, on a fixed
 * iso direction, with no reference to the body at all. That is a fine studio
 * vantage for the fixtures this repo grades itself on — a 10x20x30 box, a
 * 150x80x8 plate — and it is INSIDE a real part.
 *
 * Measured on the gauntlet's `gearbox-11752` (1018 faces, extents
 * **1280.16 x 144.27 x 133.35 mm**), in a real browser at 1280x800:
 *
 * | after                        | the 452 face marks                       |
 * | ---------------------------- | ---------------------------------------- |
 * | auto-fit / explicit fit      | body framed, whole part on screen        |
 * | **click "New sketch"**       | camera dives inside the part             |
 * | armed face pick              | 226 behind camera, 222 off-canvas left,  |
 * |                              | **4 on canvas, 0 reachable**             |
 *
 * `document.elementFromPoint` resolved **zero** of 452 marks to themselves. The
 * gauntlet reported this as "selecting one face takes 55-73 seconds", which
 * understates it: on a part this size the face you want is not on screen, and
 * the only faces that are, are stacked on top of each other against the left
 * edge of the frame. No unit test could see it — the marks are all present,
 * correctly positioned (their coordinate span matches the body's bounding box
 * to 0.5 mm), correctly named, and pointed at by nothing.
 *
 * ## Why a floor rather than a replacement
 *
 * 230 mm is a deliberate composition for a small part: it puts a datum sheet
 * and a modest body in a studio three-quarter view with the bench reading to
 * the horizon. Solving the distance unconditionally would zoom OUT of every
 * small part to make room for corners that are already comfortably inside the
 * frame. So the solved distance is a FLOOR-raiser: it takes effect only when
 * the subject does not fit, which is exactly the case that was broken, and
 * every existing fixture keeps the vantage it was composed with.
 *
 * ## Why it reuses `fitDistance` rather than a bounding sphere
 *
 * A sphere fit is blind to the subject's aspect ratio, and the part that broke
 * this has an aspect ratio of 8.9:1 — a sphere about a 1280 mm rail is mostly
 * empty air, so it would stand off ~1.5x further than needed and shrink the
 * part for no reason. `fitDistance` already solves this from the eight
 * projected corners, accounts for the chrome the panels cover, and is unit
 * tested. Two framing rules that disagree is the defect this file is fixing,
 * in a second costume.
 *
 * ## The second question, same arithmetic (CRAFT-12)
 *
 * "How far back must the camera stand?" has a yes/no sibling: "is the subject
 * OUT of frame from where the camera is standing now?" — which is what a
 * feature preview needs answered, because a proposal the modeler cannot see is
 * a proposal they have to navigate to before they can judge it. {@link
 * frameOverrun} asks it with the same corners, the same free rect and the same
 * two solvers, so the check and the fix cannot drift apart. It lives here and
 * not in `Viewport.tsx` for the reason the whole module exists: a framing rule
 * written twice is a framing rule that will eventually disagree with itself.
 */
import type { Box3, Vector3 } from "three";

import {
  fitDistance,
  fitZoom,
  measureChrome,
  unobstructedRect,
  type CameraSpacePoint,
  type Rect,
} from "./fitFraming";

/**
 * Plane-pick vantage floor (mm) — the studio iso the shell opens with, for a
 * subject small enough to sit inside it. See the module note for why this is a
 * floor and not the answer.
 */
export const PICK_CAMERA_DISTANCE_MM = 230;

/**
 * The subject's eight bounding corners resolved onto the camera's own axes —
 * the silhouette a fit has to make room for, DEPTH INCLUDED (a corner nearer
 * the camera projects wider, which is what `fitDistance` solves for). Empty for
 * an empty/absent box.
 *
 * `center` is the point the corners are measured from: the orbit TARGET, not
 * the box's centre, because a camera framing a subject it is not centred on has
 * to make room for the whole offset.
 */
export function boxCornersInCameraAxes(
  box: Box3 | null,
  center: Vector3,
  right: Vector3,
  up: Vector3,
  dir: Vector3,
): CameraSpacePoint[] {
  if (box === null || box.isEmpty()) return [];
  const corners: CameraSpacePoint[] = [];
  for (let i = 0; i < 8; i += 1) {
    const x = (i & 1 ? box.max.x : box.min.x) - center.x;
    const y = (i & 2 ? box.max.y : box.min.y) - center.y;
    const z = (i & 4 ? box.max.z : box.min.z) - center.z;
    corners.push({
      a: x * right.x + y * right.y + z * right.z,
      b: x * up.x + y * up.y + z * up.z,
      c: x * dir.x + y * dir.y + z * dir.z,
    });
  }
  return corners;
}

/** The canvas rect and the rect the chrome leaves free, for a viewport node. */
export function framingOf(
  container: Element | null,
): { canvas: Rect; free: Rect } | null {
  if (container === null) return null;
  const { canvas, obstructions } = measureChrome(container);
  if (canvas.width <= 0 || canvas.height <= 0) return null;
  return { canvas, free: unobstructedRect(canvas, obstructions) };
}

export interface PlanePickStandoff {
  /** Camera basis vectors at the pick attitude. */
  right: Vector3;
  up: Vector3;
  /** Points from the orbit target TOWARD the camera; unit length. */
  dir: Vector3;
  /** The orbit target the vantage is composed about. */
  target: Vector3;
}

/**
 * How far along `dir` the plane-pick camera must stand to have the subject on
 * screen — never closer than {@link PICK_CAMERA_DISTANCE_MM}.
 *
 * Returns the floor when there is no subject, no measurable frame, or a
 * degenerate solve, so a missing measurement can only ever leave the vantage
 * exactly as it was before this function existed.
 */
export function planePickDistanceMm(
  box: Box3 | null,
  basis: PlanePickStandoff,
  framing: { canvas: Rect; free: Rect } | null,
  fovDeg: number,
): number {
  if (framing === null) return PICK_CAMERA_DISTANCE_MM;
  const corners = boxCornersInCameraAxes(
    box,
    basis.target,
    basis.right,
    basis.up,
    basis.dir,
  );
  if (corners.length === 0) return PICK_CAMERA_DISTANCE_MM;
  const solved = fitDistance(corners, framing.canvas, framing.free, fovDeg);
  if (!Number.isFinite(solved) || solved <= 0) return PICK_CAMERA_DISTANCE_MM;
  return Math.max(PICK_CAMERA_DISTANCE_MM, solved);
}

/**
 * How the camera is projecting right now — everything needed to ask whether the
 * subject fits, and nothing else. The two variants are not interchangeable and
 * the reason is in `fitFraming`: a perspective frame is sized by DISTANCE, a
 * parallel one by ZOOM, and distance carries no size information at all under a
 * parallel projection.
 */
export type ProjectionState =
  | { kind: "perspective"; fovDeg: number; distanceMm: number }
  | { kind: "orthographic"; zoom: number };

/**
 * HOW MUCH TOO BIG THE SUBJECT IS FOR THE FRAME IT IS BEING SEEN IN.
 *
 * `1` is an exact fit, `> 1` means it runs past the frame (2 = twice as much
 * subject as there is room for), `< 1` means there is air to spare. `0` means
 * the question could not be asked — no subject, no measurable frame, or a
 * degenerate solve — and a caller MUST read that as "do nothing", never as "it
 * fits", because those two answers have opposite consequences.
 *
 * One expression for both projections, because the alternative is two framing
 * rules that can disagree, which is the defect the top of this file is about.
 * Perspective compares the distance the subject NEEDS against the distance the
 * camera is standing at; parallel compares the zoom it needs against the zoom
 * in force, inverted because a bigger zoom is a tighter frame.
 *
 * Note what this deliberately does NOT do: it does not say where to put the
 * camera. Framing is `Viewport.framePose`'s job and stays there — this only
 * answers the yes/no that decides whether to disturb the modeler at all.
 */
export function frameOverrun(
  corners: readonly CameraSpacePoint[],
  framing: { canvas: Rect; free: Rect } | null,
  projection: ProjectionState,
): number {
  if (framing === null || corners.length === 0) return 0;
  if (projection.kind === "orthographic") {
    const needed = fitZoom(corners, framing.free);
    if (!(needed > 0) || !(projection.zoom > 0)) return 0;
    return projection.zoom / needed;
  }
  const needed = fitDistance(
    corners,
    framing.canvas,
    framing.free,
    projection.fovDeg,
  );
  if (!(needed > 0) || !(projection.distanceMm > 0)) return 0;
  return needed / projection.distanceMm;
}

/**
 * How far past an exact fit the subject must run before the camera is allowed
 * to move on its own.
 *
 * NOT an epsilon. `fitDistance` already builds in 1 % of slack (`FIT_PADDING`),
 * so a freshly fitted scene sits a hair BELOW 1 and a bare `> 1` test would
 * re-fire on rounding. Two per cent of the frame is roughly a dozen pixels of
 * overhang at 1280 wide — small enough that a modeler has not lost anything,
 * and moving the camera to recover it would cost more attention than it buys.
 * Above it, part of what the tool is proposing is off the screen, which is the
 * thing this whole mechanism exists to prevent.
 */
export const PREVIEW_REFIT_OVERRUN = 1.02;

/**
 * Should a preview at this overrun pull the camera back?
 *
 * Deliberately a named predicate over a bare comparison: it is the ONE place
 * the policy is stated, and `0` — the unmeasurable answer — has to fall on the
 * "leave the modeler alone" side, which an inlined `> 1.02` gets right by luck
 * rather than by saying so.
 */
export function overrunNeedsRefit(overrun: number): boolean {
  return overrun > PREVIEW_REFIT_OVERRUN;
}
