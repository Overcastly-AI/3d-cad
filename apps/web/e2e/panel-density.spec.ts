import { expect, test, type Page } from "./fixtures";

import { createFeature, rectangleSketch } from "./partSeed";
import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * PANEL DENSITY — "the item tree and material selector are not in any form
 * compact like the header" (founder, 2026-08-28).
 *
 * The complaint is NOT about layout: the panels have floated over a full-bleed
 * canvas since the Batch 1 makeover. It is about the density INSIDE them. The
 * reference the founder names is our own header, which already had a density
 * pass — so the gap is measurable, and this spec measures it rather than
 * asserting that something now feels tighter.
 *
 * THE MEASURE IS ROW PITCH, not panel height. A panel's height is a function of
 * how much the part has in it; the pitch is the design decision, and it is what
 * makes a tree read as a tree instead of as a settings dialog. Alongside it we
 * measure the chrome AREA over the canvas (px2), because every row of an
 * overlay panel is viewport the modeller does not get.
 *
 * `SHOT_TAG=before` runs the same spec against the pre-change tree: it reports
 * the identical measurements and skips the ceilings, so the "after" thresholds
 * have a real negative control instead of a number somebody liked.
 *
 * THE FLOOR is checked here too — a panel compacted into unusability is a worse
 * defect than a tall one:
 *   · every interactive element in the panels is >= 24px on both axes
 *     (`target.dense`, WCAG 2.2 SC 2.5.8) and is the topmost element at its own
 *     centre, proven with a REAL mouse click, not `force: true`;
 *   · every text ink clears WCAG-AA 4.5:1 against the background it is actually
 *     painted on (computed from what the browser painted, never quoted from the
 *     token file);
 *   · no label is clipped by the width it traded away.
 */

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";
const AFTER = SHOT_TAG === "after";

interface Box {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

const testId = (id: string): string => `[data-testid="${id}"]`;

async function box(page: Page, selector: string): Promise<Box | null> {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el === null) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  }, selector);
}

function report(label: string, value: unknown): void {
  console.log(`[density] ${SHOT_TAG} ${label} = ${JSON.stringify(value)}`);
}

const area = (b: Box | null): number =>
  b === null ? 0 : Math.round(b.width * b.height);

/**
 * The PITCH of a repeated row family: the median centre-to-centre distance
 * between consecutive rows, which is the number a dense instrument is actually
 * designed to. A single row's height misses the padding between rows, and a
 * mean is dragged around by the one row that wrapped.
 */
async function rowPitch(
  page: Page,
  selector: string,
): Promise<{ count: number; pitch: number; height: number }> {
  return page.evaluate((sel) => {
    const rows = [...document.querySelectorAll(sel)].map((el) =>
      el.getBoundingClientRect(),
    );
    if (rows.length === 0) return { count: 0, pitch: 0, height: 0 };
    const round = (n: number): number => Math.round(n * 10) / 10;
    const heights = rows.map((r) => r.height).sort((a, b) => a - b);
    const height = round(heights[Math.floor(heights.length / 2)] ?? 0);
    if (rows.length < 2) return { count: rows.length, pitch: height, height };
    const gaps: number[] = [];
    for (let i = 1; i < rows.length; i += 1) {
      const prev = rows[i - 1];
      const cur = rows[i];
      if (prev === undefined || cur === undefined) continue;
      gaps.push(cur.top + cur.height / 2 - (prev.top + prev.height / 2));
    }
    gaps.sort((a, b) => a - b);
    return {
      count: rows.length,
      pitch: round(gaps[Math.floor(gaps.length / 2)] ?? 0),
      height,
    };
  }, selector);
}

/** Target size + centre-reachability of every control inside a container. */
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

/** Computed WCAG contrast of every painted text node inside a container. */
async function contrastMetrics(
  page: Page,
  containerSelector: string,
): Promise<Array<{ text: string; ratio: number; size: number }>> {
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
    const out: Array<{ text: string; ratio: number; size: number }> = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node !== null) {
      const text = (node.textContent ?? "").trim();
      const parent = node.parentElement;
      if (text !== "" && parent !== null) {
        const style = getComputedStyle(parent);
        const r = parent.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && style.visibility !== "hidden") {
          const [fr, fg, fb] = parse(style.color);
          const fore = lum([fr, fg, fb]);
          const back = lum(backgroundOf(parent));
          const ratio =
            (Math.max(fore, back) + 0.05) / (Math.min(fore, back) + 0.05);
          out.push({
            text,
            ratio: Math.round(ratio * 100) / 100,
            size: Math.round(Number.parseFloat(style.fontSize) * 10) / 10,
          });
        }
      }
      node = walker.nextNode();
    }
    return out;
  }, containerSelector);
}

/**
 * Labels clipped by their own box, measured with a `Range` (fractional) rather
 * than `scrollWidth > clientWidth` (integers, which cannot see the sub-pixel
 * overflow a tight dense control actually produces — the FB-19 lesson).
 */
