import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * FB-19 — "chrome is too sparse". Measured, not asserted to feel tighter.
 *
 * The founder's photo showed EDIT EXTRUDE spending six full-width rows on five
 * short values (every caption stacked over its control, plus a permanently
 * resident helper sentence) and the tree spending six more rows listing
 * XY/XZ/YZ/X/Y/Z. Both panels float OVER the model, so every row of theirs is
 * viewport the modeller does not get — which is why the acceptance number here
 * is CHROME AREA over the canvas, in px2, and not a row count.
 *
 * `SHOT_TAG=before` runs the same spec against the pre-change tree: it reports
 * the same measurements and skips the ceilings, so the "after" thresholds have
 * a real negative control rather than a number somebody liked.
 *
 * THE FLOOR is checked here too, because a panel compacted into unusability is
 * a worse defect than a tall one (ticket, non-negotiable):
 *   · every interactive element in the compacted chrome is >= 24px on both axes
 *     (`target.dense`, WCAG 2.2 SC 2.5.8) and reachable at its own centre;
 *   · every one of them shows a visible ring under REAL keyboard focus;
 *   · every text ink in the compacted chrome clears WCAG-AA 4.5:1 against the
 *     background it is actually painted on (computed, not quoted from tokens);
 *   · no dense segment label is clipped by the width it traded away.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";
const AFTER = SHOT_TAG === "after";

interface Box {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

async function box(page: Page, selector: string): Promise<Box | null> {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el === null) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  }, selector);
}

const testId = (id: string): string => `[data-testid="${id}"]`;

/** Log a measurement so the run's stdout is the evidence tail. */
function report(label: string, value: unknown): void {
  console.log(`[fb19] ${SHOT_TAG} ${label} = ${JSON.stringify(value)}`);
}

const area = (b: Box | null): number =>
  b === null ? 0 : Math.round(b.width * b.height);

/**
 * Target-size + reachability of every interactive element inside a container:
 * the rect, and whether the element is the topmost thing at its own centre.
 * A rect alone is not enough — a control clipped by a scrolling ancestor still
 * reports one.
 */
async function controlMetrics(
  page: Page,
  containerSelector: string,
): Promise<Array<{ id: string; w: number; h: number; reachable: boolean }>> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (root === null) return [];
    const out: Array<{
      id: string;
      w: number;
      h: number;
      reachable: boolean;
    }> = [];
    for (const el of root.querySelectorAll(
      "button, input, select, [role='checkbox']",
    )) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const hit = document.elementFromPoint(
        r.left + r.width / 2,
        r.top + r.height / 2,
      );
      out.push({
        id:
          el.getAttribute("data-testid") ??
          el.getAttribute("aria-label") ??
          el.tagName.toLowerCase(),
        w: Math.round(r.width * 10) / 10,
        h: Math.round(r.height * 10) / 10,
        reachable: hit !== null && (el.contains(hit) || hit.contains(el)),
      });
    }
    return out;
  }, containerSelector);
}

/**
 * Computed WCAG contrast of every text node's ink against the background it is
 * really painted on (walking ancestors past `transparent`), inside a container.
 * Nothing is quoted from the token file: this is what the browser painted.
 */
async function contrastMetrics(
  page: Page,
  containerSelector: string,
): Promise<Array<{ text: string; ratio: number }>> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (root === null) return [];
    const parse = (value: string): [number, number, number, number] => {
      const nums = value.match(/[\d.]+/g) ?? [];
      return [
        Number(nums[0] ?? 0),
        Number(nums[1] ?? 0),
        Number(nums[2] ?? 0),
        nums[3] === undefined ? 1 : Number(nums[3]),
      ];
    };
    const lum = (rgb: [number, number, number]): number => {
      const [r, g, b] = rgb.map((c) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      }) as [number, number, number];
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const backgroundOf = (start: Element): [number, number, number] => {
      let node: Element | null = start;
      while (node !== null) {
        const [r, g, b, a] = parse(getComputedStyle(node).backgroundColor);
        if (a > 0.9) return [r, g, b];
        node = node.parentElement;
      }
      return [0, 0, 0];
    };
    const out: Array<{ text: string; ratio: number }> = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node !== null) {
      const text = (node.textContent ?? "").trim();
      const parent = node.parentElement;
      if (text !== "" && parent !== null) {
        const style = getComputedStyle(parent);
        const r = parent.getBoundingClientRect();
        // Only ink that is actually painted: hidden notes and zero-size nodes
        // are not a contrast question.
        if (r.width > 0 && r.height > 0 && style.visibility !== "hidden") {
          const [fr, fg, fb] = parse(style.color);
          const fore = lum([fr, fg, fb]);
          const back = lum(backgroundOf(parent));
          const ratio =
            (Math.max(fore, back) + 0.05) / (Math.min(fore, back) + 0.05);
          out.push({ text, ratio: Math.round(ratio * 100) / 100 });
        }
      }
      node = walker.nextNode();
    }
    return out;
  }, containerSelector);
}

