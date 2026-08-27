import { describe, expect, it } from "vitest";

import {
  awayNormal,
  ghostFor,
  linearGhost,
  offsetAt,
  offsetPlacementFromComposed,
  perpendicularFoot,
  textPlacementFromComposed,
  type PlaceTarget,
} from "./placement";

/** A 20 mm horizontal edge sitting BELOW its view centre (sheet space is y-down). */
const A = { x: 0, y: 10 };
const B = { x: 20, y: 10 };
const ANCHOR = { x: 10, y: 0 };

/** Compare a normal component-wise (signed zero is not a difference here). */
const expectNormal = (
  got: { x: number; y: number } | null,
  want: { x: number; y: number },
) => {
  expect(got?.x).toBeCloseTo(want.x, 9);
  expect(got?.y).toBeCloseTo(want.y, 9);
};

describe("awayNormal", () => {
  it("points away from the view centre", () => {
    // The edge is below the anchor, so 'away' is further down the paper.
    expectNormal(awayNormal(A, B, ANCHOR), { x: 0, y: 1 });
  });

  it("flips with the geometry, not with the edge's direction", () => {
    const above = { a: { x: 0, y: -10 }, b: { x: 20, y: -10 } };
    expectNormal(awayNormal(above.a, above.b, ANCHOR), { x: 0, y: -1 });
    // Reversing the pick order must not change which side is 'away' — the
    // composer derives it from the geometry, and so must we.
    const forward = awayNormal(A, B, ANCHOR);
    expectNormal(awayNormal(B, A, ANCHOR), { x: forward!.x, y: forward!.y });
  });

  it("resolves the degenerate tie the way compose.py does", () => {
    // An edge whose midpoint sits exactly on the view centre: the dot product
    // is 0 and `_place_linear_between` keeps its `n0`, which maps to
    // (d.y, -d.x) on this side of the y-flip. Taking the NAIVE perpendicular
    // (-d.y, d.x) here would put the client on the opposite side of the paper
    // from the server for this one case.
    expectNormal(awayNormal({ x: -5, y: 0 }, { x: 5, y: 0 }, { x: 0, y: 0 }), {
      x: 0,
      y: -1,
    });
  });

  it("is null for a zero-length span", () => {
    expect(awayNormal(A, A, ANCHOR)).toBeNull();
  });
});

describe("offsetAt", () => {
  it("is positive on the away side and negative on the near side", () => {
    expect(offsetAt(A, B, ANCHOR, { x: 10, y: 25 })).toBeCloseTo(15, 9);
    expect(offsetAt(A, B, ANCHOR, { x: 10, y: 4 })).toBeCloseTo(-6, 9);
  });

  it("ignores movement ALONG the edge — only the perpendicular counts", () => {
    expect(offsetAt(A, B, ANCHOR, { x: 200, y: 25 })).toBeCloseTo(15, 9);
  });
});

describe("linearGhost", () => {
  it("draws the dimension line through the point the pointer chose", () => {
    // The round trip that keeps drag and composition agreeing: whatever the
    // pointer says, the line lands on its perpendicular projection.
    for (const pointer of [
      { x: 3, y: 31 },
      { x: 44, y: -6 },
      { x: 10, y: 10.5 },
    ]) {
      const offset = offsetAt(A, B, ANCHOR, pointer);
      const ghost = linearGhost(A, B, ANCHOR, offset);
      const dim = ghost?.lines.find((l) => l.role === "dimension");
      expect(dim).toBeDefined();
      expect(dim?.y1).toBeCloseTo(pointer.y, 9);
      expect(dim?.y2).toBeCloseTo(pointer.y, 9);
    }
  });

  it("carries the placing rule — the one mark a placed dimension lacks", () => {
    const ghost = linearGhost(A, B, ANCHOR, 12);
    const rule = ghost?.lines.find((l) => l.role === "rule");
    expect(rule).toMatchObject({ x1: 10, y1: 10, x2: 10, y2: 22 });
  });

  it("turns its arrowheads in, one per end", () => {
    const ghost = linearGhost(A, B, ANCHOR, 12);
    expect(ghost?.arrows).toHaveLength(2);
    // The barbs sit on the dimension line and point at each other.
    const tips = ghost?.arrows.map((arrow) => arrow.points[0]);
    expect(tips?.[0]).toEqual({ x: 0, y: 22 });
    expect(tips?.[1]).toEqual({ x: 20, y: 22 });
    expect(ghost?.arrows[0]?.points[1]?.x).toBeGreaterThan(0);
    expect(ghost?.arrows[1]?.points[1]?.x).toBeLessThan(20);
  });

  it("mirrors to the near side for a negative offset", () => {
    const ghost = linearGhost(A, B, ANCHOR, -12);
    const dim = ghost?.lines.find((l) => l.role === "dimension");
    expect(dim?.y1).toBeCloseTo(-2, 9);
  });

  it("is null for a degenerate span", () => {
    expect(linearGhost(A, A, ANCHOR, 12)).toBeNull();
  });

  it("carries its own READING, seated past the dimension line", () => {
    // Before this, the ghost's `<g>` held four `<line>`s and zero `<text>`, so
    // at the moment of placement the paper showed a line with no number and
    // the number was 372 px away at the foot of the window (P1-C).
    const ghost = linearGhost(A, B, ANCHOR, 12);
    expect(ghost?.figure?.text).toBe("12.00");
    // Centred on the rule (x = the span's midpoint) and standing off BEYOND
    // the dimension line, in the direction the placement is being pushed.
    expect(ghost?.figure?.at.x).toBeCloseTo(10, 9);
    expect(ghost?.figure?.at.y).toBeGreaterThan(22);

    // A negative offset takes the figure to the other side WITH the line.
    const near = linearGhost(A, B, ANCHOR, -12);
    expect(near?.figure?.text).toBe("-12.00");
    expect(near?.figure?.at.y).toBeLessThan(-2);
  });

  it("never prints a negative zero on the paper", () => {
    expect(linearGhost(A, B, ANCHOR, -0.001)?.figure?.text).toBe("0.00");
  });
});

