/**
 * CRAFT-9b — the shell/datum gauge seats and their line-work previews.
 *
 * These cases exist because the two decisions in `faceAnchor.ts` are both the
 * kind that DRAW BEAUTIFULLY AND MEAN NOTHING when they are wrong. A uniform
 * scale of a rectangle looks exactly like a wall of constant thickness and is
 * not one; a collapsed offset draws a crisp bow-tie; a seat pointing the wrong
 * way along the normal is a perfectly good arrow measuring the outside air. A
 * browser cannot tell you which of those you have, so the arithmetic is asserted
 * here in numbers and the browser is left to answer the questions only it can
 * (is it reachable, does it follow the pointer).
 */
import { describe, expect, it } from "vitest";

import type { OverlayResult, Vec3 as ApiVec3 } from "../api/measure";
import type { PlanarFaceSignature } from "../api/parts";
import {
  chainLoops,
  datumAnchor,
  datumOutline,
  drawnAdvance,
  drawnLength,
  faceLoop,
  insetOutline,
  insetPolygon,
  shellAnchor,
  signedArea,
  type DatumGaugeSeed,
} from "./faceAnchor";
import type { Vec3 } from "@loft/design";

/** A planar face signature — OCCT frame, as the overlay publishes it. */
function face(
  normal: [number, number, number],
  centroid: [number, number, number],
  areaMm2: number,
  outerAreaMm2?: number,
): PlanarFaceSignature {
  return {
    subshape_type: "face",
    surface: "plane",
    normal: { x: normal[0], y: normal[1], z: normal[2] },
    centroid: { x: centroid[0], y: centroid[1], z: centroid[2] },
    area_mm2: areaMm2,
    ...(outerAreaMm2 === undefined ? {} : { outer_area_mm2: outerAreaMm2 }),
  };
}

function v(x: number, y: number, z: number): ApiVec3 {
  return { x, y, z };
}

/** An overlay carrying just the edges a loop test needs. */
function overlayOf(polylines: readonly (readonly ApiVec3[])[]): OverlayResult {
  return {
    vertices: [],
    faces: [],
    edges: polylines.map((polyline) => ({
      kind: "line" as const,
      start: polyline[0] as ApiVec3,
      end: polyline[polyline.length - 1] as ApiVec3,
      polyline: [...polyline],
      signature: {
        subshape_type: "edge" as const,
        curve: "line" as const,
        end_a: polyline[0] as ApiVec3,
        end_b: polyline[polyline.length - 1] as ApiVec3,
        midpoint: polyline[0] as ApiVec3,
        length_mm: 1,
      },
    })),
  };
}

const RECT: [number, number][] = [
  [-30, -15],
  [30, -15],
  [30, 15],
  [-30, 15],
];

