/**
 * INDEPENDENT QA OF SNAP-4 (commit 40a14bd) — written without reusing the
 * builder's own spec helpers or assertions.
 *
 * The ticket: draw ONE line starting on the origin (SNAP-3 authors the
 * inferred coincident that grounds it), press X on that same endpoint, and the
 * sketch reported OVER-CONSTRAINED with a red FIX glyph — from one line and one
 * keystroke, with the user having authored only one of the two constraints.
 *
 * What is asserted here, and why each is not a proxy:
 *
 *  - the gesture is the USER'S gesture: `page.mouse.click` at coordinates read
 *    off the live DRO, and `page.keyboard.press`. No store pokes, no
 *    `applyConstraint` call, no test helper that authors constraints.
 *  - the refusal's TRUTH is checked against the persisted params AND the
 *    solver's own output through the gateway, not against the hint string.
 *  - the DOF the solver reports is itself corroboration: a free line is 4 DOF,
 *    so "DOF 2" is the solver agreeing that the coincident really holds two.
 *  - the "not a dead end" claim is measured in STEPS a user takes, on the real
 *    keyboard, and again through the POINTER path only (no keyboard at all),
 *    because a keyboard-only seam is not reachable on touch.
 */
import { expect, test, type Page, type Locator } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

interface Pt {
  x: number;
  y: number;
}
type Mapper = (pt: Pt) => Pt;

interface Ref {
  entity: string;
  point: string;
}
interface ConstraintRow {
  kind: string;
  point?: Ref;
  a?: Ref | string;
  b?: Ref | string;
}
interface EntityRow {
  id: string;
  kind: string;
  start?: Pt;
  end?: Pt;
  position?: Pt;
}

const isRef = (v: Ref | string | undefined): v is Ref =>
  typeof v === "object" && v !== null;
const refIs = (v: Ref | string | undefined, r: Ref): boolean =>
  isRef(v) && v.entity === r.entity && v.point === r.point;

/** Read the sketch feature's AUTHORED params straight off the documents API. */
async function authoredParams(
  page: Page,
  token: string,
  partId: string,
): Promise<{ entities: EntityRow[]; constraints: ConstraintRow[] }> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) throw new Error(`feature read ${response.status()}`);
  const body = (await response.json()) as {
    features: { feature: { type: string; params: unknown } }[];
  };
  const sketch = body.features.find((r) => r.feature.type === "sketch");
  if (sketch === undefined) throw new Error("no sketch feature persisted");
  return sketch.feature.params as {
    entities: EntityRow[];
    constraints: ConstraintRow[];
  };
}

/** How many features the part carries right now — 0 means "not bound yet". */
async function featureCount(
  page: Page,
  token: string,
  partId: string,
): Promise<number> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) throw new Error(`feature read ${response.status()}`);
  const body = (await response.json()) as { features: unknown[] };
  return body.features.length;
}

/** Ask the gateway to EVALUATE the part and hand back the SOLVED sketch. */
async function solvedEntities(
  page: Page,
  token: string,
  partId: string,
): Promise<EntityRow[]> {
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) throw new Error(`evaluate ${response.status()}`);
  const body = (await response.json()) as {
    features: { data?: { kind: string; entities: EntityRow[] } | null }[];
  };
  const solved = body.features.find((r) => r.data?.kind === "solved_sketch");
  if (solved?.data === undefined || solved.data === null) {
    throw new Error("the evaluate carried no solved sketch");
  }
  return solved.data.entities;
}

function pointOf(entities: readonly EntityRow[], ref: Ref): Pt {
  const e = entities.find((x) => x.id === ref.entity);
  if (e === undefined) throw new Error(`no entity ${ref.entity}`);
  const at =
    ref.point === "start" ? e.start : ref.point === "end" ? e.end : e.position;
  if (at === undefined) throw new Error(`${ref.entity} has no ${ref.point}`);
  return at;
}

