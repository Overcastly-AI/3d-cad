/**
 * Store-level tests for the selection/constraint state machine and the
 * revision bookkeeping the live save loop depends on (user edits bump
 * `revision`; adopting solved geometry must NOT).
 */
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

import {
  constraintEntityRefs,
  formatSolveCell,
  solveDiagnostic,
} from "./constraints";
import { datumFrame } from "./datum";
import { shapeRigidity } from "./drawDimensions";
import { DIMENSION_PICK_HINT, useSketchStore } from "./store";
import type { Point2D } from "./plane";
import type { SketchEntity } from "./tools";

const rectangleAt = (store = useSketchStore.getState()) => {
  store.begin();
  useSketchStore.getState().choosePlane("XY");
  useSketchStore.getState().setTool("rect");
  useSketchStore.getState().placeAt({ x: 0, y: 0 });
  useSketchStore.getState().placeAt({ x: 40, y: 25 });
  useSketchStore.getState().setTool("select");
};

/**
 * How many constraints `rectangleAt` leaves behind before any test does
 * anything: the RECT-1 rigidity set the draw itself authors. DERIVED from the
 * real function rather than typed as 12, so it cannot drift away from the
 * product — if the rigidity set changes, every delta assertion below moves
 * with it instead of silently measuring the wrong window.
 */
const RECT_RIGIDITY = shapeRigidity("rect", ["e1", "e2", "e3", "e4"]).length;

/**
 * The constraints a test's OWN verb added, with the fixture's rigidity set
 * dropped. Tests here are about what a verb does, not about how a rectangle is
 * held together — that has its own coverage in `drawDimensions.test.ts` and in
 * the `placeAt` describe below.
 */
const authored = () =>
  useSketchStore.getState().constraints.slice(RECT_RIGIDITY);

/**
 * Author one constraint on the fixture rectangle that its rigidity set does NOT
 * already imply, for the tests below that just need SOME authored constraint to
 * push around (remove it, undo it, select its glyph).
 *
 * Horizontal/vertical used to be the cheap way to do that and no longer are:
 * RECT-1 makes every edge horizontal or vertical at the draw, so the verb now
 * correctly answers "Already horizontal." and authors nothing. `equal` between
 * two edges is not in the rigidity set, so it lands.
 */
const authorEqual = (a: Point2D, b: Point2D) => {
  const store = useSketchStore.getState;
  store().selectAt(a, 2);
  store().setSnapModifiers({ suppressed: false, axisLock: true }); // Shift: add
  store().selectAt(b, 2);
  store().setSnapModifiers({ suppressed: false, axisLock: false });
  store().applyConstraint("equal");
};

/** The fixture rectangle's two horizontal edges (e1 bottom, e3 top). */
const EDGE_BOTTOM = { x: 20, y: 0.5 } as const;
const EDGE_TOP = { x: 20, y: 25 } as const;
/** …and its two vertical ones (e2 right, e4 left). */
const EDGE_RIGHT = { x: 40, y: 12 } as const;
const EDGE_LEFT = { x: 0, y: 12 } as const;

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
  it("selectAt picks, and clears on empty clicks", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line curve
    expect(store().selection).toEqual([{ kind: "entity", id: "e1" }]);
    store().selectAt({ x: 20, y: 0.5 }, 2); // same spot → still the line
    expect(store().selection).toEqual([{ kind: "entity", id: "e1" }]);
    store().selectAt({ x: 500, y: 500 }, 2); // empty steel → clear
    expect(store().selection).toEqual([]);
  });

  // FB-14: the founder's path — click one line, then another, and dimension
  // the SECOND. Appending left both selected and `distance` refused.
  it("a plain click on a second entity replaces the first", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().selectAt({ x: 40, y: 12 }, 2); // right line e2
    expect(store().selection).toEqual([{ kind: "entity", id: "e2" }]);
    store().applyConstraint("distance"); // one line → the editor opens
    expect(store().dimensionEdit).toMatchObject({
      kind: "distance",
      entity: "e2",
    });
    expect(store().hint).toBeNull();
  });

  it("Shift (axis-lock modifier) adds — the two-entity constraint path", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().setSnapModifiers({ suppressed: false, axisLock: true });
    store().selectAt({ x: 40, y: 12 }, 2); // right line e2, Shift held
    expect(store().selection).toEqual([
      { kind: "entity", id: "e1" },
      { kind: "entity", id: "e2" },
    ]);
    store().applyConstraint("perpendicular");
    expect(authored()).toHaveLength(1);
  });

  it("Ctrl/Cmd (snap-suppress modifier) adds too", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().setSnapModifiers({ suppressed: true, axisLock: false });
    store().selectAt({ x: 40, y: 12 }, 2);
    expect(store().selection).toHaveLength(2);
    // A modifier-click that MISSES keeps what is being assembled.
    store().selectAt({ x: 500, y: 500 }, 2);
    expect(store().selection).toHaveLength(2);
  });

  it("an explicit mode beats the tracked modifier state", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().setSnapModifiers({ suppressed: false, axisLock: true });
    store().selectAt({ x: 40, y: 12 }, 2, "replace");
    expect(store().selection).toEqual([{ kind: "entity", id: "e2" }]);
  });

  it("corner clicks cycle through the stacked endpoints, one at a time", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 40, y: 0 }, 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "e1", point: "end" },
    ]);
    store().selectAt({ x: 40, y: 0 }, 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "e2", point: "start" },
    ]);
    // Shift on the second click collects BOTH — how a coincident is authored.
    store().clearSelection();
    store().selectAt({ x: 40, y: 0 }, 1);
    store().setSnapModifiers({ suppressed: false, axisLock: true });
    store().selectAt({ x: 40, y: 0 }, 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "e1", point: "end" },
      { kind: "point", entity: "e2", point: "start" },
    ]);
  });

  it("the fit-point handles stay toggles (aria-pressed, modifier-free)", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const a = { kind: "point", entity: "e1", point: "start" } as const;
    const b = { kind: "point", entity: "e2", point: "end" } as const;
    store().togglePick(a);
    store().togglePick(b);
    expect(store().selection).toEqual([a, b]);
    store().togglePick(b);
    expect(store().selection).toEqual([a]);
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
    // `equal` is a verb a rectangle does NOT already imply — the two horizontal
    // edges are each horizontal, but nothing says they are the same LENGTH.
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().setSnapModifiers({ suppressed: false, axisLock: true });
    store().selectAt({ x: 20, y: 25 }, 2); // top line e3, Shift held
    store().setSnapModifiers({ suppressed: false, axisLock: false });
    store().applyConstraint("equal");
    expect(authored()).toEqual([{ kind: "equal", a: "e1", b: "e3" }]);
    expect(store().revision).toBe(before + 1);
    expect(store().selection).toEqual([]); // applied verbs clear selection

    store().applyConstraint("coincident"); // nothing selected → hint
    expect(store().hint).toMatch(/two points/i);
    expect(store().revision).toBe(before + 1);
  });

  // RECT-1's most visible interaction, and the one that would have been an
  // over-constraint report if the rigidity set were authored twice: the draw
  // already made the bottom edge horizontal, so the verb must REFUSE and say
  // so, not stack a redundant copy and let the solver complain later.
  it("a verb the drawn rectangle already implies is refused, not stacked", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const before = store().revision;
    store().selectAt({ x: 20, y: 0.5 }, 2); // bottom line e1
    store().applyConstraint("horizontal");
    expect(authored()).toEqual([]);
    expect(store().hint).toMatch(/already horizontal/i);
    expect(store().revision).toBe(before); // a refusal is not an edit
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
    store().commitDimension({
      valueMm: 60,
      expression: null,
      name: null,
      driving: true,
    });
    expect(authored()).toEqual([
      {
        kind: "distance",
        entity: "e1",
        value_mm: 60,
        expression: null,
        name: null,
        driving: null,
      },
    ]);
    expect(store().dimensionEdit).toBeNull();
    expect(store().revision).toBe(revision + 1);
  });

  it("editDimension re-opens an existing dimension; commit replaces it", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    store().commitDimension({
      valueMm: 40,
      expression: null,
      name: null,
      driving: true,
    });
    store().editDimension(RECT_RIGIDITY);
    expect(store().dimensionEdit).toMatchObject({
      initialMm: 40,
      initialDriving: true,
      constraintIndex: RECT_RIGIDITY,
    });
    store().commitDimension({
      valueMm: 60,
      expression: null,
      name: null,
      driving: true,
    });
    expect(authored()).toEqual([
      {
        kind: "distance",
        entity: "e1",
        value_mm: 60,
        expression: null,
        name: null,
        driving: null,
      },
    ]);
  });

  it("commits an expression + name; sends expression, keeps value_mm placeholder", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    store().commitDimension({
      valueMm: 20,
      expression: "width/2",
      name: "half",
      driving: true,
    });
    expect(authored()).toEqual([
      {
        kind: "distance",
        entity: "e1",
        value_mm: 20,
        expression: "width/2",
        name: "half",
        driving: null,
      },
    ]);
  });

  it("a driven commit sends driving:false and drops the expression", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    store().commitDimension({
      valueMm: 40,
      expression: "width/2",
      name: null,
      driving: false,
    });
    expect(authored()).toEqual([
      {
        kind: "distance",
        entity: "e1",
        value_mm: 40,
        expression: null,
        name: null,
        driving: false,
      },
    ]);
  });

  it("commitDimension refuses non-positive values", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance");
    const revision = store().revision;
    store().commitDimension({
      valueMm: 0,
      expression: null,
      name: null,
      driving: true,
    });
    expect(authored()).toEqual([]);
    expect(store().revision).toBe(revision);
    expect(store().dimensionEdit).not.toBeNull();
  });

  it("removeConstraint reindexes the selected glyph", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    authorEqual(EDGE_BOTTOM, EDGE_TOP); // equal(e1, e3)
    authorEqual(EDGE_RIGHT, EDGE_LEFT); // equal(e2, e4)
    store().selectConstraint(RECT_RIGIDITY + 1);
    store().removeConstraint(RECT_RIGIDITY);
    expect(authored()).toEqual([{ kind: "equal", a: "e2", b: "e4" }]);
    expect(store().selectedConstraint).toBe(RECT_RIGIDITY);
  });
});