describe("insetPolygon — the wall, not a scaled copy of the rim", () => {
  it("contracts a 60x30 rectangle by 5 into 50x20", () => {
    const inner = insetPolygon(RECT, 5);
    expect(inner).not.toBeNull();
    // THE WHOLE POINT. A uniform scale that preserved the 60x30 aspect would
    // give 55 x 27.5 here — plausible on screen, and a lie about a wall of
    // constant thickness. Every side must move by exactly the inset.
    expect(inner).toEqual([
      [-25, -10],
      [25, -10],
      [25, 10],
      [-25, 10],
    ]);
  });

  it("is winding-independent — a clockwise rim gives the same wall", () => {
    const cw = [...RECT].reverse() as [number, number][];
    expect(signedArea(RECT)).toBeGreaterThan(0);
    expect(signedArea(cw)).toBeLessThan(0);
    const fromCcw = insetPolygon(RECT, 4) ?? [];
    const fromCw = insetPolygon(cw, 4) ?? [];
    // Same set of corners, walked the other way round.
    const key = (pts: [number, number][]) =>
      pts
        .map(([x, y]) => `${x.toFixed(6)},${y.toFixed(6)}`)
        .sort()
        .join(" ");
    expect(fromCw).toHaveLength(4);
    expect(key(fromCw)).toBe(key(fromCcw));
  });

  it("refuses once the wall has eaten the face", () => {
    // Half the short side is 15, so 15 is the medial axis and 20 is past it.
    expect(insetPolygon(RECT, 14.9)).not.toBeNull();
    expect(insetPolygon(RECT, 20)).toBeNull();
    // AND THE CASE THE WINDING TEST WAVED THROUGH. At 40 both dimensions
    // invert (-20 x -50), the two sign flips cancel, and the bow-tie comes back
    // with a POSITIVE area of 1000 — closed, crisp and a lie about where the
    // material is. This is the fixture that made the check per-edge.
    const bowtie = insetPolygon(RECT, 40);
    expect(bowtie).toBeNull();
  });

  it("bevels a sliver corner instead of drawing a spike through the part", () => {
    // A 4-degree wedge: the true mitre runs to ~29x the inset.
    const wedge: [number, number][] = [
      [0, 0],
      [100, 0],
      [100, 7],
    ];
    const inner = insetPolygon(wedge, 1);
    expect(inner).not.toBeNull();
    const apex = (inner ?? [])[0] as [number, number];
    // Bounded by the mitre limit rather than by taste: past 4x the inset the
    // corner takes the plain edge-normal offset.
    expect(Math.hypot(apex[0], apex[1])).toBeLessThanOrEqual(4 * 1 + 1e-9);
  });

  it("refuses degenerate input rather than emitting NaN", () => {
    expect(insetPolygon(RECT, 0)).toBeNull();
    expect(insetPolygon(RECT, -3)).toBeNull();
    expect(insetPolygon([[0, 0] as [number, number]], 1)).toBeNull();
    expect(
      insetPolygon(
        [
          [0, 0],
          [0, 0],
          [1, 1],
        ],
        1,
      ),
    ).toBeNull();
  });
});

describe("chainLoops — a boundary or nothing", () => {
  const p = (x: number, z: number): Vec3 => [x, 0, z];

  it("joins scrambled, reversed segments into one closed loop", () => {
    const loops = chainLoops([
      [p(0, 0), p(10, 0)],
      [p(10, 10), p(10, 0)], // reversed
      [p(0, 10), p(0, 0)], // reversed
      [p(10, 10), p(0, 10)],
    ]);
    expect(loops).toHaveLength(1);
    // Stored OPEN — the closing edge is implicit, so the first point is not
    // repeated at the end.
    expect(loops[0]).toHaveLength(4);
  });

  it("drops an open chain rather than insetting a line that means nothing", () => {
    expect(
      chainLoops([
        [p(0, 0), p(10, 0)],
        [p(10, 0), p(10, 10)],
      ]),
    ).toHaveLength(0);
  });
});

describe("shellAnchor — the seat", () => {
  const top = face([0, 0, 1], [0, 0, 20], 2400, 2400);

  it("is null until a face is picked — nothing to stand on is not a guess", () => {
    expect(shellAnchor(null, [])).toBeNull();
  });

  it("stands on the LAST pick and runs INTO the material", () => {
    const other = face([0, 0, -1], [0, 0, 0], 2400);
    const anchor = shellAnchor(null, [other, top]);
    expect(anchor).not.toBeNull();
    const seat = (anchor as NonNullable<typeof anchor>).seat;
    // OCCT +Z is scene +Y; a thickness grows the other way, into the body.
    expect(seat.base.map((n) => Math.round(n))).toEqual([0, 20, 0]);
    expect(seat.dir.map((n) => Math.round(n))).toEqual([0, -1, 0]);
    // Area-equivalent radius, the reading `FacePatch` already gives a face.
    expect(seat.radius).toBeCloseTo(Math.sqrt(2400 / Math.PI), 6);
  });

  it("sizes itself from the OUTER area, so drilling holes does not shrink it", () => {
    const drilled = face([0, 0, 1], [0, 0, 20], 900, 2400);
    const anchor = shellAnchor(null, [drilled]);
    expect((anchor as NonNullable<typeof anchor>).seat.radius).toBeCloseTo(
      Math.sqrt(2400 / Math.PI),
      6,
    );
  });
});

