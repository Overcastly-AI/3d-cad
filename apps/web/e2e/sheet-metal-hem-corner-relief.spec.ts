import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Sheet-metal AUTHORING UI, batch 2 — CLOSED HEM + CORNER RELIEF made
 * click-through. Both features shipped backend-first (API only); this drives
 * the whole loop through a real browser against the real stack (gateway +
 * documents + geometry, no mocks):
 *
 *   (a) a PLATE with a CLOSED HEM — a base flange, then a hem folded 180° back
 *       off a picked edge; the body renders + the flat pattern develops the
 *       hemmed edge as a bend row.
 *   (b) a TRAY with a RELIEVED CORNER — a base flange + two PERPENDICULAR edge
 *       flanges (adjacent edges meeting at a corner), then a corner relief that
 *       references those two edge-flange FEATURES; the notch appears in the body
 *       and the flat pattern.
 *
 * Only the rectangular profile is seeded via the API (the sketcher is tested
 * elsewhere); every sheet-metal feature is authored through its editor by
 * clicking.
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

/** The base flange's gauge (mm) — `authorBaseFlange` sets it; top-plate edges sit here. */
const GAUGE_MM = 2;

/**
 * Click the TOP-PLATE edge whose mid-span is extreme along `axis` (x or y) — the
 * straight plate-face edge to fold off. Restricted to edges whose mid-span sits
 * on the top plate (z ≈ gauge): once a flange is folded UP, its raised edges (high
 * z) must NOT win the pick, so we filter to the plate face first, then take the
 * extreme along the axis. Read from the accessible name (mid-span x, y, z), so the
 * pick is deterministic. `dir` +1 picks the max side, −1 the min.
 */