/**
 * FOUNDER 2026-08-14, "I still cannot click dimension and actually have it
 * assign a dimension." Reproduced in a browser as a DEAD END, not a wrong
 * value: a draw tool stays armed after it draws, so the click meant to select
 * the line is eaten as the next shape's first corner, and the dimension verb
 * kept answering "Select one line to dimension." These tests hold the fix at
 * the level where it lives — the verb arms and consumes the next entity click.
 */
describe("dimension verb with nothing selected — arms instead of refusing", () => {
  /** Draw a rectangle and leave the RECT TOOL ARMED, as a real user does. */
  const rectangleStillDrawing = () => {
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    useSketchStore.getState().setTool("rect");
    useSketchStore.getState().placeAt({ x: 0, y: 0 });
    useSketchStore.getState().placeAt({ x: 40, y: 25 });
  };

  it("drops the draw tool and asks for a click, instead of a dead end", () => {
    rectangleStillDrawing();
    const store = useSketchStore.getState;
    expect(store().tool).toBe("rect"); // the reason a click could not select
    expect(store().drawDimension).not.toBeNull();

    store().applyConstraint("distance");

    expect(store().dimensionPick).toBe("distance");
    expect(store().tool).toBe("select"); // the load-bearing half
    expect(store().pending).toEqual([]);
    expect(store().drawDimension).toBeNull();
    expect(store().hint).toBe("Click a line to dimension it.");
    expect(store().dimensionEdit).toBeNull();
  });

  it("the next entity click opens THAT entity's editor and disarms", () => {
    rectangleStillDrawing();
    const store = useSketchStore.getState;
    store().applyConstraint("distance");
    store().selectAt({ x: 20, y: 0.5 }, 2); // the bottom line

    expect(store().dimensionEdit).toMatchObject({
      kind: "distance",
      entity: "e1",
      initialMm: 40,
      constraintIndex: null,
    });
    expect(store().dimensionPick).toBeNull();
    // The pick is CONSUMED by the verb, not left as a selection behind the
    // editor — the editor already names its target.
    expect(store().selection).toEqual([]);
  });

  it("a click on empty space keeps it armed rather than silently disarming", () => {
    rectangleStillDrawing();
    const store = useSketchStore.getState;
    store().applyConstraint("distance");
    store().selectAt({ x: 500, y: 500 }, 2);
    expect(store().dimensionPick).toBe("distance");
    expect(store().dimensionEdit).toBeNull();
  });

  it("a wrong-kind pick says so and stays armed (circle under Distance)", () => {
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    useSketchStore.getState().setTool("circle");
    useSketchStore.getState().placeAt({ x: 0, y: 0 });
    useSketchStore.getState().placeAt({ x: 10, y: 0 });
    const store = useSketchStore.getState;
    store().applyConstraint("distance");
    store().selectAt({ x: 10, y: 0 }, 2); // on the circle
    expect(store().dimensionEdit).toBeNull();
    expect(store().dimensionPick).toBe("distance");
    // It names what was picked (DIM-3). This assertion used to read
    // `/one line/i`, which passed on "Select one line to dimension." — the
    // selection-first refusal this whole verb exists to eliminate, and false
    // while armed besides: the user clicked, they did not select.
    expect(store().hint).toBe(
      "That is a circle. Click a line to dimension it.",
    );
  });

  it("radius arms the same way, and picks the circle", () => {
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    useSketchStore.getState().setTool("circle");
    useSketchStore.getState().placeAt({ x: 0, y: 0 });
    useSketchStore.getState().placeAt({ x: 10, y: 0 });
    const store = useSketchStore.getState;
    store().applyConstraint("radius");
    expect(store().dimensionPick).toBe("radius");
    expect(store().hint).toBe("Click a circle or arc to dimension it.");
    store().selectAt({ x: 10, y: 0 }, 2);
    expect(store().dimensionEdit).toMatchObject({
      kind: "radius",
      entity: "e1",
      initialMm: 10,
    });
  });

  it("Escape disarms it and does NOT exit the sketch", () => {
    rectangleStillDrawing();
    const store = useSketchStore.getState;
    store().applyConstraint("distance");
    store().escape();
    expect(store().dimensionPick).toBeNull();
    expect(store().hint).toBeNull();
    expect(store().mode).toBe("draw"); // the sketch survives
    expect(store().entities).toHaveLength(4);
  });

  it("reaching for another tool abandons the armed verb", () => {
    rectangleStillDrawing();
    const store = useSketchStore.getState;
    store().applyConstraint("distance");
    store().setTool("line");
    expect(store().dimensionPick).toBeNull();
  });

  it("a NON-dimension verb still refuses with its own hint", () => {
    rectangleStillDrawing();
    const store = useSketchStore.getState;
    store().applyConstraint("coincident");
    expect(store().dimensionPick).toBeNull();
    expect(store().hint).toMatch(/two points/i);
  });
});

/**
 * DIM-3 — the two things reviewing the arm-fix (c449235) turned up.
 *
 * (a) ARMED WAS INVISIBLE. `dimensionPick` has no surface but `hint`, and
 * ordinary actions clear the hint as a matter of course when their own message
 * is over — so the verb stayed armed and went silent, and the NEXT canvas click
 * opened a dimension editor with nothing on screen to have predicted it. Held
 * now as an invariant (`withArmedPrompt`) rather than as care at each site,
 * which is why the third case below matters as much as the two that were filed.
 *
 * (b) A WRONG-KIND PICK REUSED THE REFUSAL SENTENCE. "Select one line to
 * dimension." is the dead end arming exists to remove, and it is false while
 * armed: the user clicked. It now names what they hit.
 */
