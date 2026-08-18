import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * The two founder-traced sketcher defects from the 2026-08-01 session, driven
 * against the real stack.
 *
 * **FB-13 — Escape must not end the sketch.** The cascade's last rung used to
 * be `finishSketch()`, so the reflex after a click that appeared to do nothing
 * ("tap Escape, start over") persisted and CLOSED the sketch — while the
 * strip's own chip advertised Escape as SAVE. Escape is a cancel key: it
 * unwinds the most local thing and, at rest, does nothing but say so. It still
 * backs out of a sketch that holds no work (nothing to lose).
 *
 * **FB-14 — a plain click replaces, a modifier adds.** Clicking line A then
 * line B used to leave BOTH selected, so `D` refused with "Select one line to
 * dimension" while the user believed they had selected one line. Multi-entity
 * constraints are still authorable — with Shift (or Ctrl/Cmd) held.
 */

/** Open a fresh part and enter the sketcher on the XY datum. */
async function openSketchOnXy(page: Page, name: string): Promise<void> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
}

/** A rectangle at fixed screen coordinates; returns pickable edge midpoints. */
async function drawRectangle(page: Page): Promise<{
  bottom: [number, number];
  right: [number, number];
  corner: [number, number];
}> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(700, 420);
  await page.mouse.move(1000, 640);
  await page.mouse.click(1000, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.keyboard.press("Escape"); // rect tool → select
  return { bottom: [850, 640], right: [1000, 530], corner: [1000, 640] };
}

test.describe("FB-13 — Escape unwinds; it never ends a sketch with work in it", () => {
  test("hammering Escape leaves the sketch open, the geometry intact", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Escape reflex");
    const { bottom } = await drawRectangle(page);

    // Rung: a selection. Escape drops it and stays put.
    await page.mouse.click(bottom[0], bottom[1]);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await expect(page.getByTestId("sketch-strip")).toBeVisible();

    // At rest: the founder's reflex. Nothing left to unwind — and the app says
    // so instead of closing the sketch.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "Nothing to cancel",
    );
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // …and it does not fall through on the next press, or the next.
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // The explicit finish still works, and mints the sketch it was holding.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
  });

  test("Escape still backs out of a sketch that holds no work", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Escape empty");
    await page.goto(`/parts/${part.id}`);

    // The plane-pick step: nothing chosen, nothing drawn.
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // …and an empty sketch on a chosen plane, opened by mistake.
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    // DISCARDS — the behavioural half of ESC-2's guard. The last rung means a
    // fresh session, and the empty feature row is what proves it: the mapping
    // this replaced sent `"exit"` to `finishSketch()`, which persists, so a
    // second cascade re-derived anywhere in the keyboard path mints a sketch
    // feature here from a sketch the user backed out of.
    await expect(page.getByTestId("feature-row")).toHaveCount(0);
  });
});

test.describe("FB-14 — a plain click replaces the selection, a modifier adds", () => {
  test("clicking a second line dimensions THAT line", async ({ page }) => {
    await openSketchOnXy(page, "Replace on click");
    const { bottom, right } = await drawRectangle(page);

    await page.mouse.click(bottom[0], bottom[1]);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    // The founder's path: hunt for a click that works, land on a second line.
    await page.mouse.click(right[0], right[1]);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await expect(page.getByTestId("selection-readout")).not.toContainText(
      "2 ent",
    );

    // …and D dimensions it, instead of refusing with "Select one line".
    await page.keyboard.press("d");
    await expect(page.getByTestId("dimension-input")).toBeVisible();
    await expect(page.getByTestId("constraint-hint")).toHaveCount(0);
  });

  test("Shift-click adds — a two-line constraint is still authorable", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Shift adds");
    const { bottom, right } = await drawRectangle(page);

    await page.mouse.click(bottom[0], bottom[1]);
    await page.keyboard.down("Shift");
    await page.mouse.click(right[0], right[1]);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");

    // L = perpendicular in the constraint vocabulary (the two entities relate).
    //
    // Located BY SYMBOL, not by index. `glyph-N` is a position in the
    // constraint array, and the rectangle now arrives carrying its own: RECT-1
    // authors the rigidity set at the draw, and SNAP-3 authors a coincident
    // wherever a placed point snapped. `glyph-0` is one of those coincidences,
    // so an index-based assertion here tests the fixture rather than the verb
    // this test is named for.
    await page.keyboard.press("l");
    await expect(
      page.locator('[data-testid^="glyph-"]').filter({ hasText: /^⊥$/ }),
    ).toHaveCount(1);
  });

  test("Ctrl/Cmd-click adds too, on both platform conventions", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Ctrl adds");
    const { bottom, right } = await drawRectangle(page);

    await page.mouse.click(bottom[0], bottom[1]);
    await page.keyboard.down("Control");
    await page.mouse.click(right[0], right[1]);
    await page.keyboard.up("Control");
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");

    await page.keyboard.press("Escape"); // clear, then the macOS gesture
    await expect(page.getByTestId("selection-readout")).toContainText(
      "nothing selected",
    );
    await page.mouse.click(bottom[0], bottom[1]);
    await page.keyboard.down("Meta");
    await page.mouse.click(right[0], right[1]);
    await page.keyboard.up("Meta");
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
  });

  test("plain clicks on a stacked corner CYCLE, one pick at a time", async ({
    page,
  }) => {
    await openSketchOnXy(page, "Corner cycle");
    const { corner } = await drawRectangle(page);

    // Two lines meet here, so two endpoints are stacked under the cursor.
    await page.mouse.click(corner[0], corner[1]);
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.mouse.click(corner[0], corner[1]);
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");

    // Shift is how you collect BOTH — the coincident-constraint gesture.
    await page.keyboard.down("Shift");
    await page.mouse.click(corner[0], corner[1]);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    await expect(page.getByTestId("glyph-0")).toHaveText("C");
  });
});
