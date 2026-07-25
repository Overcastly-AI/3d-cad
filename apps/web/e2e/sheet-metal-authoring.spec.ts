import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Sheet-metal AUTHORING UI — the honest gap made click-through. The sheet-metal
 * GEOMETRY (base flange, edge flange, unfold) shipped backend-first; until now
 * the only way to build a sheet-metal part was the API (that seeded the
 * flat-pattern founder shots). This drives the WHOLE loop through a real browser
 * against the real stack (gateway + documents + geometry, no mocks): a base
 * flange authored from a sketch by clicking, N edge flanges folded by picking a
 * straight edge, then the flat pattern unfolded from the part — all by clicking.
 *
 * Only the rectangular profile is seeded via the API (the sketcher is tested
 * elsewhere); every sheet-metal feature is authored through its editor.
 */

/** A closed rectangle profile on the XY datum (the base-flange blank). */
function rectangleSketch(width: number, height: number): unknown {
  return {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "e1",
            kind: "line",
            start: { x: 0, y: 0 },
            end: { x: width, y: 0 },
          },
          {
            id: "e2",
            kind: "line",
            start: { x: width, y: 0 },
            end: { x: width, y: height },
          },
          {
            id: "e3",
            kind: "line",
            start: { x: width, y: height },
            end: { x: 0, y: height },
          },
          {
            id: "e4",
            kind: "line",
            start: { x: 0, y: height },
            end: { x: 0, y: 0 },
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: 0,
  };
}

/** Seed a part whose only feature is a rectangular profile sketch. */
async function seedSketchPart(
  page: Page,
  name: string,
  width: number,
  height: number,
): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  const res = await page.request.post(`/api/v1/parts/${part.id}/features`, {
    data: rectangleSketch(width, height),
    headers: { Authorization: `Bearer ${account.token}` },
  });
  if (!res.ok()) {
    throw new Error(
      `e2e seed sketch failed: ${res.status()} ${await res.text()}`,
    );
  }
  return part.id;
}

/** The face count parsed from the topology readout. */
async function faceCount(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-faces").innerText();
  return Number.parseInt(text.replace(/[^\d]/g, ""), 10);
}

/**
 * Click the edge-pick node on the sheet's far (max-x) or near (min-x) SIDE — the
 * long straight edge of the top face to fold a flange off. Chosen from the
 * accessible name (x, y, z of the edge mid-span), so the pick is deterministic:
 * the extreme x, then the top of the gauge (max z), which is the plate-face edge
 * an edge flange folds about.
 */
