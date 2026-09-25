/**
 * THE FILLET / CHAMFER ANCHOR'S ARITHMETIC (CRAFT-9a).
 *
 * The e2e drags the real gauge in a real browser and asserts that the field
 * moved and the preview redrew; that proves it is WIRED. These prove it is
 * CORRECT — that the ball is tangent to both faces, that the offset is the
 * distance it claims, and above all that the instrument is on the RIGHT SIDE
 * OF THE METAL, which is the one thing a passing drag test cannot see.
 *
 * The central case is `identical normals, opposite convexity`. A box's convex
 * edge and a step's concave one present the same two outward normals; a preview
 * that read convexity from the normals would draw the round inside the air on
 * one of them and be green on both in every other assertion here.
 */
import { describe, expect, it } from "vitest";

import {
  chamferPreview,
  edgeAnchor,
  edgeGaugeTrack,
  filletPreview,
  FULL_TURN_SEGMENTS,
  MAX_EDGE_VALUE_MM,
  MIN_EDGE_VALUE_MM,
  rollingBallCentre,
  type EdgeAnchorInput,
  type EdgeFacePlane,
} from "./edgeAnchor";
import type { Vec3 } from "@loft/design";

const ROOT_HALF = Math.SQRT1_2;

/** The edge shared by the two faces in every fixture: along X at y=1, z=1. */
const EDGE: EdgeAnchorInput = {
  key: "e",
  polyline: [
    [-1, 1, 1],
    [1, 1, 1],
  ],
  midpoint: [0, 1, 1],
  lengthMm: 2,
};

/**
 * A BOX's convex edge: the top face extends to -z from it, the front face to
 * -y. Material is the intersection of the two negative half-spaces.
 */
const CONVEX: EdgeFacePlane[] = [
  { normal: [0, 1, 0], centroid: [0, 1, 0] },
  { normal: [0, 0, 1], centroid: [0, 0, 1] },
];

/**
 * A STEP's concave edge, with THE SAME TWO NORMALS. The floor extends to +z and
 * the wall to +y, so the material is the UNION of the negative half-spaces and
 * the metal is on the other side of the same pair of planes.
 */
const CONCAVE: EdgeFacePlane[] = [
  { normal: [0, 1, 0], centroid: [0, 1, 2] },
  { normal: [0, 0, 1], centroid: [0, 2, 1] },
];

/**
 * `digits` defaults to 9 for values that never leave double precision, and
 * callers reading a drawn buffer pass 6: the previews are `Float32Array`, so a
 * point that round-trips through one is right to about 1e-7 and asserting
 * further is asserting the storage format rather than the geometry.
 */
function close(a: Vec3, b: readonly number[], digits = 9): void {
  expect(a[0]).toBeCloseTo(b[0] as number, digits);
  expect(a[1]).toBeCloseTo(b[1] as number, digits);
  expect(a[2]).toBeCloseTo(b[2] as number, digits);
}

/** Signed distance from a point to a plane. */
function planeDistance(plane: EdgeFacePlane, p: Vec3): number {
  return (
    plane.normal[0] * (p[0] - plane.centroid[0]) +
    plane.normal[1] * (p[1] - plane.centroid[1]) +
    plane.normal[2] * (p[2] - plane.centroid[2])
  );
}

/** Read a `Float32Array` of segment pairs back as points. */
function points(buffer: Float32Array): Vec3[] {
  const out: Vec3[] = [];
  for (let i = 0; i < buffer.length; i += 3) {
    out.push([
      buffer[i] as number,
      buffer[i + 1] as number,
      buffer[i + 2] as number,
    ]);
  }
  return out;
}

