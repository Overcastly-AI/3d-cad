import { describe, expect, it } from "vitest";

import type { DimensionParams, EdgeSignature } from "../api/drawings";
import {
  IDLE,
  type EdgeTarget,
  armCentre,
  beginPlacement,
  buildDimension,
  commitParams,
  menuActions,
  movePlacement,
  pickCentre,
  pickEdge,
  pickHint,
  placementTarget,
  selectedCentres,
} from "./authoring";
import {
  type CentreTarget,
  centrePairTarget,
  centrePlacementFromComposed,
  centreSpan,
  clearedOffset,
  initialOrientation,
  orientationAt,
} from "./centres";
import { alongGhost, ghostFor } from "./placement";

const vec = (x: number, y: number, z: number) => ({ x, y, z });

/** A full circle of radius 4 at (cx, cy, 8): seam twice, antipode as midpoint. */
const rim = (cx: number, cy: number): EdgeSignature => ({
  curve: "circle",
  end_a: vec(cx + 4, cy, 8),
  end_b: vec(cx + 4, cy, 8),
  midpoint: vec(cx - 4, cy, 8),
  length_mm: 8 * Math.PI,
  subshape_type: "edge",
});
const leftEdge = (): EdgeSignature => ({
  curve: "line",
  end_a: vec(0, -30, 8),
  end_b: vec(0, 0, 8),
  midpoint: vec(0, -15, 8),
  length_mm: 30,
  subshape_type: "edge",
});

const VIEW_ANCHOR = { x: 100, y: 100 };

/** Hole A sits up-right of hole B on the sheet (sheet y is DOWN). */
const centreA = (): CentreTarget => ({
  projection: "top",
  viewId: "view-1",
  sourceEdge: rim(80, -10),
  clientX: 400,
  clientY: 200,
  at: { x: 120, y: 95 },
  viewAnchor: VIEW_ANCHOR,
});
const centreB = (): CentreTarget => ({
  projection: "top",
  viewId: "view-1",
  sourceEdge: rim(20, -20),
  clientX: 300,
  clientY: 220,
  at: { x: 90, y: 100 },
  viewAnchor: VIEW_ANCHOR,
});
const left = (): EdgeTarget => ({
  projection: "top",
  viewId: "view-1",
  sourceEdge: leftEdge(),
  primitive: "line",
  clientX: 250,
  clientY: 210,
  geometry: {
    line: { a: { x: 80, y: 107.5 }, b: { x: 80, y: 92.5 } },
    circle: null,
    viewAnchor: VIEW_ANCHOR,
  },
});

describe("hole-centre picks", () => {
  it("waits after one centre, then pairs with a second centre", () => {
    const one = pickCentre(IDLE, centreA());
    expect(one.kind).toBe("one-centre");
    expect(pickHint(one)).toMatch(/second centre, or an edge/);
    expect(menuActions(one)).toEqual([]);
    const two = pickCentre(one, centreB());
    expect(two.kind).toBe("centre-pair-ready");
    expect(menuActions(two)).toEqual(["centre_to_centre"]);
    expect(selectedCentres(two)).toHaveLength(2);
  });

  it("re-picking the same centre restarts rather than pairing it with itself", () => {
    const again = pickCentre(pickCentre(IDLE, centreA()), centreA());
    expect(again.kind).toBe("one-centre");
  });

  it("pairs an edge and a centre in either order", () => {
    // Edge first: its menu's "Distance to centre" arms the centre pick.
    const armed = armCentre(pickEdge(IDLE, left()));
    expect(armed.kind).toBe("arming-centre");
    expect(pickHint(armed)).toBe("Pick the hole centre");
    const edgeFirst = pickCentre(armed, centreA());
    const centreFirst = pickEdge(pickCentre(IDLE, centreA()), left());
    for (const state of [edgeFirst, centreFirst]) {
      expect(state.kind).toBe("edge-centre-ready");
      expect(menuActions(state)).toEqual(["edge_to_centre"]);
    }
  });

  it("builds the stored references: the edge and the hole RIM", () => {
    const state = pickCentre(armCentre(pickEdge(IDLE, left())), centreA());
    expect(buildDimension(state, "edge_to_centre")).toEqual({
      viewId: "view-1",
      params: {
        type: "linear",
        measurement: {
          mode: "edge_to_centre",
          edge: leftEdge(),
          centre: rim(80, -10),
        },
      },
    });
  });

  it("opens a centre pair along its larger separation", () => {
    const state = pickCentre(pickCentre(IDLE, centreA()), centreB());
    const built = buildDimension(state, "centre_to_centre");
    expect(built?.params).toMatchObject({
      measurement: { mode: "centre_to_centre", orientation: "horizontal" },
    });
  });
});