describe("faceLoop — the rim, recovered geometrically", () => {
  // A 60 x 30 top face at z = 20 (OCCT), plus one edge of the side wall that
  // must NOT be swept in.
  const top = face([0, 0, 1], [0, 0, 20], 1800, 1800);
  const rim: ApiVec3[][] = [
    [v(-30, -15, 20), v(30, -15, 20)],
    [v(30, -15, 20), v(30, 15, 20)],
    [v(30, 15, 20), v(-30, 15, 20)],
    [v(-30, 15, 20), v(-30, -15, 20)],
  ];
  const wall: ApiVec3[] = [v(-30, -15, 20), v(-30, -15, 0)];

  it("keeps only the edges in the face's own plane", () => {
    const anchor = shellAnchor(overlayOf([...rim, wall]), [top]);
    const loop = (anchor as NonNullable<typeof anchor>).loop;
    expect(loop).toHaveLength(4);
    // Scene frame: OCCT (x, y, z) -> (x, z, -y), so every rim point sits at y=20.
    for (const point of loop) expect(point[1]).toBeCloseTo(20, 9);
  });

  it("takes the OUTER wire when a hole loop is coplanar with it", () => {
    const hole: ApiVec3[][] = [
      [v(-5, -5, 20), v(5, -5, 20)],
      [v(5, -5, 20), v(5, 5, 20)],
      [v(5, 5, 20), v(-5, 5, 20)],
      [v(-5, 5, 20), v(-5, -5, 20)],
    ];
    const loop = faceLoop(overlayOf([...hole, ...rim]), [0, 20, 0], [0, 1, 0]);
    // The rim, not the 10 mm bore — the outer wire encloses the most area.
    const spanX = Math.max(...loop.map((p) => p[0]));
    expect(spanX).toBeCloseTo(30, 9);
  });

  it("returns an empty rim rather than a guess when nothing closes", () => {
    const anchor = shellAnchor(overlayOf([rim[0] as ApiVec3[], wall]), [top]);
    expect((anchor as NonNullable<typeof anchor>).loop).toHaveLength(0);
  });
});

describe("insetOutline — the shell's route-(b) preview", () => {
  const top = face([0, 0, 1], [0, 0, 20], 1800, 1800);
  const rim: ApiVec3[][] = [
    [v(-30, -15, 20), v(30, -15, 20)],
    [v(30, -15, 20), v(30, 15, 20)],
    [v(30, 15, 20), v(-30, 15, 20)],
    [v(-30, 15, 20), v(-30, -15, 20)],
  ];

  it("draws a closed outline whose perimeter falls as the wall thickens", () => {
    const anchor = shellAnchor(overlayOf(rim), [top]);
    expect(anchor).not.toBeNull();
    const at = (t: number) =>
      drawnLength(insetOutline(anchor as NonNullable<typeof anchor>, t));
    // 60 x 30 rim: at 5 mm the cavity is 50 x 20, perimeter 140.
    expect(at(5)).toBeCloseTo(140, 6);
    expect(at(2)).toBeCloseTo(2 * (56 + 26), 6);
    // MONOTONE, which is the property the e2e stamp leans on.
    expect(at(8)).toBeLessThan(at(5));
    expect(at(5)).toBeLessThan(at(2));
  });

  it("stays IN the face's plane", () => {
    const anchor = shellAnchor(overlayOf(rim), [top]);
    const buffer = insetOutline(anchor as NonNullable<typeof anchor>, 4);
    expect(buffer.length).toBe(4 * 6);
    for (let i = 1; i < buffer.length; i += 3) {
      expect(buffer[i]).toBeCloseTo(20, 9); // scene Y == the face plane
    }
  });

  it("draws nothing at all once the wall has eaten the face", () => {
    const anchor = shellAnchor(overlayOf(rim), [top]);
    expect(insetOutline(anchor as NonNullable<typeof anchor>, 40).length).toBe(
      0,
    );
  });
});

