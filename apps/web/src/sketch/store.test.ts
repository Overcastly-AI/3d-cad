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

describe("plane choice", () => {
  it("choosePlane keeps the one-click origin path (kind: origin)", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XZ");
    expect(store().mode).toBe("draw");
    expect(store().plane).toEqual({ kind: "origin", base: "XZ" });
  });

  it("choosePlaneSpec seats a sketch on an authored offset plane", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlaneSpec({
      kind: "offset",
      base: "XY",
      offsetMm: 30,
      flip: false,
      datumFeatureId: "f-p001",
    });
    expect(store().mode).toBe("draw");
    expect(store().plane).toEqual({
      kind: "offset",
      base: "XY",
      offsetMm: 30,
      flip: false,
      datumFeatureId: "f-p001",
    });
  });
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

describe("spline draw tool", () => {
  it("accumulates fit points, then finishPlacement commits one spline", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("spline");
    const before = store().revision;
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 10, y: 20 });
    store().placeAt({ x: 30, y: 5 });
    // Open sequence — nothing committed, no revision bump yet.
    expect(store().entities).toEqual([]);
    expect(store().pending).toHaveLength(3);
    expect(store().revision).toBe(before);

    store().finishPlacement();
    expect(store().pending).toEqual([]);
    expect(store().entities).toEqual([
      {
        id: "e1",
        kind: "spline",
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 20 },
          { x: 30, y: 5 },
        ],
        construction: false,
      },
    ]);
    expect(store().revision).toBe(before + 1);
  });

  it("finishPlacement below two fit points is a no-op", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("spline");
    store().placeAt({ x: 0, y: 0 });
    const before = store().revision;
    store().finishPlacement();
    expect(store().entities).toEqual([]);
    expect(store().pending).toEqual([{ x: 0, y: 0 }]);
    expect(store().revision).toBe(before);
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

describe("offset — appends a parallel copy, no reconciliation", () => {
  it("beginOffset opens the distance editor; a miss hints instead", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().beginOffset(null);
    expect(store().offsetDraft).toBeNull();
    expect(store().hint).toMatch(/aim at a curve to offset/i);

    store().beginOffset("e1");
    expect(store().offsetDraft).toEqual({ target: "e1" });
    expect(store().hint).toBeNull();
  });

  it("armOffset arms one request; rejects a zero distance", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().beginOffset("e1");
    store().armOffset(0); // zero → sketch_offset_zero_distance; refused here
    expect(store().offset).toBeNull();
    expect(store().offsetDraft).toEqual({ target: "e1" });

    store().armOffset(-3);
    expect(store().offset).toMatchObject({
      target: "e1",
      distance: -3,
      nonce: 1,
    });
    expect(store().offsetDraft).toBeNull();
    expect(store().editBusy).toBe(true);
  });

  it("applyOffsetResult APPENDS the new entity, bumps revision, keeps constraints", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().applyConstraint("horizontal");
    expect(store().constraints).toHaveLength(1);
    const before = store().entities.length;

    store().beginOffset("e1");
    store().armOffset(2);
    const revision = store().revision;
    // Backend returns ONLY the new offset entity (fresh id, source untouched).
    const added: SketchEntity = {
      id: "e1.1",
      kind: "line",
      start: { x: 0, y: 2 },
      end: { x: 40, y: 2 },
      construction: false,
    };
    store().applyOffsetResult([added]);

    expect(store().entities).toHaveLength(before + 1);
    expect(store().entities.at(-1)).toEqual(added);
    // Nothing was deleted — the source's constraint survives untouched.
    expect(store().constraints).toEqual([{ kind: "horizontal", entity: "e1" }]);
    expect(store().revision).toBe(revision + 1);
    expect(store().editBusy).toBe(false);
    expect(store().offset).toBeNull();
    expect(store().editNote).toMatch(/offset added/i);
  });

  it("failOffset clears the request and surfaces the degenerate message", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().beginOffset("e1");
    store().armOffset(2);
    store().failOffset("Offset radius collapses to zero or less.");
    expect(store().offset).toBeNull();
    expect(store().editBusy).toBe(false);
    expect(store().hint).toMatch(/collapses/i);
  });

  it("Escape closes the offset editor before resetting the tool", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("offset");
    store().beginOffset("e1");
    store().escape();
    expect(store().offsetDraft).toBeNull();
    expect(store().tool).toBe("offset"); // editor closed first, tool survived
  });
});

