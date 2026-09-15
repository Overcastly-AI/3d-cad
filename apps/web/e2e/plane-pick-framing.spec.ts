import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * THE PLANE-PICK VANTAGE HAS TO SEE THE BODY IT IS ASKING YOU TO PICK FROM.
 *
 * ## What this exists for (2026-09-15)
 *
 * Entering the plane-pick step used to pose the camera at a hardcoded 230 mm
 * from the world origin with no reference to the body. Measured in a real
 * browser on the gauntlet's `gearbox-11752` (1018 faces, extents
 * 1280.16 x 144.27 x 133.35 mm), at 1280x800, with the face pick armed:
 *
 *   452 marks — 226 behind the camera, 222 off the left edge of the canvas,
 *   4 on canvas, and `elementFromPoint` resolving ZERO of them to themselves.
 *
 * The camera was inside the part. Every mark was present, correctly placed and
 * correctly named; not one of them was a control. That is this repo's oldest
 * defect class wearing its sixth costume, and the reason nothing caught it is
 * worth stating: every fixture in this suite is small enough that 230 mm frames
 * it, so the constant was correct on 100 % of the corpus.
 *
 * ## Why the body here is deliberately LARGE
 *
 * A guard built on the usual 10-30 mm fixture cannot fail for this reason — it
 * sits comfortably inside the old fixed vantage, which is exactly how the defect
 * survived. So this extrudes a tall body on purpose, and asserts its size first:
 * without that check the whole spec would pass vacuously the day somebody
 * changes the default extrude distance.
 *
 * ## What is asserted, and why it is a COUNT and not a clock
 *
 * The gauntlet reports this area as "selecting one face takes 55-73 seconds",
 * and a timing assertion on a shared runner is a false-red machine. The durable
 * property is structural and deterministic: with the pick armed, every offered
 * mark is in front of the camera and inside the canvas. Both halves of the
 * measured failure are named separately, because they fail differently — drei
 * gives a mark behind the camera `display:none` (zero area), while a mark that
 * merely projects outside the frame keeps its box and lands off-canvas.
 */

/** The nav cue covers the lower viewport on a first run; get it out of the way. */
async function dismissNavCue(page: Page): Promise<void> {
  const cue = page.getByTestId("nav-cue-dismiss");
  if (await cue.isVisible().catch(() => false)) {
    await cue.click();
    await expect(page.getByTestId("nav-cue")).toHaveCount(0);
  }
}

/** Where every offered face mark sits relative to the canvas it is drawn over. */
async function markCensus(page: Page): Promise<{
  total: number;
  behindCamera: number;
  offCanvas: number;
  onCanvas: number;
  reachable: number;
  worst: string[];
}> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    const rect = canvas?.getBoundingClientRect() ?? null;
    const marks = [
      ...document.querySelectorAll<HTMLElement>(
        '[data-testid^="plane-pick-face-"]',
      ),
    ];
    let behindCamera = 0;
    let offCanvas = 0;
    let onCanvas = 0;
    let reachable = 0;
    const worst: string[] = [];
    for (const mark of marks) {
      const box = mark.getBoundingClientRect();
      const id = mark.dataset["testid"] ?? "?";
      if (box.width === 0 || box.height === 0) {
        behindCamera += 1;
        if (worst.length < 6) worst.push(`${id} behind camera`);
        continue;
      }
      const x = box.left + box.width / 2;
      const y = box.top + box.height / 2;
      if (
        rect === null ||
        x < rect.left ||
        x > rect.right ||
        y < rect.top ||
        y > rect.bottom
      ) {
        offCanvas += 1;
        if (worst.length < 6)
          worst.push(`${id} off-canvas at ${x.toFixed(0)},${y.toFixed(0)}`);
        continue;
      }
      onCanvas += 1;
      const hit = document.elementFromPoint(x, y);
      if (hit === mark || mark.contains(hit)) reachable += 1;
    }
    return {
      total: marks.length,
      behindCamera,
      offCanvas,
      onCanvas,
      reachable,
      worst,
    };
  });
}

test.describe("the plane-pick vantage frames the body", () => {
  test("a tall body's face marks are all in front of the camera and on canvas", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tall column");
    await page.goto(`/parts/${part.id}`);
    await dismissNavCue(page);

    // Base sketch on XY.
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await page.keyboard.press("r");
    await page.mouse.click(660, 430);
    await page.mouse.move(900, 620);
    await page.mouse.click(900, 620);
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    // A COLUMN, not a plate. 1600 mm is seven times the vantage the plane pick
    // used to stand at, so a camera that ignores the body ends up inside it.
    await page.getByTestId("new-extrude").click();
    const distance = page.getByTestId("extrude-distance");
    await distance.fill("1600");
    await distance.press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    // NON-VACUITY. The whole spec is about a body too big for a fixed vantage,
    // so prove it IS too big before asserting anything about the marks — this
    // is the assertion that stops the guard quietly turning into a no-op if the
    // default extrude distance or the sketch scale ever changes.
    const extents = await page.getByTestId("prop-extents").innerText();
    const largest = Math.max(
      ...(extents.match(/[\d,.]+/g) ?? []).map((n) =>
        Number.parseFloat(n.replace(/,/g, "")),
      ),
    );
    expect(
      largest,
      `this guard needs a body bigger than the 230 mm plane-pick floor; ` +
        `the extents read "${extents.replace(/\n/g, " ")}"`,
    ).toBeGreaterThan(400);

    // Arm the face pick.
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    await expect(page.getByTestId("face-pick-prompt")).toBeVisible({
      timeout: 60_000,
    });
    const marks = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(marks.first()).toBeAttached({ timeout: 60_000 });

    // The camera eases into the vantage over several frames on a demand-rendered
    // scene, so poll the census rather than sampling it once — the settle is
    // stated here rather than being supplied by whatever the previous awaits
    // happened to cost.
    await expect
      .poll(async () => (await markCensus(page)).behindCamera, {
        timeout: 60_000,
        message:
          "no offered face mark may sit behind the plane-pick camera — " +
          "226 of 452 did on the gauntlet's gearbox before this was fixed",
      })
      .toBe(0);

    const census = await markCensus(page);
    // The census IS the evidence: a bare pass/fail here would leave a future
    // regression with nothing to read but a number that changed.
    console.log(`[plane-pick framing] ${JSON.stringify(census)}`);

    expect(
      census.total,
      "the pick must offer some faces at all",
    ).toBeGreaterThan(0);
    expect(
      census.offCanvas,
      `every offered mark must project inside the canvas; worst: ${census.worst.join(", ")}`,
    ).toBe(0);
    expect(census.onCanvas).toBe(census.total);
    // And the flow has to actually work: at least one mark is a real pointer
    // target. The others are legitimately occluded by nearer geometry — that is
    // what a solid body does, and the drawn surface stays the primary hit-test.
    expect(
      census.reachable,
      "at least one face mark must resolve to itself under elementFromPoint",
    ).toBeGreaterThan(0);
  });
});
