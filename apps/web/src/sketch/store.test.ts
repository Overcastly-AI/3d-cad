/**
 * Store-level tests for the selection/constraint state machine and the
 * revision bookkeeping the live save loop depends on (user edits bump
 * `revision`; adopting solved geometry must NOT).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useSketchStore } from "./store";
import type { SketchEntity } from "./tools";

const rectangleAt = (store = useSketchStore.getState()) => {
  store.begin();
  useSketchStore.getState().choosePlane("XY");
  useSketchStore.getState().setTool("rect");
  useSketchStore.getState().placeAt({ x: 0, y: 0 });
  useSketchStore.getState().placeAt({ x: 40, y: 25 });
  useSketchStore.getState().setTool("select");
};

beforeEach(() => {
  useSketchStore.getState().exit();
});

describe("selection", () => {
  it("selectAt toggles picks and clears on empty clicks", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line curve
    expect(store().selection).toEqual([{ kind: "entity", id: "e1" }]);
    store().selectAt({ x: 20, y: 0.5 }, 2); // same spot → deselect
    expect(store().selection).toEqual([]);
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().selectAt({ x: 500, y: 500 }, 2); // empty steel → clear
    expect(store().selection).toEqual([]);
  });

  it("corner clicks cycle through the stacked endpoints", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 40, y: 0 }, 1);
    store().selectAt({ x: 40, y: 0 }, 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "e1", point: "end" },
      { kind: "point", entity: "e2", point: "start" },
    ]);
  });

  it("switching tools clears selection and pending state", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().setTool("line");
    expect(store().selection).toEqual([]);
    expect(store().tool).toBe("line");
  });
});

describe("constraints", () => {
  it("applyConstraint adds and bumps revision; hints do not", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const before = store().revision;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("horizontal");
    expect(store().constraints).toEqual([{ kind: "horizontal", entity: "e1" }]);
    expect(store().revision).toBe(before + 1);
    expect(store().selection).toEqual([]); // applied verbs clear selection

    store().applyConstraint("coincident"); // nothing selected → hint
    expect(store().hint).toMatch(/two points/i);
    expect(store().revision).toBe(before + 1);
  });

  it("distance opens the editor; commit appends and closes", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    expect(store().dimensionEdit).toMatchObject({
      kind: "distance",
      entity: "e1",
      initialMm: 40,
      constraintIndex: null,
    });
    const revision = store().revision;
    store().commitDimension(60);
    expect(store().constraints).toEqual([
      { kind: "distance", entity: "e1", value_mm: 60 },
    ]);
    expect(store().dimensionEdit).toBeNull();
    expect(store().revision).toBe(revision + 1);
  });

  it("editDimension re-opens an existing dimension; commit replaces it", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    store().commitDimension(40);
    store().editDimension(0);
    expect(store().dimensionEdit).toMatchObject({
      initialMm: 40,
      constraintIndex: 0,
    });
    store().commitDimension(60);
    expect(store().constraints).toEqual([
      { kind: "distance", entity: "e1", value_mm: 60 },
    ]);
  });

  it("commitDimension refuses non-positive values", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    const revision = store().revision;
    store().commitDimension(0);
    expect(store().constraints).toEqual([]);
    expect(store().revision).toBe(revision);
    expect(store().dimensionEdit).not.toBeNull();
  });

  it("removeConstraint reindexes the selected glyph", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("horizontal");
    store().selectAt({ x: 40, y: 12 }, 2); // right line
    store().applyConstraint("vertical");
    store().selectConstraint(1);
    store().removeConstraint(0);
    expect(store().constraints).toEqual([{ kind: "vertical", entity: "e2" }]);
    expect(store().selectedConstraint).toBe(0);
  });
});

describe("construction toggle", () => {
  it("marks the selected entity construction, bumps revision, clears selection", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const before = store().revision;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().toggleConstruction();
    const e1 = store().entities.find((e) => e.id === "e1");
    expect(e1?.construction).toBe(true);
    // Only the addressed entity flips; the other three stay profile.
    expect(store().entities.filter((e) => e.construction)).toHaveLength(1);
    expect(store().revision).toBe(before + 1);
    expect(store().selection).toEqual([]); // deselected so the dash shows
  });

  it("toggles a construction entity back to profile geometry", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().toggleConstruction();
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().toggleConstruction();
    expect(store().entities.find((e) => e.id === "e1")?.construction).toBe(
      false,
    );
    expect(store().entities.some((e) => e.construction)).toBe(false);
  });

  it("hints (no revision bump) when no entity is selected", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const before = store().revision;
    store().toggleConstruction();
    expect(store().hint).toMatch(/select an entity/i);
    expect(store().revision).toBe(before);
  });
});

describe("adoptSolved — the loop terminator", () => {
  it("merges solved positions by id without bumping revision", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const revision = store().revision;
    const solvedLine: SketchEntity = {
      id: "e1",
      kind: "line",
      start: { x: 1, y: 2 },
      end: { x: 41, y: 2 },
      construction: false,
    };
    store().adoptSolved([solvedLine], {
      status: "underconstrained",
      dof: 12,
      conflicting: [],
      redundant: [],
    });
    expect(store().revision).toBe(revision);
    expect(store().entities[0]).toEqual(solvedLine);
    expect(store().entities).toHaveLength(4); // unmatched entities kept
    expect(store().solve).toMatchObject({
      status: "underconstrained",
      dof: 12,
    });
  });

  it("null entities update only the solve diagnosis (conflict echo)", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const entities = store().entities;
    store().adoptSolved(null, {
      status: "conflicting",
      dof: null,
      conflicting: [0, 1],
      redundant: [],
    });
    expect(store().entities).toBe(entities);
    expect(store().solve?.conflicting).toEqual([0, 1]);
  });
});

describe("escape cascade", () => {
  it("editor → placement → tool → selection → exit", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance"); // editor open
    store().escape();
    expect(store().dimensionEdit).toBeNull();
    expect(store().selection).toHaveLength(1); // selection survived
    store().escape();
    expect(store().selection).toEqual([]);
    store().escape();
    expect(store().mode).toBe("off");
  });

  it("placement and tool stages still come before selection", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("line");
    store().placeAt({ x: 0, y: 0 });
    store().escape(); // cancels the pending point
    expect(store().pending).toEqual([]);
    expect(store().tool).toBe("line");
    store().escape(); // resets the tool
    expect(store().tool).toBe("select");
  });
});

describe("trim/extend edit + constraint reconciliation", () => {
  it("requestEdit arms one edit, blocks re-entry while busy, hints on a miss", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().requestEdit("trim", "e1", { x: 20, y: 0 });
    expect(store().edit).toMatchObject({ op: "trim", target: "e1", nonce: 1 });
    expect(store().editBusy).toBe(true);
    // A second arm while busy is ignored (one edit in flight at a time).
    store().requestEdit("trim", "e2", { x: 40, y: 12 });
    expect(store().edit?.target).toBe("e1");
    // A miss (null target) never arms a request — it hints instead.
    store().failEdit("reset");
    store().requestEdit("extend", null, { x: 99, y: 99 });
    expect(store().edit).toBeNull();
    expect(store().hint).toMatch(/aim at a curve to extend/i);
  });

  it("applyEditResult swaps entities, drops dangling constraints, notes the count", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    // Constrain e1 (bottom) horizontal, e2 (right) vertical.
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("horizontal");
    store().selectAt({ x: 40, y: 12 }, 2);
    store().applyConstraint("vertical");
    expect(store().constraints).toHaveLength(2);

    store().requestEdit("trim", "e2", { x: 40, y: 12 });
    const revision = store().revision;
    // The result deletes e2 entirely (whole-curve trim) — its vertical
    // constraint is now dangling and must be dropped.
    const kept = store().entities.filter((e) => e.id !== "e2");
    store().applyEditResult("trim", kept);

    expect(store().entities.map((e) => e.id)).toEqual(["e1", "e3", "e4"]);
    expect(store().constraints).toEqual([{ kind: "horizontal", entity: "e1" }]);
    expect(store().revision).toBe(revision + 1);
    expect(store().editBusy).toBe(false);
    expect(store().edit).toBeNull();
    expect(store().editNote).toMatch(/trimmed\. 1 constraint removed/i);
  });

  it("a clean extend notes the verb without a removed count", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().requestEdit("extend", "e1", { x: 0, y: 0 });
    const grown = store().entities.map((e) =>
      e.id === "e1" && e.kind === "line"
        ? { ...e, start: { x: -10, y: 0 } }
        : e,
    );
    store().applyEditResult("extend", grown);
    expect(store().editNote).toBe("Extended.");
    expect(store().constraints).toEqual([]);
    const e1 = store().entities.find((e) => e.id === "e1");
    expect(e1?.kind === "line" ? e1.start : null).toEqual({ x: -10, y: 0 });
  });

  it("switching tools clears the edit note", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().requestEdit("trim", "e1", { x: 20, y: 0 });
    store().applyEditResult("trim", store().entities);
    expect(store().editNote).not.toBeNull();
    store().setTool("line");
    expect(store().editNote).toBeNull();
  });
});

describe("bind + revision bookkeeping", () => {
  it("placing entities bumps revision; bind records the feature", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    expect(store().revision).toBe(1); // one placement batch (4 lines)
    store().bind("feat-1");
    expect(store().featureId).toBe("feat-1");
    store().exit();
    expect(store().featureId).toBeNull();
    expect(store().revision).toBe(0);
  });
});
