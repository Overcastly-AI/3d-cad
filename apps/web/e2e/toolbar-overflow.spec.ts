import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
} from "./support";

/**
 * Command-band overflow + tooltip-stacking regression guard (the 2026-07-24
 * hard-audit P0 + P1, docs/UI-REVIEW.md "HARD AUDIT").
 *
 * The defect class: `ToolButton`'s label tier was viewport-breakpoint
 * arithmetic ("labeled band ≈ 1315px → fits ≥1360") written before the
 * Sheet-metal + Inspect groups landed — at 1440–1600 the labeled band
 * overflowed the frame, whole tool groups rendered off-screen, and hovering
 * a hidden tool horizontally scrolled the ENTIRE app. The fix is measured:
 * `CommandBand` probes whether the labeled row fits its own width and steps
 * tiers, and clips its own X overflow so the band can never widen the root.
 *
 * These specs pin the invariants at the audit's exact widths so a future
 * tool group can never silently re-introduce the clip:
 *   1. every tool group (History … Inspect) fully inside the frame;
 *   2. document scrollWidth == clientWidth (no app-level horizontal scroll);
 *   3. hovering/focusing the LAST tool never scrolls the app;
 *   4. the band's chosen tier actually FITS (content <= bandWidth) — the
 *      width-independent form of "never silently clip", valid for any
 *      future group set. If even the icon tier ever fails this at 1280,
 *      move quieter verbs into a group's ▾ menu (`ToolGroup.more`) — do not widen a magic number;
 *   5. a CREATE-group tooltip paints ABOVE the feature-tree panel (the P1:
 *      the band's old `z-10` context trapped tooltips under `z-30` panels).
 *
 * Since EXPORT-1 the tier is GRADUATED rather than all-or-nothing: the band
 * sheds labels one `ToolGroup.labelPriority` level at a time. Six groups made
 * the old two-position switch untenable — the fully labeled row needs 2650.9px
 * against 1047.5px of icons, so no display in the 1280–2560 range could show a
 * single label. These specs now pin the ORDER as well as the fit, because the
 * order is the design decision: export keeps its format codes longest (a code
 * is an identifier no glyph can spell), sheet metal sheds first.
 */

/** Every group eyebrow on the part command band, left to right. */
const BAND_GROUPS = [
  "History",
  "Create",
  "Modify",
  "Sheet metal",
  "Build",
  "Inspect",
] as const;

async function openEmptyPart(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Band part");
  await page.goto(`/parts/${part.id}`);
  // The tree has loaded once Sketch arms — the band is in its resting state.
  await expect(page.getByTestId("new-sketch")).toBeEnabled();
}

/**
 * The band's measured-tier truth, read straight off the primitive.
 *
 * `contentWidth` — not the row's rect — is the honest fit probe. The row is
 * `w-max min-w-full`, so once the tools are narrower than the frame its rect
 * width is pinned to the band's and `rowWidth <= bandWidth` becomes a
 * tautology that cannot fail. What actually answers "does the band clip" is
 * how far the RIGHTMOST group reaches from the band's left edge.
 */
async function bandFit(page: Page) {
  return page.getByTestId("top-toolbar").evaluate((band) => {
    const left = band.getBoundingClientRect().left;
    const groups = Array.from(
      band.querySelectorAll<HTMLElement>("[data-label-priority]"),
    );
    return {
      tier: band.getAttribute("data-band-tier"),
      bandWidth: band.clientWidth,
      contentWidth: Math.max(
        0,
        ...groups.map((g) => g.getBoundingClientRect().right - left),
      ),
      /** Which groups kept their words, in band order. */
      labeled: groups
        .filter((g) => g.dataset.labels !== "off")
        .map((g) => g.getAttribute("aria-label")),
    };
  });
}

async function appScroll(page: Page) {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    scrollLeft: document.documentElement.scrollLeft,
    scrollX: window.scrollX,
  }));
}

