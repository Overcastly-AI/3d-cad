import { describe, expect, it } from "vitest";

import {
  intersectEntities,
  perpendicularFoot,
  resolveSnap,
  snapCandidates,
  tangentPoints,
  type SnapInput,
} from "./snap";
import type { SketchEntity } from "./tools";

const line = (
  id: string,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): SketchEntity => ({
  id,
  kind: "line",
  start: { x: x1, y: y1 },
  end: { x: x2, y: y2 },
  construction: false,
});

const circle = (
  id: string,
  cx: number,
  cy: number,
  radius: number,
): SketchEntity => ({
  id,
  kind: "circle",
  center: { x: cx, y: cy },
  radius,
  construction: false,
});

/** A CCW quarter arc, centre (0,0) radius 10, from +x to +y. */
const quarterArc: SketchEntity = {
  id: "arc",
  kind: "arc",
  center: { x: 0, y: 0 },
  start: { x: 10, y: 0 },
  end: { x: 0, y: 10 },
  construction: false,
};

const input = (over: Partial<SnapInput>): SnapInput => ({
  point: { x: 0, y: 0 },
  entities: [],
  from: null,
  toleranceMm: 1,
  gridStepMm: 1,
  suppressed: false,
  axisLock: false,
  entitySnap: true,
  ...over,
});

describe("snapCandidates — the point kinds", () => {
  const horizontal = line("a", 0, 0, 10, 0);

  it("offers a line's ends as endpoints", () => {
    const [best] = snapCandidates([horizontal], { x: 10.2, y: 0.1 }, null, 1);
    expect(best?.kind).toBe("endpoint");
    expect(best?.at).toEqual({ x: 10, y: 0 });
    expect(best?.entities).toEqual(["a"]);
  });

  it("offers a line's midpoint", () => {
    const [best] = snapCandidates([horizontal], { x: 5.1, y: 0.2 }, null, 1);
    expect(best?.kind).toBe("midpoint");
    expect(best?.at).toEqual({ x: 5, y: 0 });
  });

  it("offers a circle's centre — and it has no midpoint", () => {
    const found = snapCandidates(
      [circle("c", 4, 4, 3)],
      { x: 4.2, y: 4.2 },
      null,
      1,
    );
    expect(found.map((c) => c.kind)).toEqual(["center"]);
    expect(found[0]?.at).toEqual({ x: 4, y: 4 });
  });

  it("offers an arc's midpoint at half its SWEEP, not half its chord", () => {
    // Quarter arc r=10: the sweep midpoint is at 45deg, |p| = 10 — a chord
    // midpoint would sit at |p| ~ 7.07 and be off the curve entirely.
    const mid = snapCandidates(
      [quarterArc],
      { x: 7.07, y: 7.07 },
      null,
      0.5,
    ).find((c) => c.kind === "midpoint");
    expect(mid?.at.x).toBeCloseTo(7.0711, 3);
    expect(Math.hypot(mid?.at.x ?? 0, mid?.at.y ?? 0)).toBeCloseTo(10, 9);
  });

  it("ranks an endpoint over a NEARER midpoint (class priority is strict)", () => {
    // Cursor exactly on the midpoint of a 1 mm line: both ends are 0.5 away,
    // the midpoint is 0.0 away, and the endpoint still wins. Strict ranking is
    // what keeps the resolution from flickering as the cursor jitters.
    const short = line("s", 0, 0, 1, 0);
    const [best] = snapCandidates([short], { x: 0.5, y: 0 }, null, 1);
    expect(best?.kind).toBe("endpoint");
  });

  it("offers nothing beyond the tolerance", () => {
    expect(snapCandidates([horizontal], { x: 40, y: 40 }, null, 1)).toEqual([]);
  });
});