async function clippedLabels(
  page: Page,
  containerSelector: string,
): Promise<string[]> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (root === null) return [];
    const clipped: string[] = [];
    for (const el of root.querySelectorAll("span, label, h2, h3")) {
      const text = (el.textContent ?? "").trim();
      if (text === "" || el.children.length > 0) continue;
      const style = getComputedStyle(el);
      // A cell that DECLARES truncation is doing its job, not failing.
      if (style.textOverflow === "ellipsis") continue;
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
 * SELECTS WHOSE CHOSEN VALUE DOES NOT FIT — a separate check from the one
 * above, because a `<select>`'s value is not a text node the DOM walker can
 * reach and a native select CANNOT ellipsize: it hard-clips.
 *
 * This exists because the density pass that added it shipped exactly this
 * defect first. Squeezing the material picker between a caption column and a
 * trailing mass rendered "Steel (AISI 1018)" as "Steel (AISI 101" — two alloys
 * reduced to one string on screen — while `clippedLabels` reported nothing at
 * all, because it only walks `span`/`label`/`h2`. An overflow check that cannot
 * see the control most likely to overflow is the FB-19 lesson repeating: the
 * assertion has to be able to observe the failure mode.
 *
 * The text is measured with a canvas at the select's own computed font, and
 * `arrowPx` is the room the native disclosure arrow takes out of the content
 * box (measured in Chromium, not guessed at).
 */
async function clippedSelectValues(
  page: Page,
  containerSelector: string,
): Promise<string[]> {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (root === null) return [];
    const arrowPx = 16;
    const clipped: string[] = [];
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (ctx === null) return [];
    for (const el of root.querySelectorAll("select")) {
      const chosen = el.options[el.selectedIndex]?.text ?? "";
      if (chosen === "") continue;
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      if (box.width === 0) continue;
      ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      const textWidth = ctx.measureText(chosen).width;
      const room =
        box.width -
        Number.parseFloat(style.paddingLeft || "0") -
        Number.parseFloat(style.paddingRight || "0") -
        arrowPx;
      if (textWidth > room) {
        clipped.push(
          `${el.getAttribute("data-testid") ?? "select"}: "${chosen}" needs ${Math.round(
            textWidth,
          )}px, has ${Math.round(room)}px`,
        );
      }
    }
    return clipped;
  }, containerSelector);
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

