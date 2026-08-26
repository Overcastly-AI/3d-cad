import { describe, expect, it } from "vitest";

import {
  AXIS_INFERENCE_MAX_DEG,
  inferredAxisConstraints,
  inferredCoincidents,
  intersectEntities,
  perpendicularFoot,
  resolveSnap,
  snapAnchorOf,
  snapCandidates,
  tangentPoints,
  type SnapAnchor,
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
  // OFF by default so every pre-existing case still measures the ENTITY snap
  // alone; the plane-frame cases below opt in explicitly, which also makes
  // their negative control (the same aim with `originSnap: null`) meaningful.
  originSnap: null,
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

describe("the plane's own frame — origin and axes (founder, 2026-08-02)", () => {
  const ORIGIN = { label: "Origin" };

  it("offers the origin of an EMPTY sketch — nothing drawn to hold onto", () => {
    // The whole defect in one case: with no entities, every other snap kind is
    // undefined, so before this the first point of a sketch could only ever
    // take the grid. The negative control is the same aim with the frame off.
    const aim = { x: 0.4, y: -0.3 };
    const withFrame = resolveSnap(
      input({ point: aim, gridStepMm: 0, originSnap: ORIGIN }),
    );
    expect(withFrame.candidate?.kind).toBe("origin");
    expect(withFrame.at).toEqual({ x: 0, y: 0 });

    const without = resolveSnap(input({ point: aim, gridStepMm: 0 }));
    expect(without.candidate).toBeNull();
    expect(without.at).toEqual(aim);
  });

  it("carries the plane's OWN word for zero, so a face centroid is never called the origin", () => {
    const result = resolveSnap(
      input({
        point: { x: 0.2, y: 0.2 },
        gridStepMm: 0,
        originSnap: { label: "Face centre" },
      }),
    );
    expect(result.candidate?.kind).toBe("origin");
    expect(result.candidate?.label).toBe("Face centre");
  });

  it("snaps ONTO an axis with the free coordinate still on the grid", () => {
    // Grid ON: `25.4 → 25` is the grid's doing, `y → 0` is the axis's. Both
    // have to happen, or "start on the X axis" gives you 24.87.
    const onX = resolveSnap(
      input({ point: { x: 25.4, y: 0.3 }, originSnap: ORIGIN }),
    );
    expect(onX.candidate?.kind).toBe("x-axis");
    expect(onX.at).toEqual({ x: 25, y: 0 });

    const onY = resolveSnap(
      input({ point: { x: -0.3, y: 12.4 }, originSnap: ORIGIN }),
    );
    expect(onY.candidate?.kind).toBe("y-axis");
    expect(onY.at).toEqual({ x: 0, y: 12 });
  });

  it("holds the axis exactly at zero with the grid OFF", () => {
    const result = resolveSnap(
      input({ point: { x: 25.37, y: 0.3 }, gridStepMm: 0, originSnap: ORIGIN }),
    );
    expect(result.candidate?.kind).toBe("x-axis");
    expect(result.at).toEqual({ x: 25.37, y: 0 });
  });

  it("lets a drawn point outrank the axis it happens to lie on", () => {
    // An axis is a whole LINE — the weakest claim about where you are aiming.
    // If it could outrank an endpoint, drawing along X would stop snapping to
    // the corners you already made, which is the silent-wrong-thing this
    // module exists to refuse.
    const result = resolveSnap(
      input({
        point: { x: 9.7, y: 0.2 },
        entities: [line("a", 0, 0, 9.7, 0.4)],
        toleranceMm: 1,
        gridStepMm: 0,
        originSnap: ORIGIN,
      }),
    );
    expect(result.candidate?.kind).toBe("endpoint");
    expect(result.at).toEqual({ x: 9.7, y: 0.4 });
  });

  it("yields to a corner drawn AT the origin — the ink is the finer claim", () => {
    // The constant real case: a rectangle started at zero. Both candidates are
    // the same point to the last bit, so the tie is decided on which is more
    // specific — the endpoint, which carries an entity id a constraint can
    // address, and which the user can actually see.
    const result = resolveSnap(
      input({
        point: { x: 0.3, y: 0.2 },
        entities: [line("a", 0, 0, 40, 0)],
        gridStepMm: 0,
        originSnap: ORIGIN,
      }),
    );
    expect(result.candidate?.kind).toBe("endpoint");
    expect(result.at).toEqual({ x: 0, y: 0 });
  });

  it("prefers the origin over the axes that cross it", () => {
    const result = resolveSnap(
      input({ point: { x: 0.2, y: 0.1 }, gridStepMm: 0, originSnap: ORIGIN }),
    );
    expect(result.candidate?.kind).toBe("origin");
  });

  it("is suppressed by Ctrl/Cmd like every other snap", () => {
    const raw = { x: 0.3, y: 0.2 };
    const result = resolveSnap(
      input({
        point: raw,
        suppressed: true,
        gridStepMm: 0,
        originSnap: ORIGIN,
      }),
    );
    expect(result.candidate).toBeNull();
    expect(result.at).toEqual(raw);
  });

  it("never reaches past the magnet — an aim 40 mm out stays where it is", () => {
    const result = resolveSnap(
      input({
        point: { x: 40, y: 40 },
        toleranceMm: 1,
        gridStepMm: 0,
        originSnap: ORIGIN,
      }),
    );
    expect(result.candidate).toBeNull();
    expect(result.at).toEqual({ x: 40, y: 40 });
  });
});

describe("a snap carries the ADDRESS it took, not just the coordinate (SNAP-3)", () => {
  const ORIGIN = { label: "Origin" };

  it("names the exact endpoint an endpoint snap took", () => {
    const result = resolveSnap(
      input({
        point: { x: 40.3, y: 0.2 },
        entities: [line("e1", 0, 0, 40.4, 0)],
        gridStepMm: 0,
      }),
    );
    expect(result.candidate?.kind).toBe("endpoint");
    expect(result.candidate?.ref).toEqual({ entity: "e1", point: "end" });
  });

  it("distinguishes the two ends of the SAME line", () => {
    const entities = [line("e1", 0, 0, 40, 0)];
    const near0 = resolveSnap(
      input({ point: { x: 0.2, y: 0.1 }, entities, gridStepMm: 0 }),
    );
    expect(near0.candidate?.ref).toEqual({ entity: "e1", point: "start" });
    const near40 = resolveSnap(
      input({ point: { x: 39.8, y: 0.1 }, entities, gridStepMm: 0 }),
    );
    expect(near40.candidate?.ref).toEqual({ entity: "e1", point: "end" });
  });

  it("names a circle's centre", () => {
    const result = resolveSnap(
      input({
        point: { x: 10.2, y: 4.9 },
        entities: [circle("e2", 10, 5, 8)],
        gridStepMm: 0,
      }),
    );
    expect(result.candidate?.kind).toBe("center");
    expect(result.candidate?.ref).toEqual({ entity: "e2", point: "center" });
  });

  it("names the plane's zero as the datum point (SNAP-2's whole case)", () => {
    const result = resolveSnap(
      input({ point: { x: 0.3, y: -0.2 }, gridStepMm: 0, originSnap: ORIGIN }),
    );
    expect(result.candidate?.kind).toBe("origin");
    expect(result.candidate?.ref).toEqual({
      entity: "origin",
      point: "position",
    });
  });

  it("gives a MIDPOINT no address — the schema has no midpoint relation", () => {
    const result = resolveSnap(
      input({
        point: { x: 20.1, y: 0.1 },
        entities: [line("e1", 0, 0, 40, 0)],
        gridStepMm: 0,
      }),
    );
    expect(result.candidate?.kind).toBe("midpoint");
    expect(result.candidate?.ref).toBeUndefined();
  });

  it("gives the AXES no address — point-on-object is not expressible", () => {
    // Deliberate, and the reason is in `SnapCandidate.ref`: `coincident` joins
    // two named points and `fixed` pins BOTH coordinates, so the only
    // authorable reading of "somewhere on the X axis" would also nail the
    // coordinate the user left free.
    const result = resolveSnap(
      input({ point: { x: 25.3, y: 0.2 }, gridStepMm: 0, originSnap: ORIGIN }),
    );
    expect(result.candidate?.kind).toBe("x-axis");
    expect(result.candidate?.ref).toBeUndefined();
  });

  it("gives intersection / tangent / perpendicular no address", () => {
    const crossing = resolveSnap(
      input({
        point: { x: 10.2, y: 0.1 },
        // BOTH midpoints are kept clear of the crossing at (10,0) — e1's is at
        // (15,0), e2's at (10,3). A midpoint outranks an intersection, so a
        // symmetric crosser would have measured the wrong kind entirely.
        entities: [line("e1", 0, 0, 30, 0), line("e2", 10, -3, 10, 9)],
        gridStepMm: 0,
        // Off the endpoints, so the intersection is the best candidate.
        toleranceMm: 0.5,
      }),
    );
    expect(crossing.candidate?.kind).toBe("intersection");
    expect(crossing.candidate?.ref).toBeUndefined();

    const foot = resolveSnap(
      input({
        point: { x: 5.1, y: 0.2 },
        entities: [line("e1", 0, 0, 20, 0)],
        from: { x: 5, y: 12 },
        gridStepMm: 0,
        toleranceMm: 0.5,
      }),
    );
    expect(foot.candidate?.kind).toBe("perpendicular");
    expect(foot.candidate?.ref).toBeUndefined();
  });

  it("snapAnchorOf banks an addressable snap and drops the rest", () => {
    const at = { x: 3, y: 4 };
    expect(
      snapAnchorOf(
        {
          kind: "endpoint",
          at,
          entities: ["e1"],
          ref: { entity: "e1", point: "end" },
        },
        at,
      ),
    ).toEqual({ at, ref: { entity: "e1", point: "end" } });
    expect(
      snapAnchorOf({ kind: "midpoint", at, entities: ["e1"] }, at),
    ).toBeNull();
    expect(snapAnchorOf(null, at)).toBeNull();
  });
});

describe("inferredCoincidents — one path, every tool (SNAP-3 / SNAP-2)", () => {
  const anchor = (
    x: number,
    y: number,
    entity: string,
    point: string,
  ): SnapAnchor => ({ at: { x, y }, ref: { entity, point } });

  it("binds the named point the click actually became", () => {
    // A line drawn FROM e1's end: the new line's `start` is what landed there.
    const emitted = [line("e2", 40, 0, 40, 30)];
    expect(inferredCoincidents([anchor(40, 0, "e1", "end")], emitted)).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "start" },
        b: { entity: "e1", point: "end" },
      },
    ]);
  });

  it("binds BOTH ends when a closing edge snaps at each end", () => {
    const emitted = [line("e3", 40, 30, 0, 0)];
    const out = inferredCoincidents(
      [anchor(40, 30, "e2", "end"), anchor(0, 0, "e1", "start")],
      emitted,
    );
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ a: { entity: "e3", point: "start" } });
    expect(out[1]).toMatchObject({ a: { entity: "e3", point: "end" } });
  });

  it("grounds a rectangle corner to the origin with ONE constraint, not two", () => {
    // THE over-constraint guard. A rectangle's corner is shared by two of its
    // four lines, so the obvious "bind every named point at this coordinate"
    // would state the same fact twice — and against the corner coincidences a
    // rectangle carries, that reports an ordinary sketch as over-constrained.
    const emitted = [
      line("e1", 0, 0, 40, 0),
      line("e2", 40, 0, 40, 25),
      line("e3", 40, 25, 0, 25),
      line("e4", 0, 25, 0, 0),
    ];
    const out = inferredCoincidents(
      [anchor(0, 0, "origin", "position")],
      emitted,
    );
    expect(out).toEqual([
      {
        kind: "coincident",
        a: { entity: "e1", point: "start" },
        b: { entity: "origin", point: "position" },
      },
    ]);
  });

  it("authors NOTHING for a circle's rim click — a rim is not a named point", () => {
    // The centre click banks an anchor and binds; the radius click banks one
    // too, and finds no named point of the circle at that coordinate.
    const emitted = [circle("e2", 10, 10, 20)];
    expect(
      inferredCoincidents(
        [anchor(10, 10, "e1", "end"), anchor(30, 10, "e1", "start")],
        emitted,
      ),
    ).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "center" },
        b: { entity: "e1", point: "end" },
      },
    ]);
  });

  it("authors nothing for an arc's PROJECTED end, and does for one on the circle", () => {
    // `arcEndPoint` projects the third click onto the arc's circle, so the
    // emitted `end` is generally not where the user clicked. No match, no
    // false claim — and where the target IS on the circle, the claim is true.
    const arc: SketchEntity = {
      id: "e2",
      kind: "arc",
      center: { x: 0, y: 0 },
      start: { x: 10, y: 0 },
      end: { x: 0, y: 10 },
      construction: false,
    };
    expect(
      inferredCoincidents([anchor(3, 14, "e1", "end")], [arc]),
    ).toHaveLength(0);
    expect(inferredCoincidents([anchor(0, 10, "e1", "end")], [arc])).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "end" },
        b: { entity: "e1", point: "end" },
      },
    ]);
  });

  it("addresses a spline's Nth fit point", () => {
    const spline: SketchEntity = {
      id: "e2",
      kind: "spline",
      points: [
        { x: 0, y: 0 },
        { x: 5, y: 8 },
        { x: 12, y: 3 },
      ],
      construction: false,
    };
    expect(
      inferredCoincidents([anchor(12, 3, "e1", "start")], [spline]),
    ).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "fit2" },
        b: { entity: "e1", point: "start" },
      },
    ]);
  });

  it("never restates a relation the sketch already carries", () => {
    const emitted = [line("e2", 40, 0, 40, 30)];
    const already = {
      kind: "coincident" as const,
      // Reversed operands — `sameConstraint` is unordered, and so is the guard.
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    };
    expect(
      inferredCoincidents([anchor(40, 0, "e1", "end")], emitted, [already]),
    ).toEqual([]);
  });

  it("authors nothing at all when no click was snapped", () => {
    expect(inferredCoincidents([], [line("e2", 1, 1, 9, 9)])).toEqual([]);
  });
});

