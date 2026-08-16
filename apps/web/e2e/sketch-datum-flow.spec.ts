import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * SKETCH-2, SECOND PASS — the frame must never lead anywhere the user cannot
 * walk out of.
 *
 * `5ceed6e` made the origin and axes selectable. An independent review then
 * found the feature's own RECOMMENDED verb dead-ends, plus three quieter costs
 * of putting invisible geometry under the whole sheet. Every test here is one
 * of those, driven the way a person drives it — pointer, keyboard, readouts —
 * against the real solver.
 *
 * ## 1. The blocking one: symmetric about a datum axis
 *
 * The frame refuses to be the SUBJECT of a verb and says so by name:
 * *"The origin and axes are fixed — constrain TO them (coincident, symmetric,
 * parallel, perpendicular)."* Take it at its word on a floating rectangle and
 * the sketch came back:
 *
 *     DIAGNOSTIC: "OVER-CONSTRAINED — A redundant constraint is flagged in the
 *                  sketch. Remove it — the geometry is already determined
 *                  without it."
 *     GLYPHS: 9      FLAGGED GLYPHS: 0
 *
 * The geometry was CORRECT. The redundant constraint the banner meant was one
 * of the axis's own pins — glyph-suppressed by design, so it could not be seen,
 * selected or deleted, and `removeConstraint` is only reachable through a
 * glyph. Isolated against the real solver: unpinned centreline ->
 * underconstrained; ONE pin -> underconstrained; BOTH pins -> overconstrained,
 * redundant = the second pin. Pinning both ends is right (a line fixed at one
 * end still swings), so the REPORT was the defect.
 *
 * This file's first test is that walk, and its assertions are the two halves
 * that made it a dead end: no banner, and — the guard against fixing it by
 * blinding the banner — a GENUINE over-constraint on the very same sketch still
 * stops the user and still flags a glyph they can click.
 *
 * ## 2..4. The three the review measured against `ce40e44`
 *
 * The axes are an invisible cross spanning the viewport of which only +/-8 px
 * is ink, so anything that treats "the pointer is over a datum" as intent has a
 * very large false-positive area: a modifier UN-pick became an append, and a
 * plain click on empty steel stopped clearing. Plus two readouts that counted
 * or lit for geometry nobody drew.
 */

interface Point {
  x: number;
  y: number;
}

type Mapper = (pt: Point) => Point;

interface SketchEntityRow {
  id: string;
  kind: string;
  start?: Point;
  end?: Point;
}

/**
 * A 24 x 16 rectangle at (10,8), RIGID IN SHAPE and floating in position:
 * corners tied and both pairs of edges axis-aligned, so the profile can only
 * translate. Eight authored constraints, so the strip reads "8 applied" before
 * anything here touches it and "9 applied" after the symmetric.
 *
 * The rigidity is load-bearing, not decoration, and getting it wrong is how
 * this file nearly shipped as a gate that could not fail. The FIRST fixture
 * written here used two driven dimensions instead of the second H/V pair; the
 * solver answers `underconstrained, redundant=[]` for that one, so the "no
 * banner" assertions all passed against a sketch that never produced a banner
 * in the first place. Measured, and the four rows are why this shape:
 *
 *     rigid + symmetric + BOTH pins   -> overconstrained  dof 3  redundant [10]
 *     rigid + symmetric + ONE pin     -> underconstrained dof 4  redundant []
 *     the loose fixture, both pins    -> underconstrained dof 2  redundant []
 *     rigid + symmetric + parallel    -> overconstrained  dof 3  redundant [10, 11]
 *
 * Row 1 is the defect. Row 4 is the guard: a pin and a USER constraint flagged
 * together, which is what proves the filter drops the unreachable one and keeps
 * the one with a glyph on it.
 */
const RIGID_RECT = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 10, y: 8 }, end: { x: 34, y: 8 } },
    { id: "e2", kind: "line", start: { x: 34, y: 8 }, end: { x: 34, y: 24 } },
    { id: "e3", kind: "line", start: { x: 34, y: 24 }, end: { x: 10, y: 24 } },
    { id: "e4", kind: "line", start: { x: 10, y: 24 }, end: { x: 10, y: 8 } },
  ],
  constraints: [
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e3", point: "end" },
      b: { entity: "e4", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e4", point: "end" },
      b: { entity: "e1", point: "start" },
    },
    { kind: "horizontal", entity: "e1" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e2" },
    { kind: "vertical", entity: "e4" },
  ],
};

/** A line lying exactly ALONG the X axis — the un-pick case, drawn as data. */
const LINE_ON_AXIS = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 8, y: 0 }, end: { x: 44, y: 0 } },
  ],
  constraints: [{ kind: "horizontal", entity: "e1" }],
};

