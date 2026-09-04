import { expect, test, type Page } from "./fixtures";

import {
  authorBoltMates,
  setupTwoInstances,
  waitForSolved,
} from "./assemblyFlow";
import { SCREENSHOT_DIR } from "./support";

/**
 * Fit-scaling an ASSEMBLY sheet (ASMDRAW-FIT-1b).
 *
 * The layout action has always fitted its scale to the source's bounding box —
 * for a PART. An assembly kept whatever scale the picker was on, so the founder's
 * parts-list rig (instances seeded 80 mm apart, unmated) laid out at 1:1 with its
 * iso view oversized and its RIGHT view's frame straddling the title block
 * (`docs/screenshots/drawing-assembly-parts-list.png`). The fix reads
 * `GET /api/v1/assemblies/{id}/extents` — the SOLVED compound's AABB.
 *
 * Two properties, and the second is the one that is easy to fake:
 *
 *  - the sheet is FITTED: no view frame lands on the title block. Measured as
 *    geometry — every frame rect against the title-block rect — because that is
 *    the thing the founder saw. `toBeVisible()` is a box property and is true of
 *    a frame drawn straight through the title block.
 *  - the fit reads the SOLVED pose, not the authored seeds. The rig makes those
 *    two answers DIFFERENT (seeds span 120 mm in x, the bolted compound 40), and
 *    `layout.test.ts` pins the scales they imply: 1:2 for the seeds, 1:1 for the
 *    solve. Note the status cannot stand in for this — geometry's
 *    `test_status_alone_cannot_distinguish_the_two` shows the mated and unmated
 *    rigs BOTH report `under_constrained`, so a spec asserting on the status (or
 *    on the 200) passes in a world where the route answers with seeds.
 */

/** The rig's two readings, kept next to the scales they imply. */
const SEEDED_X_MM = 120; // two 40 mm plates, the second seeded at x = 80
const SEEDED_SCALE = "1:2";
const SOLVED_SCALE = "1:1"; // bolted flush: 40 x 25 x 20 fits its cells at 1:1

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Every view FRAME on the sheet plus the title block, in viewport px.
 *
 * `drawing-view-drag` is the frame rect the placement chrome draws (geometry
 * bounds + pad) and is present at rest, unlike `drawing-view-frame`, which only
 * paints while a view is hovered/dragged. Reading the frame rather than the ink
 * is deliberate: a view whose ink clears the title block by a millimetre while
 * its frame sits on top of it is still the defect the founder reported.
 */
async function sheetRects(page: Page): Promise<{
  title: Rect;
  frames: { view: string; rect: Rect }[];
}> {
  return page.evaluate(() => {
    const box = (el: Element) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    };
    const titleEl = document.querySelector(
      '[data-testid="drawing-title-block"]',
    );
    if (titleEl === null) throw new Error("no title block on the sheet");
    const frames = Array.from(
      document.querySelectorAll('[data-testid="drawing-view-drag"]'),
    ).map((el) => ({
      view: el.closest("[data-view]")?.getAttribute("data-view") ?? "?",
      rect: box(el),
    }));
    return { title: box(titleEl), frames };
  });
}

/** Overlap area (px^2) of two rects — 0 when they are disjoint. */
function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

/** The solved extents the gateway reports for this assembly, in mm. */
async function solvedExtents(
  page: Page,
  token: string,
  assemblyId: string,
): Promise<{ x: number; y: number; z: number; status: string }> {
  const response = await page.request.get(
    `/api/v1/assemblies/${assemblyId}/extents`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok()) {
    throw new Error(
      `extents failed: ${response.status()} ${await response.text()}`,
    );
  }
  const body = (await response.json()) as {
    bounding_box: {
      min: { x: number; y: number; z: number };
      max: { x: number; y: number; z: number };
    } | null;
    status: string;
  };
  const box = body.bounding_box;
  if (box === null) throw new Error("the rig reported no bounding box");
  return {
    x: box.max.x - box.min.x,
    y: box.max.y - box.min.y,
    z: box.max.z - box.min.z,
    status: body.status,
  };
}

/** Assembly workspace → the Drawing action → the sheet, source pre-selected. */
async function openDrawingFromAssembly(page: Page): Promise<void> {
  const draft = page.getByTestId("assembly-drawing");
  await expect(draft).toBeEnabled();
  await draft.click();
  await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+\?source=/, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("drawing-part-select")).toBeVisible();
}

/** Lay the four standard views out and wait for the composed sheet. */
async function layOut(page: Page): Promise<void> {
  await page.getByTestId("drawing-autolayout").click();
  await expect(
    page.locator('[data-testid="drawing-view"]').first(),
  ).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.locator('[data-testid="drawing-view"]')).toHaveCount(4, {
    timeout: 60_000,
  });
}