describe("edgeAnchor — seating", () => {
  it("finds the two faces that bound the edge and ignores the rest", () => {
    // The two side faces of the same box CONTAIN one endpoint of the edge each
    // but not the whole edge, which is exactly what `planeHoldsEdge` is for.
    const withSides: EdgeFacePlane[] = [
      ...CONVEX,
      { normal: [1, 0, 0], centroid: [1, 0, 0] },
      { normal: [-1, 0, 0], centroid: [-1, 0, 0] },
      { normal: [0, -1, 0], centroid: [0, -1, 0] },
    ];
    const anchor = edgeAnchor(EDGE, withSides);
    expect(anchor).not.toBeNull();
    close(anchor!.normals[0], [0, 1, 0]);
    close(anchor!.normals[1], [0, 0, 1]);
  });

  it("seats the gauge at the midpoint, along the outward bisector", () => {
    const anchor = edgeAnchor(EDGE, CONVEX);
    expect(anchor).not.toBeNull();
    close(anchor!.midpoint, [0, 1, 1]);
    close(anchor!.tangent, [1, 0, 0]);
    close(anchor!.outward, [0, ROOT_HALF, ROOT_HALF]);
    expect(anchor!.halfAngleCos).toBeCloseTo(ROOT_HALF, 9);
  });

  it("points each faceOut ALONG its own face, away from the edge", () => {
    const anchor = edgeAnchor(EDGE, CONVEX);
    // The top face lies at -z of this edge; the front face at -y.
    close(anchor!.faceOut[0], [0, 0, -1]);
    close(anchor!.faceOut[1], [0, -1, 0]);
    // Each direction stays ON its own plane — that is what makes the offset an
    // offset rather than a step off the face.
    expect(planeDistance(CONVEX[0] as EdgeFacePlane, [0, 1, 0])).toBeCloseTo(
      0,
      9,
    );
  });
});

describe("edgeAnchor — the case the normals cannot decide", () => {
  it("reads OPPOSITE convexity from the SAME normal pair", () => {
    const convex = edgeAnchor(EDGE, CONVEX);
    const concave = edgeAnchor(EDGE, CONCAVE);
    expect(convex).not.toBeNull();
    expect(concave).not.toBeNull();

    // Same normals, same bisector — nothing about the two faces' ORIENTATION
    // differs. A convexity test that read only these would be green here and
    // draw one of the two previews inside the air.
    close(convex!.normals[0], concave!.normals[0]);
    close(convex!.normals[1], concave!.normals[1]);
    close(convex!.outward, concave!.outward);

    expect(convex!.convex).toBe(true);
    expect(concave!.convex).toBe(false);
    // And the faces extend the other way, which is what carried the answer.
    close(convex!.faceOut[0], [0, 0, -1]);
    close(concave!.faceOut[0], [0, 0, 1]);
  });

  it("puts the ball INSIDE the metal for convex and in the notch for concave", () => {
    const r = 0.2;
    const convex = rollingBallCentre(edgeAnchor(EDGE, CONVEX)!, r);
    const concave = rollingBallCentre(edgeAnchor(EDGE, CONCAVE)!, r);
    // A 90-degree corner puts the centre at exactly (r, r) from both faces.
    close(convex, [0, 1 - r, 1 - r]);
    close(concave, [0, 1 + r, 1 + r]);
  });
});

describe("edgeAnchor — refusals, never guesses", () => {
  it("refuses an edge no planar face bounds", () => {
    expect(edgeAnchor(EDGE, [])).toBeNull();
  });

  it("refuses a CLOSED edge with only one planar face", () => {
    // A bore's rim and a boss's rim are the same circle bounding one planar
    // face whose centroid is the circle's centre in both cases; the metal is
    // inside for one and outside for the other and nothing here can tell.
    const circle: Vec3[] = [];
    for (let i = 0; i <= 32; i += 1) {
      const t = (i / 32) * Math.PI * 2;
      circle.push([Math.cos(t), 1, Math.sin(t)]);
    }
    const rim: EdgeAnchorInput = {
      key: "rim",
      polyline: circle,
      midpoint: [-1, 1, 0],
      lengthMm: 2 * Math.PI,
    };
    const top: EdgeFacePlane[] = [{ normal: [0, 1, 0], centroid: [0, 1, 0] }];
    expect(edgeAnchor(rim, top)).toBeNull();
  });

  it("refuses two back-to-back faces, which have no bisector", () => {
    const backToBack: EdgeFacePlane[] = [
      { normal: [0, 1, 0], centroid: [0, 1, 0] },
      { normal: [0, -1, 0], centroid: [0, 1, 2] },
    ];
    expect(edgeAnchor(EDGE, backToBack)).toBeNull();
  });

  it("refuses when the two convexity readings disagree", () => {
    // A face whose centroid sits across a re-entrant boundary from its own
    // edge: the top reads convex, the front reads concave.
    const disagreeing: EdgeFacePlane[] = [
      { normal: [0, 1, 0], centroid: [0, 1, 0] },
      { normal: [0, 0, 1], centroid: [0, 2, 1] },
    ];
    expect(edgeAnchor(EDGE, disagreeing)).toBeNull();
  });

  it("seats a SHOULDER — one planar face, one curved neighbour", () => {
    // The plane extends to +z; the curved surface drops away below it. The
    // curved normal at the edge is derived (-faceOut), not invented.
    const shoulder: EdgeFacePlane[] = [
      { normal: [0, 1, 0], centroid: [0, 1, 2] },
    ];
    const anchor = edgeAnchor(EDGE, shoulder);
    expect(anchor).not.toBeNull();
    close(anchor!.faceOut[0], [0, 0, 1]);
    close(anchor!.normals[1], [0, 0, -1]);
    close(anchor!.faceOut[1], [0, -1, 0]);
    close(anchor!.outward, [0, ROOT_HALF, -ROOT_HALF]);
    expect(anchor!.convex).toBe(true);
  });
});

