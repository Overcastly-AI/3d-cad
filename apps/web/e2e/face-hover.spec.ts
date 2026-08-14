import { expect, test, type Page } from "./fixtures";

import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
} from "./support";

/**
 * SEL-1 / spec A1 (`docs/design/pre-selection.md` §1, §6) — hovering a body
 * addresses ONE FACE, not the whole solid.
 *
 * The founder's report was "when picking a point on the screen there are too
 * many to see what you are clicking" (FB-8), and underneath it "picking a face
 * is very difficult" (FB-3). The mechanism was that `ModelMesh` typed its
 * highlight per BODY, so the pointer's answer to "what am I about to act on"
 * was the entire solid — which is the same answer everywhere, i.e. no answer.
 * A mis-aim was invisible until it was expensive.
 *
 * WHY THIS IS A NUMBER AND NOT A SCREENSHOT. `countSketchInkPixels` taught us
 * (FB-17d) that a pixel census can REWARD the broken screen — it went up 500x
 * when the sketch became unusable. A hover gate has the same trap available to
 * it: "more lit pixels" is exactly what the whole-body glow produces, so a
 * pixel-count gate would score the DEFECT higher than the fix. The honest
 * assertion is the identity of the addressed face, which the viewport stamps
 * as `data-hovered-face` against `data-total-faces` — the same
 * raster-independent posture `data-selected-faces` already takes for
 * selection.
 *
 * MUTATION-VERIFIED (FB-17's standing requirement). Removing `onPointerMove`
 * from the mesh — i.e. restoring the `onPointerOver`-only handling this ships
 * to replace — turns "the addressed face FOLLOWS the cursor" red while the
 * arrival case stays green, because r3f re-fires `onPointerOver` only when the
 * pointer ENTERS the mesh and never when it crosses between two faces of the
 * same fused mesh. That is the precise defect, and it is the one a spec that
 * only hovered a single point could never see.
 */

/** A 10x20 rectangle fixed at the origin on XY — solves to clean corners. */
const RECTANGLE_10x20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 9.7, y: 0.4 } },
    {
      id: "e2",
      kind: "line",
      start: { x: 10, y: 0.2 },
      end: { x: 10.3, y: 19 },
    },
    { id: "e3", kind: "line", start: { x: 10, y: 20 }, end: { x: 0.4, y: 20 } },
    { id: "e4", kind: "line", start: { x: 0.2, y: 19.6 }, end: { x: 0, y: 0 } },
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
    { kind: "distance", entity: "e1", value_mm: 10 },
    { kind: "distance", entity: "e2", value_mm: 20 },
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

/** A part whose body is a 10x20x30 box — six planar faces, so "one face" and
 *  "the whole body" are provably different sets. */
async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Face hover box");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

/** A 10 mm circle at the box's centre — the profile the bore is cut with. */
const CIRCLE_R5 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "c1", kind: "circle", center: { x: 5, y: 10 }, radius: 3.5 },
  ],
  constraints: [],
};

/**
 * The same box with a THROUGH BORE — a body with a face that WRAPS.
 *
 * Every fixture in this file until now was a six-face box, where every face's
 * boundary is entirely front-facing and the trace cannot be wrong. A cylinder
 * is where it can: `subsetEdges` feeds `EdgesGeometry` one face's triangles and
 * `EdgesGeometry` emits every unmatched edge, so the bore wall's loop is the
 * top circle AND the bottom one. The first cut of the hover trace drew that
 * with no depth test, and the bottom circle painted a bright ellipse across the
 * OUTSIDE of the plate (code review, 2026-08-06). It is the founder shot for
 * exactly that reason: the defect is only legible on a curved face.
 */
async function seedBoredPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Bored plate");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_10x20 },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 12,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  const bore = await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: CIRCLE_R5 },
    expected_tree_version: extrude.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Bore",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: bore.feature.id },
        distance_mm: 12,
        operation: "cut",
        direction: "normal",
      },
    },
    expected_tree_version: bore.tree_version,
  });
  return part;
}

async function openBoxPart(page: Page) {
  const part = await seedBoxPart(page);
  await page.goto(`/parts/${part.id}`);
  // The solid is BUILT (volume) and DRAWN (a lit body puts far more shades on
  // the canvas than the bare bench) — `expectRenderedModel` is the modeler
  // route's wait and its `tessellation-status` cell does not exist here.
  await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
  return page.getByTestId("viewport");
}

/** The addressed face ordinal, or null when the hover addresses nothing. */
async function hoveredFace(page: Page): Promise<number | null> {
  const raw = await page
    .getByTestId("viewport")
    .getAttribute("data-hovered-face");
  return raw === null ? null : Number(raw);
}

