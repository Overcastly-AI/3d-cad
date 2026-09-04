/**
 * SEL-8 — HOVERING THE REAL EDGE LIGHTS IT UP.
 *
 * ## What this pins, and why it is not what the ticket expected
 *
 * `docs/AUDIT-PRODUCT.md` R-8 reported that in Fillet's `PICK EDGES` mode a
 * 5 px sweep across the hub/flange junction produced "no hover highlight, no
 * readout, no preselection anywhere along the real edge — only its diamond is a
 * target", and the ticket offered three candidate causes: a regression since
 * SEL-4, a hit-test wired for CLICK but not HOVER, or Fillet never wired to it
 * at all. Measured against the audit's own part, all three are wrong.
 *
 * SEL-4's hit-test was intact and covered BOTH gestures: the hover state fired
 * correctly along the real edge the whole time. What was never wired was the
 * FEEDBACK. The highlight was a 1 px `lineBasicMaterial` drawn exactly
 * coincident with the body's own surface, so it lost the depth test and was
 * discarded — hovering the junction changed 13 of 1,363,200 canvas pixels, i.e.
 * nothing. The auditor was looking at the screen and the screen was telling the
 * truth. (`overlaySegments.HighlightLines` has the mechanism and the fix.)
 *
 * ## Why every existing pick spec was green through all of it
 *
 * They assert on `data-edge-pick-hover`, the QA stamp — which is set by the
 * hit-test, one layer ABOVE the draw. That is the family CLAUDE.md keeps
 * paying for: an assertion that cannot observe the failure mode. So the
 * assertion here is CANVAS PIXELS in the highlight's own token colour, which is
 * the thing the user actually receives, and the stamp is checked only as a
 * cross-reference. Reverting `HighlightLines` to `Segments` fails this spec on
 * the pixel count while leaving the stamp assertions green — i.e. it fails for
 * exactly the reason the audit filed, which the old assertions could not.
 *
 * The pick point is chosen on the edge's own polyline and PROVED to be outside
 * every diamond's box before it is used, so "the real edge, not its mark" is a
 * measured property of this test rather than a claim in its title. Nothing here
 * uses `click({ force: true })`.
 */
import { expect, test, type Page } from "./fixtures";

import { seedShaftCoupling } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/** Hover brass (`measure.edgeHover` = `color.brassHover`). */
const HOVER_RGB = [0xef, 0xc9, 0x8a] as const;
/** Selection brass (`measure.edgeSelected` = `color.brass`). */
const SELECTED_RGB = [0xe3, 0xa6, 0x4b] as const;
/** Per-channel slack, for antialiasing against the matcap body. */
const CHANNEL_TOLERANCE = 18;

/**
 * The floor a highlight must clear to count as DRAWN.
 *
 * Not a tuned number: the measured readings are 0 px broken and 348 px fixed,
 * so anything in the low hundreds separates them by an order of magnitude.
 * 60 leaves room for a smaller viewport or a differently-framed part without
 * leaving room for "a handful of stray antialiased pixels".
 */
const HIGHLIGHT_MIN_PX = 60;

/** Canvas pixels within tolerance of each highlight colour. */
async function brassPixels(
  page: Page,
): Promise<{ hover: number; selected: number }> {
  return page.evaluate(
    ({ hoverRgb, selectedRgb, slack }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (!canvas) return { hover: -1, selected: -1 };
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return { hover: -1, selected: -1 };
      ctx.drawImage(canvas, 0, 0);
      const data = ctx.getImageData(0, 0, probe.width, probe.height).data;
      const near = (i: number, rgb: readonly number[]) =>
        Math.abs((data[i] as number) - (rgb[0] as number)) < slack &&
        Math.abs((data[i + 1] as number) - (rgb[1] as number)) < slack &&
        Math.abs((data[i + 2] as number) - (rgb[2] as number)) < slack;
      let hover = 0;
      let selected = 0;
      for (let i = 0; i < data.length; i += 4) {
        if (near(i, hoverRgb)) hover += 1;
        if (near(i, selectedRgb)) selected += 1;
      }
      return { hover, selected };
    },
    {
      hoverRgb: [...HOVER_RGB],
      selectedRgb: [...SELECTED_RGB],
      slack: CHANNEL_TOLERANCE,
    },
  );
}

