import { describe, expect, it } from "vitest";

import {
  bandRadius,
  buildEdgeBand,
  edgeOcclusionBias,
  resolveBandEdge,
  resolveBandIntersections,
  type BandIntersection,
  BAND_SCREEN_TIE_PX,
  EDGE_BAND_TOLERANCE_PX,
  EDGE_BAND_WIDTH_PX,
  EDGE_OCCLUSION_MIN_BIAS,
} from "./edgeBand";

const p = (x: number, y: number, z: number) => ({ x, y, z });

describe("buildEdgeBand", () => {
  it("emits one segment pair per polyline span, in scene space", () => {
    const band = buildEdgeBand([
      { index: 0, polyline: [p(0, 0, 0), p(1, 2, 3)] },
    ]);
    // occtToScene: (x, y, z) → (x, z, -y).
    expect(band.points).toEqual([
      [0, 0, 0],
      [1, 3, -2],
    ]);
    expect([...band.edgeOfSegment]).toEqual([0]);
  });

  it("maps every segment back to the EDGE that owns it, not to its position", () => {
    // A three-point polyline is two segments; the map has to say "edge 7" for
    // both, or a hit halfway along a tessellated arc picks the wrong bore.
    const band = buildEdgeBand([
      { index: 7, polyline: [p(0, 0, 0), p(1, 0, 0), p(2, 0, 0)] },
      { index: 2, polyline: [p(0, 1, 0), p(0, 2, 0)] },
    ]);
    expect([...band.edgeOfSegment]).toEqual([7, 7, 2]);
    expect(band.points).toHaveLength(6);
  });

  it("preserves the caller's SUBSET indices", () => {
    // InstanceMateOverlay bands only the circular edges, but reports the index
    // in the full overlay list — the number its pick handler is keyed on.
    const band = buildEdgeBand([
      { index: 4, polyline: [p(0, 0, 0), p(1, 0, 0)] },
      { index: 9, polyline: [p(0, 0, 0), p(0, 1, 0)] },
    ]);
    expect([...band.edgeOfSegment]).toEqual([4, 9]);
  });

  it("drops degenerate polylines rather than emitting empty segments", () => {
    const band = buildEdgeBand([
      { index: 0, polyline: [] },
      { index: 1, polyline: [p(0, 0, 0)] },
    ]);
    expect(band.points).toEqual([]);
    expect(band.edgeOfSegment).toHaveLength(0);
  });
});

describe("EDGE_BAND_WIDTH_PX", () => {
  it("is the full corridor, because LineSegments2 halves the material width", () => {
    expect(EDGE_BAND_WIDTH_PX).toBe(2 * EDGE_BAND_TOLERANCE_PX);
    // WCAG 2.5.8's 24 px target, spent along the entity instead of on a dot.
    expect(EDGE_BAND_WIDTH_PX).toBe(24);
  });
});

describe("bandRadius", () => {
  it("is half the diagonal of the band's extent", () => {
    const band = buildEdgeBand([
      { index: 0, polyline: [p(0, 0, 0), p(3, 4, 0)] },
    ]);
    // occtToScene of those two points spans 3 in x and 4 in z → diagonal 5.
    expect(bandRadius(band.points)).toBeCloseTo(2.5);
  });

  it("is zero for an empty band, which the bias floor then rescues", () => {
    expect(bandRadius([])).toBe(0);
    expect(edgeOcclusionBias(bandRadius([]))).toBe(EDGE_OCCLUSION_MIN_BIAS);
  });
});

describe("edgeOcclusionBias", () => {
  it("scales with the body, so one constant works at every part size", () => {
    expect(edgeOcclusionBias(20)).toBeCloseTo(1);
    expect(edgeOcclusionBias(2000)).toBeCloseTo(100);
  });

  it("floors at a positive value for a degenerate body", () => {
    expect(edgeOcclusionBias(0)).toBe(EDGE_OCCLUSION_MIN_BIAS);
    expect(edgeOcclusionBias(-5)).toBe(EDGE_OCCLUSION_MIN_BIAS);
    expect(edgeOcclusionBias(Number.NaN)).toBe(EDGE_OCCLUSION_MIN_BIAS);
  });
});

