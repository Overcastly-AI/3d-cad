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
 * frameOverrun} asks it with the same corners and the same free rect, and it
 * asks it as CONTAINMENT through the camera as it stands rather than as a fit
 * ratio — its own note says why a ratio disagreed with the pose it triggered,
 * and the unit tests pin that the check and the pose agree. It lives here and
 * not in `Viewport.tsx` for the reason the whole module exists: a framing rule
 * written twice is a framing rule that will eventually disagree with itself.
 */
import type { Box3, Vector3 } from "three";

import {
  fitDistance,
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
 * A WORLD SIZE THAT HOLDS ITS APPARENT SIZE AS THE CAMERA STANDS BACK.
 *
 * ## The defect this exists for (measured 2026-09-16, by review)
 *
 * The plane-pick standoff became variable and the three datum sheets did not.
 * `PLANE_SIZE_MM` is a fixed 90 mm of world, so the sheets subtend an angle
 * that falls off as 1/distance — which means the fix that finally made big
 * parts pickable SHRANK the affordance you have to click to start a sketch on
 * one, by exactly the factor it moved the camera. Face-on, at FOV 40 on a
 * 1280x800 frame:
 *
 * | subject                    | standoff  | sheet    |
 * | -------------------------- | --------- | -------- |
 * | 10x20x30 box (the fixture) |   230 mm  | ~430 px  |
 * | 150x80x8 plate             |   230 mm  | ~430 px  |
 * | 1280 mm gearbox            |  1291 mm  | ~ 77 px  |
 * | 1600 mm column             |  2366 mm  | ~ 42 px  |
 *
 * and at the iso attitude the sheets foreshorten by `|dir·n|` (XZ 0.375, YZ
 * 0.552, XY 0.745), so the most foreshortened sheet's minor dimension is ~29 px
 * on the gearbox and ~16 px on the column, against ~161 px at the old fixed
 * vantage. Small parts are unchanged, which is why nothing caught it — and
 * `plane-pick-framing.spec.ts` is structurally blind to it, because it clicks
 * `plane-pick-face` first and the sheets render only while `!facePicking`.
 *
 * ## Why a ratio to the FLOOR and not an absolute angular size
 *
 * 90 mm at 230 mm IS the composition — it was chosen by eye against the bench
 * and the body, and it is correct for every part that still gets the floor. A
 * sheet sized from an angle would re-derive that composition from a number
 * nobody chose and would move the small-part case, which is the one thing the
 * standoff fix was careful not to do. Scaling by `standoff / floor` is exactly
 * 1 at the floor, so this is a no-op on every fixture in the repo and grows
 * only where the camera actually went somewhere new.
 */
export function apparentSizeMm(
  sizeAtFloorMm: number,
  standoffMm: number,
): number {
  if (!(standoffMm > PICK_CAMERA_DISTANCE_MM)) return sizeAtFloorMm;
  return (sizeAtFloorMm * standoffMm) / PICK_CAMERA_DISTANCE_MM;
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
 * HOW FAR PAST THE VISIBLE FRAME THE SUBJECT RUNS, FROM WHERE THE CAMERA IS.
 *
 * `corners` are measured from the ORBIT TARGET on the camera's own axes (see
 * {@link boxCornersInCameraAxes}). Each is projected exactly as the renderer
 * will draw it — the target lands on the CANVAS centre, because that is what
 * the camera looks at — and the answer is how far the furthest corner sits
 * from the centre of the chrome-free rect, as a fraction of that rect's
 * half-extent. So `<= 1` means every corner is on screen and clear of every
 * panel, `> 1` means some of the subject is off the frame or under the chrome.
 * `0` means the question could not be asked — no subject, no measurable frame,
 * a degenerate camera — and a caller MUST read that as "do nothing", never as
 * "it fits", because those two answers have opposite consequences. A corner
 * BEHIND a perspective camera reads `Infinity`: it is certainly not on screen.
 *
 * ## Why containment, and the defect the old ratio had (measured 2026-09-23)
 *
 * This used to be `fitZoom(corners) / zoom` (resp. `fitDistance / distance`):
 * "would a frame CENTRED ON THE TARGET hold the subject?". That is a FIT
 * question, and it is the wrong one twice over:
 *
 *  · the camera does not look at the target through the free rect, it looks
 *    through the canvas — and `framePose` deliberately parks the target OFF the
 *    subject (`targetShift`) so the subject lands mid-free-rect. The ratio
 *    ignored both offsets, so it disagreed with the very pose it triggers;
 *  · after a proposal SHRINKS, the target still sits at the old subject's
 *    centre, and mirroring a 14 mm ghost about a point 150 mm above it reads as
 *    needing as much room as the 300 mm ghost did. Measured on a 10 mm body,
 *    300 mm -> 12 mm extrude: overrun **1.139 for both**, so the re-fit fired
 *    on the SHRINK and re-centred on the small subject — a 15.7x pull IN, from
 *    a mechanism documented as "only outward". Whether it fired depended on
 *    whether an earlier ease was still in flight when the smaller box arrived,
 *    which is why it was bimodal across identical runs (6 of 11).
 *
 * Containment has neither problem. It is a statement about pixels the modeler
 * can see, it agrees with `framePose` by construction (a freshly posed subject
 * reads `1 / FIT_PADDING`, just under 1), and a subject that got smaller cannot
 * read larger — so "only outward" is now a property of the arithmetic rather
 * than of a race.
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
  const { canvas, free } = framing;
  if (!(free.width > 0) || !(free.height > 0) || !(canvas.height > 0)) {
    return 0;
  }
  // Pixels per world unit at depth `c` (measured TOWARD the camera from the
  // target), or null when the corner cannot be projected at all.
  let scaleAt: (c: number) => number | null;
  if (projection.kind === "orthographic") {
    // r3f's frustum is the canvas's CSS half-extents over `zoom`, so one world
    // unit is `zoom` pixels at every depth (the convention `fitZoom` uses).
    if (!(projection.zoom > 0)) return 0;
    const zoom = projection.zoom;
    scaleAt = () => zoom;
  } else {
    const tan = Math.tan((projection.fovDeg * Math.PI) / 360);
    const distance = projection.distanceMm;
    if (!(tan > 0) || !(distance > 0)) return 0;
    const focal = canvas.height / 2 / tan;
    scaleAt = (c) => {
      const depth = distance - c;
      return depth > distance * 1e-6 ? focal / depth : null;
    };
  }
  const aimX = canvas.width / 2 - (free.x - canvas.x);
  const aimY = canvas.height / 2 - (free.y - canvas.y);
  const halfW = free.width / 2;
  const halfH = free.height / 2;
  let worst = 0;
  for (const { a, b, c } of corners) {
    const scale = scaleAt(c);
    if (scale === null) return Number.POSITIVE_INFINITY;
    // Free-rect coordinates of the projected corner (y down, as the DOM is).
    const x = aimX + a * scale;
    const y = aimY - b * scale;
    worst = Math.max(
      worst,
      Math.abs(x - halfW) / halfW,
      Math.abs(y - halfH) / halfH,
    );
  }
  return worst;
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