// Measured on the part band (empty part, 2026-10-16, after Pipe + Plane along
// path went into CREATE ▾ and Draft + Combine into MODIFY ▾). The icon row is
// 1073.4px, so at the 1280 floor Export's format codes (+160) fit again —
// 1233.4px — and Build's title (+97) is the first that does not. At 1440 and
// 1600 the tier settles on Export + Build + Inspect labeled (1367.6px), the
// three big verb families in icons. A new low-frequency verb goes into its
// group's ▾ menu (`ToolGroup.more`), not onto the row.
for (const { width, height, tier } of [
  { width: 1280, height: 800, tier: "mixed" },
  { width: 1440, height: 900, tier: "mixed" },
  { width: 1600, height: 900, tier: "mixed" },
] as const) {
  test.describe(`command band at ${width}×${height}`, () => {
    test.use({ viewport: { width, height } });

    test("every tool group is inside the frame and nothing scrolls the app", async ({
      page,
    }) => {
      await openEmptyPart(page);

      // 1. Every group — including the audit's hidden SHEET METAL + INSPECT —
      //    renders fully inside the frame.
      for (const name of BAND_GROUPS) {
        const group = page.getByRole("group", { name, exact: true });
        await expect(group).toBeVisible();
        const box = await group.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      }
      // The very last tool (Measure) — the one whose hover used to scroll the
      // whole app into the void — sits fully inside the frame.
      const measure = await page.getByTestId("measure-tool").boundingBox();
      expect(measure).not.toBeNull();
      expect(measure!.x + measure!.width).toBeLessThanOrEqual(width);

      // 2. No app-level horizontal scroll exists at all.
      const before = await appScroll(page);
      expect(before.scrollWidth).toBe(before.clientWidth);

      // 3. Hovering AND focusing the last tool scrolls nothing (the band
      //    clips its own overflow; `clip` forbids even programmatic scroll).
      await page.getByTestId("measure-tool").hover();
      await page.getByTestId("measure-tool").focus();
      const after = await appScroll(page);
      expect(after.scrollLeft).toBe(0);
      expect(after.scrollX).toBe(0);
      expect(after.scrollWidth).toBe(after.clientWidth);
      // The band itself did not scroll either — Measure is where it was.
      const measureAfter = await page.getByTestId("measure-tool").boundingBox();
      expect(measureAfter!.x).toBeCloseTo(measure!.x, 0);

      // 4. The measured tier actually fits — the width-independent guard that
      //    stays valid whatever groups land later.
      const fit = await bandFit(page);
      expect(fit.contentWidth).toBeLessThanOrEqual(fit.bandWidth + 1);
      expect(fit.tier).toBe(tier);

      // 5. The SHEDDING ORDER is the design decision, so it is asserted, not
      //    left to arithmetic. Export holds its format codes at the responsive
      //    floor — "STEP"/"STL"/"3MF"/"GLB" are identifiers three near-identical
      //    mesh glyphs cannot spell — while the verb families, whose glyph and
      //    eyebrow already name them, go to icons first.
      expect(fit.labeled).not.toContain("Sheet metal");
      if (tier === "mixed") {
        expect(fit.labeled).toContain("Export");
        await expect(page.getByTestId("part-export-band-step")).toContainText(
          "STEP",
        );
      }
    });
  });
}

/** Is the button's own inline label — not its tooltip — really painted? */
async function inlineLabelShown(
  page: Page,
  testId: string,
  text: string,
): Promise<boolean> {
  return page
    .getByTestId(testId)
    .evaluate(
      (btn, want) =>
        Array.from(btn.querySelectorAll(":scope > span")).some(
          (span) =>
            !span.hasAttribute("aria-hidden") &&
            span.textContent === want &&
            getComputedStyle(span).display !== "none",
        ),
      text,
    );
}

test.describe("the band buys labels back as it widens (2000)", () => {
  test.use({ viewport: { width: 2000, height: 1000 } });

  test("CREATE gets its words back — measured, not hardcoded", async ({
    page,
  }) => {
    await openEmptyPart(page);

    // At 2000 the band affords Export, Build, Inspect and Create labeled
    // (1774.9px); Modify's words would take it to 2219.1, so Modify and Sheet
    // metal — the widest labels on the band, for a family inert on every part
    // that is not sheet metal — are in icons (measured 2026-10-16). So the
    // step-back-up this spec was written to prove is live, and it is the
    // CREATE group (the audit's own example) that demonstrates it.
    await expect(page.getByTestId("top-toolbar")).toHaveAttribute(
      "data-band-tier",
      "mixed",
    );
    expect(await inlineLabelShown(page, "new-extrude", "Extrude")).toBe(true);
    expect(await inlineLabelShown(page, "new-fillet", "Fillet")).toBe(false);
    expect(await inlineLabelShown(page, "new-base-flange", "Base flange")).toBe(
      false,
    );

    const fit = await bandFit(page);
    expect(fit.contentWidth).toBeLessThanOrEqual(fit.bandWidth + 1);
    expect(fit.labeled).not.toContain("Sheet metal");
  });
});