describe("DIM-3 — an armed verb is never silent, and never answers with the refusal", () => {
  /** A rectangle, then Distance armed exactly as the strip arms it. */
  const armedOnRectangle = () => {
    rectangleAt();
    useSketchStore.getState().applyConstraint("distance");
    return useSketchStore.getState;
  };

  it("selecting a constraint glyph leaves the armed prompt standing", () => {
    const store = armedOnRectangle();
    expect(store().hint).toBe(DIMENSION_PICK_HINT.distance);

    // WHICH glyph is not the claim — any constraint the rectangle carries will
    // do — so index 0 here is a fixture detail, not an assertion about order.
    store().selectConstraint(0);

    expect(store().dimensionPick).toBe("distance"); // still armed…
    expect(store().hint).toBe(DIMENSION_PICK_HINT.distance); // …and still says so
  });

  it("toggling a pick leaves the armed prompt standing", () => {
    const store = armedOnRectangle();
    store().togglePick({ kind: "entity", id: "e1" });
    expect(store().dimensionPick).toBe("distance");
    expect(store().hint).toBe(DIMENSION_PICK_HINT.distance);
  });

  it("…and so does a site nobody filed — the invariant, not two patches", () => {
    // `toggleConstruction` clears the hint too, and was never mentioned in the
    // report. It is fixed by the same rule, which is the whole argument for
    // making this an invariant: the third site costs nothing to cover.
    const store = armedOnRectangle();
    store().togglePick({ kind: "entity", id: "e1" });
    store().toggleConstruction();
    expect(store().dimensionPick).toBe("distance");
    expect(store().hint).toBe(DIMENSION_PICK_HINT.distance);
  });

  it("does NOT keep talking once the verb is disarmed", () => {
    // The other direction, so the invariant cannot pass by shouting forever:
    // Escape disarms, and the prompt goes with the arming.
    const store = armedOnRectangle();
    store().escape();
    expect(store().dimensionPick).toBeNull();
    expect(store().hint).toBeNull();
  });

  it("names the picked kind under Radius too, not just Distance", () => {
    const store = useSketchStore.getState;
    rectangleAt();
    store().applyConstraint("radius");
    store().selectAt({ x: 20, y: 0.5 }, 2); // a LINE, under Radius

    expect(store().hint).toBe(
      "That is a line. Click a circle or arc to dimension it.",
    );
    expect(store().dimensionPick).toBe("radius"); // still armed
    expect(store().dimensionEdit).toBeNull();
  });

  it("never answers a click with the selection-first refusal, either verb", () => {
    /** A rectangle AND a circle, so each verb has a wrong kind to be handed. */
    const both = () => {
      rectangleAt();
      useSketchStore.getState().setTool("circle");
      useSketchStore.getState().placeAt({ x: 80, y: 0 });
      useSketchStore.getState().placeAt({ x: 90, y: 0 });
      useSketchStore.getState().setTool("select");
    };
    // Each pair is a verb and a point on geometry of the kind it CANNOT take.
    const wrongKind = [
      { verb: "distance", at: { x: 90, y: 0 } }, // the circle
      { verb: "radius", at: { x: 20, y: 0.5 } }, // a line of the rectangle
    ] as const;

    for (const { verb, at } of wrongKind) {
      both();
      const store = useSketchStore.getState;
      store().applyConstraint(verb);
      store().selectAt(at, 2);

      // Non-vacuity: this is only a statement about the wrong-kind reply if the
      // click was in fact refused an editor and left the verb armed.
      expect(store().dimensionEdit).toBeNull();
      expect(store().dimensionPick).toBe(verb);

      const hint = store().hint ?? "";
      expect(hint).not.toBe("Select one line to dimension.");
      expect(hint).not.toBe("Select one circle or arc to dimension.");
      // …and not any future rewording of the same instruction: nothing said to
      // someone who has just clicked should open by asking them to select.
      expect(hint).not.toMatch(/^select /i);
    }
  });

  it("passes the FRAME's refusal through — it is about the subject, not the kind", () => {
    // SKETCH-2: the axes are refused as a SUBJECT ("constrain TO them"), which
    // stays true while armed, so it must not be overwritten by a sentence about
    // kinds — the axis IS a line, and "That is a line. Click a line…" would be
    // the most confusing answer available.
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("rect");
    store().placeAt({ x: 20, y: 20 });
    store().placeAt({ x: 60, y: 45 });
    store().setTool("select");
    store().applyConstraint("distance");
    store().selectAt({ x: -30, y: 0 }, 2); // the X axis, clear of the rectangle

    expect(store().hint).toMatch(/origin and axes are fixed/i);
    expect(store().dimensionPick).toBe("distance"); // still armed
  });
});

