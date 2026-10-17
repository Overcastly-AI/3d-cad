import { expect, test, type Locator, type Page } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * LIBRARY-THUMBNAILS, end to end: the registers and the assembly Add panel
 * show a server-rendered picture of each document (Fusion's Data Panel,
 * Onshape's document list).
 *
 *  - Saved parts show their picture on the Parts page and in the Add panel.
 *  - Editing a part changes its picture (a new image, not the old one).
 *  - A part that does not rebuild shows the placeholder, never a picture.
 *  - An assembly and a drawing get their own pictures too.
 *
 * Writes `docs/screenshots/thumbnails-{parts,add-panel,before-edit,after-edit}.png`.
 */

type Auth = Record<string, string>;
type Point = readonly [number, number];

interface Line {
  id: string;
  kind: "line";
  start: { x: number; y: number };
  end: { x: number; y: number };
}

function outline(points: readonly Point[], prefix = "e"): Line[] {
  return points.map((start, index) => {
    const end = points[(index + 1) % points.length] ?? start;
    return {
      id: `${prefix}${index + 1}`,
      kind: "line",
      start: { x: start[0], y: start[1] },
      end: { x: end[0], y: end[1] },
    };
  });
}

async function postFeature(
  page: Page,
  auth: Auth,
  partId: string,
  body: Record<string, unknown>,
): Promise<{ id: string }> {
  const current = (await (
    await page.request.get(`/api/v1/parts/${partId}`, { headers: auth })
  ).json()) as { tree_version: number };
  const created = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: { ...body, expected_tree_version: current.tree_version },
    headers: auth,
  });
  expect(created.ok(), await created.text()).toBe(true);
  return ((await created.json()) as { feature: { id: string } }).feature;
}

/** A part made of one sketch (`entities`) extruded `depth` mm. */
async function sketchExtrudePart(
  page: Page,
  auth: Auth,
  name: string,
  entities: unknown[],
  depth: number,
): Promise<{ id: string; extrudeId: string }> {
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth,
  });
  expect(part.ok(), await part.text()).toBe(true);
  const id = ((await part.json()) as { id: string }).id;
  const sketch = await postFeature(page, auth, id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities,
        constraints: [],
      },
    },
  });
  const extrude = await postFeature(page, auth, id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.id },
        distance_mm: depth,
        operation: "add",
        direction: "normal",
      },
    },
  });
  return { id, extrudeId: extrude.id };
}

const L_BRACKET: Point[] = [
  [0, 0],
  [60, 0],
  [60, 12],
  [12, 12],
  [12, 45],
  [0, 45],
];
const BLOCK: Point[] = [
  [0, 0],
  [30, 0],
  [30, 30],
  [0, 30],
];
const TEE: Point[] = [
  [0, 0],
  [50, 0],
  [50, 10],
  [30, 10],
  [30, 40],
  [20, 40],
  [20, 10],
  [0, 10],
];

function thumbnailIn(scope: Locator): Locator {
  return scope.getByTestId("document-thumbnail");
}

function partRow(page: Page, partId: string): Locator {
  return page.locator(`[data-testid="part-row"][data-part-id="${partId}"]`);
}

/** SHA-256 of the image the tile is displaying, read back from its blob URL. */
async function pictureDigest(tile: Locator): Promise<string> {
  await expect(tile).toHaveAttribute("data-thumbnail-state", "ready", {
    timeout: 90_000,
  });
  return tile.locator("img").evaluate(async (img) => {
    const bytes = await (
      await fetch((img as HTMLImageElement).src)
    ).arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  });
}

/**
 * The Parts register, framed: a PAGE screenshot clipped to it, so the write
 * goes through the fixture's UPDATE_SCREENSHOTS gate (a locator screenshot
 * would bypass it and dirty the tree on every routine run).
 */
