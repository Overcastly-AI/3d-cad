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
 *       hemmed edge as a bend row. Asserted by SIZE, not by status: a closed
 *       hem's radius is 0.05 × gauge, so the hemmed plate stands 4.2 mm and the
 *       bend table reads R0.10 (HEM-1 — see `HEM_CLOSED_RADIUS_MM`).
 *   (b) a CLOSED HEM REFUSING an open-hem radius — the other half of that rule,
 *       with the recovery a user needs when they hit it.
 *   (c) a TRAY with a RELIEVED CORNER — a base flange + two PERPENDICULAR edge
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

/**
 * The bounding-box EXTENTS readout as [dx, dy, dz] in mm — the product's own
 * numbers, read the way a user reads them (the inspector row, not the wire).
 * The readout renders "Extents / 50 <times> 30 <times> 2 / mm"; the value line
 * is the one carrying the separator glyph.
 */
async function extentsMm(page: Page): Promise<number[]> {
  const line = (await page.getByTestId("prop-extents").innerText())
    .split("\n")
    .find((l) => l.includes("×"));
  const nums = (line?.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
  expect(nums, `extents readout was ${JSON.stringify(line)}`).toHaveLength(3);
  return nums;
}

/** The base flange's gauge (mm) — `authorBaseFlange` sets it; top-plate edges sit here. */
const GAUGE_MM = 2;

/**
 * The base flange's GENERAL bend radius (mm) — `authorBaseFlange` sets it. It
 * describes a free-standing die bend (what an edge flange IS), and a hem must
 * NOT inherit it: see `HEM_CLOSED_RADIUS_MM`.
 */
const PART_BEND_RADIUS_MM = 3;

/** The base flange's K-factor default. A hem DOES inherit K — it is a material
 *  property (where the neutral surface sits), unlike the radius. */
const K_FACTOR = 0.44;

/**
 * A CLOSED hem's inner bend radius = 0.05 x gauge (HEM-1). The rule the product
 * ships: a hem's radius is a function of its TYPE and the part's GAUGE, never of
 * the base flange's general radius. Restated here rather than imported because a
 * spec that computed its expectation from the code under test could not fail.
 *
 * The fold's cross-section puts the two layers exactly `2 * radius` apart, so on
 * this fixture (2 mm gauge, 3 mm part radius):
 *   correct   R 0.10 mm -> 0.20 mm air gap -> the hemmed plate stands 4.2 mm
 *   inherited R 3.00 mm -> 6.00 mm air gap -> it stood 10.0 mm  (the HEM-1 defect)
 * Both readings pass `eval-status = Solved`, which is why the assertions below
 * are on the NUMBERS and not on the status.
 */
const HEM_CLOSED_RADIUS_MM = 0.05 * GAUGE_MM;

/** Overall height of a hemmed plate: parent layer + air gap + returned layer. */
const HEMMED_HEIGHT_MM = GAUGE_MM + 2 * HEM_CLOSED_RADIUS_MM + GAUGE_MM;

/** A radius that describes an OPEN hem on this gauge — refused for a closed one
 *  (`hem_type_radius_conflict`). 1 mm is 0.5 x gauge, the open-hem ratio. */
const OPEN_HEM_RADIUS_MM = 1;

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
  await page.getByTestId("base-flange-thickness").fill(String(GAUGE_MM));
  await page
    .getByTestId("base-flange-bend-radius")
    .fill(String(PART_BEND_RADIUS_MM));
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

  // 2) A closed hem folded 180° back off the far (+x) edge. NO radius override:
  //    a closed hem's radius is 0.05 × gauge by the type rule, and taking the
  //    default is the only way this spec exercises that rule at all (an override
  //    would test the number the spec itself chose — this spec used to override
  //    to 1 mm, which is why the defect below sailed past it for weeks).
  await expect(page.getByTestId("new-hem")).toBeEnabled();
  await page.getByTestId("new-hem").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await expect(page.getByTestId("hem-pick-count")).toHaveText("No edge picked");
  // A closed hem folds flat back — the fold angle is fixed at 180° (stated, not a field).
  await expect(page.getByTestId("hem-fold-readout")).toHaveText(
    "180° (closed)",
  );
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

  // THE HEM IS CLOSED — asserted as a NUMBER, in the panel a user reads.
  // `Solved` was true throughout the HEM-1 defect and so was `faces > 6`; the
  // ONLY thing that told closed from three-gauges-of-air was the size of the
  // thing. The plate is 2 mm; hemmed it must stand gauge + gap + gauge = 4.2 mm,
  // and it stood 10.0 mm while the hem inherited the part's 3 mm bend radius.
  // Read via `expect.poll` because the inspector repaints from the same
  // evaluation `eval-status` reports — condition-based, never a sleep.
  await expect
    .poll(async () => (await extentsMm(page))[2], { timeout: 30_000 })
    .toBeCloseTo(HEMMED_HEIGHT_MM, 3);
  // …and in plan: the return folds BACK over the plate, so the blank's 30 mm
  // width is untouched and the length grows only by the fold's outer bulge,
  // radius + gauge = 2.1 mm. (Under the inherited radius this read 55.0.)
  const [dx, dy] = await extentsMm(page);
  expect(dy).toBeCloseTo(30, 3);
  expect(dx).toBeCloseTo(50 + HEM_CLOSED_RADIUS_MM + GAUGE_MM, 3);

  // Founder frame of the hemmed plate (desktop).
  await page.mouse.move(700, 450);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("viewport")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-hem-body-1440.png`,
  });

  // 3) Flat pattern — the hemmed edge develops as a bend row, and the SHOP gets
  //    the same number the solid has. The bend table is where a wrong radius
  //    would reach the press brake, so it is asserted cell by cell against the
  //    type rule rather than merely counted.
  await openFlatPattern(page);
  await expect(page.getByTestId("drawing-bend-table")).toBeVisible();
  const bendRows = page.getByTestId("drawing-bend-row");
  await expect(bendRows).toHaveCount(1);
  const cells = await bendRows.first().locator("text").allTextContents();
  expect(cells[1]).toBe("180.0°");
  // R0.10 — the closed-hem rule. It read R3.00 (the part's die-bend radius)
  // while the defect shipped, on the same green spec.
  expect(cells[2]).toBe(`R${HEM_CLOSED_RADIUS_MM.toFixed(2)}`);
  // Bend allowance π(R + K·t): K IS inherited from the base flange (a material
  // property), the radius is not — so this cell moves with both and pins the
  // distinction. 3.08 mm correct; 12.19 mm under the inherited radius.
  expect(cells[4]).toBe(
    (Math.PI * (HEM_CLOSED_RADIUS_MM + K_FACTOR * GAUGE_MM)).toFixed(2),
  );
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-hem-flat-1440.png`,
  });
});

