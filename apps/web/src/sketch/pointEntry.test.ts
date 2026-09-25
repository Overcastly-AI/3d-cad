import { describe, expect, it } from "vitest";

import {
  gridStepOptions,
  pointEntryOpening,
  withNamedPointAt,
} from "./pointEntry";
import type { SketchEntity } from "./tools";

const line: SketchEntity = {
  id: "e1",
  kind: "line",
  construction: false,
  start: { x: 2, y: 1 },
  end: { x: 12, y: 6 },
};

const base = {
  pending: [],
  cursor: { x: 5, y: 5 },
  selection: [],
  entities: [line],
  drawDimension: null,
  dimensionEdit: null,
};

describe("pointEntryOpening", () => {
  it("opens at the cursor for the first point of any placing tool", () => {
    for (const tool of ["line", "rect", "circle", "arc", "spline"] as const) {
      expect(pointEntryOpening({ ...base, tool })).toEqual({
        anchor: { x: 5, y: 5 },
        target: null,
      });
    }
  });

  it("opens for the next point of a line, arc or spline, never a rectangle's or circle's size", () => {
    const pending = [{ x: 1, y: 1 }];
    expect(
      pointEntryOpening({ ...base, tool: "line", pending }),
    ).not.toBeNull();
    expect(
      pointEntryOpening({ ...base, tool: "spline", pending }),
    ).not.toBeNull();
    expect(pointEntryOpening({ ...base, tool: "rect", pending })).toBeNull();
    expect(pointEntryOpening({ ...base, tool: "circle", pending })).toBeNull();
  });

  it("stands aside while the size cells or a dimension editor own the keyboard", () => {
    expect(
      pointEntryOpening({ ...base, tool: "line", drawDimension: {} }),
    ).toBeNull();
    expect(
      pointEntryOpening({ ...base, tool: "line", dimensionEdit: {} }),
    ).toBeNull();
  });

  it("with exactly one point selected, opens ON that point to move it", () => {
    expect(
      pointEntryOpening({
        ...base,
        tool: "select",
        selection: [{ kind: "point", entity: "e1", point: "end" }],
      }),
    ).toEqual({
      anchor: { x: 12, y: 6 },
      target: { entity: "e1", point: "end" },
    });
  });

  it("does not open for a curve pick, two picks, or the sketch frame", () => {
    const select = { ...base, tool: "select" as const };
    expect(
      pointEntryOpening({
        ...select,
        selection: [{ kind: "entity", id: "e1" }],
      }),
    ).toBeNull();
    expect(
      pointEntryOpening({
        ...select,
        selection: [
          { kind: "point", entity: "e1", point: "start" },
          { kind: "point", entity: "e1", point: "end" },
        ],
      }),
    ).toBeNull();
    expect(
      pointEntryOpening({
        ...select,
        selection: [{ kind: "point", entity: "origin", point: "position" }],
      }),
    ).toBeNull();
  });
});

describe("withNamedPointAt", () => {
  it("moves exactly the named point", () => {
    expect(withNamedPointAt(line, "end", { x: 20.5, y: 9.75 })).toEqual({
      ...line,
      end: { x: 20.5, y: 9.75 },
    });
    const spline: SketchEntity = {
      id: "s1",
      kind: "spline",
      construction: false,
      points: [
        { x: 0, y: 0 },
        { x: 1, y: 1 },
        { x: 2, y: 0 },
      ],
    };
    const moved = withNamedPointAt(spline, "fit1", { x: 1, y: 3 });
    expect(moved?.kind === "spline" ? moved.points : null).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 3 },
      { x: 2, y: 0 },
    ]);
  });

  it("refuses a point the entity does not have", () => {
    expect(withNamedPointAt(line, "center", { x: 0, y: 0 })).toBeNull();
  });
});

describe("gridStepOptions", () => {
  it("offers round steps in the document's unit, in mm underneath", () => {
    const mm = gridStepOptions("mm", 1);
    expect(mm.map((o) => o.label)).toEqual([
      "0.01 mm",
      "0.1 mm",
      "0.5 mm",
      "1 mm",
      "5 mm",
      "10 mm",
    ]);
    const inch = gridStepOptions("in", 25.4 / 16);
    expect(inch.find((o) => o.label === "0.0625 in")?.mm).toBeCloseTo(
      1.5875,
      9,
    );
  });

  it("always lists the step in use, even one no preset names", () => {
    const options = gridStepOptions("in", 1); // the 1 mm default in an inch file
    const current = options.find((o) => Math.abs(o.mm - 1) < 1e-9);
    // Three significant figures: the label names the step, and the value
    // underneath stays exact. "0.0393701 in" overflowed the DRO's GRID column.
    expect(current?.label).toBe("0.0394 in");
    expect(current?.mm).toBe(1);
  });

  it("keeps every label it can produce short enough for the GRID column", () => {
    // Every step the store can hold is a preset of SOME unit (the 1 mm
    // default is one), and any of them can be listed in any other unit.
    const units = ["mm", "cm", "m", "in", "ft"] as const;
    const held = units.flatMap((unit) =>
      gridStepOptions(unit, 1).map((option) => option.mm),
    );
    let longest = "";
    for (const unit of units) {
      for (const mm of held) {
        for (const option of gridStepOptions(unit, mm)) {
          if (option.label.length > longest.length) longest = option.label;
        }
      }
    }
    // SketchDro's DRO_COLUMNS sizes GRID for this label; keep them in step.
    expect(longest).toBe("0.0000328 ft");
  });
});
