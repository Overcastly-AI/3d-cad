import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * The 2026-07-30 P1 burn-down, asserted by MEASUREMENT rather than by
 * screenshot — because every defect in it was an element with zero size, and a
 * 0px element photographs as absent-by-design. Three consecutive audits looked
 * at these surfaces and passed them.
 *
 * What is pinned here:
 *  1. The signature brass scribe on an active tool and an active segment has a
 *     real, non-zero line (`data-scribe`).
 *  2. A command-band tool is a comfortable target, not a bare 16px glyph.
 *  3. The bottom TIMELINE is a real instrument: the strip and its way have size,
 *     and the two controls that used to be the design system's one ESSENTIAL
 *     target-size exception (the 8px `rollback-slot-N` drop slots wedged between
 *     tree rows) now MEET the 24px floor as slots on the way plus a draggable
 *     travel stop (UI-W1 retired that exception — tokens.ts `target`).
 *  4. The measure readout is seated in the BOTTOM HUD lane, below mid-frame and
 *     clear of the command band.
 *  5. The tallest hole form (C'sink + Tapped + Blind) fits the frame at
 *     1280x800 AND 1366x768 with its tap-drill chip and footer reachable, and
 *     never makes the app root scrollable.
 *
 * Assertions are SOFT so a single dead element cannot hide the remaining
 * measurements — the whole picture lands in one run. `SHOT_TAG` lets the same
 * spec capture the `before` pass from a stashed tree.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

interface Box {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

/** `getBoundingClientRect` of a testid, or null when the element is absent. */
async function box(page: Page, testId: string): Promise<Box | null> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"]`);
    if (el === null) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  }, testId);
}

/** Rect of the first `[data-scribe]` inside a testid (the active accent line). */
async function scribeBox(page: Page, testId: string): Promise<Box | null> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"] [data-scribe]`);
    if (el === null) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  }, testId);
}

/**
 * Is this element actually ON SCREEN — i.e. is it (or a descendant of it) the
 * topmost thing at its own centre? A rect inside the frame is NOT enough: a
 * control clipped by a scrolling ancestor still reports a rect. This is the
 * "the user can reach it" assertion.
 */
async function isOnScreen(page: Page, testId: string): Promise<boolean> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"]`);
    if (el === null) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    if (r.bottom > window.innerHeight || r.top < 0) return false;
    const hit = document.elementFromPoint(
      r.left + r.width / 2,
      r.top + r.height / 2,
    );
    return hit !== null && (el.contains(hit) || hit.contains(el));
  }, testId);
}

/** Root scrollability — the "the page scrolled the top bar away" symptom. */
async function rootOverflow(
  page: Page,
): Promise<{ scrollHeight: number; clientHeight: number }> {
  return page.evaluate(() => ({
    scrollHeight: document.documentElement.scrollHeight,
    clientHeight: document.documentElement.clientHeight,
  }));
}

/** Log a measurement so the run's stdout is the evidence tail. */
function report(label: string, value: unknown): void {
  console.log(`[measure] ${label} = ${JSON.stringify(value)}`);
}

