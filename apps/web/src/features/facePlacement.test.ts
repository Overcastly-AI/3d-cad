import { describe, expect, it } from "vitest";

import type { OverlayEdge, Vec3 } from "../api/measure";
import type { PlanarFaceSignature } from "../api/parts";
import {
  checkPlacement,
  describeDirection,
  faceFrame,
  facePlacement,
  toFacePoint,
  toWorldPoint,
} from "./facePlacement";

/**
 * The dogfooding part, reduced to what the client can see (QA-REVIEW
 * 2026-08-01, QA3-1): a plate's BACK face at z = 0 — a 42.3 mm square outline,
 * a Ø5.2 shaft bore on the axis, and four Ø3 mounting holes on a 31 mm square.
 * Its area centroid is NOT (0, 0) on purpose in one test below: that is the
 * whole reason the frame's origin is the part origin and not the centroid.
 */
const BACK: PlanarFaceSignature = {
  normal: { x: 0, y: 0, z: -1 },
  centroid: { x: 0, y: 0, z: 0 },
  area_mm2: 1689.7785,
  subshape_type: "face",
  surface: "plane",
};

function lineEdge(a: Vec3, b: Vec3): OverlayEdge {
  return {
    kind: "line",
    start: a,
    end: b,
    polyline: [a, b],
    signature: {
      curve: "line",
      end_a: a,
      end_b: b,
      midpoint: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 },
      length_mm: Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z),
      subshape_type: "edge",
    },
  };
}

/** A full circle in the z = `z` plane, sampled the way the tessellator does. */
function circleEdge(cx: number, cy: number, r: number, z: number): OverlayEdge {
  const points: Vec3[] = [];
  const n = 32;
  for (let i = 0; i <= n; i += 1) {
    const t = (2 * Math.PI * i) / n;
    points.push({ x: cx + r * Math.cos(t), y: cy + r * Math.sin(t), z });
  }
  const first = points[0] as Vec3;
  return {
    kind: "circle",
    start: first,
    end: first,
    polyline: points,
    signature: {
      curve: "circle",
      end_a: first,
      end_b: first,
      midpoint: { x: cx - r, y: cy, z },
      length_mm: 2 * Math.PI * r,
      subshape_type: "edge",
    },
  };
}

function squareOutline(half: number, z: number): OverlayEdge[] {
  const c: Vec3[] = [
    { x: -half, y: -half, z },
    { x: half, y: -half, z },
    { x: half, y: half, z },
    { x: -half, y: half, z },
  ];
  return c.map((a, i) => lineEdge(a, c[(i + 1) % 4] as Vec3));
}

const PLATE: OverlayEdge[] = [
  ...squareOutline(21.15, 0),
  circleEdge(0, 0, 2.6, 0),
  circleEdge(15.5, 15.5, 1.5, 0),
  circleEdge(-15.5, 15.5, 1.5, 0),
  circleEdge(15.5, -15.5, 1.5, 0),
  circleEdge(-15.5, -15.5, 1.5, 0),
  // The FRONT face's boss rim, 8 mm away — a different plane, never a snap here.
  circleEdge(0, 0, 11, 8),
];

