import { expect, test, type Page } from "./fixtures";

import {
  calibratePlane,
  clickPlane,
  enterSketch,
  hoverPlane,
} from "./planeMap";
import { seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * TWO FOUNDER REPORTS, 2026-08-02, and they are one theme — the sketcher gave
 * you nothing to work from and no way back:
 *
 *   1. *"there isn't an origin to start a drawing from."* The snap layer
 *      offered four kinds, every one of them derived from geometry you had
 *      already drawn, and nothing on screen said where zero was. So the FIRST
 *      point of a sketch — the one that decides where the part sits — could
 *      hold onto nothing. (Same mechanism as QA3-2, where a ring drawn at
 *      "sketch (0,0)" came out 0.065 mm eccentric.)
 *   2. *"there are no undo or redo buttons."* True inside the sketcher, which
 *      is where the most reversible, most error-prone work happens.
 *
 * The discriminator throughout the snap half is the one `sketch-snap.spec`
 * established: the GRID IS TURNED OFF first. With no grid, an exact `+0.00` in
 * the DRO can only have come from the plane-frame snap.
 *
 * The load-bearing assertion in the history half is the NEGATIVE one: the
 * feature tree and the body volume must be untouched by a sketch undo. Wiring
 * the sketcher's buttons to the part's feature-history ring would have looked
 * identical in every screenshot and silently rolled back the extrude — the
 * caption-vs-binding defect class with a destructive twist.
 *
 * Real stack: gateway + documents + geometry.
 */

/** Which side of the change these founder shots record (see the run notes). */
const SHOT = process.env.SKETCH_SHOT_LABEL ?? "after";

/** Turn the grid off and prove it — from here an exact mm means a snap. */
async function gridOff(page: Page): Promise<void> {
  await page.keyboard.press("g");
  await expect(page.getByTestId("dro-snap")).toContainText("no grid");
}

const marker = (page: Page) => page.getByTestId("snap-marker");

test.describe("the sketch plane's own origin", () => {
  test("marks zero, names it, and lets the first click start there", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Origin plate");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");

    // The sheet says where zero is, and what kind of zero it is. On a datum
    // plane that is the part origin — fixed, so no caveat.
    await expect(page.getByTestId("sketch-origin")).toHaveAttribute(
      "data-origin-label",
      "Origin",
    );
    await expect(page.getByTestId("sketch-axis-label-x")).toHaveText("X");
    await expect(page.getByTestId("sketch-axis-label-y")).toHaveText("Y");

    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await gridOff(page);
    await page.keyboard.press("l"); // a placement tool — snapping is live

    // ORIGIN: aim 6 px off zero. The mark names it BEFORE the click, and the
    // DRO reads exact zeroes with no grid to round them.
    await hoverPlane(page, at, { x: 0, y: 0 }, { x: 6, y: -5 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "origin");
    await expect(marker(page)).toHaveAttribute(
      "aria-label",
      "Snapping to origin",
    );
    await expect(page.getByTestId("dro-x")).toHaveText("+0.00");
    await expect(page.getByTestId("dro-y")).toHaveText("+0.00");

    // X AXIS: 25 mm out along it, aimed 5 px off. Only `y` is claimed — the
    // free coordinate stays where the pointer is (the grid is off).
    await hoverPlane(page, at, { x: 25, y: 0 }, { x: 0, y: -5 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "x-axis");
    await expect(page.getByTestId("dro-y")).toHaveText("+0.00");
    await expect(page.getByTestId("dro-x")).not.toHaveText("+0.00");

    // Y AXIS, the mirror case.
    await hoverPlane(page, at, { x: 0, y: 20 }, { x: 5, y: 0 });
    await expect(marker(page)).toHaveAttribute("data-snap-kind", "y-axis");
    await expect(page.getByTestId("dro-x")).toHaveText("+0.00");

    // Ctrl/Cmd suppresses the plane frame like every other snap — the mark
    // goes away rather than promising a point the click will not take.
    await page.keyboard.down("Control");
    await hoverPlane(page, at, { x: 0, y: 0 }, { x: 6, y: -5 });
    await expect(marker(page)).toHaveCount(0);
    await page.keyboard.up("Control");

    // NOW DRAW FROM IT. Rectangle, first corner aimed 6 px off zero with the
    // grid still off, so an exact (0,0) in the PERSISTED sketch can only have
    // come from the origin snap.
    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 0, y: 0 }, { x: 6, y: -5 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 30_000,
    });

    const tree = await page.request.get(`/api/v1/parts/${part.id}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(tree.ok()).toBe(true);
    const body = (await tree.json()) as {
      features: Array<{
        feature: {
          type: string;
          params: {
            entities: Array<{
              start?: { x: number; y: number };
              end?: { x: number; y: number };
            }>;
          };
        };
      }>;
    };
    const sketch = body.features.find((f) => f.feature.type === "sketch");
    const points = (sketch?.feature.params.entities ?? []).flatMap((e) =>
      [e.start, e.end].filter((p): p is { x: number; y: number } => Boolean(p)),
    );
    // Exactly zero, not near it. This is the QA3-2 fix stated as a number.
    expect(
      points.some((p) => p.x === 0 && p.y === 0),
      `no corner at exactly (0,0): ${JSON.stringify(points)}`,
    ).toBe(true);
  });

  test("names a face-seated sketch's zero honestly — it is a centroid, and it moves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face origin");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    // Drive the affordance the overlay offers rather than guessing pixels: any
    // planar face will do here — the point is what the sketch's zero is CALLED.
    const faces = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(faces.first()).toBeVisible({ timeout: 30_000 });
    await faces.first().click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 30_000,
    });

    // NOT "Origin". The sketch's zero here is the face's area centroid, which
    // moves when the outline changes — calling it the origin would imply a
    // stability it does not have. The caveat rides the accessible name, so the
    // surface that states it is the one the user is reading.
    const origin = page.getByTestId("sketch-origin");
    await expect(origin).toHaveAttribute("data-origin-label", "Face centre");
    await expect(origin).toHaveAttribute(
      "aria-label",
      /moves if the outline changes/,
    );
  });
});

test.describe("undo and redo inside the sketcher", () => {
  test("un-draws the last shape — and never touches the feature tree", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Undo plate");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // Nothing drawn yet: the button is honestly gated, and it says so in
    // SKETCH terms — there are two features it is deliberately not offering.
    const undo = page.getByTestId("undo-button");
    const redo = page.getByTestId("redo-button");
    await expect(undo).toBeDisabled();
    await expect(undo).toContainText("Nothing drawn yet");
    await expect(redo).toBeDisabled();

    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 50, y: 5 });
    await clickPlane(page, at, { x: 90, y: 30 });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await expect(undo).toBeEnabled();

    await undo.click();
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    // THE assertion this whole test exists for: the sketch's undo reversed a
    // SKETCH edit. The two features that made the cube are untouched — a
    // feature-history undo would have taken the extrude off the tree here.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    await expect(redo).toBeEnabled();
    await redo.click();
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // The chord is bound to the same stack as the buttons.
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    await page.keyboard.press("Control+Shift+z");
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await expect(page.getByTestId("feature-row")).toHaveCount(2);

    // And the body itself: undo everything, leave the sketcher, and read the
    // inspector (it stands down while sketching, so this is the check that
    // needs the round trip). Still a 20 mm cube, to the millimetre.
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("sketch-save")).toContainText("0 entities");
    await page.getByTestId("sketch-exit").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });
  });

  test("founder shots: the sheet has an origin and the band has history", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Origin shot");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 0, y: 0 }, { x: 4, y: -4 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    // Park the aim ON the origin so the frame, the mark and its word are all
    // in the frame the founder sees.
    await page.keyboard.press("l");
    await hoverPlane(page, at, { x: 0, y: 0 }, { x: 5, y: -5 });

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-origin-history-${SHOT}-1600.png`,
    });

    // The small-laptop floor. The mapping is measured from the canvas, so a
    // resize invalidates it — re-measure rather than aim at a stale pixel.
    await page.setViewportSize({ width: 1280, height: 800 });
    const narrow = await calibratePlane(
      page,
      { x: 560, y: 500 },
      { x: 800, y: 340 },
    );
    await page.keyboard.press("l");
    await hoverPlane(page, narrow, { x: 0, y: 0 }, { x: 5, y: -5 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-origin-history-${SHOT}-1280.png`,
    });
  });
});
