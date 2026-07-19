import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Sheet-metal v1 slice #4 — the visible payoff: model a bracket, see the flat
 * blank a shop can cut. Driven end to end through a real browser against the
 * real stack (gateway + documents + geometry, no mocks): a sheet-metal part
 * (base flange + edge flange(s)) is built via the API, a drawing is created
 * through the register UI, and its FLAT PATTERN is unfolded onto a lone-view
 * sheet. The unfold arrives from `/geometry/drawing/evaluate` (no HLR — a flat
 * blank is already 2D) and renders as scale-correct SVG: the cut outline solid,
 * the fold lines as a distinct dashed-blue stroke (`edge_role="bend"`), and the
 * bend table placed at its server anchor. Rows key POSITIONALLY to fold lines
 * (sheet-metal.md §6): the i-th `drawing-bend-row` ↔ the i-th `data-edge-role="bend"`
 * edge. Founder frames at desktop + small-laptop widths.
 */

interface EdgeFlangeSpec {
  /** Fixed sketch x of the base-flange edge to fold off (0 or the width). */
  x: number;
  /** Base-flange height (the folded edge's length along y). */
  height: number;
  flangeLengthMm: number;
}

/**
 * Build a sheet-metal bracket via the real gateway: a rectangular base flange
 * thickened to gauge, plus N edge flanges folded off its straight side edges.
 * The edge signatures are the fixed geometric invariants of the rectangle at
 * gauge z (top face at z = thickness), the same ones the geometry goldens use —
 * only the base-flange feature id is server-assigned and threaded through.
 */
async function createSheetMetalPartViaApi(
  page: Page,
  token: string,
  name: string,
  opts: { width: number; height: number; flanges: EdgeFlangeSpec[] },
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const thickness = 2.0;
  const { width, height, flanges } = opts;

  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  if (!part.ok()) {
    throw new Error(
      `create part failed: ${part.status()} ${await part.text()}`,
    );
  }
  const partId = ((await part.json()) as { id: string }).id;

  // A closed rectangle profile (width × height) on the XY datum.
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
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
    },
    headers: auth,
  });
  if (!sketch.ok()) {
    throw new Error(`sketch failed: ${sketch.status()} ${await sketch.text()}`);
  }
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };

  // The base flange — the sheet's first body, carrying the part's gauge / K /
  // default bend radius (sheet-metal.md §4.1).
  const base = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Base flange",
      feature: {
        type: "sheet_metal_base_flange",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          thickness_mm: thickness,
          bend_radius_mm: 3.0,
          k_factor: 0.44,
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!base.ok()) {
    throw new Error(
      `base flange failed: ${base.status()} ${await base.text()}`,
    );
  }
  const baseBody = (await base.json()) as {
    feature: { id: string };
    tree_version: number;
  };

  let treeVersion = baseBody.tree_version;
  for (const [i, flange] of flanges.entries()) {
    const z = thickness;
    const flangeRes = await page.request.post(
      `/api/v1/parts/${partId}/features`,
      {
        data: {
          name: `Edge flange ${i + 1}`,
          feature: {
            type: "sheet_metal_edge_flange",
            version: 1,
            params: {
              edge: {
                kind: "subshape",
                feature_id: baseBody.feature.id,
                subshape_type: "edge",
                selector: {
                  selector_version: 1,
                  signature: {
                    subshape_type: "edge",
                    curve: "line",
                    end_a: { x: flange.x, y: 0, z },
                    end_b: { x: flange.x, y: flange.height, z },
                    midpoint: { x: flange.x, y: flange.height / 2, z },
                    length_mm: flange.height,
                  },
                },
              },
              flange_length_mm: flange.flangeLengthMm,
              bend_angle_deg: 90.0,
            },
          },
          expected_tree_version: treeVersion,
        },
        headers: auth,
      },
    );
    if (!flangeRes.ok()) {
      throw new Error(
        `edge flange ${i + 1} failed: ${flangeRes.status()} ${await flangeRes.text()}`,
      );
    }
    treeVersion = ((await flangeRes.json()) as { tree_version: number })
      .tree_version;
  }

  return { id: partId };
}

/** Settle the chrome for a clean founder frame: drop focus off the just-clicked
 * tool (so its caption flyout hides) and park the pointer over empty paper. */
async function settleForShot(page: Page): Promise<void> {
  await page.evaluate(() =>
    (document.activeElement as HTMLElement | null)?.blur(),
  );
  await page.mouse.move(700, 450);
}

/** Create a drawing through the register UI and open its editor. */
async function openNewDrawing(page: Page, name: string): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill(name);
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
}