describe("mirror — two-phase pick, appends reflected copies", () => {
  it("arming Mirror opens the targets phase; targets toggle in and out", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("mirror");
    expect(store().mirror).toEqual({ phase: "targets", targets: [] });

    store().toggleMirrorTarget("e1");
    store().toggleMirrorTarget("e3");
    expect(store().mirror).toEqual({ phase: "targets", targets: ["e1", "e3"] });
    store().toggleMirrorTarget("e1"); // re-click removes
    expect(store().mirror).toEqual({ phase: "targets", targets: ["e3"] });

    store().toggleMirrorTarget(null); // a miss hints, no change
    expect(store().hint).toMatch(/click an entity/i);
    expect(store().mirror?.targets).toEqual(["e3"]);
  });

  it("advanceMirror needs at least one target; then reaches the axis phase", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("mirror");
    store().advanceMirror(); // empty → hint, stay in targets
    expect(store().mirror?.phase).toBe("targets");
    expect(store().hint).toMatch(/at least one/i);

    store().toggleMirrorTarget("e1");
    store().advanceMirror();
    expect(store().mirror).toEqual({ phase: "axis", targets: ["e1"] });
  });

  it("pickMirrorAxis rejects a non-line and a miss; arms on a line", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    // Add a circle (e5) so a non-line axis pick is testable.
    store().setTool("circle");
    store().placeAt({ x: 60, y: 60 });
    store().placeAt({ x: 70, y: 60 });

    store().setTool("mirror");
    store().toggleMirrorTarget("e1");
    store().advanceMirror();

    store().pickMirrorAxis(null); // miss
    expect(store().mirrorRequest).toBeNull();
    expect(store().hint).toMatch(/aim at a line/i);

    store().pickMirrorAxis("e5"); // circle → not a valid axis
    expect(store().mirrorRequest).toBeNull();
    expect(store().hint).toMatch(/must be a line/i);

    store().pickMirrorAxis("e2"); // e2 is a rectangle line
    expect(store().mirrorRequest).toMatchObject({
      targets: ["e1"],
      axis: { kind: "entity", entity: "e2" },
      nonce: 1,
    });
    expect(store().editBusy).toBe(true);
  });

  it("applyMirrorResult APPENDS the copies, re-solves, re-arms targets phase", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("mirror");
    store().toggleMirrorTarget("e1");
    store().advanceMirror();
    store().pickMirrorAxis("e2");
    const before = store().entities.length;
    const revision = store().revision;

    const added: SketchEntity = {
      id: "e1.2",
      kind: "line",
      start: { x: 80, y: 0 },
      end: { x: 120, y: 0 },
      construction: false,
    };
    store().applyMirrorResult([added]);

    expect(store().entities).toHaveLength(before + 1);
    expect(store().entities.at(-1)).toEqual(added);
    expect(store().revision).toBe(revision + 1);
    expect(store().editBusy).toBe(false);
    expect(store().mirrorRequest).toBeNull();
    // Re-armed for another mirror, still on the tool.
    expect(store().mirror).toEqual({ phase: "targets", targets: [] });
    expect(store().editNote).toMatch(/mirrored/i);
  });

  it("failMirror surfaces the message and keeps the axis phase for a retry", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("mirror");
    store().toggleMirrorTarget("e1");
    store().advanceMirror();
    store().pickMirrorAxis("e2");
    store().failMirror("The mirror axis must be a line.");
    expect(store().mirrorRequest).toBeNull();
    expect(store().editBusy).toBe(false);
    expect(store().hint).toMatch(/must be a line/i);
    expect(store().mirror?.phase).toBe("axis"); // survives for another pick
  });

  it("Escape cascades axis → targets → drop tool", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("mirror");
    store().toggleMirrorTarget("e1");
    store().advanceMirror();
    expect(store().mirror?.phase).toBe("axis");

    store().escape(); // axis → back to targets (picks kept)
    expect(store().mirror).toEqual({ phase: "targets", targets: ["e1"] });

    store().escape(); // targets with picks → clear picks
    expect(store().mirror).toEqual({ phase: "targets", targets: [] });

    store().escape(); // empty targets → drop the tool
    expect(store().mirror).toBeNull();
    expect(store().tool).toBe("select");
  });
});

