import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FLOW-A2 — THE THREE ORDINARY EXITS CANNOT SILENTLY DISCARD A SKETCH.
 *
 * AUDIT-FLOW-2026-09 A2 (P0): with four entities drawn and nine constraints
 * solved, the browser Back button, the in-app breadcrumb and a page reload each
 * destroyed the lot and landed the user on "EMPTY PART — Start with a Sketch".
 * Measured on the dev tip before this spec: `beforeunload`, `onbeforeunload`,
 * `useBlocker`, `usePrompt` and `useNavigationBlocker` returned ZERO files
 * across `apps/web/src`. There was no navigation guard of any kind.
 *
 * Each exit gets its own case, and each case proves BOTH halves of the fix:
 * the guard stopped the exit, and the work came back.
 *
 * ## What these cases are built to be able to fail
 *
 * The trap this repo has paid for five times is an assertion that cannot
 * observe the failure mode. Three specific hazards here, and what is done
 * about each:
 *
 *  - **"A prompt appeared" is not "the prompt knows what is at stake."** The
 *    manifest counts are asserted by VALUE (`4` entities), so a prompt wired to
 *    the wrong state reddens. A `toBeVisible()` on the panel would not.
 *
 *  - **"Navigation happened" is not "beforeunload ran."** Playwright
 *    auto-dismisses the browser's own unload dialog, so a reload proceeds
 *    whether or not a handler exists and asserting on the reload alone is
 *    vacuous. The handler's DECISION is read directly instead — a cancelable
 *    `beforeunload` is dispatched and `defaultPrevented` is the answer — and
 *    the same probe is run again with the sketch CLEAN, where it must come back
 *    false. A blanket handler that always prevents would pass the first reading
 *    and fail the second.
 *
 *  - **"The sketcher is open" is not "the entities are back."** Restoration is
 *    asserted through the SketchStrip's own derived count ("4 entities"), which
 *    is computed from the live store by code this fix does not touch.
 *
 * ## Why Back is reached by pressing Back after a CLIENT-SIDE entry
 *
 * The part is opened by clicking its row in the register, not by `page.goto`.
 * A `goto` makes each entry a separate document, so Back would be an unload
 * rather than a popstate and the case would silently be testing the reload
 * path a second time instead of the router's history block.
 */

/** A 1280x800 frame's sketch plane: two corners that make a comfortable box. */
const RECT_FROM = { x: 500, y: 320 };
const RECT_TO = { x: 820, y: 520 };

/**
 * Open the part from the register — a CLIENT-SIDE push, so Back is a popstate.
 *
 * The settle waits on the BREADCRUMB, not on `new-sketch`: the whole point of
 * the re-entry cases is that the workspace may come back with the sketcher
 * already open, and the create strip does not exist in that state. Waiting on a
 * mode-specific control would make the helper assert the absence of the fix.
 */
async function openPartFromRegister(page: Page, name: string): Promise<void> {
  await page.goto("/");
  await page.getByTestId("part-open").filter({ hasText: name }).click();
  await expect(page.getByTestId("part-name")).toHaveText(name, {
    timeout: 30_000,
  });
}

/** Draw the audit's four entities and leave them unsaved. */
async function drawFourEntities(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(RECT_FROM.x, RECT_FROM.y);
  await page.mouse.move(RECT_TO.x, RECT_TO.y);
  await page.mouse.click(RECT_TO.x, RECT_TO.y);
  // The strip's OWN derived readout — not this spec's arithmetic.
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
}

/**
 * Does a `beforeunload` handler claim this page? Read from the handler's own
 * decision, not from whether a navigation happened.
 */
async function unloadIsGuarded(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  });
}

async function seedPart(page: Page, name: string): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  return part.id;
}

