import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import { inkAt } from "./reachability";
import { createPartViaApi, seedSession, waitForFrames } from "./support";

/**
 * QA of SKETCH-2 (independent of the builder's own
 * `sketch-origin-constraint.spec.ts`) — can a working engineer GROUND a profile
 * to the sketch frame and keep it grounded?
 *
 * The builder's spec proves one click, on one plane, at one zoom, with one verb
 * (coincident-to-origin). This file asks the questions a user's hand asks:
 *
 *  1. THE FOUNDER'S GESTURE. Clicking the drawn INK — measured from the canvas,
 *     not assumed — all the way round the ring, at three zoom levels. The
 *     builder measured that the ring sits ~10 px out against an 8 px point
 *     tolerance, so a naive centre-point fix would still have missed; the
 *     question that leaves open is whether the correspondence between ink and
 *     grab region survives a zoom, since the ink is a fixed size in PLANE MM
 *     and the tolerance is a fixed size in SCREEN PX.
 *  2. THE AXES AS TARGETS, not just as selectable things: "this plate is
 *     symmetric about the origin" — the sentence the ticket says was not
 *     expressible at all — authored through the Y axis and held through a
 *     re-drive.
 *  3. THE FRAME ON A PLANE THAT IS NOT XY, and on a sketch seated on a FACE
 *     (where the origin is the face's area centroid and can move).
 *  4. THE SNAP TRAP. A corner SNAPPED onto the origin looks grounded and is
 *     not. Measured as a user would experience it: the profile walks off zero
 *     the moment a dimension is re-driven.
 *  5. GROUNDED PROFILE STILL EXTRUDES — the frame is construction geometry, so
 *     it must not open the wire the extrude consumes.
 *
 * Reads use the park-then-wait shape (`pick-affordance.spec.ts`'s
 * `confirmsPlacementFace`): park on a known-empty state, wait for the readout
 * to say so, then act and wait for the new value. A bare read after a pointer
 * move both lags and leads.
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

/** The design token the frame's ink wears when held (`sketch.selectedInk`). */
const INK_SELECTED = "#E3A64B"; // packages/design tokens.ts -> color.brass

/** Somewhere with nothing to pick — the park that makes a stale read visible. */
const EMPTY_STEEL: Point = { x: 46, y: -22 };

/**
 * Plane-mm -> screen-px mapper, read off the DRO with the grid OFF so the two
 * calibration samples are raw. Re-run after every camera change: the whole
 * point of the zoom leg is that this mapping is not constant.
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

/**
 * The radius (screen px) at which the ORIGIN RING is actually drawn, measured
 * off the canvas at 45 degrees — a diagonal so neither axis's ink can be
 * mistaken for the ring. Sampled while the origin is SELECTED so the ring is
 * brass and nothing else on an empty sheet is.
 */
