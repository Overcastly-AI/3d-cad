import { Quaternion, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import {
  occtPointToScene,
  placementMovedSq,
  placementToScene,
  type Placement,
} from "./placement";

const IDENTITY = { w: 1, x: 0, y: 0, z: 0 };

describe("occtPointToScene", () => {
  it("applies the Z-up→Y-up node rotation (x,y,z)→(x,z,-y)", () => {
    expect(occtPointToScene({ x: 1, y: 2, z: 3 })).toEqual([1, 3, -2]);
  });

  it("normalises -0 to 0 so a zero never renders signed", () => {
    expect(occtPointToScene({ x: 0, y: 0, z: 0 })).toEqual([0, 0, 0]);
  });
});

describe("placementToScene", () => {
  it("translates by occtToScene(position) with identity orientation", () => {
    const p: Placement = {
      position: { x: 10, y: 20, z: 30 },
      orientation: IDENTITY,
    };
    const t = placementToScene(p);
    expect(t.position).toEqual([10, 30, -20]);
    // Identity world orientation stays identity in scene space.
    expect(t.quaternion[3]).toBeCloseTo(1, 12);
    expect(t.quaternion[0]).toBeCloseTo(0, 12);
    expect(t.quaternion[1]).toBeCloseTo(0, 12);
    expect(t.quaternion[2]).toBeCloseTo(0, 12);
  });

  it("conjugates the world rotation so a rotated local point lands at the solved world point in scene space", () => {
    // A 90° rotation about world +Z (OCCT) takes local +X → world +Y.
    const half = Math.SQRT1_2;
    const p: Placement = {
      position: { x: 0, y: 0, z: 0 },
      orientation: { w: half, x: 0, y: 0, z: half },
    };
    const t = placementToScene(p);
    // The rendered geometry is already in scene space, so apply the derived
    // scene rotation to scene(local +X) and expect scene(world +Y).
    const localXScene = new Vector3(...occtPointToScene({ x: 1, y: 0, z: 0 }));
    const worldYScene = new Vector3(...occtPointToScene({ x: 0, y: 1, z: 0 }));
    const q = new Quaternion(
      t.quaternion[0],
      t.quaternion[1],
      t.quaternion[2],
      t.quaternion[3],
    );
    const out = localXScene.clone().applyQuaternion(q);
    expect(out.x).toBeCloseTo(worldYScene.x, 6);
    expect(out.y).toBeCloseTo(worldYScene.y, 6);
    expect(out.z).toBeCloseTo(worldYScene.z, 6);
  });

  it("normalises a zero quaternion to identity rather than NaN", () => {
    const p: Placement = {
      position: { x: 0, y: 0, z: 0 },
      orientation: { w: 0, x: 0, y: 0, z: 0 },
    };
    const t = placementToScene(p);
    expect(t.quaternion.every((n) => Number.isFinite(n))).toBe(true);
  });
});

describe("placementMovedSq", () => {
  it("is zero for equal placements and positive once the origin shifts", () => {
    const a: Placement = {
      position: { x: 0, y: 0, z: 0 },
      orientation: IDENTITY,
    };
    const b: Placement = {
      position: { x: 3, y: 4, z: 0 },
      orientation: IDENTITY,
    };
    expect(placementMovedSq(a, a)).toBe(0);
    expect(placementMovedSq(a, b)).toBeCloseTo(25, 9);
  });
});