test.describe("the fully labeled tier returns when it genuinely fits (3000)", () => {
  test.use({ viewport: { width: 3000, height: 1000 } });

  test("every group has its words, and the row still fits", async ({
    page,
  }) => {
    await openEmptyPart(page);

    // 3000 is not a magic number: the fully labeled row measured 2743.1px
    // once the low-frequency verbs moved into the groups' ▾ menus (it had
    // grown past 3000 with Pipe on the row), and 2931.6px after Cut list
    // joined Inspect and Deck joined Build (measured 2026-10-17), so this is
    // the first round width above it. It is the top of the ramp — the guard that the probe really
    // is measuring and not latched to a tier.
    await expect(page.getByTestId("top-toolbar")).toHaveAttribute(
      "data-band-tier",
      "labeled",
    );
    expect(await inlineLabelShown(page, "new-base-flange", "Base flange")).toBe(
      true,
    );
    const fit = await bandFit(page);
    expect(fit.contentWidth).toBeLessThanOrEqual(fit.bandWidth + 1);
    expect(fit.labeled).toEqual([...BAND_GROUPS, "Export"]);
  });
});

test.describe("nothing is unreachable at the 1280 floor", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Pipe, Plane along path and Twisted prism are one click (or key) away", async ({
    page,
  }) => {
    // A sketch, so the path-consuming verbs are live rather than explained.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Reach part");
    await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("new-sketch")).toBeEnabled();

    /** The element's whole box is inside the 1280 frame. */
    const inFrame = async (testId: string) => {
      const box = await page.getByTestId(testId).boundingBox();
      expect(box, `${testId} is not rendered`).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(1280);
    };

    // Wall and Deck sit on the band itself, in BUILD; Twisted prism
    // (PLUGIN-UI) is one click away in BUILD ▾.
    await inFrame("plugin-tool-loft.wall");
    await inFrame("plugin-tool-loft.deck");
    await page.getByTestId("build-more").click();
    const prism = page.getByTestId("plugin-tool-loft.twisted_prism");
    await expect(prism).toBeEnabled();
    await expect(prism).toHaveAccessibleName(/^Twisted prism/);
    await inFrame("plugin-tool-loft.twisted_prism");
    // Timber frame (TIMBER-FRAME) is there too, inside the frame.
    const timber = page.getByTestId("plugin-tool-loft.timber_frame");
    await expect(timber).toBeEnabled();
    await inFrame("plugin-tool-loft.timber_frame");
    await page.keyboard.press("Escape");
    await expect(prism).toBeHidden();

    // CREATE ▾ names itself on hover, like every band control.
    const more = page.getByTestId("create-more");
    await expect(more).toHaveAccessibleName("More Create tools");
    await more.hover();
    await expect(more.locator("[data-tooltip]")).toHaveText(
      "More Create tools",
    );

    // Pointer: CREATE ▾ → Pipe opens the pipe editor.
    await more.click();
    await expect(page.getByTestId("new-pipe")).toBeEnabled();
    await inFrame("new-pipe");
    await inFrame("tool-plane-along-path");
    await page.getByTestId("new-pipe").click();
    await expect(page.getByTestId("pipe-editor")).toBeVisible();
    await page.getByTestId("pipe-cancel").click();
    await expect(page.getByTestId("pipe-editor")).toBeHidden();

    // Keyboard: focus the trigger, Enter opens on the first row, ArrowDown
    // walks to Plane along path, Enter opens the datum editor on that kind.
    await more.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("new-pipe")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByTestId("tool-plane-along-path")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await expect(page.getByTestId("datum-kind")).toHaveValue("along_path");
    await page.getByTestId("datum-cancel").click();

    // MODIFY ▾ holds Draft and Combine; on a one-sketch part neither can act,
    // and each says what it needs instead of going quiet.
    await page.getByTestId("modify-more").click();
    await expect(page.getByTestId("new-draft")).toHaveAccessibleName(
      /needs a body$/,
    );
    await expect(page.getByTestId("new-combine")).toHaveAccessibleName(
      /needs two bodies$/,
    );
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("modify-more")).toBeFocused();
  });
});

