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
 *   (b1) the RADIUS THE EDITOR SUGGESTS being one the evaluator accepts — the
 *       hint used to name 0.5 × gauge (the OPEN ratio) for a closed hem, so the
 *       product walked the user into (b)'s refusal and then repeated the advice
 *       in the edit form (HEM-1C). The number is read off the rendered card and
 *       typed back in, so the case cannot pass by agreeing with itself.
 *   (b2) an OPEN HEM authored by clicking (HEM-1D) — `hem_type` was hardcoded
 *       `closed`, so the shape the API ships was unreachable. Asserted by the
 *       gap it leaves (1 × gauge), not by a 2xx.
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

/**
 * Seed a part whose only feature is a rectangular profile sketch, keeping the
 * session token — the HEM-1B case needs it to make an UNRELATED edit through
 * the API (the sketcher is exercised elsewhere; here it is only the cause).
 */
async function seedSketchPartWithToken(
  page: Page,
  name: string,
  width: number,
  height: number,
): Promise<{ partId: string; token: string }> {
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
  return { partId: part.id, token: account.token };
}

/** Seed a part whose only feature is a rectangular profile sketch. */
async function seedSketchPart(
  page: Page,
  name: string,
  width: number,
  height: number,
): Promise<string> {
  return (await seedSketchPartWithToken(page, name, width, height)).partId;
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

/** Overall height of a plate hemmed at `radiusMm`: layer + air gap (2R) + layer. */
function hemmedHeightMm(radiusMm: number): number {
  return GAUGE_MM + 2 * radiusMm + GAUGE_MM;
}

/** Overall height of a plate with the DEFAULT closed hem. */
const HEMMED_HEIGHT_MM = hemmedHeightMm(HEM_CLOSED_RADIUS_MM);

/** A radius that describes an OPEN hem on this gauge — refused for a closed one
 *  (`hem_type_radius_conflict`). 1 mm is 0.5 x gauge, the open-hem ratio. */
const OPEN_HEM_RADIUS_MM = 1;

/**
 * The closed/open BOUNDARY on this gauge: 0.125 x 2 mm. A closed hem is refused
 * a radius above it, an open hem one below it, and it belongs to both. Restated
 * here rather than imported for the same reason as `HEM_CLOSED_RADIUS_MM`: a
 * band computed from the code under test could not fail.
 */
const HEM_BOUNDARY_RADIUS_MM = 0.25;

/** Every number in a string, as numbers — the reading a user does off the card. */
function numbersIn(text: string): number[] {
  return (text.match(/\d+(?:\.\d+)?/g) ?? []).map(Number);
}

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

test("repairing an orphaned hem never meets a silent disabled Save (HEM-1B)", async ({
  page,
}) => {
  // The audit's sequence, driven end to end (`docs/AUDIT-PRODUCT.md` S-26): an
  // UNRELATED edit widens the blank, the hem's stored edge no longer resolves,
  // and the user goes to repair it. What they met was `hem-submit` with
  // `aria-disabled="true"` and an EMPTY `title` — no message, no red field —
  // which is indistinguishable from a dead end. Two things are asserted here:
  // the form re-opens as it was AUTHORED (overrides off, Save live), and every
  // state that DOES gate Save puts a sentence on screen where the user is
  // looking. The second is asserted as READABLE INK — a box with area, hit-
  // testing to the Save cell — never as an attribute's presence, because an
  // attribute is exactly what the audit found carrying nothing.
  const { partId, token } = await seedSketchPartWithToken(
    page,
    "Hem repair (clicked)",
    50,
    30,
  );
  const headers = { Authorization: `Bearer ${token}` };
  await page.goto(`/parts/${partId}`);
  await authorBaseFlange(page);

  // A hem with NO overrides — exactly what the audit authored.
  await page.getByTestId("new-hem").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await pickTopEdge(page, "x", 1);
  await page.getByTestId("hem-length").fill("8");
  await page.getByTestId("hem-submit").click();
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });

  // THE UNRELATED EDIT: the blank grows 50 → 60 mm. The hemmed edge moves, so
  // the hem's stored signature stops resolving and the feature fails.
  const listed = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers,
  });
  const tree = await listed.json();
  const sketchRow = tree.features[0];
  const widened = await page.request.patch(
    `/api/v1/parts/${partId}/features/${sketchRow.id}`,
    {
      data: {
        feature: (rectangleSketch(60, 30) as { feature: unknown }).feature,
        expected_tree_version: tree.tree_version,
      },
      headers,
    },
  );
  expect(widened.ok(), await widened.text()).toBe(true);
  await page.reload();
  await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
    timeout: 60_000,
  });
  // The code as the DOM holds it — the panel's `uppercase` is CSS.
  await expect(page.getByTestId("feature-error-2")).toContainText(
    "subshape_unresolved",
  );

  // 1) THE FORM RE-OPENS AS IT WAS AUTHORED. The audit found "Override
  //    K-factor" CHECKED with an empty value — an override never authored —
  //    which is what silently invalidated the form.
  await page.getByTestId("feature-select-2").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await expect(page.getByTestId("hem-override-k")).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await expect(page.getByTestId("hem-k-factor")).toHaveCount(0);
  await expect(page.getByTestId("hem-override-radius")).toHaveAttribute(
    "aria-checked",
    "false",
  );
  const submit = page.getByTestId("hem-submit");
  await expect(submit).toBeEnabled();

  // 2) TICKING AN OVERRIDE SEEDS IT. "Checked with no value" is not a state a
  //    click can produce any more: the field opens on the inherited K the card
  //    names one line above it, and Save stays live.
  await page.getByTestId("hem-override-k").click();
  await expect(page.getByTestId("hem-k-factor")).toHaveValue(String(K_FACTOR));
  await expect(submit).toBeEnabled();

  // 3) A GATED SAVE SAYS WHY, IN INK — AT THE 1280x800 FLOOR. The width is set
  //    BEFORE the measurement on purpose: a sentence that only fits on a big
  //    monitor is not an explanation, and the card's action row is exactly what
  //    a short frame clips first.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByTestId("hem-k-factor").fill("");
  await expect(submit).toBeDisabled();
  const reason = submit.locator("[data-disabled-reason]");
  await expect(
    reason,
    "a gated Save with nothing to read IS the HEM-1B defect",
  ).toHaveCount(1);
  const said = (await reason.innerText()).trim();
  expect(said).toContain("K-factor");
  expect(said).toContain("uncheck");
  // Ink, not markup: a box with real area, whose centre hit-tests INSIDE the
  // Save cell. `toBeVisible()` would pass on a 1x1 node clipped out of frame,
  // and `textContent` would pass on a `display:none` one.
  const box = await reason.boundingBox();
  expect(box, "the reason has no box at all").not.toBe(null);
  expect(box!.width).toBeGreaterThan(60);
  expect(box!.height).toBeGreaterThan(8);
  const hit = await page.evaluate(
    ([x, y]) =>
      document
        .elementFromPoint(x as number, y as number)
        ?.closest("[data-testid]")
        ?.getAttribute("data-testid") ?? null,
    [box!.x + box!.width / 2, box!.y + box!.height / 2],
  );
  expect(hit, "the reason is covered by something else").toBe("hem-submit");
  // …and a screen reader is told the same sentence, not a different one.
  const describedBy = await submit.getAttribute("aria-describedby");
  expect(describedBy).not.toBe(null);
  expect((await page.locator(`#${describedBy}`).innerText()).trim()).toBe(said);
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/hem-blocked-save-after-1280.png`,
  });

  // 4) THE WAY OUT THE SENTENCE NAMES WORKS, and the repair completes: drop the
  //    override, re-pick the edge that is there now, save, and the part builds.
  //    A real mouse click on the Save cell's centre, not a synthetic dispatch —
  //    the claim is that a USER can finish this.
  await page.getByTestId("hem-override-k").click();
  await expect(submit).toBeEnabled();
  await pickTopEdge(page, "x", 1);
  await expect(page.getByTestId("hem-pick-count")).toHaveText("1 edge picked");
  const saveBox = await submit.boundingBox();
  expect(saveBox).not.toBe(null);
  await page.mouse.click(
    saveBox!.x + saveBox!.width / 2,
    saveBox!.y + saveBox!.height / 2,
  );
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  // The repaired hem is still a CLOSED hem on the widened blank: 60 mm of plate
  // plus the fold's outer bulge, and the same 4.2 mm stand.
  const [dx, , dz] = await extentsMm(page);
  expect(dz).toBeCloseTo(HEMMED_HEIGHT_MM, 3);
  expect(dx).toBeCloseTo(60 + HEM_CLOSED_RADIUS_MM + GAUGE_MM, 3);
});

test("the radius the hem editor suggests is one the evaluator accepts", async ({
  page,
}) => {
  // HEM-1C. The card used to advise `≈0.5 × gauge` for a CLOSED hem — the OPEN
  // ratio, and the exact value the case above proves is refused — so following
  // the product's own guidance produced `hem_type_radius_conflict`, and the hint
  // persisted into the EDIT form afterwards: the only advice on screen was the
  // advice that had just failed. This types the card's OWN number back in, so it
  // cannot pass by agreeing with itself.
  const partId = await seedSketchPart(page, "Hem hint (clicked)", 50, 30);
  await page.goto(`/parts/${partId}`);
  await authorBaseFlange(page);

  await page.getByTestId("new-hem").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();

  // With no override, the card states where the radius COMES from. It must not
  // claim the base flange (a hem does not inherit it — HEM-1) and must name the
  // derived value, so the number is legible before anything is typed.
  const derived = page.getByTestId("hem-override-radius");
  await expect(derived).not.toContainText("base flange");
  await expect(derived).toContainText(`${HEM_CLOSED_RADIUS_MM} mm`);
  // The gap is what that radius MEANS — the reading a feeler gauge would give.
  await expect(page.getByTestId("hem-gap-readout")).toHaveText(
    `${2 * HEM_CLOSED_RADIUS_MM} mm (0.1 × gauge)`,
  );

  // Turn the override on and read the guidance the user reads.
  await page.getByTestId("hem-override-radius").click();
  const hint = (await derived.innerText()).replace(
    /^Override bend radius\n/,
    "",
  );
  const suggested = numbersIn(hint);
  expect(suggested.length, `guidance named no number: ${hint}`).toBeGreaterThan(
    0,
  );
  // EVERY number the card offers must be one a closed hem can take. Before the
  // fix this line reported 1 — 0.5 × gauge, four times the ceiling.
  for (const value of suggested) {
    expect(
      value,
      `the card offers ${value} mm, which a closed hem is refused for`,
    ).toBeLessThanOrEqual(HEM_BOUNDARY_RADIUS_MM);
    expect(value).toBeGreaterThan(0);
  }

  // Type the first number the card named, and build it.
  const typed = suggested[0] as number;
  await page.getByTestId("hem-bend-radius").fill(String(typed));
  // Nothing objects to the card's own suggestion (the advisory note is for a
  // radius that contradicts the type — see the next case).
  await expect(page.getByTestId("hem-radius-conflict")).toHaveCount(0);
  await pickTopEdge(page, "x", 1);
  await expect(page.getByTestId("hem-pick-count")).toHaveText("1 edge picked");
  await page.getByTestId("hem-length").fill("8");

  // Founder frame: the card as the user reads it while typing the radius.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.mouse.move(700, 450);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-hem-radius-1280.png`,
  });

  await page.getByTestId("hem-submit").click();
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });
  // It SOLVES. This is the assertion the defect fails: the suggested 1 mm came
  // back `Failed` with `hem_type_radius_conflict`.
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  // …and it builds the hem the number describes — the gap is exactly 2 × R.
  await expect
    .poll(async () => (await extentsMm(page))[2], { timeout: 30_000 })
    .toBeCloseTo(hemmedHeightMm(typed), 3);
});