test.describe("FLOW-A2 — leaving a sketch with unsaved work", () => {
  test("the Back button is held, names what is at stake, and both answers are honoured", async ({
    page,
  }) => {
    const partId = await seedPart(page, "Backstop");
    await openPartFromRegister(page, "Backstop");
    await drawFourEntities(page);

    // ---- Back #1: the guard holds, and "Stay" really stays ---------------
    await page.goBack();
    const prompt = page.getByTestId("leave-sketch-prompt");
    await expect(prompt).toBeVisible();
    // By VALUE: a prompt reading the wrong state reddens here.
    await expect(page.getByTestId("leave-sketch-entities")).toHaveText("4");
    await expect(
      Number(await page.getByTestId("leave-sketch-constraints").innerText()),
    ).toBeGreaterThan(0);
    // The exit names where it goes — half of what made it ambiguous.
    await expect(page.getByTestId("leave-sketch-destination")).toContainText(
      "Parts",
    );
    // Every rung says what it does, in words, on the button itself (FB-13).
    await expect(page.getByTestId("leave-sketch-save")).toContainText(
      "Save sketch, then leave",
    );
    await expect(page.getByTestId("leave-sketch-leave")).toContainText(
      "restored when you reopen this part",
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/flow-a2-exit-prompt-desktop.png`,
    });

    await page.getByTestId("leave-sketch-stay").click();
    await expect(prompt).toHaveCount(0);
    expect(page.url()).toContain(`/parts/${partId}`);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // ---- Back #2: "Leave without saving" leaves, and the draft survives --
    await page.goBack();
    await expect(prompt).toBeVisible();
    await page.getByTestId("leave-sketch-leave").click();
    await expect(page.getByTestId("part-row").first()).toBeVisible({
      timeout: 30_000,
    });
    expect(page.url()).not.toContain(`/parts/${partId}`);

    // ---- And back in: the entities are there ----------------------------
    await openPartFromRegister(page, "Backstop");
    await expect(page.getByTestId("sketch-draft-restored")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/flow-a2-draft-restored-desktop.png`,
    });
  });

  test("the breadcrumb is held, and the save rung puts the sketch in the part", async ({
    page,
  }) => {
    await seedPart(page, "Crumb");
    await openPartFromRegister(page, "Crumb");
    await drawFourEntities(page);

    await page.getByTestId("breadcrumb-register").click();
    const prompt = page.getByTestId("leave-sketch-prompt");
    await expect(prompt).toBeVisible();
    await expect(page.getByTestId("leave-sketch-entities")).toHaveText("4");
    // The part is named, so "in the part" is not an abstraction.
    await expect(prompt).toContainText("Crumb");

    // The top rung: the work goes into the part, THEN we leave.
    await page.getByTestId("leave-sketch-save").click();
    await expect(page.getByTestId("part-row").first()).toBeVisible({
      timeout: 30_000,
    });

    await openPartFromRegister(page, "Crumb");
    // Saved means IN THE PART: a feature row, from the server's tree.
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    // …and therefore no draft: the browser copy is retired once the part has it.
    await expect(page.getByTestId("sketch-draft-restored")).toHaveCount(0);
  });

  test("a reload arms the unload guard, hands the entities back, and disarms when clean", async ({
    page,
  }) => {
    await seedPart(page, "Reloader");
    await openPartFromRegister(page, "Reloader");
    await drawFourEntities(page);

    // The handler's own decision — not "did the reload happen".
    expect(await unloadIsGuarded(page)).toBe(true);

    await page.reload();
    await expect(page.getByTestId("sketch-draft-restored")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // NEGATIVE CONTROL, and the reason the reading above is not vacuous: with
    // the work deliberately thrown away there is nothing to guard, so a
    // handler that simply always prevents fails here.
    await page.getByTestId("sketch-exit").click();
    await page.getByTestId("sketch-discard-confirm").click();
    await expect(page.getByTestId("new-sketch")).toBeVisible();
    expect(await unloadIsGuarded(page)).toBe(false);

    // …and a discarded sketch does not come back from the dead on reload.
    await page.reload();
    await expect(page.getByTestId("new-sketch")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("sketch-draft-restored")).toHaveCount(0);
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  });

  test("an exit with nothing unsaved is not held up", async ({ page }) => {
    // The guard must cost nothing on the ordinary path, or it becomes the
    // thing people click through without reading.
    await seedPart(page, "Clean");
    await openPartFromRegister(page, "Clean");
    await page.getByTestId("breadcrumb-register").click();
    await expect(page.getByTestId("part-row").first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("leave-sketch-prompt")).toHaveCount(0);
  });
});
