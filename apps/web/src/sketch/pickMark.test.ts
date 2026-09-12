/**
 * The select tool's cursor mark (SEL-2) — acceptance A3 in
 * `docs/design/pre-selection.md` §6: "Hovering a sketch line with no closer
 * point present shows the extended `SnapMarker` naming the entity kind before
 * the click; the click selects exactly the named candidate."
 *
 * Two halves, and the second is the one with teeth: naming a candidate is easy,
 * naming the one the click will ACTUALLY take is the property that makes the
 * mark worth trusting. `namesWhatTheClickTakes` asserts it against `applyPick`
 * itself rather than against a hand-written expectation, so the two cannot drift.
 */
import { describe, expect, it } from "vitest";

import {
  DATUM_ORIGIN_ID,
  DATUM_X_AXIS_ID,
  datumFrame,
  pickWithDatums,
} from "./datum";
import {
  applyPick,
  closestOnCurve,
  curveDistance,
  replacementPick,
  samePick,
  type SketchPick,
} from "./pick";
import { pickMark } from "./pickMark";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

const line: SketchEntity = {
  id: "e1",
  kind: "line",
  start: { x: 0, y: 0 },
  end: { x: 40, y: 0 },
  construction: false,
};
const circle: SketchEntity = {
  id: "e2",
  kind: "circle",
  center: { x: 100, y: 0 },
  radius: 10,
  construction: false,
};
const arc: SketchEntity = {
  id: "e3",
  kind: "arc",
  center: { x: 0, y: 100 },
  start: { x: 10, y: 100 },
  end: { x: 0, y: 110 },
  construction: false,
};
const spline: SketchEntity = {
  id: "e4",
  kind: "spline",
  points: [
    { x: -50, y: 0 },
    { x: -40, y: 10 },
    { x: -30, y: 0 },
  ],
  construction: false,
};

const FRAME = datumFrame(60);
const TOL = 1;

describe("closestOnCurve", () => {
  it("stands on the curve, at the distance the pick ranked it by", () => {
    for (const [entity, probe] of [
      [line, { x: 12, y: 3 }],
      [circle, { x: 100, y: 30 }],
      [arc, { x: 8, y: 108 }],
      [spline, { x: -40, y: 4 }],
    ] as const) {
      const on = closestOnCurve(probe, entity);
      expect(on, entity.kind).not.toBeNull();
      const at = on as Point2D;
      // The mark stands where the hit was measured — the one property that
      // keeps a mark from naming a curve while sitting beside it.
      expect(Math.hypot(at.x - probe.x, at.y - probe.y)).toBeCloseTo(
        curveDistance(probe, entity),
        9,
      );
    }
  });

  it("clamps to the near end past an arc's sweep, and to a segment's end", () => {
    // 270°, outside the CCW quarter start(0°) → end(90°): the near END wins.
    expect(closestOnCurve({ x: 0, y: 80 }, arc)).toEqual(arc.start);
    expect(closestOnCurve({ x: -10, y: 0 }, line)).toEqual(line.start);
  });

  it("answers a total function at a circle's dead centre", () => {
    expect(closestOnCurve(circle.center, circle)).toEqual({ x: 110, y: 0 });
    expect(curveDistance(circle.center, circle)).toBe(10);
  });

  it("has nothing on-curve for a bare point", () => {
    const point: SketchEntity = {
      id: "e5",
      kind: "point",
      position: { x: 5, y: 5 },
      construction: false,
    };
    expect(closestOnCurve({ x: 5, y: 5 }, point)).toBeNull();
    expect(curveDistance({ x: 5, y: 5 }, point)).toBe(Infinity);
  });
});