describe("SKETCH-2 — the origin and axes are selectable constraint targets", () => {
  /** A rectangle clear of the frame, so the origin and axes are reachable. */
  const rectangleOffOrigin = () => {
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    useSketchStore.getState().setTool("rect");
    useSketchStore.getState().placeAt({ x: 20, y: 20 });
    useSketchStore.getState().placeAt({ x: 60, y: 45 });
    useSketchStore.getState().setTool("select");
  };

  it("selects the origin from a click on the drawn RING — the founder's gesture", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    // Reported: clicking the ring answered "nothing selected" while a click on
    // a drawn line answered "1 ent". The ring is ~1.36 mm out at the parked
    // frame, so a bare point tolerance measured from (0,0) never reached it.
    const ring = datumFrame(store().datumFrameHalfMm).ringRadiusMm;
    expect(ring).toBeCloseTo(1.361, 3);
    store().selectAt({ x: ring, y: 0 }, 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "origin", point: "position" },
    ]);
  });

  it("selects either axis from an empty selection, and clears on empty steel", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 30, y: 0 }, 1);
    expect(store().selection).toEqual([{ kind: "entity", id: "x-axis" }]);
    store().clearSelection();
    store().selectAt({ x: 0, y: -30 }, 1);
    expect(store().selection).toEqual([{ kind: "entity", id: "y-axis" }]);
    store().selectAt({ x: 300, y: 300 }, 1);
    expect(store().selection).toEqual([]);
  });

  it("a plain click on the invisible axis CLEARS a standing selection", () => {
    // "Click away to deselect" is a constant gesture, and the axes are an
    // invisible cross spanning the viewport (1.25 x the frame half-height) of
    // which only +/-8 px is ink. Before SKETCH-2 every such click answered
    // nothing selected; letting the cross convert one into "you have now also
    // got the X axis" turns a deselect into a multi-select whose next verb
    // refuses with "The origin and axes are fixed".
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 40, y: 20 }, 1); // the rectangle's bottom edge
    expect(store().selection).toHaveLength(1);
    store().selectAt({ x: -30, y: 0 }, 1); // empty steel, but ON the X axis
    expect(store().selection).toEqual([]);
    // …and with nothing held there is nothing to drop, so the same click means
    // what it looks like.
    store().selectAt({ x: -30, y: 0 }, 1);
    expect(store().selection).toEqual([{ kind: "entity", id: "x-axis" }]);
  });

  it("a modifier UN-pick still un-picks where the frame lies under the line", () => {
    // `toggleSelection`'s documented grain: the same modifier click twice
    // returns you to where you started. Appending the axis to the candidates
    // cost it that — [e1] then [e1, x-axis] — and the frame joined a
    // multi-select the user never asked for.
    useSketchStore.getState().begin();
    useSketchStore.getState().choosePlane("XY");
    useSketchStore.getState().setTool("line");
    useSketchStore.getState().placeAt({ x: 10, y: 0 });
    useSketchStore.getState().placeAt({ x: 50, y: 0 }); // lies ALONG the X axis
    useSketchStore.getState().setTool("select");
    const store = useSketchStore.getState;
    store().selectAt({ x: 30, y: 0 }, 1, "add");
    expect(store().selection).toEqual([{ kind: "entity", id: "e1" }]);
    store().selectAt({ x: 30, y: 0 }, 1, "add");
    expect(store().selection).toEqual([]);
  });

  it("grounds a corner to the origin: one authored constraint, one pin, DOF-neutral", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    const before = store().entities.length;
    store().selectAt({ x: 20, y: 20 }, 1); // the near corner (a point pick)
    store().selectAt(
      { x: datumFrame(store().datumFrameHalfMm).ringRadiusMm, y: 0 },
      1,
      "add",
    );
    expect(store().selection).toHaveLength(2);
    store().applyConstraint("coincident");

    // The authored constraint names the origin by the id the solver resolves.
    expect(authored()[0]).toEqual({
      kind: "coincident",
      a: { entity: "e1", point: "start" },
      b: { entity: "origin", point: "position" },
    });
    // …and the origin is now real, pinned CONSTRUCTION geometry, so the solver
    // moves the corner rather than the sketch's zero.
    expect(store().entities).toHaveLength(before + 1);
    const origin = store().entities.find((e) => e.id === "origin");
    expect(origin).toMatchObject({
      kind: "point",
      position: { x: 0, y: 0 },
      construction: true,
    });
    expect(authored()).toContainEqual({
      kind: "fixed",
      point: { entity: "origin", point: "position" },
    });
    // Only the origin was reached for — the axes stay out of the sketch.
    expect(store().entities.filter((e) => e.id.endsWith("axis"))).toEqual([]);
  });

  it("grounds symmetry about the Y axis, pinning the axis at both ends", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 20 }, 1);
    store().selectAt({ x: 60, y: 20 }, 1, "add");
    store().selectAt({ x: 0, y: 30 }, 1, "add"); // the Y axis
    expect(store().selection).toHaveLength(3);
    store().applyConstraint("symmetric");
    expect(authored()[0]).toMatchObject({
      kind: "symmetric",
      line: "y-axis",
    });
    expect(store().entities.find((e) => e.id === "y-axis")).toMatchObject({
      kind: "line",
      construction: true,
    });
    expect(
      authored().filter(
        (c) => c.kind === "fixed" && c.point.entity === "y-axis",
      ),
    ).toHaveLength(2);
  });

  it("grounds only ONCE — a second constraint to the origin adds no second pin", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    const ring = datumFrame(store().datumFrameHalfMm).ringRadiusMm;
    store().selectAt({ x: 20, y: 20 }, 1);
    store().selectAt({ x: ring, y: 0 }, 1, "add");
    store().applyConstraint("coincident");
    const entities = store().entities.length;
    store().selectAt({ x: 40, y: 45 }, 1); // the top edge, mid-span
    store().selectAt({ x: 0, y: 40 }, 1, "add"); // Y axis
    store().applyConstraint("perpendicular");
    expect(store().entities).toHaveLength(entities + 1); // the axis only
    expect(
      authored().filter(
        (c) => c.kind === "fixed" && c.point.entity === "origin",
      ),
    ).toHaveLength(1);
  });

  it("refuses to make the frame the SUBJECT of a verb, and adds nothing", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    const before = { ...store() };
    store().selectAt({ x: 30, y: 0 }, 1); // the X axis
    for (const verb of ["distance", "horizontal", "fixed"] as const) {
      store().applyConstraint(verb);
      expect(store().hint).toMatch(/origin and axes are fixed/i);
      expect(store().dimensionEdit).toBeNull();
    }
    expect(authored()).toEqual([]);
    expect(store().entities).toHaveLength(before.entities.length);
    expect(store().revision).toBe(before.revision);
  });

  it("refuses to flip the frame to profile geometry", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 30, y: 0 }, 1);
    store().toggleConstruction();
    expect(store().hint).toMatch(/select an entity/i);
    expect(store().entities.some((e) => e.id === "x-axis")).toBe(false);
  });

  it("Escape gives the frame selection back through the existing rung", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 30, y: 0 }, 1);
    expect(store().selection).toHaveLength(1);
    store().escape();
    expect(store().selection).toEqual([]);
    expect(store().mode).toBe("draw"); // did not fall through and exit
  });

  it("re-opening a grounded sketch keeps the frame addressable, not duplicated", () => {
    const store = useSketchStore.getState;
    const ring = datumFrame(store().datumFrameHalfMm).ringRadiusMm;
    rectangleOffOrigin();
    store().selectAt({ x: 20, y: 20 }, 1);
    store().selectAt({ x: ring, y: 0 }, 1, "add");
    store().applyConstraint("coincident");
    // The FULL set, rigidity included — this is what `beginEdit` is handed, and
    // a re-opened sketch that lost its rectangle's rigidity would be the RECT-1
    // defect reintroduced through the save path.
    const saved = {
      entities: store().entities,
      constraints: store().constraints,
    };

    store().exit();
    store().beginEdit("f-1", { kind: "origin", base: "XY" }, saved.entities, [
      ...saved.constraints,
    ]);
    expect(store().entities.filter((e) => e.id === "origin")).toHaveLength(1);
    // Still selectable, and constraining to it again materialises nothing new.
    store().selectAt({ x: ring, y: 0 }, 1);
    expect(store().selection).toEqual([
      { kind: "point", entity: "origin", point: "position" },
    ]);
    store().selectAt({ x: 60, y: 20 }, 1, "add");
    store().applyConstraint("coincident");
    expect(store().entities).toEqual(saved.entities);
    expect(store().constraints).toHaveLength(saved.constraints.length + 1);
  });

  /**
   * THE BLOCKING REVIEW FINDING, end to end through the store. The unit tests
   * in `datum.test.ts` prove the filter; this proves the WIRING — that the one
   * seam every reader goes through (`adoptSolved`) actually applies it, on the
   * sketch the store really authors, with the indices the real solver really
   * returned for it.
   */
  it("never reports an OVER-CONSTRAINT the user cannot act on", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 20 }, 1);
    store().selectAt({ x: 20, y: 45 }, 1, "add");
    store().selectAt({ x: -30, y: 0 }, 1, "add"); // the X axis
    store().applyConstraint("symmetric");

    // The two pins the store authored ARE the last two constraints, and the
    // index the solver flagged is the second of them.
    // ABSOLUTE index: this is the number the SOLVER reports back in `redundant`,
    // so it counts the rigidity set too.
    const pinAt = store().constraints.length - 1;
    expect(store().constraints[pinAt]).toEqual({
      kind: "fixed",
      point: { entity: "x-axis", point: "end" },
    });

    // Exactly what the solver returned for this shape (planegcs, measured):
    // overconstrained, dof 3, redundant = [the second pin].
    store().adoptSolved(null, {
      status: "overconstrained",
      dof: 3,
      conflicting: [],
      redundant: [pinAt],
    });

    const solve = store().solve;
    expect(solve?.redundant).toEqual([]);
    expect(solve?.status).toBe("underconstrained");
    // The banner the user would have read is gone, and the DRO reads the DOF.
    expect(solveDiagnostic(solve)).toBeNull();
    expect(formatSolveCell(solve, false).value).toBe(
      "DOF 3 · UNDER-CONSTRAINED",
    );
  });

  it("still reports an over-constraint the user CAN act on", () => {
    rectangleOffOrigin();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 20 }, 1);
    store().selectAt({ x: -30, y: 0 }, 1, "add");
    store().applyConstraint("coincident"); // corner ON the axis, + 2 pins
    store().selectAt({ x: 40, y: 20 }, 1); // the bottom edge
    store().applyConstraint("horizontal"); // index 3: a real, glyphed verb

    store().adoptSolved(null, {
      status: "overconstrained",
      dof: 2,
      conflicting: [],
      redundant: [3],
    });
    expect(store().solve?.status).toBe("overconstrained");
    expect(store().solve?.redundant).toEqual([3]);
    expect(solveDiagnostic(store().solve)).toMatchObject({
      title: "Over-constrained",
    });
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

  it("adopts per-dimension readouts; omitting them keeps the last-good", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    const dims = [
      { constraint_index: 0, name: "width", driving: true, value_mm: 20 },
      {
        constraint_index: 1,
        name: null,
        driving: true,
        value_mm: 10,
        expression: "width/2",
      },
    ];
    store().adoptSolved(
      [],
      { status: "underconstrained", dof: 1, conflicting: [], redundant: [] },
      dims,
    );
    expect(store().solvedDimensions).toEqual(dims);
    // An `invalid` error path omits dimensions → the last-good readouts survive.
    store().adoptSolved(null, {
      status: "invalid",
      dof: null,
      conflicting: [],
      redundant: [],
      message: "unknown dimension 'wdth'",
    });
    expect(store().solvedDimensions).toEqual(dims);
    expect(store().solve?.status).toBe("invalid");
  });
});