describe("faceFrame", () => {
  it("puts 0,0 at the part origin projected onto the face, not at the centroid", () => {
    // The QA3-2 mechanism, refused: adding a hole moves a face's AREA centroid,
    // so a frame seated there means the same typed coordinate drills somewhere
    // else after the next edit. Two signatures, same plane, centroid shifted by
    // the 0.065 mm the dogfooding pass measured — one frame.
    const shifted: PlanarFaceSignature = {
      ...BACK,
      centroid: { x: 0.065111, y: 0, z: 0 },
      area_mm2: 1661.5,
    };
    expect(faceFrame(shifted).origin).toEqual(faceFrame(BACK).origin);
    const origin = faceFrame(BACK).origin;
    expect(origin.x).toBeCloseTo(0, 12);
    expect(origin.y).toBeCloseTo(0, 12);
    expect(origin.z).toBeCloseTo(0, 12);
  });

  it("keeps the part's own axes on an axis-aligned face", () => {
    const frame = faceFrame(BACK);
    expect(describeDirection(frame.u)).toBe("+X");
    // Right-handed against the outward -Z normal: Y runs the other way, and
    // saying so is the point of the FRAME row.
    expect(describeDirection(frame.v)).toBe("-Y");
    expect(describeDirection(frame.normal)).toBe("-Z");
  });

  it("seats the origin ON the plane of an offset face", () => {
    const top: PlanarFaceSignature = {
      ...BACK,
      normal: { x: 0, y: 0, z: 1 },
      centroid: { x: 3, y: -4, z: 8 },
    };
    const frame = faceFrame(top);
    expect(frame.origin.z).toBeCloseTo(8, 12);
    expect(describeDirection(frame.v)).toBe("+Y");
  });

  it("round-trips a coordinate through the frame", () => {
    const frame = faceFrame(BACK);
    const world = toWorldPoint(frame, { x: 15.5, y: 0 });
    expect(world.x).toBeCloseTo(15.5, 12);
    expect(world.y).toBeCloseTo(0, 12);
    expect(world.z).toBeCloseTo(0, 12);
    const back = toFacePoint(frame, world);
    expect(back.x).toBeCloseTo(15.5, 12);
    expect(back.y).toBeCloseTo(0, 12);
  });

  it("reports a direction cosine triple when the axis is not a world axis", () => {
    const angled = describeDirection({
      x: Math.SQRT1_2,
      y: Math.SQRT1_2,
      z: 0,
    });
    expect(angled).toBe("(0.707, 0.707, 0)");
  });
});

describe("facePlacement", () => {
  it("finds every circular edge IN the face's plane, largest first", () => {
    const { circles } = facePlacement(BACK, PLATE);
    expect(circles.map((c) => Number(c.radiusMm.toFixed(4)))).toEqual([
      2.6, 1.5, 1.5, 1.5, 1.5,
    ]);
    // The Ø22 boss rim sits 8 mm away on the front face — not on this one.
    expect(circles.some((c) => c.radiusMm > 3)).toBe(false);
  });

  it("puts a bore centre exactly where a concentric snap needs it", () => {
    const { circles, frame } = facePlacement(BACK, PLATE);
    const bore = circles[0]!;
    expect(bore.center.x).toBeCloseTo(0, 9);
    expect(bore.center.y).toBeCloseTo(0, 9);
    expect(bore.center.z).toBeCloseTo(0, 9);
    const mount = circles.find(
      (c) => Math.abs(toFacePoint(frame, c.center).x - 15.5) < 1e-9,
    );
    expect(mount).toBeDefined();
  });
});

describe("checkPlacement", () => {
  const placement = facePlacement(BACK, PLATE);

  it("passes the fifth mounting hole the UI could not place", () => {
    // The QA3-1 headline: (15.5, 0) is solid material on this plate, and the
    // old two-choice pick could not express it at all.
    expect(checkPlacement(placement, { x: 15.5, y: 0 }).verdict).toBe(
      "material",
    );
  });

  it("names the bore the seeded centre falls into", () => {
    const check = checkPlacement(placement, { x: 0, y: 0 });
    expect(check.verdict).toBe("opening");
    expect(check.circle?.radiusMm).toBeCloseTo(2.6, 9);
  });

  it("picks the SMALLEST containing opening, so the message names the right one", () => {
    const check = checkPlacement(placement, { x: 15.5, y: -15.5 });
    expect(check.verdict).toBe("opening");
    expect(check.circle?.radiusMm).toBeCloseTo(1.5, 9);
  });

  it("calls a point beyond the outline off the face", () => {
    expect(checkPlacement(placement, { x: 30, y: 30 }).verdict).toBe("outside");
  });

  it("says UNKNOWN rather than guessing before the overlay arrives", () => {
    expect(checkPlacement(facePlacement(BACK, null), { x: 0, y: 0 })).toEqual({
      verdict: "unknown",
      circle: null,
    });
  });
});