test.describe("Drawings — an assembly sheet fits its paper", () => {
  test("an assembly seeded apart fits the sheet, and a mate solved afterwards does not re-scale it", async ({
    page,
  }) => {
    const { idA, idB, token, assemblyId } = await setupTwoInstances(page);

    // The premise, from the server rather than assumed: unmated, the solved
    // compound IS the seeds — 120 mm across, which does not fit A4 at 1:1.
    const seeded = await solvedExtents(page, token, assemblyId);
    expect(seeded.x).toBeCloseTo(SEEDED_X_MM, 1);

    await openDrawingFromAssembly(page);
    await layOut(page);

    // The sheet reduced the picked 1:1 to the scale the extents earn. Read from
    // the band's post-layout readout (derived from the PERSISTED view scale, so
    // this is what was written, not what the picker was left showing) and from
    // the title block the exporter stamps.
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText(
      SEEDED_SCALE,
    );
    await expect(page.getByTestId("title-block-scale")).toHaveText(
      SEEDED_SCALE,
    );

    // --- the founder-visible property: nothing lands on the title block ------
    const { title, frames } = await sheetRects(page);
    expect(frames).toHaveLength(4);
    const overlaps = frames.map((f) => ({
      view: f.view,
      overlap: Math.round(overlapArea(f.rect, title)),
    }));
    // Filtered rather than looped so a failure PRINTS which view straddles the
    // block and by how much (it was `right`, before the fix), not merely that
    // one did.
    expect(overlaps.filter((o) => o.overlap > 0)).toEqual([]);
    // And the sheet is not fitted by being empty: the front view carries ink.
    const edges = await page
      .locator('[data-testid="drawing-view"][data-view="front"]')
      .evaluate(
        (g) => g.querySelectorAll("line, circle, polyline, path").length,
      );
    expect(edges).toBeGreaterThan(8);

    // The founder shot for this fix (refresh with UPDATE_SCREENSHOTS=1). Its
    // `-before` twin was captured from the same rig with the assembly branch of
    // `fetchSourceExtents` disabled: 1:1, with the RIGHT view's frame 337 px^2
    // inside the title block.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-assembly-fit-after.png`,
    });

    // --- a later solve does NOT move a sheet the user already laid out -------
    // Bolting the plates together shrinks the compound to 40 mm, which would fit
    // 1:1. The sheet stays at 1:2 on purpose: the scale of a laid-out sheet
    // belongs to the user (they can re-pick it, and a dragged view is pinned),
    // and re-flowing paper underneath someone is the surprise the flow rule
    // exists to prevent. The sheet's own layout checks report; they never move.
    const drawingUrl = page.url();
    await page.goto(`/assemblies/${assemblyId}`);
    await waitForSolved(page);
    await authorBoltMates(page, idA, idB);
    await waitForSolved(page);
    const solved = await solvedExtents(page, token, assemblyId);
    expect(solved.x).toBeLessThan(seeded.x - 1); // the solve really did move it

    await page.goto(drawingUrl);
    await expect(page.locator('[data-testid="drawing-view"]')).toHaveCount(4, {
      timeout: 60_000,
    });
    await expect(page.getByTestId("drawing-scale-readout")).toHaveText(
      SEEDED_SCALE,
    );
  });

  test("the fit reads the SOLVED compound, not the authored seed placements", async ({
    page,
  }) => {
    const { idA, idB, token, assemblyId } = await setupTwoInstances(page);
    await authorBoltMates(page, idA, idB);
    await waitForSolved(page);

    // The discriminator: the solve has moved the compound well inside its seeds.
    // Both readings report `under_constrained`, which is exactly why the status
    // cannot be the assertion.
    //
    // BOUNDED, NOT PINNED. Two mates do not determine six DOF, so the bolted
    // pose is a best fit (§2.4) carrying a small residual rotation, and the
    // compound's AABB is a little wider than the 40 mm plate — measured 42.2 mm
    // here. Pinning that number would make this a solver-precision tripwire; the
    // property under test is that the reading is a stacked pair of plates and
    // nowhere near the 120 mm the SEEDS span. Every value in this band fits at
    // 1:1 and none of it fits at 2:1, so the scale assertion below stays exact.
    const solved = await solvedExtents(page, token, assemblyId);
    expect(solved.x).toBeGreaterThan(38);
    expect(solved.x).toBeLessThan(60);
    expect(solved.z).toBeGreaterThan(18); // both plates, stacked (10 + 10)
    expect(solved.x).toBeLessThan(SEEDED_X_MM - 1);

    await openDrawingFromAssembly(page);
    // Pick 2:1 so the outcome separates three worlds: no fit at all leaves 2:1,
    // a fit that folded the SEEDS gives 1:2, and a fit on the solved compound
    // gives 1:1. Only the last is correct, and it is not the default.
    await page.getByTestId("drawing-scale-select").selectOption("2:1");
    await layOut(page);

    await expect(page.getByTestId("drawing-scale-readout")).toHaveText(
      SOLVED_SCALE,
    );
    await expect(page.getByTestId("title-block-scale")).toHaveText(
      SOLVED_SCALE,
    );

    const { title, frames } = await sheetRects(page);
    expect(frames).toHaveLength(4);
    for (const f of frames) {
      expect(
        Math.round(overlapArea(f.rect, title)),
        `the ${f.view} view frame overlaps the title block`,
      ).toBe(0);
    }
  });
});