describe("escape cascade", () => {
  it("editor → placement → tool → selection → and then STOPS", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().selectAt({ x: 20, y: 0.5 }, 2);
    store().applyConstraint("distance"); // editor open
    store().escape();
    expect(store().dimensionEdit).toBeNull();
    expect(store().selection).toHaveLength(1); // selection survived
    store().escape();
    expect(store().selection).toEqual([]);
    // FB-13: the founder's reflex — one more Escape at rest. The sketch stays
    // open with its geometry intact, and says where finishing lives.
    store().escape();
    expect(store().mode).toBe("draw");
    expect(store().entities).toHaveLength(4);
    expect(store().hint).toMatch(/nothing to cancel/i);
    store().escape(); // …and it never falls through on the next press either
    expect(store().mode).toBe("draw");
  });

  it("a bound sketch's rest hint names Finish, not Save", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    store().bind("feat-1");
    store().escape();
    expect(store().hint).toMatch(/finish sketch/i);
    expect(store().mode).toBe("draw");
  });

  // The latent second half of FB-13: `escape` weighed only `selection`, so a
  // picked constraint GLYPH left the cascade one rung short and fell straight
  // through to exit — Escape wiped the session with a dimension selected.
  it("a selected constraint glyph is a selection rung, not an exit", () => {
    rectangleAt();
    const store = useSketchStore.getState;
    authorEqual(EDGE_BOTTOM, EDGE_TOP);
    store().selectConstraint(RECT_RIGIDITY);
    store().escape();
    expect(store().mode).toBe("draw");
    expect(store().selectedConstraint).toBeNull();
    expect(authored()).toHaveLength(1);
  });

  it("still backs out of the plane-pick step (nothing drawn yet)", () => {
    const store = useSketchStore.getState;
    store().begin();
    expect(store().mode).toBe("plane");
    store().escape();
    expect(store().mode).toBe("off");
  });

  it("still backs out of an empty sketch opened by mistake", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
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

/**
 * ESC-2 — ONE cascade, and this store owns it.
 *
 * There were two. `PartPage`'s keydown handler re-derived the rung with its own
 * `escapeAction(…)` call and mapped `"exit"` to `finishSketch()` — which SAVES —
 * while `escape` maps that same verb to a fresh session — which DISCARDS. They
 * agreed only because that call omitted `escapeAction`'s fifth argument, so
 * `unstarted` defaulted false, `"exit"` was unreachable there, and the
 * `finishSketch()` never ran. FB-13 is "a key that sometimes saves and sometimes
 * discards"; this was that defect one argument away from waking up, in a verb
 * whose name says nothing about which of the two it means.
 *
 * So the guard has two halves, because a mapping cannot be tested by its own
 * output: what the exit rung DOES (below), and that nothing derives it twice.
 */
describe("ESC-2 — one Escape cascade, owned by the store", () => {
  /** The armed-verb state the keyboard reaches, on a sketch holding no work. */
  const armedOnEmptySketch = () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().applyConstraint("distance");
    return store;
  };

  it("the armed verb is a rung of its own — Escape disarms before it exits", () => {
    const store = armedOnEmptySketch();
    expect(store().dimensionPick).toBe("distance");

    store().escape();

    expect(store().dimensionPick).toBeNull();
    expect(store().mode).toBe("draw"); // the sketch is still open
  });

  it("the exit rung DISCARDS, and leaves nothing for a save loop to flush", () => {
    const store = armedOnEmptySketch();
    store().escape(); // disarm
    store().escape(); // …and now the last rung

    // DISCARD, stated as the whole of it: the session is gone, not handed to
    // the persistence effect. `PartPage`'s save loop keys on `mode === "draw"`
    // and a `revision` above the last synced one, so a fresh session is exactly
    // "nothing to write". This is safe only because the rung is `unstarted`.
    expect(store().mode).toBe("off");
    expect(store().entities).toEqual([]);
    expect(store().constraints).toEqual([]);
    expect(store().revision).toBe(0);
    expect(store().featureId).toBeNull();
    // And `userConstrained` is untouched by the cascade: it records that the
    // USER asked for a relation, which is what the unsaved-exit confirm reads.
    // Escape must not be able to set it, or backing out of an empty sketch
    // would start claiming there was work in it.
    expect(store().userConstrained).toBe(false);
  });

  it("still exits an unstarted sketch with no verb armed", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().escape();
    expect(store().mode).toBe("off");
  });

  it("PartPage routes Escape here instead of re-deriving the rung", () => {
    // The structural half. A behavioural test cannot see this: the second
    // mapping was DEAD code, so it broke nothing until an argument reached it —
    // which is the whole reason it survived to be filed. What can be asserted
    // is that the second derivation does not exist.
    const partPage = readFileSync(
      new URL("../routes/PartPage.tsx", import.meta.url),
      "utf8",
    );
    // Non-vacuity: a moved handler, or a renamed file, must fail loudly here
    // rather than pass by finding nothing to object to.
    expect(partPage).toMatch(/event\.key === "Escape"/);
    expect(partPage).toContain("store.escape()");

    // `escapeAction` maps state → verb; whoever calls it then owns a mapping
    // from that verb to an ACTION, and two such mappings can disagree. One
    // caller, one mapping. (Matching the CALL rather than the bare name is
    // deliberate — the handler's comment has to be able to name the function
    // it no longer calls, or the code cannot explain itself.)
    expect(partPage).not.toMatch(/\bescapeAction\s*\(/);
    const toolsImport =
      /import\s*\{([^}]*)\}\s*from\s*"\.\.\/sketch\/tools"/.exec(partPage);
    expect(toolsImport).not.toBeNull();
    expect(toolsImport?.[1]).not.toMatch(/escapeAction/);
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
    authorEqual(EDGE_RIGHT, EDGE_LEFT); // equal(e2, e4) — dangles when e2 goes
    authorEqual(EDGE_BOTTOM, EDGE_TOP); // equal(e1, e3) — survives
    // RECT-1 makes this a real number rather than 1: the DRAW already named e2
    // three times (its `vertical` and the two corner coincidences), so a
    // whole-curve trim must take those with it. Counting the doomed set from
    // the constraints themselves — rather than hard-coding 4 — is what makes
    // this an assertion about reconciliation instead of about arithmetic.
    const doomed = store().constraints.filter((c) =>
      constraintEntityRefs(c).includes("e2"),
    ).length;
    expect(doomed).toBe(4);

    store().requestEdit("trim", "e2", { x: 40, y: 12 });
    const revision = store().revision;
    const kept = store().entities.filter((e) => e.id !== "e2");
    store().applyEditResult("trim", kept);

    expect(store().entities.map((e) => e.id)).toEqual(["e1", "e3", "e4"]);
    // Every reference to the departed entity is gone…
    expect(
      store().constraints.some((c) => constraintEntityRefs(c).includes("e2")),
    ).toBe(false);
    // …and nothing that did NOT name it was collateral damage.
    expect(store().constraints).toContainEqual({
      kind: "equal",
      a: "e1",
      b: "e3",
    });
    expect(store().revision).toBe(revision + 1);
    expect(store().editBusy).toBe(false);
    expect(store().edit).toBeNull();
    expect(store().editNote).toMatch(/trimmed\. 4 constraints removed/i);
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
    expect(authored()).toEqual([]);
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
    authorEqual(EDGE_BOTTOM, EDGE_TOP);
    expect(authored()).toHaveLength(1);
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
    expect(authored()).toEqual([{ kind: "equal", a: "e1", b: "e3" }]);
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
    authorEqual(EDGE_BOTTOM, EDGE_TOP);
    expect(authored()).toHaveLength(1);

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
    // e1 and e3 kept their ids, so the constraint between them survives.
    expect(authored()).toEqual([{ kind: "equal", a: "e1", b: "e3" }]);
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

describe("snapping (UI-W5)", () => {
  const NONE = { suppressed: false, axisLock: false };
  /** A rectangle whose far corner is deliberately OFF the 1 mm grid, so an
   *  entity snap and a grid snap can never be mistaken for each other. */
  const offGridRect = () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("rect");
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 40.4, y: 25.4 });
    store().setTool("line");
  };

  beforeEach(() => {
    // Preferences survive `exit` by design, so reset them here explicitly.
    useSketchStore.setState({ snapEnabled: true, snapStepMm: 1 });
  });

  it("takes the entity snap over the grid and names what it took", () => {
    offGridRect();
    const store = useSketchStore.getState;
    const at = store().aim({ x: 40.3, y: 0.2 }, 1, NONE);
    expect(at).toEqual({ x: 40.4, y: 0 });
    expect(store().cursor).toEqual({ x: 40.4, y: 0 });
    expect(store().snapCandidate?.kind).toBe("endpoint");
  });

  it("suppresses every snap while Ctrl/Cmd is held", () => {
    offGridRect();
    const store = useSketchStore.getState;
    const raw = { x: 40.31, y: 0.22 };
    expect(store().aim(raw, 1, { suppressed: true, axisLock: false })).toEqual(
      raw,
    );
    expect(store().snapCandidate).toBeNull();
    expect(store().snapSuppressed).toBe(true);
  });

  it("re-resolves the live aim when a modifier is pressed WITHOUT moving", () => {
    offGridRect();
    const store = useSketchStore.getState;
    const raw = { x: 40.31, y: 0.22 };
    store().aim(raw, 1, NONE);
    expect(store().snapCandidate?.kind).toBe("endpoint");
    // No second aim() — the keyboard alone must make the mark honest again.
    store().setSnapModifiers({ suppressed: true, axisLock: false });
    expect(store().snapCandidate).toBeNull();
    expect(store().cursor).toEqual(raw);
    store().setSnapModifiers({ suppressed: false, axisLock: false });
    expect(store().snapCandidate?.kind).toBe("endpoint");
    expect(store().cursor).toEqual({ x: 40.4, y: 0 });
  });

  it("locks to an axis through the open placement's anchor under Shift", () => {
    offGridRect();
    const store = useSketchStore.getState;
    store().placeAt({ x: 5, y: 5 }); // the line's first point = the anchor
    const at = store().aim({ x: 30.4, y: 7 }, 1, {
      suppressed: false,
      axisLock: true,
    });
    expect(at).toEqual({ x: 30, y: 5 });
    expect(store().snapCandidate?.kind).toBe("axis-h");
  });

  it("honours a configured grid step, and G still toggles only the grid", () => {
    offGridRect();
    const store = useSketchStore.getState;
    store().setSnapStep(5);
    expect(store().aim({ x: 12.2, y: 18.1 }, 0.1, NONE)).toEqual({
      x: 10,
      y: 20,
    });
    store().toggleSnap(); // grid off
    expect(store().aim({ x: 12.2, y: 18.1 }, 0.1, NONE)).toEqual({
      x: 12.2,
      y: 18.1,
    });
    // …and the entity snap is untouched by G.
    expect(store().aim({ x: 40.3, y: 0.2 }, 1, NONE)).toEqual({
      x: 40.4,
      y: 0,
    });
  });

  it("rejects a non-positive grid step", () => {
    const store = useSketchStore.getState;
    store().setSnapStep(0);
    store().setSnapStep(Number.NaN);
    expect(store().snapStepMm).toBe(1);
  });

  it("does NOT entity-snap the pick-grain tools", () => {
    offGridRect();
    const store = useSketchStore.getState;
    store().setTool("select");
    expect(store().aim({ x: 40.3, y: 0.2 }, 1, NONE)).toEqual({ x: 40, y: 0 });
    expect(store().snapCandidate).toBeNull();
  });

  it("drops the mark when the pointer leaves the plane", () => {
    offGridRect();
    const store = useSketchStore.getState;
    store().aim({ x: 40.3, y: 0.2 }, 1, NONE);
    store().setCursor(null);
    expect(store().snapCandidate).toBeNull();
    expect(store().cursor).toBeNull();
  });

  it("keeps the snap PREFERENCES across exit (they are settings, not state)", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().setSnapStep(0.5);
    store().toggleSnap();
    store().exit();
    expect(store().snapStepMm).toBe(0.5);
    expect(store().snapEnabled).toBe(false);
    expect(store().entities).toEqual([]); // the session itself still resets
  });
});