describe("inferredAxisConstraints — line-by-line drawing states its axes (SNAP-5)", () => {
  /** The default sketcher: 1 mm grid, snap radius 1 mm, nothing suppressed. */
  const GRID = { gridStepMm: 1, toleranceMm: 1, suppressed: false };
  /** Grid off (G), so the placement is continuous and the radius governs. */
  const FREE = { gridStepMm: 0, toleranceMm: 1.5, suppressed: false };

  /** A line of `run` mm rising by `rise` mm — the shape of every case here. */
  const sloped = (run: number, rise: number): SketchEntity =>
    line("e1", 10, 10, 10 + run, 10 + rise);

  it("reads a horizontal line as horizontal, and a vertical one as vertical", () => {
    expect(inferredAxisConstraints([line("e1", 0, 0, 27, 0)], GRID)).toEqual([
      { kind: "horizontal", entity: "e1" },
    ]);
    expect(inferredAxisConstraints([line("e2", 27, 0, 27, 8)], GRID)).toEqual([
      { kind: "vertical", entity: "e2" },
    ]);
  });

  it("says nothing about a line drawn at an angle", () => {
    // 45 deg, and a shallow-but-deliberate 10 deg — neither is a near miss.
    expect(inferredAxisConstraints([sloped(30, 30)], GRID)).toEqual([]);
    expect(inferredAxisConstraints([sloped(30, 5.3)], GRID)).toEqual([]);
  });

  it("leaves ONE grid step of rise alone — that is a slope somebody chose", () => {
    // With the grid on, a placement lands on multiples of the step, so the
    // smallest rise anyone can draw IS one step. Treating it as a near miss
    // would rewrite geometry the user deliberately made (RECT-1 in reverse).
    expect(inferredAxisConstraints([sloped(60, 1)], GRID)).toEqual([]);
    // …however long the run, where a bare angular threshold would have caved:
    // atan(1/60) is 0.95 deg, well inside the ceiling.
    expect(Math.atan2(1, 60) * (180 / Math.PI)).toBeLessThan(
      AXIS_INFERENCE_MAX_DEG,
    );
  });

  it("catches the near miss the grid cannot express, once the grid is off", () => {
    // Grid off: the aim is continuous, so a hand-drawn "horizontal" lands a
    // fraction out. Inside the snap radius AND inside the ceiling -> inferred.
    expect(inferredAxisConstraints([sloped(60, 1)], FREE)).toEqual([
      { kind: "horizontal", entity: "e1" },
    ]);
    // Same deviation, a third of the run: 2.9 deg is still inside the ceiling.
    expect(inferredAxisConstraints([sloped(20, 1)], FREE)).toEqual([
      { kind: "horizontal", entity: "e1" },
    ]);
    // Same deviation again, over a run short enough to make it a real slope
    // (4.3 deg): the ceiling is what refuses this, not the radius.
    expect(inferredAxisConstraints([sloped(13, 1)], FREE)).toEqual([]);
  });

  it("refuses a stub, where millimetres say nothing about direction", () => {
    // 2 mm x 1.4 mm is 35 deg and it is INSIDE the snap radius on both axes —
    // a deviation rule alone would call it horizontal. The run has to clear
    // the same limit the rise stays under, and the ceiling backs it up.
    expect(inferredAxisConstraints([sloped(2, 1.4)], FREE)).toEqual([]);
    expect(inferredAxisConstraints([sloped(1, 1)], FREE)).toEqual([]);
  });

  it("never claims both axes for one line", () => {
    for (const [run, rise] of [
      [0, 0],
      [1, 1],
      [30, 0],
      [0, 30],
      [1.4, 1.4],
    ] as const) {
      expect(
        inferredAxisConstraints([sloped(run, rise)], FREE).length,
      ).toBeLessThan(2);
    }
  });

  it("stands down while the user suppresses snapping (Ctrl/Cmd)", () => {
    expect(
      inferredAxisConstraints([line("e1", 0, 0, 27, 0)], {
        ...GRID,
        suppressed: true,
      }),
    ).toEqual([]);
  });

  it("never restates an axis the sketch already carries", () => {
    // A rectangle's four edges pass through here too; `rectangleRigidity` has
    // already said this, and saying it twice reports an ordinary sketch as
    // OVER-CONSTRAINED.
    expect(
      inferredAxisConstraints([line("e1", 0, 0, 27, 0)], GRID, [
        { kind: "horizontal", entity: "e1" },
      ]),
    ).toEqual([]);
  });

  it("has nothing to say about a circle, an arc or a point", () => {
    expect(
      inferredAxisConstraints([circle("e1", 0, 0, 10), quarterArc], GRID),
    ).toEqual([]);
  });

  it("infers an axis for an exactly-drawn line even with no tolerance at all", () => {
    // The axis lock (Shift) and a grid landing are both bit-exact, so the
    // inference must not depend on the caller reporting a radius.
    expect(
      inferredAxisConstraints([line("e1", 0, 0, 27, 0)], {
        gridStepMm: 0,
        toleranceMm: 0,
        suppressed: false,
      }),
    ).toEqual([{ kind: "horizontal", entity: "e1" }]);
  });
});
