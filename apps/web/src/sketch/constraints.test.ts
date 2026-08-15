import { describe, expect, it } from "vitest";

import {
  applyConstraintAction,
  authoredConstraintCount,
  constraintEntityRefs,
  constraintGlyphs,
  describeSelection,
  dimensionEditorAnchor,
  dimensionVerbHint,
  formatDimensionMm,
  formatSolveCell,
  reconcileConstraints,
  resolveSketchKey,
  sameConstraint,
  selectionAllConstruction,
  solveDiagnostic,
  toggleConstruction,
  type SketchConstraint,
  type SolvedDimension,
} from "./constraints";
import { DATUM_X_AXIS_ID, datumEntities, datumFrame } from "./datum";
import type { SketchPick } from "./pick";
import type { SketchEntity } from "./tools";

const line: SketchEntity = {
  id: "e1",
  kind: "line",
  start: { x: 0, y: 0 },
  end: { x: 40, y: 0 },
  construction: false,
};
const line2: SketchEntity = {
  id: "e2",
  kind: "line",
  start: { x: 40, y: 0 },
  end: { x: 40, y: 25 },
  construction: false,
};
const circle: SketchEntity = {
  id: "e3",
  kind: "circle",
  center: { x: 100, y: 0 },
  radius: 10,
  construction: false,
};
const circle2: SketchEntity = {
  id: "e4",
  kind: "circle",
  center: { x: 200, y: 0 },
  radius: 5,
  construction: false,
};
const arc: SketchEntity = {
  id: "e5",
  kind: "arc",
  center: { x: 0, y: 100 },
  start: { x: 10, y: 100 },
  end: { x: 0, y: 110 },
  construction: false,
};
const entities = [line, line2, circle, circle2, arc];

const pickLine = (id: string): SketchPick => ({ kind: "entity", id });
const pickPoint = (
  entity: string,
  point: "start" | "end" | "center",
): SketchPick => ({
  kind: "point",
  entity,
  point,
});