test("an OPEN hem is authorable by clicking, and leaves one gauge of air", async ({
  page,
}) => {
  // HEM-1D. `buildHemParams` hardcoded `hem_type: "closed"` and the card had no
  // type control, so the open hem HEM-1 shipped on the API could not be reached
  // by clicking at all — and an open hem is the only route to the wide gap the
  // old default was silently producing.
  const partId = await seedSketchPart(page, "Open hem (clicked)", 50, 30);
  await page.goto(`/parts/${partId}`);
  await authorBaseFlange(page);

  await page.getByTestId("new-hem").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await expect(page.getByTestId("hem-fold-readout")).toHaveText(
    "180° (closed)",
  );

  // A user who wants the opening reaches it in one click, and the card says what
  // they will get BEFORE the rebuild.
  await page.getByTestId("hem-type-open").click();
  await expect(page.getByTestId("hem-type-open")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByTestId("hem-fold-readout")).toHaveText("180° (open)");
  await expect(page.getByTestId("hem-gap-readout")).toHaveText(
    `${2 * OPEN_HEM_RADIUS_MM} mm (1 × gauge)`,
  );

  await pickTopEdge(page, "x", 1);
  await expect(page.getByTestId("hem-pick-count")).toHaveText("1 edge picked");
  await page.getByTestId("hem-length").fill("8");
  await page.getByTestId("hem-submit").click();
  await expect(page.getByTestId("hem-editor")).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });

  // ASSERTED ON THE BUILT BODY, not on a 2xx. A params model is pydantic-default
  // `extra="ignore"`, so a misspelled `hem_type` would validate, evaluate and
  // quietly give the CLOSED reading — which stands 4.2 mm, not 6.0. Two
  // independent readings, because the radius moves both: the plate must stand
  // gauge + 1 gauge of air + gauge, and grow in plan by radius + gauge.
  await expect
    .poll(async () => (await extentsMm(page))[2], { timeout: 30_000 })
    .toBeCloseTo(hemmedHeightMm(OPEN_HEM_RADIUS_MM), 3);
  const [dx, dy] = await extentsMm(page);
  expect(dy).toBeCloseTo(30, 3);
  expect(dx).toBeCloseTo(50 + OPEN_HEM_RADIUS_MM + GAUGE_MM, 3);

  // The type PERSISTED: re-opening the feature seeds the form from the stored
  // params, so a hem that merely built wide would show as closed here.
  await page.getByTestId("feature-select-2").click();
  await expect(page.getByTestId("hem-editor")).toBeVisible();
  await expect(page.getByTestId("hem-type-open")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByTestId("hem-fold-readout")).toHaveText("180° (open)");

  // NO DEAD END: the radius that the closed hem refuses is legal HERE, and the
  // card says so — the same 1 mm, now with the type that means it.
  await page.getByTestId("hem-override-radius").click();
  await page.getByTestId("hem-bend-radius").fill(String(OPEN_HEM_RADIUS_MM));
  await expect(page.getByTestId("hem-radius-conflict")).toHaveCount(0);
  // …and switching back to closed states the refusal BEFORE the rebuild, naming
  // the way out, instead of spending a rebuild to discover it.
  await page.getByTestId("hem-type-closed").click();
  const conflict = page.getByTestId("hem-radius-conflict");
  await expect(conflict).toContainText(`${2 * OPEN_HEM_RADIUS_MM} mm gap`);
  await expect(conflict).toContainText("Switch the type to Open");
  await expect(conflict).toContainText(`at most ${HEM_BOUNDARY_RADIUS_MM} mm`);
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