test.describe("SEL-1 — the pointer addresses a face, not the solid", () => {
  test("hovering the body names ONE face out of the body's total", async ({
    page,
  }) => {
    const viewport = await openBoxPart(page);
    const box = await viewport.boundingBox();
    if (box === null) throw new Error("no viewport box");

    // At rest nothing is addressed — the attribute is absent rather than a
    // sentinel, so "no face" cannot be confused with "face 0".
    await expect(viewport).not.toHaveAttribute("data-hovered-face", /.*/);

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expect(viewport).toHaveAttribute("data-body-highlight", "hover", {
      timeout: 10_000,
    });
    await expect(viewport).toHaveAttribute("data-hovered-face", /^\d+$/, {
      timeout: 10_000,
    });

    // The addressed face is a PROPER member of the body: a box has six, and the
    // ordinal has to be one of them. This is the "one face, not the solid"
    // claim stated as arithmetic — a whole-body highlight cannot satisfy it,
    // because there is no single ordinal that names the whole solid.
    const total = Number(await viewport.getAttribute("data-total-faces"));
    expect(total).toBe(6);
    const ordinal = await hoveredFace(page);
    expect(ordinal).not.toBeNull();
    expect(ordinal).toBeGreaterThanOrEqual(0);
    expect(ordinal).toBeLessThan(total);
  });

  test("the addressed face FOLLOWS the cursor across a face boundary", async ({
    page,
  }) => {
    const viewport = await openBoxPart(page);
    const box = await viewport.boundingBox();
    if (box === null) throw new Error("no viewport box");

    // Sweep a grid across the middle of the frame. The auto-fit seats the box
    // at an isometric attitude, where three of its six faces are toward the
    // camera, so a grid necessarily crosses at least one face boundary — while
    // the pointer stays on ONE fused mesh the whole way, which is exactly the
    // case `onPointerOver` alone cannot see. A grid rather than a single line
    // because which faces land where depends on the fit, and a gate that
    // depends on guessing two exact coordinates is a flake waiting to happen.
    const seen = new Set<number>();
    // Enter the mesh once so the first `onPointerOver` has fired; from here on
    // it is `onPointerMove` doing all the work.
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expect(viewport).toHaveAttribute("data-hovered-face", /^\d+$/, {
      timeout: 10_000,
    });
    for (let row = 0; row <= 8; row += 1) {
      for (let col = 0; col <= 8; col += 1) {
        await page.mouse.move(
          box.x + box.width * (0.3 + (0.4 * col) / 8),
          box.y + box.height * (0.2 + (0.6 * row) / 8),
        );
        const ordinal = await hoveredFace(page);
        if (ordinal !== null) seen.add(ordinal);
      }
    }

    // At least two DISTINCT faces were addressed during the sweep. Under the
    // old body-grain hover this set is empty (no ordinal is ever published);
    // under an `onPointerOver`-only implementation it has exactly one member
    // (the face the pointer arrived on, frozen for the whole sweep). Two or
    // more is only reachable when the highlight tracks the cursor.
    expect(seen.size).toBeGreaterThanOrEqual(2);
  });

  test("leaving the body drops the addressed face", async ({ page }) => {
    const viewport = await openBoxPart(page);
    const box = await viewport.boundingBox();
    if (box === null) throw new Error("no viewport box");

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expect(viewport).toHaveAttribute("data-hovered-face", /^\d+$/, {
      timeout: 10_000,
    });

    // A corner of the frame is bench, not body. A hover that sticks lit after
    // the pointer has left is the "which one is live?" confusion the founder
    // reported, one step removed.
    await page.mouse.move(box.x + 4, box.y + 4);
    await expect(viewport).not.toHaveAttribute("data-hovered-face", /.*/, {
      timeout: 10_000,
    });
    await expect(viewport).toHaveAttribute("data-body-highlight", "none");
  });
});

/**
 * Founder gallery (design mandate rule 4). The pointer rests on the box's top
 * face; the shot is what the modeller sees while deciding whether to click.
 * Both widths, because a hover cue that only reads at 1600 is not a cue.
 */