/**
 * FB-16 — the size cells a shape offers while it is being drawn. The gesture
 * that opens them is the scene's (FB-15, press-drag-release or click-click);
 * both funnel through `placeAt`, so this is the one place the draft is born.
 */
describe("draw-time dimensions", () => {
  const drawRect = () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("rect");
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 43, y: 23 });
  };

  it("opens size cells on the shape a placement emitted", () => {
    drawRect();
    const store = useSketchStore.getState;
    expect(store().drawDimension).toMatchObject({
      shape: "rect",
      ids: ["e1", "e2", "e3", "e4"],
      from: { x: 0, y: 0 },
      to: { x: 43, y: 23 },
    });
    expect(store().drawDimension?.fields.map((f) => f.key)).toEqual([
      "width",
      "height",
    ]);
  });

  it("offers nothing for the tools a drag cannot finish", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("arc");
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 10, y: 0 });
    store().placeAt({ x: 0, y: 10 });
    expect(store().entities).toHaveLength(1);
    expect(store().drawDimension).toBeNull();
  });

  it("a typed size resizes the shape AND records a driving dimension", () => {
    drawRect();
    const store = useSketchStore.getState;
    const before = store().revision;
    store().commitDrawDimensions({ width: 50, height: 30 });
    expect(store().drawDimension).toBeNull();
    expect(store().revision).toBe(before + 1);
    const bottom = store().entities[0];
    expect(bottom?.kind === "line" && bottom.end).toEqual({ x: 50, y: 0 });
    // Rigidity first (the rectangle must stay a rectangle), then the two dims.
    expect(store().constraints).toHaveLength(10);
    expect(store().constraints.filter((c) => c.kind === "distance")).toEqual([
      { kind: "distance", entity: "e1", value_mm: 50 },
      { kind: "distance", entity: "e2", value_mm: 30 },
    ]);
  });

  it("typing ONE size leaves the other free but still rigid", () => {
    drawRect();
    const store = useSketchStore.getState;
    store().commitDrawDimensions({ width: 50 });
    expect(store().constraints.filter((c) => c.kind === "distance")).toEqual([
      { kind: "distance", entity: "e1", value_mm: 50 },
    ]);
    const right = store().entities[1];
    // Height untouched by the width edit.
    expect(right?.kind === "line" && right.start).toEqual({ x: 50, y: 0 });
    expect(right?.kind === "line" && right.end).toEqual({ x: 50, y: 23 });
  });

  it("a drag with nothing typed leaves an undimensioned shape, not a refusal", () => {
    drawRect();
    const store = useSketchStore.getState;
    const before = store().revision;
    store().commitDrawDimensions({});
    expect(store().drawDimension).toBeNull();
    expect(store().entities).toHaveLength(4); // still drawn
    // RECT-1 — "undimensioned" is not "unconstrained". The draw itself made
    // this a rectangle (4 coincidences + 2 H + 2 V), so it is a CLOSED profile
    // free to translate and resize; it used to be four disconnected lines that
    // tore apart the moment anyone dimensioned one edge. What must still be
    // absent is a DIMENSION: nothing was typed, so nothing was measured.
    expect(store().constraints).toHaveLength(RECT_RIGIDITY);
    expect(
      store().constraints.filter(
        (c) => c.kind === "distance" || c.kind === "radius",
      ),
    ).toEqual([]);
    expect(store().revision).toBe(before); // nothing further to save
  });

  it("rejects a zero or negative size rather than authoring it", () => {
    drawRect();
    const store = useSketchStore.getState;
    store().commitDrawDimensions({ width: 0, height: -5 });
    // The rigidity set is the draw's and stays; the rejected sizes author no
    // dimension on top of it.
    expect(store().constraints).toHaveLength(RECT_RIGIDITY);
    expect(store().constraints.filter((c) => c.kind === "distance")).toEqual(
      [],
    );
  });

  it("Escape keeps the shape, drops the cells, and drops the tool in one go", () => {
    drawRect();
    const store = useSketchStore.getState;
    store().escape();
    expect(store().drawDimension).toBeNull();
    expect(store().entities).toHaveLength(4);
    expect(store().tool).toBe("select");
  });

  it("a new placement supersedes the last shape's cells", () => {
    drawRect();
    const store = useSketchStore.getState;
    store().placeAt({ x: 60, y: 0 }); // first corner of the next rectangle
    expect(store().drawDimension).toBeNull();
    store().placeAt({ x: 70, y: 10 });
    expect(store().drawDimension?.ids).toEqual(["e5", "e6", "e7", "e8"]);
  });

  it("changing tool dismisses the cells", () => {
    drawRect();
    const store = useSketchStore.getState;
    store().focusDrawDimension("width");
    store().setTool("select");
    expect(store().drawDimension).toBeNull();
    expect(store().drawDimensionFocus).toBeNull();
  });

  it("dimensions a circle by radius", () => {
    const store = useSketchStore.getState;
    store().begin();
    store().choosePlane("XY");
    store().setTool("circle");
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 5, y: 0 });
    store().commitDrawDimensions({ radius: 12 });
    const circle = store().entities[0];
    expect(circle?.kind === "circle" && circle.radius).toBe(12);
    expect(store().constraints).toEqual([
      { kind: "radius", entity: "e1", value_mm: 12 },
    ]);
  });
});

