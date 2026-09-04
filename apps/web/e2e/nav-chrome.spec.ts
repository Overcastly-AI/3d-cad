import { expect, test, type Page } from "./fixtures";

import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
} from "./support";

/**
 * Makeover Batch 2 — "every element earns its place" (UI-REVIEW 2026-07-16,
 * Track C). Three user-facing guarantees, driven against the REAL stack:
 *   1. a gated tool EXPLAINS itself — reachable by mouse AND keyboard, showing
 *      its reason (the aria-disabled fix; native `disabled` made it mute).
 *   2. an open command SCOPES the band — Fillet locks Extrude, so switching
 *      tools can never silently discard the open command's picks.
 *   3. finishing a sketch twice mints EXACTLY ONE feature — never the
 *      duplicate "Sketch1" the audit reproduced. (Escape used to be the second
 *      finish; since FB-13 it never ends a drawn sketch, so the hammering here
 *      doubles as that regression guard.)
 */

/** A 10×20 rectangle fixed at the origin on XY — solves to clean corners. */
const RECTANGLE_10x20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 9.7, y: 0.4 } },
    {
      id: "e2",
      kind: "line",
      start: { x: 10, y: 0.2 },
      end: { x: 10.3, y: 19 },
    },
    {
      id: "e3",
      kind: "line",
      start: { x: 10.2, y: 20.4 },
      end: { x: -0.3, y: 19.7 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.3, y: 19.5 },
      end: { x: -0.2, y: 0.5 },
    },
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
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Seed a part whose body is a 10×20×30 box (a solved sketch AND a solid). */
async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Scoped box");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

/** The computed opacity of a ToolButton's tooltip (0 hidden, ~1 revealed). */
async function tooltipOpacity(page: Page, testId: string): Promise<number> {
  return page.getByTestId(testId).evaluate((btn) => {
    const tip = btn.querySelector(":scope > span:last-child");
    return tip ? Number(getComputedStyle(tip).opacity) : 0;
  });
}

test.describe("gated tools explain themselves", () => {
  test("disabled Extrude is reachable by mouse AND keyboard and shows its reason", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Empty part");
    await page.goto(`/parts/${part.id}`);

    const extrude = page.getByTestId("new-extrude");
    // No sketch yet → honestly disabled (aria-disabled, still in the a11y tree).
    await expect(extrude).toBeDisabled();
    await expect(extrude).toContainText("Draw a sketch to extrude");

    // MOUSE: a native-disabled button is pointer-events:none — hovering it would
    // hit the element behind and time out. This hover SUCCEEDING proves the tool
    // is reachable, and the reason tooltip animates in.
    await extrude.hover();
    await expect
      .poll(() => tooltipOpacity(page, "new-extrude"), { timeout: 3_000 })
      .toBeGreaterThan(0.5);

    // KEYBOARD: a native-disabled button cannot receive focus. This focusing
    // proves the reason is reachable by keyboard too (the audit's P1 defect).
    await extrude.focus();
    await expect(extrude).toBeFocused();
  });

  test("a band tool's caption is announced whether it is gated or merely qualified", async ({
    page,
  }) => {
    // A11Y-TOOLBTN-1. `ToolButton` used to wire `aria-describedby` only while
    // disabled, so an ENABLED tool whose caption QUALIFIES the click ("Switch
    // to orthographic", "marks the file partial") was hover-only — the sighted
    // user was told and the screen-reader user was not.
    //
    // Asserted through `toHaveAccessibleDescription`, which computes the
    // description the way an AT does: it resolves `aria-describedby` against
    // the document, so an id pointing at nothing fails here. The unit suite
    // uses jsdom's reimplementation; this is Chrome's own computation, which is
    // the thing users actually get.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Empty part");
    await page.goto(`/parts/${part.id}`);

    // GATED: the reason describes the cell, and the NAME stays the format. The
    // name used to carry the reason too (an ExportToolGroup workaround for this
    // very gap), which announced it twice and renamed the control per state.
    const step = page.getByTestId("part-export-band-step");
    await expect(step).toBeDisabled();
    await expect(step).toHaveAccessibleName("Export STEP (exact B-rep)");
    await expect(step).toHaveAccessibleDescription(/No body/);

    // ENABLED-BUT-QUALIFIED: the projection toggle always works and always says
    // what the click would switch TO. This description is empty before the fix.
    const projection = page.getByTestId("view-projection");
    await expect(projection).toBeEnabled();
    await expect(projection).toHaveAccessibleName(/Projection:/);
    await expect(projection).toHaveAccessibleDescription(/^Switch to /);
  });
});