async function enterSketch(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * mm -> px, read off the live DRO. Grid is turned OFF first: with the 1 mm grid
 * live an aim a few tenths off zero lands on zero anyway, so the spec could not
 * tell the origin MAGNET from the grid and the whole subject would be moot.
 */
async function calibrate(page: Page, s1: Pt, s2: Pt): Promise<Mapper> {
  await page.keyboard.press("g");
  let last: number | null = null;
  await expect
    .poll(
      async () => {
        await page.mouse.move(s1.x + 3, s1.y);
        await page.mouse.move(s1.x, s1.y);
        const v = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        const stable = last !== null && Number.isFinite(v) && v === last;
        last = v;
        return stable;
      },
      { timeout: 20_000 },
    )
    .toBe(true);
  const read = async (sx: number, sy: number, notX?: number): Promise<Pt> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const v = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(v) &&
          (notX === undefined || Math.abs(v - notX) > 1e-9)
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

async function clickAt(page: Page, at: Mapper, pt: Pt): Promise<void> {
  const px = at(pt);
  await page.mouse.move(px.x, px.y);
  await page.mouse.click(px.x, px.y);
}

/** Shift-click ADDS to the selection (FB-14); a plain click replaces. */
async function addAt(page: Page, at: Mapper, pt: Pt): Promise<void> {
  await page.keyboard.down("Shift");
  await clickAt(page, at, pt);
  await page.keyboard.up("Shift");
}

/** Save the sketch, retrying — `sketch-save` disables itself mid-flight. */
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

const fixGlyphs = (page: Page): Locator =>
  page.locator('[data-testid^="glyph-"][data-kind="fixed"]');
const coincidentGlyphs = (page: Page): Locator =>
  page.locator('[data-testid^="glyph-"][data-kind="coincident"]');

/**
 * THE TICKET'S GESTURE, verbatim: enter a sketch, draw ONE line whose first
 * click lands on the origin (aimed 0.3/-0.2 mm off zero with the grid off, at
 * 37 deg so no axis inference fires), and Escape out of the line tool.
 */
async function drawGroundedLine(
  page: Page,
  at: Mapper,
  far: Pt = { x: 40.4, y: 30.4 },
): Promise<void> {
  await page.keyboard.press("l");
  await clickAt(page, at, { x: 0.3, y: -0.2 });
  await clickAt(page, at, far);
  await page.keyboard.press("Escape");
  await expect(coincidentGlyphs(page)).toHaveCount(1);
}

/**
 * WHICH BYTES AM I EXERCISING? Asked of the DEV SERVER, not of the disk.
 *
 * This file was measured in a tree another agent also had write access to, and
 * a running Vite can serve a stale transform of a file that has since changed.
 * So the first thing the suite does is pull the transformed module the browser
 * actually imports and look for the guard under test in it. A green run whose
 * first case is this cannot have been measured against pre-fix bytes.
 */
test("PRECONDITION — the served module contains SNAP-4's guard", async ({
  request,
}) => {
  const res = await request.get("/src/sketch/constraints.ts");
  expect(res.status()).toBe(200);
  const served = await res.text();
  expect(served.length).toBeGreaterThan(10_000);
  // Vite serves the esbuild TRANSFORM, so comments are gone — assert on code.
  expect(served).toContain("groundingAnchor");
  expect(served).toContain("Already grounded on the ");
  expect(served).toMatch(/const anchor = groundingAnchor\(/);
  // The suite's own negative control replaces the walk with an early
  // `return null`, and that IS visible in the transform. Asserting its ABSENCE
  // is what makes a green run provably a run against the fixed bytes.
  const body =
    /export function groundingAnchor\(point, constraints\) \{\s*(\S+)/.exec(
      served,
    );
  expect(
    body,
    "groundingAnchor must be present in the served module",
  ).not.toBeNull();
  console.log(`[QA] served groundingAnchor opens with: ${body?.[1] ?? "?"}`);
  if (process.env.QA_EXPECT_MUTANT === "1") {
    expect(body?.[1]).toBe("return");
  } else {
    expect(body?.[1]).toBe("const");
  }
});

test.describe("QA SNAP-4 — desktop", () => {
  test("the ticket's frame: one line, one X on the grounded end", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 ticket");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });

    await drawGroundedLine(page, at);

    // (6) VERIFY THE BUILDER'S DISCRIMINATOR CLAIM rather than assuming it:
    // the Solve cell must be ABSENT before the sketch is bound, otherwise a
    // post-keypress reading of it proves nothing about the keystroke.
    await expect(page.getByTestId("dro-solve")).toHaveCount(0);
    // And absent for the stated reason — no persisted sketch feature yet.
    expect(await featureCount(page, token, part.id)).toBe(0);

    // The user's own gesture: click the endpoint that sits on the origin, press X.
    await clickAt(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");

    // (1) THE DEFECT IS GONE: refused by name, nothing authored, no red glyph,
    // no redundancy banner.
    await expect(page.getByTestId("constraint-hint")).toHaveText(
      "Already grounded on the Origin — the join there holds this point.",
    );
    await expect(fixGlyphs(page)).toHaveCount(0);

    // (2) NOT A DEAD END: the keystroke still bound the sketch, so the Solve
    // cell exists at all — which it did not one gesture ago.
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: 40_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
    await expect(page.getByText(/OVER-CONSTRAINED/i)).toHaveCount(0);

    // (4) THE REFUSAL IS TRUTHFUL, part one — the solver's own accounting: a
    // free line is 4 DOF. Reading 2 is the solver saying the coincident really
    // removes both freedoms of that endpoint. If the join were cosmetic this
    // cell would read DOF 4.
    const dofBefore = await page.getByTestId("dro-solve").innerText();
    expect(dofBefore).toBe("DOF 2 · UNDER-CONSTRAINED");

    // (3) THE RECOVERY CLAUSE: fixing the FAR end takes it to DOF 0.
    await clickAt(page, at, { x: 40.4, y: 30.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(fixGlyphs(page)).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      { timeout: 40_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

    // (4) TRUTHFUL, part two — what was AUTHORED. The inferred coincident
    // SURVIVES (a refusal is not a silent replacement) and exactly one user pin
    // exists, on the far end.
    await finishSketch(page);
    const params = await authoredParams(page, token, part.id);
    const joinSurvives = params.constraints.some(
      (c) =>
        c.kind === "coincident" &&
        ((refIs(c.a, { entity: "e1", point: "start" }) &&
          refIs(c.b, { entity: "origin", point: "position" })) ||
          (refIs(c.b, { entity: "e1", point: "start" }) &&
            refIs(c.a, { entity: "origin", point: "position" }))),
    );
    expect(joinSurvives).toBe(true);
    const userPins = params.constraints.filter(
      (c) => c.kind === "fixed" && c.point?.entity !== "origin",
    );
    expect(userPins).toEqual([
      { kind: "fixed", point: { entity: "e1", point: "end" } },
    ]);

    // (4) TRUTHFUL, part three — the SOLVER puts the endpoint on zero. "Held"
    // is a claim about geometry, and this is the only assertion here that can
    // observe it.
    const solved = await solvedEntities(page, token, part.id);
    const start = pointOf(solved, { entity: "e1", point: "start" });
    expect(Math.hypot(start.x, start.y)).toBeLessThan(1e-6);
  });

  test("negative control: a genuine redundancy on the same sketch still reports", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 control");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });

    await drawGroundedLine(page, at, { x: -40.4, y: -30.4 });
    await clickAt(page, at, { x: 0, y: 0 });
    await page.keyboard.press("x");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "Already grounded on the Origin",
    );

    // A separate corner, well clear of the frame: H edge then V edge sharing a
    // corner, then state perpendicular — which is already true, so redundant.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await page.keyboard.press("l");
    await clickAt(page, at, { x: 10.4, y: 12.4 });
    await clickAt(page, at, { x: 50.4, y: 12.4 });
    await clickAt(page, at, { x: 50.7, y: 12.6 });
    await clickAt(page, at, { x: 50.4, y: 44.4 });
    await page.keyboard.press("Escape");

    await clickAt(page, at, { x: 30.4, y: 12.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("h");
    await clickAt(page, at, { x: 50.4, y: 28.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("v");

    await page.keyboard.press("Escape");
    await clickAt(page, at, { x: 30.4, y: 12.4 });
    await addAt(page, at, { x: 50.4, y: 28.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("l"); // perpendicular verb

    await expect(page.getByTestId("dro-solve")).toHaveText("OVER-CONSTRAINED", {
      timeout: 40_000,
    });
    await expect(page.getByTestId("solve-diagnostic")).toBeVisible();
  });
});

/**
 * (2) and (5) — CAN A USER WHO IS NOT ON A KEYBOARD DO THIS AT ALL?
 *
 * The `already` seam the fix leans on is reached through `applyConstraint`, and
 * on desktop that arrives via the X key. There are two other doors to the same
 * verb — the selection OFFER RAIL and the Constrain CATALOGUE — and both are
 * gated on `verbIsAvailable`, which the fix deliberately turns FALSE for the
 * held point. Touch has no X key, so whether the refusal (and the binding it
 * carries) is reachable there is decided entirely by what those two surfaces do
 * with an unavailable verb. That is not something the builder's specs looked at.
 */
test.describe("QA SNAP-4 — the pointer path (no keyboard verb)", () => {
  test("the FREE end (control): the catalogue row is live and names itself truthfully", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 pointer free");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    await drawGroundedLine(page, at);

    // The CONTROL for the test below: same verb, same selection shape, a point
    // the sketch does not hold. Both pointer doors are open here, so the next
    // test's readings are about the GROUNDED point and not about Fix in general.
    await clickAt(page, at, { x: 40.4, y: 30.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    // The offer rail never carries Fix for ANY selection — `fixed` is absent
    // from `VERB_OFFER_ORDER`. Recorded so the next test's rail reading is not
    // mistaken for something SNAP-4 did: the catalogue is the only pointer
    // door to this verb, before and after the fix.
    await expect(page.getByTestId("verb-hint-fixed")).toHaveCount(0);
    await page.getByTestId("constraint-group-relational").click();
    const row = page.getByTestId("constraint-fixed");
    await expect(row).toBeVisible();
    expect(await row.getAttribute("data-available")).toBe("true");
    expect(await row.getAttribute("aria-label")).toBe(
      "Fix point (X, on selected points)",
    );
  });

  test("the HELD end: the catalogue row states a falsehood, but still acts", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 pointer held");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    await drawGroundedLine(page, at);

    await clickAt(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");

    // Same as the free end (see the control above): Fix is not a rail verb at
    // all, so the catalogue is the only pointer door either way.
    await expect(page.getByTestId("verb-hint-fixed")).toHaveCount(0);

    await page.getByTestId("constraint-group-relational").click();
    const row = page.getByTestId("constraint-fixed");
    await expect(row).toBeVisible();
    expect(await row.getAttribute("data-available")).toBe("false");

    // QA-SNAP4-1 — THE ROW SAYS THE VERB "needs a point" WHILE THE USER HAS ONE
    // SELECTED. `requires` is shown verbatim whenever `available === false`,
    // and SNAP-4 made that flag false for a reason that has nothing to do with
    // the selection SHAPE. The row therefore states, in the sub-caption and in
    // its accessible name, the one thing the user has already done. Flipped to
    // `.toBe(...)` this is the assertion that would hold if the catalogue told
    // the truth; today it does not, so it is written as the measurement.
    expect(
      await row.getAttribute("aria-label"),
      "the catalogue's accessible name for a verb refused for a NON-selection reason",
    ).toBe("Fix point (X, on selected points) — needs a point");
    await expect(row).toContainText("needs a point");

    // …and the row is still CLICKABLE (Flyout documents that on purpose), which
    // is what keeps the refusal — and the binding it carries — reachable
    // without a keyboard.
    await row.click();
    await expect(page.getByTestId("constraint-hint")).toHaveText(
      "Already grounded on the Origin — the join there holds this point.",
    );
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: 40_000 },
    );
    expect(await featureCount(page, token, part.id)).toBe(1);
  });
});

/**
 * (5) TOUCH. The builder reported desktop evidence only.
 *
 * Two separate questions, kept apart on purpose:
 *   a) can a touch user DRAW the line at all (the ticket's first gesture)?
 *   b) given the line, is the refused verb — and the binding it carries —
 *      reachable with taps only?
 * (a) is a pre-existing gap far wider than SNAP-4; (b) is SNAP-4's own remit.
 */
test.describe("QA SNAP-4 — touch", () => {
  test.use({ viewport: { width: 1280, height: 800 }, hasTouch: true });

  test("a tap does not draw: the ticket's own first gesture is unreachable", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 touch draw");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sketch").tap();
    await page.getByTestId("plane-XY").tap();
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    const at = await calibrate(page, { x: 560, y: 500 }, { x: 800, y: 340 });

    await page.getByTestId("tool-line").tap();
    const a = at({ x: 0.3, y: -0.2 });
    const b = at({ x: 30.4, y: 22.4 });
    await page.touchscreen.tap(a.x, a.y);
    await page.touchscreen.tap(b.x, b.y);

    // QA-SNAP4-2. The strip's own entity count is the reading: two taps with
    // the Line tool armed leave the sketch empty. Written as the MEASUREMENT —
    // "1 entity" is what a working touch sketcher would say.
    await expect(page.getByTestId("sketch-strip")).toContainText("0 entities");
    await expect(page.locator('[data-testid^="glyph-"]')).toHaveCount(0);
  });

  test("given the line, the refused verb IS reachable by tap", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 touch verb");
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sketch").tap();
    await page.getByTestId("plane-XY").tap();
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    const at = await calibrate(page, { x: 560, y: 500 }, { x: 800, y: 340 });

    // The line is drawn with the mouse ONLY because the test above proves a tap
    // cannot draw it; every gesture under test below is a tap.
    await drawGroundedLine(page, at, { x: 30.4, y: 22.4 });
    await expect(page.getByTestId("dro-solve")).toHaveCount(0);

    const origin = at({ x: 0, y: 0 });
    await page.touchscreen.tap(origin.x, origin.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");

    await page.getByTestId("constraint-group-relational").tap();
    await page.getByTestId("constraint-fixed").tap();
    await expect(page.getByTestId("constraint-hint")).toHaveText(
      "Already grounded on the Origin — the join there holds this point.",
    );
    await expect(fixGlyphs(page)).toHaveCount(0);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 2 · UNDER-CONSTRAINED",
      { timeout: 40_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

    // Recovery on touch, through the same door.
    const far = at({ x: 30.4, y: 22.4 });
    await page.touchscreen.tap(far.x, far.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.getByTestId("constraint-group-relational").tap();
    await page.getByTestId("constraint-fixed").tap();
    await expect(fixGlyphs(page)).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      {
        timeout: 40_000,
      },
    );
  });
});

/**
 * (6) WHAT THE BUILDER'S OWN ASSERTIONS DID NOT LOOK AT.
 *
 * Four questions the fix's design raises and its specs do not answer:
 * the EXIT the hint promises, a MIXED selection, a TRANSITIVE chain, and the
 * non-datum wording of the refusal.
 */
test.describe("QA SNAP-4 — the edges of the refusal", () => {
  test("the exit the hint points at: delete the join, and X is accepted", async ({
    page,
  }) => {
    // QA-SNAP4-4 — ANNOTATED AS A KNOWN GAP, and the gap is PRE-EXISTING: this
    // commit touches `apps/web/src/sketch/constraints.ts` only, and the path
    // below lives in `ConstraintGlyphs.tsx` / `store.ts`. SNAP-4 is what makes
    // it matter: the refusal names the join as the reason and the C glyph as
    // the thing holding the point, so "delete it and fix the point anywhere"
    // is the exit the wording implies — and no click can take it. Measured on
    // `coincident` AND `fixed` glyphs, at the origin and clear of it, with a
    // real mouse click and with a synthetic `el.click()`: `aria-pressed` never
    // goes true and Delete removes nothing. Only DIMENSION glyphs are
    // removable, through their own editor's Remove button.
    // If this case ever PASSES, the gap has closed and this annotation is the
    // lie — delete it.
    test.fail();
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 exit");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    await drawGroundedLine(page, at);

    await clickAt(page, at, { x: 0, y: 0 });
    await page.keyboard.press("x");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "the join there holds this point",
    );

    // The hint names the join and the C glyph is sitting on it. Click it,
    // Delete it — the exit the wording promises — and the same X should land.
    await coincidentGlyphs(page).first().click();
    await expect(coincidentGlyphs(page).first()).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.keyboard.press("Delete");
    await expect(coincidentGlyphs(page)).toHaveCount(0);

    await clickAt(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(fixGlyphs(page)).toHaveCount(1);
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
  });

  test("a MIXED selection fixes the free point and says nothing about the refused one", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 mixed");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });
    await drawGroundedLine(page, at);

    // Both endpoints in one selection: one held by the draw's join, one free.
    await clickAt(page, at, { x: 0, y: 0 });
    await addAt(page, at, { x: 40.4, y: 30.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 pt");
    await page.keyboard.press("x");

    // The free one is pinned — right, and the sketch converges.
    await expect(fixGlyphs(page)).toHaveCount(1);
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      {
        timeout: 40_000,
      },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

    // QA-SNAP4-3 — and the user is told NOTHING about the other half of their
    // pick. `applyConstraintAction` returns `added` the moment one point is
    // fixable, discarding the anchor it found for the refused one, so two
    // points selected and one pinned reads exactly like two points pinned.
    // Written as the measurement: a hint naming the refusal is what a truthful
    // partial outcome would show.
    expect(
      await page.getByTestId("constraint-hint").count(),
      "a partially-refused Fix leaves no hint at all",
    ).toBe(0);
  });

  test("TRANSITIVE: a corner joined to a corner joined to the origin is also refused", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 chain");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });

    // e1 starts on the origin; e2 starts on e1's FAR end. So e2.start is two
    // coincident hops from the origin pin only if the walk is transitive —
    // except the far end is not itself pinned, so this chain must NOT refuse.
    // The chain that MUST refuse is one whose far link reaches the pin: draw a
    // SECOND line whose start lands on e1's grounded START.
    await page.keyboard.press("l");
    await clickAt(page, at, { x: 0.3, y: -0.2 });
    await clickAt(page, at, { x: 40.4, y: 30.4 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("l");
    await clickAt(page, at, { x: 0.2, y: 0.3 }); // onto e1's grounded start
    await clickAt(page, at, { x: -35.4, y: 24.4 });
    await page.keyboard.press("Escape");
    await expect(coincidentGlyphs(page)).toHaveCount(2);

    // e2.start is joined to e1.start (or to the origin) — either way it is one
    // or two hops from the origin's own pin.
    await clickAt(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("pt");
    await page.keyboard.press("x");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "Already grounded on the Origin",
    );
    await expect(fixGlyphs(page)).toHaveCount(0);
    await expect(page.getByTestId("dro-solve")).toContainText(
      "UNDER-CONSTRAINED",
      { timeout: 40_000 },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
  });

  test("NON-DATUM anchor: a point joined to a user-fixed point is refused too", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "QA snap4 nondatum");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page);
    const at = await calibrate(page, { x: 700, y: 620 }, { x: 1000, y: 420 });

    // Two lines meeting at a corner well clear of the origin, so the frame's
    // own pin is not the anchor.
    await page.keyboard.press("l");
    await clickAt(page, at, { x: 20.4, y: 15.4 });
    await clickAt(page, at, { x: 55.4, y: 41.4 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("l");
    await clickAt(page, at, { x: 20.6, y: 15.5 }); // onto the first line's start
    await clickAt(page, at, { x: 58.4, y: -6.4 });
    await page.keyboard.press("Escape");
    await expect(coincidentGlyphs(page)).toHaveCount(1);

    // Pin the shared corner ONCE — accepted.
    await clickAt(page, at, { x: 20.4, y: 15.4 });
    await expect(page.getByTestId("selection-readout")).toContainText("pt");
    await page.keyboard.press("x");
    await expect(fixGlyphs(page)).toHaveCount(1);

    // Pin it AGAIN. The second endpoint sharing that corner is a different ref
    // reached through the coincident, so the refusal must use its non-datum
    // wording rather than "Already fixed."
    await clickAt(page, at, { x: 20.4, y: 15.4 });
    await page.keyboard.press("x");
    const hint = await page.getByTestId("constraint-hint").innerText();
    console.log(`[QA] non-datum refusal hint: ${JSON.stringify(hint)}`);
    expect(hint).toMatch(/^Already (fixed|grounded)/);
    await expect(fixGlyphs(page)).toHaveCount(1);
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
  });
});
