/**
 * Helical-gear gap G7 — the constraints a trim or extend leaves behind must
 * not pull the edited curve back to its old shape.
 */
import { describe, expect, it } from "vitest";

import {
  deleteSelectedEntities,
  reconcileEditedConstraints,
  type SketchConstraint,
} from "./constraints";
import type { SketchEntity } from "./tools";

const line = (
  id: string,
  a: [number, number],
  b: [number, number],
): SketchEntity => ({
  id,
  kind: "line",
  construction: false,
  start: { x: a[0], y: a[1] },
  end: { x: b[0], y: b[1] },
});

const joint = (
  a: string,
  ap: "start" | "end",
  b: string,
  bp: "start" | "end",
): SketchConstraint => ({
  kind: "coincident",
  a: { entity: a, point: ap },
  b: { entity: b, point: bp },
});

describe("reconcileEditedConstraints", () => {
  it("drops the length dimension of a line a trim shortened (the keyway stub)", () => {
    const before = [
      line("e2", [6, 12], [6, 25.6]),
      line("e3", [6, 25.6], [-6, 25.6]),
    ];
    const after = [line("e2", [6, 19.08], [6, 25.6]), before[1]!];
    const constraints: SketchConstraint[] = [
      { kind: "vertical", entity: "e2" },
      { kind: "distance", entity: "e2", value_mm: 13.6 },
      joint("e2", "end", "e3", "start"),
    ];
    const result = reconcileEditedConstraints(constraints, before, after, "e2");
    expect(result.constraints.map((c) => c.kind)).toEqual([
      "vertical",
      "coincident",
    ]);
    expect(result.removed).toBe(1);
  });

  it("drops a constraint on the end the trim moved, keeps the one on the end it kept", () => {
    const before = [
      line("a", [0, 0], [40, 0]),
      line("b", [40, 0], [40, 10]),
      line("c", [-5, 0], [0, 0]),
    ];
    // Trimmed back to x = 20: `a`'s END moved, its START did not.
    const after = [line("a", [0, 0], [20, 0]), before[1]!, before[2]!];
    const constraints = [
      joint("a", "end", "b", "start"),
      joint("c", "end", "a", "start"),
    ];
    const result = reconcileEditedConstraints(constraints, before, after, "a");
    expect(result.constraints).toEqual([joint("c", "end", "a", "start")]);
    expect(result.removed).toBe(1);
  });

  it("re-homes a moved end's constraint onto the split piece that now owns that point", () => {
    // A 0..40 line cut out between 10 and 30: `a` keeps 0..10, `a.2` is 30..40
    // and owns the old END, where `b` was joined.
    const before = [line("a", [0, 0], [40, 0]), line("b", [40, 0], [40, 10])];
    const after = [
      line("a", [0, 0], [10, 0]),
      line("a.2", [30, 0], [40, 0]),
      before[1]!,
    ];
    const constraints = [
      joint("a", "end", "b", "start"),
      { kind: "horizontal", entity: "a" } as SketchConstraint,
    ];
    const result = reconcileEditedConstraints(constraints, before, after, "a");
    expect(result.constraints).toEqual([
      joint("a.2", "end", "b", "start"),
      { kind: "horizontal", entity: "a" },
    ]);
    expect(result.removed).toBe(0);
  });

  it("drops a midpoint relation on a line whose length changed", () => {
    const before = [
      line("bar", [0, 0], [40, 0]),
      line("stem", [20, 0], [20, 20]),
    ];
    const after = [line("bar", [0, 0], [20, 0]), before[1]!];
    const constraints: SketchConstraint[] = [
      {
        kind: "midpoint",
        point: { entity: "stem", point: "start" },
        line: "bar",
      },
      { kind: "vertical", entity: "stem" },
    ];
    const result = reconcileEditedConstraints(
      constraints,
      before,
      after,
      "bar",
    );
    expect(result.constraints.map((c) => c.kind)).toEqual(["vertical"]);
  });

  it("keeps an arc's radius and centre relations: a trimmed circle is still that circle", () => {
    const before: SketchEntity[] = [
      {
        id: "c1",
        kind: "circle",
        construction: false,
        center: { x: 0, y: 0 },
        radius: 20,
      },
    ];
    const after: SketchEntity[] = [
      {
        id: "c1",
        kind: "arc",
        construction: false,
        center: { x: 0, y: 0 },
        start: { x: -6, y: 19.08 },
        end: { x: 6, y: 19.08 },
      },
    ];
    const constraints: SketchConstraint[] = [
      { kind: "radius", entity: "c1", value_mm: 20 },
      { kind: "fixed", point: { entity: "c1", point: "center" } },
    ];
    const result = reconcileEditedConstraints(constraints, before, after, "c1");
    expect(result.constraints).toEqual(constraints);
    expect(result.removed).toBe(0);
  });

  it("still drops what names a vanished id (a line trimmed away whole)", () => {
    const before = [
      line("e1", [-6, 12], [6, 12]),
      line("e2", [6, 12], [6, 25.6]),
    ];
    const after = [before[1]!];
    const constraints = [joint("e1", "end", "e2", "start")];
    const result = reconcileEditedConstraints(constraints, before, after, "e1");
    expect(result.constraints).toEqual([]);
    expect(result.removed).toBe(1);
  });
});

describe("deleteSelectedEntities", () => {
  const entities = [line("e1", [0, 0], [10, 0]), line("e2", [10, 0], [10, 10])];
  const constraints: SketchConstraint[] = [
    joint("e1", "end", "e2", "start"),
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
  ];

  it("removes a picked curve and every constraint that named it", () => {
    const result = deleteSelectedEntities(
      [{ kind: "entity", id: "e1" }],
      entities,
      constraints,
    );
    expect(result?.entities.map((e) => e.id)).toEqual(["e2"]);
    expect(result?.constraints).toEqual([{ kind: "vertical", entity: "e2" }]);
    expect(result?.deleted).toBe(1);
    expect(result?.removedConstraints).toBe(2);
  });

  it("a point pick ON a curve deletes nothing; the sketch frame is never deleted", () => {
    expect(
      deleteSelectedEntities(
        [
          { kind: "point", entity: "e1", point: "end" },
          { kind: "entity", id: "x-axis" },
        ],
        [...entities, line("x-axis", [-50, 0], [50, 0])],
        constraints,
      ),
    ).toBeNull();
  });

  it("a picked standalone point entity is deleted", () => {
    const point: SketchEntity = {
      id: "p1",
      kind: "point",
      construction: false,
      position: { x: 3, y: 3 },
    };
    const result = deleteSelectedEntities(
      [{ kind: "point", entity: "p1", point: "position" }],
      [...entities, point],
      constraints,
    );
    expect(result?.entities.map((e) => e.id)).toEqual(["e1", "e2"]);
  });
});
