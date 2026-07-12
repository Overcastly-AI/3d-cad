import { describe, expect, it } from "vitest";

import {
  DATUM_PLANES,
  offsetBasis,
  originBasis,
  PLANE_BASES,
  planeCameraPose,
  planeRefFromSpec,
  planeToWorld,
  resolveSpecBasis,
  snapPoint,
  snapValue,
  worldToPlane,
} from "./plane";

describe("plane bases", () => {
  it("matches build123d's datum planes (normal = u × v)", () => {
    for (const plane of DATUM_PLANES) {
      const { u, v, normal } = PLANE_BASES[plane];
      const cross = [
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
      ];
      expect(cross).toEqual([...normal]);
    }
    expect(PLANE_BASES.XZ.normal).toEqual([0, -1, 0]); // build123d Plane.XZ
    // Origin datums sit through the world origin.
    for (const plane of DATUM_PLANES) {
      expect([...PLANE_BASES[plane].origin]).toEqual([0, 0, 0]);
    }
  });

  it("maps plane points into the right world axes (origin datums)", () => {
    expect(planeToWorld(originBasis("XY"), { x: 3, y: 4 })).toEqual([3, 4, 0]);
    expect(planeToWorld(originBasis("XZ"), { x: 3, y: 4 })).toEqual([3, 0, 4]);
    expect(planeToWorld(originBasis("YZ"), { x: 3, y: 4 })).toEqual([0, 3, 4]);
  });

  it("round-trips world → plane → world on the plane", () => {
    for (const plane of DATUM_PLANES) {
      const basis = originBasis(plane);
      const point = { x: -12.5, y: 7.25 };
      expect(worldToPlane(basis, planeToWorld(basis, point))).toEqual(point);
    }
  });

  it("projects off-plane world points along the normal", () => {
    expect(worldToPlane(originBasis("XY"), [3, 4, 99])).toEqual({ x: 3, y: 4 });
    expect(worldToPlane(originBasis("XZ"), [3, -99, 4])).toEqual({
      x: 3,
      y: 4,
    });
  });
});

describe("offsetBasis — the sketch-at-a-height math", () => {
  it("slides the origin along the base normal by offset_mm", () => {
    // XY normal is +Z, so a +30 offset lifts the plane to z=30.
    const up = offsetBasis("XY", 30, false);
    expect([...up.origin]).toEqual([0, 0, 30]);
    // Orientation is unchanged from the base, so u/v are identical.
    expect([...up.u]).toEqual([1, 0, 0]);
    expect([...up.v]).toEqual([0, 1, 0]);
    expect([...up.normal]).toEqual([0, 0, 1]);
    // A plane point maps to world at the offset height.
    expect(planeToWorld(up, { x: 5, y: 7 })).toEqual([5, 7, 30]);
  });

  it("uses the base normal's sign (XZ normal is −Y)", () => {
    const back = offsetBasis("XZ", 10, false);
    expect([...back.origin]).toEqual([0, -10, 0]);
    expect(planeToWorld(back, { x: 2, y: 3 })).toEqual([2, -10, 3]);
  });

  it("flip reverses the normal and v, keeps u and the offset origin", () => {
    const flipped = offsetBasis("XY", 30, true);
    // Origin still slides along the ORIGINAL base normal (offset unchanged).
    expect([...flipped.origin]).toEqual([0, 0, 30]);
    expect([...flipped.u]).toEqual([1, 0, 0]); // +u unchanged
    expect(flipped.v[1]).toBe(-1); // +v flips
    expect(flipped.normal[2]).toBe(-1); // normal flips (was +1)
    // A negative offset selects the other side.
    expect([...offsetBasis("XY", -12, false).origin]).toEqual([0, 0, -12]);
  });

  it("offset 0 coincides with the origin datum", () => {
    expect([...offsetBasis("XY", 0, false).origin]).toEqual([0, 0, 0]);
    expect(planeToWorld(offsetBasis("YZ", 0, false), { x: 3, y: 4 })).toEqual(
      planeToWorld(originBasis("YZ"), { x: 3, y: 4 }),
    );
  });
});

describe("plane spec ↔ wire ref", () => {
  it("resolves an origin spec to its world-frame basis", () => {
    expect([
      ...resolveSpecBasis({ kind: "origin", base: "XZ" }).origin,
    ]).toEqual([0, 0, 0]);
  });

  it("resolves an offset spec to its placed basis", () => {
    const basis = resolveSpecBasis({
      kind: "offset",
      base: "XY",
      offsetMm: 25,
      flip: false,
      datumFeatureId: "f-1",
    });
    expect([...basis.origin]).toEqual([0, 0, 25]);
  });

  it("builds a datum_plane ref for an origin spec", () => {
    expect(planeRefFromSpec({ kind: "origin", base: "YZ" })).toEqual({
      kind: "datum_plane",
      plane: "YZ",
    });
  });

  it("builds a FeatureRef for an offset spec", () => {
    expect(
      planeRefFromSpec({
        kind: "offset",
        base: "XY",
        offsetMm: 30,
        flip: false,
        datumFeatureId: "f-p001",
      }),
    ).toEqual({ kind: "feature", feature_id: "f-p001" });
  });
});

describe("planeCameraPose", () => {
  it("looks normal-on with the sketch +v axis up (origin datums)", () => {
    expect(planeCameraPose(originBasis("XY"), 140)).toEqual({
      position: [0, 0, 140],
      up: [0, 1, 0],
      target: [0, 0, 0],
    });
    // XZ's normal is −Y (build123d), so the camera sits below the ground.
    expect(planeCameraPose(originBasis("XZ"), 140).position).toEqual([
      0, -140, 0,
    ]);
    expect(planeCameraPose(originBasis("YZ"), 140).up).toEqual([0, 0, 1]);
  });

  it("sits normal-on above an offset plane, looking at its centre", () => {
    const pose = planeCameraPose(offsetBasis("XY", 30, false), 140);
    expect(pose.position).toEqual([0, 0, 170]); // 30 + 140 along +Z
    expect(pose.target).toEqual([0, 0, 30]); // the plane centre
  });
});

describe("snap", () => {
  it("rounds to the step and disables at step <= 0", () => {
    expect(snapValue(12.4, 1)).toBe(12);
    expect(snapValue(12.5, 1)).toBe(13);
    expect(snapValue(-3.6, 1)).toBe(-4);
    expect(snapValue(12.4, 0)).toBe(12.4);
  });

  it("never produces -0", () => {
    expect(Object.is(snapValue(-0.4, 1), 0)).toBe(true);
  });

  it("snaps both coordinates of a point", () => {
    expect(snapPoint({ x: 1.2, y: -2.7 }, 1)).toEqual({ x: 1, y: -3 });
  });
});
