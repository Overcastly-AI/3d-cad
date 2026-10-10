import { describe, expect, it } from "vitest";

import type { OverlayResult } from "../api/measure";
import {
  beginJointDrag,
  beginPlaneDrag,
  driveModeFor,
  type JointAxis,
  placementAfterDrive,
  placementAfterShift,
  rayAngleAbout,
  rayParamAlong,
  type Ray,
  sceneRayToKernel,
  worldPoint,
  wrapDelta,
} from "./jointDrag";
import { facePoints, nearestPoint, originCandidates } from "./jointOrigins";
import type { Placement } from "./placement";

/** The hinge axis: world +Z through (20, 12.5, 10). */
const hinge: JointAxis = {
  point: { x: 20, y: 12.5, z: 10 },
  dir: { x: 0, y: 0, z: 1 },
};
/** A ray straight down onto the plane z = 10 at (x, y). */
const down = (x: number, y: number): Ray => ({
  origin: { x, y, z: 100 },
  dir: { x: 0, y: 0, z: -1 },
});
const identity: Placement = {
  position: { x: 0, y: 0, z: 10 },
  orientation: { w: 1, x: 0, y: 0, z: 0 },
};

describe("projecting the pointer onto a revolute's axis", () => {
  it("reads the angle about the axis, right-handed", () => {
    const east = rayAngleAbout(hinge, down(30, 12.5));
    const north = rayAngleAbout(hinge, down(20, 22.5));
    expect(east).not.toBeNull();
    expect(wrapDelta(east as number, north as number)).toBeCloseTo(
      Math.PI / 2,
      12,
    );
  });

  it("refuses an edge-on plane rather than inventing an angle", () => {
    const sideways: Ray = {
      origin: { x: -100, y: 12.5, z: 10 },
      dir: { x: 1, y: 0, z: 0 },
    };
    expect(rayAngleAbout(hinge, sideways)).toBeNull();
  });

  it("winds past ±180° and stops at the limits", () => {
    const drag = beginJointDrag({
      mode: "turn",
      axis: hinge,
      value: 0,
      min: -3600,
      max: 200,
      ray: down(30, 12.5),
    });
    if (drag === null) throw new Error("press should be readable");
    const at = (deg: number) => {
      const r = (deg * Math.PI) / 180;
      return down(20 + 10 * Math.cos(r), 12.5 + 10 * Math.sin(r));
    };
    expect(drag.move(at(90))).toBeCloseTo(90, 6);
    expect(drag.move(at(170))).toBeCloseTo(170, 6);
    // Past the half turn the sweep keeps counting instead of jumping to -170.
    expect(drag.move(at(190))).toBeCloseTo(190, 6);
    // ...and the limit holds however far the pointer goes.
    expect(drag.move(at(260))).toBe(200);
  });
});

describe("the grabbed point stays under an oblique cursor", () => {
  it("reads the sweep on the plane through the point pressed", () => {
    const eye = { x: 60, y: -40, z: 80 };
    const toward = (p: { x: number; y: number; z: number }): Ray => {
      const d = { x: p.x - eye.x, y: p.y - eye.y, z: p.z - eye.z };
      const n = Math.hypot(d.x, d.y, d.z);
      return { origin: eye, dir: { x: d.x / n, y: d.y / n, z: d.z / n } };
    };
    // A point on B's top face, 10 mm above the axis origin's plane.
    const on = (deg: number) => {
      const r = (deg * Math.PI) / 180;
      return { x: 20 + 15 * Math.cos(r), y: 12.5 + 15 * Math.sin(r), z: 20 };
    };
    const drag = beginJointDrag({
      mode: "turn",
      axis: hinge,
      value: 0,
      min: -3600,
      max: 3600,
      ray: toward(on(0)),
      grab: on(0),
    });
    if (drag === null) throw new Error("press should be readable");
    drag.move(toward(on(30)));
    expect(drag.move(toward(on(60)))).toBeCloseTo(60, 3);
  });
});

describe("projecting the pointer onto a slider's axis", () => {
  const rail: JointAxis = {
    point: { x: 0, y: 0, z: 0 },
    dir: { x: 1, y: 0, z: 0 },
  };
  it("takes the ray's closest approach along the axis", () => {
    expect(rayParamAlong(rail, down(42, 7))).toBeCloseTo(42, 12);
    const along: Ray = { origin: { x: -5, y: 0, z: 0 }, dir: rail.dir };
    expect(rayParamAlong(rail, along)).toBeNull();
  });

  it("moves by the pointer's travel from the press, clamped", () => {
    const drag = beginJointDrag({
      mode: "slide",
      axis: rail,
      value: 10,
      min: 0,
      max: 50,
      ray: down(5, 3),
    });
    if (drag === null) throw new Error("press should be readable");
    expect(drag.move(down(25, -4))).toBeCloseTo(30, 6);
    expect(drag.move(down(-40, 0))).toBe(0);
  });
});