describe("resolveBandEdge", () => {
  const map = Uint32Array.from([3, 3, 8]);

  it("returns the owning edge when nothing occludes the hit", () => {
    expect(resolveBandEdge({ segment: 1, distance: 50 }, null, map, 1)).toBe(3);
  });

  it("accepts a SILHOUETTE edge — no surface behind it at all", () => {
    expect(resolveBandEdge({ segment: 2, distance: 90 }, null, map, 1)).toBe(8);
  });

  it("accepts a front edge whose surface sample is marginally nearer", () => {
    // The surface point under the cursor is up to 12 px away from the edge, so
    // on an angled face it sits slightly in front. Within the bias it wins.
    expect(resolveBandEdge({ segment: 0, distance: 50.4 }, 50, map, 1)).toBe(3);
  });

  it("REFUSES an edge behind the solid", () => {
    expect(
      resolveBandEdge({ segment: 2, distance: 70 }, 50, map, 1),
    ).toBeNull();
  });

  it("returns null with no hit", () => {
    expect(resolveBandEdge(null, 50, map, 1)).toBeNull();
  });

  it("refuses a segment ordinal outside the map rather than reading garbage", () => {
    expect(
      resolveBandEdge({ segment: 3, distance: 1 }, null, map, 1),
    ).toBeNull();
    expect(
      resolveBandEdge({ segment: -1, distance: 1 }, null, map, 1),
    ).toBeNull();
    expect(
      resolveBandEdge({ segment: 1.5, distance: 1 }, null, map, 1),
    ).toBeNull();
  });
});