describe("datumAnchor — a distance and a side", () => {
  const resolveNone = () => null;

  it("seats an origin-plane offset at world zero, along the scene normal", () => {
    const seed: DatumGaugeSeed = { plane: "origin", base: "XY", offsetMm: 30 };
    const anchor = datumAnchor(seed, resolveNone);
    expect(anchor).not.toBeNull();
    const { seat, sign } = anchor as NonNullable<typeof anchor>;
    expect(sign).toBe(1);
    expect(seat.base).toEqual([0, 0, 0]);
    // OCCT XY's +Z normal is the scene's +Y — the ground plane, seen Y-up.
    expect(seat.dir.map((n) => Math.round(n))).toEqual([0, 1, 0]);
  });

  it("puts the SIGN in the seat, so the gauge only ever drives a distance", () => {
    const anchor = datumAnchor(
      { plane: "origin", base: "XY", offsetMm: -30 },
      resolveNone,
    );
    const { seat, sign } = anchor as NonNullable<typeof anchor>;
    expect(sign).toBe(-1);
    expect(seat.dir.map((n) => Math.round(n))).toEqual([0, -1, 0]);
  });

  it("is null when the base datum cannot be resolved", () => {
    expect(
      datumAnchor(
        { plane: "datum", baseFeatureId: "abc", offsetMm: 10 },
        resolveNone,
      ),
    ).toBeNull();
    expect(
      datumAnchor({ plane: "datum", baseFeatureId: "", offsetMm: 10 }, () => ({
        u: [1, 0, 0],
        v: [0, 0, 1],
        normal: [0, 1, 0],
        origin: [0, 0, 0],
      })),
    ).toBeNull();
    expect(datumAnchor(null, resolveNone)).toBeNull();
  });

  it("seats an on-face datum on the face's own plane and scale", () => {
    const anchor = datumAnchor(
      {
        plane: "face",
        signature: face([0, 0, 1], [0, 0, 12], 400),
        offsetMm: 5,
      },
      resolveNone,
    );
    const { seat } = anchor as NonNullable<typeof anchor>;
    expect(seat.base.map((n) => Math.round(n))).toEqual([0, 12, 0]);
    expect(seat.radius).toBeCloseTo(Math.sqrt(400 / Math.PI), 6);
  });
});

describe("datumOutline — the datum's route-(b) preview", () => {
  const anchor = datumAnchor(
    { plane: "origin", base: "XY", offsetMm: 30 },
    () => null,
  );

  it("stands the sheet at the offset, measured from the drawn vertices", () => {
    const a = anchor as NonNullable<typeof anchor>;
    const at = (mm: number) =>
      drawnAdvance(datumOutline(a, mm), a.seat.base, a.seat.dir);
    expect(at(30)).toBeCloseTo(30, 9);
    expect(at(12)).toBeCloseTo(12, 9);
    // The perimeter is INVARIANT here, which is exactly why the shell's stamp
    // would be useless for this preview and the two are different functions.
    expect(drawnLength(datumOutline(a, 30))).toBeCloseTo(
      drawnLength(datumOutline(a, 12)),
      9,
    );
  });

  it("walks the seat's own direction, so a negative offset draws below", () => {
    const below = datumAnchor(
      { plane: "origin", base: "XY", offsetMm: -30 },
      () => null,
    ) as NonNullable<typeof anchor>;
    const buffer = datumOutline(below, -30);
    for (let i = 1; i < buffer.length; i += 3) {
      expect(buffer[i]).toBeCloseTo(-30, 9);
    }
  });

  it("draws four sides, closed", () => {
    const buffer = datumOutline(anchor as NonNullable<typeof anchor>, 30);
    expect(buffer.length).toBe(4 * 6);
    // Last segment's end == first segment's start: the square closes.
    expect(buffer[18 + 3]).toBeCloseTo(buffer[0] as number, 9);
    expect(buffer[18 + 5]).toBeCloseTo(buffer[2] as number, 9);
  });
});
