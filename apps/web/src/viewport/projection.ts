/**
 * SWITCHING PROJECTION WITHOUT MOVING THE MODEL (ORTHO-1).
 *
 * A perspective camera and an orthographic one describe "how big is it on
 * screen" with different numbers — a DISTANCE and a ZOOM — so a naive swap
 * jumps the subject to some unrelated size, which reads as the viewport losing
 * the part. The two conversions below are each other's inverse and preserve
 * APPARENT SIZE across the swap: whatever filled the frame before fills it
 * after, and only the convergence of the edges changes. That is the whole
 * visible difference the feature is for, so it must be the ONLY visible
 * difference the swap makes.
 *
 * Both use r3f's own orthographic frustum convention (`updateCamera` sets
 * left/right/top/bottom to the canvas's CSS-pixel half-extents), under which
 * the visible world height is `canvasHeightPx / zoom` and one world unit
 * measures exactly `zoom` pixels. `fitFraming.fitZoom` solves in the same
 * units, so the two agree by construction rather than by a shared constant
 * somebody has to keep in step.
 *
 * Pure arithmetic, kept out of the rig so the invariant is unit-testable
 * without a GPU — the same posture `fitFraming.ts` takes for framing.
 */

/** Half the vertical field of view, as a tangent. */
function halfFovTangent(fovDeg: number): number {
  return Math.tan((fovDeg * Math.PI) / 360);
}

/**
 * The orthographic `zoom` that makes a subject at `distance` from a `fovDeg`
 * perspective camera keep the size it already had.
 *
 * Returns 0 when the inputs cannot describe a view (a degenerate canvas, a
 * camera sitting on its own target), leaving the caller to keep what it has.
 */
export function orthoZoomForDistance(
  canvasHeightPx: number,
  distance: number,
  fovDeg: number,
): number {
  const tan = halfFovTangent(fovDeg);
  if (canvasHeightPx <= 0 || distance <= 0 || tan <= 0) return 0;
  return canvasHeightPx / (2 * distance * tan);
}

/**
 * The inverse: how far a `fovDeg` perspective camera must sit from its target
 * to reproduce what an orthographic camera at `zoom` was showing.
 */
export function distanceForOrthoZoom(
  canvasHeightPx: number,
  zoom: number,
  fovDeg: number,
): number {
  const tan = halfFovTangent(fovDeg);
  if (canvasHeightPx <= 0 || zoom <= 0 || tan <= 0) return 0;
  return canvasHeightPx / (2 * zoom * tan);
}

/** An orthographic frustum in r3f's convention — canvas half-extents. */
export interface OrthoFrustum {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/**
 * The frustum for a canvas of this size.
 *
 * r3f applies exactly this on RESIZE (`updateCamera`), but not when a camera is
 * swapped in with `set({ camera })` — so an ortho camera activated between two
 * resizes would carry three.js's default 1-unit frustum and render the scene at
 * a wild scale until the window happened to change. Same arithmetic, applied at
 * the one moment r3f does not.
 */
export function orthoFrustum(width: number, height: number): OrthoFrustum {
  return {
    left: -width / 2,
    right: width / 2,
    top: height / 2,
    bottom: -height / 2,
  };
}

/**
 * Clip planes for an orthographic camera framing a subject of `diagonal`
 * sitting `distance` away.
 *
 * Orthographic depth is LINEAR, so there is no precision argument for a tight
 * near plane the way there is under perspective (where `near` too small
 * destroys the depth buffer). The only requirement is that the slab contains
 * the subject with room for the bench grid behind it — and that it never goes
 * negative-and-clipping when the modeler dollies in close.
 */
export function orthoClipPlanes(
  distance: number,
  diagonal: number,
): { near: number; far: number } {
  const depth = Math.max(diagonal, 1);
  return {
    // Behind the camera by a subject-depth: dollying past the near face of the
    // part must not slice it away, which a `near = 0.01` would do.
    near: -depth,
    far: Math.max(distance + depth * 4, 5000),
  };
}