async function shootRegister(page: Page, name: string): Promise<void> {
  const box = await page.getByTestId("parts-register").boundingBox();
  if (box === null) throw new Error("the parts register is not on screen");
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png`, clip: box });
}

test.describe("library thumbnails", () => {
  test("parts, the Add panel, an edit and a failed part", async ({ page }) => {
    test.setTimeout(300_000);
    await page.setViewportSize({ width: 1600, height: 1000 });
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };

    // ---- Several distinct parts, saved through the real gateway -------------
    const plate = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Hole plate",
    );
    const bracket = await sketchExtrudePart(
      page,
      auth,
      "L bracket",
      outline(L_BRACKET),
      8,
    );
    const block = await sketchExtrudePart(
      page,
      auth,
      "Spacer block",
      outline(BLOCK),
      6,
    );
    const tee = await sketchExtrudePart(
      page,
      auth,
      "Tee rail",
      outline(TEE),
      70,
    );
    const puck = await sketchExtrudePart(
      page,
      auth,
      "Round puck",
      [{ id: "c1", kind: "circle", center: { x: 0, y: 0 }, radius: 20 }],
      12,
    );
    // An open outline: its extrude has no closed profile, so it fails.
    const broken = await sketchExtrudePart(
      page,
      auth,
      "Broken bracket",
      outline(L_BRACKET).slice(0, 5),
      8,
    );
    const good = [plate.id, bracket.id, block.id, tee.id, puck.id];

    // ---- Parts page: a picture per part, the placeholder for the failure ----
    await page.goto("/");
    for (const id of good) {
      await expect(thumbnailIn(partRow(page, id))).toHaveAttribute(
        "data-thumbnail-state",
        "ready",
        { timeout: 90_000 },
      );
    }
    const brokenTile = thumbnailIn(partRow(page, broken.id));
    await expect(brokenTile).toHaveAttribute("data-thumbnail-state", "failed", {
      timeout: 90_000,
    });
    await expect(brokenTile.locator("img")).toHaveCount(0);
    // Distinct parts, distinct pictures.
    const digests = await Promise.all(
      good.map((id) => pictureDigest(thumbnailIn(partRow(page, id)))),
    );
    expect(new Set(digests).size).toBe(good.length);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/thumbnails-parts.png` });

    const before = await pictureDigest(thumbnailIn(partRow(page, block.id)));
    await shootRegister(page, "thumbnails-before-edit");

    // ---- The Add panel shows the same pictures --------------------------------
    const assembly = await page.request.post("/api/v1/assemblies", {
      data: { name: "Fixture" },
      headers: auth,
    });
    expect(assembly.ok(), await assembly.text()).toBe(true);
    const assemblyId = ((await assembly.json()) as { id: string }).id;
    await page.goto(`/assemblies/${assemblyId}`);
    await page.getByTestId("add-instance").click();
    const cell = (id: string) =>
      thumbnailIn(page.getByTestId(`add-instance-part-${id}`));
    for (const id of good) {
      await expect(cell(id)).toHaveAttribute("data-thumbnail-state", "ready", {
        timeout: 90_000,
      });
    }
    await expect(cell(broken.id)).toHaveAttribute(
      "data-thumbnail-state",
      "failed",
    );
    expect(await pictureDigest(cell(block.id))).toBe(before);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/thumbnails-add-panel.png`,
    });
    // Two components, so the assembly has a picture of its own below.
    await page.getByTestId(`add-instance-part-${bracket.id}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await page.getByTestId(`add-instance-part-${tee.id}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await page.getByTestId("add-instance-done").click();

    // ---- Edit the spacer block: a different body, a different picture ------
    const tree = (await (
      await page.request.get(`/api/v1/parts/${block.id}/features`, {
        headers: auth,
      })
    ).json()) as {
      tree_version: number;
      features: Array<{
        id: string;
        feature: { params: Record<string, unknown> };
      }>;
    };
    const extrude = tree.features.find((f) => f.id === block.extrudeId);
    if (extrude === undefined) throw new Error("the block has no extrude");
    const patched = await page.request.patch(
      `/api/v1/parts/${block.id}/features/${block.extrudeId}`,
      {
        data: {
          expected_tree_version: tree.tree_version,
          feature: {
            ...extrude.feature,
            params: { ...extrude.feature.params, distance_mm: 60 },
          },
        },
        headers: auth,
      },
    );
    expect(patched.ok(), await patched.text()).toBe(true);

    await page.goto("/");
    const after = await pictureDigest(thumbnailIn(partRow(page, block.id)));
    expect(after).not.toBe(before);
    await shootRegister(page, "thumbnails-after-edit");

    // The Add panel follows the edit as well.
    await page.goto(`/assemblies/${assemblyId}`);
    await page.getByTestId("add-instance").click();
    expect(await pictureDigest(cell(block.id))).toBe(after);

    // ---- The assembly and a drawing have pictures in their registers --------
    await page.goto("/assemblies");
    await expect(
      thumbnailIn(
        page.locator(
          `[data-testid="assembly-row"][data-assembly-id="${assemblyId}"]`,
        ),
      ),
    ).toHaveAttribute("data-thumbnail-state", "ready", { timeout: 90_000 });

    const drawingId = await drawingOf(page, auth, bracket.id);
    await page.goto("/drawings");
    await expect(
      thumbnailIn(
        page.locator(
          `[data-testid="drawing-row"][data-drawing-id="${drawingId}"]`,
        ),
      ),
    ).toHaveAttribute("data-thumbnail-state", "ready", { timeout: 90_000 });
  });
});

/** A drawing of `partId` with one isometric view on its first sheet. */
async function drawingOf(page: Page, auth: Auth, partId: string) {
  const created = await page.request.post("/api/v1/drawings", {
    data: { name: "Bracket drawing" },
    headers: auth,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const drawingId = ((await created.json()) as { id: string }).id;
  const tree = (await (
    await page.request.get(`/api/v1/drawings/${drawingId}`, { headers: auth })
  ).json()) as {
    drawing: { doc_version: number };
    sheets: Array<{ sheet: { id: string } }>;
  };
  let version = tree.drawing.doc_version;
  let sheetId = tree.sheets[0]?.sheet.id;
  if (sheetId === undefined) {
    const sheet = await page.request.post(
      `/api/v1/drawings/${drawingId}/sheets`,
      { data: { expected_version: version, name: "Sheet 1" }, headers: auth },
    );
    expect(sheet.ok(), await sheet.text()).toBe(true);
    const body = (await sheet.json()) as {
      sheet: { id: string };
      doc_version: number;
    };
    sheetId = body.sheet.id;
    version = body.doc_version;
  }
  const view = await page.request.post(
    `/api/v1/drawings/${drawingId}/sheets/${sheetId}/views`,
    {
      data: {
        expected_version: version,
        ref_document_id: partId,
        ref_document_kind: "part",
        projection: "iso",
        position: { x_mm: 120, y_mm: 100 },
      },
      headers: auth,
    },
  );
  expect(view.ok(), await view.text()).toBe(true);
  return drawingId;
}