/**
 * Plane-mm -> screen-px, read off the DRO with the grid OFF so the two
 * calibration samples are raw. Same shape as the sibling spec's; kept local
 * because that file is another agent's this batch.
 */
async function calibratePlane(
  page: Page,
  s1: Point,
  s2: Point,
): Promise<Mapper> {
  await page.keyboard.press("g");
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<Point> => {
    await page.mouse.move(sx + 2, sy);
    await page.mouse.move(sx, sy);
    await expect
      .poll(
        async () => {
          const value = Number.parseFloat(
            await page.getByTestId("dro-x").innerText(),
          );
          return (
            Number.isFinite(value) &&
            (distinctFromX === undefined ||
              Math.abs(value - distinctFromX) > 1e-9)
          );
        },
        { timeout: 15_000 },
      )
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  await page.keyboard.press("g");
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

/**
 * Somewhere with nothing drawn AND nothing of the frame — the park that makes a
 * stale readout visible. Deliberately OFF both axes: the whole point of test 3
 * is that a point off the geometry but ON an axis behaves differently, so the
 * park must not be one.
 */
const EMPTY_STEEL: Point = { x: 46, y: -22 };

/** Park on empty steel, wait for "nothing selected", then click and wait. */
async function selectAndRead(
  page: Page,
  at: Mapper,
  screen: Point,
  expected: string | RegExp,
): Promise<void> {
  const empty = at(EMPTY_STEEL);
  await page.mouse.click(empty.x, empty.y);
  await expect(page.getByTestId("selection-readout")).toContainText(
    "nothing selected",
  );
  await page.mouse.click(screen.x, screen.y);
  await expect(page.getByTestId("selection-readout")).toContainText(expected);
}

/** One Shift-click, with the modifier held around it. */
async function shiftClick(page: Page, screen: Point): Promise<void> {
  await page.keyboard.down("Shift");
  await page.mouse.click(screen.x, screen.y);
  await page.keyboard.up("Shift");
}

/** The SOLVED entities — the solver's output, not the authored definition. */
async function solvedSketch(
  page: Page,
  token: string,
  partId: string,
): Promise<SketchEntityRow[]> {
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(`e2e evaluate failed: ${response.status()}`);
  }
  const body = (await response.json()) as {
    features: { data?: { kind: string; entities: SketchEntityRow[] } | null }[];
  };
  const solved = body.features.find(
    (row) => row.data?.kind === "solved_sketch",
  );
  if (solved?.data === undefined || solved.data === null) {
    throw new Error("the evaluate carried no solved sketch");
  }
  return solved.data.entities;
}

async function seedSketch(
  page: Page,
  token: string,
  partId: string,
  params: unknown,
): Promise<void> {
  await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params },
    expected_tree_version: 0,
  });
}

