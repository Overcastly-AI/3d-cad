import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH-2 — THE SKETCH ORIGIN AND AXES ARE SELECTABLE CONSTRAINT TARGETS.
 *
 * The founder reported *"snap points do not work"* (2026-08-14). SNAP-1 measured
 * snap DETECTION as correct in every configuration it could build and
 * reproduced this instead, with a positive control in the same test:
 *
 *     click the drawn line   -> selection-readout = "1 ent"
 *     click the origin ring  -> "nothing selected"
 *     click the X axis       -> "nothing selected"
 *
 * You could AIM at the origin and could not SELECT it, which from the user's
 * chair is the same complaint. The mechanism: `SketchOrigin` drew the frame as
 * decorative `InkSegments` with nothing behind it to hit, and the only DOM at
 * (0,0) was a screen-reader-only span.
 *
 * ## What this file asserts, and why it is not "does a click register"
 *
 * A sketch that cannot be constrained to its own origin is not parametric — the
 * profile floats and every dimension is measured from nothing. So the bar is
 * that the frame can be selected AND USED, end to end:
 *
 *   1. the reported repro, inverted, with the same positive control;
 *   2. a floating rigid profile GROUNDED to the origin — the solver translates
 *      the whole rectangle so the chosen corner lands on (0,0);
 *   3. the grounding SURVIVES save + re-open (SKETCH-1's path);
 *   4. RESIZING the grounded profile leaves that corner on (0,0) — which is
 *      what makes it relational rather than `Fixed`-at-absolute-coordinates,
 *      the only grounding that was expressible before.
 *
 * Geometry is read over the API rather than from pixels — exact and
 * raster-independent. Two different reads, and the difference matters: the
 * SOLVED positions come from an evaluate (the client persists the authored
 * definition, never the solver's output), while the persisted params are where
 * the materialised origin entity and its pin have to show up.
 *
 * The DOM reads use the park-then-wait shape (`pick-affordance.spec.ts`'s
 * `confirmsPlacementFace`): park on a known-EMPTY state and wait for the
 * readout to say so, then click the target and wait for the new value. A bare
 * read after a pointer event yields both lagging and leading values, so without
 * the park a stale "nothing selected" would read as this defect and a stale
 * "1 pt" would read as the fix.
 */

interface Point {
  x: number;
  y: number;
}

type Mapper = (pt: Point) => Point;

interface SketchEntityRow {
  id: string;
  kind: string;
  construction?: boolean;
  position?: Point;
  start?: Point;
  end?: Point;
}

interface SketchConstraintRow {
  kind: string;
  entity?: string;
  line?: string;
  value_mm?: number;
  point?: { entity: string; point: string };
  a?: { entity: string; point: string } | string;
  b?: { entity: string; point: string } | string;
}

/**
 * A 24 x 16 rectangle at (10,8): rigid in SHAPE (corners tied, edges H/V, both
 * sizes driven) and NOT grounded — it floats with two translational degrees of
 * freedom. That is the state the ticket is about: before this change the only
 * way to pin it was `fixed` at absolute coordinates, which does not re-centre
 * when the profile's size changes.
 */
const FLOATING_RECT = {
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
    { kind: "vertical", entity: "e2" },
    { kind: "distance", entity: "e1", value_mm: 24 },
    { kind: "distance", entity: "e2", value_mm: 16 },
  ],
};

/** How many constraints the user authored in the fixture (glyph count). */
const FIXTURE_CONSTRAINTS = FLOATING_RECT.constraints.length;

/**
 * Plane-mm -> screen-px mapper, read off the DRO with the grid OFF so the two
 * calibration samples are raw. Local to this file rather than shared: the
 * suite's other copy lives in `sketch-snap-defaults.spec.ts`, which a sibling
 * owns this batch.
 */
async function calibratePlane(
  page: Page,
  s1: Point,
  s2: Point,
): Promise<Mapper> {
  await page.keyboard.press("g"); // grid off for raw readings
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
  await page.keyboard.press("g"); // grid back on — the default
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

/** Somewhere with nothing to pick — the park that makes a stale read visible. */
const EMPTY_STEEL: Point = { x: 46, y: -22 };

/**
 * Click at `screen` and wait for the readout to reach `expected`, having first
 * parked on empty steel and waited for "nothing selected". Without the park a
 * value left over from the previous click satisfies the wait.
 */
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

async function sketchParams(
  page: Page,
  token: string,
  partId: string,
): Promise<{
  entities: SketchEntityRow[];
  constraints: SketchConstraintRow[];
}> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(`e2e feature read failed: ${response.status()}`);
  }
  const body = (await response.json()) as {
    features: { feature: { type: string; params: unknown } }[];
  };
  const sketch = body.features.find((row) => row.feature.type === "sketch");
  if (sketch === undefined) throw new Error("no sketch feature on the part");
  return sketch.feature.params as {
    entities: SketchEntityRow[];
    constraints: SketchConstraintRow[];
  };
}

