/**
 * The sketch store's half of Project (SKETCH-PROJECT-EDGES): the tool arms on
 * P, a picked edge lands as a linked entity (undoable, saved like any edit),
 * Break link frees it, and the solver's sick statuses are adopted without
 * bumping the revision.
 */
import { beforeEach, describe, expect, it } from "vitest";

import type { OverlayEdge, Vec3 } from "../api/measure";
import { isProjected } from "./project";
import { PROJECT_SPLINE_HINT } from "./projectEdge";
import { useSketchStore } from "./store";
import { placesPoints, TOOL_SHORTCUTS } from "./tools";

const v = (x: number, y: number, z: number): Vec3 => ({ x, y, z });
const line = (a: Vec3, b: Vec3): OverlayEdge => ({
  kind: "line",
  start: a,
  end: b,
  polyline: [a, b],
  signature: {
    subshape_type: "edge",
    curve: "line",
    end_a: a,
    end_b: b,
    midpoint: v((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2),
    length_mm: Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z),
  },
});
const RIM = line(v(-60, -40, 35), v(60, -40, 35));
const ANCHOR = "00000000-0000-0000-0000-00000000a004";

const store = () => useSketchStore.getState();

beforeEach(() => {
  store().exit();
  store().begin();
  store().choosePlane("XY");
});

describe("the Project tool", () => {
  it("is P, and places no points of its own", () => {
    expect(TOOL_SHORTCUTS.p).toBe("project");
    expect(placesPoints("project")).toBe(false);
    store().setTool("project");
    store().placeAt({ x: 1, y: 1 });
    expect(store().entities).toHaveLength(0);
  });

  it("projects a picked edge as a linked entity, one undoable edit", () => {
    store().setTool("project");
    const before = store().revision;
    store().projectEdge(RIM, ANCHOR);
    const [entity] = store().entities;
    expect(entity).toMatchObject({
      id: "e1",
      kind: "line",
      start: { x: -60, y: -40 },
      end: { x: 60, y: -40 },
    });
    expect(isProjected(entity)).toBe(true);
    expect(
      entity !== undefined &&
        "projection" in entity &&
        entity.projection?.edge.feature_id,
    ).toBe(ANCHOR);
    expect(store().revision).toBe(before + 1);
    expect(store().nextIdIndex).toBe(2);
    store().undo();
    expect(store().entities).toHaveLength(0);
  });

  it("refuses the same edge twice, and a spline, in words", () => {
    store().projectEdge(RIM, ANCHOR);
    store().projectEdge(RIM, ANCHOR);
    expect(store().entities).toHaveLength(1);
    expect(store().hint).toMatch(/already projected/);
    store().projectEdge(
      {
        ...RIM,
        kind: "other",
        signature: { ...RIM.signature, curve: "other" },
      },
      ANCHOR,
    );
    expect(store().entities).toHaveLength(1);
    expect(store().hint).toBe(PROJECT_SPLINE_HINT);
  });

  it("Escape drops the tool back to Select", () => {
    store().setTool("project");
    store().escape();
    expect(store().tool).toBe("select");
  });
});

describe("Break link", () => {
  it("frees the selected projected entity where it lies", () => {
    store().projectEdge(RIM, ANCHOR);
    store().togglePick({ kind: "entity", id: "e1" });
    store().breakLink();
    const [entity] = store().entities;
    expect(isProjected(entity)).toBe(false);
    expect(entity).toMatchObject({ start: { x: -60, y: -40 } });
    expect(store().editNote).toMatch(/Link broken on 1 entity/);
  });

  it("says why when nothing selected is projected", () => {
    store().breakLink();
    expect(store().hint).toMatch(/Select projected geometry/);
  });
});

describe("adoptSolved carries the projection statuses", () => {
  it("adopts sick statuses without an edit", () => {
    store().projectEdge(RIM, ANCHOR);
    const revision = store().revision;
    store().adoptSolved(
      null,
      { status: "converged", dof: 0, conflicting: [], redundant: [] },
      [],
      [],
      [{ entity: "e1", state: "sick", reason: "unresolved" }],
    );
    expect(store().projections).toEqual([
      { entity: "e1", state: "sick", reason: "unresolved" },
    ]);
    expect(store().revision).toBe(revision);
  });

  it("keeps the last statuses when an error path omits them", () => {
    store().adoptSolved(null, null, [], [], [{ entity: "e1", state: "ok" }]);
    store().adoptSolved(null, null);
    expect(store().projections).toHaveLength(1);
  });

  it("a new session starts with none", () => {
    store().adoptSolved(null, null, [], [], [{ entity: "e1", state: "ok" }]);
    store().exit();
    expect(store().projections).toEqual([]);
  });
});
