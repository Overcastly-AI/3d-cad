import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * UI-W1 — the bottom TIMELINE strip, driven in a real browser against the real
 * stack (founder-directed 2026-07-30: "should the timeline be at the bottom with
 * the ability to drag the slider to revert?").
 *
 * What this proves that the component tests cannot: the travel stop can actually
 * be DRAGGED with a pointer and the drop lands on the slot under the cursor; the
 * dashed-past-the-stop encoding really renders (computed style, not a class
 * name); keyboard travel keeps focus on the stop across the move; and each move
 * genuinely rebuilds the BODY — a rolled-back build loses its fillet and then its
 * whole solid, and TO TIP brings them back.
 *
 * The founder before/after pair is captured by the `rolled-back build` test,
 * which drives ONLY `rollback-slot-1` — a hook that exists on both sides of this
 * change — so the same tree, the same state and the same frame can be shot
 * against the old tree (`SHOT_TAG=before`, sources at HEAD) and the new one.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** Seed sketch → extrude → fillet(all edges, r2): a lightly rounded 20 mm cube. */
async function seedThreeOpPart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Timeline plate");
  const sketch = await createFeature(page, account.token, part.id, {
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
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 2 },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

/** The body volume (mm³) parsed from the mass-properties readout. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[0] ?? "NaN");
}

/** Drag the travel stop onto the way slot after feature `slotIndex`. */
async function dragStopToSlot(page: Page, slotIndex: number): Promise<void> {
  const stop = await page.getByTestId("timeline-stop").boundingBox();
  const target = await page
    .getByTestId(`rollback-slot-${slotIndex}`)
    .boundingBox();
  expect(stop).not.toBeNull();
  expect(target).not.toBeNull();
  if (stop === null || target === null) return;
  await page.mouse.move(stop.x + stop.width / 2, stop.y + stop.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    target.x + target.width / 2,
    target.y + target.height / 2,
    { steps: 12 },
  );
  await page.mouse.up();
}

/**
 * Wait for the strip's tree write to SETTLE. The stop refuses to travel while a
 * rollback is in flight (one rebuild at a time — the same mutual exclusion the
 * History tools honour), so a test that presses again too early loses the press
 * exactly as a user would.
 */
async function waitForSettled(page: Page): Promise<void> {
  await expect(page.getByTestId("timeline-strip")).not.toHaveAttribute(
    "data-busy",
    "true",
    { timeout: 30_000 },
  );
}

/** Rendered border style of a timeline chip — the solid/dashed encoding. */
async function chipBorderStyle(page: Page, index: number): Promise<string> {
  return page.evaluate((i) => {
    const chip = document.querySelector(`[data-testid="timeline-chip-${i}"]`);
    return chip === null ? "" : getComputedStyle(chip).borderTopStyle;
  }, index);
}

test.describe("timeline strip (1440×900)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("reads the build order: a chip per op, ordinals, stop at the tip", async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("timeline-strip")).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    await expect(page.getByTestId("timeline-chip-0")).toContainText("Sketch1");
    await expect(page.getByTestId("timeline-chip-0")).toContainText("01");
    await expect(page.getByTestId("timeline-chip-1")).toContainText("Extrude1");
    await expect(page.getByTestId("timeline-chip-2")).toContainText("Fillet1");
    await expect(page.getByTestId("timeline-position")).toHaveText("03/03");
    await expect(page.getByTestId("timeline-stop")).toHaveAttribute(
      "aria-valuenow",
      "3",
    );
    // At the tip the escape hatch is honestly gated, with its reason on screen.
    await expect(page.getByTestId("timeline-to-tip")).toBeDisabled();
    await expect(page.getByTestId("timeline-to-tip")).toContainText(
      "Already at the tip",
    );
    // Every op is built, so the whole way is solid.
    expect(await chipBorderStyle(page, 2)).toBe("solid");

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timeline-tip-1440.png`,
    });
  });

  test("DRAGGING the stop back un-builds the ops past it; TO TIP restores them", async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const filleted = await bodyVolume(page);
    expect(filleted).toBeLessThan(8000);

    // Drag the stop one op back: the fillet stops being built (a full 8,000 mm³
    // cube returns) and its chip goes dashed.
    await dragStopToSlot(page, 1);
    await expect(page.getByTestId("timeline-position")).toHaveText("02/03", {
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeCloseTo(8000, 0);
    await expect(page.getByTestId("timeline-chip-2")).toHaveAttribute(
      "data-rolled-back",
      "true",
    );
    expect(await chipBorderStyle(page, 2)).toBe("dashed");
    expect(await chipBorderStyle(page, 1)).toBe("solid");
    // The tree panel still SHOWS the effect, it just no longer offers the control.
    await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
      "data-rolled-back",
      "true",
    );
    await expect(page.getByTestId("feature-row")).toHaveCount(3); // nothing deleted

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timeline-rolled-back-1440.png`,
    });

    // Drag all the way back to the first op: no body at all (a sketch-only part).
    await waitForSettled(page);
    await dragStopToSlot(page, 0);
    await expect(page.getByTestId("timeline-position")).toHaveText("01/03", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeHidden({
      timeout: 30_000,
    });

    // The escape hatch: back to everything included.
    await waitForSettled(page);
    await page.getByTestId("timeline-to-tip").click();
    await expect(page.getByTestId("timeline-position")).toHaveText("03/03", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeCloseTo(filleted, 0);
  });

  test("the stop is keyboard-operable and keeps focus across a move", async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    await page.getByTestId("timeline-stop").focus();
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByTestId("timeline-position")).toHaveText("02/03", {
      timeout: 30_000,
    });
    await waitForSettled(page);
    // Focus followed the stop, so the NEXT arrow press still travels (the
    // keyboard-first bar: one press, one op, no re-aiming).
    expect(
      await page.evaluate(
        () => document.activeElement?.getAttribute("data-testid") ?? "(none)",
      ),
    ).toBe("timeline-stop");
    await page.keyboard.press("ArrowLeft");
    await expect(page.getByTestId("timeline-position")).toHaveText("01/03", {
      timeout: 30_000,
    });
    await waitForSettled(page);
    await expect(page.getByTestId("body-inspector")).toBeHidden({
      timeout: 30_000,
    });

    // End = the tip.
    await page.keyboard.press("End");
    await expect(page.getByTestId("timeline-position")).toHaveText("03/03", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
  });

  test(`founder screenshot: rolled-back build (${SHOT_TAG})`, async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    // The body must be ON SCREEN before the frame, or the A/B pair compares
    // chrome over an empty grid (the shot's subject is the build, not the grid).
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
      "data-rolled-back",
      "true",
      { timeout: 30_000 },
    );
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timeline-${SHOT_TAG}-1440.png`,
    });
  });

  test("a chip selects its feature (one selection model, two surfaces)", async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await page.getByTestId("timeline-chip-1").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await expect(page.getByTestId("timeline-chip-1")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

test.describe("timeline strip (1366×768)", () => {
  test.use({ viewport: { width: 1366, height: 768 } });

  test(`founder screenshot: rolled-back build at laptop width (${SHOT_TAG})`, async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    // The body must be ON SCREEN before the frame, or the A/B pair compares
    // chrome over an empty grid (the shot's subject is the build, not the grid).
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("feature-row").nth(2)).toHaveAttribute(
      "data-rolled-back",
      "true",
      { timeout: 30_000 },
    );
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timeline-${SHOT_TAG}-1366.png`,
    });
  });

  test("the strip stays a usable instrument at laptop width", async ({
    page,
  }) => {
    const partId = await seedThreeOpPart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("timeline-chip-2")).toBeVisible();
    await expect(page.getByTestId("timeline-stop")).toBeVisible();
    await expect(page.getByTestId("timeline-to-tip")).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timeline-tip-1366.png`,
    });

    await dragStopToSlot(page, 1);
    await expect(page.getByTestId("timeline-position")).toHaveText("02/03", {
      timeout: 30_000,
    });
    await waitForSettled(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timeline-rolled-back-1366.png`,
    });
  });
});