describe("filletPreview — the round's band", () => {
  const anchor = edgeAnchor(EDGE, CONVEX)!;
  const r = 0.3;
  /** A 90-degree corner takes a quarter of a turn's segments. */
  const STEPS = FULL_TURN_SEGMENTS / 4;

  it("is TANGENT to both faces — the ball touches the metal, it does not cut it", () => {
    const centre = rollingBallCentre(anchor, r);
    // Inside the material on both faces, at exactly the radius.
    expect(planeDistance(CONVEX[0] as EdgeFacePlane, centre)).toBeCloseTo(
      -r,
      9,
    );
    expect(planeDistance(CONVEX[1] as EdgeFacePlane, centre)).toBeCloseTo(
      -r,
      9,
    );
  });

  it("draws every arc point at exactly the radius from its own ball centre", () => {
    const { arcs } = filletPreview(anchor, r);
    expect(arcs).toHaveLength(3 * STEPS * 6);
    // Each station's ball centre is the seat's, translated along the edge —
    // which for this fixture means the x coordinate varies and nothing else.
    const seat = rollingBallCentre(anchor, r);
    for (const p of points(arcs)) {
      const centre: Vec3 = [p[0], seat[1], seat[2]];
      expect(Math.hypot(p[0] - centre[0], p[1] - centre[1], p[2] - centre[2])) //
        .toBeCloseTo(r, 5);
    }
  });

  it("runs each arc between that station's two tangency points", () => {
    const { arcs } = filletPreview(anchor, r);
    const drawn = points(arcs);
    // Station 1 of 3 is the edge's START, at x = -1; its arc runs from the
    // tangency point on face 0 to the one on face 1.
    close(drawn[0] as Vec3, [-1, 1, 1 - r], 5);
    close(drawn[2 * STEPS - 1] as Vec3, [-1, 1 - r, 1], 5);
    // Station 2 is the SEAT, where the gauge stands.
    close(drawn[2 * STEPS] as Vec3, [0, 1, 1 - r], 5);
    // Station 3 is the edge's END.
    close(drawn[drawn.length - 1] as Vec3, [1, 1 - r, 1], 5);
  });

  it("closes the band with THREE distinct arcs, on a two-point edge", () => {
    // The same legibility guard the chamfer band carries: a middle station
    // taken from a polyline INDEX would land on the start one for a straight
    // edge, and the band would read as two marks.
    const drawn = points(filletPreview(anchor, r).arcs);
    const xs = [drawn[0]?.[0], drawn[2 * STEPS]?.[0], drawn[4 * STEPS]?.[0]];
    expect(new Set(xs).size).toBe(3);
    expect(xs).toEqual([-1, 0, 1]);
  });

  it("lays the tangency lines the length of the edge, r from it on each face", () => {
    const { tangencyLines } = filletPreview(anchor, r);
    const drawn = points(tangencyLines);
    expect(drawn).toHaveLength(4); // two 2-point polylines
    close(drawn[0] as Vec3, [-1, 1, 1 - r], 6);
    close(drawn[1] as Vec3, [1, 1, 1 - r], 6);
    close(drawn[2] as Vec3, [-1, 1 - r, 1], 6);
    close(drawn[3] as Vec3, [1, 1 - r, 1], 6);
  });

  it("REDRAWS when the value moves — the whole point of route (b)", () => {
    const small = filletPreview(anchor, 0.2);
    const large = filletPreview(anchor, 0.6);
    expect(Array.from(small.arcs)).not.toEqual(Array.from(large.arcs));
    expect(Array.from(small.tangencyLines)) //
      .not.toEqual(Array.from(large.tangencyLines));
  });

  it("draws nothing at a non-positive radius", () => {
    const none = filletPreview(anchor, 0);
    expect(none.arcs).toHaveLength(0);
    expect(none.tangencyLines).toHaveLength(0);
  });
});