describe("resolveBandIntersections", () => {
  const map = Uint32Array.from([3, 3, 8]);
  const band = { id: "band" };
  const surface = { id: "surface" };
  const targets = { band, surface };

  const hit = (
    object: object,
    distance: number,
    faceIndex?: number,
  ): BandIntersection => ({ object, distance, faceIndex });

  it("resolves the band hit and ignores objects that are neither target", () => {
    const grid = { id: "grid" };
    expect(
      resolveBandIntersections(
        [hit(grid, 10, 0), hit(band, 50, 1)],
        targets,
        map,
        1,
      ),
    ).toBe(3);
  });

  it("takes the NEAREST band hit — r3f orders the list by distance", () => {
    expect(
      resolveBandIntersections(
        [hit(band, 50, 2), hit(band, 90, 0)],
        targets,
        map,
        1,
      ),
    ).toBe(8);
  });

  it("REFUSES an edge behind drawn material", () => {
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        targets,
        map,
        1,
      ),
    ).toBeNull();
  });

  // "accepts an edge behind a HIDDEN body" USED TO LIVE HERE and now lives in
  // `pickRaycast.test.ts`. The decision moved a layer down: a hidden body's
  // triangle never reaches this intersection list, so there is no longer a
  // `surfaceOccludes` predicate here to state it against (SEL-6). The case
  // below is what remains — and it is now the guard that the new filter did
  // NOT become "drop everything unresolvable".

  it("still occludes when the surface has no B-rep partition at all", () => {
    // "No ordinal" is NOT "no material": an unpartitioned mesh is still solid,
    // so the occlusion test must keep applying. Only a hidden body is skipped,
    // and it is skipped before this list is built.
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        targets,
        map,
        1,
      ),
    ).toBeNull();
  });

  it("accepts a silhouette edge, with no surface hit in the list", () => {
    expect(resolveBandIntersections([hit(band, 70, 2)], targets, map, 1)).toBe(
      8,
    );
  });

  it("resolves nothing before the band mounts — a null target matches no hit", () => {
    // The refs are null on the first render, and `intersection.object` is never
    // null, so an unmounted target must simply never match.
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        { band: null, surface },
        map,
        1,
      ),
    ).toBeNull();
  });

  // EDGE-MARK-OVERLAP: a 2 mm wall's outer and inner rims both lie inside
  // the corridor, and the one nearer the camera is not the one under the
  // cursor.
  const gap = (distance: number, faceIndex: number, px: number) => ({
    ...hit(band, distance, faceIndex),
    screenGapPx: px,
  });
  const always = () => true;
  const never = () => false;

  it("takes the band hit nearest the CURSOR when it is proven visible", () => {
    expect(
      resolveBandIntersections(
        [gap(50, 0, 8), gap(52, 2, 0.5)],
        targets,
        map,
        1,
        always,
      ),
    ).toBe(8);
  });

  // The review finding: the body-scale bias admits an edge hidden behind a
  // wall thinner than the bias, so screen distance alone must not decide.
  it("keeps the edge in FRONT when the nearer-to-cursor one is not visible at its own pixel", () => {
    expect(
      resolveBandIntersections(
        [gap(130.1, 0, 8), hit(surface, 130.3, 4), gap(132.4, 2, 0.5)],
        targets,
        map,
        2.69,
        never,
      ),
    ).toBe(3);
  });

  it("keeps the edge in front when there is no visibility oracle to prove otherwise", () => {
    expect(
      resolveBandIntersections(
        [gap(50, 0, 8), gap(52, 2, 0.5)],
        targets,
        map,
        1,
      ),
    ).toBe(3);
  });

  // EDGE-HIDDEN-LONE: the only edge in the corridor, 2.31 mm behind the
  // face under the cursor, inside a 2.69 mm slack.
  it("refuses a LONE edge behind the surface under the cursor unless it is proven visible", () => {
    const lone = [hit(surface, 130, 4), gap(132.31, 2, 6)];
    expect(resolveBandIntersections(lone, targets, map, 2.69, never)).toBe(
      null,
    );
    expect(resolveBandIntersections(lone, targets, map, 2.69, always)).toBe(8);
  });

  it("falls through an unproven slack hit to the next edge that is visible", () => {
    expect(
      resolveBandIntersections(
        [hit(surface, 130, 4), gap(131, 2, 1), gap(132, 0, 3)],
        targets,
        map,
        2.69,
        (h) => h.faceIndex === 0,
      ),
    ).toBe(3);
  });

  it("asks nothing about a front hit that is in front of the surface", () => {
    const asked: number[] = [];
    expect(
      resolveBandIntersections(
        [gap(129.9, 2, 1), hit(surface, 130, 4)],
        targets,
        map,
        2.69,
        (h) => {
          asked.push(h.faceIndex as number);
          return false;
        },
      ),
    ).toBe(8);
    expect(asked).toEqual([]);
  });

  it("asks the oracle only about hits that would beat the front one", () => {
    const asked: number[] = [];
    resolveBandIntersections(
      [gap(50, 0, 1), gap(52, 2, 6)],
      targets,
      map,
      1,
      (h) => {
        asked.push(h.faceIndex as number);
        return true;
      },
    );
    expect(asked).toEqual([]);
  });

  it("breaks a screen tie by depth, so a seam behind its silhouette loses", () => {
    expect(
      resolveBandIntersections(
        [gap(50, 0, 2), gap(60, 2, 2 - BAND_SCREEN_TIE_PX / 2)],
        targets,
        map,
        1,
        always,
      ),
    ).toBe(3);
  });

  it("never hands the pick to a nearer-to-cursor edge behind material", () => {
    expect(
      resolveBandIntersections(
        [gap(50, 0, 9), hit(surface, 55, 4), gap(70, 2, 0)],
        targets,
        map,
        1,
        always,
      ),
    ).toBe(3);
  });

  it("treats a band hit with no faceIndex as no hit", () => {
    expect(
      resolveBandIntersections([hit(band, 70)], targets, map, 1),
    ).toBeNull();
  });
});
