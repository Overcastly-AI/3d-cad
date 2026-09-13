// The TOKENS subpath, not the package root: the root re-exports the Tailwind
// preset, whose `tailwindcss/plugin` import Node's ESM loader cannot resolve
// (that package has no `exports` map), so importing it here fails the whole
// spec file at collection with "No tests found".
import { proposal } from "@loft/design/tokens";

import { partVerbKey } from "../src/shortcuts/registry";

import { expect, test, type Page } from "./fixtures";
import { createFeature, rectangleSketch, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * FLOW-B1 — the solve itself writes a proposal onto the profile.
 *
 * The measurement this answers (`AUDIT-FLOW-2026-09`): across three parts
 * modelled end to end, **8 of the 15 recorded hunts were this one transition** —
 * a sketch solves, the app knows perfectly well that the next verb is Extrude
 * on that profile, and the hand leaves the model for the toolbar to fetch it.
 *
 * What the suite has to prove, in the order it matters:
 *
 *  1. **The chip appears without the pointer.** There is no hover in this path;
 *     the trigger is the state transition. So every assertion here is made with
 *     the mouse parked where the flow left it.
 *  2. **Accepting PRE-SELECTS.** The chip promises "Extrude, on this sketch",
 *     so the editor must open holding that sketch — not the tree's default,
 *     which is a different sketch the moment there is more than one. This is
 *     the assertion that catches the failure the whole cross-agent key contract
 *     exists to prevent: if the note's capture-phase binding does not
 *     `preventDefault()`, `PartPage`'s bubble-phase opener runs too and
 *     `setEditor`s over the top with the DEFAULT profile. The editor is open
 *     either way and looks right — only the noun is wrong.
 *  3. **It can be ignored cheaply**, and taking that option teaches the app:
 *     one offer per subject, per session.
 *  4. **One note at a time, pointer first.**
 *
 * Nothing here uses `click({ force: true })`: the chip's centre is checked with
 * `elementFromPoint` and clicked with a real mouse, because a forced click
 * skips the only check that asks whether a user could have hit the thing.
 *
 * WHAT IS DELIBERATELY NOT HERE: the refusal. A profile whose centroid does not
 * land inside the frame gets no note at all (`loopAnchor`), and that branch is
 * covered by arithmetic in `proposalAnchor.test.ts` rather than by a browser,
 * because reaching it in a browser means pinning a CAMERA POSE — measured while
 * writing this suite: the same 30 mm profile 40 mm off-origin is anchored in one
 * pose and out of the frustum in another, so a spec asserting either answer
 * would be asserting the fly-back's timing. The layer stamps
 * `data-proposal-anchored` for exactly this reason: when it does refuse, a
 * reader can tell a refusal from a bug without a debugger.
 */

/** The letter the chip must print — from the registry, never a literal. */
const EXTRUDE_KEY = partVerbKey("extrude") as string;

/** Park the pointer well away from the model so no hover offer can be written. */
async function parkPointer(page: Page): Promise<void> {
  const frame = await page.getByTestId("viewport").boundingBox();
  if (frame === null) throw new Error("the viewport has no box");
  await page.mouse.move(frame.x + frame.width - 8, frame.y + 8);
}

/** Open a part that already holds `Sketch1` (20x20) and `Sketch2` (30x30). */
async function seedTwoSketches(
  page: Page,
): Promise<{ partId: string; sketch1: string; sketch2: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Solve proposal");
  const first = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const second = await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(-28, -28, 24, 24),
    },
    expected_tree_version: first.tree_version,
  });
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("viewport")).toBeVisible();
  await expect(page.getByTestId("feature-row")).toHaveCount(2);
  return {
    partId: part.id,
    sketch1: first.feature.id,
    sketch2: second.feature.id,
  };
}

/**
 * Re-open a saved sketch from its tree row and finish it — the cheapest REAL
 * solve transition there is, and the one that discriminates "the sketch that
 * just solved" from "the last sketch in the tree".
 */
