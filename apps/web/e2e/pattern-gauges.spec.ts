/**
 * CRAFT-11 — TWO INSTRUMENTS ON ONE FEATURE, AND EACH ONE MUST BE ITS OWN.
 *
 * A pattern mounts the gauge twice: a `stepped` count gauge along the row and a
 * `linear` spacing gauge across the first gap (direction §5.3). The roadmap's
 * single acceptance criterion — *"drag changes spacing; past the pitch
 * increments count"* — described ONE pointer driving TWO numbers, which is the
 * ambiguity the split exists to remove, so it is amended here into two
 * assertions that are only both true if the instruments are genuinely separate:
 *
 *   · dragging SPACING moves `pattern-spacing` and leaves `pattern-count` ALONE;
 *   · dragging COUNT moves `pattern-count` and leaves `pattern-spacing` ALONE.
 *
 * An independence claim needs both halves measured in the same gesture. A spec
 * that only asserted the value it expected to move would pass identically if
 * one drag moved both numbers, which is the exact defect being ruled out — and
 * both halves are asserted against the DRAWING as well as the field, because
 * §8.4 will not ship a gauge whose drag moves a number and not the model.
 *
 * ## The hazard this file exists for
 *
 * Two gauges means two DOM hit sleeves in the same neighbourhood, and this repo
 * has paid four separate times for a control that is present, correctly
 * computed, and unreachable — an SVG stroke `getBoundingClientRect` ignores, an
 * `sr-only` element clipped out of frame, a Tailwind utility that was never
 * generated, and a GL-drawn shaft with no DOM target at all. The new way to
 * fail is the fifth: a sleeve that resolves to its SIBLING, which a census
 * asking only "did this land on a gauge" would score as a perfect run. That
 * check now lives in the shared `expectReach` — extended rather than forked
 * into a third copy of the walk — so every gauge spec gets it.
 *
 * **There is no `force: true` in this file and there must never be.** Every
 * pick is a real `page.mouse` gesture or an `elementFromPoint` resolution.
 */
import { expect, test, type Page } from "./fixtures";
import {
  dragGauge,
  expectReach,
  gripCentre,
  projectedSpine,
  reach,
  viewportStamp,
} from "./gaugeProbe";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

const COUNT_GAUGE = "pattern-count-gauge";
const SPACING_GAUGE = "pattern-spacing-gauge";

/** Sketch a rectangle, extrude it, and open the pattern editor on the body. */
async function openPattern(page: Page): Promise<void> {
  // The first-run navigation cue sits OVER the lower viewport, which is exactly
  // where the dimension rails hang. Measured before this line: 5 of 16 samples
  // down the count gauge's own track resolved to `nav-cue` / `nav-cue-dismiss`.
  // That is the onboarding card occluding the instrument, not the instrument
  // failing to be reachable — but it is worth stating rather than tolerating,
  // because an occluded control is unusable for whoever has not dismissed it.
  const cue = page.getByTestId("nav-cue-dismiss");
  if (await cue.isVisible().catch(() => false)) {
    await cue.click();
    await expect(page.getByTestId("nav-cue")).toHaveCount(0);
  }
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await page.keyboard.press("r");
  await page.mouse.click(620, 400);
  await page.mouse.move(820, 560);
  await page.mouse.click(820, 560);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page.getByTestId("new-pattern").click();
  await expect(page.getByTestId("pattern-editor")).toBeVisible();
  // Iso, so both rails have a readable screen direction to walk. Straight down
  // the row a track has no projected length and nothing can be sampled along it
  // — a camera artefact, not a defect, and the gauge's own `screenValueAt`
  // fallback covers the user's case.
  await page.getByTestId("view-iso").click();
  await waitForCameraRest(page);
  await expect(page.getByTestId(`${COUNT_GAUGE}-handle`)).toBeVisible();
  await expect(page.getByTestId(`${SPACING_GAUGE}-handle`)).toBeVisible();
}

const countValue = async (page: Page): Promise<string> =>
  page.getByTestId("pattern-count").inputValue();
const spacingValue = async (page: Page): Promise<string> =>
  page.getByTestId("pattern-spacing").inputValue();

/**
 * THE TWO PREVIEW STAMPS, and why there have to be two.
 *
 * Both are computed from the vertices actually handed to the renderer, never
 * from the count and spacing that produced them — a stamp of the INPUT cannot
 * fail when the picture stops following it, which is the one failure §8.4
 * exists to prevent.
 *
 * One stamp would not be enough here, and that is the sharper half. Adding a
 * copy and moving the copies apart both change the same drawing, so a single
 * number cannot say WHICH happened, and "the spacing drag left the count alone"
 * could pass while both moved. `segments` counts what is drawn and moves only
 * when a copy is added; `spanMm` measures how far the row reaches and moves
 * when the pitch changes. (CRAFT-9b met the same shape from the other side: a
 * translating square has a constant perimeter, so a perimeter stamp would
 * report a frozen plane as a moving one.)
 */