async function measureRingRadiusPx(
  page: Page,
  centre: Point,
  maxPx = 90,
): Promise<number> {
  /*
    THE SETTLE HAS TO BE EXPLICIT, and it was not — it was ACCIDENTAL, which is
    how batching this scan briefly broke it (CI-4 headroom pass, 2026-08-29).

    The caller selects the origin through the keyboard and waits for the
    selection READOUT, which is DOM; the ring is CANVAS, drawn by a
    demand-rendered r3f scene. So the readout can say "1 pt" a frame or more
    before the brass ring is painted. The old per-point version issued 356
    sequential awaits, and the renderer simply won the race inside the first few
    of them — nothing in the code said so. Taking ONE snapshot removed that
    incidental slack and the scan started reading a pre-paint frame, failing as
    "the origin ring must be visible ink" in 1 of 4 quiet runs.

    Waiting on real RENDERS rather than re-introducing latency is the fix: it
    states the requirement, and it is what the batched version needs to be
    correct rather than lucky.
  */
  await waitForFrames(page, 2);
  const diagonals = [
    [1, 1],
    [-1, 1],
    [1, -1],
    [-1, -1],
  ];
  // ONE readback for the whole scan. This used to call a per-point probe inside
  // the loop, and reading the canvas costs a copy of the ENTIRE frame however
  // few pixels you then inspect — so the scan paid 89 radii x 4 diagonals =
  // 356 full-frame copies per leg, 1068 across the three zoom legs, to read
  // nine pixels each time.
  //
  // AND IT WAS NOT THE PROBLEM, which is the useful half of this comment. That
  // looked like an obvious cause for a test that had started timing out at 60 s
  // (CI-4 headroom pass, 2026-08-29), and batching it changed the wall clock by
  // NOTHING: the phase timers below put this scan at 190 ms of a 33.2 s test —
  // 0.6 % — while the zoom loop was 47 %. Keep the batching, it is strictly
  // less work; do not believe it bought any headroom. A cost model is a
  // hypothesis until it is measured.
  //
  // Every sampled coordinate, tolerance and threshold below is unchanged; only
  // the number of readbacks is.
  const probes: { x: number; y: number }[] = [];
  const radii: number[] = [];
  for (let r = 2; r <= maxPx; r += 1) {
    radii.push(r);
    for (const [dx, dy] of diagonals) {
      probes.push({
        x: centre.x + ((dx as number) * r) / Math.SQRT2,
        y: centre.y + ((dy as number) * r) / Math.SQRT2,
      });
    }
  }
  const counts = await inkAt(page, probes, INK_SELECTED, 1);
  const hits: number[] = [];
  radii.forEach((r, i) => {
    let found = 0;
    for (let d = 0; d < diagonals.length; d += 1) {
      if ((counts[i * diagonals.length + d] ?? -1) > 0) found += 1;
    }
    if (found >= 3) hits.push(r);
  });
  if (hits.length === 0) return NaN;
  // Two brass blobs answer here when the origin is held: the picked-point DOT
  // at the centre and the RING outside it. Split the hits into contiguous runs
  // and take the OUTERMOST — averaging across both put the "ring" at 6.5 px in
  // the first draft of this helper, which is the dot's edge, not the ring.
  const runs: number[][] = [];
  for (const r of hits) {
    const last = runs[runs.length - 1];
    if (last !== undefined && r === (last[last.length - 1] as number) + 1) {
      last.push(r);
    } else {
      runs.push([r]);
    }
  }
  const outer = runs[runs.length - 1] as number[];
  return ((outer[0] as number) + (outer[outer.length - 1] as number)) / 2;
}

/** Click at `screen`, having first parked on empty steel. */
async function parkThenClick(
  page: Page,
  at: Mapper,
  screen: Point,
  modifier?: "Shift",
): Promise<void> {
  const empty = at(EMPTY_STEEL);
  await page.mouse.click(empty.x, empty.y);
  await expect(page.getByTestId("selection-readout")).toContainText(
    "nothing selected",
  );
  if (modifier) await page.keyboard.down(modifier);
  await page.mouse.click(screen.x, screen.y);
  if (modifier) await page.keyboard.up(modifier);
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

/** The SOLVED entity set — what the solver produced, not what was authored. */
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

/**
 * A 24 x 16 rectangle at (10,8) carrying THE PRODUCT'S OWN rigidity set —
 * `drawDimensions.ts` `rectangleRigidity`: four corner coincidences plus
 * horizontal on BOTH horizontal edges and vertical on BOTH vertical edges,
 * which is what the rect tool authors the moment a dimension is typed. Rigid in
 * shape (16 DOF − 12 − 2 driven = 2, i.e. free to translate and nothing else),
 * floating in position.
 *
 * The builder's fixture in `sketch-origin-constraint.spec.ts` carries only ONE
 * horizontal and ONE vertical while calling itself "rigid in SHAPE", which is
 * the difference between a rectangle and a four-bar linkage — see the QA report
 * and `docs/UI-REVIEW.md`.
 */
function floatingRect(plane: Record<string, unknown>) {
  return {
    plane,
    entities: [
      { id: "e1", kind: "line", start: { x: 10, y: 8 }, end: { x: 34, y: 8 } },
      { id: "e2", kind: "line", start: { x: 34, y: 8 }, end: { x: 34, y: 24 } },
      {
        id: "e3",
        kind: "line",
        start: { x: 34, y: 24 },
        end: { x: 10, y: 24 },
      },
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
      { kind: "distance", entity: "e1", value_mm: 24 },
      { kind: "distance", entity: "e2", value_mm: 16 },
    ],
  };
}

/** How many constraints the fixture authors (the "N applied" baseline). */
const FIXTURE_CONSTRAINTS = 10;

/**
 * The four corners of the solved rectangle, in emission order (bottom-left,
 * bottom-right, top-right, top-left). Reading ALL FOUR is the point: the
 * builder's spec checks two, and the two it checks are the two that stay put
 * when the profile deforms instead of translating.
 */
function corners(entities: SketchEntityRow[]): Point[] {
  return ["e1", "e2", "e3", "e4"].map((id) => {
    const start = entities.find((e) => e.id === id)?.start;
    if (start === undefined) throw new Error(`${id} lost its start point`);
    return start;
  });
}

/**
 * Assert the solved profile is the rectangle `expected`, corner by corner.
 * `precision` is `toBeCloseTo`'s: a DOF the constraints leave free (a plate
 * held symmetric about Y is free in y) settles within a micron or two of where
 * it started, which is the solver working, not the profile moving.
 */
function expectCorners(
  entities: SketchEntityRow[],
  expected: readonly (readonly [number, number])[],
  precision = 5,
): void {
  const got = corners(entities);
  expected.forEach(([x, y], i) => {
    expect((got[i] as Point).x, `corner ${i} x`).toBeCloseTo(x, precision);
    expect((got[i] as Point).y, `corner ${i} y`).toBeCloseTo(y, precision);
  });
}

async function seedRect(
  page: Page,
  token: string,
  partId: string,
  plane: Record<string, unknown> = { kind: "datum_plane", plane: "XY" },
): Promise<void> {
  await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: floatingRect(plane) },
    expected_tree_version: 0,
  });
}