async function captureFaceHover(
  page: Page,
  width: "desktop" | "laptop",
): Promise<void> {
  const viewport = await openBoxPart(page);
  const box = await viewport.boundingBox();
  if (box === null) throw new Error("no viewport box");
  // Upper-middle of the frame — at the fit's isometric attitude that is the
  // box's TOP face, the one a modeller reaches for first to sketch on.
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.42);
  await expect(viewport).toHaveAttribute("data-hovered-face", /^\d+$/, {
    timeout: 10_000,
  });
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sel1-face-hover-${width}.png`,
  });
}

/**
 * SEL-1 A7 — the pick reticles at rest, over a body, with a face pick armed.
 * This is the "blanket of floating squares" the founder was reading through;
 * since A2 they are the keyboard/touch fallback rather than the way you aim.
 */
async function captureArmedPick(
  page: Page,
  width: "desktop" | "laptop",
): Promise<void> {
  await openBoxPart(page);
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-pick-face").click();
  await expect(page.getByTestId("face-pick-prompt")).toBeVisible();
  await expect(
    page.locator('[data-testid^="plane-pick-face-"]').first(),
  ).toBeVisible({ timeout: 20_000 });
  // Park the pointer off the body so nothing is hover-lit — the shot is the
  // RESTING state, which is the whole subject of A7.
  await page.mouse.move(8, 8);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sel1-pick-reticles-${width}.png`,
  });
}

/**
 * Founder gallery — the addressed face on a BORE. Hovers the cylindrical wall
 * through the hole's mouth, which is the one place the trace's depth handling
 * is visible: the near circle is traced solid, the far one shows only as a
 * faint x-ray hint through the material instead of a bright ellipse painted on
 * the outside of the plate.
 */
async function captureBoreHover(
  page: Page,
  width: "desktop" | "laptop",
): Promise<void> {
  const part = await seedBoredPart(page);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
  const viewport = page.getByTestId("viewport");
  const box = await viewport.boundingBox();
  if (box === null) throw new Error("no viewport box");

  // Find the bore wall by ADDRESSING it, not by guessing a coordinate — the
  // fit's zoom is not fixed run to run, so a hard-coded point is a flake. The
  // bore's mouth is the one place on this body where a face appears as an
  // ISLAND: a run of samples whose ordinal differs from an identical ordinal on
  // both sides of it. Nothing else on a bored plate has that shape, and it
  // needs no assumption about where the fit put the part.
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.42);
  await expect(viewport).toHaveAttribute("data-hovered-face", /^\d+$/, {
    timeout: 10_000,
  });
  const COLS = 40;
  const ROWS = 24;
  const at = (col: number, row: number) => ({
    x: box.x + box.width * (0.1 + (0.8 * col) / COLS),
    y: box.y + box.height * (0.1 + (0.8 * row) / ROWS),
  });
  let island: { col: number; row: number } | null = null;
  // Row by row, stopping at the first island — the bore sits in the upper half
  // of an isometric fit, so the scan usually ends well before the last row.
  for (let row = 0; row <= ROWS && island === null; row += 1) {
    const line: (number | null)[] = [];
    for (let col = 0; col <= COLS; col += 1) {
      const point = at(col, row);
      await page.mouse.move(point.x, point.y);
      line.push(await hoveredFace(page));
    }
    for (let col = 2; col <= COLS - 2 && island === null; col += 1) {
      const here = line[col];
      const left = line[col - 2];
      const right = line[col + 2];
      if (here !== null && left !== null && left === right && here !== left) {
        island = { col, row };
      }
    }
  }
  expect(island, "the bore wall was never addressed").not.toBeNull();
  const target = at(
    (island as { col: number; row: number }).col,
    (island as { col: number; row: number }).row,
  );
  await page.mouse.move(target.x, target.y);
  await expect(viewport).toHaveAttribute("data-hovered-face", /^\d+$/, {
    timeout: 10_000,
  });
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sel1-bore-trace-${width}.png`,
  });
}

test.describe("SEL-1 — founder screenshots", () => {
  test("pick reticles at rest (desktop 1600×1000)", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await captureArmedPick(page, "desktop");
  });

  test("pick reticles at rest (small laptop 1280×800)", async ({ page }) => {
    // A7 shipped with the desktop shot only. A chrome-DENSITY change is exactly
    // where the small-laptop width earns its keep — the same reticles over a
    // smaller frame are a denser blanket, and 1280×800 is the supported floor
    // (design mandate rule 4, rule 5's responsive floor).
    await page.setViewportSize({ width: 1280, height: 800 });
    await captureArmedPick(page, "laptop");
  });

  test("the addressed face (desktop 1600×1000)", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await captureFaceHover(page, "desktop");
  });

  test("the addressed face (small laptop 1280×800)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await captureFaceHover(page, "laptop");
  });

  test("the addressed BORE wall (desktop 1600×1000)", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await captureBoreHover(page, "desktop");
  });

  test("the addressed BORE wall (small laptop 1280×800)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await captureBoreHover(page, "laptop");
  });
});