describe("fillet/chamfer — two-line pick, rewrites in place", () => {
  it("arming Fillet opens a corner draft; legs toggle in and out (cap 2)", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("fillet");
    expect(store().corner).toEqual({ op: "fillet", picks: [] });

    store().pickCornerLine("e1");
    store().pickCornerLine("e2");
    expect(store().corner).toEqual({ op: "fillet", picks: ["e1", "e2"] });

    // A third leg is ignored once two are held (editor is open).
    store().pickCornerLine("e3");
    expect(store().corner?.picks).toEqual(["e1", "e2"]);
  });

  it("a miss and a non-line leg hint instead of picking", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    // Add a circle (e5) so a non-line leg is testable.
    store().setTool("circle");
    store().placeAt({ x: 60, y: 60 });
    store().placeAt({ x: 70, y: 60 });

    store().setTool("chamfer");
    store().pickCornerLine(null); // miss
    expect(store().corner?.picks).toEqual([]);
    expect(store().hint).toMatch(/click a line/i);

    store().pickCornerLine("e5"); // circle → unsupported in v1
    expect(store().corner?.picks).toEqual([]);
    expect(store().hint).toMatch(/two lines/i);
  });

  it("armCorner builds the request from the two legs; rejects a non-positive value", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("fillet");
    store().pickCornerLine("e1");
    store().pickCornerLine("e2");

    store().armCorner(0); // radius must be > 0 → refused at the edge
    expect(store().cornerRequest).toBeNull();
    store().armCorner(-2);
    expect(store().cornerRequest).toBeNull();

    store().armCorner(2);
    expect(store().cornerRequest).toMatchObject({
      op: "fillet",
      a: "e1",
      b: "e2",
      value: 2,
      nonce: 1,
    });
    expect(store().editBusy).toBe(true);
  });

  it("applyCornerResult SWAPS the whole rewritten set, bumps revision, keeps ids' constraints", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().applyConstraint("horizontal");
    expect(store().constraints).toHaveLength(1);

    store().setTool("fillet");
    store().pickCornerLine("e1");
    store().pickCornerLine("e2");
    store().armCorner(2);
    const revision = store().revision;

    // Backend echoes the WHOLE set: e1/e2 trimmed in place (ids preserved) plus
    // a fresh bridge arc appended.
    const rewritten: SketchEntity[] = [
      {
        id: "e1",
        kind: "line",
        start: { x: 2, y: 0 },
        end: { x: 40, y: 0 },
        construction: false,
      },
      {
        id: "e2",
        kind: "line",
        start: { x: 40, y: 0 },
        end: { x: 40, y: 25 },
        construction: false,
      },
      {
        id: "e3",
        kind: "line",
        start: { x: 40, y: 25 },
        end: { x: 0, y: 25 },
        construction: false,
      },
      {
        id: "e4",
        kind: "line",
        start: { x: 0, y: 25 },
        end: { x: 0, y: 0 },
        construction: false,
      },
      {
        id: "e1.2",
        kind: "arc",
        center: { x: 2, y: 2 },
        start: { x: 2, y: 0 },
        end: { x: 0, y: 2 },
        construction: false,
      },
    ];
    store().applyCornerResult(rewritten);

    expect(store().entities).toEqual(rewritten);
    // e1 kept its id, so its horizontal constraint survives the trim.
    expect(store().constraints).toEqual([{ kind: "horizontal", entity: "e1" }]);
    expect(store().revision).toBe(revision + 1);
    expect(store().editBusy).toBe(false);
    expect(store().cornerRequest).toBeNull();
    // Re-armed for another corner, still on the tool.
    expect(store().corner).toEqual({ op: "fillet", picks: [] });
    expect(store().editNote).toMatch(/filleted/i);
  });

  it("failCorner surfaces the message and keeps the picks for a retry", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("chamfer");
    store().pickCornerLine("e1");
    store().pickCornerLine("e2");
    store().armCorner(999);
    store().failCorner("Radius is too large for this corner.");
    expect(store().cornerRequest).toBeNull();
    expect(store().editBusy).toBe(false);
    expect(store().hint).toMatch(/too large/i);
    // Both legs survive so a smaller value can be retyped without re-picking.
    expect(store().corner?.picks).toEqual(["e1", "e2"]);
  });

  it("Escape cascades close editor/clear picks → drop the tool", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().setTool("fillet");
    store().pickCornerLine("e1");
    store().pickCornerLine("e2");

    store().escape(); // picks (editor open) → clear picks
    expect(store().corner).toEqual({ op: "fillet", picks: [] });

    store().escape(); // empty picks → drop the tool
    expect(store().corner).toBeNull();
    expect(store().tool).toBe("select");
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