/** Every pick mark's client box — what a point must avoid to be "the edge". */
async function markBoxes(page: Page, prefix: string) {
  return page.evaluate(
    (testIdPrefix) =>
      [...document.querySelectorAll(`[data-testid^="${testIdPrefix}"]`)].map(
        (el) => {
          const r = el.getBoundingClientRect();
          return {
            id: el.getAttribute("data-testid") ?? "?",
            label: el.getAttribute("aria-label") ?? "",
            left: r.left,
            top: r.top,
            right: r.right,
            bottom: r.bottom,
          };
        },
      ),
    prefix,
  );
}

/**
 * Move and let the hover settle. `page.mouse.move` resolves when the CDP event
 * is dispatched, not when React has re-rendered and the draw has landed, so a
 * bare read returns the PREVIOUS point's answer.
 */
async function hoverAt(page: Page, x: number, y: number): Promise<void> {
  await page.mouse.move(x, y);
  await waitForFrames(page, 3);
}

/**
 * THE EDGE R-8 NAMES, found by its accessible name.
 *
 * Not "whichever edge a sweep meets first", and the difference is the whole
 * value of this test. The first draft took the first live point on a vertical
 * sweep, which landed on the hub's TOP circle — a convex edge whose polyline
 * pokes clear of the tessellated surface here and there, so it survived the
 * depth fight at **68 px** even with the defect present, against a floor of 60.
 * The mutation run is what caught it: a spec that fails by 13 px is a spec that
 * passes next week. The hub/flange junction, which is what the auditor actually
 * swept, is the CONCAVE case and reads a clean 0 broken against 348 fixed.
 *
 * Its label is quoted verbatim in R-8, so this lookup also ties the fixture to
 * the report.
 */
async function junctionEdgeIndex(page: Page): Promise<number> {
  const boxes = await markBoxes(page, "edge-pick-");
  const mark = boxes.find((b) =>
    b.label.includes("circle, centred at -13.9, 0, 8 millimetres"),
  );
  expect(
    mark,
    "the fixture must carry the hub/flange junction R-8 swept " +
      '("Edge N, circle, centred at -13.9, 0, 8 millimetres")',
  ).toBeDefined();
  return Number((mark?.id ?? "").replace("edge-pick-", ""));
}

export interface EdgePoint {
  x: number;
  y: number;
}

/**
 * A point that addresses `index` AND lies outside every pick mark's box.
 *
 * Walks columns outward from the edge's own mark, because that mark sits at the
 * edge's mid-span so the geometry is certainly nearby — a blind raster of the
 * frame would cost hundreds of settled moves to learn the same thing. The
 * mark's own box is excluded, so a hit here is the EDGE answering and never the
 * diamond: that is the acceptance criterion, measured rather than asserted.
 */
async function pointOnEdge(
  page: Page,
  viewport: ReturnType<Page["getByTestId"]>,
  index: number,
  prefix: string,
  stampAttribute: string,
): Promise<EdgePoint | null> {
  const boxes = await markBoxes(page, prefix);
  const mark = boxes.find((b) => b.id === `${prefix}${index}`);
  const cx = mark === undefined ? 0 : Math.round((mark.left + mark.right) / 2);
  const cy = mark === undefined ? 0 : Math.round((mark.top + mark.bottom) / 2);
  const insideAMark = (x: number, y: number) =>
    boxes.some(
      (b) =>
        x >= b.left - 1 &&
        x <= b.right + 1 &&
        y >= b.top - 1 &&
        y <= b.bottom + 1,
    );
  for (const dx of [0, 24, -24, 48, -48, 72, -72, 96, -96, 120, -120]) {
    for (let dy = -120; dy <= 120; dy += 5) {
      const x = cx + dx;
      const y = cy + dy;
      if (insideAMark(x, y)) continue;
      await page.mouse.move(x, y);
      await waitForFrames(page, 1);
      if ((await viewport.getAttribute(stampAttribute)) === String(index)) {
        return { x, y };
      }
    }
  }
  return null;
}