async function reopenSketch(page: Page, planeLabel = "XY"): Promise<void> {
  await page.getByTestId("feature-row").first().click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-strip")).toBeVisible();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${planeLabel}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Click "Finish sketch" and wait for the strip to close — clicking AGAIN if it
 * does not, which is what a user does.
 *
 * This is not test padding, it is working around a measured product race
 * (`docs/UI-REVIEW.md` QA-SK2-3): the strip's button is
 * `disabled={saving || …}`, every constraint edit kicks off a live save, and a
 * click that lands in the window between Playwright's actionability check and
 * React's re-render is delivered to a disabled button and dropped silently.
 * Measured 2 of 10 attempts under load, always with the sketch fully saved
 * (`DOF 0 · CONVERGED`, the button focused) and the strip simply still open.
 * The retry is bounded and condition-gated, never a sleep.
 */
async function finishSketch(page: Page): Promise<void> {
  const strip = page.getByTestId("sketch-strip");
  const button = page.getByTestId("sketch-save");
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await expect(button).not.toHaveAttribute("aria-busy", "true");
    await button.click();
    try {
      await expect(strip).toHaveCount(0, { timeout: 8_000 });
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });
      return;
    } catch {
      // The click was swallowed; the strip is still up. Try again.
    }
  }
  throw new Error(
    "Finish sketch was clicked 5 times and the sketch strip never closed",
  );
}

/**
 * Re-open the sketch, click the distance glyph reading `current`, type `next`,
 * and save. The re-drive is the gesture that separates a GROUNDED profile from
 * a merely SNAPPED one: the solver re-places the geometry, and only a real
 * constraint holds the corner where the user put it.
 */
async function redriveWidth(
  page: Page,
  current: RegExp,
  next: string,
): Promise<void> {
  await reopenSketch(page);
  const glyph = page
    .locator('[data-testid^="glyph-"][data-kind="distance"]')
    .filter({ hasText: current });
  await expect(glyph).toHaveCount(1);
  await glyph.click();
  await expect(page.getByTestId("dimension-editor")).toBeVisible();
  await page.getByTestId("dimension-input").fill(next);
  await page.getByTestId("dimension-input").press("Enter");
  await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
  await finishSketch(page);
}

async function openPartWithRect(
  page: Page,
  name: string,
  plane?: Record<string, unknown>,
): Promise<{ token: string; partId: string }> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await seedRect(page, token, part.id, plane);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  return { token, partId: part.id };
}