async function pickTopEdge(
  page: Page,
  axis: "x" | "y",
  dir: 1 | -1,
): Promise<void> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestScore = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = (label.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
    // aria-label: "Edge N, line, centred at X, Y, Z millimetres".
    const [, x, y, z] = nums;
    if (x === undefined || y === undefined || z === undefined) continue;
    // Only the top plate face (z ≈ gauge) — never a raised flange edge.
    if (Math.abs(z - GAUGE_MM) > 0.6) continue;
    const along = axis === "x" ? x : y;
    const score = dir * along;
    if (score > bestScore) {
      bestScore = score;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Author the base flange from the seeded sketch by clicking its editor. */
async function authorBaseFlange(page: Page): Promise<void> {
  await expect(page.getByTestId("new-base-flange")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-base-flange").click();
  await expect(page.getByTestId("base-flange-editor")).toBeVisible();
  await page.getByTestId("base-flange-thickness").fill("2");
  await page.getByTestId("base-flange-bend-radius").fill("3");
  await page.getByTestId("base-flange-submit").click();
  await expect(page.getByTestId("base-flange-editor")).toBeHidden();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect.poll(() => faceCount(page), { timeout: 30_000 }).toBe(6);
}

/** Author one edge flange by picking an edge extreme along an axis + a leg length. */
async function authorEdgeFlange(
  page: Page,
  axis: "x" | "y",
  dir: 1 | -1,
  lengthMm: number,
): Promise<void> {
  await page.getByTestId("new-edge-flange").click();
  await expect(page.getByTestId("edge-flange-editor")).toBeVisible();
  await pickTopEdge(page, axis, dir);
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
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
  const view = page.locator(
    '[data-testid="drawing-view"][data-view="flat_pattern"]',
  );
  await expect(view).toHaveAttribute("data-view-error", "false");
  expect(await view.locator("line, polyline").count()).toBeGreaterThan(0);
}

test("model a plate with a closed hem by clicking: base flange → hem → flat pattern", async ({
  page,
}) => {
  const partId = await seedSketchPart(page, "Hemmed plate (clicked)", 50, 30);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(1);

  // 1) Base flange from the sketch.
  await authorBaseFlange(page);
  await expect(page.getByTestId("feature-row")).toHaveCount(2);

  // 2) A closed hem folded 180° back off the far (+x) edge.
  await expect(page.getByTestId("new-hem")).toBeEnabled();
  await page.getByTestId("new-hem").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await expect(page.getByTestId("hem-pick-count")).toHaveText("No edge picked");
  // A closed hem folds flat back — the fold angle is fixed at 180° (stated, not a field).
  await expect(page.getByTestId("hem-fold-readout")).toHaveText(
    "180° (closed)",
  );
  // A tight hem needs a small radius (a 2 mm gauge, 3 mm base radius would gap
  // wide); override to ~1 mm so the layers close.
  await page.getByTestId("hem-override-radius").click();
  await page.getByTestId("hem-bend-radius").fill("1");
  await pickTopEdge(page, "x", 1);
  await expect(page.getByTestId("hem-pick-count")).toHaveText("1 edge picked");
  await page.getByTestId("hem-length").fill("8");
  await page.getByTestId("hem-submit").click();
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-row")).toHaveCount(3);
  await expect(page.getByTestId("feature-row").nth(2)).toContainText("hem");

  // The fold adds material + faces beyond the flat plate's six.
  await expect
    .poll(() => faceCount(page), { timeout: 30_000 })
    .toBeGreaterThan(6);
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // Founder frame of the hemmed plate (desktop).
  await page.mouse.move(700, 450);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("viewport")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-hem-body-1440.png`,
  });

  // 3) Flat pattern — the hemmed edge develops as a bend row.
  await openFlatPattern(page);
  await expect(page.getByTestId("drawing-bend-table")).toBeVisible();
  await expect(page.getByTestId("drawing-bend-row")).toHaveCount(1);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-hem-flat-1440.png`,
  });
});

test("model a tray with a relieved corner by clicking: two edge flanges → corner relief", async ({
  page,
}) => {
  // Mirrors the geometry golden `corner-tray-relieved-unfold`: a 40×30 blank,
  // a 20 mm flange off the +x edge, a 25 mm flange off the +y edge, then a
  // 1.5 × gauge corner relief — the known-good relieved tray that unfolds flat.
  const partId = await seedSketchPart(page, "Relieved tray (clicked)", 40, 30);
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(1);

  await authorBaseFlange(page);
  // Two PERPENDICULAR edge flanges — the +x edge and the +y edge — whose bends
  // meet at the +x/+y corner (a real tray corner needing relief).
  await authorEdgeFlange(page, "x", 1, 20);
  await authorEdgeFlange(page, "y", 1, 25);
  await expect(page.getByTestId("feature-row")).toHaveCount(4);

  // Corner relief references the two edge-flange FEATURES (not an edge pick).
  await expect(page.getByTestId("new-corner-relief")).toBeEnabled();
  await page.getByTestId("new-corner-relief").click();
  await expect(page.getByTestId("corner-relief-editor")).toBeVisible();
  // The two selects are pre-seeded with the two edge flanges, in tree order.
  await expect(page.getByTestId("corner-relief-bend-a")).toHaveValue(/.+/);
  await expect(page.getByTestId("corner-relief-bend-b")).toHaveValue(/.+/);
  // The ratio-sized notch is previewed from the part gauge (ratio × 2 mm).
  await expect(page.getByTestId("corner-relief-size-preview")).toContainText(
    "mm",
  );
  // Size the notch to 1.5 × gauge = 3 mm so it clears the 3 mm bend arc (the
  // manufacturing floor size ≥ bend radius — the notch develops cleanly flat).
  await page.getByTestId("corner-relief-ratio").fill("1.5");
  await expect(page.getByTestId("corner-relief-size-preview")).toContainText(
    "3 mm",
  );
  await page.getByTestId("corner-relief-submit").click();
  await expect(page.getByTestId("corner-relief-editor")).toBeHidden({
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-row")).toHaveCount(5);
  await expect(page.getByTestId("feature-row").nth(4)).toContainText(
    "corner relief",
  );
  // The relieved body still renders richly (studio-shaded, not a blank frame).
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // Founder frame of the relieved tray (desktop).
  await page.mouse.move(700, 450);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("viewport")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-corner-relief-body-1440.png`,
  });

  // The relief develops into the flat pattern — a two-bend blank with the notch.
  await openFlatPattern(page);
  await expect(page.getByTestId("drawing-bend-row")).toHaveCount(2);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-corner-relief-flat-1440.png`,
  });
});

test.describe("small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the hem + corner-relief editors keep the viewport dominant", async ({
    page,
  }) => {
    const partId = await seedSketchPart(page, "Hem (laptop)", 50, 30);
    await page.goto(`/parts/${partId}`);
    await authorBaseFlange(page);

    await page.getByTestId("new-hem").click();
    await expect(page.getByTestId("hem-editor")).toBeVisible();
    await pickTopEdge(page, "x", 1);
    await expect(page.getByTestId("hem-pick-count")).toHaveText(
      "1 edge picked",
    );
    await page.mouse.move(700, 450);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sheet-metal-hem-edit-1280.png`,
    });

    // The viewport still owns the width — chrome recedes (design mandate #3).
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);
  });
});
