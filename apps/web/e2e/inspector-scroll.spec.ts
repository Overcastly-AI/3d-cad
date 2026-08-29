import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * T-18 — the inspector at the documented 1280x800 floor.
 *
 * Three audit passes reported the same thing: on a finished part the `Min` row
 * sat at y 474..491 while the pinned EXPORT strip owned y 459..589, so
 * `document.elementFromPoint` at the Min row's own coordinates returned
 * `SPAN:"Export"` and Min / Max / TOPOLOGY / STATUS were all unreachable. The
 * cause was not that the panel lacked a scroll container — it had one — but
 * that the container was INVISIBLE: the clip landed mid-row (`Max 150, 80, 8`
 * sliced through its digits) with no scrollbar, no rule and no mark, on a
 * platform whose overlay scrollbars take no layout space and appear only while
 * scrolling. Measured here: 542 px of title block in a 347 px column, gutter
 * 0 px. An overflow with no affordance is a truncation.
 *
 * This spec pins the fix at the floor: the region SAYS it is clipped
 * (`ScrollRegion`'s break rule + `data-scroll-edges` readout), it is reachable
 * by keyboard, and every row the audit called covered resolves to ITSELF under
 * `elementFromPoint` once brought into view.
 */

const PLATE_150x80 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 150, y: 0 } },
    { id: "e2", kind: "line", start: { x: 150, y: 0 }, end: { x: 150, y: 80 } },
    { id: "e3", kind: "line", start: { x: 150, y: 80 }, end: { x: 0, y: 80 } },
    { id: "e4", kind: "line", start: { x: 0, y: 80 }, end: { x: 0, y: 0 } },
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
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 150 },
    { kind: "distance", entity: "e2", value_mm: 80 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** The audit's subject: a 150 x 80 x 8 plate, solved, on a 1280x800 frame. */
async function seedPlate(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(
    page,
    account.token,
    "Laptop floor plate",
  );
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: PLATE_150x80 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 8,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part.id;
}

/**
 * What `document.elementFromPoint` returns at the CENTRE of `testId`'s own box,
 * reported as the nearest ancestor carrying a testid. The audit's exact probe.
 */
async function ownerAtCentreOf(page: Page, testId: string): Promise<string> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"]`);
    if (el === null) return "MISSING";
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(
      Math.round(r.x + r.width / 2),
      Math.round(r.y + r.height / 2),
    );
    if (hit === null) return "NOTHING";
    const owner = hit.closest("[data-testid]");
    return owner === null
      ? `UNOWNED:${hit.tagName}:${hit.textContent ?? ""}`
      : (owner.getAttribute("data-testid") ?? "");
  }, testId);
}