async function reopenAndFinish(page: Page, row: number): Promise<void> {
  await page.getByTestId("feature-row").nth(row).click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-strip")).toBeVisible();
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await parkPointer(page);
}

/** Draw a rectangle in the open sketcher and finish it, all by hand. */
async function drawRectangleAndFinish(page: Page): Promise<void> {
  const frame = await page.getByTestId("viewport").boundingBox();
  if (frame === null) throw new Error("the viewport has no box");
  const at = (fx: number, fy: number) => ({
    x: Math.round(frame.x + frame.width * fx),
    y: Math.round(frame.y + frame.height * fy),
  });
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const start = at(0.36, 0.36);
  const end = at(0.62, 0.64);
  await page.mouse.click(start.x, start.y);
  await page.mouse.move(end.x, end.y);
  await page.mouse.click(end.x, end.y);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Where the chip is, and whether a real pointer could reach its centre. */
async function chipReach(
  page: Page,
  testId: string,
): Promise<{
  box: { x: number; y: number; width: number; height: number };
  at: string;
}> {
  const box = await page.getByTestId(testId).boundingBox();
  if (box === null) throw new Error(`${testId} has no box`);
  const at = await page.evaluate(
    ({ x, y }) => {
      const hit = document.elementFromPoint(x, y);
      return hit === null
        ? "(nothing)"
        : (hit.closest("[data-testid]")?.getAttribute("data-testid") ??
            hit.tagName);
    },
    { x: box.x + box.width / 2, y: box.y + box.height / 2 },
  );
  return { box, at };
}

/**
 * Rest the pointer on the body, wherever the camera put it.
 *
 * Spiralling out from the centre rather than assuming a point: the fit framed
 * the body there, so the first hit is near the middle of a large face instead
 * of on an edge — and the viewport publishes which face it is addressing, so
 * this asks the app rather than guessing.
 */
async function restOnBody(page: Page): Promise<void> {
  const frame = await page.getByTestId("viewport").boundingBox();
  if (frame === null) throw new Error("the viewport has no box");
  const cx = frame.x + frame.width / 2;
  const cy = frame.y + frame.height / 2;
  const viewport = page.getByTestId("viewport");
  for (const radius of [0, 40, 80, 120]) {
    for (const [dx, dy] of [
      [0, 0],
      [0, radius],
      [radius, 0],
      [0, -radius],
      [-radius, 0],
    ] as const) {
      const x = Math.round(cx + dx);
      const y = Math.round(cy + dy);
      await page.mouse.move(x + 1, y);
      await page.mouse.move(x, y);
      if ((await viewport.getAttribute("data-hovered-face")) !== null) return;
    }
  }
  throw new Error("no point of the body could be found to rest on");
}

test.describe("a solved sketch proposes its extrude", () => {
  test("the offer is written on the profile, and its key opens Extrude holding it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "First sketch");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport")).toBeVisible();

    // An empty part offers nothing: there is nothing to extrude yet.
    await expect(page.getByTestId("extrude-proposal")).toHaveCount(0);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await drawRectangleAndFinish(page);

    // --- the offer, with the mouse exactly where the sketch left it ---------
    // No park, no jiggle, no hover: if this passes, the note was written by the
    // TRANSITION. (The last click of the rectangle left the pointer inside the
    // viewport, so a note that needed a pointer event would have nothing.)
    const chip = page.getByTestId("extrude-proposal");
    await expect(chip).toBeVisible({ timeout: 30_000 });
    await expect(chip).toHaveAttribute("data-proposal-verb", "extrude");
    await expect(chip).toHaveAttribute("data-proposal-subject", "Sketch1");
    // The NOUN is carried in words in the accessible name, and only there —
    // the chip says the verb alone because the leader names the noun in space.
    await expect(chip).toHaveAttribute("aria-label", "Extrude Sketch1");
    // The chip PRINTS the key, which is the only reason a mouse user would
    // ever learn it — and it prints the one the registry actually binds, so
    // the glyph and the binding cannot drift.
    await expect(chip).toContainText(EXTRUDE_KEY.toUpperCase());
    // A screen-reader user is TOLD, because this note arrived without them
    // doing anything to summon it.
    await expect(page.getByTestId("proposal-announcement")).toHaveText(
      "Extrude Sketch1",
    );

    // --- it is a real target, at the size the token says -------------------
    const { box, at } = await chipReach(page, "extrude-proposal");
    expect(box.width).toBeCloseTo(proposal.chipWidth, 0);
    expect(box.height).toBeGreaterThanOrEqual(proposal.chipHeight);
    // …and NOTHING INSIDE IT IS BEING SQUEEZED. The assertion above compares
    // the box against the token the placement maths uses — the drift that
    // matters — but both sides move together, so it cannot see a chip too
    // narrow for what it says. This can: at the old 112 the same content
    // measured 110 px of 110 available, and a flex row with no slack does not
    // overflow — it SHRINKS ITS ITEMS. The verb glyph came out at 11.5 px
    // instead of the 13 it was asked for, which looks like nothing at all in a
    // screenshot. `EXTRUDE` is the longest verb this note carries and is the
    // whole reason `chipWidth` went 112 -> 120.
    const fit = await page.getByTestId("extrude-proposal").evaluate((node) => ({
      scroll: node.scrollWidth,
      client: node.clientWidth,
      glyph: node.querySelector("svg")?.getBoundingClientRect().width ?? 0,
    }));
    expect(
      fit.scroll,
      `the chip clips its own contents: ${JSON.stringify(fit)}`,
    ).toBeLessThanOrEqual(fit.client);
    expect(
      fit.glyph,
      `the chip is squeezing its verb glyph: ${JSON.stringify(fit)}`,
    ).toBeGreaterThanOrEqual(13);
    expect(
      at,
      "elementFromPoint at the chip's centre resolves to something else, so a " +
        "real mouse cannot hit it however green a forced click would be",
    ).toBe("extrude-proposal");
    // The leader has to point at something: the anchor dot is drawn inside the
    // frame, and the chip hangs off it rather than floating anywhere.
    const frame = await page.getByTestId("viewport").boundingBox();
    expect(frame).not.toBeNull();

    // --- accept with the key the chip printed ------------------------------
    await page.keyboard.press(EXTRUDE_KEY);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    // THE POINT OF THE WHOLE ITEM: the noun arrived with the verb.
    await expect(page.getByTestId("extrude-profile")).toHaveText("Sketch1");
    // …and the caret is already in the one field this command needs.
    const focused = await page.evaluate(() =>
      document.activeElement?.getAttribute("data-testid"),
    );
    expect(focused, "the distance field must be ready to type into").toBe(
      "extrude-distance",
    );
    // The offer is gone: a command is open, so nothing may be proposed.
    await expect(page.getByTestId("extrude-proposal")).toHaveCount(0);

    // Accepting OPENS; it does not commit. One more Enter does.
    await expect(page.getByTestId("body-inspector")).toHaveCount(0);
    await page.getByTestId("extrude-distance").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
  });

  test("it names the sketch that just solved, not the last one in the tree", async ({
    page,
  }) => {
    // Two sketches, so "the sketch that solved" and "the tree's default
    // profile" are different features. Re-solving Sketch1 while Sketch2 sits
    // above it is the case where a chip that merely opened the generic Extrude
    // command would be silently wrong — and it is also the only way to see
    // whether the note's key binding actually consumed the key, because the
    // bubble-phase opener would seed Sketch2.
    const ids = await seedTwoSketches(page);
    await reopenAndFinish(page, 0);

    const chip = page.getByTestId("extrude-proposal");
    await expect(chip).toBeVisible({ timeout: 30_000 });
    await expect(chip).toHaveAttribute("data-proposal-subject", "Sketch1");

    await page.keyboard.press(EXTRUDE_KEY);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    // A real picker this time (two profiles), so the assertion is on the VALUE
    // the form holds, not on a rendered name.
    await expect(page.getByTestId("extrude-profile")).toHaveValue(ids.sketch1);
    expect(ids.sketch1).not.toBe(ids.sketch2);
  });

  test("a camera gesture withdraws it, and that sketch never offers again", async ({
    page,
  }) => {
    await seedTwoSketches(page);
    await reopenAndFinish(page, 0);
    const chip = page.getByTestId("extrude-proposal");
    await expect(chip).toBeVisible({ timeout: 30_000 });

    // The cheapest dismissal there is: start doing something else. A camera
    // gesture also invalidates the note's own anchor, so this is not merely
    // polite — the note is about a point that is moving.
    const frame = await page.getByTestId("viewport").boundingBox();
    if (frame === null) throw new Error("the viewport has no box");
    await page.mouse.move(frame.x + 40, frame.y + frame.height - 40);
    await page.mouse.down();
    await page.mouse.up();
    await expect(chip).toHaveCount(0);

    // …and dismissing TEACHES it. Solve the same sketch again and it stays
    // quiet: one offer per subject, per session. A note that came back after
    // being waved away would be a nag, which is worse than no note at all.
    await reopenAndFinish(page, 0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(chip).toHaveCount(0);

    // A DIFFERENT sketch is a different subject, and still offers.
    await reopenAndFinish(page, 1);
    await expect(chip).toBeVisible({ timeout: 30_000 });
    await expect(chip).toHaveAttribute("data-proposal-subject", "Sketch2");

    // Escape withdraws it explicitly, and stops there — the note is simply the
    // frontmost step, so backing out of it backs out of nothing else.
    await page.keyboard.press("Escape");
    await expect(chip).toHaveCount(0);
    await expect(page.getByTestId("viewport")).toBeVisible();
  });

  test("when both notes could show, the pointer-addressed one wins", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Two notes");
    // A body to hover, plus a second sketch to solve on top of it.
    const first = await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    const extrude = await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: first.feature.id },
          distance_mm: 20,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: first.tree_version,
    });
    // INSIDE the cube's own footprint on XY, which is not decoration: the model
    // camera is framed on the BODY, and a profile whose centroid falls outside
    // that frame is refused an anchor (the test below). This one is squarely in
    // view, so the question this test asks is about priority and nothing else.
    await createFeature(page, account.token, part.id, {
      name: "Sketch2",
      feature: {
        type: "sketch",
        version: 1,
        params: rectangleSketch(2, 2, 16, 16),
      },
      expected_tree_version: extrude.tree_version,
    });
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport")).toBeVisible();
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });

    await reopenAndFinish(page, 2);
    const solveChip = page.getByTestId("extrude-proposal");
    await expect(solveChip).toBeVisible({ timeout: 30_000 });

    // Now rest on the body. Both notes are live in principle; exactly one may
    // be on screen, and it is the one the user is pointing at.
    const frame = await page.getByTestId("viewport").boundingBox();
    if (frame === null) throw new Error("the viewport has no box");
    await restOnBody(page);
    const faceChip = page.getByTestId("sketch-proposal");
    await expect(faceChip).toBeVisible({ timeout: 10_000 });
    await expect(solveChip).toHaveCount(0);

    // Leave the face: the pointer note goes with the pointer, and the ambient
    // one does NOT come back. Two notes never queue, and the ambient one is
    // one-shot — waiting for it to reappear is the nag this design refuses.
    await page.mouse.move(frame.x + frame.width - 8, frame.y + 8);
    await expect(faceChip).toHaveCount(0);
    await expect(solveChip).toHaveCount(0);
  });
});

