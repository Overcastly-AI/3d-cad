import { Quaternion, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import {
  occtPointToScene,
  placementToScene,
  sceneToPlacement,
  scenePointToOcct,
  type Placement,
  type SceneTransform,
} from "./placement";

/** A deterministic spread of poses: every octant, odd angles, a half-turn. */
function samplePlacements(): Placement[] {
  const axes: [number, number, number][] = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
    [1, 2, 3],
    [-0.3, 0.9, -0.4],
  ];
  const angles = [0, 0.37, Math.PI / 2, 2.9, Math.PI];
  const positions = [
    { x: 0, y: 0, z: 0 },
    { x: 80, y: 30, z: 0 },
    { x: -12.5, y: 4.25, z: -300 },
  ];
  const out: Placement[] = [];
  for (const axis of axes) {
    for (const angle of angles) {
      for (const position of positions) {
        const q = new Quaternion().setFromAxisAngle(
          new Vector3(...axis).normalize(),
          angle,
        );
        out.push({
          position,
          orientation: { w: q.w, x: q.x, y: q.y, z: q.z },
        });
      }
    }
  }
  return out;
}

/** Same rotation: |q·q'| = 1 (q and −q are one rotation). */
function expectSameRotation(
  a: Placement["orientation"],
  b: Placement["orientation"],
): void {
  const dot = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z;
  expect(Math.abs(dot)).toBeCloseTo(1, 12);
}

describe("scenePointToOcct", () => {
  it("inverts occtPointToScene exactly, without signed zeros", () => {
    expect(scenePointToOcct([1, 3, -2])).toEqual({ x: 1, y: 2, z: 3 });
    const zero = scenePointToOcct([0, 0, 0]);
    expect(Object.is(zero.y, -0)).toBe(false);
  });
});

describe("sceneToPlacement", () => {
  it("round-trips every sampled placement through placementToScene", () => {
    for (const placement of samplePlacements()) {
      const back = sceneToPlacement(placementToScene(placement));
      expect(back.position.x).toBeCloseTo(placement.position.x, 9);
      expect(back.position.y).toBeCloseTo(placement.position.y, 9);
      expect(back.position.z).toBeCloseTo(placement.position.z, 9);
      expectSameRotation(back.orientation, placement.orientation);
    }
  });

  it("round-trips the other way: scene → placement → scene", () => {
    for (const placement of samplePlacements()) {
      const scene = placementToScene(placement);
      const again = placementToScene(sceneToPlacement(scene));
      for (let i = 0; i < 3; i += 1) {
        expect(again.position[i]).toBeCloseTo(scene.position[i] as number, 9);
      }
      const [x, y, z, w] = again.quaternion;
      const [x0, y0, z0, w0] = scene.quaternion;
      expect(Math.abs(x * x0 + y * y0 + z * z0 + w * w0)).toBeCloseTo(1, 12);
    }
  });

  it("maps a scene turn about +Y to a kernel turn about +Z (Y-up → Z-up)", () => {
    const half = Math.SQRT1_2;
    const scene: SceneTransform = {
      position: [80, 0, -30],
      quaternion: [0, half, 0, half],
    };
    const placement = sceneToPlacement(scene);
    expect(placement.position).toEqual({ x: 80, y: 30, z: 0 });
    expect(placement.orientation.w).toBeCloseTo(half, 12);
    expect(placement.orientation.z).toBeCloseTo(half, 12);
    expect(placement.orientation.x).toBeCloseTo(0, 12);
    expect(placement.orientation.y).toBeCloseTo(0, 12);
  });

  it("writes w ≥ 0 so equal poses always serialise to equal bytes", () => {
    const scene: SceneTransform = {
      position: [0, 0, 0],
      quaternion: [0, -Math.SQRT1_2, 0, -Math.SQRT1_2],
    };
    expect(sceneToPlacement(scene).orientation.w).toBeGreaterThan(0);
  });

  it("normalises a zero or unnormalised scene quaternion", () => {
    const zero = sceneToPlacement({
      position: [0, 0, 0],
      quaternion: [0, 0, 0, 0],
    });
    expect(zero.orientation).toEqual({ w: 1, x: 0, y: 0, z: 0 });
    const scaled = sceneToPlacement({
      position: [0, 0, 0],
      quaternion: [0, 0, 0, 5],
    });
    expect(scaled.orientation.w).toBeCloseTo(1, 12);
  });

  it("agrees with the point map: a local point lands at the same world point", () => {
    const placement = samplePlacements()[23] as Placement;
    const scene = placementToScene(placement);
    const local = { x: 7, y: -2, z: 5 };
    // Kernel: R·local + t.
    const o = placement.orientation;
    const world = new Vector3(local.x, local.y, local.z)
      .applyQuaternion(new Quaternion(o.x, o.y, o.z, o.w))
      .add(
        new Vector3(
          placement.position.x,
          placement.position.y,
          placement.position.z,
        ),
      );
    // Scene: (S R S⁻¹)·S·local + S·t, read back through the inverse point map.
    const viaScene = new Vector3(...occtPointToScene(local))
      .applyQuaternion(new Quaternion(...scene.quaternion))
      .add(new Vector3(...scene.position));
    const back = scenePointToOcct([viaScene.x, viaScene.y, viaScene.z]);
    expect(back.x).toBeCloseTo(world.x, 9);
    expect(back.y).toBeCloseTo(world.y, 9);
    expect(back.z).toBeCloseTo(world.z, 9);
  });
});