describe("chamferPreview — the bevel band", () => {
  const anchor = edgeAnchor(EDGE, CONVEX)!;
  const d = 0.25;

  it("offsets each face by exactly the distance", () => {
    const { offsets } = chamferPreview(anchor, d);
    const drawn = points(offsets);
    close(drawn[0] as Vec3, [-1, 1, 1 - d], 6);
    close(drawn[2] as Vec3, [-1, 1 - d, 1], 6);
  });

  it("closes the band with THREE distinct rungs, on a two-point edge", () => {
    // The legibility guard. A middle rung taken from a polyline INDEX lands on
    // top of the start rung for a straight edge — arithmetically fine, and the
    // band then reads as two marks. The middle one comes from the midpoint.
    const { bevels } = chamferPreview(anchor, d);
    const drawn = points(bevels);
    expect(drawn).toHaveLength(6);
    const xs = [drawn[0]?.[0], drawn[2]?.[0], drawn[4]?.[0]];
    expect(new Set(xs).size).toBe(3);
    expect(xs).toEqual([-1, 0, 1]);
  });

  it("REDRAWS when the value moves", () => {
    expect(Array.from(chamferPreview(anchor, 0.2).offsets)) //
      .not.toEqual(Array.from(chamferPreview(anchor, 0.5).offsets));
  });
});

describe("the two verbs share one offset", () => {
  it("a fillet's tangency lines ARE a chamfer's offsets at the same value", () => {
    // Not a coincidence and worth pinning: a ball of radius r seated in the
    // corner touches each face exactly r from the edge, which is where the
    // bevel of distance r reaches to. One construction serves both, and this
    // is the assertion that keeps them from drifting apart.
    const anchor = edgeAnchor(EDGE, CONVEX)!;
    expect(Array.from(filletPreview(anchor, 0.4).tangencyLines)) //
      .toEqual(Array.from(chamferPreview(anchor, 0.4).offsets));
  });
});

describe("edgeGaugeTrack", () => {
  const anchor = edgeAnchor(EDGE, CONVEX)!;
  const track = edgeGaugeTrack(anchor, "mm");

  it("puts the arrow tip the value's distance out along the bisector", () => {
    close(track.pointAt(2), [0, 1 + 2 * ROOT_HALF, 1 + 2 * ROOT_HALF]);
  });

  it("clamps to the range the form can submit", () => {
    expect(track.clamp(-5)).toBe(MIN_EDGE_VALUE_MM);
    expect(track.clamp(1e9)).toBe(MAX_EDGE_VALUE_MM);
  });

  it("steps by the document unit's own increment", () => {
    // The same 0.5 mm grid an extrude drag uses — imported rather than
    // re-picked, so a fillet and an extrude cannot snap differently.
    expect(track.nudge(2, "ArrowUp", false)).toBeCloseTo(2.5, 9);
    expect(track.nudge(2, "ArrowDown", false)).toBeCloseTo(1.5, 9);
    // Coarse lands on the NEXT MULTIPLE OF ITS OWN GRID (5 mm here), not on
    // current + 5 — `steppedValue`'s rule, so a coarse press after a free drag
    // puts you back on a round number instead of carrying the fraction along.
    expect(track.nudge(2, "ArrowUp", true)).toBeCloseTo(5, 9);
    expect(track.nudge(2, "q", false)).toBeNull();
  });

  it("formats in the document unit", () => {
    expect(track.format(2.5)).toContain("2.5");
    expect(track.format(2.5, { unitSuffix: false })).toBe("2.5");
  });
});
