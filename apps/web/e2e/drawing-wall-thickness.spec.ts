import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FB-10 — dimensioning a SHELL WALL THICKNESS on a drawing, end to end through a
 * real browser against the real stack.
 *
 * The founder could not put a number on a wall. The two shipped linear modes are
 * an edge's own length and the distance between two picked ENDPOINTS, and a wall's
 * two faces do not line up end to end — the inner rim of a shelled box is shorter
 * than the outer one by exactly one wall on each side — so point-to-point measures
 * a diagonal, not the thickness. `edge_to_edge` names the two EDGES and measures
 * the perpendicular distance between them.
 *
 * Two things are proved here, and the second matters as much as the first:
 *
 *  1. two parallel wall edges dimension to the EXACT authored thickness; and
 *  2. a NON-PARALLEL pair is REFUSED — the sheet stamps the typed
 *     `dimension_not_parallel` marker with words a machinist can act on, and no
 *     number at all. A plausible number on a print that goes to a shop is the
 *     worst outcome this feature has, so the refusal is a gate, not a nicety.
 */

/** Wall thickness (mm) of the shelled housing built below. */
const WALL_MM = 5;

/** Build a 60x40x30 box shelled to a `WALL_MM` wall, open at the top. */
async function createShelledBoxViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const auth = { Authorization: `Bearer ${token}` };
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
              end: { x: 60, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 60, y: 0 },
              end: { x: 60, y: 40 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 60, y: 40 },
              end: { x: 0, y: 40 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 40 },
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

  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: 30,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth,
  });
  if (!extrude.ok()) {
    throw new Error(
      `extrude failed: ${extrude.status()} ${await extrude.text()}`,
    );
  }
  const extrudeBody = (await extrude.json()) as {
    feature: { id: string };
    tree_version: number;
  };

  // Hollow it, leaving the TOP face (z = 30) open — the housing shape.
  const shell = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Shell1",
      feature: {
        type: "shell",
        version: 1,
        params: {
          thickness_mm: WALL_MM,
          faces: {
            kind: "faces",
            refs: [
              {
                kind: "subshape",
                feature_id: extrudeBody.feature.id,
                subshape_type: "face",
                selector: {
                  selector_version: 1,
                  signature: {
                    subshape_type: "face",
                    surface: "plane",
                    area_mm2: 60 * 40,
                    centroid: { x: 30, y: 20, z: 30 },
                    normal: { x: 0, y: 0, z: 1 },
                  },
                },
              },
            ],
          },
        },
      },
      expected_tree_version: extrudeBody.tree_version,
    },
    headers: auth,
  });
  if (!shell.ok()) {
    throw new Error(`shell failed: ${shell.status()} ${await shell.text()}`);
  }
  return { id: partId };
}

/** Create a drawing through the UI and auto-lay-out the four views of `partId`. */
async function layOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<void> {
  await page.goto("/drawings");
  await expect(page.getByTestId("nav-drawings")).toBeVisible();
  await page.getByTestId("create-drawing-name").fill(name);
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await expect(page.getByTestId("drawing-setup-hint")).toBeVisible();
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 30_000,
  });
}

interface PickTarget {
  index: number;
  cx: number;
  cy: number;
}

/**
 * The straight pick-targets of a view, split by orientation and ordered along the
 * axis they are spaced on. In the TOP view of the housing the "vertical" ones are
 * the four Y-running wall edges at x = 0, WALL, 60-WALL, 60 — so the first two are
 * the outer and inner faces of the SAME left wall, which is the pair a thickness
 * dimension names.
 */
async function orderedEdges(
  page: Page,
  view: string,
  orientation: "vertical" | "horizontal",
): Promise<PickTarget[]> {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  const found: PickTarget[] = [];
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    const isVertical = box.height > box.width;
    if (isVertical !== (orientation === "vertical")) continue;
    found.push({
      index: i,
      cx: box.x + box.width / 2,
      cy: box.y + box.height / 2,
    });
  }
  found.sort((a, b) =>
    orientation === "vertical" ? a.cx - b.cx : a.cy - b.cy,
  );
  return found;
}