test("unfold an L-bracket's flat pattern with its bend table", async ({
  page,
}) => {
  const account = await seedSession(page);
  const part = await createSheetMetalPartViaApi(
    page,
    account.token,
    "L-bracket 50×20",
    {
      width: 50,
      height: 20,
      flanges: [{ x: 50, height: 20, flangeLengthMm: 30 }],
    },
  );

  await openNewDrawing(page, "L-bracket — flat pattern");
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  await page.getByTestId("drawing-flat-pattern").click();

  // The sheet renders once the unfold composes.
  const sheet = page.getByTestId("drawing-sheet");
  await expect(sheet).toBeVisible({ timeout: 30_000 });

  // The lone flat-pattern view is placed and carries geometry (not a failure).
  const view = page.locator(
    '[data-testid="drawing-view"][data-view="flat_pattern"]',
  );
  await expect(view).toHaveAttribute("data-view-error", "false");
  expect(await view.locator("line, polyline").count()).toBeGreaterThan(0);

  // Cut outline (body edges) AND at least one fold line (bend edge) are drawn.
  const bendEdges = view.locator('[data-edge-role="bend"]');
  expect(await bendEdges.count()).toBeGreaterThanOrEqual(1);
  expect(await view.locator('[data-edge-role="body"]').count()).toBeGreaterThan(
    0,
  );

  // The bend table renders with one row per bend (an L-bracket has one bend).
  await expect(page.getByTestId("drawing-bend-table")).toBeVisible();
  const rows = page.getByTestId("drawing-bend-row");
  await expect(rows).toHaveCount(1);
  // Positional correlation (sheet-metal.md §6): the i-th row ↔ the i-th fold
  // line — both carry the same `data-bend-index`.
  await expect(rows.first()).toHaveAttribute("data-bend-index", "0");
  await expect(bendEdges.first()).toHaveAttribute("data-bend-index", "0");

  // The text-accessible bend schedule (a11y twin of the SVG table, which lives
  // inside a role="img" sheet AT can't read): one row per bend, keyed to the
  // fold line by the SAME positional `data-bend-index`.
  await expect(page.getByTestId("bend-schedule-panel")).toBeVisible();
  const scheduleRows = page.getByTestId("bend-schedule-row");
  await expect(scheduleRows).toHaveCount(1);
  await expect(scheduleRows.first()).toHaveAttribute("data-bend-index", "0");

  // Founder frames — desktop + small-laptop widths.
  await settleForShot(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-flat-pattern-l-1440.png`,
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-flat-pattern-l-1280.png`,
  });
});

test("unfold a U-channel's flat pattern (two fold lines + two-row bend table)", async ({
  page,
}) => {
  const account = await seedSession(page);
  const part = await createSheetMetalPartViaApi(
    page,
    account.token,
    "U-channel 40×20",
    {
      width: 40,
      height: 20,
      flanges: [
        { x: 40, height: 20, flangeLengthMm: 30 },
        { x: 0, height: 20, flangeLengthMm: 25 },
      ],
    },
  );

  await openNewDrawing(page, "U-channel — flat pattern");
  await page.getByTestId("drawing-part-select").selectOption(part.id);
  await page.getByTestId("drawing-flat-pattern").click();

  const sheet = page.getByTestId("drawing-sheet");
  await expect(sheet).toBeVisible({ timeout: 30_000 });

  const view = page.locator(
    '[data-testid="drawing-view"][data-view="flat_pattern"]',
  );
  await expect(view).toHaveAttribute("data-view-error", "false");

  // Two bends → two fold lines and a two-row bend table.
  const bendEdges = view.locator('[data-edge-role="bend"]');
  expect(await bendEdges.count()).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId("drawing-bend-table")).toBeVisible();
  await expect(page.getByTestId("drawing-bend-row")).toHaveCount(2);

  // The text-accessible bend schedule carries both fold rows for AT / keyboard.
  await expect(page.getByTestId("bend-schedule-panel")).toBeVisible();
  await expect(page.getByTestId("bend-schedule-row")).toHaveCount(2);

  await settleForShot(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-flat-pattern-u-1440.png`,
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sheet-metal-flat-pattern-u-1280.png`,
  });
});

/**
 * The honest failure path (sheet-metal.md §7): a plain solid (no sheet-metal
 * bends) asked for a flat pattern composes a typed `flat_pattern_not_sheet_metal`
 * failed view — rendered as an inline error state, never a crash or a blank.
 */
test("a non-sheet-metal part shows an honest flat-pattern error", async ({
  page,
}) => {
  const account = await seedSession(page);
  const auth = { Authorization: `Bearer ${account.token}` };
  const part = await page.request.post("/api/v1/parts", {
    data: { name: "Plain block" },
    headers: auth,
  });
  const partId = ((await part.json()) as { id: string }).id;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
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
              end: { x: 30, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 30, y: 0 },
              end: { x: 30, y: 20 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 30, y: 20 },
              end: { x: 0, y: 20 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 20 },
              end: { x: 0, y: 0 },
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth,
  });
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };
  await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });

  await openNewDrawing(page, "Plain block — flat pattern");
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-flat-pattern").click();

  // The sheet composes; the flat-pattern view is an honest inline error, not a
  // crash — with the typed reason surfaced.
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
  const errorState = page.getByTestId("drawing-view-error");
  await expect(errorState).toBeVisible();
  await expect(errorState).toHaveAttribute(
    "data-error-code",
    "flat_pattern_not_sheet_metal",
  );
  await expect(page.getByTestId("drawing-bend-table")).toHaveCount(0);
});
