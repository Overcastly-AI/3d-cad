/**
 * The pick mark's scene→CSS arithmetic (board item #70).
 *
 * These exist because the portal-host rewrite is allowed to change COST and
 * nothing else. The functions under test are drei `Html`'s own numerics moved
 * into our tree, so "it still lands in the same place" is a claim somebody has
 * to be able to check — and the only honest way to check it is against values
 * derived by hand from the camera, not against the implementation's own output.
 *
 * Every expectation below is computed from the frustum in the comment above it.
 */
import { describe, expect, it } from "vitest";
import { OrthographicCamera, PerspectiveCamera, Vector3 } from "three";

import {
  depthZIndex,
  isBehindCamera,
  projectToScreen,
  slotTransform,
} from "./pickMarkProjection";

/** The quality floor's frame, and the scene camera's fov (`Viewport.tsx`). */
const WIDTH = 1280;
const HEIGHT = 800;
const FOV = 40;
const NEAR = 0.1;
const FAR = 1000;

function sceneCamera(): PerspectiveCamera {
  const camera = new PerspectiveCamera(FOV, WIDTH / HEIGHT, NEAR, FAR);
  camera.position.set(0, 0, 10);
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  return camera;
}

describe("projectToScreen", () => {
  it("puts a point on the camera axis at the centre of the frame", () => {
    const camera = sceneCamera();
    const out = { x: 0, y: 0 };
    projectToScreen(
      new Vector3(0, 0, 0),
      camera,
      WIDTH,
      HEIGHT,
      new Vector3(),
      out,
    );
    expect(out.x).toBeCloseTo(WIDTH / 2, 9);
    expect(out.y).toBeCloseTo(HEIGHT / 2, 9);
  });

  it("puts the frustum's own half-extents on the frame edges", () => {
    // At 10 units from a 40 degree camera the visible half-height is
    // 10*tan(20 deg) and the half-width is that times the 1.6 aspect. A point
    // exactly there is the right/top edge of the frame, by construction.
    const camera = sceneCamera();
    const halfHeight = 10 * Math.tan((FOV * Math.PI) / 360);
    const halfWidth = halfHeight * (WIDTH / HEIGHT);
    const out = { x: 0, y: 0 };
    projectToScreen(
      new Vector3(halfWidth, halfHeight, 0),
      camera,
      WIDTH,
      HEIGHT,
      new Vector3(),
      out,
    );
    expect(out.x).toBeCloseTo(WIDTH, 6);
    // Screen y grows DOWNWARD: the top of the frustum is y = 0, not y = 800.
    // Getting this inverted is the classic way to put every mark on the wrong
    // side of its anchor, so it is asserted rather than assumed.
    expect(out.y).toBeCloseTo(0, 6);
  });

  it("leaves the point it was handed untouched", () => {
    // The caller passes the mark's live world position; projecting it in place
    // would corrupt the distance reading taken from it immediately after.
    const camera = sceneCamera();
    const point = new Vector3(1, 2, 3);
    projectToScreen(point, camera, WIDTH, HEIGHT, new Vector3(), {
      x: 0,
      y: 0,
    });
    expect([point.x, point.y, point.z]).toEqual([1, 2, 3]);
  });
});

describe("isBehindCamera", () => {
  const at = (x: number, y: number, z: number) => new Vector3(x, y, z);
  const origin = at(0, 0, 0);
  /** A camera at the origin with three.js's default forward direction. */
  const forward = at(0, 0, -1);

  it("keeps a point in front", () => {
    expect(isBehindCamera(at(0, 0, -5), origin, forward, new Vector3())).toBe(
      false,
    );
  });

  it("drops a point behind", () => {
    expect(isBehindCamera(at(0, 0, 5), origin, forward, new Vector3())).toBe(
      true,
    );
  });

  it("keeps a point exactly abeam — the boundary is > 90 degrees, not >=", () => {
    // drei's own convention. A mark that vanishes half a degree early on a
    // pan is a flicker, and the direction of the inequality is the whole
    // difference, so it is pinned here.
    expect(isBehindCamera(at(5, 0, 0), origin, forward, new Vector3())).toBe(
      false,
    );
  });
});

describe("depthZIndex", () => {
  const range: [number, number] = [30, 10];

  it("maps the near plane to the top of the band and the far plane to the bottom", () => {
    const camera = sceneCamera();
    expect(depthZIndex(NEAR, camera, range)).toBe(30);
    expect(depthZIndex(FAR, camera, range)).toBe(10);
  });

  it("puts a nearer mark above a further one", () => {
    // a = (10-30)/(1000-0.1) = -0.0200020..., b = 10 - a*1000 = 30.00200...
    // so at 500 units the index is round(-10.00100 + 30.00200) = 20.
    const camera = sceneCamera();
    expect(depthZIndex(500, camera, range)).toBe(20);
    expect(depthZIndex(100, camera, range)).toBeGreaterThan(
      depthZIndex(500, camera, range) ?? 0,
    );
  });

  it("maps an orthographic camera too — the projection toggle swaps to one", () => {
    const camera = new OrthographicCamera(-640, 640, 400, -400, NEAR, FAR);
    expect(depthZIndex(NEAR, camera, range)).toBe(30);
    expect(depthZIndex(FAR, camera, range)).toBe(10);
  });

  it("refuses a camera with no frustum rather than inventing an index", () => {
    // The caller leaves the existing z-index in place on null. Writing a
    // fabricated one would silently restack every mark against the HUD.
    const bare = { far: 1, near: 0 } as unknown as PerspectiveCamera;
    expect(depthZIndex(0.5, bare, range)).toBeNull();
  });

  it("recognises a camera from a SECOND copy of three, not just ours", () => {
    // three ships an ESM and a CJS build and a bundle routinely carries both,
    // so `camera instanceof PerspectiveCamera` is FALSE for a perfectly good
    // camera that came from the other copy — and the symptom is silent (marks
    // keep whatever z-index they had, so the overlay quietly restacks). The
    // duck-typed flag is three's own cross-realm answer; this stand-in has the
    // flag and none of our classes in its prototype chain.
    const foreign = {
      isPerspectiveCamera: true,
      near: NEAR,
      far: FAR,
    } as unknown as PerspectiveCamera;
    expect(foreign).not.toBeInstanceOf(PerspectiveCamera);
    expect(depthZIndex(NEAR, foreign, range)).toBe(30);
  });
});

describe("slotTransform", () => {
  it("translates to the point and then back by half the mark's own box", () => {
    // Two steps, because the slot is ONE element doing what drei split across
    // an outer host div and an inner `center` div.
    expect(slotTransform(640, 400)).toBe(
      "translate3d(640px,400px,0) translate3d(-50%,-50%,0)",
    );
  });
});