/**
 * Labels clipped by their own box — the cost a dense control must NOT pay.
 *
 * Measured with a `Range` over the element's contents, NOT with
 * `scrollWidth > clientWidth`. Both of those are INTEGERS, and the first version
 * of this check used them: it reported "no clipped labels" on a build whose
 * screenshot plainly read `REVER…`, because the overflow was 0.7px and both
 * numbers rounded to the same integer. A gate that cannot see a sub-pixel
 * overflow cannot see the only kind of overflow a tight dense control produces.
 * The range rect is fractional and reflects the laid-out text, which is still
 * laid out at full width under `text-overflow: ellipsis` — only the paint is
 * clipped.
 */
async function clippedLabels(
  page: Page,
  containerSelector: string,
): Promise<string[]> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (root === null) return [];
    const clipped: string[] = [];
    for (const el of root.querySelectorAll("span, label")) {
      const text = (el.textContent ?? "").trim();
      if (text === "" || el.children.length > 0) continue;
      const boxWidth = el.getBoundingClientRect().width;
      if (boxWidth === 0) continue;
      const range = document.createRange();
      range.selectNodeContents(el);
      const textWidth = range.getBoundingClientRect().width;
      if (textWidth > boxWidth + 0.5) {
        clipped.push(
          `${text} (${Math.round(textWidth * 10) / 10}px in ${
            Math.round(boxWidth * 10) / 10
          }px)`,
        );
      }
    }
    return clipped;
  }, containerSelector);
}

/**
 * Walk keyboard focus forward `steps` times and record, for each stop, the
 * focused element's test hook and its computed outline width. `:focus-visible`
 * only matches for REAL keyboard focus, so this cannot be done with `.focus()`.
 */