describe("resolveSketchKey — one keyboard, two vocabularies", () => {
  it("letters arm tools while nothing is selected", () => {
    expect(resolveSketchKey("r", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("c", false)).toEqual({ type: "tool" });
    // J/K arm the modify tools (trim/extend) — also empty-selection tools.
    expect(resolveSketchKey("j", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("k", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("h", false)).toBeNull();
  });

  /**
   * FOUNDER 2026-08-14 ("cannot click dimension and have it assign one"): D
   * with an empty selection used to resolve to NOTHING — no tool owns `d` —
   * so the one advertised dimension key was a no-op at exactly the moment a
   * user reaches for it (just after drawing, when nothing is selected). It now
   * hands `distance` to the store, which arms the verb for the next click.
   */
  it("D dimensions even with nothing selected; R stays the Rectangle tool", () => {
    expect(resolveSketchKey("d", false)).toEqual({
      type: "constraint",
      action: "distance",
    });
    // A DRAWING key must never turn into a dimension key.
    expect(resolveSketchKey("r", false)).toEqual({ type: "tool" });
    // Nothing else changes: the other verbs are still selection-first.
    for (const key of ["h", "v", "x", "p", "t", "e", "o", "n"]) {
      expect(resolveSketchKey(key, false)).toBeNull();
    }
  });

  it("J/K are not constraint verbs when a selection exists", () => {
    expect(resolveSketchKey("j", true)).toBeNull();
    expect(resolveSketchKey("k", true)).toBeNull();
  });

  it("letters become constraint verbs once something is selected", () => {
    expect(resolveSketchKey("h", true)).toEqual({
      type: "constraint",
      action: "horizontal",
    });
    expect(resolveSketchKey("r", true)).toEqual({
      type: "constraint",
      action: "radius",
    });
    expect(resolveSketchKey("c", true)).toEqual({
      type: "constraint",
      action: "coincident",
    });
    expect(resolveSketchKey("p", true)).toEqual({
      type: "constraint",
      action: "parallel",
    });
    expect(resolveSketchKey("l", true)).toEqual({
      type: "constraint",
      action: "perpendicular",
    });
    expect(resolveSketchKey("t", true)).toEqual({
      type: "constraint",
      action: "tangent",
    });
    // The size/shape trio: E equal, S symmetric, O concentric.
    expect(resolveSketchKey("e", true)).toEqual({
      type: "constraint",
      action: "equal",
    });
    expect(resolveSketchKey("s", true)).toEqual({
      type: "constraint",
      action: "symmetric",
    });
    expect(resolveSketchKey("o", true)).toEqual({
      type: "constraint",
      action: "concentric",
    });
    // With an empty selection the letters arm draw tools: L is the line tool
    // and S is the spline tool (the same cross-vocabulary reuse — S is Spline
    // with nothing selected, Symmetric with a selection). P/T/E/O aren't tools.
    expect(resolveSketchKey("l", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("s", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("p", false)).toBeNull();
    expect(resolveSketchKey("t", false)).toBeNull();
    expect(resolveSketchKey("e", false)).toBeNull();
    expect(resolveSketchKey("o", false)).toBeNull();
  });

  it("N toggles construction only while something is selected", () => {
    expect(resolveSketchKey("n", true)).toEqual({ type: "construction" });
    expect(resolveSketchKey("N", true)).toEqual({ type: "construction" });
    expect(resolveSketchKey("n", false)).toBeNull(); // not a draw tool
  });
});

describe("construction geometry", () => {
  it("marks the selected entities construction; ignores point picks", () => {
    const next = toggleConstruction([pickLine("e1")], entities);
    expect(next).not.toBeNull();
    expect(next?.find((e) => e.id === "e1")?.construction).toBe(true);
    expect(next?.filter((e) => e.construction)).toHaveLength(1);
  });

  it("reverts the whole group when every selected entity is construction", () => {
    const marked = toggleConstruction(
      [pickLine("e1"), pickLine("e2")],
      entities,
    ) as SketchEntity[];
    const reverted = toggleConstruction(
      [pickLine("e1"), pickLine("e2")],
      marked,
    );
    expect(reverted?.some((e) => e.construction)).toBe(false);
  });

  it("returns null when the selection addresses no entity", () => {
    expect(toggleConstruction([], entities)).toBeNull();
    expect(toggleConstruction([pickPoint("e1", "start")], entities)).toBeNull();
  });

  it("selectionAllConstruction drives the toggle's pressed state", () => {
    const marked = toggleConstruction(
      [pickLine("e1")],
      entities,
    ) as SketchEntity[];
    expect(selectionAllConstruction([pickLine("e1")], marked)).toBe(true);
    expect(selectionAllConstruction([pickLine("e2")], marked)).toBe(false);
    expect(selectionAllConstruction([], marked)).toBe(false);
  });

  it("is not pressed for a selection the verb would refuse — the frame", () => {
    // A control that looks engaged and then declines. The axis is not in
    // `entities` until something grounds to it, so resolving the selected id
    // against them found nothing and `[].every(…)` answered true: the chip
    // rendered pressed and, pressed, hinted "Select an entity to toggle
    // construction." The pressed state and the verb now share one derivation.
    const onlyAxis = [pickLine(DATUM_X_AXIS_ID)];
    expect(toggleConstruction(onlyAxis, entities)).toBeNull();
    expect(selectionAllConstruction(onlyAxis, entities)).toBe(false);
    // …and still not pressed once the frame IS materialised (it is
    // construction, but the verb still refuses to flip it).
    const grounded = [...entities, ...datumEntities(datumFrame(80))];
    expect(toggleConstruction(onlyAxis, grounded)).toBeNull();
    expect(selectionAllConstruction(onlyAxis, grounded)).toBe(false);
  });
});

describe("applyConstraintAction", () => {
  it("horizontal/vertical apply to every selected line, skipping duplicates", () => {
    const result = applyConstraintAction(
      "horizontal",
      [pickLine("e1"), pickLine("e2"), pickLine("e3")], // e3 is a circle
      entities,
      [{ kind: "horizontal", entity: "e1" }],
    );
    expect(result).toEqual({
      outcome: "added",
      constraints: [{ kind: "horizontal", entity: "e2" }],
    });
  });

  it("hints (never silence) when the selection cannot take the verb", () => {
    expect(
      applyConstraintAction("horizontal", [pickLine("e3")], entities, []),
    ).toMatchObject({ outcome: "hint" });
    expect(applyConstraintAction("coincident", [], entities, [])).toMatchObject(
      { outcome: "hint" },
    );
  });

  it("distance opens the inline editor prefilled with the measured length", () => {
    expect(
      applyConstraintAction("distance", [pickLine("e1")], entities, []),
    ).toEqual({
      outcome: "editor",
      target: {
        kind: "distance",
        entity: "e1",
        initialMm: 40,
        initialExpression: null,
        initialName: null,
        initialDriving: true,
        constraintIndex: null,
      },
    });
  });

  it("distance re-opens an existing dimension for editing", () => {
    const existing: SketchConstraint[] = [
      { kind: "horizontal", entity: "e1" },
      {
        kind: "distance",
        entity: "e1",
        value_mm: 60,
        expression: "width/2",
        name: "half",
        driving: false,
      },
    ];
    expect(
      applyConstraintAction("distance", [pickLine("e1")], entities, existing),
    ).toEqual({
      outcome: "editor",
      target: {
        kind: "distance",
        entity: "e1",
        initialMm: 60,
        initialExpression: "width/2",
        initialName: "half",
        initialDriving: false,
        constraintIndex: 1,
      },
    });
  });

  it("radius targets exactly one circle or arc", () => {
    expect(
      applyConstraintAction("radius", [pickLine("e3")], entities, []),
    ).toEqual({
      outcome: "editor",
      target: {
        kind: "radius",
        entity: "e3",
        initialMm: 10,
        initialExpression: null,
        initialName: null,
        initialDriving: true,
        constraintIndex: null,
      },
    });
    expect(
      applyConstraintAction("radius", [pickLine("e1")], entities, []),
    ).toMatchObject({ outcome: "hint" });
  });

  it("fixed anchors each selected point", () => {
    expect(
      applyConstraintAction("fixed", [pickPoint("e1", "start")], entities, []),
    ).toEqual({
      outcome: "added",
      constraints: [{ kind: "fixed", point: { entity: "e1", point: "start" } }],
    });
  });

  it("coincident joins exactly two distinct points", () => {
    expect(
      applyConstraintAction(
        "coincident",
        [pickPoint("e1", "end"), pickPoint("e2", "start")],
        entities,
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [
        {
          kind: "coincident",
          a: { entity: "e1", point: "end" },
          b: { entity: "e2", point: "start" },
        },
      ],
    });
  });

  it("coincident routes a spline fit point through unchanged", () => {
    const spline: SketchEntity = {
      id: "e6",
      kind: "spline",
      points: [
        { x: 0, y: 0 },
        { x: 10, y: 20 },
        { x: 20, y: 0 },
      ],
      construction: false,
    };
    const fitPick: SketchPick = { kind: "point", entity: "e6", point: "fit0" };
    const result = applyConstraintAction(
      "coincident",
      [fitPick, pickPoint("e1", "end")],
      [...entities, spline],
      [],
    );
    expect(result).toEqual({
      outcome: "added",
      constraints: [
        {
          kind: "coincident",
          a: { entity: "e6", point: "fit0" },
          b: { entity: "e1", point: "end" },
        },
      ],
    });
    // The fit point is a normal EntityPointRef the entity-ref walk resolves.
    expect(
      result.outcome === "added"
        ? constraintEntityRefs(result.constraints[0] as SketchConstraint)
        : [],
    ).toEqual(["e6", "e1"]);
  });

  it("fixed anchors a spline fit point", () => {
    const fitPick: SketchPick = { kind: "point", entity: "e6", point: "fit2" };
    expect(applyConstraintAction("fixed", [fitPick], entities, [])).toEqual({
      outcome: "added",
      constraints: [{ kind: "fixed", point: { entity: "e6", point: "fit2" } }],
    });
  });

  it("refuses a duplicate coincident regardless of point order", () => {
    const existing: SketchConstraint[] = [
      {
        kind: "coincident",
        a: { entity: "e2", point: "start" },
        b: { entity: "e1", point: "end" },
      },
    ];
    expect(
      applyConstraintAction(
        "coincident",
        [pickPoint("e1", "end"), pickPoint("e2", "start")],
        entities,
        existing,
      ),
    ).toMatchObject({ outcome: "hint" });
  });

  it("parallel/perpendicular relate exactly two selected lines", () => {
    for (const action of ["parallel", "perpendicular"] as const) {
      expect(
        applyConstraintAction(
          action,
          [pickLine("e1"), pickLine("e2")],
          entities,
          [],
        ),
      ).toEqual({
        outcome: "added",
        constraints: [{ kind: action, a: "e1", b: "e2" }],
      });
      // One line, or a line + a circle: not two lines.
      expect(
        applyConstraintAction(action, [pickLine("e1")], entities, []),
      ).toMatchObject({ outcome: "hint" });
      expect(
        applyConstraintAction(
          action,
          [pickLine("e1"), pickLine("e3")],
          entities,
          [],
        ),
      ).toMatchObject({ outcome: "hint" });
    }
  });

  it("refuses a duplicate parallel regardless of entity order", () => {
    expect(
      applyConstraintAction(
        "parallel",
        [pickLine("e1"), pickLine("e2")],
        entities,
        [{ kind: "parallel", a: "e2", b: "e1" }],
      ),
    ).toMatchObject({ outcome: "hint" });
  });

  it("tangent needs a curve — a line + arc/circle or two curves, never two lines", () => {
    // line + circle: valid.
    expect(
      applyConstraintAction(
        "tangent",
        [pickLine("e1"), pickLine("e3")],
        entities,
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [{ kind: "tangent", a: "e1", b: "e3" }],
    });
    // two lines: rejected with a guiding hint.
    expect(
      applyConstraintAction(
        "tangent",
        [pickLine("e1"), pickLine("e2")],
        entities,
        [],
      ),
    ).toMatchObject({ outcome: "hint" });
    // one entity: rejected.
    expect(
      applyConstraintAction("tangent", [pickLine("e3")], entities, []),
    ).toMatchObject({ outcome: "hint" });
  });

  it("equal relates two lines or two rounds, never a mixed pair", () => {
    // two lines → equal length.
    expect(
      applyConstraintAction(
        "equal",
        [pickLine("e1"), pickLine("e2")],
        entities,
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [{ kind: "equal", a: "e1", b: "e2" }],
    });
    // two circles → equal radius.
    expect(
      applyConstraintAction(
        "equal",
        [pickLine("e3"), pickLine("e4")],
        entities,
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [{ kind: "equal", a: "e3", b: "e4" }],
    });
    // a circle + an arc → equal radius (both rounds).
    expect(
      applyConstraintAction(
        "equal",
        [pickLine("e3"), pickLine("e5")],
        entities,
        [],
      ),
    ).toMatchObject({ outcome: "added" });
    // a line + a circle: no equal-size relation → hint.
    expect(
      applyConstraintAction(
        "equal",
        [pickLine("e1"), pickLine("e3")],
        entities,
        [],
      ),
    ).toMatchObject({ outcome: "hint" });
    // one entity: rejected.
    expect(
      applyConstraintAction("equal", [pickLine("e1")], entities, []),
    ).toMatchObject({ outcome: "hint" });
  });

  it("refuses a duplicate equal regardless of entity order", () => {
    expect(
      applyConstraintAction(
        "equal",
        [pickLine("e1"), pickLine("e2")],
        entities,
        [{ kind: "equal", a: "e2", b: "e1" }],
      ),
    ).toMatchObject({ outcome: "hint" });
  });

  it("concentric relates exactly two circles/arcs, rejecting lines", () => {
    expect(
      applyConstraintAction(
        "concentric",
        [pickLine("e3"), pickLine("e5")],
        entities,
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [{ kind: "concentric", a: "e3", b: "e5" }],
    });
    // a line has no center → hint (only the two rounds would be picked).
    expect(
      applyConstraintAction(
        "concentric",
        [pickLine("e1"), pickLine("e3")],
        entities,
        [],
      ),
    ).toMatchObject({ outcome: "hint" });
    expect(
      applyConstraintAction("concentric", [pickLine("e3")], entities, []),
    ).toMatchObject({ outcome: "hint" });
  });

  it("symmetric ties two points about a selected line axis", () => {
    expect(
      applyConstraintAction(
        "symmetric",
        [pickPoint("e1", "start"), pickPoint("e2", "end"), pickLine("e2")],
        entities,
        [],
      ),
    ).toEqual({
      outcome: "added",
      constraints: [
        {
          kind: "symmetric",
          a: { entity: "e1", point: "start" },
          b: { entity: "e2", point: "end" },
          line: "e2",
        },
      ],
    });
    // two points, no axis line → hint about the axis.
    expect(
      applyConstraintAction(
        "symmetric",
        [pickPoint("e1", "start"), pickPoint("e2", "end")],
        entities,
        [],
      ),
    ).toMatchObject({ outcome: "hint" });
    // one point + a line → hint about the point count.
    expect(
      applyConstraintAction(
        "symmetric",
        [pickPoint("e1", "start"), pickLine("e2")],
        entities,
        [],
      ),
    ).toMatchObject({ outcome: "hint" });
  });

  it("refuses a duplicate symmetric regardless of point order", () => {
    expect(
      applyConstraintAction(
        "symmetric",
        [pickPoint("e1", "start"), pickPoint("e2", "end"), pickLine("e2")],
        entities,
        [
          {
            kind: "symmetric",
            a: { entity: "e2", point: "end" },
            b: { entity: "e1", point: "start" },
            line: "e2",
          },
        ],
      ),
    ).toMatchObject({ outcome: "hint" });
  });
});

describe("sameConstraint", () => {
  it("distance constraints match per entity (one driving value per line)", () => {
    expect(
      sameConstraint(
        { kind: "distance", entity: "e1", value_mm: 40 },
        { kind: "distance", entity: "e1", value_mm: 60 },
      ),
    ).toBe(true);
  });
});

describe("SKETCH-2 — the sketch frame as a constraint target", () => {
  const framed: SketchEntity[] = [line, ...datumEntities(datumFrame(80))];
  const originPick: SketchPick = {
    kind: "point",
    entity: "origin",
    point: "position",
  };
  const axisPick: SketchPick = { kind: "entity", id: "x-axis" };

  it("accepts the origin as a coincident target", () => {
    const result = applyConstraintAction(
      "coincident",
      [{ kind: "point", entity: "e1", point: "start" }, originPick],
      framed,
      [],
    );
    expect(result).toEqual({
      outcome: "added",
      constraints: [
        {
          kind: "coincident",
          a: { entity: "e1", point: "start" },
          b: { entity: "origin", point: "position" },
        },
      ],
    });
  });

  it("accepts an axis as a parallel/perpendicular partner", () => {
    const result = applyConstraintAction(
      "parallel",
      [{ kind: "entity", id: "e1" }, axisPick],
      framed,
      [],
    );
    expect(result).toMatchObject({ outcome: "added" });
  });

  it("refuses the verbs that would DRIVE the frame, naming the ones that work", () => {
    for (const verb of [
      "distance",
      "radius",
      "horizontal",
      "vertical",
      "fixed",
      "equal",
    ] as const) {
      const result = applyConstraintAction(verb, [axisPick], framed, []);
      expect(result.outcome).toBe("hint");
      expect(result).toMatchObject({ hint: /coincident, symmetric/ });
    }
  });

  it("carries no glyph for the frame's own pins", () => {
    const constraints: SketchConstraint[] = [
      { kind: "fixed", point: { entity: "e1", point: "start" } },
      { kind: "fixed", point: { entity: "origin", point: "position" } },
      { kind: "fixed", point: { entity: "x-axis", point: "start" } },
    ];
    expect(
      constraintGlyphs(constraints, framed, 3.5).map((g) => g.label),
    ).toEqual(["FIX"]);
    // …and the index space is untouched: a glyph still names its own
    // constraint, which is what Delete and the dimension editor address.
    expect(constraintGlyphs(constraints, framed, 3.5)[0]?.index).toBe(0);
  });

  it("counts only the constraints the user authored", () => {
    expect(
      authoredConstraintCount([
        { kind: "horizontal", entity: "e1" },
        { kind: "fixed", point: { entity: "origin", point: "position" } },
        { kind: "fixed", point: { entity: "e1", point: "start" } },
      ]),
    ).toBe(2);
  });

  it("never flips the frame out of construction geometry", () => {
    expect(toggleConstruction([axisPick], framed)).toBeNull();
  });
});

describe("constraintGlyphs — engineering notation", () => {
  const constraints: SketchConstraint[] = [
    { kind: "horizontal", entity: "e1" },
    { kind: "distance", entity: "e1", value_mm: 40 },
    { kind: "radius", entity: "e3", value_mm: 12.5 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
  ];

  it("labels are bare mono text: H, dims, R-dims, FIX, C", () => {
    const glyphs = constraintGlyphs(constraints, entities, 3.5);
    expect(glyphs.map((g) => g.label)).toEqual([
      "H",
      "40",
      "R12.5",
      "FIX",
      "C",
    ]);
    expect(glyphs.map((g) => g.editable)).toEqual([
      false,
      true,
      true,
      false,
      false,
    ]);
    expect(glyphs.map((g) => g.index)).toEqual([0, 1, 2, 3, 4]);
  });

  it("solved readouts drive the label: expression resolves, driven parenthesises", () => {
    const withDims: SketchConstraint[] = [
      { kind: "distance", entity: "e1", value_mm: 20, name: "width" },
      {
        kind: "distance",
        entity: "e2",
        value_mm: 20,
        expression: "width/2",
      },
      { kind: "radius", entity: "e3", value_mm: 12.5, driving: false },
    ];
    const solved = new Map<number, SolvedDimension>([
      [0, { constraint_index: 0, name: "width", driving: true, value_mm: 20 }],
      [
        1,
        {
          constraint_index: 1,
          name: null,
          driving: true,
          value_mm: 10,
          expression: "width/2",
        },
      ],
      [2, { constraint_index: 2, name: null, driving: false, value_mm: 12.5 }],
    ]);
    const glyphs = constraintGlyphs(withDims, entities, 3.5, solved);
    // Driving literal → "20"; driving expression → its resolved "10"; driven
    // radius → reference parentheses "(R12.5)".
    expect(glyphs.map((g) => g.label)).toEqual(["20", "10", "(R12.5)"]);
    expect(glyphs.map((g) => g.driven)).toEqual([false, false, true]);
    expect(glyphs[1]?.expression).toBe("width/2");
  });

  it("without a solved map, a driven flag alone parenthesises the label", () => {
    const glyphs = constraintGlyphs(
      [{ kind: "distance", entity: "e1", value_mm: 40, driving: false }],
      entities,
      3.5,
    );
    expect(glyphs[0]?.label).toBe("(40)");
    expect(glyphs[0]?.driven).toBe(true);
  });

  it("H and the dimension sit on opposite sides of the line", () => {
    const glyphs = constraintGlyphs(constraints, entities, 3.5);
    const h = glyphs[0]?.anchor;
    const dim = glyphs[1]?.anchor;
    // e1 runs +x from the origin: left-hand normal is +y.
    expect(h).toEqual({ x: 20, y: 3.5 });
    expect(dim).toEqual({ x: 20, y: -3.5 });
  });

  it("renders the relational marks (∥ / ⊥ / T) near their first entity", () => {
    const glyphs = constraintGlyphs(
      [
        { kind: "parallel", a: "e1", b: "e2" },
        { kind: "perpendicular", a: "e1", b: "e2" },
        { kind: "tangent", a: "e1", b: "e3" },
      ],
      entities,
      3.5,
    );
    expect(glyphs.map((g) => g.label)).toEqual(["∥", "⊥", "T"]);
    expect(glyphs.map((g) => g.kind)).toEqual([
      "parallel",
      "perpendicular",
      "tangent",
    ]);
    expect(glyphs.every((g) => !g.editable)).toBe(true);
    // Anchored on entity `a` (e1 midpoint normal), not at the origin.
    expect(glyphs[0]?.anchor).toEqual({ x: 20, y: 3.5 });
  });

  it("renders the size/shape marks (= / ⟷ / ◎) for equal/symmetric/concentric", () => {
    const glyphs = constraintGlyphs(
      [
        { kind: "equal", a: "e3", b: "e4" },
        { kind: "concentric", a: "e3", b: "e5" },
        {
          kind: "symmetric",
          a: { entity: "e1", point: "start" },
          b: { entity: "e1", point: "end" },
          line: "e2",
        },
      ],
      entities,
      3.5,
    );
    expect(glyphs.map((g) => g.label)).toEqual(["=", "◎", "⟷"]);
    expect(glyphs.map((g) => g.kind)).toEqual([
      "equal",
      "concentric",
      "symmetric",
    ]);
    expect(glyphs.every((g) => !g.editable)).toBe(true);
    // Symmetric sits at the mirrored pair's midpoint, nudged clear of the axis.
    // e1 runs (0,0)→(40,0): midpoint (20,0), + offset on both axes.
    expect(glyphs[2]?.anchor).toEqual({ x: 23.5, y: 3.5 });
  });

  it("skips a symmetric constraint whose points' entity is gone", () => {
    expect(
      constraintGlyphs(
        [
          {
            kind: "symmetric",
            a: { entity: "missing", point: "start" },
            b: { entity: "e1", point: "end" },
            line: "e2",
          },
        ],
        entities,
        3.5,
      ),
    ).toEqual([]);
  });

  it("skips a relational constraint whose first entity is gone", () => {
    expect(
      constraintGlyphs(
        [{ kind: "parallel", a: "missing", b: "e2" }],
        entities,
        3.5,
      ),
    ).toEqual([]);
  });

  it("skips constraints whose entity is gone (mid-edit safety)", () => {
    const glyphs = constraintGlyphs(
      [{ kind: "horizontal", entity: "missing" }],
      entities,
      3.5,
    );
    expect(glyphs).toEqual([]);
  });

  it("the new-dimension editor anchors where its glyph will land", () => {
    expect(
      dimensionEditorAnchor(
        {
          kind: "distance",
          entity: "e1",
          initialMm: 40,
          initialExpression: null,
          initialName: null,
          initialDriving: true,
          constraintIndex: null,
        },
        entities,
        3.5,
      ),
    ).toEqual({ x: 20, y: -3.5 });
  });
});

describe("formatDimensionMm", () => {
  it("trims trailing zeros, keeps drawing-style values", () => {
    expect(formatDimensionMm(40)).toBe("40");
    expect(formatDimensionMm(12.5)).toBe("12.5");
    expect(formatDimensionMm(0.25)).toBe("0.25");
  });
});

describe("solve feedback", () => {
  it("formats the DRO SOLVE cell per status", () => {
    expect(formatSolveCell(null, true)).toEqual({
      value: "SOLVING…",
      tone: "gauge",
    });
    expect(
      formatSolveCell(
        { status: "converged", dof: 0, conflicting: [], redundant: [] },
        false,
      ),
    ).toEqual({ value: "DOF 0 · CONVERGED", tone: "brass" });
    expect(
      formatSolveCell(
        { status: "underconstrained", dof: 3, conflicting: [], redundant: [] },
        false,
      ),
    ).toEqual({ value: "DOF 3 · UNDER-CONSTRAINED", tone: "mist" });
    expect(
      formatSolveCell(
        { status: "conflicting", dof: null, conflicting: [1], redundant: [] },
        false,
      ),
    ).toEqual({ value: "CONFLICT", tone: "flag" });
    expect(
      formatSolveCell(
        {
          status: "invalid",
          dof: null,
          conflicting: [],
          redundant: [],
          message: "unknown dimension 'w'",
        },
        false,
      ),
    ).toEqual({ value: "INVALID EXPRESSION", tone: "flag" });
  });

  it("diagnoses sick solves and stays quiet on healthy ones", () => {
    expect(
      solveDiagnostic({
        status: "underconstrained",
        dof: 3,
        conflicting: [],
        redundant: [],
      }),
    ).toBeNull();
    expect(
      solveDiagnostic({
        status: "conflicting",
        dof: null,
        conflicting: [0, 2],
        redundant: [],
      }),
    ).toMatchObject({ title: "Solve conflict" });
    expect(
      solveDiagnostic({
        status: "overconstrained",
        dof: 0,
        conflicting: [],
        redundant: [4],
      }),
    ).toMatchObject({ title: "Over-constrained" });
    // `invalid` surfaces the server's descriptive message verbatim.
    expect(
      solveDiagnostic({
        status: "invalid",
        dof: null,
        conflicting: [],
        redundant: [],
        message: "cycle: width → height → width",
      }),
    ).toEqual({
      title: "Dimension expression",
      body: "cycle: width → height → width",
    });
  });

  it("never claims a flag that is not in the sketch", () => {
    // "A redundant constraint is FLAGGED in the sketch. Remove it" with zero
    // flagged glyphs is a dead end with an ambiguous exit — the user is told to
    // remove something they cannot find. Both branches say what is true and
    // name a next move instead.
    const over = solveDiagnostic({
      status: "overconstrained",
      dof: 0,
      conflicting: [],
      redundant: [],
    });
    expect(over?.body).not.toContain("flagged");
    expect(over?.body).toContain("Remove the last one you added");

    // A conflict is never softened — the geometry on screen is wrong — so when
    // the only thing the solver could name is unreachable, point at the frame.
    const conflict = solveDiagnostic({
      status: "conflicting",
      dof: null,
      conflicting: [],
      redundant: [],
    });
    expect(conflict).toMatchObject({ title: "Solve conflict" });
    expect(conflict?.body).not.toContain("flagged");
    expect(conflict?.body).toContain("origin and axes");
  });

  it("describes the selection for the strip readout", () => {
    expect(describeSelection([])).toBe("nothing selected");
    expect(describeSelection([pickLine("e1"), pickPoint("e1", "start")])).toBe(
      "1 ent · 1 pt",
    );
  });
});

describe("constraint reconciliation after trim/extend", () => {
  it("lists every entity id a constraint binds to", () => {
    expect(constraintEntityRefs({ kind: "horizontal", entity: "e1" })).toEqual([
      "e1",
    ]);
    expect(
      constraintEntityRefs({
        kind: "fixed",
        point: { entity: "e2", point: "start" },
      }),
    ).toEqual(["e2"]);
    expect(
      constraintEntityRefs({ kind: "parallel", a: "e1", b: "e2" }),
    ).toEqual(["e1", "e2"]);
    expect(
      constraintEntityRefs({
        kind: "symmetric",
        a: { entity: "e1", point: "start" },
        b: { entity: "e2", point: "end" },
        line: "e6",
      }),
    ).toEqual(["e1", "e2", "e6"]);
  });

  it("keeps every constraint when nothing was deleted (a shortened trim)", () => {
    const before: SketchConstraint[] = [
      { kind: "horizontal", entity: "e1" },
      { kind: "distance", entity: "e1", value_mm: 40 },
    ];
    // A shortened/split trim keeps e1 (first piece keeps the target id).
    const result = reconcileConstraints(before, entities);
    expect(result.removed).toBe(0);
    expect(result.constraints).toEqual(before);
  });

  it("drops a constraint on a whole-curve-deleted target", () => {
    const before: SketchConstraint[] = [
      { kind: "horizontal", entity: "e1" },
      { kind: "radius", entity: "e3", value_mm: 10 },
    ];
    // e3 (the circle) is gone from the result → its radius dim is dangling.
    const after = entities.filter((e) => e.id !== "e3");
    const result = reconcileConstraints(before, after);
    expect(result.removed).toBe(1);
    expect(result.constraints).toEqual([{ kind: "horizontal", entity: "e1" }]);
  });

  it("drops a relational constraint when EITHER referenced entity vanished", () => {
    const before: SketchConstraint[] = [
      { kind: "parallel", a: "e1", b: "e2" },
      {
        kind: "coincident",
        a: { entity: "e1", point: "end" },
        b: { entity: "e2", point: "start" },
      },
    ];
    // e2 disappears (e.g. a split dropped the second, unidentified piece).
    const after = entities.filter((e) => e.id !== "e2");
    const result = reconcileConstraints(before, after);
    expect(result.removed).toBe(2);
    expect(result.constraints).toEqual([]);
  });

  it("binds a survivor to the first split piece (v1 rule): {target}.n gets no constraints", () => {
    // Split of e1 → first piece keeps "e1", second becomes "e1.2" (fresh id,
    // nothing referenced it before). The distance dim on e1 stays, bound to
    // the first piece; the new piece carries none.
    const before: SketchConstraint[] = [
      { kind: "distance", entity: "e1", value_mm: 40 },
    ];
    const after: SketchEntity[] = [
      { ...line }, // "e1", shortened first piece
      {
        id: "e1.2",
        kind: "line",
        start: { x: 30, y: 0 },
        end: { x: 40, y: 0 },
        construction: false,
      },
      line2,
    ];
    const result = reconcileConstraints(before, after);
    expect(result.removed).toBe(0);
    expect(result.constraints).toEqual(before);
  });
});

describe("dimensionVerbHint", () => {
  it("offers D on a single selected line", () => {
    expect(dimensionVerbHint([pickLine("e1")], entities, [])).toEqual({
      key: "D",
      label: "dimension",
    });
  });

  it("offers R on a single selected circle or arc", () => {
    expect(dimensionVerbHint([pickLine("e3")], entities, [])).toEqual({
      key: "R",
      label: "add a radius",
    });
    expect(dimensionVerbHint([pickLine("e5")], entities, [])).toEqual({
      key: "R",
      label: "add a radius",
    });
  });

  it("stays silent with no selection", () => {
    expect(dimensionVerbHint([], entities, [])).toBeNull();
  });

  it("stays silent when no single dimension verb applies", () => {
    // Two lines: distance/radius both need exactly one — no dimension hint.
    expect(
      dimensionVerbHint([pickLine("e1"), pickLine("e2")], entities, []),
    ).toBeNull();
    // A bare point is neither a line nor a round.
    expect(
      dimensionVerbHint([pickPoint("e1", "start")], entities, []),
    ).toBeNull();
  });
});