async function pickSideEdge(page: Page, side: "left" | "right"): Promise<void> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestScore = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = (label.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
    // aria-label: "Edge N, line, centred at X, Y, Z millimetres".
    const [, x, , z] = nums;
    if (x === undefined || z === undefined) continue;
    const score = (side === "right" ? x : -x) * 1000 + z;
    if (score > bestScore) {
      bestScore = score;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Author the base flange from the seeded sketch by clicking its editor. */
async function authorBaseFlange(
  page: Page,
  gauge = "2",
  bendRadius = "3",
): Promise<void> {
  await expect(page.getByTestId("new-base-flange")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-base-flange").click();
  await expect(page.getByTestId("base-flange-editor")).toBeVisible();
  await page.getByTestId("base-flange-thickness").fill(gauge);
  await page.getByTestId("base-flange-bend-radius").fill(bendRadius);
  await page.getByTestId("base-flange-submit").click();
  await expect(page.getByTestId("base-flange-editor")).toBeHidden();
  // The sheet body renders (a flat plate is a six-faced box).
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect.poll(() => faceCount(page), { timeout: 30_000 }).toBe(6);
}

/** Author one edge flange by picking a side edge + entering the leg length. */
async function authorEdgeFlange(
  page: Page,
  side: "left" | "right",
  lengthMm: number,
): Promise<void> {
  await page.getByTestId("new-edge-flange").click();
  await expect(page.getByTestId("edge-flange-editor")).toBeVisible();
  await expect(page.getByTestId("edge-flange-pick-count")).toHaveText(
    "No edge picked",
  );
  await pickSideEdge(page, side);
  await expect(page.getByTestId("edge-flange-pick-count")).toHaveText(
    "1 edge picked",
  );
  await page.getByTestId("edge-flange-length").fill(String(lengthMm));
  await page.getByTestId("edge-flange-submit").click();
  await expect(page.getByTestId("edge-flange-editor")).toBeHidden({
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Open the flat pattern from the part — creates a drawing + unfolds the blank. */
async function openFlatPattern(page: Page): Promise<void> {
  await expect(page.getByTestId("new-flat-pattern")).toBeEnabled();
  await page.getByTestId("new-flat-pattern").click();
  // Navigation lands on the drawing; the unfold composes onto the sheet.
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
  const view = page.locator(
    '[data-testid="drawing-view"][data-view="flat_pattern"]',
  );
  await expect(view).toHaveAttribute("data-view-error", "false");
  expect(await view.locator("line, polyline").count()).toBeGreaterThan(0);
}

test("model an L-bracket by clicking: base flange → edge flange → flat pattern", async ({
  page,
}) => {
  const partId = await seedSketchPart(page, "L-bracket (clicked)", 50, 20);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(1);

  // 1) Base flange from the sketch.
  await authorBaseFlange(page);
  await expect(page.getByTestId("feature-row")).toHaveCount(2);
  await expect(page.getByTestId("feature-row").nth(1)).toContainText(
    "base flange",
  );

  // 2) One edge flange folded off the right edge → the L-bracket.
  await authorEdgeFlange(page, "right", 30);
  await expect(page.getByTestId("feature-row")).toHaveCount(3);
  await expect(page.getByTestId("feature-row").nth(2)).toContainText(
    "edge flange",
  );
  // The fold adds material + faces beyond the flat plate's six.
  await expect
    .poll(() => faceCount(page), { timeout: 30_000 })
    .toBeGreaterThan(6);
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // Founder frame of the authored body (desktop).
  await page.mouse.move(700, 450);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("viewport")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-authoring-l-body-1440.png`,
  });

  // 3) Flat pattern — reachable from the modeling flow, one click.
  await openFlatPattern(page);
  await expect(page.getByTestId("drawing-bend-table")).toBeVisible();
  await expect(page.getByTestId("drawing-bend-row")).toHaveCount(1);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-authoring-l-flat-1440.png`,
  });
});

test("model a U-channel by clicking: two edge flanges → two-bend flat pattern", async ({
  page,
}) => {
  const partId = await seedSketchPart(page, "U-channel (clicked)", 40, 20);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(1);

  await authorBaseFlange(page);
  await authorEdgeFlange(page, "right", 30);
  await authorEdgeFlange(page, "left", 25);
  await expect(page.getByTestId("feature-row")).toHaveCount(4);
  await expect
    .poll(() => faceCount(page), { timeout: 30_000 })
    .toBeGreaterThan(6);

  await openFlatPattern(page);
  // Two folds → a two-row bend table + two fold lines.
  const view = page.locator(
    '[data-testid="drawing-view"][data-view="flat_pattern"]',
  );
  expect(
    await view.locator('[data-edge-role="bend"]').count(),
  ).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId("drawing-bend-row")).toHaveCount(2);
});

test("model the founder's width-extent flange by clicking: 50-wide × 50-tall on a 100 mm edge → notched flat pattern", async ({
  page,
}) => {
  // §4.5 acceptance case: a 100×100 base (t=1.5, r=2) with a 90° flange 50 mm
  // WIDE × 50 mm tall on the full 100 mm edge — entirely by clicking, no cut.
  const partId = await seedSketchPart(page, "Width-extent flange", 100, 100);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(1);

  await authorBaseFlange(page, "1.5", "2");
  await expect(page.getByTestId("feature-row")).toHaveCount(2);

  // Fold a PARTIAL flange off the right (100 mm) edge via the width extents.
  await page.getByTestId("new-edge-flange").click();
  await expect(page.getByTestId("edge-flange-editor")).toBeVisible();
  await pickSideEdge(page, "right");
  await expect(page.getByTestId("edge-flange-pick-count")).toHaveText(
    "1 edge picked",
  );

  // Choose the offset extent, 50 wide from the edge start (offset 0), 50 tall.
  await page.getByTestId("edge-flange-extent-offset").click();
  await page.getByTestId("edge-flange-width").fill("50");
  await page.getByTestId("edge-flange-offset").fill("0");
  await page.getByTestId("edge-flange-length").fill("50");
  // The auto bend-end relief note + the in-scene span preview are surfaced.
  await expect(page.getByTestId("edge-flange-relief-note")).toBeVisible();
  await expect(page.getByTestId("edge-flange-span-tag")).toBeVisible();

  // Founder frame of the editor-open state (span preview + relief note).
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.mouse.move(700, 450);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-width-extent-editor-1440.png`,
  });

  await page.getByTestId("edge-flange-submit").click();
  await expect(page.getByTestId("edge-flange-editor")).toBeHidden({
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-row")).toHaveCount(3);
  // The fold + auto bend-end relief add material + faces beyond the flat plate.
  await expect
    .poll(() => faceCount(page), { timeout: 30_000 })
    .toBeGreaterThan(6);

  // Founder frame of the authored body.
  await page.mouse.move(700, 450);
  await expect(page.getByTestId("viewport")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-width-extent-body-1440.png`,
  });

  // Flat pattern — the notched blank develops with one bend, no error.
  await openFlatPattern(page);
  const view = page.locator(
    '[data-testid="drawing-view"][data-view="flat_pattern"]',
  );
  await expect(view).toHaveAttribute("data-view-error", "false");
  // The notched blank outline carries more than a plain rectangle's 4 edges.
  expect(await view.locator("[data-edge]").count()).toBeGreaterThanOrEqual(5);
  await expect(page.getByTestId("drawing-bend-row")).toHaveCount(1);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-width-extent-flat-1440.png`,
  });
});

test.describe("small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the sheet-metal authoring flow keeps the viewport dominant", async ({
    page,
  }) => {
    const partId = await seedSketchPart(page, "L-bracket (laptop)", 50, 20);
    await page.goto(`/parts/${partId}`);
    await authorBaseFlange(page);

    await page.getByTestId("new-edge-flange").click();
    await expect(page.getByTestId("edge-flange-editor")).toBeVisible();
    await pickSideEdge(page, "right");
    await expect(page.getByTestId("edge-flange-pick-count")).toHaveText(
      "1 edge picked",
    );
    await page.mouse.move(700, 450);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sheet-metal-authoring-edge-pick-1280.png`,
    });

    // The viewport still owns the width — chrome recedes (design mandate #3).
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
  });
});