describe("sketch-local history (founder, 2026-08-02: no undo/redo in the sketcher)", () => {
  const store = useSketchStore.getState;

  it("undoes the last DRAWN shape and redoes it, without touching the plane", () => {
    rectangleAt(); // 4 lines, one placement batch
    store().setTool("circle");
    store().placeAt({ x: 60, y: 0 });
    store().placeAt({ x: 65, y: 0 });
    expect(store().entities).toHaveLength(5);

    store().undo();
    expect(store().entities).toHaveLength(4);
    expect(store().entities.every((e) => e.kind === "line")).toBe(true);
    // The sketch itself survives: undo reverses an EDIT, not the session.
    expect(store().mode).toBe("draw");
    expect(store().plane).toEqual({ kind: "origin", base: "XY" });

    store().redo();
    expect(store().entities).toHaveLength(5);
    expect(store().entities[4]?.kind).toBe("circle");
  });

  it("restores the id counter, so a redrawn entity cannot collide", () => {
    rectangleAt();
    const before = store().nextIdIndex;
    store().setTool("circle");
    store().placeAt({ x: 60, y: 0 });
    store().placeAt({ x: 65, y: 0 });
    expect(store().nextIdIndex).toBeGreaterThan(before);
    store().undo();
    expect(store().nextIdIndex).toBe(before);
  });

  it("undoes a CONSTRAINT — a sketch edit is not only geometry", () => {
    rectangleAt();
    authorEqual(EDGE_BOTTOM, EDGE_TOP);
    expect(authored()).toHaveLength(1);
    store().undo();
    expect(authored()).toHaveLength(0);
    store().redo();
    expect(authored()).toHaveLength(1);
  });

  it("re-solves and re-saves: every step bumps the revision the sync loop watches", () => {
    // Undo is not a local rewind the server never hears about. If this ever
    // stops bumping, a bound sketch would show the undone state and persist the
    // undone-away one.
    rectangleAt();
    const drawn = store().revision;
    store().undo();
    expect(store().revision).toBe(drawn + 1);
    store().redo();
    expect(store().revision).toBe(drawn + 2);
  });

  it("is empty at the top and the bottom of the stack — the buttons' honest gates", () => {
    store().begin();
    store().choosePlane("XY");
    expect(store().past).toHaveLength(0); // "Nothing drawn yet"
    expect(store().future).toHaveLength(0);
    rectangleAt();
    expect(store().past).toHaveLength(1);
    store().undo();
    expect(store().past).toHaveLength(0);
    expect(store().future).toHaveLength(1);
    // A no-op at the floor, not a throw and not a wrap-around.
    store().undo();
    expect(store().entities).toHaveLength(0);
    expect(store().future).toHaveLength(1);
  });

  it("forks the timeline: drawing after an undo drops the redo", () => {
    rectangleAt();
    store().undo();
    expect(store().future).toHaveLength(1);
    store().setTool("circle");
    store().placeAt({ x: 0, y: 0 });
    store().placeAt({ x: 5, y: 0 });
    expect(store().future).toHaveLength(0);
  });

  it("never records a transient: tool, selection, cursor and solved geometry", () => {
    rectangleAt();
    const depth = store().past.length;
    store().setTool("line");
    store().selectAt({ x: 20, y: 0 }, 2);
    store().aim({ x: 3, y: 3 }, 1, { suppressed: false, axisLock: false });
    store().adoptSolved(
      store().entities.map((e) => ({ ...e })),
      { status: "converged", dof: 0, conflicting: [], redundant: [] },
    );
    expect(store().past).toHaveLength(depth);
  });

  it("holds while a geometry edit is in flight — the result must land on what it saw", () => {
    rectangleAt();
    store().setTool("trim");
    store().requestEdit("trim", "e1", { x: 20, y: 0 });
    expect(store().editBusy).toBe(true);
    const entities = store().entities.length;
    store().undo();
    expect(store().entities).toHaveLength(entities);
  });

  it("starts a fresh sketch with an EMPTY stack — no reaching into the last session", () => {
    rectangleAt();
    expect(store().past.length).toBeGreaterThan(0);
    store().exit();
    expect(store().past).toHaveLength(0);
    expect(store().future).toHaveLength(0);
    store().begin();
    store().choosePlane("XY");
    store().undo();
    expect(store().entities).toHaveLength(0);
  });

  it("hands back the drafts that pointed at what it replaced", () => {
    rectangleAt();
    store().setTool("rect");
    store().placeAt({ x: 60, y: 0 });
    store().placeAt({ x: 80, y: 20 });
    // The just-drawn shape's size cells are open and name those entity ids.
    expect(store().drawDimension).not.toBeNull();
    store().undo();
    expect(store().drawDimension).toBeNull();
    expect(store().pending).toEqual([]);
    expect(store().selection).toEqual([]);
  });
});

describe("beginEdit — re-opening a SAVED sketch (SKETCH-1)", () => {
  const store = useSketchStore.getState;
  const PERSISTED: SketchEntity[] = [
    {
      id: "e1",
      kind: "line",
      start: { x: 0, y: 0 },
      end: { x: 20, y: 0 },
      construction: false,
    },
    {
      id: "e2",
      kind: "line",
      start: { x: 20, y: 0 },
      end: { x: 20, y: 20 },
      construction: false,
    },
  ];
  const CONSTRAINTS = [
    { kind: "horizontal", entity: "e1" },
    { kind: "distance", entity: "e1", value_mm: 20 },
  ] as const;

  it("hydrates the persisted session and skips the plane-pick step", () => {
    store().beginEdit(
      "feat-sketch-1",
      { kind: "origin", base: "XZ" },
      PERSISTED,
      CONSTRAINTS,
    );
    expect(store().mode).toBe("draw"); // NOT "plane": the plane is already fixed
    expect(store().plane).toEqual({ kind: "origin", base: "XZ" });
    expect(store().entities).toEqual(PERSISTED);
    expect(store().constraints).toEqual([...CONSTRAINTS]);
    // The EXISTING id: this is what makes the next save a PATCH, not a create.
    expect(store().featureId).toBe("feat-sketch-1");
    // A loaded buffer is not an edit — nothing to save until the user acts.
    expect(store().revision).toBe(0);
  });

  it("resumes the id counter ABOVE the loaded entities (never re-mints e1)", () => {
    store().beginEdit(
      "feat-sketch-1",
      { kind: "origin", base: "XY" },
      PERSISTED,
      [],
    );
    store().setTool("line");
    store().placeAt({ x: 0, y: 40 });
    store().placeAt({ x: 10, y: 40 });
    const ids = store().entities.map((e) => e.id);
    expect(ids).toEqual(["e1", "e2", "e3"]);
    expect(new Set(ids).size).toBe(ids.length); // no id addresses two entities
  });

  it("takes the HIGHEST index numerically, not lexicographically", () => {
    store().beginEdit(
      "feat-sketch-1",
      { kind: "origin", base: "XY" },
      [
        {
          id: "e9",
          kind: "circle",
          center: { x: 0, y: 0 },
          radius: 5,
          construction: false,
        },
        {
          id: "e10",
          kind: "circle",
          center: { x: 30, y: 0 },
          radius: 5,
          construction: false,
        },
      ],
      [],
    );
    expect(store().nextIdIndex).toBe(11); // not 10 ("e9" > "e10" as strings)
  });

  it("replaces the previous session rather than merging into it", () => {
    rectangleAt(); // four entities of an unrelated, unsaved sketch
    expect(store().entities).toHaveLength(4);
    store().beginEdit(
      "feat-sketch-1",
      { kind: "origin", base: "XY" },
      PERSISTED,
      CONSTRAINTS,
    );
    expect(store().entities).toEqual(PERSISTED);
    // …and its history: undo must not reach back into the abandoned session.
    expect(store().past).toHaveLength(0);
    expect(store().future).toHaveLength(0);
    store().undo();
    expect(store().entities).toEqual(PERSISTED);
  });

  it("keeps the snap preferences the user chose", () => {
    store().toggleSnap();
    store().setSnapStep(0.5);
    const snapEnabled = store().snapEnabled;
    store().beginEdit(
      "feat-sketch-1",
      { kind: "origin", base: "XY" },
      PERSISTED,
      [],
    );
    expect(store().snapEnabled).toBe(snapEnabled);
    expect(store().snapStepMm).toBe(0.5);
  });
});