for (const width of [1280, 1920] as const) {
  test.describe(`band shot at ${width}`, () => {
    test.use({ viewport: { width, height: 900 } });

    test(`the part band at ${width}`, async ({ page }) => {
      await openEmptyPart(page);
      const fit = await bandFit(page);
      expect(fit.contentWidth).toBeLessThanOrEqual(fit.bandWidth + 1);
      // `page.screenshot` with a clip, not `locator.screenshot`: only the
      // former goes through the UPDATE_SCREENSHOTS write gate (fixtures.ts).
      const band = await page.getByTestId("top-toolbar").boundingBox();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/toolbar-${width}.png`,
        clip: band!,
      });
    });
  });
}

test.describe("band tooltips paint above the floating panels (audit P1)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a CREATE-group gate-reason tooltip is not occluded by the feature tree", async ({
    page,
  }) => {
    await openEmptyPart(page);

    // The audit's exact case: Extrude disabled ("Solve a sketch first") —
    // its tooltip hangs from the band straight over the feature-tree panel.
    const extrude = page.getByTestId("new-extrude");
    await expect(extrude).toBeDisabled();
    await extrude.hover();
    const tooltip = extrude.locator("[data-tooltip]");
    await expect
      .poll(() =>
        tooltip.evaluate((el) => Number(getComputedStyle(el).opacity)),
      )
      .toBeGreaterThan(0.5);

    // Precondition: the tooltip really overlaps the tree panel's rect —
    // otherwise the z-order assert below would be vacuous.
    const panel = await page
      .getByTestId("panel-collapse-tree")
      .evaluate((el) => {
        const r = el.parentElement!.getBoundingClientRect();
        return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
      });
    const tip = await tooltip.evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    });
    expect(tip.left).toBeLessThan(panel.right);
    expect(tip.right).toBeGreaterThan(panel.left);
    expect(tip.bottom).toBeGreaterThan(panel.top);

    // The z-order truth: the topmost paint at the tooltip's center is the
    // tooltip itself, not the panel. (The tooltip is pointer-events:none by
    // design; it is made hit-testable only for the duration of the probe.)
    const paintsOnTop = await tooltip.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const style = (el as HTMLElement).style;
      style.pointerEvents = "auto";
      const hit = document.elementFromPoint(
        r.left + r.width / 2,
        r.top + r.height / 2,
      );
      style.pointerEvents = "";
      return el === hit || el.contains(hit);
    });
    expect(paintsOnTop).toBe(true);

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/toolbar-tooltip-above-panel-1440.png`,
    });
  });
});

/**
 * Founder before/after gallery (gated by UPDATE_SCREENSHOTS, e2e/fixtures.ts).
 * Befores are the audit's own evidence: `docs/screenshots/audit-ui/
 * 19-bracket-measure-armed-1440.png` (half-frame void after a hover-scroll)
 * and `29-band-1600.png` (SHEET METAL clipped, INSPECT gone).
 */
const BAND_RECTANGLE = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 10, y: 0 } },
    { id: "e2", kind: "line", start: { x: 10, y: 0 }, end: { x: 10, y: 20 } },
    { id: "e3", kind: "line", start: { x: 10, y: 20 }, end: { x: 0, y: 20 } },
    { id: "e4", kind: "line", start: { x: 0, y: 20 }, end: { x: 0, y: 0 } },
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
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

/** Seed a part with a solid body so the whole band is armed for the shot. */
async function seedBodiedPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Band body");
  const sketch = await page.request.post(`/api/v1/parts/${part.id}/features`, {
    data: {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: BAND_RECTANGLE },
      expected_tree_version: 0,
    },
    headers: { Authorization: `Bearer ${account.token}` },
  });
  if (!sketch.ok()) {
    throw new Error(`e2e seed sketch failed: ${sketch.status()}`);
  }
  const created = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };
  const extrude = await page.request.post(`/api/v1/parts/${part.id}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: created.feature.id },
          distance_mm: 30,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: created.tree_version,
    },
    headers: { Authorization: `Bearer ${account.token}` },
  });
  if (!extrude.ok()) {
    throw new Error(`e2e seed extrude failed: ${extrude.status()}`);
  }
  return part;
}

for (const [width, height] of [
  [1440, 900],
  [1600, 900],
] as const) {
  test.describe(`founder shot — full band at ${width}`, () => {
    test.use({ viewport: { width, height } });

    test(`every group aboard with a body at ${width}`, async ({ page }) => {
      const part = await seedBodiedPart(page);
      await page.goto(`/parts/${part.id}`);
      await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
        timeout: 30_000,
      });
      await expect
        .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
        .toBeGreaterThan(24);
      await expect(
        page.getByRole("group", { name: "Inspect", exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/toolbar-band-fix-${width}.png`,
      });
    });
  });
}