const ghostSegments = async (page: Page): Promise<number | null> =>
  viewportStamp(page, "pattern-ghost-segments");
const ghostSpanMm = async (page: Page): Promise<number | null> =>
  viewportStamp(page, "pattern-ghost-span-mm");

test.describe("the pattern gauges are two instruments, not one", () => {
  test("each sleeve resolves to ITSELF along its own drawn track", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Reachable row");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);

    // `expectReach` asserts BOTH halves: the floor of 12/16 on the gauge's own
    // track, and zero points resolving to the sibling instrument.
    expectReach(await reach(page, COUNT_GAUGE), COUNT_GAUGE);
    expectReach(await reach(page, SPACING_GAUGE), SPACING_GAUGE);
  });

  test("dragging SPACING moves the spacing and leaves the count alone", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spacing drag");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);

    expect(await countValue(page)).toBe("3");
    const spacingBefore = Number.parseFloat(await spacingValue(page));
    const segmentsBefore = await ghostSegments(page);
    const spanBefore = await ghostSpanMm(page);
    expect(segmentsBefore).toBeGreaterThan(0);

    await dragGauge(page, SPACING_GAUGE, { dx: 90, dy: -70 });

    await expect
      .poll(async () => Number.parseFloat(await spacingValue(page)), {
        message: "a drag on the spacing gauge must move pattern-spacing",
      })
      .not.toBe(spacingBefore);
    // THE INDEPENDENCE HALF. Without it this case would pass identically if the
    // one drag moved both numbers, which is the whole thing §5.3 forbids.
    expect(
      await countValue(page),
      "the spacing drag must not touch the count",
    ).toBe("3");

    // …and the same independence asserted against the PICTURE. The row got
    // longer (the copies moved apart) while the number of copies drawn did not
    // change — which is what says the model followed the spacing and ONLY the
    // spacing.
    expect(
      await ghostSpanMm(page),
      "the drawn row must stretch when the pitch does",
    ).not.toBe(spanBefore);
    expect(
      await ghostSegments(page),
      "…and no copy may appear or vanish while only the spacing moved",
    ).toBe(segmentsBefore);
  });

  test("dragging COUNT past a rung adds a copy and leaves the spacing alone", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Count drag");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);

    const spacingBefore = await spacingValue(page);
    const segmentsBefore = await ghostSegments(page);
    expect(segmentsBefore).toBeGreaterThan(0);

    // Along the row, away from the seat. The count track's pitch IS the
    // spacing, and the drawn shaft spans `count` pitches, so one pitch is
    // length/count of projected travel.
    const { seat } = await projectedSpine(page, COUNT_GAUGE);
    const apex = await gripCentre(page, COUNT_GAUGE);
    const along = { x: apex.x - seat.x, y: apex.y - seat.y };
    const length = Math.hypot(along.x, along.y);
    const pitchPx = length / 3;
    await dragGauge(page, COUNT_GAUGE, {
      dx: (along.x / length) * pitchPx * 1.5,
      dy: (along.y / length) * pitchPx * 1.5,
    });

    await expect
      .poll(async () => Number.parseInt(await countValue(page), 10), {
        message: "dragging the count gauge past a rung must add a copy",
      })
      .toBeGreaterThan(3);
    expect(
      await spacingValue(page),
      "the count drag must not touch the spacing",
    ).toBe(spacingBefore);

    // The drawing gained a copy — the preview and the ladder are one drawing,
    // so the rung the arrow crossed is the copy that appeared.
    expect(
      await ghostSegments(page),
      "a copy must APPEAR in the preview, not only in the field",
    ).toBeGreaterThan(segmentsBefore ?? 0);
  });

  test("CONTRACT β — the instrument stays where it was dragged to", async ({
    page,
  }) => {
    // The quiet half of the override contract: the gauge renders `live ?? value`
    // and clears `live` on pointerup, so if the editor takes `onChange` without
    // its echo feeding the gauge's `value` back, the arrow SPRINGS BACK the
    // instant you let go while the rail field shows the number you dragged to.
    // The drag is smooth and correct for its whole duration and the defect
    // fires after every screenshot anyone would take — so it is measured here,
    // on the DRAWN instrument, well after the pointer is up.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Echoed row");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);

    const shown = async (): Promise<number> =>
      Number.parseFloat(
        (await page
          .getByTestId(`${SPACING_GAUGE}-handle`)
          .getAttribute("data-value")) ?? "NaN",
      );

    const before = await shown();
    await dragGauge(page, SPACING_GAUGE, { dx: 90, dy: -70 });

    // SETTLE FIRST, then assert. Reading `data-value` on the frame after the
    // release catches the echo chain mid-flight — the value moved 16 -> 17 in
    // the first draft of this case, which is the last ask ARRIVING, not a
    // spring-back. The distinction is the whole point: a missing echo reverts
    // to `before`, so the property to assert is "it settled somewhere that is
    // not where it started, and it stays there". Verified by deleting the echo
    // prop: the gauge then springs back to 10, its starting value.
    await page.waitForTimeout(600);
    const settled = await shown();
    expect(
      settled,
      "a released drag must not spring back to its starting value — that is " +
        "the missing-echo defect, and it fires after every screenshot",
    ).not.toBe(before);

    // Nothing is touching the gauge now. Anything that moves it from here is
    // the instrument disagreeing with the value it is supposed to be showing.
    await page.waitForTimeout(600);
    expect(await shown(), "the instrument must hold still once released").toBe(
      settled,
    );
    // …and it must be showing the SAME number the rail is showing. One value,
    // read twice.
    expect(Number.parseFloat(await spacingValue(page))).toBeCloseTo(settled, 3);
  });

  test("arrow keys step the same values the drags do", async ({ page }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Keyed row");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);

    // COUNT: one press is one copy, the picture gains one, and the spacing
    // never moves.
    const spacingBefore = await spacingValue(page);
    const segmentsBefore = await ghostSegments(page);
    await page.getByTestId(`${COUNT_GAUGE}-handle`).focus();
    await page.keyboard.press("ArrowUp");
    await expect.poll(async () => await countValue(page)).toBe("4");
    expect(await spacingValue(page)).toBe(spacingBefore);
    expect(await ghostSegments(page)).toBeGreaterThan(segmentsBefore ?? 0);

    // SPACING: one press is one snap increment, the count holds, and no copy
    // appears or vanishes.
    const spacing = Number.parseFloat(await spacingValue(page));
    const segmentsAtFour = await ghostSegments(page);
    await page.getByTestId(`${SPACING_GAUGE}-handle`).focus();
    await page.keyboard.press("ArrowUp");
    await expect
      .poll(async () => Number.parseFloat(await spacingValue(page)))
      .toBeGreaterThan(spacing);
    expect(await countValue(page)).toBe("4");
    expect(await ghostSegments(page)).toBe(segmentsAtFour);
  });

  test("only ONE instrument carries a tag", async ({ page }) => {
    // Two tags twenty millimetres apart carrying different numbers is the "two
    // dialects on screen" failure drawn literally (direction §9). The count
    // gauge is the silent one: its quantity is the ghosts, which you can count.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "One voice");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);

    await expect(page.getByTestId(`${SPACING_GAUGE}-readout`)).toBeVisible();
    await expect(page.getByTestId(`${COUNT_GAUGE}-readout`)).toHaveCount(0);

    // …and the rail keeps BOTH fields. A gauge with no tag especially must not
    // be the only place its value lives.
    await expect(page.getByTestId("pattern-count")).toBeVisible();
    await expect(page.getByTestId("pattern-spacing")).toBeVisible();
  });

  test("the preview and both instruments clear when the editor closes", async ({
    page,
  }) => {
    // ANCHOR B, from the outside. A stamp left set after the command closes is
    // the "gate measuring the wrong input" failure this repo keeps relearning,
    // and an override left set seeds the NEXT pattern from the last drag.
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Closed row");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);
    expect(await ghostSegments(page)).toBeGreaterThan(0);

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("pattern-editor")).toHaveCount(0);
    await expect(page.getByTestId(`${COUNT_GAUGE}-handle`)).toHaveCount(0);
    await expect(page.getByTestId(`${SPACING_GAUGE}-handle`)).toHaveCount(0);
    expect(await ghostSegments(page)).toBeNull();
    expect(await ghostSpanMm(page)).toBeNull();

    // Re-opening seeds from the DEFAULT, not from the closed session.
    await page.getByTestId("new-pattern").click();
    await expect(page.getByTestId("pattern-editor")).toBeVisible();
    expect(await countValue(page)).toBe("3");
    expect(await spacingValue(page)).toBe("10");
  });

  test("founder capture — the two rails and the ghost copies", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Pattern gauges");
    await page.goto(`/parts/${part.id}`);
    await openPattern(page);
    // THE DEFAULT ROW, deliberately: this is the state a user lands in the
    // instant Pattern opens (3 up, 10 mm), so it is the state whose legibility
    // decides whether the instruments read. A larger row is a fair thing to
    // capture too, but it photographs the CAMERA's framing of a row bigger than
    // the frame rather than the crowding question this gate is here to ask.
    await expect.poll(() => ghostSegments(page)).toBeGreaterThan(0);
    // Address the COUNT gauge, so the capture carries the thing this item
    // claims: its ladder, whose rungs stand on the ghost copies.
    await page.getByTestId(`${COUNT_GAUGE}-handle`).hover();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/w3-after-pattern-gauges-1280.png`,
    });
  });
});