describe("perpendicularFoot", () => {
  it("squares onto the second wall's supporting line", () => {
    const foot = perpendicularFoot(
      { x: 5, y: 0 },
      { x: 0, y: 8 },
      { x: 20, y: 8 },
    );
    expect(foot).toEqual({ x: 5, y: 8 });
  });

  it("is null when the wall is degenerate", () => {
    expect(perpendicularFoot(A, B, B)).toBeNull();
  });
});

describe("ghostFor", () => {
  it("draws a leader + crosshair for a text placement", () => {
    const target: PlaceTarget = {
      mode: "text",
      leaderFrom: { x: 40, y: 40 },
      textPos: { x: 60, y: 20 },
    };
    const ghost = ghostFor(target);
    expect(ghost?.target).toEqual({ x: 60, y: 20 });
    expect(ghost?.lines).toHaveLength(1);
    expect(ghost?.lines[0]?.role).toBe("leader");
    // …and NO figure: a text seat is a point, not a scalar, so a coordinate
    // pair floated beside the crosshair would decorate rather than read.
    expect(ghost?.figure).toBeNull();
  });
});

describe("reading a PLACED dimension back into a placement", () => {
  /** The composed annotation a linear dimension at `offsetMm` actually has —
   * built by the FORWARD construction, so the round trip is measured against
   * the same geometry the composer emits rather than against a hand-typed
   * fixture that could quietly encode the same mistake twice. */
  const composedLinesAt = (offsetMm: number) =>
    linearGhost(A, B, ANCHOR, offsetMm)!
      .lines.filter((l) => l.role === "extension" || l.role === "dimension")
      .map((l) => ({ role: l.role, x1: l.x1, y1: l.y1, x2: l.x2, y2: l.y2 }));

  it("recovers the span AND the signed offset, both signs", () => {
    for (const offset of [11, 25, -33, -11]) {
      const target = offsetPlacementFromComposed(
        composedLinesAt(offset),
        ANCHOR,
      );
      expect(target?.mode).toBe("offset");
      expect(target?.offsetMm).toBeCloseTo(offset, 6);
      // The recovered span IS the measured edge — that is what makes the
      // re-placement measure against the same thing the first one did.
      expect(target?.span.a.x).toBeCloseTo(A.x, 6);
      expect(target?.span.a.y).toBeCloseTo(A.y, 6);
      expect(target?.span.b.x).toBeCloseTo(B.x, 6);
      expect(target?.span.b.y).toBeCloseTo(B.y, 6);
    }
  });

  it("round-trips: recover, redraw, and the paper is unchanged", () => {
    // The property that actually matters — grabbing a dimension and dropping
    // it without moving must leave the drawing byte-identical.
    const before = linearGhost(A, B, ANCHOR, -17.5);
    const target = offsetPlacementFromComposed(composedLinesAt(-17.5), ANCHOR)!;
    const after = linearGhost(
      target.span.a,
      target.span.b,
      target.viewAnchor,
      target.offsetMm,
    );
    for (const [i, line] of after!.lines.entries()) {
      expect(line.x1).toBeCloseTo(before!.lines[i]!.x1, 6);
      expect(line.y1).toBeCloseTo(before!.lines[i]!.y1, 6);
      expect(line.x2).toBeCloseTo(before!.lines[i]!.x2, 6);
      expect(line.y2).toBeCloseTo(before!.lines[i]!.y2, 6);
    }
  });

  it("works for an AUTO-placed dimension, which has no stored offset at all", () => {
    // Most dimensions on a sheet were never hand-placed, so nothing is stored
    // to read back — and those are exactly the ones a user wants to nudge.
    // The geometry is on the paper either way, which is why the inversion
    // reads the composed annotation rather than the params.
    const target = offsetPlacementFromComposed(composedLinesAt(11), ANCHOR);
    expect(target?.offsetMm).toBeCloseTo(11, 6);
  });

  it("declines rather than inventing a placement it cannot derive", () => {
    const lines = composedLinesAt(20);
    expect(offsetPlacementFromComposed([], ANCHOR)).toBeNull();
    // One witness line is not two endpoints.
    expect(
      offsetPlacementFromComposed(lines.slice(0, 1).concat(lines[2]!), ANCHOR),
    ).toBeNull();
    // Witness lines with no dimension line between them.
    expect(offsetPlacementFromComposed(lines.slice(0, 2), ANCHOR)).toBeNull();
  });

  it("seats a text placement where the stamp already is", () => {
    const target = textPlacementFromComposed(
      [{ x1: 20, y1: 40, x2: 60, y2: 12 }],
      { x: 60, y: 12 },
    );
    expect(target.textPos).toEqual({ x: 60, y: 12 });
    expect(target.leaderFrom).toEqual({ x: 20, y: 40 });
    // An annotation drawn without a leader still yields a usable target.
    expect(textPlacementFromComposed([], { x: 5, y: 6 })).toEqual({
      mode: "text",
      leaderFrom: { x: 5, y: 6 },
      textPos: { x: 5, y: 6 },
    });
  });
});