/**
 * The SOLVED entity set for the part's sketch — what the solver produced, not
 * what the client authored. The persisted params are the authored definition
 * (the client never writes solved coordinates back), so the geometric claims
 * here have to come from an evaluate: this is the same payload the sketcher
 * adopts, read at its source.
 */
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
    features: {
      status: string;
      data?: { kind: string; entities: SketchEntityRow[] } | null;
    }[];
  };
  const solved = body.features.find(
    (row) => row.data?.kind === "solved_sketch",
  );
  if (solved?.data === undefined || solved.data === null) {
    throw new Error("the evaluate carried no solved sketch");
  }
  return solved.data.entities;
}

/** The corner point shared by `e4.end` and `e1.start` — the one being grounded. */
function groundedCorner(entities: SketchEntityRow[]): Point {
  const e1 = entities.find((e) => e.id === "e1");
  if (e1?.start === undefined) throw new Error("e1 lost its start point");
  return e1.start;
}

async function seedFloatingRect(
  page: Page,
  token: string,
  partId: string,
): Promise<void> {
  await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: FLOATING_RECT },
    expected_tree_version: 0,
  });
}

async function reopenSketch(page: Page): Promise<void> {
  await page.getByTestId("feature-row").first().click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-strip")).toBeVisible();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

test.describe("SKETCH-2 — grounding a profile to the sketch frame", () => {
  test("the origin ring and both axes SELECT, with a drawn line as the control", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Frame picking");
    await seedFloatingRect(page, token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await reopenSketch(page);

    // FOUNDER SHOT (before): the frame at rest, at both widths. Before this
    // change every click on it left the viewport looking exactly like this,
    // with the readout saying "nothing selected".
    await page.mouse.move(1400, 900); // park the cursor off the sheet
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-origin-selected-before-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-origin-selected-before-1280.png`,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });

    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // THE POSITIVE CONTROL, exactly as SNAP-1 measured it: a drawn line picks.
    // If this ever fails the file is measuring a broken sketcher, not this bug.
    await selectAndRead(page, at, at({ x: 22, y: 8 }), "1 ent");

    // THE REPORTED DEFECT. The click lands on the drawn RING, ~11 px out from
    // zero — the founder's gesture, and the one the old code could not answer:
    // the ring is ~10 px from centre at the parked frame while a point pick
    // reaches 8 px, so aiming at the mark missed it by construction.
    const origin = at({ x: 0, y: 0 });
    await selectAndRead(page, at, { x: origin.x + 11, y: origin.y }, "1 pt");
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-pick-state",
      "selected",
    );
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await selectAndRead(page, at, at({ x: 30, y: 0 }), "1 ent");
    await expect(page.getByTestId("sketch-axis-x")).toHaveAttribute(
      "data-pick-state",
      "selected",
    );
    await selectAndRead(page, at, at({ x: 0, y: -20 }), "1 ent");
    await expect(page.getByTestId("sketch-axis-y")).toHaveAttribute(
      "data-pick-state",
      "selected",
    );
    // The frame is a target, not a subject: dimensioning an axis is refused by
    // name rather than silently arming a verb that would fight its pins.
    await page.keyboard.press("d");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "origin and axes are fixed",
    );

    // Keyboard path: the frame's handles are screen-reader-only buttons, so a
    // keyboard user can hold the origin without a pointer. Focus shows in the
    // VIEWPORT (the ink lights) — a sr-only control has nowhere else to show it.
    await page.mouse.click(at(EMPTY_STEEL).x, at(EMPTY_STEEL).y);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await page.getByTestId("sketch-origin").focus();
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-pick-state",
      "hover",
    );
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");

    // FOUNDER SHOT (after): the frame answering a pick — the ring in brass with
    // the picked-point dot every other defining point wears. The "before" of
    // this pair is the idle frame, because before this change the frame could
    // never look like anything else, whatever you clicked.
    await page.mouse.move(1400, 900); // park the cursor off the sheet
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-origin-selected-after-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-origin-selected-after-1280.png`,
    });
  });

  test("grounds a floating profile to the origin — and it holds through save, re-open and a resize", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Grounded plate");
    await seedFloatingRect(page, token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await reopenSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // ---- ground it: corner + origin -> coincident ------------------------
    await selectAndRead(page, at, at({ x: 10, y: 8 }), "1 pt");
    const origin = at({ x: 0, y: 0 });
    // Shift is held around the click rather than passed as an option:
    // `mouse.click` has no `modifiers` (only `locator.click` does), and the
    // sketcher reads the modifier off the keyboard state it tracks.
    await page.keyboard.down("Shift");
    await page.mouse.click(origin.x + 11, origin.y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");

    // The pin the frame needs is NOT the user's work: it carries no glyph and
    // is not counted. One more glyph than the fixture, and no FIX anywhere.
    await expect(page.getByTestId("selection-readout")).toContainText(
      `${FIXTURE_CONSTRAINTS + 1} applied`,
    );
    await expect(page.locator('[data-testid^="glyph-"]')).toHaveCount(
      FIXTURE_CONSTRAINTS + 1,
    );
    await expect(
      page.locator('[data-testid^="glyph-"]', { hasText: "FIX" }),
    ).toHaveCount(0);

    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // ---- what the solver actually did ------------------------------------
    const solved = await solvedSketch(page, token, part.id);
    // The whole rigid profile TRANSLATED: the chosen corner is on zero and the
    // far corner has moved by the same vector, still 24 x 16.
    expect(groundedCorner(solved).x).toBeCloseTo(0, 6);
    expect(groundedCorner(solved).y).toBeCloseTo(0, 6);
    const far = solved.find((e) => e.id === "e2");
    expect(far?.end?.x).toBeCloseTo(24, 6);
    expect(far?.end?.y).toBeCloseTo(16, 6);

    // The origin is real, pinned CONSTRUCTION geometry — so it can never open
    // the profile a downstream extrude consumes.
    const grounded = await sketchParams(page, token, part.id);
    const originEntity = grounded.entities.find((e) => e.id === "origin");
    expect(originEntity).toMatchObject({
      kind: "point",
      construction: true,
      position: { x: 0, y: 0 },
    });
    expect(
      grounded.constraints.filter(
        (c) => c.kind === "fixed" && c.point?.entity === "origin",
      ),
    ).toHaveLength(1);
    // The authored constraint names the origin RELATIONALLY. Nothing anywhere
    // fixes the corner at absolute coordinates — the distinction the whole
    // ticket turns on.
    expect(
      grounded.constraints.some(
        (c) =>
          c.kind === "coincident" &&
          [c.a, c.b].some(
            (ref) => typeof ref === "object" && ref?.entity === "origin",
          ),
      ),
    ).toBe(true);
    expect(
      grounded.constraints.some(
        (c) => c.kind === "fixed" && c.point?.entity.startsWith("e"),
      ),
    ).toBe(false);
    // The axes were never reached for, so they were never materialised.
    expect(grounded.entities.map((e) => e.id)).not.toContain("x-axis");

    // ---- it survives the round trip --------------------------------------
    await reopenSketch(page);
    await expect(page.locator('[data-testid^="glyph-"]')).toHaveCount(
      FIXTURE_CONSTRAINTS + 1,
    );
    const at2 = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    // Still selectable in the re-opened sketch, and not doubled by the
    // materialised copy that came back over the wire. The ring is sampled on
    // the -X side because the profile now occupies +X/+Y: drawn geometry has
    // priority on a plain click, so the ring is reached where it is clear.
    const origin2 = at2({ x: 0, y: 0 });
    await selectAndRead(page, at2, { x: origin2.x - 11, y: origin2.y }, "1 pt");

    // ---- resize: the corner STAYS on zero --------------------------------
    // A `Fixed` at absolute coordinates would hold the corner too. What it
    // would not do is keep holding it as the profile changes size, which is the
    // property being asserted here.
    await page.mouse.click(at2(EMPTY_STEEL).x, at2(EMPTY_STEEL).y);
    const width = page
      .locator('[data-testid^="glyph-"][data-kind="distance"]')
      .filter({ hasText: /^24$/ });
    await expect(width).toHaveCount(1);
    await width.click();
    await expect(page.getByTestId("dimension-editor")).toBeVisible();
    await page.getByTestId("dimension-input").fill("36");
    await page.getByTestId("dimension-input").press("Enter");
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);

    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const resized = await solvedSketch(page, token, part.id);
    expect(groundedCorner(resized).x).toBeCloseTo(0, 6);
    expect(groundedCorner(resized).y).toBeCloseTo(0, 6);
    const grew = resized.find((e) => e.id === "e1");
    expect(grew?.end?.x).toBeCloseTo(36, 6); // the profile got wider…
    expect(grew?.start?.x).toBeCloseTo(0, 6); // …away from the grounded corner
  });
});