test.describe("QA SKETCH-2 — grounding to the sketch frame", () => {
  test("the founder's gesture: the drawn ring picks all the way round, at three zoom levels", async ({
    page,
  }) => {
    /*
      180 s, and the DEFAULT 60 s was never a considered number — this test was
      simply born under it (CI-4 headroom pass, 2026-08-29). Measured on a
      4-core box before any change: 45.9 / 47.5 s quiet and a TIMEOUT in 1 of 3
      quiet isolated runs, 0 of 3 passing under two CPU spinners, and the
      failure arrives as "Test timeout of 60000ms exceeded", which names none of
      the 54 clicks and 81 settle-waits it might have died in.

      The work was cut first and the ceiling raised second, which is the order
      that matters: the per-notch pointer re-park is gone (see the zoom loop)
      and the ring scan takes one canvas readback instead of 356. After that,
      quiet 36.6-39.0 s (4/4) and loaded 55.7-57.5 s (4/4) — so it now PASSES
      under load, at 1.04x its old ceiling, which is not headroom.

      180 s is 4.6x the worst quiet reading and 3.1x the worst loaded one, and
      it is the ceiling this suite's other census tests already carry. What is
      NOT being widened is any assertion: the gesture is still eight compass
      points plus the centre, at three zoom levels, on measured ink.
    */
    test.setTimeout(180_000);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Frame ink");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    void token;

    // Three cameras: as the sketch opens, zoomed IN, and zoomed OUT. The ring
    // is a fixed size in PLANE MM and the pick tolerance a fixed size in SCREEN
    // PX, so the correspondence between the two is not automatic across a zoom.
    // OrbitControls dollies by a fixed ratio PER WHEEL EVENT (three-stdlib
    // reads only the sign of `deltaY`), so one big delta is one notch: the
    // first draft of this loop scrolled -600 and moved the camera 17 %, which
    // is not a zoom test. Notches it is.
    const legs: { label: string; notches: number }[] = [
      { label: "as opened", notches: 0 },
      { label: "zoomed in", notches: -16 },
      { label: "zoomed out", notches: 32 },
    ];
    const radii: Record<string, number> = {};
    // Phase timing, printed. This test began TIMING OUT at 60 s (CI-4 headroom
    // pass, 2026-08-29) and the first theory — that its ring scan's per-point
    // canvas readbacks were the cost — was WRONG: batching them 356:1 changed
    // the wall clock by nothing. So the split is measured here rather than
    // reasoned about, and it stays in the log so the next person does not have
    // to guess either.
    for (const leg of legs) {
      const legStart = Date.now();
      // The pointer is parked ONCE, not re-parked before every notch. Each
      // `mouse.move` is its own CDP round trip and the cursor is already at
      // (800, 500) after the first, so 46 of the 48 were paying full latency to
      // move the pointer nowhere — and this loop is the single most expensive
      // phase of the test (measured below: 15.8 s of 33.2 s quiet).
      if (leg.notches !== 0) await page.mouse.move(800, 500);
      for (let i = 0; i < Math.abs(leg.notches); i += 1) {
        await page.mouse.wheel(0, leg.notches < 0 ? -120 : 120);
      }
      if (leg.notches !== 0) await page.waitForTimeout(400);
      const zoomMs = Date.now() - legStart;
      const calStart = Date.now();
      const at = await calibratePlane(
        page,
        { x: 700, y: 620 },
        { x: 1000, y: 420 },
      );
      const calibrateMs = Date.now() - calStart;
      const centre = at({ x: 0, y: 0 });

      // Select through the KEYBOARD handle so the ink can be measured without
      // a pointer click having already proved the thing under test. The handle
      // TOGGLES, so park on empty first — otherwise the leg that follows a
      // successful click deselects and reads as this defect.
      await page.mouse.click(at(EMPTY_STEEL).x, at(EMPTY_STEEL).y);
      await expect(page.getByTestId("selection-readout")).toContainText(
        "nothing selected",
      );
      await page.getByTestId("sketch-origin").focus();
      await page.keyboard.press("Enter");
      await expect(
        page.getByTestId("selection-readout"),
        `${leg.label}: keyboard handle selects the origin`,
      ).toContainText("1 pt");
      const selectMs = Date.now() - calStart - calibrateMs;
      const scanStart = Date.now();
      const ringPx = await measureRingRadiusPx(page, centre);
      const scanMs = Date.now() - scanStart;
      radii[leg.label] = ringPx;
      expect(
        ringPx,
        `${leg.label}: the origin ring must be visible ink`,
      ).toBeGreaterThan(2);

      // THE GESTURE: click ON the ink, all the way round.
      const gestureStart = Date.now();
      const compass = [0, 45, 90, 135, 180, 225, 270, 315];
      for (const deg of compass) {
        const rad = (deg * Math.PI) / 180;
        const target = {
          x: centre.x + Math.cos(rad) * ringPx,
          y: centre.y + Math.sin(rad) * ringPx,
        };
        await parkThenClick(page, at, target);
        await expect(
          page.getByTestId("selection-readout"),
          `${leg.label}: click on the ring ink at ${deg} deg`,
        ).toContainText("1 pt");
        await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
          "data-pick-state",
          "selected",
        );
      }

      // And the exact centre of the mark, which is where a person actually
      // aims: inside the disc, so it must select too.
      await parkThenClick(page, at, centre);
      await expect(
        page.getByTestId("selection-readout"),
        `${leg.label}: click at the exact centre of the mark`,
      ).toContainText("1 pt");
      console.log(
        `    [SKETCH-2] leg "${leg.label}" ${Date.now() - legStart} ms = ` +
          `zoom ${zoomMs} + calibrate ${calibrateMs} + select ${selectMs} + ` +
          `ring scan ${scanMs} + gesture ${Date.now() - gestureStart}`,
      );
    }
    // The legs really were different cameras — otherwise the loop above is one
    // measurement repeated three times and proves nothing about zoom.
    expect(radii["zoomed in"] as number).toBeGreaterThan(
      (radii["as opened"] as number) * 1.15,
    );
    expect(radii["zoomed out"] as number).toBeLessThan(
      (radii["as opened"] as number) * 0.85,
    );
  });

  test("the Y axis grounds a plate SYMMETRICALLY about the origin, and holds through a re-drive", async ({
    page,
  }) => {
    const { token, partId } = await openPartWithRect(page, "Symmetric plate");
    await reopenSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // Two corners of the rectangle + the Y axis -> symmetric. This is the
    // sentence the ticket says was not expressible at all before: "this plate
    // is symmetric about the origin".
    await parkThenClick(page, at, at({ x: 10, y: 8 }));
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.down("Shift");
    await page.mouse.click(at({ x: 34, y: 8 }).x, at({ x: 34, y: 8 }).y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    // The Y axis, sampled well below the profile so nothing drawn is in range.
    await page.keyboard.down("Shift");
    await page.mouse.click(at({ x: 0, y: -30 }).x, at({ x: 0, y: -30 }).y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText(
      "1 ent · 2 pts",
    );
    await page.keyboard.press("s");
    await expect(page.getByTestId("selection-readout")).toContainText(
      `${FIXTURE_CONSTRAINTS + 1} applied`,
    );
    // The axis's two pins are not the user's work and are not counted.
    await expect(page.locator('[data-testid^="glyph-"]')).toHaveCount(
      FIXTURE_CONSTRAINTS + 1,
    );

    await finishSketch(page);

    // THE WHOLE PLATE, all four corners — a rectangle centred on x = 0 and
    // still 24 x 16. Checking only the edge that was picked would pass on a
    // profile the solver had sheared.
    const solved = await solvedSketch(page, token, partId);
    expectCorners(
      solved,
      [
        [-12, 8],
        [12, 8],
        [12, 24],
        [-12, 24],
      ],
      2,
    );

    // The Y axis is now real, pinned CONSTRUCTION geometry in the saved sketch.
    const params = await sketchParams(page, token, partId);
    expect(params.entities.find((e) => e.id === "y-axis")).toMatchObject({
      kind: "line",
      construction: true,
    });
    expect(
      params.constraints.filter(
        (c) => c.kind === "fixed" && c.point?.entity === "y-axis",
      ),
    ).toHaveLength(2);
    // Nothing was reached for that was not needed.
    expect(params.entities.map((e) => e.id)).not.toContain("x-axis");

    // RE-DRIVE: widen 24 -> 36. Symmetric means the plate grows BOTH ways.
    await reopenSketch(page);
    const at2 = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
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
    await finishSketch(page);
    const resized = await solvedSketch(page, token, partId);
    expectCorners(
      resized,
      [
        [-18, 8],
        [18, 8],
        [18, 24],
        [-18, 24],
      ],
      2,
    );
  });

  test("THE SNAP TRAP IS CLOSED: a corner snapped onto the origin IS grounded", async ({
    page,
  }) => {
    // THIS TEST USED TO ASSERT THE DEFECT, and it is kept — inverted — rather
    // than deleted, because a characterisation test is the best regression
    // test the trap will ever have. QA's original words (QA-SK2-4): the corner
    // "looks grounded and is not" — the snap copied the coordinate, recorded no
    // relationship, and the plate walked off zero on the first re-drive with
    // nothing having warned anybody. SNAP-3 authors the coincident the snap
    // meant, so every "and nothing says so" assertion below is now its opposite.
    //
    // What this keeps that the SNAP-3 spec does not have: the DRAW-TIME
    // dimension path. The width is typed during the gesture, so the
    // rectangle's whole rigidity set (`drawDimensions.ts`) rides in ALONGSIDE
    // the inferred coincident — which is precisely the combination that would
    // over-constrain if the inference were careless, and precisely the state
    // QA was in when they found the trap.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Snapped and grounded");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // Draw a rectangle whose FIRST corner is snapped to the origin — the
    // gesture a user makes when they mean "start this part at zero". The snap
    // fires and says "Origin", so the tool has visibly understood the aim.
    await page.keyboard.press("r");
    const origin = at({ x: 0, y: 0 });
    // Park somewhere with no mark, so the mark seen next was produced by this
    // move and not left over from the last one.
    await page.mouse.move(
      at({ x: 33.3, y: 17.7 }).x,
      at({ x: 33.3, y: 17.7 }).y,
    );
    await expect(page.getByTestId("snap-marker")).toHaveCount(0);
    await page.mouse.move(origin.x + 5, origin.y - 4);
    await expect(page.getByTestId("snap-marker")).toHaveAttribute(
      "data-snap-kind",
      "origin",
    );
    await expect(page.getByTestId("dro-x")).toHaveText("+0.00");
    await expect(page.getByTestId("dro-y")).toHaveText("+0.00");
    await page.mouse.click(origin.x + 5, origin.y - 4);
    const far = at({ x: 30, y: 20 });
    await page.mouse.move(far.x, far.y);
    await page.mouse.click(far.x, far.y);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    // Type the width at draw time, which is what makes this a REAL modelling
    // state rather than a scribble: `drawDimensions.ts` rides the rectangle's
    // whole rigidity set in with the first typed value, so what follows is a
    // rigid, dimensioned, apparently-anchored plate.
    await page.keyboard.type("30");
    await page.keyboard.press("Enter");
    // TEN, not the nine this read before SNAP-3: the rectangle's eight
    // rigidity constraints, the typed width, and the coincident the ORIGIN
    // SNAP authored. The origin's own pin rides in with it and is deliberately
    // not counted — the user authored none of it (`isDatumPin`).
    //
    // This number is the readout QA called out by name: "the strip reads
    // '9 applied' — and there is no `origin` entity and no constraint naming
    // it." The count moving is the first thing on screen that distinguishes a
    // snapped corner from a coordinate that happens to match.
    await expect(page.getByTestId("selection-readout")).toContainText(
      "10 applied",
    );
    // The first typed dimension binds the sketch and it saves LIVE, so the
    // strip's button swaps from "Save (N entities)" to "Finish sketch" while
    // that POST is in flight. Clicking across the swap lands on the old
    // handler and the strip never closes — wait for the bound state first.
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("sketch-save")).toContainText("Finish");
    await finishSketch(page);

    // The corner IS at zero — the snap landed it exactly. That was never the
    // defect and it is still true; it is the half that made the trap invisible.
    const solved = await solvedSketch(page, token, part.id);
    const corner = solved
      .flatMap((e) => [e.start, e.end])
      .filter((p): p is Point => p !== undefined)
      .find((p) => Math.hypot(p.x, p.y) < 1e-6);
    expect(corner, "the snap put a corner exactly on zero").toBeDefined();

    // AND NOW THE SAVED MODEL SAYS SO. Inverted from `not.toContain("origin")`
    // / `toHaveLength(0)`: the datum is materialised as pinned construction
    // geometry and a coincident names it, so the relationship is recorded and
    // not merely implied by two numbers that agree.
    const params = await sketchParams(page, token, part.id);
    expect(params.entities.map((e) => e.id)).toContain("origin");
    expect(
      params.constraints.filter(
        (c) =>
          c.kind === "coincident" && JSON.stringify(c).includes('"origin"'),
      ),
    ).toHaveLength(1);
    expect(
      params.constraints.filter(
        (c) => c.kind === "fixed" && c.point?.entity === "origin",
      ),
    ).toHaveLength(1);

    // HOW THE USER USED TO FIND OUT: re-drive a dimension and the part they
    // anchored at zero slides off it. It now holds — this is the assertion the
    // coordinate copy could never satisfy, and it is the one that reddens if
    // the inference is removed.
    await redriveWidth(page, /^30$/, "40");
    const held = await solvedSketch(page, token, part.id);
    const left = (held.find((e) => e.id === "e1") as SketchEntityRow)
      .start as Point;
    expect(left.x).toBeCloseTo(0, 5);
    expect(left.y).toBeCloseTo(0, 5);

    // THE CONTROL, and it is doing different work now that the trap is closed.
    // Before, it proved the solver CAN hold a grounded corner; now it proves
    // the automatic grounding did not quietly cost the sketch its solvability.
    // Re-drive once more and the plate is still solved, still on zero, and
    // still not over-constrained — an inference that grounded the corner by
    // over-determining it would show here and nowhere else.
    await redriveWidth(page, /^40$/, "55");
    const again = await solvedSketch(page, token, part.id);
    const anchored = (again.find((e) => e.id === "e1") as SketchEntityRow)
      .start as Point;
    expect(anchored.x).toBeCloseTo(0, 5);
    expect(anchored.y).toBeCloseTo(0, 5);
    const bottom = again.find((e) => e.id === "e1") as SketchEntityRow;
    expect(
      Math.hypot(
        (bottom.end as Point).x - (bottom.start as Point).x,
        (bottom.end as Point).y - (bottom.start as Point).y,
      ),
    ).toBeCloseTo(55, 3);
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
  });

  test("a grounded profile still extrudes — the frame is construction, not part of the wire", async ({
    page,
  }) => {
    const { token, partId } = await openPartWithRect(page, "Grounded boss");
    await reopenSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await parkThenClick(page, at, at({ x: 10, y: 8 }));
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    const origin = at({ x: 0, y: 0 });
    await page.keyboard.down("Shift");
    await page.mouse.click(origin.x + 11, origin.y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    await finishSketch(page);

    // THE WHOLE PROFILE TRANSLATED. Every corner moved by the same (-10,-8),
    // so it is still a 24 x 16 rectangle. This is the claim the ticket makes
    // and the one its own spec cannot see: with a rectangle that is not
    // actually rigid the solver satisfies the coincident by DEFORMING, and the
    // two corners the builder's spec samples are exactly the two that survive.
    const grounded = await solvedSketch(page, token, partId);
    expectCorners(grounded, [
      [0, 0],
      [24, 0],
      [24, 16],
      [0, 16],
    ]);

    await page.getByTestId("new-extrude").click();
    await page.getByTestId("extrude-distance").fill("5");
    await page.getByTestId("extrude-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    // 24 x 16 x 5 = 1920 mm^3. A frame member leaking into the profile would
    // change this number, not merely look wrong. (The readout is grouped —
    // "1,920.00 mm³" — so match the grouped string, as the extrude specs do.)
    await expect(page.getByTestId("prop-volume")).toContainText("1,920", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-extents")).toContainText("24 × 16 × 5");
    // …and the grounded corner is still the body's own zero corner.
    const solved = await solvedSketch(page, token, partId);
    const e1 = solved.find((e) => e.id === "e1");
    expect(e1?.start?.x).toBeCloseTo(0, 6);
    expect(e1?.start?.y).toBeCloseTo(0, 6);
  });

  test("the frame grounds a profile on XZ too — not just the plane the spec used", async ({
    page,
  }) => {
    const { token, partId } = await openPartWithRect(page, "XZ plate", {
      kind: "datum_plane",
      plane: "XZ",
    });
    await reopenSketch(page, "XZ");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await parkThenClick(page, at, at({ x: 10, y: 8 }));
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    const origin = at({ x: 0, y: 0 });
    await page.keyboard.down("Shift");
    await page.mouse.click(origin.x + 11, origin.y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    await expect(page.getByTestId("selection-readout")).toContainText(
      `${FIXTURE_CONSTRAINTS + 1} applied`,
    );
    await finishSketch(page);
    expectCorners(await solvedSketch(page, token, partId), [
      [0, 0],
      [24, 0],
      [24, 16],
      [0, 16],
    ]);
  });

  test("TARGET, NOT SUBJECT: every driving verb is refused by name, and the ones that work still work", async ({
    page,
  }) => {
    const { token, partId } = await openPartWithRect(page, "Frame verbs");
    await reopenSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    const origin = at({ x: 0, y: 0 });

    // Every verb that would DRIVE the frame, on the origin and on an axis.
    for (const [target, screen] of [
      ["origin", { x: origin.x + 11, y: origin.y }],
      ["x-axis", at({ x: 30, y: 0 })],
      ["y-axis", at({ x: 0, y: -30 })],
    ] as const) {
      for (const key of ["h", "v", "d", "r", "x", "e"]) {
        await parkThenClick(page, at, screen);
        await expect(page.getByTestId("selection-readout")).not.toContainText(
          "nothing selected",
        );
        await page.keyboard.press(key);
        await expect(
          page.getByTestId("constraint-hint"),
          `${key} on the ${target} must be refused by name`,
        ).toContainText("origin and axes are fixed");
        // Refused means refused: nothing was authored behind the hint.
        await expect(page.getByTestId("selection-readout")).toContainText(
          `${FIXTURE_CONSTRAINTS} applied`,
        );
      }
    }

    // …and the verbs the refusal ADVERTISES actually work. Perpendicular
    // between a drawn edge and the X axis is a real relation to the frame.
    await parkThenClick(page, at, at({ x: 10, y: 16 })); // the left edge, e4
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.down("Shift");
    await page.mouse.click(at({ x: 30, y: 0 }).x, at({ x: 30, y: 0 }).y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 ents");
    await page.keyboard.press("l"); // perpendicular
    await expect(page.getByTestId("selection-readout")).toContainText(
      `${FIXTURE_CONSTRAINTS + 1} applied`,
    );
    await finishSketch(page);
    const params = await sketchParams(page, token, partId);
    expect(
      params.constraints.some(
        (c) => c.kind === "perpendicular" && [c.a, c.b].includes("x-axis"),
      ),
    ).toBe(true);
    expect(params.entities.find((e) => e.id === "x-axis")).toMatchObject({
      kind: "line",
      construction: true,
    });
  });

  test("an ARMED dimension cannot be eaten by the frame — and is not lost to it either", async ({
    page,
  }) => {
    await openPartWithRect(page, "Armed dimension");
    await reopenSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // Arm Distance with NOTHING selected (the `dimensionPick` rung), then
    // click the origin: the frame must neither open an editor nor swallow the
    // arming.
    await page.mouse.click(at(EMPTY_STEEL).x, at(EMPTY_STEEL).y);
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await page.keyboard.press("d");
    const origin = at({ x: 0, y: 0 });
    await page.mouse.click(origin.x + 11, origin.y);
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "origin and axes are fixed",
    );
    // Still armed: the very next click on a real line dimensions THAT line.
    await page.mouse.click(at({ x: 22, y: 8 }).x, at({ x: 22, y: 8 }).y);
    await expect(page.getByTestId("dimension-editor")).toBeVisible();
    await expect(page.getByTestId("dimension-input")).toHaveValue("24");
    await page.keyboard.press("Escape");
  });

  test("a FACE-SEATED sketch's origin is selectable and grounds a profile to the face centroid", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Boss on a face");
    const sketch = await createFeature(page, token, part.id, {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: floatingRect({ kind: "datum_plane", plane: "XY" }),
      },
      expected_tree_version: 0,
    });
    await createFeature(page, token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Seat a sketch on the TOP face — the case where the origin is the face's
    // AREA CENTROID and can move, which is the plane kind the origin module
    // singles out as needing a caveat.
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
    const nodes = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
    let bestZ = -Infinity;
    let bestIndex = 0;
    for (let i = 0; i < (await nodes.count()); i += 1) {
      const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
      const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
      const z = Number.parseFloat(nums[nums.length - 1] as string);
      if (Number.isFinite(z) && z > bestZ) {
        bestZ = z;
        bestIndex = i;
      }
    }
    await nodes.nth(bestIndex).click();
    await expect(page.getByTestId("dro-plane")).toHaveText("Face");
    await expect(page.getByTestId("sketch-dro")).toBeVisible();

    // The frame's DOM handle knows it is a face centre, not a datum zero —
    // and the accessible name carries the caveat that it can move.
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-origin-label",
      "Face centre",
    );
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "aria-label",
      /moves if the outline changes/,
    );

    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    // Draw a rectangle clear of the origin, then ground its corner to it.
    await page.keyboard.press("r");
    await page.mouse.click(at({ x: 3, y: 2 }).x, at({ x: 3, y: 2 }).y);
    await page.mouse.move(at({ x: 9, y: 6 }).x, at({ x: 9, y: 6 }).y);
    await page.mouse.click(at({ x: 9, y: 6 }).x, at({ x: 9, y: 6 }).y);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.keyboard.press("Escape");

    await parkThenClick(page, at, at({ x: 3, y: 2 }));
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    const origin = at({ x: 0, y: 0 });
    await page.keyboard.down("Shift");
    await page.mouse.click(origin.x + 11, origin.y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    // 9 = RECT-1's rigidity set (4 coincidences + 2H + 2V, authored by the
    // draw) plus this grounding one. The rectangle is deliberately drawn CLEAR
    // of the origin, so SNAP-3 infers nothing here and the grounding below is
    // still a real gesture rather than a redundant one.
    await expect(page.getByTestId("selection-readout")).toContainText(
      "9 applied",
    );
    await finishSketch(page);

    // The second sketch carries a pinned origin and a coincident naming it.
    const response = await page.request.get(
      `/api/v1/parts/${part.id}/features`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const body = (await response.json()) as {
      features: { feature: { type: string; params: unknown } }[];
    };
    const seated = body.features.filter((r) => r.feature.type === "sketch")[1]
      ?.feature.params as {
      entities: SketchEntityRow[];
      constraints: SketchConstraintRow[];
    };
    expect(seated.entities.find((e) => e.id === "origin")).toMatchObject({
      kind: "point",
      construction: true,
      position: { x: 0, y: 0 },
    });
    expect(
      seated.constraints.filter(
        (c) => c.kind === "fixed" && c.point?.entity === "origin",
      ),
    ).toHaveLength(1);
  });
});