describe("one drag scheme for every motion", () => {
  it("turns on a plain drag and slides on Shift where both are free", () => {
    expect(driveModeFor("revolute", true)).toBe("turn");
    expect(driveModeFor("slider", false)).toBe("slide");
    expect(driveModeFor("cylindrical", false)).toBe("turn");
    expect(driveModeFor("cylindrical", true)).toBe("slide");
    expect(driveModeFor("planar", false)).toBe("turn");
    expect(driveModeFor("planar", true)).toBe("plane");
  });

  it("slides a planar joint across its plane, never off it", () => {
    // The plane z = 10 (normal +Z), pressed at (20, 12.5) from an oblique eye.
    const eye = { x: 60, y: -40, z: 80 };
    const toward = (x: number, y: number): Ray => {
      const d = { x: x - eye.x, y: y - eye.y, z: 10 - eye.z };
      const n = Math.hypot(d.x, d.y, d.z);
      return { origin: eye, dir: { x: d.x / n, y: d.y / n, z: d.z / n } };
    };
    const drag = beginPlaneDrag({
      axis: hinge,
      ray: toward(20, 12.5),
      grab: { x: 20, y: 12.5, z: 10 },
    });
    if (drag === null) throw new Error("press should be readable");
    const shift = drag.move(toward(27, 9.5));
    expect(shift?.x).toBeCloseTo(7, 3);
    expect(shift?.y).toBeCloseTo(-3, 3);
    expect(shift?.z).toBe(0);
    // Edge-on, the plane cannot be read: no shift is invented.
    const sideways: Ray = {
      origin: { x: -100, y: 12.5, z: 10 },
      dir: { x: 1, y: 0, z: 0 },
    };
    expect(drag.move(sideways)).toBeNull();
    const moved = placementAfterShift(identity, { x: 7, y: -3, z: 0 });
    expect(moved.position).toEqual({ x: 7, y: -3, z: 10 });
    expect(moved.orientation).toEqual(identity.orientation);
  });
});

describe("the local preview pose", () => {
  it("turns a part about the axis, leaving every point on the axis fixed", () => {
    const turned = placementAfterDrive(identity, "turn", hinge, 90);
    // B's own origin sits on the axis: it does not move at all.
    const origin = worldPoint(turned, { x: 20, y: 12.5, z: 0 });
    expect(origin.x).toBeCloseTo(20, 12);
    expect(origin.y).toBeCloseTo(12.5, 12);
    expect(origin.z).toBeCloseTo(10, 12);
    // A corner 20 along +X of the axis swings to 20 along +Y.
    const corner = worldPoint(turned, { x: 40, y: 12.5, z: 0 });
    expect(corner.x).toBeCloseTo(20, 9);
    expect(corner.y).toBeCloseTo(32.5, 9);
  });

  it("slides a part along the axis without turning it", () => {
    const slid = placementAfterDrive(identity, "slide", hinge, 7);
    expect(slid.position).toEqual({ x: 0, y: 0, z: 17 });
    expect(slid.orientation).toEqual(identity.orientation);
  });

  it("maps a scene (Y-up) ray into the kernel (Z-up) frame", () => {
    const ray = sceneRayToKernel([1, 2, 3], [0, -2, 0]);
    expect(ray.origin).toEqual({ x: 1, y: -3, z: 2 });
    expect(ray.dir).toEqual({ x: 0, y: 0, z: -1 });
  });
});

describe("joint origin snap points", () => {
  // A 40×25×10 plate: its top face, the hole's top rim, and one top edge.
  const overlay = {
    vertices: [],
    faces: [
      {
        index: 1,
        planar: true,
        signature: {
          subshape_type: "face",
          surface: "plane",
          normal: { x: 0, y: 0, z: 1 },
          centroid: { x: 20, y: 12.5, z: 10 },
          area_mm2: 921.46,
        },
      },
      { index: 2, planar: false, signature: null },
    ],
    edges: [
      {
        kind: "circle",
        start: { x: 25, y: 12.5, z: 10 },
        end: { x: 25, y: 12.5, z: 10 },
        polyline: [],
        signature: {
          subshape_type: "edge",
          curve: "circle",
          end_a: { x: 25, y: 12.5, z: 10 },
          end_b: { x: 25, y: 12.5, z: 10 },
          midpoint: { x: 15, y: 12.5, z: 10 },
          length_mm: 31.4,
        },
      },
      {
        kind: "line",
        start: { x: 0, y: 0, z: 10 },
        end: { x: 40, y: 0, z: 10 },
        polyline: [],
        signature: {
          subshape_type: "edge",
          curve: "line",
          end_a: { x: 0, y: 0, z: 10 },
          end_b: { x: 40, y: 0, z: 10 },
          midpoint: { x: 20, y: 0, z: 10 },
          length_mm: 40,
        },
      },
      {
        kind: "line",
        start: { x: 0, y: 0, z: 0 },
        end: { x: 40, y: 0, z: 0 },
        polyline: [],
        signature: {
          subshape_type: "edge",
          curve: "line",
          end_a: { x: 0, y: 0, z: 0 },
          end_b: { x: 40, y: 0, z: 0 },
          midpoint: { x: 20, y: 0, z: 0 },
          length_mm: 40,
        },
      },
    ],
  } as unknown as OverlayResult;

  it("offers face centres, hole centres and edge start / mid / end", () => {
    const keys = originCandidates(overlay).map((c) => c.key);
    expect(keys).toEqual([
      "face-1",
      "circle-0",
      "edge-1-start",
      "edge-1-mid",
      "edge-1-end",
      "edge-2-start",
      "edge-2-mid",
      "edge-2-end",
    ]);
    const hole = originCandidates(overlay)[1];
    expect(hole?.label).toBe(
      "Hole centre, edge 1, at 20, 12.5, 10 millimetres",
    );
  });

  it("reveals the hovered face's own points and snaps to the nearest", () => {
    const all = originCandidates(overlay);
    const top = facePoints(all, 1).map((c) => c.key);
    // The bottom edge (z = 0) is not in the top face's plane.
    expect(top).toEqual([
      "face-1",
      "circle-0",
      "edge-1-start",
      "edge-1-mid",
      "edge-1-end",
    ]);
    expect(facePoints(all, 2)).toEqual([]);
    const near = nearestPoint(facePoints(all, 1), { x: 38, y: 1, z: 10 });
    expect(near?.key).toBe("edge-1-end");
  });
});