describe("Fusion's placement rule for centre to centre", () => {
  const pair = {
    p: { x: 120, y: 95 },
    q: { x: 90, y: 100 },
    orientation: "horizontal" as const,
  };

  it("above or below -> horizontal; left or right -> vertical", () => {
    expect(orientationAt(pair, { x: 100, y: 80 })).toBe("horizontal");
    expect(orientationAt(pair, { x: 100, y: 120 })).toBe("horizontal");
    expect(orientationAt(pair, { x: 60, y: 97 })).toBe("vertical");
    expect(orientationAt(pair, { x: 140, y: 97 })).toBe("vertical");
    // Diagonally outside, or inside the box: keep the current one.
    expect(orientationAt(pair, { x: 60, y: 60 })).toBe("horizontal");
    expect(
      orientationAt({ ...pair, orientation: "vertical" }, { x: 100, y: 97 }),
    ).toBe("vertical");
  });

  it("never offers a zero-length orientation", () => {
    const column = { p: { x: 10, y: 0 }, q: { x: 10, y: 50 } };
    expect(
      orientationAt({ ...column, orientation: "horizontal" }, { x: 10, y: -9 }),
    ).toBe("vertical");
    expect(initialOrientation({ x: 0, y: 0 }, { x: 3, y: 30 })).toBe(
      "vertical",
    );
  });

  it("spans are ordered like the composer's axis", () => {
    expect(centreSpan(pair)).toEqual({
      a: { x: 90, y: 97.5 },
      b: { x: 120, y: 97.5 },
    });
    // Vertical: bottom (larger sheet y) to top, on the mid x.
    expect(centreSpan({ ...pair, orientation: "vertical" })).toEqual({
      a: { x: 105, y: 100 },
      b: { x: 105, y: 95 },
    });
  });

  it("dragging re-aims the placement and the commit carries the orientation", () => {
    const state = pickCentre(pickCentre(IDLE, centreA()), centreB());
    const built = buildDimension(state, "centre_to_centre");
    const target = placementTarget(state, "centre_to_centre");
    expect(built).not.toBeNull();
    expect(target).not.toBeNull();
    const placing = beginPlacement(state, "view-1", built!.params, target!);
    // Drag to the RIGHT of both centres: it becomes a vertical dimension.
    const moved = movePlacement(placing, { x: 150, y: 97 });
    const commit = commitParams(moved);
    const params = commit?.params as DimensionParams;
    expect(params).toMatchObject({
      measurement: { mode: "centre_to_centre", orientation: "vertical" },
    });
    // 150 is 45 mm right of the centres' mid x (105), and right is the side
    // AWAY from the view anchor (100, 100), so the offset is +45.
    expect(params.placement?.offset_mm).toBe(45);
  });

  it("the horizontal ghost witnesses square from each centre", () => {
    const target = centrePairTarget(pair.p, pair.q, VIEW_ANCHOR);
    const ghost = ghostFor(target);
    expect(ghost).not.toBeNull();
    const witness = ghost!.lines.filter((l) => l.role === "extension");
    expect(witness).toHaveLength(2);
    for (const w of witness) expect(w.x1).toBeCloseTo(w.x2, 9);
    const dim = ghost!.lines.find((l) => l.role === "dimension")!;
    expect(dim.y1).toBeCloseTo(dim.y2, 9);
    expect(Math.abs(dim.x2 - dim.x1)).toBeCloseTo(30, 9);
    expect(alongGhost(pair, centreSpan(pair), VIEW_ANCHOR, 0)).not.toBeNull();
  });

  it("opens clear of the part, as the composer's auto placement does", () => {
    // A 60 x 40 plate drawn from (80, 80) to (140, 120); the centres sit inside
    // it, so the line must clear the plate's top edge (y = 80) by 11 mm.
    const box = { min: { x: 80, y: 80 }, max: { x: 140, y: 120 } };
    const target = centrePairTarget(pair.p, pair.q, { x: 110, y: 100 }, box);
    expect(target.offsetMm).toBeCloseTo(28.5, 9);
    expect(target.span.a.y - target.offsetMm).toBeCloseTo(80 - 11, 9);
    // Without the extents it clears the two centres only.
    expect(
      clearedOffset(
        target.span,
        [pair.p, pair.q],
        { x: 110, y: 100 },
        undefined,
      ),
    ).toBeCloseTo(-95 + 11 + 97.5, 9);
  });

  it("a placed vertical dimension reads back to the same placement", () => {
    const vertical = { ...pair, orientation: "vertical" as const };
    const span = centreSpan(vertical);
    const ghost = alongGhost(vertical, span, VIEW_ANCHOR, 20)!;
    const back = centrePlacementFromComposed(
      ghost.lines,
      VIEW_ANCHOR,
      "vertical",
      1.4,
    );
    expect(back?.offsetMm).toBeCloseTo(20, 9);
    expect(back?.centres?.p.x).toBeCloseTo(vertical.q.x, 9);
  });
});
