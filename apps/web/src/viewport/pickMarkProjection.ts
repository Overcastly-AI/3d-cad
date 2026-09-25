/**
 * WHERE A PICK MARK LANDS ON THE SCREEN — the scene→CSS arithmetic, lifted out
 * of the component so it is testable without a GPU.
 *
 * These are drei `Html`'s own numerics, transcribed rather than reinvented:
 * `defaultCalculatePosition`, `isObjectBehindCamera` and `objectZIndex` from
 * `@react-three/drei/web/Html.js`. That is deliberate and it is the point of
 * the file. `PickMarkLayer` replaced drei's per-instance React root with one
 * shared host, and the ONLY thing that replacement is allowed to change is
 * COST — a mark must land on the same pixel, in the same depth band, and
 * vanish behind the camera at the same moment it always did. Keeping the
 * arithmetic in one named, tested place is what makes that claim checkable
 * rather than asserted; `pickMarkProjection.test.ts` pins each function against
 * a hand-computed value.
 *
 * Every entry point takes already-extracted vectors and writes into
 * caller-owned scratch, because the whole reason this file exists is that it
 * runs once per mark per frame and 452 marks is a real number here. The
 * camera's world position and direction are hoisted to the caller for the same
 * reason: they are the same for every mark in a frame, so resolving them
 * per-mark would be 452 redundant matrix walks.
 */
import type { Camera, Vector3 } from "three";

/** A point in CSS pixels, measured from the canvas's top-left. */
export interface ScreenPoint {
  x: number;
  y: number;
}

/**
 * Project a world point to CSS pixels within a `width` x `height` canvas.
 *
 * Mutates `scratch` and `out`. `scratch` must not alias `point` — `point` is
 * normally the mark's live world position and projecting it in place would
 * corrupt the next reading.
 */
export function projectToScreen(
  point: Vector3,
  camera: Camera,
  width: number,
  height: number,
  scratch: Vector3,
  out: ScreenPoint,
): void {
  scratch.copy(point).project(camera);
  const widthHalf = width / 2;
  const heightHalf = height / 2;
  out.x = scratch.x * widthHalf + widthHalf;
  out.y = -(scratch.y * heightHalf) + heightHalf;
}

/**
 * Is the point behind the camera — i.e. must its mark stop being drawn?
 *
 * The angle between (point - camera) and the camera's forward direction, not a
 * sign test on projected z, because that is what drei does: a mark that
 * disappears one frame earlier or later than the geometry it labels is a
 * visible defect, not a rounding difference.
 *
 * Mutates `scratch`.
 */
export function isBehindCamera(
  point: Vector3,
  cameraPosition: Vector3,
  cameraDirection: Vector3,
  scratch: Vector3,
): boolean {
  scratch.copy(point).sub(cameraPosition);
  return scratch.angleTo(cameraDirection) > Math.PI / 2;
}

/**
 * The CSS `z-index` for a mark `distance` from the camera, mapped into the
 * caller's band. Near → `range[0]`, far → `range[1]`, so a mark in front of
 * another stacks above it.
 *
 * Returns `null` for a camera with no frustum depth to map (neither
 * perspective nor orthographic) — drei's `undefined` case, where the caller
 * leaves the existing z-index alone rather than writing a nonsense one. Both
 * of this app's cameras are covered (the projection toggle swaps between
 * exactly those two), so the null branch is a refusal, not a fallback.
 *
 * The test is three.js's OWN duck-typed flags rather than `instanceof`, which
 * is what drei uses too and which matters here: three is routinely present
 * twice in a bundle (its ESM and CJS builds both ship a class of each name),
 * and `instanceof` across those two instances is FALSE for a perfectly good
 * camera. That failure is silent — every mark simply keeps whatever z-index it
 * had — so the robust check is the one three itself relies on.
 */
export function depthZIndex(
  distance: number,
  camera: Camera,
  range: readonly [number, number],
): number | null {
  const projected = camera as unknown as {
    isPerspectiveCamera?: boolean;
    isOrthographicCamera?: boolean;
    near?: number;
    far?: number;
  };
  if (
    (projected.isPerspectiveCamera !== true &&
      projected.isOrthographicCamera !== true) ||
    typeof projected.near !== "number" ||
    typeof projected.far !== "number"
  ) {
    return null;
  }
  const a = (range[1] - range[0]) / (projected.far - projected.near);
  const b = range[1] - a * projected.far;
  return Math.round(a * distance + b);
}

/**
 * The transform a mark's slot carries. Translate to the projected point, THEN
 * back by half the slot's own box — which is how the mark ends up centred on
 * its anchor. drei splits those two steps across an outer host div (the
 * projected translate) and an inner `center` div (`translate3d(-50%,-50%,0)`);
 * the shared host gives each mark ONE element, so they compose here.
 */
export function slotTransform(x: number, y: number): string {
  return `translate3d(${x}px,${y}px,0) translate3d(-50%,-50%,0)`;
}