describe("pickMark", () => {
  it("names the entity's own kind, not a generic curve", () => {
    const kinds = [line, circle, arc, spline].map((entity) => {
      const at = closestOnCurve({ x: 0, y: 0 }, entity) as Point2D;
      return pickMark({ kind: "entity", id: entity.id }, [entity], at, FRAME)
        ?.label;
    });
    expect(kinds).toEqual(["Line", "Circle", "Arc", "Spline"]);
  });

  it("stands on the curve at the pick point, with the on-curve tick", () => {
    const mark = pickMark(
      { kind: "entity", id: "e1" },
      [line],
      { x: 12, y: 3 },
      FRAME,
    );
    expect(mark).toEqual({
      kind: "on-curve",
      label: "Line",
      at: { x: 12, y: 0 },
    });
  });

  it("reuses the drawing vocabulary for defining points", () => {
    const of = (entity: SketchEntity, point: string) =>
      pickMark(
        { kind: "point", entity: entity.id, point },
        [entity],
        { x: 0, y: 0 },
        FRAME,
      );
    expect(of(line, "start")).toMatchObject({
      kind: "endpoint",
      label: "Endpoint",
      at: { x: 0, y: 0 },
    });
    expect(of(circle, "center")).toMatchObject({
      kind: "center",
      label: "Centre",
      at: { x: 100, y: 0 },
    });
    // A fit point is an endpoint-CLASS vertex with its own honest word.
    expect(of(spline, "fit1")).toMatchObject({
      kind: "endpoint",
      label: "Fit point",
      at: { x: -40, y: 10 },
    });
  });

  it("calls the frame by its own names, on a sketch with nothing drawn", () => {
    // The datums are pickable before they are materialised into the buffer, so
    // an EMPTY sketch is exactly where this has to work.
    expect(
      pickMark(
        { kind: "point", entity: DATUM_ORIGIN_ID, point: "position" },
        [],
        { x: 0.4, y: -0.2 },
        FRAME,
      ),
    ).toEqual({ kind: "origin", label: "Origin", at: { x: 0, y: 0 } });
    expect(
      pickMark(
        { kind: "entity", id: DATUM_X_AXIS_ID },
        [],
        { x: 20, y: 0.3 },
        FRAME,
      ),
    ).toEqual({ kind: "x-axis", label: "X axis", at: { x: 20, y: 0 } });
  });

  it("says nothing about a pick whose entity is gone (a hover that outlived an undo)", () => {
    expect(
      pickMark({ kind: "entity", id: "e9" }, [line], { x: 0, y: 0 }, FRAME),
    ).toBeNull();
    expect(
      pickMark(
        { kind: "point", entity: "e9", point: "start" },
        [line],
        { x: 0, y: 0 },
        FRAME,
      ),
    ).toBeNull();
  });
});

describe("replacementPick — the mark names what the click takes", () => {
  const entities = [line, circle, arc, spline];
  /** Every distinct pick these entities offer, as candidate selections. */
  const selections: SketchPick[][] = [
    [],
    [{ kind: "entity", id: "e1" }],
    [{ kind: "point", entity: "e1", point: "start" }],
    [{ kind: "point", entity: "e1", point: "end" }],
    [{ kind: "entity", id: "e2" }],
    [
      { kind: "entity", id: "e1" },
      { kind: "entity", id: "e2" },
    ],
  ];
  const probes: Point2D[] = [
    { x: 0, y: 0 }, // the line's start: point AND curve stacked
    { x: 20, y: 0.2 }, // mid-line, nothing nearer
    { x: 40, y: 0 }, // the line's end
    { x: 110, y: 0 }, // on the circle
    { x: 100, y: 0 }, // the circle's centre
    { x: 500, y: 500 }, // empty steel
  ];

  it("agrees with applyPick for every selection over every probe", () => {
    let stacked = 0;
    for (const selection of selections) {
      for (const at of probes) {
        const candidates = pickWithDatums(
          entities,
          at,
          TOL,
          FRAME,
          "replace",
          selection,
        );
        if (candidates.length > 1) stacked += 1;
        const named = replacementPick(selection, candidates);
        const clicked = applyPick(selection, candidates, "replace");
        expect(
          named === null ? [] : [named],
          `${JSON.stringify(selection)} @ ${JSON.stringify(at)}`,
        ).toEqual(clicked);
      }
    }
    // A vacuous pass is the failure mode this whole family of checks has: prove
    // the sweep actually met stacked candidates, which is where naming the head
    // of the list and naming the taken pick come apart.
    expect(stacked).toBeGreaterThan(4);
  });

  it("names the NEXT candidate in the cycle, not the head of the list", () => {
    // The founder-visible case: one thing held, the cursor over a stack. The
    // click walks on — so the mark has to walk with it.
    const selection: SketchPick[] = [
      { kind: "point", entity: "e1", point: "start" },
    ];
    const candidates = pickWithDatums(
      entities,
      { x: 0, y: 0 },
      TOL,
      FRAME,
      "replace",
      selection,
    );
    expect(candidates.length).toBeGreaterThan(1);
    const named = replacementPick(selection, candidates) as SketchPick;
    expect(samePick(named, candidates[0] as SketchPick)).toBe(false);
    expect(samePick(named, candidates[1] as SketchPick)).toBe(true);
  });
});