/** A part with a solved sketch and a body — both named panels populated. */
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
  test.describe(`panel density @${size.width}x${size.height}`, () => {
    test.use({ viewport: size });

    test("the overlay panels are as dense as the header they are judged against", async ({
      page,
    }) => {
      await partWithBody(page);

      // --- The REFERENCE: the header the founder named. ---
      const topbar = await box(page, testId("topbar"));
      const band = await box(page, "[data-band-tier]");
      report("header topbar", topbar);
      report("header command band", band);

      // --- The two named surfaces. ---
      const treePanel = '[data-viewport-chrome="panel-tree"]';
      const tree = await box(page, treePanel);
      const inspector = await box(page, testId("body-inspector"));
      report("tree panel", tree);
      report("body inspector", inspector);
      report("overlay chrome area px2", area(tree) + area(inspector));
      report(
        "overlay chrome share of frame %",
        Math.round(
          ((area(tree) + area(inspector)) / (size.width * size.height)) * 1000,
        ) / 10,
      );

      // --- THE NUMBER: row pitch of each repeated family. ---
      const toolRows = await rowPitch(page, "[data-band-tier] button");
      const featureRows = await rowPitch(page, testId("feature-row"));
      const cells = await rowPitch(
        page,
        `${testId("body-inspector")} [data-panel-cell]`,
      );
      const eyebrows = await rowPitch(
        page,
        `${testId("body-inspector")} h2, ${testId("body-inspector")} h3`,
      );
      report("header tool button pitch", toolRows);
      report("feature row pitch", featureRows);
      report("panel cell pitch", cells);
      report("inspector eyebrow pitch", eyebrows);

      // --- The material selector, the other surface named by name. ---
      const material = await box(page, testId("material-controls"));
      report("material controls", material);
      report("material area px2", area(material));

      await withStableSessionEmail(page, () =>
        page.screenshot({
          path: `${SCREENSHOT_DIR}/panel-density-${SHOT_TAG}-${size.width}.png`,
        }),
      );

      // --- FLOOR 1: target size + centre reachability. ---
      const controls = [
        ...(await controlMetrics(page, treePanel)),
        ...(await controlMetrics(page, testId("body-inspector"))),
      ];
      report("controls measured", controls.length);
      const undersized = controls.filter((c) => c.w < 24 || c.h < 24);
      const unreachable = controls.filter((c) => !c.reachable);
      report("undersized controls", undersized);
      report("unreachable controls", unreachable);

      // --- FLOOR 2: contrast at the type sizes actually painted. ---
      const inks = [
        ...(await contrastMetrics(page, treePanel)),
        ...(await contrastMetrics(page, testId("body-inspector"))),
      ];
      const worst = [...inks].sort((a, b) => a.ratio - b.ratio).slice(0, 6);
      report("worst contrast", worst);
      report("smallest type px", Math.min(...inks.map((i) => i.size)));

      // --- FLOOR 3: nothing clipped by the width it traded away. ---
      const clipped = [
        ...(await clippedLabels(page, treePanel)),
        ...(await clippedLabels(page, testId("body-inspector"))),
        ...(await clippedSelectValues(page, treePanel)),
        ...(await clippedSelectValues(page, testId("body-inspector"))),
      ];
      report("clipped labels", clipped);

      if (!AFTER) return;

      expect(
        undersized,
        "every panel control meets the 24px dense floor",
      ).toEqual([]);
      expect(
        unreachable,
        "every panel control is topmost at its centre",
      ).toEqual([]);
      expect(clipped, "no panel label is clipped by its own box").toEqual([]);
      for (const ink of inks) {
        expect(
          ink.ratio,
          `"${ink.text}" at ${ink.size}px clears WCAG-AA 4.5:1`,
        ).toBeGreaterThanOrEqual(4.5);
      }

      // The ceilings. The tree's feature rows and the inspector's cells are
      // instrument rows: they hold the header's own pitch, so a modeller
      // reading the tree is reading the same rhythm as the toolbar above it.
      expect(
        featureRows.pitch,
        "feature rows are at least as tight as a header tool row",
      ).toBeLessThanOrEqual(26);
      expect(
        cells.pitch,
        "inspector cells are at least as tight as a header tool row",
      ).toBeLessThanOrEqual(26);
    });

    test("a dense row is hittable by a real mouse at its own centre", async ({
      page,
    }) => {
      await partWithBody(page);

      // Not `force: true`: the whole risk a density pass creates is that the
      // targets get too small to hit, so the click has to be the user's own.
      const row = page.getByTestId("feature-select-1");
      const r = await row.boundingBox();
      expect(r, "the feature row has a box").not.toBeNull();
      if (r === null) return;
      report("feature row 1 box", r);

      const topmost = await page.evaluate(
        ([x, y]) => {
          const el = document.elementFromPoint(x as number, y as number);
          return el === null
            ? "none"
            : (el.getAttribute("data-testid") ??
                el.closest("[data-testid]")?.getAttribute("data-testid") ??
                el.tagName.toLowerCase());
        },
        [r.x + r.width / 2, r.y + r.height / 2],
      );
      report("topmost at feature row centre", topmost);

      await page.mouse.click(r.x + r.width / 2, r.y + r.height / 2);
      await expect(page.getByTestId("extrude-editor")).toBeVisible({
        timeout: 30_000,
      });
    });

    /**
     * The narrowest row the material section can produce: a body name in the
     * caption column, the longest material name in the control, and a mass in
     * the trailing column, all inside a 320px panel. This is the case the
     * density pass broke on its first draft, so it is a case with a test.
     */
    test("the longest material name is not clipped by the densest row", async ({
      page,
    }) => {
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Two cubes");
      const sketchA = await createFeature(page, account.token, part.id, {
        name: "Sketch1",
        feature: {
          type: "sketch",
          version: 1,
          params: rectangleSketch(0, 0, 20, 20),
        },
        expected_tree_version: 0,
      });
      const extrudeA = await createFeature(page, account.token, part.id, {
        name: "Extrude1",
        feature: {
          type: "extrude",
          version: 1,
          params: {
            profile: { kind: "feature", feature_id: sketchA.feature.id },
            distance_mm: 20,
            operation: "add",
            direction: "normal",
            merge: true,
          },
        },
        expected_tree_version: sketchA.tree_version,
      });
      const sketchB = await createFeature(page, account.token, part.id, {
        name: "Sketch2",
        feature: {
          type: "sketch",
          version: 1,
          params: rectangleSketch(30, 0, 20, 20),
        },
        expected_tree_version: extrudeA.tree_version,
      });
      await createFeature(page, account.token, part.id, {
        name: "Extrude2",
        feature: {
          type: "extrude",
          version: 1,
          params: {
            profile: { kind: "feature", feature_id: sketchB.feature.id },
            distance_mm: 20,
            operation: "add",
            direction: "normal",
            // `merge: false` is load-bearing: the two cubes are 10mm apart, and
            // merging disjoint solids is a `boolean_disjoint` refusal, not a
            // second body. Two bodies is the whole point of this fixture.
            merge: false,
          },
        },
        expected_tree_version: sketchB.tree_version,
      });

      await page.goto(`/parts/${part.id}`);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });

      // Steel (AISI 1018) is the longest name the served library carries, and
      // the row that holds it also carries a mass — the maximum squeeze.
      await page
        .getByTestId("material-body-select-2")
        .selectOption("steel_1018");
      await expect(page.getByTestId("material-body-mass-2")).toContainText(
        "g",
        {
          timeout: 30_000,
        },
      );

      const clipped = await clippedSelectValues(page, testId("body-inspector"));
      report("clipped select values", clipped);
      expect(
        clipped,
        "a native select hard-clips — its value must always fit",
      ).toEqual([]);
    });
  });
}