async function sketchRectangleAndSave(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

async function extrudeTenMm(page: Page): Promise<void> {
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
}

async function buildBaseBox(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
  await extrudeTenMm(page);
}

/** A part with a solved sketch + extrude, so the tree has a rollback bar. */
async function partWithBody(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Token scale plate");
  await page.goto(`/parts/${part.id}`);
  await buildBaseBox(page);
}

/** Click the body's top face node (greatest z in the accessible name). */
async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** The tallest hole form the app can author: C'sink + Tapped + Blind. */
async function openTallestHoleForm(page: Page): Promise<void> {
  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  // UI-W3: the face pick is armed on open — no arming step.
  await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await clickTopFace(page);
  await expect(page.getByTestId("hole-face")).toContainText("10");
  await page.getByTestId("hole-type-countersink").click();
  await page.getByTestId("hole-depth-blind").click();
  // Thread is progressively disclosed (UI-W4) — open the block, then tap.
  await page.getByTestId("hole-thread-toggle").click();
  await page.getByTestId("hole-tapped").click();
  await expect(page.getByTestId("hole-thread-designation")).toBeVisible();
}

test.describe("design-system P1 — measured, 1440x900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("scribe, band target, timeline and measure HUD have real size", async ({
    page,
  }) => {
    await partWithBody(page);

    // (2) A command-band tool: the doc comment promises a comfortable target.
    const tool = await box(page, "new-sketch");
    report("band tool (new-sketch)", tool);
    expect.soft(tool).not.toBeNull();
    expect.soft(tool?.height ?? 0).toBeGreaterThanOrEqual(24);

    // The band is tall enough for the targets it holds. (`scrollHeight` is not
    // the probe: the band keeps `overflow-y: visible` so its tooltips hang into
    // the viewport, and they inflate it. The real question is whether the
    // tallest tool GROUP — eyebrow + row + its own padding — fits the band.)
    const bandFit = await page.evaluate(() => {
      const band = document.querySelector<HTMLElement>("[data-band-tier]");
      if (band === null) return null;
      const b = band.getBoundingClientRect();
      let top = Infinity;
      let bottom = -Infinity;
      let tallest = 0;
      for (const el of band.querySelectorAll("button")) {
        const r = el.getBoundingClientRect();
        if (r.height === 0) continue;
        top = Math.min(top, r.top);
        bottom = Math.max(bottom, r.bottom);
        tallest = Math.max(tallest, r.height);
      }
      return {
        band: { top: b.top, bottom: b.bottom, height: b.height },
        tools: { top, bottom, tallest },
      };
    });
    report("command band fit", bandFit);
    // No tool spills out of the band's own frame, at any tier.
    expect
      .soft(bandFit?.tools.top ?? 0)
      .toBeGreaterThanOrEqual(bandFit?.band.top ?? 0);
    expect
      .soft(bandFit?.tools.bottom ?? 0)
      .toBeLessThanOrEqual(bandFit?.band.bottom ?? 0);

    // (3) The TIMELINE is a real instrument, and rollback's controls now meet
    // the target-size floor the old 8px drop slots were excused from.
    const strip = await box(page, "timeline-strip");
    report("timeline strip", strip);
    expect.soft(strip).not.toBeNull();
    expect.soft(strip?.height ?? 0).toBeGreaterThanOrEqual(44);
    const way = await box(page, "timeline-way");
    report("timeline way", way);
    expect.soft(way?.width ?? 0).toBeGreaterThan(100);
    const stop = await box(page, "timeline-stop");
    report("travel stop", stop);
    expect.soft(stop?.width ?? 0).toBeGreaterThanOrEqual(24);
    expect.soft(stop?.height ?? 0).toBeGreaterThanOrEqual(24);
    const slot = await box(page, "rollback-slot-0");
    report("way slot 0", slot);
    expect.soft(slot?.width ?? 0).toBeGreaterThanOrEqual(24);
    expect.soft(slot?.height ?? 0).toBeGreaterThanOrEqual(24);
    // The strip is docked at the bottom of the frame, under the viewport.
    const frame = page.viewportSize();
    expect
      .soft((strip?.y ?? 0) + (strip?.height ?? 0))
      .toBeCloseTo(frame?.height ?? 900, 0);

    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/p1-timeline-${SHOT_TAG}-1440.png`,
        clip: {
          x: 0,
          y: (frame?.height ?? 900) - 120,
          width: 900,
          height: 120,
        },
      }),
    );

    // (4) The measure readout sits in the bottom HUD lane, not under the band.
    await page.keyboard.press("m");
    await expect(page.getByTestId("measure-readout")).toBeVisible();
    const hud = await box(page, "measure-readout");
    const viewportSize = page.viewportSize();
    report("measure readout", hud);
    expect.soft(hud).not.toBeNull();
    // Below mid-frame, and its bottom clears the frame's bottom edge.
    expect.soft(hud?.y ?? 0).toBeGreaterThan((viewportSize?.height ?? 900) / 2);
    expect
      .soft((hud?.y ?? 0) + (hud?.height ?? 0))
      .toBeLessThan(viewportSize?.height ?? 900);

    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/p1-measure-hud-${SHOT_TAG}-1440.png`,
      }),
    );

    // (1) The active-tool scribe: the app's most-used pressed state. Sketch mode
    // last — it replaces the band's contents.
    await page.getByTestId("measure-exit").click();
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await page.keyboard.press("r");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const toolScribe = await scribeBox(page, "tool-rect");
    report("active tool scribe (tool-rect)", toolScribe);
    expect.soft(toolScribe).not.toBeNull();
    expect.soft(toolScribe?.height ?? 0).toBeGreaterThanOrEqual(1);
    expect.soft(toolScribe?.width ?? 0).toBeGreaterThan(8);

    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/p1-active-scribe-${SHOT_TAG}-1440.png`,
        clip: { x: 0, y: 0, width: 1440, height: 160 },
      }),
    );
  });
});

test.describe("design-system P1 — measured, 1280x800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the same elements hold at laptop width", async ({ page }) => {
    await partWithBody(page);

    const strip = await box(page, "timeline-strip");
    report("timeline strip @1280", strip);
    expect.soft(strip?.height ?? 0).toBeGreaterThanOrEqual(44);
    expect.soft(await isOnScreen(page, "timeline-stop")).toBe(true);
    expect.soft(await isOnScreen(page, "timeline-to-tip")).toBe(true);

    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/p1-timeline-${SHOT_TAG}-1280.png`,
        clip: { x: 0, y: 680, width: 900, height: 120 },
      }),
    );

    await page.keyboard.press("m");
    const hud = await box(page, "measure-readout");
    report("measure readout @1280", hud);
    expect.soft(hud?.y ?? 0).toBeGreaterThan(400);
    await withStableSessionEmail(page, () =>
      page.screenshot({
        path: `${SCREENSHOT_DIR}/p1-measure-hud-${SHOT_TAG}-1280.png`,
      }),
    );
  });
});

