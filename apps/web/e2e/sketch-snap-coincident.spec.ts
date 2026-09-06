import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SNAP-3 (and SNAP-2 with it) — A SNAP AUTHORS THE CONSTRAINT IT MEANT.
 *
 * Independent QA of SKETCH-2 put the defect better than a ticket can
 * (`docs/UI-REVIEW.md` QA-SK2-4): draw a corner onto something, and *"there is
 * no signal in between — the mark looks identical, the count is identical,
 * nothing marks the corner."* The aim landed exactly; the sketch recorded only
 * the COORDINATE, and the join came apart on the first re-drive. SolidWorks and
 * Fusion both author the inferred coincident at draw time; we shipped the aim
 * and threw the intent away.
 *
 * SNAP-2 filed the datum-frame half (a corner on the origin), SNAP-3 the
 * general half (a corner on an entity's endpoint). They are ONE defect and this
 * file drives ONE mechanism: `snapCandidates` now hands out the address it took
 * the coordinate from, and a placement cashes the addresses it consumed in
 * through `inferredCoincidents`. The origin is just another addressable point,
 * so it needs no second code path — and two of them would be the DRY defect.
 *
 * ## What is asserted, and what would pass without the fix
 *
 * Everything here is read from the API — the persisted params (what was
 * AUTHORED) and an evaluate (what the SOLVER produced) — because the pixels are
 * identical either way. That is the whole complaint. The three tests are:
 *
 *   1. the general case: a corner drawn onto an endpoint carries a coincident,
 *      and survives a re-drive of the edge it hangs off;
 *   2. the datum case (SNAP-2's own acceptance): a corner drawn on the origin
 *      is GROUNDED — the origin entity and its pin are materialised, and the
 *      corner is still at exactly (0,0) after the profile is re-driven;
 *   3. the risk this change carries: authoring constraints that were not
 *      authored before can OVER-constrain. So an ordinary snapped
 *      draw-then-dimension flow must not redden, and — the guard against
 *      buying that by blinding the diagnosis — a genuinely redundant
 *      constraint on the same sketch must still stop the user with a glyph
 *      they can click.
 *
 * Tests 1 and 2 fail on pre-SNAP-3 HEAD at their first constraint assertion
 * (no coincident is authored at all) and again on the geometry after the
 * re-drive. Test 3's first half PASSES pre-fix, which is the point of it.
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

interface Ref {
  entity: string;
  point: string;
}

interface SketchConstraintRow {
  kind: string;
  entity?: string;
  value_mm?: number;
  point?: Ref;
  a?: Ref | string;
  b?: Ref | string;
}

const isRef = (value: Ref | string | undefined): value is Ref =>
  typeof value === "object" && value !== null;

const refIs = (value: Ref | string | undefined, ref: Ref): boolean =>
  isRef(value) && value.entity === ref.entity && value.point === ref.point;

/** Is there a coincident joining exactly these two named points, either way round? */
function joins(
  constraints: readonly SketchConstraintRow[],
  a: Ref,
  b: Ref,
): boolean {
  return constraints.some(
    (c) =>
      c.kind === "coincident" &&
      ((refIs(c.a, a) && refIs(c.b, b)) || (refIs(c.a, b) && refIs(c.b, a))),
  );
}

const dist = (a: Point, b: Point): number => Math.hypot(b.x - a.x, b.y - a.y);

function pointOf(entities: readonly SketchEntityRow[], ref: Ref): Point {
  const entity = entities.find((e) => e.id === ref.entity);
  if (entity === undefined) throw new Error(`no entity ${ref.entity}`);
  const at =
    ref.point === "start"
      ? entity.start
      : ref.point === "end"
        ? entity.end
        : entity.position;
  if (at === undefined) {
    throw new Error(`${ref.entity} has no ${ref.point}`);
  }
  return at;
}

async function enterSketch(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm -> screen-px mapper, read off the DRO at two points.
 *
 * THE GRID IS LEFT OFF when this returns, deliberately, and it is load-bearing
 * for this file rather than a tidiness choice. With the 1 mm grid live, an aim
 * a few tenths off a whole-millimetre corner lands on that corner ANYWAY — so a
 * spec that drew on round coordinates would measure the same geometry whether
 * the entity snap fired or not, and could not tell the two apart. Every corner
 * here is therefore off-grid (x.4 / y.4), where only the entity snap can
 * produce an exact join.
 */
async function calibratePlane(
  page: Page,
  s1: Point,
  s2: Point,
): Promise<Mapper> {
  await page.keyboard.press("g"); // grid off
  {
    // The camera eases into the normal-on pose after the plane pick, and the
    // DRO only re-raycasts on a pointer move: poll the same point until two
    // consecutive readings agree, which is the camera having settled.
    let last: number | null = null;
    await expect
      .poll(
        async () => {
          await page.mouse.move(s1.x + 2, s1.y);
          await page.mouse.move(s1.x, s1.y);
          const value = Number.parseFloat(
            await page.getByTestId("dro-x").innerText(),
          );
          const stable =
            last !== null && Number.isFinite(value) && value === last;
          last = value;
          return stable;
        },
        { timeout: 15_000 },
      )
      .toBe(true);
  }
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<Point> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (distinctFromX === undefined ||
            Math.abs(value - distinctFromX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(page: Page, at: Mapper, pt: Point): Promise<void> {
  const px = at(pt);
  await page.mouse.move(px.x, px.y);
  await page.mouse.click(px.x, px.y);
}

/** The corner glyphs alone — see the note at the "before" assertion (SNAP-5). */
const coincidentGlyph = (page: Page) =>
  page.locator('[data-testid^="glyph-"][data-kind="coincident"]');

/** FIX glyphs alone, by kind — the datum's own pin deliberately draws none. */
const fixGlyph = (page: Page) =>
  page.locator('[data-testid^="glyph-"][data-kind="fixed"]');

/** Click with Ctrl held — freehand: every snap suppressed (the UI-W5 polarity). */
async function clickFreehand(page: Page, at: Mapper, pt: Point): Promise<void> {
  await page.keyboard.down("Control");
  await clickPlane(page, at, pt);
  await page.keyboard.up("Control");
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
 * The SOLVED entity set — what the solver produced, not what was authored. The
 * client never writes solved coordinates back, so every geometric claim about a
 * re-drive has to be read here rather than from the persisted params.
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

/**
 * Finish the sketch, retrying the click: `sketch-save` disables itself while a
 * save is in flight, so a click that passes actionability can still land in the
 * window where it has just gone disabled (measured at ~2 in 10 under load —
 * `sketch-origin-constraint.spec.ts` carries the same guard and the reasoning).
 */
async function finishSketch(page: Page): Promise<void> {
  await expect
    .poll(
      async () => {
        if ((await page.getByTestId("sketch-strip").count()) === 0) return 0;
        await page.getByTestId("sketch-save").click({ timeout: 5_000 });
        await page
          .getByTestId("sketch-strip")
          .waitFor({ state: "detached", timeout: 5_000 })
          .catch(() => undefined);
        return page.getByTestId("sketch-strip").count();
      },
      { timeout: 60_000 },
    )
    .toBe(0);
}

/** Select the line under `pt` and drive its length to `mm` through the inline editor. */
async function driveLength(
  page: Page,
  at: Mapper,
  pt: Point,
  mm: number,
): Promise<void> {
  await clickPlane(page, at, pt);
  await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
  await page.keyboard.press("d");
  const input = page.getByTestId("dimension-input");
  await expect(input).toBeVisible();
  await input.fill(String(mm));
  await input.press("Enter");
  await expect(input).toHaveCount(0);
}

test.describe("SNAP-3 — a snap records the intent, not just the coordinate", () => {
  test("a corner drawn onto an endpoint stays joined through a re-drive", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Snapped corner");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // e1, off-grid and clear of the datum frame so the only thing that can
    // catch the next click is e1's own end.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10.4, y: 12.4 });
    await clickPlane(page, at, { x: 50.4, y: 12.4 });

    // e2 STARTS on e1's end — aimed 0.3 mm off, which only the endpoint snap
    // can close (the grid is off; see `calibratePlane`).
    await clickPlane(page, at, { x: 50.7, y: 12.6 });
    await clickPlane(page, at, { x: 50.4, y: 44.4 });
    await page.keyboard.press("Escape"); // back to the select tool

    await finishSketch(page);
    const authored = await sketchParams(page, token, part.id);
    expect(authored.entities.filter((e) => e.kind === "line")).toHaveLength(2);

    // THE DEFECT, inverted. Pre-fix this sketch carried ZERO constraints: the
    // corner was two numbers that happened to agree.
    expect(
      joins(
        authored.constraints,
        { entity: "e1", point: "end" },
        { entity: "e2", point: "start" },
      ),
    ).toBe(true);
    // Exactly one — a corner bound twice is the over-constraint this could
    // easily have shipped instead.
    expect(
      authored.constraints.filter((c) => c.kind === "coincident"),
    ).toHaveLength(1);

    // …and the coordinate really was copied exactly, so "it looked joined" was
    // true. That is why the constraint above is the only thing that can tell
    // the fixed build from the broken one at this point.
    const before = await solvedSketch(page, token, part.id);
    const cornerBefore = pointOf(before, { entity: "e1", point: "end" });
    expect(
      dist(cornerBefore, pointOf(before, { entity: "e2", point: "start" })),
    ).toBeLessThan(1e-6);

    // RE-DRIVE the edge the corner hangs off: 40 mm as drawn -> 25 mm.
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    const at2 = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await driveLength(page, at2, { x: 30.4, y: 12.4 }, 25);
    await expect(page.getByTestId("dro-solve")).toContainText("DOF", {
      timeout: 30_000,
    });
    await finishSketch(page);

    // THE ASSERTION THE COORDINATE COPY CANNOT SATISFY. Poll: the sketcher
    // persists on a debounce, so an evaluate fired too early answers for the
    // sketch as it was before the dimension landed.
    await expect
      .poll(
        async () => {
          const solved = await solvedSketch(page, token, part.id);
          const e1 = solved.find((e) => e.id === "e1");
          if (e1?.start === undefined || e1.end === undefined) return -1;
          return dist(e1.start, e1.end);
        },
        { timeout: 30_000 },
      )
      .toBeCloseTo(25, 3);

    const after = await solvedSketch(page, token, part.id);
    const corner = pointOf(after, { entity: "e1", point: "end" });
    const neighbour = pointOf(after, { entity: "e2", point: "start" });
    // Still one point, not two that used to agree.
    expect(dist(corner, neighbour)).toBeLessThan(1e-6);
    // …and the re-drive genuinely MOVED it, so "still joined" is not "nothing
    // happened". Pre-fix this is exactly where they separate: e1's end travels
    // 15 mm and e2's start stays where it was drawn.
    expect(dist(corner, cornerBefore)).toBeGreaterThan(1);
  });

  test("a corner drawn on the origin is GROUNDED there, and stays (SNAP-2)", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Grounded corner");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // The founder's gesture: start the profile ON the origin. Aimed 0.3 mm
    // off with the grid OFF, so only the origin magnet can land it on zero.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0.3, y: -0.2 });
    await clickPlane(page, at, { x: 40.4, y: 0.4 });
    await page.keyboard.press("Escape");

    await finishSketch(page);
    const authored = await sketchParams(page, token, part.id);

    // The datum is MATERIALISED on demand as pinned construction geometry —
    // the same lazy path the explicit verb uses, so nothing changes for a
    // sketch that never touches the frame.
    const origin = authored.entities.find((e) => e.id === "origin");
    expect(origin?.kind).toBe("point");
    expect(origin?.construction).toBe(true);
    expect(
      authored.constraints.some(
        (c) => c.kind === "fixed" && c.point?.entity === "origin",
      ),
    ).toBe(true);
    expect(
      joins(
        authored.constraints,
        { entity: "e1", point: "start" },
        { entity: "origin", point: "position" },
      ),
    ).toBe(true);

    const before = await solvedSketch(page, token, part.id);
    expect(
      dist(pointOf(before, { entity: "e1", point: "start" }), {
        x: 0,
        y: 0,
      }),
    ).toBeLessThan(1e-6);

    // Re-drive the edge. QA's repro drove a width 30 -> 40 and watched the part
    // slide to x = -7.1716; the grounded twin stays on zero.
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    const at2 = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await driveLength(page, at2, { x: 20.2, y: 0.2 }, 55);
    await expect(page.getByTestId("dro-solve")).toContainText("DOF", {
      timeout: 30_000,
    });
    await finishSketch(page);

    await expect
      .poll(
        async () => {
          const solved = await solvedSketch(page, token, part.id);
          const e1 = solved.find((e) => e.id === "e1");
          if (e1?.start === undefined || e1.end === undefined) return -1;
          return dist(e1.start, e1.end);
        },
        { timeout: 30_000 },
      )
      .toBeCloseTo(55, 3);

    const after = await solvedSketch(page, token, part.id);
    expect(
      dist(pointOf(after, { entity: "e1", point: "start" }), { x: 0, y: 0 }),
    ).toBeLessThan(1e-6);
  });

  test("the inferred coincident does not over-constrain — and a real redundancy still stops the user", async ({
    page,
  }) => {
    // THE RISK THIS TICKET CARRIES, in one test with both halves. Authoring
    // relations nobody asked for is how a fix like this breaks ordinary work,
    // so the first half proves a normal snapped draw-then-dimension flow stays
    // clean — and because "clean" is trivially achievable by silencing the
    // diagnosis, the second half proves the diagnosis still fires on the very
    // same sketch when the user really does over-constrain it.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Snap over-constraint");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10.4, y: 12.4 });
    await clickPlane(page, at, { x: 50.4, y: 12.4 });
    await clickPlane(page, at, { x: 50.7, y: 12.6 }); // snapped to e1's end
    await clickPlane(page, at, { x: 50.4, y: 44.4 });
    await page.keyboard.press("Escape");

    // The ordinary next moves: square the two edges up and size them.
    await clickPlane(page, at, { x: 30.4, y: 12.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("h");
    await clickPlane(page, at, { x: 50.4, y: 28.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("v");
    await driveLength(page, at, { x: 30.4, y: 12.4 }, 40);
    await driveLength(page, at, { x: 50.4, y: 28.4 }, 32);

    // Wait for the ANSWER, not for the absence of a banner: the solve is a
    // debounced round trip, so asserting the absences straight after the last
    // keystroke measures the gap before the reply and passes on a broken
    // build. Two joined, squared, sized lines: 8 DOF, and the coincident (2),
    // H (1), V (1) and two distances (2) take 6 of them.
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
    await expect(page.locator("[data-flagged]")).toHaveCount(0);
    // The positive control for "0 flagged": the glyphs really are rendered.
    await expect(page.getByTestId(/^glyph-/)).toHaveCount(5);

    // NOW over-constrain it for real. A horizontal line and a vertical one are
    // already perpendicular, so saying so is redundant — and the user CAN see
    // and delete this one, which is the property that makes it a stop rather
    // than a dead end.
    await clickPlane(page, at, { x: 30.4, y: 12.4 });
    await page.keyboard.down("Shift");
    await clickPlane(page, at, { x: 50.4, y: 28.4 });
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 ents");
    await page.keyboard.press("l"); // perpendicular

    await expect(page.getByTestId("solve-diagnostic")).toContainText(
      "Over-constrained",
      { timeout: 30_000 },
    );
    const flagged = page.locator("[data-flagged]");
    await expect(flagged.first()).toBeVisible();
    await expect(flagged.first()).toHaveAttribute("data-testid", /^glyph-/);
  });

  test("founder shots: the same corner, snapped and freehand", async ({
    page,
  }) => {
    // BEFORE / AFTER inside one run, which is the only honest way to shoot
    // this: the two states are pixel-identical in the geometry and differ only
    // in whether the join was recorded. The "before" is drawn with Ctrl held
    // (every snap suppressed) — the exact appearance of every corner in the
    // product until this landed: no glyph, and the strip's count unmoved.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Snap glyph shots");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10.4, y: 12.4 });
    await clickPlane(page, at, { x: 50.4, y: 12.4 });
    await clickFreehand(page, at, { x: 50.4, y: 12.4 }); // same point, no snap
    await clickFreehand(page, at, { x: 50.4, y: 44.4 });
    await page.keyboard.press("Escape");
    // COUNTED BY KIND, not by grand total. The subject is the corner — whether
    // the join was recorded — and since SNAP-5 the horizontal line also arrives
    // with its axis stated, which is a different fact authored by a different
    // feature. A total would redden here every time a neighbour authors
    // anything and would say nothing about the corner when it did.
    await expect(coincidentGlyph(page)).toHaveCount(0);

    await page.mouse.move(1400, 900); // park the cursor off the sheet
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-snap-coincident-before-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-snap-coincident-before-1280.png`,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });

    // AFTER: the identical gesture with the snap live. One "C" glyph appears at
    // the corner and the strip's count ticks — no new chrome was added for
    // this, and none was needed: the constraint layer already had a truthful
    // way to say it, and the defect was that it had nothing to say.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10.4, y: -18.4 });
    await clickPlane(page, at, { x: 50.4, y: -18.4 });
    await clickPlane(page, at, { x: 50.7, y: -18.2 }); // snapped
    await clickPlane(page, at, { x: 50.4, y: 8.4 });
    await page.keyboard.press("Escape");
    await expect(coincidentGlyph(page)).toHaveCount(1);
    await expect(coincidentGlyph(page)).toHaveText("C");

    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-snap-coincident-after-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-snap-coincident-after-1280.png`,
    });
    expect(token).not.toBe("");
  });
});

/**
 * SNAP-4 — TWO CORRECT FEATURES MEETING ON ONE POINT.
 *
 * Start a line ON the origin and SNAP-3 authors the coincident that grounds it.
 * Press X (Fix) on that same endpoint — correct in isolation — and the point
 * was pinned twice, so the sketch reported OVER-CONSTRAINED. The report was
 * TRUE, which is what made it bad: the user authored one of the two
 * constraints and the draw authored the other, so the tool was asking them to
 * delete something they never knowingly created.
 *
 * A `coincident` is a point-to-point identity, so a point joined to a pinned
 * one is not nearly fixed, it is fixed, and X now says so instead of restating
 * it. The two tests below are the fix and its guard: the second proves the
 * diagnosis was not bought by blinding it, because "no over-constraint" is
 * trivially achievable by never reporting one.
 */
test.describe("SNAP-4 — Fix on a point the draw already grounded", () => {
  test("is refused by name, and the sketch still converges", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Grounded fix");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // The ticket's gesture. Aimed 0.3 mm off zero with the grid OFF, so only
    // the origin magnet can land it — and at 37 deg, clear of SNAP-5's 3 deg
    // axis inference, so the only inferred relation on this sketch is the one
    // under test.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0.3, y: -0.2 });
    await clickPlane(page, at, { x: 40.4, y: 30.4 });
    await page.keyboard.press("Escape");

    // The setup is really the ticket's setup: the draw authored the join. The
    // sketch is NOT bound yet and therefore has no solve at all — an inferred
    // constraint is the tool recording the aim, not the user asking for a
    // relation (see `userConstrained`), so the Solve cell is not on screen.
    await expect(coincidentGlyph(page)).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveCount(0);

    await clickPlane(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");

    // THE FIX. Pre-fix there is no hint at all here — the verb succeeded — so
    // this assertion cannot pass on the old build for a timing reason: it
    // waits for text that is never written.
    await expect(page.getByTestId("constraint-hint")).toHaveText(
      "Already grounded on the Origin — the join there holds this point.",
    );
    // …and nothing was authored: pre-fix a second pin lands on this point and
    // a FIX glyph appears over the origin.
    await expect(fixGlyph(page)).toHaveCount(0);

    // THE STATUS THE USER READS, and the one this ticket is about. The
    // keystroke still binds the sketch (the `already` seam SNAP-5 put there),
    // so the solve runs and answers — pre-fix it answered OVER-CONSTRAINED
    // about a constraint the user never authored. Waiting for the WHOLE cell
    // rather than the absence of a banner: the solve is a debounced round
    // trip, and an assertion made in the gap before the reply passes on a
    // broken build.
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

    // THE FOUNDER SHOT, taken at exactly the moment the ticket is about — one
    // line drawn from the origin, one X pressed on that endpoint. The "before"
    // frame of the same moment is a flag-red OVER-CONSTRAINED cell, a banner
    // reading "a redundant constraint is flagged … Remove it", and a red FIX
    // over the origin the user never asked for.
    await page.mouse.move(1400, 900); // park the cursor off the sheet
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-snap-fix-grounded-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-snap-fix-grounded-1280.png`,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });

    // THE VERB IS NOT DISABLED, it is answered. The far end still fixes, and
    // takes the last two freedoms with it.
    await clickPlane(page, at, { x: 40.4, y: 30.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(fixGlyph(page)).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      {
        timeout: 30_000,
      },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

    await finishSketch(page);
    const authored = await sketchParams(page, token, part.id);

    // WHAT THE STATUS CLAIMED, CHECKED AGAINST WHAT WAS AUTHORED AND SOLVED.
    // Exactly one user pin (the far end) and the frame's own; the inferred
    // join SURVIVES — Fix refusing is not Fix quietly replacing it, which
    // would have thrown away the relation SNAP-3 exists to record.
    expect(
      authored.constraints.filter(
        (c) => c.kind === "fixed" && c.point?.entity !== "origin",
      ),
    ).toEqual([{ kind: "fixed", point: { entity: "e1", point: "end" } }]);
    expect(
      authored.constraints.some(
        (c) => c.kind === "fixed" && c.point?.entity === "origin",
      ),
    ).toBe(true);
    expect(
      joins(
        authored.constraints,
        { entity: "e1", point: "start" },
        { entity: "origin", point: "position" },
      ),
    ).toBe(true);

    // And "grounded" is a claim about the geometry, not a word in a hint: the
    // solver puts that endpoint on zero.
    const solved = await solvedSketch(page, token, part.id);
    expect(
      dist(pointOf(solved, { entity: "e1", point: "start" }), { x: 0, y: 0 }),
    ).toBeLessThan(1e-6);
  });

  test("a genuine over-constraint on the same sketch still stops the user", async ({
    page,
  }) => {
    // THE GUARD. Refusing X is only a fix if the diagnosis it removed was the
    // spurious one; a build that had simply stopped reporting redundancy would
    // pass the test above. So: same grounded start, same refusal — then a
    // redundancy the user really does author, on the same sketch, which must
    // still stop them with a glyph they can see and delete.
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Grounded fix control");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // The grounded line runs into the THIRD quadrant so it cannot cross the
    // corner drawn below, which lives where this file's other over-constraint
    // test already proves the gesture works.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0.3, y: -0.2 });
    await clickPlane(page, at, { x: -40.4, y: -30.4 });
    await page.keyboard.press("Escape");
    await clickPlane(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "Already grounded on the Origin",
    );
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: 30_000 },
    );

    // A corner clear of the frame: one horizontal edge, one vertical edge, the
    // second starting on the first's end. Escape FIRST — a refused verb leaves
    // the selection standing (it is still the user's pick), and with a
    // selection L is the perpendicular verb, not the Line tool.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10.4, y: 12.4 });
    await clickPlane(page, at, { x: 50.4, y: 12.4 });
    await clickPlane(page, at, { x: 50.7, y: 12.6 }); // snapped to the corner
    await clickPlane(page, at, { x: 50.4, y: 44.4 });
    await page.keyboard.press("Escape");

    // Stated explicitly, whether or not SNAP-5 got there first — either way
    // the sketch ends up holding both facts.
    await clickPlane(page, at, { x: 30.4, y: 12.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("h");
    await clickPlane(page, at, { x: 50.4, y: 28.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("v");

    // A horizontal edge and a vertical one are ALREADY perpendicular, so
    // saying so is redundant — and this one the user authored, can see, and
    // can delete.
    await clickPlane(page, at, { x: 30.4, y: 12.4 });
    await page.keyboard.down("Shift");
    await clickPlane(page, at, { x: 50.4, y: 28.4 });
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 ents");
    await page.keyboard.press("l"); // perpendicular

    await expect(page.getByTestId("solve-diagnostic")).toContainText(
      "Over-constrained",
      { timeout: 30_000 },
    );
    const flagged = page.locator("[data-flagged]");
    await expect(flagged.first()).toBeVisible();
    await expect(flagged.first()).toHaveAttribute("data-testid", /^glyph-/);
  });
});