describe("a snap authors the constraint it meant (SNAP-3, and SNAP-2 with it)", () => {
  const store = useSketchStore.getState;
  const NONE = { suppressed: false, axisLock: false };

  /** Aim at `point`, then place whatever the aim resolved to — the real path:
   *  `SketchScene` only ever calls `placeAt(aim(...))`. */
  const aimAndPlace = (x: number, y: number, toleranceMm = 1) =>
    store().placeAt(store().aim({ x, y }, toleranceMm, NONE));

  const draw = (tool: "line" | "rect" | "circle") => {
    store().begin();
    store().choosePlane("XY");
    store().setTool(tool);
  };

  const coincidents = () =>
    store().constraints.filter((c) => c.kind === "coincident");

  /**
   * The coincidents that NAME `id` — how an inferred one is told apart from a
   * shape's own rigidity set now that RECT-1 gives every drawn rectangle four
   * corner coincidences of its own. An inferred coincident always reaches
   * OUTSIDE the shape just drawn (to the origin, or to an earlier entity),
   * which is exactly what makes this filter the right question rather than a
   * way of getting the number down: a rigidity coincident can only ever name
   * two lines of the same new rectangle.
   */
  const coincidentsNaming = (id: string) =>
    store().constraints.filter(
      (c) =>
        c.kind === "coincident" && (c.a.entity === id || c.b.entity === id),
    );

  beforeEach(() => {
    useSketchStore.setState({ snapEnabled: true, snapStepMm: 1 });
  });

  /** e1 = (10,10) -> (50,10). Deliberately clear of the datum frame: an aim on
   *  the origin or along an axis is its OWN case below, and stacking the two
   *  would make every assertion here ambiguous about which snap it measured. */
  const firstLine = () => {
    draw("line");
    aimAndPlace(10, 10);
    aimAndPlace(50, 10);
  };

  it("joins a corner drawn onto an existing endpoint", () => {
    firstLine();
    // The second line STARTS on e1's end — aimed a fraction off, so only the
    // snap can land it exactly, which is the gesture the ticket describes.
    aimAndPlace(50.3, 10.2);
    aimAndPlace(50, 40); // e2
    expect(store().entities.map((e) => e.id)).toEqual(["e1", "e2"]);
    expect(coincidents()).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "start" },
        b: { entity: "e1", point: "end" },
      },
    ]);
  });

  it("grounds a corner snapped to the origin, and PINS the origin (SNAP-2)", () => {
    draw("rect");
    aimAndPlace(0.3, -0.2); // the origin magnet
    aimAndPlace(40, 25);
    // The datum is materialised on demand, exactly as the explicit verb does.
    expect(store().entities.map((e) => e.id)).toContain("origin");
    expect(coincidentsNaming("origin")).toEqual([
      {
        kind: "coincident",
        a: { entity: "e1", point: "start" },
        b: { entity: "origin", point: "position" },
      },
    ]);
    // Without the pin the coincident is satisfiable by moving the ORIGIN.
    expect(
      store().constraints.some(
        (c) => c.kind === "fixed" && c.point.entity === "origin",
      ),
    ).toBe(true);
  });

  it("binds a shared rectangle corner ONCE — the over-constraint guard", () => {
    // The corner belongs to two of the four lines, and since RECT-1 those two
    // are ALREADY tied to each other by the rectangle's own rigidity set.
    // Grounding both of them would therefore state the same fact three times
    // and report an ordinary rectangle as over-constrained — a worse defect
    // than the one being fixed.
    draw("rect");
    aimAndPlace(0.3, -0.2);
    aimAndPlace(40, 25);
    expect(coincidentsNaming("origin")).toHaveLength(1);
    // The positive control for that number: the rigidity set really is there,
    // so "1" is not "the rectangle authored nothing".
    expect(coincidents().length).toBeGreaterThan(1);
  });

  it("authors NOTHING when the aim took the grid or a free point", () => {
    // The negative control for the whole feature: an ordinary draw with no
    // snap must cost the sketch exactly as many constraints as it did before.
    draw("line");
    store().setSnapStep(1);
    aimAndPlace(5, 5);
    aimAndPlace(25, 17);
    expect(store().entities).toHaveLength(1);
    expect(store().constraints).toEqual([]);

    // …and with the snap SUPPRESSED over a live endpoint, still nothing.
    store().setTool("line");
    const held = { suppressed: true, axisLock: false };
    store().placeAt(store().aim({ x: 25.02, y: 17.03 }, 1, held));
    store().placeAt(store().aim({ x: 60.4, y: 3.1 }, 1, held));
    expect(store().entities).toHaveLength(2);
    expect(store().constraints).toEqual([]);
  });

  it("authors nothing for a snap to an AXIS — point-on-object is not expressible", () => {
    draw("line");
    aimAndPlace(25.3, 0.2); // x-axis
    aimAndPlace(40, 30);
    expect(store().entities).toHaveLength(1);
    expect(store().constraints).toEqual([]);
  });

  it("does not bank an anchor from a REJECTED placement", () => {
    // A zero-height rectangle is refused. If that click still banked its snap,
    // the intent would be cashed in by whatever the user drew next.
    firstLine();
    store().setTool("rect");
    aimAndPlace(50.3, 10.2); // snapped to e1's end — first corner
    aimAndPlace(80, 10.1); // snapped BACK onto y=10: zero height, rejected
    expect(store().entities).toHaveLength(1); // nothing emitted
    aimAndPlace(80, 40); // now a real second corner
    expect(store().entities).toHaveLength(5);
    // Exactly the FIRST corner's intent, and nothing from the refused click.
    // Filtered to constraints reaching back to e1: the rectangle's own rigidity
    // set names only e2..e5, so anything here came from a banked snap.
    expect(coincidentsNaming("e1")).toEqual([
      {
        kind: "coincident",
        a: { entity: "e2", point: "start" },
        b: { entity: "e1", point: "end" },
      },
    ]);
  });

  it("drops the collected intents when the placement is cancelled", () => {
    firstLine();
    aimAndPlace(50.3, 10.2); // a snapped first point…
    store().escape(); // …abandoned
    expect(store().pending).toHaveLength(0);
    store().setTool("line");
    // Ctrl held: the aim takes the raw point and banks NO intent of its own —
    // yet it starts at exactly the coordinate the abandoned one held, so a
    // stale anchor would still match it and author a relation nobody asked
    // for. Nothing here can produce a constraint except the leak.
    const held = { suppressed: true, axisLock: false };
    store().placeAt(store().aim({ x: 50, y: 10 }, 1, held));
    store().placeAt(store().aim({ x: 80, y: 19 }, 1, held));
    expect(store().entities).toHaveLength(2);
    expect(store().constraints).toEqual([]);
  });

  it("leaves `userConstrained` false — an inferred relation must not bind", () => {
    // Binding starts the live save loop and retires the unsaved-work exit
    // confirm. A corner that happened to snap is not the user asking for that.
    firstLine();
    aimAndPlace(50.3, 10.2);
    aimAndPlace(50, 40);
    expect(coincidents()).toHaveLength(1);
    expect(store().userConstrained).toBe(false);

    // A verb the user pressed DOES bind.
    store().setTool("select");
    store().selectAt({ x: 30, y: 10 }, 2);
    store().applyConstraint("horizontal");
    expect(store().userConstrained).toBe(true);
  });

  it("never restates a relation the explicit verb already authored", () => {
    firstLine();
    aimAndPlace(50.3, 10.2);
    aimAndPlace(50, 40); // e2, auto-joined to e1's end
    expect(coincidents()).toHaveLength(1);
    // Ask for the same relation by hand: the verb refuses as already applied.
    store().setTool("select");
    store().selectAt({ x: 50, y: 10 }, 0.5);
    store().selectAt({ x: 50, y: 10 }, 0.5, "add");
    store().applyConstraint("coincident");
    expect(coincidents()).toHaveLength(1);
  });

  it("undo takes the inferred constraint back with its geometry", () => {
    firstLine();
    aimAndPlace(50.3, 10.2);
    aimAndPlace(50, 40);
    expect(coincidents()).toHaveLength(1);
    store().undo();
    expect(store().entities).toHaveLength(1);
    expect(coincidents()).toHaveLength(0);
    store().redo();
    expect(coincidents()).toHaveLength(1);
  });
});