describe("intersectEntities", () => {
  it("crosses two segments where they actually meet", () => {
    expect(
      intersectEntities(line("a", 0, 0, 10, 0), line("b", 5, -5, 5, 5)),
    ).toEqual([{ x: 5, y: 0 }]);
  });

  it("does NOT cross segments whose infinite lines meet off both", () => {
    // The infinite lines meet at (5,0); neither segment reaches it.
    expect(
      intersectEntities(line("a", 0, 0, 2, 0), line("b", 5, 3, 5, 8)),
    ).toEqual([]);
  });

  it("returns nothing for parallel lines", () => {
    expect(
      intersectEntities(line("a", 0, 0, 10, 0), line("b", 0, 4, 10, 4)),
    ).toEqual([]);
  });

  it("crosses a line and a circle at both roots", () => {
    const hits = intersectEntities(
      line("a", -10, 0, 10, 0),
      circle("c", 0, 0, 5),
    );
    expect(hits).toHaveLength(2);
    expect(hits.map((p) => p.x).sort((m, n) => m - n)).toEqual([-5, 5]);
  });

  it("crosses two circles at both points", () => {
    // Unit-ish lens: centres 8 apart, both r=5 -> x=4, y=+-3.
    const hits = intersectEntities(circle("p", 0, 0, 5), circle("q", 8, 0, 5));
    expect(hits).toHaveLength(2);
    for (const hit of hits) {
      expect(hit.x).toBeCloseTo(4, 9);
      expect(Math.abs(hit.y)).toBeCloseTo(3, 9);
    }
  });

  it("keeps only the crossings inside an ARC's sweep", () => {
    // The full circle meets x=0 at (0,10) and (0,-10); the quarter arc from
    // +x to +y contains only (0,10).
    const hits = intersectEntities(quarterArc, line("v", 0, -20, 0, 20));
    expect(hits).toHaveLength(1);
    expect(hits[0]?.y).toBeCloseTo(10, 9);
  });

  it("returns nothing for concentric circles or a bare point", () => {
    expect(
      intersectEntities(circle("p", 0, 0, 5), circle("q", 0, 0, 7)),
    ).toEqual([]);
    const point: SketchEntity = {
      id: "p1",
      kind: "point",
      position: { x: 0, y: 0 },
      construction: false,
    };
    expect(intersectEntities(point, line("a", -1, 0, 1, 0))).toEqual([]);
  });

  it("crosses a SPLINE through its sampled ink", () => {
    const spline: SketchEntity = {
      id: "sp",
      kind: "spline",
      points: [
        { x: 0, y: 0 },
        { x: 5, y: 10 },
        { x: 10, y: 0 },
      ],
      construction: false,
    };
    const hits = intersectEntities(spline, line("v", 5, -5, 5, 20));
    expect(hits).toHaveLength(1);
    expect(hits[0]?.x).toBeCloseTo(5, 6);
    expect(hits[0]?.y).toBeCloseTo(10, 1);
  });
});

describe("snapCandidates — intersections, tangents, perpendiculars", () => {
  it("offers a crossing as an intersection naming BOTH entities", () => {
    const found = snapCandidates(
      [line("a", 0, 0, 10, 0), line("b", 5, -5, 5, 5)],
      { x: 5.1, y: 0.1 },
      null,
      0.4,
    );
    const hit = found.find((c) => c.kind === "intersection");
    expect(hit?.at).toEqual({ x: 5, y: 0 });
    expect(hit?.entities).toEqual(["a", "b"]);
  });

  it("needs an anchor for tangent and perpendicular", () => {
    const entities = [circle("c", 0, 0, 5), line("a", 0, -10, 0, 10)];
    // Aiming at the top of the circle with nothing pending: no tangent.
    const without = snapCandidates(entities, { x: 3, y: 4 }, null, 0.5);
    expect(without.some((c) => c.kind === "tangent")).toBe(false);
    // The same aim with an anchor 25 mm out on +x: the tangent point from
    // there is (1, 4.899) — outside 0.5 of (3,4) — so aim at IT instead.
    const from = { x: 25, y: 0 };
    const [tangentPoint] = tangentPoints(from, {
      center: { x: 0, y: 0 },
      radius: 5,
    });
    const withAnchor = snapCandidates(
      entities,
      { x: (tangentPoint?.x ?? 0) + 0.1, y: tangentPoint?.y ?? 0 },
      from,
      0.5,
    );
    expect(withAnchor.some((c) => c.kind === "tangent")).toBe(true);
  });

  it("drops the perpendicular foot onto the segment", () => {
    const found = snapCandidates(
      [line("a", 0, 0, 10, 0)],
      { x: 3.1, y: 0.1 },
      { x: 3, y: 7 },
      0.5,
    );
    const foot = found.find((c) => c.kind === "perpendicular");
    expect(foot?.at).toEqual({ x: 3, y: 0 });
  });
});

describe("tangentPoints", () => {
  it("touches the circle at right angles to the anchor ray", () => {
    const circleForm = { center: { x: 0, y: 0 }, radius: 1 };
    const from = { x: 2, y: 0 };
    const points = tangentPoints(from, circleForm);
    expect(points).toHaveLength(2);
    for (const p of points) {
      expect(Math.hypot(p.x, p.y)).toBeCloseTo(1, 9);
      // (T - C) . (T - from) === 0 is the tangency condition.
      expect(p.x * (p.x - from.x) + p.y * (p.y - from.y)).toBeCloseTo(0, 9);
    }
  });

  it("has no tangent from inside the circle", () => {
    expect(
      tangentPoints({ x: 0.2, y: 0 }, { center: { x: 0, y: 0 }, radius: 1 }),
    ).toEqual([]);
  });
});