test.describe("an open command scopes the band", () => {
  test("Fillet locks Extrude with a reason; picks survive a stray Extrude click", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    // The body renders (10×20×30 = 6,000 mm³).
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    const extrude = page.getByTestId("new-extrude");
    const fillet = page.getByTestId("new-fillet");
    await expect(extrude).toBeEnabled();
    await expect(fillet).toBeEnabled();

    // Open the Fillet command and pick one edge (a live, unsaved selection).
    await fillet.click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("create-strip")).toHaveAttribute(
      "data-command",
      "Fillet",
    );
    await page.getByTestId("fillet-mode-pick").click();
    await page.locator('[data-testid^="edge-pick-"]').first().click();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );

    // The whole band is now scoped: Extrude is locked with an honest reason.
    await expect(extrude).toBeDisabled();
    await expect(extrude).toContainText("Finish Fillet first");

    // A stray Extrude activation is inert — the Fillet command and its picked
    // edge survive (the silent pick-loss the audit found is gone).
    //
    // This used to be `extrude.click({ force: true }).catch(() => {})` and it
    // proved nothing. While a command is open the whole `tool-groups` band is
    // `sr-only` (measured: `1x1@(-1,43)`, `clip: rect(0,0,0,0)`), so the button
    // is CLIPPED OUT OF THE FRAME — `checkVisibility()` and Playwright's
    // `isVisible()` both still say true, which is why nobody noticed. `force`
    // skips the hit-target check, so the synthetic click was delivered to
    // whatever was topmost at those coordinates: measured 2026-08-28, it landed
    // on `header[topbar]`, and the Extrude handler was never invoked. The
    // assertions below would have passed identically had the handler discarded
    // the picks — which is the whole thing this test exists to catch.
    //
    // So assert BOTH halves separately. First: a stray POINTER click is
    // impossible by construction, because the band is not on screen.
    const bandHidden = await page.evaluate(() => {
      const group = document.querySelector('[data-testid="tool-groups"]');
      if (group === null) return null;
      const r = group.getBoundingClientRect();
      return { w: r.width, h: r.height };
    });
    expect(
      bandHidden,
      "the tool band is in the DOM while a command is open",
    ).not.toBeNull();
    expect(
      Math.max(bandHidden!.w, bandHidden!.h),
      "an open command clips the tool band out of the frame, so no pointer can reach Extrude",
    ).toBeLessThanOrEqual(2);

    // Second: the activation path that IS still reachable — a direct activation
    // (assistive tech, a stale focus, a rogue accelerator) — must be refused by
    // the handler itself. Dispatched ON the element, so it cannot land elsewhere.
    await extrude.dispatchEvent("click");
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );
    await expect(page.getByTestId("extrude-distance")).toHaveCount(0);

    // Cancel is the honest way out — the band unlocks.
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await expect(page.getByTestId("create-strip")).not.toHaveAttribute(
      "data-command",
      "Fillet",
    );
    await expect(extrude).toBeEnabled();
  });

  test("keyboard accelerators can't discard an open command's picks either", async ({
    page,
  }) => {
    // The pointer lock is only half the guarantee: the Create/Modify keyboard
    // accelerators (H/D/P/S/L, M) must ALSO be inert while a command is open, or
    // a single documented keystroke silently `setEditor(...)`s over the live
    // selection — the keyboard twin of the fillet→extrude pick-loss.
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Open Fillet and pick an edge — a live, unsaved selection worth protecting.
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await page.getByTestId("fillet-mode-pick").click();
    await page.locator('[data-testid^="edge-pick-"]').first().click();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );

    // Every Create/Modify accelerator that is otherwise live once a body exists
    // (H shell, D draft, P pattern) is swallowed while the command is open.
    for (const key of ["h", "d", "p", "m"]) {
      await page.keyboard.press(key);
    }

    // The Fillet command and its picked edge are untouched — no editor was
    // swapped in, and Measure never activated.
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);
    await expect(page.getByTestId("draft-editor")).toHaveCount(0);
    await expect(page.getByTestId("pattern-editor")).toHaveCount(0);

    // Cancel still exits cleanly and the accelerators come back to life.
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await page.keyboard.press("h");
    await expect(page.getByTestId("shell-editor")).toBeVisible();
  });
});

test.describe("sketch exit is idempotent", () => {
  test("Escape never ends a drawn sketch; finishing twice mints one feature", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Escape part");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // Enter sketch, pick XY, draw a rectangle (no constraints → the debounce
    // loop stays quiet; only the exit path can persist it).
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await page.keyboard.press("r");
    await page.mouse.click(650, 420);
    await page.mouse.move(950, 620);
    await page.mouse.click(950, 620);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // Hammer Escape: it resets the tool and then STOPS (FB-13). The rectangle
    // is still there, the sketch is still open, and nothing was persisted by a
    // key the strip advertises as a cancel.
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // Finish twice — the second click lands while the create is still in
    // flight. The idempotent guard must mint ONE feature.
    await page.getByTestId("sketch-save").dblclick();

    // Sketch mode closes and exactly one "Sketch1" persists.
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
    await expect(page.getByTestId("feature-row")).toContainText("Sketch1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Reload proves the server holds a single feature (no duplicate slipped in).
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
  });
});

/**
 * Founder before/after gallery for Batch 2 (gated behind UPDATE_SCREENSHOTS —
 * see e2e/fixtures.ts). Each frame shows one "earns its place" win: the grouped
 * command band, the scoped-in-command band, the mode-legible sketch band with
 * its breadcrumb, and a disabled tool speaking its reason.
 */
async function captureBatch2(page: Page, width: "desktop" | "laptop") {
  const part = await seedBoxPart(page);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // 1) The grouped Create / Modify / Inspect band + breadcrumb + cleaned inspector.
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch2-band-${width}.png`,
  });

  // 2) In-command: the open Fillet scopes (locks) the whole band.
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch2-scoped-${width}.png`,
  });
  await page.getByTestId("fillet-cancel").click();

  // 3) Sketch mode: eyebrow-grouped tool band + "… › Sketch" breadcrumb.
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("workspace-mode")).toHaveText("Sketch");
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch2-sketch-${width}.png`,
  });
}

test.describe("founder gallery — Batch 2", () => {
  test("desktop states (band, scoped, sketch)", async ({ page }) => {
    await captureBatch2(page, "desktop");
  });

  test("a disabled tool speaks its reason (desktop)", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Empty part");
    await page.goto(`/parts/${part.id}`);
    const extrude = page.getByTestId("new-extrude");
    await expect(extrude).toBeDisabled();
    await extrude.hover();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/makeover-batch2-disabled-reason-desktop.png`,
    });
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });
    test("laptop states (band, scoped, sketch)", async ({ page }) => {
      await captureBatch2(page, "laptop");
    });
  });
});
