import { describe, expect, it } from "vitest";

import {
  bandRadius,
  buildEdgeBand,
  edgeOcclusionBias,
  resolveBandEdge,
  resolveBandIntersections,
  type BandIntersection,
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
  /** Every triangle is drawn — the single-body case. */
  const allDrawn = () => true;

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
        { band, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBe(3);
  });

  it("takes the NEAREST band hit — r3f orders the list by distance", () => {
    expect(
      resolveBandIntersections(
        [hit(band, 50, 2), hit(band, 90, 0)],
        { band, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBe(8);
  });

  it("REFUSES an edge behind drawn material", () => {
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        { band, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBeNull();
  });

  it("accepts an edge behind a HIDDEN body — hiding it is how you reach this", () => {
    // The regression this exists for. `Mesh.raycast` tests a switched-off
    // body's triangles like any other (single material, no per-group visible
    // check), so the nearest surface hit here is material nobody can see. Left
    // measured, it refuses every edge behind a hidden body — i.e. hiding a body
    // to get at the geometry behind it kills the pick over that whole region.
    const hidden = (faceIndex: number | null | undefined) => faceIndex !== 12;
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        { band, surface, surfaceOccludes: hidden },
        map,
        1,
      ),
    ).toBe(8);
  });

  it("still occludes when the surface has no B-rep partition at all", () => {
    // "No ordinal" is NOT "no material": an unpartitioned mesh is still solid,
    // so the occlusion test must keep applying. Only a hidden body is skipped.
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        { band, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBeNull();
  });

  it("accepts a silhouette edge, with no surface hit in the list", () => {
    expect(
      resolveBandIntersections(
        [hit(band, 70, 2)],
        { band, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBe(8);
  });

  it("resolves nothing before the band mounts — a null target matches no hit", () => {
    // The refs are null on the first render, and `intersection.object` is never
    // null, so an unmounted target must simply never match.
    expect(
      resolveBandIntersections(
        [hit(surface, 50, 12), hit(band, 70, 2)],
        { band: null, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBeNull();
  });

  it("treats a band hit with no faceIndex as no hit", () => {
    expect(
      resolveBandIntersections(
        [hit(band, 70)],
        { band, surface, surfaceOccludes: allDrawn },
        map,
        1,
      ),
    ).toBeNull();
  });
});