const pickEdge = (page: Page, view: string, index: number) =>
  page
    .locator(
      `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
    )
    .nth(index);

test("dimension a shell wall thickness edge to edge", async ({ page }) => {
  const account = await seedSession(page);
  const part = await createShelledBoxViaApi(
    page,
    account.token,
    "Housing 60x40x30",
  );
  await layOutDrawing(page, part.id, "Housing — wall");

  // The top view shows the open housing: the outer 60x40 rectangle and, one wall
  // inside it, the cavity rim. The two leftmost Y-running edges are the two faces
  // of the LEFT wall.
  const verticals = await orderedEdges(page, "top", "vertical");
  expect(verticals.length).toBeGreaterThanOrEqual(4);
  const [outer, inner] = verticals;
  expect(outer).toBeDefined();
  expect(inner).toBeDefined();
  // Sanity on the pick itself: the two wall faces are close together and far from
  // the opposite wall — if this ever fails the picks moved, not the measurement.
  const wallGapPx = inner!.cx - outer!.cx;
  const bodyWidthPx = verticals[verticals.length - 1]!.cx - outer!.cx;
  expect(wallGapPx).toBeGreaterThan(0);
  expect(wallGapPx).toBeLessThan(bodyWidthPx / 3);

  // Pick the outer wall face, then reach for the across-the-wall dimension: it
  // ARMS a second-edge pick rather than authoring (the staged two-edge flow).
  await pickEdge(page, "top", outer!.index).click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-start_edge_to_edge").click();
  await expect(page.getByTestId("dimension-pick-hint")).toContainText(
    /measure across/i,
  );

  // Pick the inner wall face → the gated menu offers the distance (first, because
  // that is what was armed) AND the angle, so a mis-entry is never a dead end.
  await pickEdge(page, "top", inner!.index).click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await expect(page.getByTestId("dimension-type-angular")).toBeVisible();
  await page.getByTestId("dimension-type-edge_to_edge").click();
  // REACH-3: choosing the type now opens the PLACE stage (the ghost tracks
  // the pointer). Enter commits it UNMOVED, which sends no placement at all —
  // so this flow is the auto-placed dimension it has always been.
  await page.keyboard.press("Enter");

  // THE NUMBER: the re-evaluate measures the perpendicular distance off the 3D
  // model and stamps the authored wall thickness exactly.
  await expect(
    page.locator(
      `[data-testid="drawing-dimension"][data-dimension-type="linear"][data-dimension-value="${WALL_MM.toFixed(3)}"]`,
    ),
  ).toHaveCount(1, { timeout: 30_000 });

  // The panel row agrees, and says WHICH kind of linear it is.
  const row = page.locator(
    '[data-testid="dimension-row"][data-dimension-mode="edge_to_edge"]',
  );
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId("dimension-row-value")).toHaveText(
    WALL_MM.toFixed(3),
  );

  // Founder frame — a housing print carrying its wall thickness.
  const sheet = page.getByTestId("drawing-sheet");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-wall-thickness-1440.png`,
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(sheet).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-wall-thickness-1280.png`,
  });
});

test("refuse an edge-to-edge dimension between non-parallel edges", async ({
  page,
}) => {
  const account = await seedSession(page);
  const part = await createShelledBoxViaApi(
    page,
    account.token,
    "Housing refusal",
  );
  await layOutDrawing(page, part.id, "Housing — refusal");

  // A wall edge and an edge at right angles to it. Their shortest distance is a
  // real number and means nothing on a print, so it must NOT be stamped.
  const verticals = await orderedEdges(page, "top", "vertical");
  const horizontals = await orderedEdges(page, "top", "horizontal");
  expect(verticals[0]).toBeDefined();
  expect(horizontals[0]).toBeDefined();

  await pickEdge(page, "top", verticals[0]!.index).click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-start_edge_to_edge").click();
  await pickEdge(page, "top", horizontals[0]!.index).click({ force: true });
  await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
  await page.getByTestId("dimension-type-edge_to_edge").click();
  await page.keyboard.press("Enter");

  // THE REFUSAL: a typed marker on the sheet, in the machinist's words, and NO
  // measured value anywhere.
  const marker = page.locator(
    '[data-testid="drawing-dimension"][data-dimension-error="dimension_not_parallel"]',
  );
  await expect(marker).toHaveCount(1, { timeout: 30_000 });
  await expect(marker.getByTestId("drawing-dimension-error")).toHaveText(
    "LINEAR DIM: EDGES NOT PARALLEL - NO PERPENDICULAR DISTANCE",
  );
  await expect(
    page.locator("[data-testid=drawing-dimension][data-dimension-value]"),
  ).toHaveCount(0);

  // The panel says the same thing, in the SERVER's words — the screen is never
  // told less than the print.
  const row = page.locator(
    '[data-testid="dimension-row"][data-dimension-mode="edge_to_edge"]',
  );
  await expect(row.getByTestId("dimension-row-value")).toHaveText("unresolved");
  await expect(row.getByTestId("dimension-row-reason")).toContainText(
    /not parallel|perpendicular distance/i,
  );

  // Founder frame — the refusal as the engineer sees it.
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("drawing-sheet")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/drawings-wall-thickness-refusal-1440.png`,
  });
});
