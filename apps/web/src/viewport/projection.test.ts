import { describe, expect, it } from "vitest";

import { fitZoom } from "./fitFraming";
import {
  distanceForOrthoZoom,
  orthoClipPlanes,
  orthoFrustum,
  orthoZoomForDistance,
} from "./projection";

/**
 * The projection swap's arithmetic (ORTHO-1).
 *
 * What these guard is not "the formula is the formula" — it is the one thing a
 * user notices when the swap is wrong: the model changing SIZE when only its
 * convergence should change. Both directions, and their composition, because
 * the toggle is pressed both ways.
 */

/** The canvas the quality floor names, and the scene camera's fov. */
const HEIGHT_PX = 800;
const FOV = 40;
const TAN = Math.tan((FOV * Math.PI) / 360);

describe("orthoZoomForDistance / distanceForOrthoZoom", () => {
  it("preserves apparent size across the swap", () => {
    // A 120mm part framed at 210mm fills some fraction of the frame under
    // perspective; the same fraction must survive into the parallel camera.
    const distance = 210;
    const zoom = orthoZoomForDistance(HEIGHT_PX, distance, FOV);
    const visibleHeightPerspective = 2 * distance * TAN;
    const visibleHeightParallel = HEIGHT_PX / zoom;
    expect(visibleHeightParallel).toBeCloseTo(visibleHeightPerspective, 9);
  });

  it("round-trips — pressing the toggle twice is a no-op", () => {
    // The failure this catches is a slow drift: a user who toggles while
    // comparing two features would zoom out a step each time.
    for (const distance of [12, 210, 4200]) {
      const zoom = orthoZoomForDistance(HEIGHT_PX, distance, FOV);
      expect(distanceForOrthoZoom(HEIGHT_PX, zoom, FOV)).toBeCloseTo(
        distance,
        6,
      );
    }
  });

  it("scales with the frame, not with the part", () => {
    // Twice the canvas height at the same distance is twice the zoom, because
    // the frustum is measured in canvas pixels (r3f's convention).
    const a = orthoZoomForDistance(HEIGHT_PX, 210, FOV);
    const b = orthoZoomForDistance(HEIGHT_PX * 2, 210, FOV);
    expect(b).toBeCloseTo(a * 2, 9);
  });

  it("returns 0 rather than Infinity or NaN on degenerate input", () => {
    // The rig keeps whatever it has on a 0. A NaN zoom blanks the viewport
    // silently, which is the worst outcome available here.
    expect(orthoZoomForDistance(0, 210, FOV)).toBe(0);
    expect(orthoZoomForDistance(HEIGHT_PX, 0, FOV)).toBe(0);
    expect(orthoZoomForDistance(HEIGHT_PX, 210, 0)).toBe(0);
    expect(distanceForOrthoZoom(HEIGHT_PX, 0, FOV)).toBe(0);
    expect(distanceForOrthoZoom(0, 4, FOV)).toBe(0);
  });
});

describe("orthoFrustum", () => {
  it("matches r3f's own convention (canvas half-extents)", () => {
    // `updateCamera` in @react-three/fiber sets exactly this on resize. If the
    // two ever disagree the scene would jump scale the first time the window
    // is resized after a swap — and only then, which is a miserable bug.
    expect(orthoFrustum(1280, 800)).toEqual({
      left: -640,
      right: 640,
      top: 400,
      bottom: -400,
    });
  });

  it("is the unit `fitZoom` solves in", () => {
    // The contract between the two files, asserted rather than commented: a
    // subject fitted to a rect must project inside that rect's pixels, where
    // one world unit is `zoom` pixels.
    const free = { x: 0, y: 0, width: 1280, height: 800 };
    const corners = [
      { a: -60, b: -40, c: 0 },
      { a: 60, b: 40, c: 0 },
    ];
    const zoom = fitZoom(corners, free);
    expect(60 * zoom).toBeLessThanOrEqual(orthoFrustum(1280, 800).right);
  });
});

describe("orthoClipPlanes", () => {
  it("contains the subject from in front of it as well as behind", () => {
    // Parallel depth is linear, so the slab is sized for CONTAINMENT. A near
    // plane at +0.01 would slice the part in half the moment the modeler
    // dollies past its front face — which a parallel camera happily allows,
    // since dollying does not change the size.
    const { near, far } = orthoClipPlanes(210, 120);
    expect(near).toBeLessThan(0);
    expect(near).toBeLessThanOrEqual(-120);
    expect(far).toBeGreaterThan(210 + 120);
  });

  it("keeps the bench grid inside the slab", () => {
    // The grid reads to the horizon (mandate 3a); a far plane that ended at
    // the part would cut it off mid-frame.
    expect(orthoClipPlanes(210, 120).far).toBeGreaterThanOrEqual(5000);
  });

  it("never collapses on a degenerate subject", () => {
    const { near, far } = orthoClipPlanes(0, 0);
    expect(far - near).toBeGreaterThan(0);
  });
});