async function openPartAndSketch(page: Page, partId: string): Promise<Mapper> {
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page.getByTestId("feature-row").first().click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-strip")).toBeVisible();
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
  return calibratePlane(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
}

test.describe("SKETCH-2 — the frame never leads anywhere you cannot leave", () => {
  test("symmetric about a datum axis solves and says so — no banner pointing at a pin", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Symmetric plate");
    await seedSketch(page, token, part.id, RIGID_RECT);
    const at = await openPartAndSketch(page, part.id);

    // The state before the verb, asserted rather than assumed: four degrees of
    // freedom (x, y, width, height) in a rigid rectangle that floats.
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 4 · UNDER-CONSTRAINED",
      { timeout: 30_000 },
    );

    // Two corners of the left edge, then the X axis they should mirror about.
    await selectAndRead(page, at, at({ x: 10, y: 8 }), "1 pt");
    await shiftClick(page, at({ x: 10, y: 24 }));
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await shiftClick(page, at({ x: -26, y: 0 })); // the X axis, clear of the rect
    await expect(page.getByTestId("selection-readout")).toContainText(
      "1 ent · 2 pts",
    );
    await page.keyboard.press("s"); // symmetric

    await expect(page.getByTestId("sketch-strip")).toContainText("9 applied");

    // WAIT FOR THE NEW SOLVE BY ITS CONTENT, not by the absence of a banner.
    // The first draft of this test asserted the absences below directly and
    // PASSED with the fix reverted, because the solve is a debounced round trip
    // and nothing had come back yet: it was measuring the gap between the
    // keystroke and the answer. `DOF 3` is the answer, and it is the number the
    // defect never produced — it read OVER-CONSTRAINED instead.
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 3 · UNDER-CONSTRAINED",
      { timeout: 30_000 },
    );

    // THE DEFECT: a banner naming a redundant constraint with nothing flagged.
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
    await expect(page.locator("[data-flagged]")).toHaveCount(0);
    // The count is the positive control: the glyphs ARE rendered (so "0
    // flagged" is not "0 glyphs"), and the frame's two pins are not among them.
    await expect(page.getByTestId(/^glyph-/)).toHaveCount(9);

    // …and the geometry the banner was slandering: the profile centres on the
    // axis. Read from the solver, not from pixels — and POLLED, because the
    // sketcher persists on a debounce and an evaluate fired too early answers
    // for the sketch as it was seeded.
    await expect
      .poll(
        async () => {
          const left = (await solvedSketch(page, token, part.id)).find(
            (e) => e.id === "e4",
          );
          return [left?.start?.y ?? NaN, left?.end?.y ?? NaN];
        },
        { timeout: 30_000 },
      )
      .toEqual([expect.closeTo(8, 3), expect.closeTo(-8, 3)]);
  });

  test("a GENUINE over-constraint on that same sketch still stops the user", async ({
    page,
  }) => {
    // The guard on the test above. Fixing the banner by blinding it would pass
    // that test and lose the product, so this walks the user on into a real
    // redundancy and demands the banner back, with a glyph they can click.
    //
    // The redundancy is `parallel` between two edges that are both already
    // horizontal. Measured on this exact sketch: `redundant = [10, 11]` — the
    // datum pin AND the parallel, flagged together. That pairing is the whole
    // point: the filter has to drop 10 and keep 11.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Redundant parallel");
    await seedSketch(page, token, part.id, RIGID_RECT);
    const at = await openPartAndSketch(page, part.id);

    await selectAndRead(page, at, at({ x: 10, y: 8 }), "1 pt");
    await shiftClick(page, at({ x: 10, y: 24 }));
    await shiftClick(page, at({ x: -26, y: 0 }));
    await page.keyboard.press("s");
    await expect(page.getByTestId("sketch-strip")).toContainText("9 applied");

    // Now the user's own redundancy, on top of the pinned frame.
    await selectAndRead(page, at, at({ x: 22, y: 8 }), "1 ent"); // the bottom edge
    await shiftClick(page, at({ x: 22, y: 24 })); // …and the top one
    await expect(page.getByTestId("selection-readout")).toContainText("2 ents");
    await page.keyboard.press("p"); // parallel
    await expect(page.getByTestId("sketch-strip")).toContainText("10 applied");

    await expect(page.getByTestId("solve-diagnostic")).toContainText(
      "Over-constrained",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toContainText(
      "flagged in the sketch",
    );
    // The exit is reachable: at least one flagged glyph, and it is one of the
    // user's own — never a pin, which would have no glyph to flag.
    const flagged = page.locator("[data-flagged]");
    await expect(flagged.first()).toBeVisible();
    await expect(flagged.first()).toHaveAttribute("data-testid", /^glyph-/);
  });

  test("two Shift-clicks on a line lying along the axis un-pick it", async ({
    page,
  }) => {
    // `toggleSelection`'s documented grain: the same modifier click twice
    // returns you to where you started. With the axis appended to the
    // candidates it went [e1] -> [e1, x-axis] instead, so the frame joined a
    // multi-select the user never asked for and the next verb refused with
    // "The origin and axes are fixed".
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Line on the axis");
    await seedSketch(page, token, part.id, LINE_ON_AXIS);
    const at = await openPartAndSketch(page, part.id);

    const onLine = at({ x: 26, y: 0 });
    await selectAndRead(page, at, onLine, "1 ent");
    await shiftClick(page, onLine);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await expect(page.getByTestId("sketch-axis-x")).toHaveAttribute(
      "data-pick-state",
      "idle",
    );
  });

  test("a plain click on empty steel along an axis drops the selection", async ({
    page,
  }) => {
    // "Click away to deselect" is a constant gesture and the axes are an
    // invisible viewport-wide cross, so this was a large area in which it
    // silently stopped working — and stopped working by selecting something.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Click away");
    await seedSketch(page, token, part.id, RIGID_RECT);
    const at = await openPartAndSketch(page, part.id);

    await selectAndRead(page, at, at({ x: 22, y: 8 }), "1 ent");
    await page.mouse.click(at({ x: -26, y: 0 }).x, at({ x: -26, y: 0 }).y);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await expect(page.getByTestId("sketch-axis-x")).toHaveAttribute(
      "data-pick-state",
      "idle",
    );

    // With nothing held there is nothing to drop, so the same click still
    // SELECTS the axis — this is a deselect rule, not a retreat from SKETCH-2.
    await page.mouse.click(at({ x: -26, y: 0 }).x, at({ x: -26, y: 0 }).y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await expect(page.getByTestId("sketch-axis-x")).toHaveAttribute(
      "data-pick-state",
      "selected",
    );
  });

  test("the frame is in neither the entity count nor the construction toggle", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Counting");
    await seedSketch(page, token, part.id, RIGID_RECT);
    const at = await openPartAndSketch(page, part.id);

    // A datum selection must not light the construction chip: an unmaterialised
    // axis matches no entity, and "every entity in an empty list is
    // construction" is true, so the chip read pressed and then declined.
    await selectAndRead(page, at, at({ x: -26, y: 0 }), "1 ent");
    await expect(page.getByTestId("sketch-construction")).not.toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.keyboard.press("n");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "Select an entity",
    );

    // …and the constraint count still excludes the frame's pins after
    // grounding: one coincident the user made, not three constraints.
    await selectAndRead(page, at, at({ x: 10, y: 8 }), "1 pt");
    await page.getByTestId("sketch-origin").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c"); // coincident
    await expect(page.getByTestId("sketch-strip")).toContainText("9 applied");
    await expect
      .poll(
        async () =>
          (await solvedSketch(page, token, part.id)).some(
            (e) => e.id === "origin",
          ),
        { timeout: 30_000 },
      )
      .toBe(true);
  });

  test("the entity count is of what was DRAWN, once the frame is materialised", async ({
    page,
  }) => {
    // The count only shows on an UNSAVED sketch (a bound one reads "edits save
    // live"), so this one is drawn rather than seeded — which is also the state
    // the number matters most in, because it is the number the discard confirm
    // offers to destroy.
    //
    // SCOPE, disclosed rather than papered over: the assertions stop at the
    // DRAWN state and do not re-read the caption after grounding, and that is a
    // property of the product, not an oversight. Authoring the coincident takes
    // the buffer's constraint count above zero, which is the condition
    // `PartPage`'s debounced persist waits for, so the sketch BINDS a moment
    // later and the caption becomes "edits save live" — an assertion after the
    // grounding is racing that debounce and was measured flaking 2 runs in 5.
    // The half this cannot reach — that the count still reads four once the
    // frame IS in the buffer — is covered deterministically by the unit test in
    // `components/SketchStrip.test.tsx`, which grounds through the real store
    // and reads "5 entities" with the fix reverted.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Drawn and grounded");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // Drawn FROM the origin, so its near corner is snapped to zero — the state
    // the grounding gesture below is for (snapped is not constrained).
    await page.keyboard.press("r"); // rectangle
    await page.mouse.click(at({ x: 0, y: 0 }).x, at({ x: 0, y: 0 }).y);
    await page.mouse.click(at({ x: 24, y: 16 }).x, at({ x: 24, y: 16 }).y);
    await page.keyboard.press("Escape"); // end the command, keep the shape
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.getByTestId("sketch-exit").click();
    await expect(page.getByTestId("sketch-discard-confirm")).toHaveAttribute(
      "aria-label",
      "Discard 4 unsaved entities — this cannot be undone",
    );
    await page.getByTestId("sketch-discard-cancel").click();

    // THE ADVERTISED GESTURE, which is what the frame was made selectable for
    // and which did not work: ground the corner the rectangle was snapped to
    // zero on, by POINTER, with the modifier. Two clicks at the same spot —
    // the drawn endpoint, then the origin under it. Appended last, the origin
    // sat behind both drawn picks and took FOUR clicks to reach, arriving with
    // entities in the selection so `coincident` refused; the keyboard handle
    // was the only route that worked.
    await page.keyboard.press("Escape"); // drop the tool back to select
    const corner = at({ x: 0, y: 0 });
    await selectAndRead(page, at, corner, "1 pt");
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-pick-state",
      "idle", // a PLAIN click takes drawn geometry; the frame is not offered
    );
    await shiftClick(page, corner);
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    // WHICH two points is the whole assertion. "2 pts" alone is satisfied by
    // the corner's two stacked endpoints, which are already coincident with
    // each other — the constraint would be accepted and would ground the corner
    // to ITSELF. Only the frame's own state distinguishes the two.
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-pick-state",
      "selected",
    );
    await page.keyboard.press("c"); // coincident — accepted, not refused
    await expect(page.getByTestId("sketch-strip")).toContainText("1 applied");
    await expect(page.getByTestId("constraint-hint")).toHaveCount(0);
    // …and the frame is really in the sketch now, which only a constraint that
    // names it can do. Tolerant of the throw: this sketch is unsaved, so there
    // is no sketch feature to evaluate until the debounced persist binds it,
    // and "not yet" is a poll iteration rather than a failure.
    await expect
      .poll(
        async () => {
          try {
            return (await solvedSketch(page, token, part.id)).some(
              (e) => e.id === "origin",
            );
          } catch {
            return false;
          }
        },
        { timeout: 30_000 },
      )
      .toBe(true);
  });
});