describe("perpendicularFoot", () => {
  it("returns null when the foot falls off the segment", () => {
    expect(
      perpendicularFoot(
        { x: -5, y: 3 },
        { a: { x: 0, y: 0 }, b: { x: 10, y: 0 } },
      ),
    ).toBeNull();
  });

  it("returns null for a degenerate segment", () => {
    expect(
      perpendicularFoot(
        { x: 1, y: 1 },
        { a: { x: 2, y: 2 }, b: { x: 2, y: 2 } },
      ),
    ).toBeNull();
  });
});

describe("resolveSnap — polarity and precedence", () => {
  const entities = [line("a", 0, 0, 10, 0)];

  it("takes the entity snap over the grid, and names it", () => {
    const result = resolveSnap(
      input({ point: { x: 9.7, y: 0.2 }, entities, toleranceMm: 1 }),
    );
    // The grid would have rounded to (10, 0) too — so use a point where the
    // two DISAGREE to prove which one ran.
    const offGrid = resolveSnap(
      input({
        point: { x: 5.4, y: 0.2 },
        entities: [line("a", 0, 0, 10.6, 0)],
        toleranceMm: 1,
      }),
    );
    expect(result.candidate?.kind).toBe("endpoint");
    expect(offGrid.candidate?.kind).toBe("midpoint");
    expect(offGrid.at).toEqual({ x: 5.3, y: 0 });
  });

  it("SUPPRESSES every snap under Ctrl/Cmd — including the grid", () => {
    const raw = { x: 9.73, y: 0.21 };
    const result = resolveSnap(
      input({ point: raw, entities, toleranceMm: 1, suppressed: true }),
    );
    expect(result.at).toEqual(raw);
    expect(result.candidate).toBeNull();
  });

  it("falls back to the grid, with no mark to show for it", () => {
    const result = resolveSnap(
      input({ point: { x: 40.4, y: 19.6 }, entities, gridStepMm: 1 }),
    );
    expect(result.at).toEqual({ x: 40, y: 20 });
    expect(result.candidate).toBeNull();
  });

  it("leaves the point raw when the grid is off and nothing is near", () => {
    const raw = { x: 40.4, y: 19.6 };
    expect(
      resolveSnap(input({ point: raw, entities, gridStepMm: 0 })).at,
    ).toEqual(raw);
  });

  it("skips entity snapping for the pick-grain tools", () => {
    const result = resolveSnap(
      input({
        point: { x: 9.7, y: 0.2 },
        entities,
        entitySnap: false,
      }),
    );
    expect(result.candidate).toBeNull();
    expect(result.at).toEqual({ x: 10, y: 0 }); // the grid, not the endpoint
  });
});

describe("resolveSnap — Shift axis lock", () => {
  const from = { x: 2, y: 3 };

  it("locks to the axis the cursor travelled furthest along", () => {
    const horizontal = resolveSnap(
      input({ point: { x: 20.4, y: 5 }, from, axisLock: true }),
    );
    expect(horizontal.candidate?.kind).toBe("axis-h");
    expect(horizontal.at).toEqual({ x: 20, y: 3 });

    const vertical = resolveSnap(
      input({ point: { x: 4, y: 30.6 }, from, axisLock: true }),
    );
    expect(vertical.candidate?.kind).toBe("axis-v");
    expect(vertical.at).toEqual({ x: 2, y: 31 });
  });

  it("beats an entity snap — holding the lock means holding it", () => {
    const result = resolveSnap(
      input({
        point: { x: 9.9, y: 3.1 },
        entities: [line("a", 0, 0, 10, 0)],
        from,
        axisLock: true,
        toleranceMm: 2,
      }),
    );
    expect(result.candidate?.kind).toBe("axis-h");
    expect(result.at).toEqual({ x: 10, y: 3 });
  });

  it("does nothing without an anchor to pivot on", () => {
    const result = resolveSnap(
      input({ point: { x: 4.4, y: 5.6 }, from: null, axisLock: true }),
    );
    expect(result.candidate).toBeNull();
    expect(result.at).toEqual({ x: 4, y: 6 });
  });

  it("is itself suppressed by Ctrl/Cmd", () => {
    const raw = { x: 20.4, y: 5.2 };
    const result = resolveSnap(
      input({ point: raw, from, axisLock: true, suppressed: true }),
    );
    expect(result.at).toEqual(raw);
  });
});