async function focusRingWalk(
  page: Page,
  steps: number,
): Promise<Array<{ id: string; outline: number }>> {
  const stops: Array<{ id: string; outline: number }> = [];
  for (let i = 0; i < steps; i += 1) {
    await page.keyboard.press("Tab");
    stops.push(
      await page.evaluate(() => {
        const el = document.activeElement;
        if (el === null) return { id: "none", outline: 0 };
        const style = getComputedStyle(el);
        const width =
          style.outlineStyle === "none"
            ? 0
            : Number.parseFloat(style.outlineWidth || "0");
        return {
          id:
            el.getAttribute("data-testid") ??
            el.getAttribute("aria-label") ??
            el.tagName.toLowerCase(),
          outline: Number.isFinite(width) ? width : 0,
        };
      }),
    );
  }
  return stops;
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

/** A part with a solved sketch and a body — the state the founder photographed. */
async function partWithBody(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Density plate");
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
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

for (const size of [
  { width: 1600, height: 1000 },
  { width: 1280, height: 800 },
]) {
  test.describe(`FB-19 chrome density @${size.width}x${size.height}`, () => {
    test.use({ viewport: size });

    test("the editor and the origin block cost the viewport fewer pixels", async ({
      page,
    }) => {
      await partWithBody(page);

      // --- 1. The tree panel ALONE (no editor open) — the resting chrome. ---
      const treePanel = '[data-viewport-chrome="panel-tree"]';
      const restingTree = await box(page, treePanel);
      const origin = await box(page, testId("origin-section"));
      report("tree panel, editor closed", restingTree);
      report("origin section", origin);
      report("origin area px2", area(origin));

      await withStableSessionEmail(page, () =>
        page.screenshot({
          path: `${SCREENSHOT_DIR}/fb19-tree-${SHOT_TAG}-${size.width}.png`,
        }),
      );

      // --- 2. The extrude editor open on the existing feature. ---
      await page.getByTestId("feature-select-1").click();
      await expect(page.getByTestId("extrude-editor")).toBeVisible({
        timeout: 30_000,
      });
      const editor = await box(page, testId("extrude-editor"));
      const openTree = await box(page, treePanel);
      const chrome = area(editor) + area(openTree);
      report("extrude editor card", editor);
      report("tree panel, editor open", openTree);
      report("left-column chrome area px2", chrome);
      report(
        "chrome share of frame %",
        Math.round((chrome / (size.width * size.height)) * 1000) / 10,
      );

      await withStableSessionEmail(page, () =>
        page.screenshot({
          path: `${SCREENSHOT_DIR}/fb19-extrude-${SHOT_TAG}-${size.width}.png`,
        }),
      );

      // --- 3. The floor. Nothing here may be traded for density. ---
      const editorControls = await controlMetrics(
        page,
        testId("extrude-editor"),
      );
      const originControls = await controlMetrics(page, testId("origin-list"));
      report("extrude controls", editorControls);
      report("origin controls", originControls);
      for (const control of [...editorControls, ...originControls]) {
        expect
          .soft(
            Math.min(control.w, control.h),
            `${control.id} must meet the 24px target floor`,
          )
          .toBeGreaterThanOrEqual(24);
        expect.soft(control.reachable, `${control.id} is reachable`).toBe(true);
      }

      const clipped = [
        ...(await clippedLabels(page, testId("extrude-editor"))),
        ...(await clippedLabels(page, testId("origin-list"))),
      ];
      report("clipped labels", clipped);
      expect.soft(clipped).toEqual([]);

      const inks = [
        ...(await contrastMetrics(page, testId("extrude-editor"))),
        ...(await contrastMetrics(page, testId("origin-list"))),
      ];
      const failing = inks.filter((ink) => ink.ratio < 4.5);
      report("min ink contrast", Math.min(...inks.map((i) => i.ratio)));
      report("inks below AA", failing);
      // Sanity: a contrast sweep that measured nothing passes vacuously.
      expect.soft(inks.length).toBeGreaterThan(8);
      expect.soft(failing).toEqual([]);

      // Real keyboard focus, one Tab at a time from the autofocused distance
      // field, across the whole compacted card.
      await page.getByTestId("extrude-distance").focus();
      const stops = await focusRingWalk(page, 6);
      report("focus ring walk", stops);
      for (const stop of stops) {
        expect
          .soft(stop.outline, `${stop.id} shows a visible focus ring`)
          .toBeGreaterThanOrEqual(2);
      }

      // --- 4. The ceilings. Skipped on the `before` pass, which is what makes
      //        these numbers a measurement and not a preference: every one of
      //        them was MEASURED failing at HEAD~ on 2026-08-14, at both widths.
      //
      //          origin block          212.0px -> 95.0px    (ceiling 100)
      //          extrude editor card   368.3px -> 219.5px   (ceiling 240)
      //          tree panel at rest    591.0px -> 474.0px   (ceiling 500)
      //
      //        The combined chrome AREA is reported, not asserted: once the card
      //        shrinks, the tree below it stops being scroll-clipped and grows
      //        into the room, so the column's total is a poor monotone signal
      //        even though every panel in it got smaller. Height per panel is
      //        the honest measurement; the area lands in the report.
      if (!AFTER) return;
      expect
        .soft(origin?.height ?? 0, "origin block height")
        .toBeLessThanOrEqual(100);
      expect
        .soft(editor?.height ?? 0, "extrude editor card height")
        .toBeLessThanOrEqual(240);
      expect
        .soft(restingTree?.height ?? 0, "tree panel height with no editor open")
        .toBeLessThanOrEqual(500);
    });
  });
}