/**
 * THE NOTE DOES NOT OWN THE KEYBOARD — W2 review, blocking finding.
 *
 * The note binds `Enter` and the verb's letter on `window` in the capture phase
 * with `preventDefault()`, guarded only by `isTypingTarget`. A `<button>` is
 * not a typing target, so both of the paths below fired the offer instead of
 * the control the user was actually standing on. Both are reached without
 * doing anything unusual: the first is the key card's own instruction.
 *
 * Every case here uses a REAL key event at a REAL focused control. A probe
 * dispatched at `document.body` passes against the defect and proves nothing,
 * because `body` is not a control and the claim never applies to it.
 */
test.describe("the offer yields the keyboard", () => {
  test("? then E reads the key card — it does not open Extrude behind it", async ({
    page,
  }) => {
    await seedTwoSketches(page);
    await reopenAndFinish(page, 0);
    const chip = page.getByTestId("extrude-proposal");
    await expect(chip).toBeVisible({ timeout: 30_000 });

    // The path the card itself teaches: open the reference, read the row that
    // says `E — Extrude`, press E.
    await page.keyboard.press("?");
    await expect(page.getByTestId("shortcut-sheet")).toBeVisible();
    await page.keyboard.press(EXTRUDE_KEY);

    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);
    await expect(page.getByTestId("shortcut-sheet")).toBeVisible();
    // The gate's own alarm, read from the DOM: a surface with
    // `aria-modal="true"` that lets a keystroke through to the workspace stamps
    // the document, so this asserts the MECHANISM and not only its effect.
    expect(
      await page.evaluate(() =>
        document.documentElement.getAttribute("data-modal-gate-leak"),
      ),
    ).toBeNull();

    // Enter on the card's own Close button closes the card. Before the fix it
    // accepted the offer instead, and the button did nothing.
    await page.getByTestId("shortcut-sheet-close").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("shortcut-sheet")).toHaveCount(0);
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);

    // NON-VACUOUS, and the whole reason the assertions above mean anything:
    // with the card gone, the same key takes the same offer, still naming the
    // sketch that solved. The offer survived the card — closing a reference is
    // not answering a proposal.
    await expect(chip).toBeVisible();
    await page.keyboard.press(EXTRUDE_KEY);
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await expect(page.getByTestId("extrude-profile")).toHaveValue(/.+/);
  });

  test("Enter on a focused tool presses that tool", async ({ page }) => {
    await seedTwoSketches(page);
    await reopenAndFinish(page, 0);
    await expect(page.getByTestId("extrude-proposal")).toBeVisible({
      timeout: 30_000,
    });

    // Tab lands a keyboard user on band tools; this puts focus on one directly
    // and presses it the way a keyboard user does.
    await page.getByTestId("new-sketch").focus();
    await page.keyboard.press("Enter");

    // BOTH halves, because the defect broke both: the tool ran…
    await expect(page.getByTestId("plane-XY")).toBeVisible();
    // …and the offer did not answer for it.
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0);
  });
});

/**
 * The small-laptop floor. The note is placed by `placeProposal` from the token,
 * so this is where the flip/clamp arithmetic meets a real frame — and it is the
 * width the founder shots are taken at.
 */
test.describe("at the 1280x800 floor", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the offer still lands inside the frame, on the profile", async ({
    page,
  }) => {
    await seedTwoSketches(page);
    await reopenAndFinish(page, 0);
    const chip = page.getByTestId("extrude-proposal");
    await expect(chip).toBeVisible({ timeout: 30_000 });
    const frame = await page.getByTestId("viewport").boundingBox();
    const box = await chip.boundingBox();
    if (frame === null || box === null) throw new Error("no box");
    expect(box.x).toBeGreaterThanOrEqual(frame.x + proposal.margin - 1);
    expect(box.y).toBeGreaterThanOrEqual(frame.y + proposal.margin - 1);
    expect(box.x + box.width).toBeLessThanOrEqual(
      frame.x + frame.width - proposal.margin + 1,
    );
    expect(box.y + box.height).toBeLessThanOrEqual(
      frame.y + frame.height - proposal.margin + 1,
    );
    const { at } = await chipReach(page, "extrude-proposal");
    expect(at).toBe("extrude-proposal");
  });
});
