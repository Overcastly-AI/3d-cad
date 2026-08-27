import { expect, test, type Page } from "./fixtures";

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
 *      grow an explicit "more" flyout — do not widen a magic number;
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

// Measured on the part band (empty part, 2026-08-22). At all three widths the
// graduated tier settles on Export + Inspect labeled and the three big verb
// families in icons — 1244.6px of content. Before EXPORT-1's group landed the
// band showed no labels at all here, because the only alternative cost 2650.9.
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
      expect(fit.labeled).toContain("Export");
      expect(fit.labeled).not.toContain("Sheet metal");
      await expect(page.getByTestId("part-export-band-step")).toContainText(
        "STEP",
      );
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

test.describe("the band buys labels back as it widens (2400)", () => {
  test.use({ viewport: { width: 2400, height: 1000 } });

  test("CREATE gets its words back — measured, not hardcoded", async ({
    page,
  }) => {
    await openEmptyPart(page);

    // At 2400 the band affords four of the five sheddable levels: Export,
    // Inspect, Create and Modify are labeled (2126.8px), and only Sheet metal
    // — the widest labels on the band, +524px, for a family inert on every
    // part that is not sheet metal — is still in icons. So the step-back-up
    // this spec was written to prove is live, and it is the CREATE group (the
    // audit's own example) that demonstrates it.
    await expect(page.getByTestId("top-toolbar")).toHaveAttribute(
      "data-band-tier",
      "mixed",
    );
    expect(await inlineLabelShown(page, "new-extrude", "Extrude")).toBe(true);
    expect(await inlineLabelShown(page, "new-fillet", "Fillet")).toBe(true);
    expect(await inlineLabelShown(page, "new-base-flange", "Base flange")).toBe(
      false,
    );

    const fit = await bandFit(page);
    expect(fit.contentWidth).toBeLessThanOrEqual(fit.bandWidth + 1);
    expect(fit.labeled).not.toContain("Sheet metal");
  });
});

test.describe("the fully labeled tier returns when it genuinely fits (2700)", () => {
  test.use({ viewport: { width: 2700, height: 1000 } });

  test("every group has its words, and the row still fits", async ({
    page,
  }) => {
    await openEmptyPart(page);

    // 2700 is not a magic number: the fully labeled row measures 2650.9px, so
    // this is the first round width above it. It is the top of the ramp — the
    // guard that the probe really is measuring and not latched to a tier.
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