test.describe("inspector at the 1280x800 floor — nothing is silently cut", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the clipped panel says so, and every readout is reachable", async ({
    page,
  }) => {
    const partId = await seedPlate(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("prop-volume")).toContainText("96,000", {
      timeout: 30_000,
    });

    // Assign a material — the audit measured a FINISHED part, and a material
    // adds the Mass row that pushed Min below the fold in the first place.
    await page
      .getByTestId("material-default-select")
      .selectOption("steel_1018");
    await expect(page.getByTestId("prop-mass")).toBeVisible({
      timeout: 30_000,
    });

    const region = page
      .getByTestId("body-inspector")
      .locator("xpath=ancestor::*[@data-scroll-edges][1]");

    // 1. The panel REPORTS that it is hiding content below, and draws the
    //    break rule there — the mark whose absence made this a defect for
    //    three passes. Nothing is marked at the top: we have not scrolled.
    await expect(region).toHaveAttribute("data-scroll-edges", "bottom");
    await expect(page.getByTestId("scroll-edge-bottom")).toBeVisible();
    await expect(page.getByTestId("scroll-edge-top")).toHaveCount(0);

    // 2. The travel mark is drawn, because this engine's scrollbars are
    //    OVERLAY: measured on the same frame, the viewport's gutter is 0 px,
    //    so the platform shows the user nothing until they already know to
    //    scroll. Assert the measurement, not just the mark — if a future
    //    engine draws a classic bar the mark correctly stands down, and this
    //    would otherwise fail for a reason that is not a defect.
    const gutter = await page.evaluate(() => {
      const el = document.querySelector(
        '[data-viewport-chrome="panel-inspector"] .scrollbar-instrument',
      ) as HTMLElement | null;
      return el === null ? -1 : el.offsetWidth - el.clientWidth;
    });
    if (gutter === 0) {
      await expect(page.getByTestId("scroll-travel")).toBeVisible();
    } else {
      await expect(page.getByTestId("scroll-travel")).toHaveCount(0);
    }

    // 3. It is a NAMED, FOCUSABLE region, so the readouts below the fold are
    //    reachable without a mouse (axe `scrollable-region-focusable`).
    const viewport = page.getByRole("region", { name: "Inspector readouts" });
    await expect(viewport).toHaveAttribute("tabindex", "0");

    // Before: the audit's frame — Min at the fold, Max fading into the rule.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/t18-inspector-1280.png`,
    });

    // 4. THE AUDIT'S PROBE, on every row it called covered. Each one resolves
    //    to ITSELF at its own coordinates once scrolled into view — where it
    //    used to resolve to the Export panel.
    for (const testId of [
      "prop-bbox-min",
      "prop-bbox-max",
      "prop-faces",
      "body-titleblock-footer",
    ]) {
      await page.getByTestId(testId).scrollIntoViewIfNeeded();
      expect(await ownerAtCentreOf(page, testId)).toBe(testId);
    }

    // 5. At the bottom of the travel the readout flips: the rule below goes
    //    out and the one above comes on. A mark that never changed would be
    //    decoration, and decoration is a defect (mandate 3a).
    await expect(region).toHaveAttribute("data-scroll-edges", "top");
    await expect(page.getByTestId("scroll-edge-top")).toBeVisible();
    await expect(page.getByTestId("scroll-edge-bottom")).toHaveCount(0);

    // 6. The pinned EXPORT strip never moved — it is why the body is clamped,
    //    and it must still be there after all that scrolling.
    await expect(page.getByTestId("panel-footer-inspector")).toBeVisible();

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/t18-inspector-1280-scrolled.png`,
    });
  });

  /**
   * LAYOUT-1's own acceptance criterion, which T-18's case does not cover.
   *
   * The two claims are different and the difference is the whole ticket. T-18
   * asks "can the user REACH every readout" and answers it by scrolling each row
   * into view first. LAYOUT-1 asks the geometric question the audit actually
   * measured — "does the pinned strip DRAW OVER a row that is on screen" — and a
   * spec that scrolls before probing can never see that, because scrolling is
   * what moves the row out from under the strip.
   *
   * It has to be CLIP-AWARE, and that is the trap in writing it. A row below the
   * fold has a `getBoundingClientRect` that runs straight through the strip's
   * band — the rect is the row's LAYOUT position, which a scroll container does
   * not intersect for you — so a naive rect-vs-rect sweep reports an overlap on
   * a perfectly healthy panel and would have "found" this defect on any build.
   * (Measured on the fixed tree: eight of ten rows report a rect that overlaps
   * the strip, and every one of them is simply scrolled away.) The visible band
   * is the scroll viewport's own rect; a row's REAL extent is its rect clipped to
   * that, and a row with nothing left is off-sheet, not covered.
   */
  test("LAYOUT-1: the pinned strip never draws over a readout on screen", async ({
    page,
  }) => {
    const partId = await seedPlate(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("prop-volume")).toContainText("96,000", {
      timeout: 30_000,
    });
    // The audit measured a FINISHED part: a material adds Mass and Centre of
    // mass, the two rows that pushed the bounding box down into the strip.
    await page
      .getByTestId("material-default-select")
      .selectOption("steel_1018");
    await expect(page.getByTestId("prop-mass")).toBeVisible({
      timeout: 30_000,
    });

    // Captured BEFORE the assertions so a red run still leaves the frame that
    // failed — the evidence is worth more when the gate is the thing that broke.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/layout1-inspector-1280.png`,
    });

    const layout = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>(
        '[data-viewport-chrome="panel-inspector"]',
      );
      const viewport = panel?.querySelector<HTMLElement>(
        "[data-scroll-edges] .scrollbar-instrument",
      );
      const strip = document.querySelector<HTMLElement>(
        '[data-testid="panel-footer-inspector"]',
      );
      if (!panel || !viewport || !strip) return null;
      const P = panel.getBoundingClientRect();
      const V = viewport.getBoundingClientRect();
      const S = strip.getBoundingClientRect();
      const rows = Array.from(
        panel.querySelectorAll<HTMLElement>("[data-testid^='prop-']"),
      ).map((row) => {
        const r = row.getBoundingClientRect();
        // The row as the USER has it: its box clipped to the visible band.
        const top = Math.max(r.top, V.top);
        const bottom = Math.min(r.bottom, V.bottom);
        const id = row.getAttribute("data-testid") ?? "";
        if (bottom - top <= 0) return { id, onScreen: false, owner: id };
        const hit = document.elementFromPoint(
          r.x + r.width / 2,
          (top + bottom) / 2,
        );
        const owner = hit?.closest("[data-testid]") ?? null;
        return {
          id,
          onScreen: true,
          owner:
            owner === null
              ? `UNOWNED:${hit?.tagName ?? "nothing"}`
              : (owner.getAttribute("data-testid") ?? ""),
        };
      });
      return {
        stripTopMinusBandBottom: S.top - V.bottom,
        stripBottomMinusPanelBottom: S.bottom - P.bottom,
        onScreenCount: rows.filter((row) => row.onScreen).length,
        rows,
      };
    });
    expect(
      layout,
      "the inspector panel, its scroll band and its strip",
    ).not.toBeNull();
    if (layout === null) return;

    // 1. THE GEOMETRY. The scrolling band ends exactly where the pinned strip
    //    begins: they abut, they never intersect. The audit measured a 73 px
    //    intersection here (`BOUNDING BOX` y=410..532 under an export band at
    //    y=459..590), which is the number this bound exists to keep at zero.
    expect(
      layout.stripTopMinusBandBottom,
      "the EXPORT strip must begin at or below the scrolling band's last pixel",
    ).toBeGreaterThanOrEqual(-1);

    // 2. And the strip stays inside the panel rather than hanging past it —
    //    the other way this collision can present, and the one that would put
    //    the strip over the reference cube instead of over the readouts.
    expect(
      layout.stripBottomMinusPanelBottom,
      "the EXPORT strip must not hang below the panel it is pinned to",
    ).toBeLessThanOrEqual(1);

    // 3. Every row the user can actually SEE answers to itself at its own
    //    centre — the audit's probe, run WITHOUT scrolling first, which is the
    //    condition under which it returned `SPAN:"Export"`. A count floor comes
    //    with it: a panel that rendered nothing would satisfy "no row is
    //    covered" vacuously, and a vacuous gate is the failure mode this repo
    //    keeps paying for.
    expect(
      layout.onScreenCount,
      "at least the properties block must be on screen at the 1280x800 floor",
    ).toBeGreaterThanOrEqual(6);
    for (const row of layout.rows) {
      if (!row.onScreen) continue;
      expect(
        row.owner,
        `${row.id} is on screen but a pointer at its centre lands on ${row.owner}`,
      ).toBe(row.id);
    }
  });
});
