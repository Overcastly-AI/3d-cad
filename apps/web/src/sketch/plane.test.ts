import { describe, expect, it } from "vitest";

import {
  DATUM_PLANES,
  PLANE_BASES,
  planeCameraPose,
  planeToWorld,
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
  });

  it("maps plane points into the right world axes", () => {
    expect(planeToWorld("XY", { x: 3, y: 4 })).toEqual([3, 4, 0]);
    expect(planeToWorld("XZ", { x: 3, y: 4 })).toEqual([3, 0, 4]);
    expect(planeToWorld("YZ", { x: 3, y: 4 })).toEqual([0, 3, 4]);
  });

  it("round-trips world → plane → world on the plane", () => {
    for (const plane of DATUM_PLANES) {
      const point = { x: -12.5, y: 7.25 };
      expect(worldToPlane(plane, planeToWorld(plane, point))).toEqual(point);
    }
  });

  it("projects off-plane world points along the normal", () => {
    expect(worldToPlane("XY", [3, 4, 99])).toEqual({ x: 3, y: 4 });
    expect(worldToPlane("XZ", [3, -99, 4])).toEqual({ x: 3, y: 4 });
  });
});

describe("planeCameraPose", () => {
  it("looks normal-on with the sketch +v axis up", () => {
    expect(planeCameraPose("XY", 140)).toEqual({
      position: [0, 0, 140],
      up: [0, 1, 0],
      target: [0, 0, 0],
    });
    // XZ's normal is −Y (build123d), so the camera sits below the ground.
    expect(planeCameraPose("XZ", 140).position).toEqual([0, -140, 0]);
    expect(planeCameraPose("YZ", 140).up).toEqual([0, 0, 1]);
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
