import { describe, expect, it } from "vitest";

import {
  applyConstraintAction,
  constraintGlyphs,
  describeSelection,
  dimensionEditorAnchor,
  formatDimensionMm,
  formatSolveCell,
  parseConflictIndices,
  resolveSketchKey,
  sameConstraint,
  selectionAllConstruction,
  solveDiagnostic,
  toggleConstruction,
  type SketchConstraint,
} from "./constraints";
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
const entities = [line, line2, circle];

const pickLine = (id: string): SketchPick => ({ kind: "entity", id });
const pickPoint = (entity: string, point: "start" | "end"): SketchPick => ({
  kind: "point",
  entity,
  point,
});

describe("resolveSketchKey — one keyboard, two vocabularies", () => {
  it("letters arm tools while nothing is selected", () => {
    expect(resolveSketchKey("r", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("c", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("h", false)).toBeNull();
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
    // The relational letters still arm/return nothing with an empty selection
    // (P/T aren't tools; L is the line tool).
    expect(resolveSketchKey("l", false)).toEqual({ type: "tool" });
    expect(resolveSketchKey("p", false)).toBeNull();
    expect(resolveSketchKey("t", false)).toBeNull();
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
        constraintIndex: null,
      },
    });
  });

  it("distance re-opens an existing dimension for editing", () => {
    const existing: SketchConstraint[] = [
      { kind: "horizontal", entity: "e1" },
      { kind: "distance", entity: "e1", value_mm: 60 },
    ];
    expect(
      applyConstraintAction("distance", [pickLine("e1")], entities, existing),
    ).toEqual({
      outcome: "editor",
      target: {
        kind: "distance",
        entity: "e1",
        initialMm: 60,
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
  it("parses conflicting indices out of the geometry error message", () => {
    expect(
      parseConflictIndices(
        "Sketch constraints are mutually unsatisfiable (conflicting constraint indices: [0, 2]).",
      ),
    ).toEqual([0, 2]);
    expect(parseConflictIndices("no indices here")).toEqual([]);
  });

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
  });

  it("describes the selection for the strip readout", () => {
    expect(describeSelection([])).toBe("nothing selected");
    expect(describeSelection([pickLine("e1"), pickPoint("e1", "start")])).toBe(
      "1 ent · 1 pt",
    );
  });
});