test("a closed hem REFUSES an open-hem radius, names the fix, and the editor recovers", async ({
  page,
}) => {
  // The other half of HEM-1: `bend_radius_mm` is honoured, never inherited, and
  // REFUSED when it contradicts `hem_type`. 1 mm on 2 mm sheet is 0.5 × gauge —
  // an OPEN hem's radius — so a hem labelled "closed" cannot take it. Before the
  // fix this was silently accepted and built a 2 mm air gap under a "closed"
  // label; the spec above used to type exactly this number, which is why the
  // refusal needs a case of its own rather than being a hole where a test was.
  const partId = await seedSketchPart(page, "Hem refusal (clicked)", 50, 30);
  await page.goto(`/parts/${partId}`);
  await authorBaseFlange(page);

  await page.getByTestId("new-hem").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await page.getByTestId("hem-override-radius").click();
  await page.getByTestId("hem-bend-radius").fill(String(OPEN_HEM_RADIUS_MM));
  await pickTopEdge(page, "x", 1);
  await expect(page.getByTestId("hem-pick-count")).toHaveText("1 edge picked");
  await page.getByTestId("hem-length").fill("8");
  await page.getByTestId("hem-submit").click();
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });

  // The build stops, in the open, with the typed code and a message that names
  // the two ways out (retype the hem, or come under the ceiling).
  await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
    timeout: 30_000,
  });
  const failure = page.getByTestId("feature-error-2");
  // The code as the DOM holds it — the panel's `uppercase` is CSS, so asserting
  // the SCREAMING form would be asserting the stylesheet, not the payload.
  await expect(failure).toContainText("hem_type_radius_conflict");
  await expect(failure).toContainText("2 mm air gap on 2 mm sheet");
  await expect(failure).toContainText("hem_type='open'");
  await expect(failure).toContainText("at most 0.25 mm");
  // NOTHING half-built was fused: the body is still the bare 2 mm plate. A
  // refusal that left a mislabelled solid behind would be the defect wearing a
  // red badge, so the geometry is checked and not just the banner.
  const plate = await extentsMm(page);
  expect(plate[0]).toBeCloseTo(50, 3);
  expect(plate[1]).toBeCloseTo(30, 3);
  expect(plate[2]).toBeCloseTo(GAUGE_MM, 3);

  // NO DEAD END (design mandate): re-open the hem, drop the override, and the
  // part builds to the closed-hem rule — the same 4.2 mm the case above asserts.
  await page.getByTestId("feature-select-2").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await expect(page.getByTestId("hem-bend-radius")).toHaveValue(
    new RegExp(`^${OPEN_HEM_RADIUS_MM}(\\.0+)?$`),
  );
  await page.getByTestId("hem-override-radius").click();
  await expect(page.getByTestId("hem-bend-radius")).toHaveCount(0);
  await page.getByTestId("hem-submit").click();
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  await expect
    .poll(async () => (await extentsMm(page))[2], { timeout: 30_000 })
    .toBeCloseTo(HEMMED_HEIGHT_MM, 3);
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
  // The references are the risky guess (the seeds are just tree order), so
  // keyboard focus opens on Bend A — not the safe-defaulted ratio.
  await expect(page.getByTestId("corner-relief-bend-a")).toBeFocused();
  // The two selects are pre-seeded with the two edge flanges, in tree order.
  const bendA = page.getByTestId("corner-relief-bend-a");
  const bendB = page.getByTestId("corner-relief-bend-b");
  await expect(bendA).toHaveValue(/.+/);
  await expect(bendB).toHaveValue(/.+/);
  // The selection is highlighted IN-SCENE: each picked flange's bend line is
  // drawn brass and tagged at its mid-span, so "Edge flange1 / Edge flange2"
  // map to physical corners (SM-relief-ui-1).
  await expect(page.getByTestId("corner-relief-bend-tag-a")).toBeVisible();
  await expect(page.getByTestId("corner-relief-bend-tag-b")).toBeVisible();
  await expect(page.getByTestId("corner-relief-bend-tag-a")).toHaveText(
    "Bend A",
  );

  // Founder frame of the OPEN editor with both bends tagged in the viewport
  // (the editor-open evidence the 2026-07-19 UI review flagged as missing).
  await page.mouse.move(700, 450);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-corner-relief-editor-1440.png`,
  });

  // Changing a bend re-targets the highlight: picking the SAME flange for both
  // collapses the tags into one "A · B" callout (plus the same-bend error) —
  // the scene always mirrors the current selection.
  const bendAValue = await bendA.inputValue();
  const bendBValue = await bendB.inputValue();
  await bendA.selectOption(bendBValue);
  await expect(page.getByTestId("corner-relief-bend-tag-ab")).toBeVisible();
  await expect(page.getByTestId("corner-relief-bend-tag-a")).toHaveCount(0);
  await expect(
    page.getByText("Pick two different edge flanges", { exact: false }),
  ).toBeVisible();
  await bendA.selectOption(bendAValue);
  await expect(page.getByTestId("corner-relief-bend-tag-a")).toBeVisible();
  await expect(page.getByTestId("corner-relief-bend-tag-b")).toBeVisible();

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

  // EDIT-MODE GUARD: roll back past the second flange so the relief's stored
  // Bend B ref no longer resolves. Re-opening the editor must show an explicit
  // guard — never silently display the wrong flange — and submit stays off.
  await page.getByTestId("rollback-slot-2").click();
  await expect(page.getByTestId("feature-row").nth(3)).toHaveAttribute(
    "data-rolled-back",
    "true",
    { timeout: 30_000 },
  );
  await page.getByTestId("feature-select-4").click();
  await expect(page.getByTestId("corner-relief-editor")).toBeVisible();
  await expect(bendB.locator("option:checked")).toHaveText(
    "Missing edge flange",
  );
  await expect(
    page.getByText("This bend no longer exists. Pick an edge flange."),
  ).toBeVisible();
  await expect(page.getByTestId("corner-relief-submit")).toBeDisabled();
  // The still-live Bend A keeps its in-scene tag; the stale ref draws nothing
  // (the guard owns that state — the scene never guesses a bend).
  await expect(page.getByTestId("corner-relief-bend-tag-a")).toBeVisible();
  await expect(page.getByTestId("corner-relief-bend-tag-b")).toHaveCount(0);
  await page.getByTestId("corner-relief-cancel").click();
  await expect(page.getByTestId("corner-relief-editor")).toBeHidden();
  // Roll forward to the tip so the flat pattern develops the full tray.
  await page.getByTestId("rollback-slot-4").click();
  await expect(page.getByTestId("feature-row").nth(4)).not.toHaveAttribute(
    "data-rolled-back",
    "true",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
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
