/**
 * The sketch plane's own frame. Two things are pinned here, and the first is
 * the one that matters:
 *
 *  1. HONESTY OF THE NAME. A face-seated sketch's zero is the face's AREA
 *     CENTROID, which moves when the outline changes; every other plane kind's
 *     zero is a fixed datum point. Calling both "Origin" would imply a
 *     stability the face case does not have — the QA3-2 shape, where a ring
 *     drawn at "sketch (0,0)" landed 0.065 mm off centre because the origin was
 *     an unnamed centroid.
 *  2. FRAME INDEPENDENCE. Everything here is expressed in plane (u,v), never in
 *     world axes, so a change of world convention (Z-up ↔ Y-up) cannot rotate
 *     the marker off its own zero.
 */
import { describe, expect, it } from "vitest";

import { originAxisSpans, originIdentity, originRingSegments } from "./origin";
import type { PlanarFaceSignature, SketchPlaneSpec } from "./plane";

const FACE: PlanarFaceSignature = {
  subshape_type: "face",
  surface: "plane",
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 3, y: 4, z: 10 },
  area_mm2: 400,
};

describe("originIdentity — the name has to be true", () => {
  it("calls a datum plane's zero the Origin, with no caveat", () => {
    const planes: SketchPlaneSpec[] = [
      { kind: "origin", base: "XY" },
      {
        kind: "offset",
        base: "XZ",
        offsetMm: 30,
        flip: false,
        datumFeatureId: "d1",
      },
      {
        kind: "datum",
        datumFeatureId: "d2",
        label: "Midplane1",
        basis: {
          u: [1, 0, 0],
          v: [0, 1, 0],
          normal: [0, 0, 1],
          origin: [0, 0, 5],
        },
      },
    ];
    for (const plane of planes) {
      expect(originIdentity(plane)).toEqual({ label: "Origin", note: null });
    }
  });

  it("refuses to call a face's area centroid the Origin, and says it moves", () => {
    const identity = originIdentity({
      kind: "on_face",
      signature: FACE,
      offsetMm: 0,
      datumFeatureId: "d3",
    });
    expect(identity.label).toBe("Face centre");
    expect(identity.label).not.toBe("Origin");
    // The caveat is the whole point: a fixed datum zero has none, this does.
    expect(identity.note).toMatch(/moves/i);
  });

  it("falls back to the fixed-datum name before a plane is picked", () => {
    expect(originIdentity(null)).toEqual({ label: "Origin", note: null });
  });
});

describe("originAxisSpans — the drawn frame", () => {
  it("runs both axes through zero, solid on +, phantom on −", () => {
    const [x, y] = originAxisSpans(50);
    expect(x?.label).toBe("X");
    expect(x?.positive).toEqual([
      { x: 0, y: 0 },
      { x: 50, y: 0 },
    ]);
    expect(x?.negative).toEqual([
      { x: 0, y: 0 },
      { x: -50, y: 0 },
    ]);
    expect(y?.label).toBe("Y");
    expect(y?.positive).toEqual([
      { x: 0, y: 0 },
      { x: 0, y: 50 },
    ]);
    // The letter hangs ON the positive half — the pairing that makes the
    // solid/dashed encoding readable without a legend — but INSIDE the entry
    // frame, not at the tip: the axes overrun the view, and +Y's tip was
    // measurably off-screen when it sat there.
    expect(y?.tip.x).toBe(0);
    expect(y?.tip.y).toBeGreaterThan(0);
    expect(y?.tip.y).toBeLessThan(50);
    expect(x?.tip.y).toBe(0);
    expect(x?.tip.x).toBeGreaterThan(0);
    expect(x?.tip.x).toBeLessThan(50);
  });

  it("names the SKETCH's axes, not the world's — no world component anywhere", () => {
    // Every coordinate this module emits is plane (u,v). If a world axis ever
    // leaked in, a plane whose u is world −Y would draw its "X" somewhere else.
    const spans = originAxisSpans(10);
    const coordinates = spans.flatMap((span) => [
      ...span.positive,
      ...span.negative,
      span.tip,
    ]);
    expect(
      coordinates.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)),
    ).toBe(true);
    expect(spans.map((span) => span.key)).toEqual(["x", "y"]);
  });

  it("survives a degenerate extent rather than emitting NaN", () => {
    const [x] = originAxisSpans(-5);
    expect(x?.positive).toEqual([
      { x: 0, y: 0 },
      { x: 0, y: 0 },
    ]);
  });
});

describe("originRingSegments — the centre punch", () => {
  it("closes, and stays on the ring", () => {
    const radius = 2;
    const segments = originRingSegments(radius);
    expect(segments.length).toBeGreaterThan(8);
    for (const [a, b] of segments) {
      expect(Math.hypot(a.x, a.y)).toBeCloseTo(radius, 9);
      expect(Math.hypot(b.x, b.y)).toBeCloseTo(radius, 9);
    }
    const first = segments[0]?.[0];
    const last = segments[segments.length - 1]?.[1];
    expect(last?.x).toBeCloseTo(first?.x ?? NaN, 9);
    expect(last?.y).toBeCloseTo(first?.y ?? NaN, 9);
  });

  it("draws nothing at all rather than a degenerate ring", () => {
    expect(originRingSegments(0)).toEqual([]);
    expect(originRingSegments(-1)).toEqual([]);
  });
});