async function openCouplingWithFilletArmed(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Shaft coupling");
  await seedShaftCoupling(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(16);

  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);

  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-mode-pick").click();
  await expect(page.locator('[data-testid^="edge-pick-"]').first()).toBeVisible(
    { timeout: 20_000 },
  );
  await waitForFrames(page, 4);
}

test.describe("SEL-8 — the hovered edge is drawn, not just recorded", () => {
  test("hovering the real edge geometry highlights it, and picking it there works", async ({
    page,
  }) => {
    // The sweep is ~140 settled pointer moves plus four full-canvas reads; the
    // config's 60 s default is one slow shard away from a false red.
    test.setTimeout(300_000);
    await openCouplingWithFilletArmed(page);
    const viewport = page.getByTestId("viewport");

    // The fixture, asserted — if this count moves, the part changed and every
    // number below stops being comparable with the audit's.
    await expect(page.locator('[data-testid^="edge-pick-"]')).toHaveCount(21);

    // R-8's own probe: sweep straight down across the hub/flange junction and
    // record which edge each point addresses.
    const box = await viewport.boundingBox();
    expect(box).not.toBeNull();
    const columnX = Math.round((box?.x ?? 0) + (box?.width ?? 0) / 2);
    const firstY = Math.round((box?.y ?? 0) + (box?.height ?? 0) * 0.12);
    const lastY = Math.round((box?.y ?? 0) + (box?.height ?? 0) * 0.92);
    const sweep: { y: number; edge: string | null }[] = [];
    for (let y = firstY; y <= lastY; y += 5) {
      await page.mouse.move(columnX, y);
      await waitForFrames(page, 1);
      sweep.push({
        y,
        edge: await viewport.getAttribute("data-edge-pick-hover"),
      });
    }
    const live = sweep.filter((s) => s.edge !== null);
    console.log(
      `    [SEL-8] sweep x=${columnX}, ${sweep.length} points at 5 px: ` +
        `${live.length} addressed an edge ` +
        `(${[...new Set(live.map((s) => s.edge))].sort().join(",")})`,
    );
    // The audit measured ZERO along this line. Anything above zero is a
    // different product; the floor is deliberately low because the claim is
    // "the edge is a target", not "this many pixels of it are".
    expect(
      live.length,
      "a vertical sweep across the part must address SOME edge — R-8 measured none",
    ).toBeGreaterThan(0);

    // THE POINT UNDER TEST: on the hub/flange junction R-8 named, provably not
    // on any mark.
    const junction = await junctionEdgeIndex(page);
    const target = await pointOnEdge(
      page,
      viewport,
      junction,
      "edge-pick-",
      "data-edge-pick-hover",
    );
    expect(
      target,
      `no point outside the marks addresses the junction (edge ${junction})`,
    ).not.toBeNull();
    const { x: targetX, y: targetY } = target as EdgePoint;

    // And prove it with the user's own mechanism: at this point the topmost
    // element is the CANVAS, so a real mouse lands on geometry, not on a mark.
    const topmost = await page.evaluate(
      ({ x, y }) => {
        const el = document.elementFromPoint(x, y);
        return el === null ? "null" : el.tagName;
      },
      { x: targetX, y: targetY },
    );
    expect(
      topmost,
      `(${targetX},${targetY}) must resolve to the canvas, not a DOM mark`,
    ).toBe("CANVAS");

    // NON-VACUITY, before the claim: parked off the body, no brass at all. A
    // stuck highlight would otherwise satisfy every assertion below.
    await hoverAt(page, 5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
    const parked = await brassPixels(page);
    expect(parked.hover, "no hover brass with the pointer off the body").toBe(
      0,
    );
    expect(
      parked.selected,
      "no selection brass before anything is picked",
    ).toBe(0);

    // THE CLAIM. Hover the real edge; the edge is DRAWN in hover brass.
    await hoverAt(page, targetX, targetY);
    expect(
      await viewport.getAttribute("data-edge-pick-hover"),
      "the hit-test still addresses the junction from this point",
    ).toBe(String(junction));
    const hovered = await brassPixels(page);
    console.log(
      `    [SEL-8] hover (${targetX},${targetY}) junction edge ${junction}: ` +
        `${hovered.hover} px of hover brass (parked: ${parked.hover})`,
    );
    // THE ASSERTION THE OLD SPECS COULD NOT MAKE. Before this fix the stamp
    // above passed and this read 0.
    expect(
      hovered.hover,
      "the hovered edge must be VISIBLE, not merely recorded in the stamp",
    ).toBeGreaterThan(HIGHLIGHT_MIN_PX);

    // And the same point takes a real click — no `force`, the mouse where the
    // user would put it.
    await expect(page.getByTestId("selected-count")).toHaveText(
      "No edges picked",
    );
    await page.mouse.click(targetX, targetY);
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );

    // A picked edge draws in selection brass, which is a different statement
    // from the hover one — same primitive, second colour.
    await hoverAt(page, 5, 5);
    const picked = await brassPixels(page);
    console.log(
      `    [SEL-8] picked junction edge ${junction}, pointer parked: ` +
        `${picked.selected} px of selection brass`,
    );
    expect(
      picked.selected,
      "a picked edge stays lit once the pointer leaves it",
    ).toBeGreaterThan(HIGHLIGHT_MIN_PX);
    expect(picked.hover, "a picked edge is not also drawn in hover brass").toBe(
      0,
    );
  });

  test("the measure overlay's edge highlight draws too — same primitive, same fix", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await openCouplingWithFilletArmed(page);
    const viewport = page.getByTestId("viewport");

    // The junction's ordinal, read while the fillet marks still carry the
    // coordinates in their names — the measure marks are named "Edge N, circle"
    // with no coordinates, so it cannot be looked up over there.
    const junction = await junctionEdgeIndex(page);
    const filletMark = (await markBoxes(page, "edge-pick-")).find(
      (b) => b.id === `edge-pick-${junction}`,
    );

    // Leave the fillet and arm Measure, whose edge highlight used the SAME
    // one-pass primitive and was invisible for the same reason. Pinned here so
    // a future "simplify the highlight back to Segments" fails in both places
    // rather than silently restoring the defect in the quieter one.
    await page.getByTestId("fillet-cancel").click();
    await waitForFrames(page, 4);
    await page.getByTestId("measure-tool").click();
    await expect(
      page.locator('[data-testid^="measure-edge-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    // CROSS-CHECK THE INDEX SPACES rather than assuming they line up. Both
    // overlays number the same B-rep edge list, so the same ordinal must put
    // its mark in the same place; if that ever stops being true this test is
    // pointing at a different edge and should say so instead of measuring the
    // wrong one quietly.
    const measureMark = (await markBoxes(page, "measure-edge-")).find(
      (b) => b.id === `measure-edge-${junction}`,
    );
    expect(
      measureMark,
      "the measure overlay offers the same ordinal",
    ).toBeDefined();
    expect(measureMark?.label).toContain("circle");
    expect(
      Math.hypot(
        (measureMark?.left ?? 0) - (filletMark?.left ?? 0),
        (measureMark?.top ?? 0) - (filletMark?.top ?? 0),
      ),
      "the two overlays put edge " + junction + "'s mark in the same place",
    ).toBeLessThan(4);

    await hoverAt(page, 5, 5);
    const parked = await brassPixels(page);
    expect(parked.hover).toBe(0);

    const target = await pointOnEdge(
      page,
      viewport,
      junction,
      "measure-edge-",
      "data-measure-edge-hover",
    );
    expect(target, "the junction is addressable in Measure too").not.toBeNull();
    const { x, y } = target as EdgePoint;
    await hoverAt(page, x, y);
    const lit = (await brassPixels(page)).hover;
    console.log(
      `    [SEL-8] measure hover (${x},${y}) junction edge ${junction}: ` +
        `${lit} px of hover brass`,
    );
    expect(
      lit,
      "a measured edge under the cursor must be visible, not just stamped",
    ).toBeGreaterThan(HIGHLIGHT_MIN_PX);
  });
});