test.describe("hole editor clamp — the tallest form", () => {
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1366, height: 768 },
  ]) {
    test.describe(`${size.width}x${size.height}`, () => {
      test.use({ viewport: size });

      test("C'sink + Tapped + Blind keeps the tap drill and footer on-frame", async ({
        page,
      }) => {
        await partWithBody(page);
        await openTallestHoleForm(page);

        const card = await box(page, "hole-editor-shell");
        const tapDrill = await box(page, "hole-thread-tap-drill");
        const submit = await box(page, "hole-submit");
        const tick = await box(page, "hole-thread-tick");
        const rule = await box(page, "hole-thread-rule");
        const overflow = await rootOverflow(page);
        report(`hole card @${size.width}x${size.height}`, card);
        report("tap drill chip", tapDrill);
        report("submit cell", submit);
        report("thread leader tick", tick);
        report("thread note rule", rule);
        report("root overflow", overflow);

        // The same signature accent on a SegmentedControl: the selected Type
        // segment (C'sink) carries a real brass line, not just brass ink.
        const segmentScribe = await scribeBox(page, "hole-type-countersink");
        report("active segment scribe (hole-type-countersink)", segmentScribe);
        expect.soft(segmentScribe?.height ?? 0).toBeGreaterThanOrEqual(1);
        expect.soft(segmentScribe?.width ?? 0).toBeGreaterThan(8);

        // The thread callout's rules are real lines (12x1 / long x1).
        expect.soft(tick?.height ?? 0).toBeGreaterThanOrEqual(1);
        expect.soft(rule?.height ?? 0).toBeGreaterThanOrEqual(1);

        // The card fits the frame and the root never becomes scrollable.
        expect
          .soft((card?.y ?? 0) + (card?.height ?? 0))
          .toBeLessThanOrEqual(size.height);
        expect
          .soft(overflow.scrollHeight)
          .toBeLessThanOrEqual(overflow.clientHeight);

        // The two controls the review found off-frame. The footer is PINNED, so
        // it must be on screen with no scrolling at all …
        expect
          .soft((submit?.y ?? 0) + (submit?.height ?? 0))
          .toBeLessThanOrEqual(size.height);
        expect.soft(await isOnScreen(page, "hole-submit")).toBe(true);
        expect.soft(await isOnScreen(page, "hole-cancel")).toBe(true);

        // … and the derived tap-drill chip — the single control the
        // "derived but overridable" design exists for — must be REACHABLE:
        // scrolled into view inside the card's own body, not the page.
        await page
          .getByTestId("hole-thread-tap-drill")
          .scrollIntoViewIfNeeded();
        expect.soft(await isOnScreen(page, "hole-thread-tap-drill")).toBe(true);
        expect
          .soft((await rootOverflow(page)).scrollHeight)
          .toBeLessThanOrEqual((await rootOverflow(page)).clientHeight);
        // It is a real control, not just visible: pressing it takes the bore to
        // the tap drill (brass = "the diameter IS the tap drill").
        await page.getByTestId("hole-thread-tap-drill").click();
        await expect(page.getByTestId("hole-thread-tap-drill")).toHaveAttribute(
          "aria-pressed",
          "true",
        );

        await withStableSessionEmail(page, () =>
          page.screenshot({
            path: `${SCREENSHOT_DIR}/p1-hole-editor-${SHOT_TAG}-${size.width}.png`,
          }),
        );
      });
    });
  }
});
