/**
 * QA wave 2026-07-30 — INTERACTION probes across the ~20 commits that landed
 * today. Everything here drives the real stack in a real browser; nothing is
 * mocked. Each probe crosses a seam that today's changes made load-bearing and
 * that no shipped spec exercises:
 *
 *  A. the REVISION path — model a real bracket (sketch → extrude → hole →
 *     pattern → mirror → fillet), then change the driving dimension and prove
 *     every downstream feature rebuilt and the file still comes out.
 *  B. a drawing's dimensions survive the edit they measure (`7fde5d2`), driven
 *     through the drawing canvas rather than the composer's unit tests.
 *  C. rollback + export together: the strip says `partial` BEFORE the click and
 *     the FILENAME says it after, and rolling to tip makes both clean again.
 *  D. a failed feature: tree, status, export gate, viewport notice AND the
 *     register next door must tell one story (`b4e075f` derives all of them
 *     from `features/partBuild.ts` — the register is the surface it does NOT
 *     reach, so it is the one worth checking).
 *  E. undo/redo across the new timeline (`1a27804`).
 *  F. the shell refusal at exactly 2x an internal wall (`5af2f6b`): does the
 *     typed error reach a modeler in words, and is the last-good body still
 *     on screen?
 *  G. a `body`-scope mirror after a revolve CUT (today's kernel fix), end to
 *     end through the workspace instead of the golden suite.
 */
import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/** A rectangle of arbitrary size on XY, fully constrained at the origin. */
function rect(width: number, height: number) {
  return {
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
      { kind: "distance", entity: "e1", value_mm: width },
      { kind: "distance", entity: "e2", value_mm: height },
      { kind: "fixed", point: { entity: "e1", point: "start" } },
    ],
  };
}

/** A picked-face reference to a planar face, by its stage-1 signature. */
function faceRef(
  featureId: string,
  area: number,
  centroid: { x: number; y: number; z: number },
  normal: { x: number; y: number; z: number },
) {
  return {
    kind: "subshape",
    feature_id: featureId,
    subshape_type: "face",
    selector: {
      selector_version: 1,
      signature: {
        subshape_type: "face",
        surface: "plane",
        area_mm2: area,
        centroid,
        normal,
      },
    },
  };
}

/** The numeric mm³ the inspector's volume cell is showing. */
async function volumeMm3(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = /([\d,]+(?:\.\d+)?)/.exec(text.replace(/\s/g, ""));
  return match ? Number(match[1]!.replace(/,/g, "")) : Number.NaN;
}

/** Open a part workspace and wait for the tree + first evaluation to land. */
async function openPart(
  page: Page,
  partId: string,
  features: number,
): Promise<void> {
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("feature-row")).toHaveCount(features, {
    timeout: 60_000,
  });
}

// ---------------------------------------------------------------------------
// A. The revision path — a real bracket, then a driving-dimension change.
// ---------------------------------------------------------------------------

/**
 * Sketch → extrude → hole → linear pattern → mirror → fillet, seeded through
 * the real gateway. 60 x 40 x 10 plate; three Ø6 through holes on 15 mm
 * centres; mirrored about XZ (the body straddles y = 0 after the mirror joins
 * across it); R1 on every edge.
 */
async function seedBracket(
  page: Page,
  token: string,
): Promise<{ partId: string; extrudeId: string; sketchId: string }> {
  const part = await createPartViaApi(page, token, "QA bracket");
  const sketch = await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: rect(60, 40) },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  const hole = await createFeature(page, token, part.id, {
    name: "Hole1",
    feature: {
      type: "hole",
      version: 1,
      params: {
        face: faceRef(
          extrude.feature.id,
          60 * 40,
          { x: 30, y: 20, z: 10 },
          { x: 0, y: 0, z: 1 },
        ),
        position: { x: 15, y: 20, z: 10 },
        diameter_mm: 6,
        depth: { kind: "through_all" },
      },
    },
    expected_tree_version: extrude.tree_version,
  });
  const pattern = await createFeature(page, token, part.id, {
    name: "Pattern1",
    feature: {
      type: "pattern",
      version: 1,
      params: {
        pattern: {
          kind: "linear",
          direction: { x: 1, y: 0, z: 0 },
          count: 3,
          spacing_mm: 60,
        },
      },
    },
    expected_tree_version: hole.tree_version,
  });
  const mirror = await createFeature(page, token, part.id, {
    name: "Mirror1",
    feature: {
      type: "mirror",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XZ" },
        scope: { kind: "body" },
      },
    },
    expected_tree_version: pattern.tree_version,
  });
  await createFeature(page, token, part.id, {
    name: "Fillet1",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "all_edges" }, radius_mm: 1 },
    },
    expected_tree_version: mirror.tree_version,
  });
  return {
    partId: part.id,
    extrudeId: extrude.feature.id,
    sketchId: sketch.feature.id,
  };
}

test.describe("A — revise a modelled part", () => {
  test("the chain builds and exports: sketch→extrude→hole→pattern→mirror→fillet", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const { partId } = await seedBracket(page, account.token);
    await openPart(page, partId, 6);

    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });

    // 3 x (60x40x10 plate less a Ø6 through hole) = 71,151.770, mirrored about
    // XZ = 142,303.540, less the R1 edge breaks.
    const volume = await volumeMm3(page);
    expect(volume).toBeGreaterThan(140_000);
    expect(volume).toBeLessThan(143_000);

    await expect(page.getByTestId("part-export-status")).toHaveText("Ready");
    const download = page.waitForEvent("download");
    await page.getByTestId("part-export-step").click();
    const file = await download;
    expect(file.suggestedFilename()).not.toContain("partial");
    const step = await readFile(await file.path(), "utf-8");
    expect(step.startsWith("ISO-10303-21")).toBe(true);
  });

  /**
   * KNOWN DEFECT, filed 2026-07-30 (docs/QA-REVIEW.md QA-2). The commonest
   * revision in CAD — change a plate's thickness — TRANSLATES the top face, and
   * the picked-face resolver keys on the face's absolute centroid, so the hole
   * drilled on that face reports `subshape_unresolved` and everything after it
   * is stranded. Measured: 142,020.953 mm³ becomes a featureless 38,400 mm³
   * brick with 3 of 6 features skipped and export blocked.
   */
  test("changing the driving thickness keeps the hole on the face it was drilled in", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const { partId } = await seedBracket(page, account.token);
    await openPart(page, partId, 6);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    const before = await volumeMm3(page);

    // THE REVISION: 10 mm thick becomes 16 mm, in the editor, per keystroke.
    await page.getByTestId("feature-select-1").click();
    const distance = page.getByTestId("extrude-distance");
    await expect(distance).toHaveValue("10");
    await distance.click();
    await distance.press("Control+a");
    await distance.pressSequentially("16", { delay: 60 });
    await distance.press("Enter");

    // Everything downstream should rebuild against the new thickness.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 60_000,
    });
    await expect
      .poll(() => volumeMm3(page), { timeout: 60_000 })
      .toBeGreaterThan(before * 1.4);
    await expect(page.getByTestId("part-export-status")).toHaveText("Ready");
  });
});

// ---------------------------------------------------------------------------
// B. A drawing's dimensions survive the edit they measure (7fde5d2 / N1).
// ---------------------------------------------------------------------------

/** A 40 x 25 x 10 plate with a Ø10 through hole — the shipped drawing fixture. */
async function seedPlate(
  page: Page,
  token: string,
): Promise<{ partId: string; extrudeId: string }> {
  const part = await createPartViaApi(page, token, "QA plate");
  const sketch = await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          ...rect(40, 25).entities,
          {
            id: "e5",
            kind: "circle",
            center: { x: 20, y: 12.5 },
            radius: 5,
            construction: false,
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return { partId: part.id, extrudeId: extrude.feature.id };
}

/** The tallest vertical line pick-target in a view. */
async function tallestVerticalEdge(page: Page, view: string) {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  let best = 0;
  let bestHeight = 0;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    if (box.height > box.width && box.height > bestHeight) {
      bestHeight = box.height;
      best = i;
    }
  }
  return edges.nth(best);
}

/** Create a drawing through the register UI and lay out its standard views. */
async function layOutPlateDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<void> {
  await page.goto("/drawings");
  await page.getByTestId("create-drawing-name").fill(name);
  await page.getByTestId("create-drawing-submit").click();
  const row = page.getByTestId("drawing-row").first();
  await expect(row).toBeVisible();
  await row.getByTestId("drawing-open").click();
  await page.getByTestId("drawing-part-select").selectOption(partId);
  await page.getByTestId("drawing-autolayout").click();
  await expect(page.getByTestId("drawing-sheet")).toBeVisible({
    timeout: 60_000,
  });
}

/** Retype the extrude's distance in the part workspace, per keystroke. */
async function reviseThickness(
  page: Page,
  partId: string,
  next: string,
): Promise<void> {
  await openPart(page, partId, 2);
  await page.getByTestId("feature-select-1").click();
  const distance = page.getByTestId("extrude-distance");
  await expect(distance).toBeVisible();
  await distance.click();
  await distance.press("Control+a");
  await distance.pressSequentially(next, { delay: 60 });
  await distance.press("Enter");
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
}

test.describe("B — a print survives a revision", () => {
  test("a dimension measuring the thickness re-anchors when the thickness changes", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const { partId } = await seedPlate(page, account.token);

    // Lay out the standard views for the plate.
    await page.goto("/drawings");
    await page.getByTestId("create-drawing-name").fill("QA revision print");
    await page.getByTestId("create-drawing-submit").click();
    const row = page.getByTestId("drawing-row").first();
    await expect(row).toBeVisible();
    await row.getByTestId("drawing-open").click();
    await page.getByTestId("drawing-part-select").selectOption(partId);
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });

    // Dimension the hole (Ø10) and the 10 mm THICKNESS edge in the front view —
    // the edge the revision is about to change out from under the dimension.
    const circle = page
      .locator(
        '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
      )
      .first();
    await circle.click({ force: true });
    await page.getByTestId("dimension-type-diameter").click();
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
      ),
    ).toHaveCount(1, { timeout: 60_000 });

    const thickness = await tallestVerticalEdge(page, "front");
    await thickness.click({ force: true });
    await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
    await page.getByTestId("dimension-type-linear").click();
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="10.000"]',
      ),
    ).toHaveCount(1, { timeout: 60_000 });

    // REVISE the part: 10 mm becomes 16 mm.
    await openPart(page, partId, 2);
    await page.getByTestId("feature-select-1").click();
    const distance = page.getByTestId("extrude-distance");
    await expect(distance).toHaveValue("10");
    await distance.click();
    await distance.press("Control+a");
    await distance.pressSequentially("16", { delay: 60 });
    await distance.press("Enter");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    // Back to the print and refresh the views from the part.
    await page.goBack();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });
    await page.getByTestId("drawing-reproject").click();

    // THE FIX (7fde5d2 N1) WORKS: the linear dimension measuring the edge the
    // revision changed followed it, 10.000 -> 16.000, instead of being
    // destroyed by the very edit it was measuring.
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="16.000"]',
      ),
    ).toHaveCount(1, { timeout: 60_000 });
    await expect(page.getByTestId("dimension-row")).toHaveCount(2);

    // The revised print still exports.
    const svg = page.waitForEvent("download");
    await page.getByTestId("drawing-export-svg").click();
    const file = await svg;
    const body = await readFile(await file.path(), "utf-8");
    expect(body).toContain("<svg");
  });

  /**
   * KNOWN DEFECT, filed 2026-07-30 (docs/QA-REVIEW.md QA-3). A thickness change
   * TRANSLATES the hole's circular edge in z without altering its diameter or
   * its (x, y) centre, and the circle tier-2 re-anchor keys on the centre, so a
   * diameter dimension on a hole the revision never touched goes `unresolved`
   * and vanishes from the sheet — the same revision-destroys-the-print failure
   * N1 set out to end, one curve kind over.
   */
  test("a diameter dimension the revision did not touch survives it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const { partId } = await seedPlate(page, account.token);
    await layOutPlateDrawing(page, partId, "QA diameter survival");

    const circle = page
      .locator(
        '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
      )
      .first();
    await circle.click({ force: true });
    await page.getByTestId("dimension-type-diameter").click();
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
      ),
    ).toHaveCount(1, { timeout: 60_000 });

    await reviseThickness(page, partId, "16");

    await page.goBack();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });
    await page.getByTestId("drawing-reproject").click();
    await expect(page.getByTestId("drawing-projecting")).toHaveCount(0, {
      timeout: 60_000,
    });

    // The hole is still Ø10 — the revision changed the plate's depth, not it.
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
      ),
    ).toHaveCount(1, { timeout: 60_000 });
  });

  /**
   * KNOWN DEFECT, filed 2026-07-30 (docs/QA-REVIEW.md QA-4). `7fde5d2` states
   * that a reference which cannot be re-anchored "now prints WORDS beside the
   * view (`DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE`) in SVG/PDF/DXF".
   * On this path it prints nothing: the authored dimension is silently ABSENT
   * from the exported SVG *and* from the on-screen sheet, and the only place
   * that says anything is the Dimensions panel's small "unresolved" cell. A
   * print that has quietly lost a dimension looks exactly like a complete one.
   */
  // STILL PINNED, and its REPRO is now stale — noted 2026-07-30 after the fixes
  // landed. This asserted that revising a thickness LOSES the diameter dimension
  // and that the loss is announced. The revision no longer loses it (that was
  // QA-3, fixed), so this repro cannot produce the state it is testing.
  //
  // It also mis-stated the defect: measured against the real gateway, the
  // EXPORTED file does carry "DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE".
  // The surface that says nothing is the ON-SCREEN sheet, where DimensionGlyph
  // still draws a bare `!` (filed as QA-4b, in flight).
  //
  // Rewrite: drive a genuine loss instead — move the hole in the sketch
  // (hole_x 20 -> 28) — and the assertion splits cleanly, the exported-file half
  // passing today and the on-screen half staying red until QA-4b lands. Left
  // pinned rather than rewritten now because QA-4b is being changed as I write.
  test("a lost reference is announced on the sheet AND in the exported file", async ({
    page,
  }) => {
    test.fail();
    const account = await seedSession(page);
    const { partId } = await seedPlate(page, account.token);
    await layOutPlateDrawing(page, partId, "QA lost reference");

    const circle = page
      .locator(
        '[data-testid="drawing-pick-edge"][data-view="top"][data-primitive="circle"]',
      )
      .first();
    await circle.click({ force: true });
    await page.getByTestId("dimension-type-diameter").click();
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="Ø10.000"]',
      ),
    ).toHaveCount(1, { timeout: 60_000 });

    await reviseThickness(page, partId, "16");
    await page.goBack();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 60_000,
    });
    await page.getByTestId("drawing-reproject").click();
    await expect(page.getByTestId("drawing-projecting")).toHaveCount(0, {
      timeout: 60_000,
    });

    // The panel knows — it marks the row `unresolved`.
    await expect(
      page.locator(
        '[data-testid="dimension-row"][data-dimension-type="diameter"]',
      ),
    ).toContainText("unresolved");

    // The print a shop reads must say so, in the words the composer defines.
    const svg = page.waitForEvent("download");
    await page.getByTestId("drawing-export-svg").click();
    const body = await readFile(await (await svg).path(), "utf-8");
    expect(body).toContain("REFERENCE LOST");

    // ...and so must the sheet the engineer is looking at.
    await expect(page.getByTestId("drawing-sheet")).toContainText(
      "REFERENCE LOST",
    );
  });
});

// ---------------------------------------------------------------------------
// C. Rollback + export together.
// ---------------------------------------------------------------------------

test.describe("C — rollback and export", () => {
  test("the strip warns BEFORE the click, the filename says partial, and TO TIP is clean again", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "QA rollback");
    const sketch = await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    const extrude = await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 20,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    await createFeature(page, account.token, part.id, {
      name: "Fillet1",
      feature: {
        type: "fillet",
        version: 1,
        params: { edges: { kind: "all_edges" }, radius_mm: 2 },
      },
      expected_tree_version: extrude.tree_version,
    });
    await openPart(page, part.id, 3);
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 60_000,
    });

    // Park the travel stop after Extrude1 — the fillet is held out.
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("timeline-strip")).not.toHaveAttribute(
      "data-busy",
      "true",
      { timeout: 60_000 },
    );
    await expect(page.getByTestId("body-status")).toHaveText("Rolled back", {
      timeout: 60_000,
    });

    // BEFORE the click: the export strip must say the file will be partial.
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "partial",
    );
    await expect(page.getByTestId("part-export-notice")).toContainText(
      "partial",
    );

    // AFTER the click: the FILENAME says it, and it is a real STEP.
    const partialDownload = page.waitForEvent("download");
    await page.getByTestId("part-export-step").click();
    const partial = await partialDownload;
    expect(partial.suggestedFilename()).toContain("-partial");
    expect(
      (await readFile(await partial.path(), "utf-8")).startsWith(
        "ISO-10303-21",
      ),
    ).toBe(true);

    // TO TIP: the mark comes OFF — both on screen and in the next filename.
    await page.getByTestId("timeline-to-tip").click();
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
    );
    const cleanDownload = page.waitForEvent("download");
    await page.getByTestId("part-export-step").click();
    const clean = await cleanDownload;
    expect(clean.suggestedFilename()).not.toContain("partial");
  });
});

// ---------------------------------------------------------------------------
// D. A failed feature, read from EVERY surface including the register.
// ---------------------------------------------------------------------------

test.describe("D — one story about a broken part", () => {
  test("tree, status, export gate, viewport notice and the parts register agree", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "QA broken");
    const sketch = await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    const extrude = await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 20,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    // A hole placed OFF the body — a real modelling mistake, not a synthetic
    // signature: the face resolves, the drill point misses the material.
    const hole = await createFeature(page, account.token, part.id, {
      name: "Hole1",
      feature: {
        type: "hole",
        version: 1,
        params: {
          face: faceRef(
            extrude.feature.id,
            400,
            { x: 10, y: 10, z: 20 },
            { x: 0, y: 0, z: 1 },
          ),
          position: { x: 60, y: 60, z: 20 },
          diameter_mm: 4,
          depth: { kind: "through_all" },
        },
      },
      expected_tree_version: extrude.tree_version,
    });
    await createFeature(page, account.token, part.id, {
      name: "Fillet1",
      feature: {
        type: "fillet",
        version: 1,
        params: { edges: { kind: "all_edges" }, radius_mm: 2 },
      },
      expected_tree_version: hole.tree_version,
    });

    await openPart(page, part.id, 4);

    // 1) SOLVE.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 60_000,
    });
    // 2) STATUS.
    await expect(page.getByTestId("body-status")).toHaveText("Partial");
    await expect(page.getByTestId("body-status-detail")).toContainText(
      "Hole1 failed",
    );
    // 3) The TREE names the cause in words a modeler can act on (the friendly
    //    copy lives in the sibling error row, keyed on the typed code).
    const holeError = page.getByTestId("feature-error-2");
    await expect(holeError).toContainText("hole_off_body");
    await expect(holeError).toContainText("no material is removed");
    // 4) The EXPORT gate refuses, and forcing it produces nothing.
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "feature-error",
    );
    const forced = page
      .waitForEvent("download", { timeout: 3_000 })
      .then(() => true)
      .catch(() => false);
    await page.getByTestId("part-export-step").click({ force: true });
    expect(await forced).toBe(false);
    // 5) The VIEWPORT says the solid is not the part.
    await expect(page.getByTestId("partial-body-notice")).toContainText(
      "Hole1 failed",
    );

    // 6) THE REGISTER NEXT DOOR — the surface `partBuild.ts` does not reach.
    await page.goto("/");
    await expect(page.getByTestId("parts-table")).toBeVisible({
      timeout: 60_000,
    });
    const registerRow = page
      .getByTestId("part-row")
      .filter({ hasText: "QA broken" })
      .first();
    await expect(registerRow).toBeVisible({ timeout: 60_000 });
    const health = registerRow.locator('[data-testid="part-health"]');
    await expect(health).toHaveAttribute("data-health", "failed", {
      timeout: 60_000,
    });
    await expect(health).toContainText("Broken");
  });
});

// ---------------------------------------------------------------------------
// E. Undo / redo across the timeline.
// ---------------------------------------------------------------------------

test.describe("E — history and the timeline", () => {
  test("the strip tracks undo/redo, and a rolled-back state survives an undo", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "QA history");
    const sketch = await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20 },
      expected_tree_version: 0,
    });
    const extrude = await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 20,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    await createFeature(page, account.token, part.id, {
      name: "Fillet1",
      feature: {
        type: "fillet",
        version: 1,
        params: { edges: { kind: "all_edges" }, radius_mm: 2 },
      },
      expected_tree_version: extrude.tree_version,
    });
    await openPart(page, part.id, 3);
    await expect(page.getByTestId("body-status")).toHaveText("Up to date", {
      timeout: 60_000,
    });
    await expect(page.locator('[data-testid^="timeline-chip-"]')).toHaveCount(
      3,
    );

    // Roll back to Extrude1 — a deliberate state with a control holding it.
    await page.getByTestId("rollback-slot-1").click();
    await expect(page.getByTestId("body-status")).toHaveText("Rolled back", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("timeline-stop")).toHaveAttribute(
      "aria-valuetext",
      "After Extrude1 — 2 of 3 built",
    );

    // Add a feature while rolled back is not the probe; UNDO is. The rollback
    // stop is a VIEW of the tree, not an edit of it, so an undo of the LAST
    // real edit (Fillet1's creation) must leave the tree at 2 features and must
    // not silently strand the travel stop past the tip.
    const undo = page.getByTestId("undo-button");
    await expect(undo).toBeEnabled({ timeout: 60_000 });
    await undo.click();
    await expect(page.getByTestId("feature-row")).toHaveCount(2, {
      timeout: 60_000,
    });
    await expect(page.locator('[data-testid^="timeline-chip-"]')).toHaveCount(
      2,
      { timeout: 60_000 },
    );
    // Whatever the stop now reads, it must name a position that EXISTS: a
    // travel stop pointing past the tip is a control describing nothing.
    const stop = page.getByTestId("timeline-stop");
    const now = Number(await stop.getAttribute("aria-valuenow"));
    const max = Number(await stop.getAttribute("aria-valuemax"));
    expect(max).toBe(2);
    expect(now).toBeLessThanOrEqual(max);

    // REDO restores Fillet1 and the strip grows back with it.
    const redo = page.getByTestId("redo-button");
    await expect(redo).toBeEnabled({ timeout: 60_000 });
    await redo.click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3, {
      timeout: 60_000,
    });
    await expect(page.locator('[data-testid^="timeline-chip-"]')).toHaveCount(
      3,
      { timeout: 60_000 },
    );
  });
});

// ---------------------------------------------------------------------------
// F. The shell refusal at exactly 2x an internal wall.
// ---------------------------------------------------------------------------

/**
 * The SH-1 layout, exactly as the pinch golden records it: a 40 x 40 x 10 plate
 * with an [4,12] x [10,30] through-pocket and r3 fillets on every Z-parallel
 * edge, leaving a 4 mm internal rib. Shelling at t = 2 makes the rib exactly
 * 2 x t, so the two inward offsets land on the same plane and the cavity
 * pinches to a zero-width slit — the service must REFUSE
 * (`shell_thickness_too_large`) rather than ship a cracked body.
 */
async function seedRibbedPlate(
  page: Page,
  token: string,
): Promise<{ partId: string; extrudeId: string; treeVersion: number }> {
  const part = await createPartViaApi(page, token, "QA rib plate");
  const sketch = await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: rect(40, 40) },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  const pocketSketch = await createFeature(page, token, part.id, {
    name: "SketchPocket",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XY" },
        entities: [
          {
            id: "a1",
            kind: "line",
            start: { x: 4, y: 10 },
            end: { x: 12, y: 10 },
          },
          {
            id: "a2",
            kind: "line",
            start: { x: 12, y: 10 },
            end: { x: 12, y: 30 },
          },
          {
            id: "a3",
            kind: "line",
            start: { x: 12, y: 30 },
            end: { x: 4, y: 30 },
          },
          {
            id: "a4",
            kind: "line",
            start: { x: 4, y: 30 },
            end: { x: 4, y: 10 },
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: extrude.tree_version,
  });
  const pocket = await createFeature(page, token, part.id, {
    name: "Pocket",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: pocketSketch.feature.id },
        distance_mm: 10,
        operation: "cut",
        direction: "normal",
      },
    },
    expected_tree_version: pocketSketch.tree_version,
  });
  const fillets = await createFeature(page, token, part.id, {
    name: "CornerFillets",
    feature: {
      type: "fillet",
      version: 1,
      params: { edges: { kind: "axis_parallel", axis: "Z" }, radius_mm: 3 },
    },
    expected_tree_version: pocket.tree_version,
  });
  return {
    partId: part.id,
    extrudeId: extrude.feature.id,
    treeVersion: fillets.tree_version,
  };
}

test.describe("F — the shell refusal reaches the user", () => {
  test("t = 2 on a 4 mm rib is refused in words, and the last good body is still there", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const { partId, extrudeId, treeVersion } = await seedRibbedPlate(
      page,
      account.token,
    );
    await openPart(page, partId, 5);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    // 40x40x10 less the 8x20 through-pocket, plus the r3 corner reliefs.
    await expect
      .poll(() => volumeMm3(page), { timeout: 60_000 })
      .toBeCloseTo(14_400, 0);

    // Shell at exactly half the rib, top face open: the pinch case.
    await createFeature(page, account.token, partId, {
      name: "Shell1",
      feature: {
        type: "shell",
        version: 1,
        params: {
          thickness_mm: 2,
          faces: {
            kind: "faces",
            refs: [
              faceRef(
                extrudeId,
                1600,
                { x: 20, y: 20, z: 10 },
                { x: 0, y: 0, z: 1 },
              ),
            ],
          },
        },
      },
      expected_tree_version: treeVersion,
    });
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(6, {
      timeout: 60_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 60_000,
    });

    // THE PROBE: the refusal has to be readable. A modeler must be told what to
    // change ("thickness") and which way, not handed a code.
    const shellError = page.getByTestId("feature-error-5");
    await expect(shellError).toContainText("shell_thickness_too_large");
    await expect(shellError).toContainText(/thickness/i);
    await expect(shellError).toContainText("2.0 mm");
    // ...and it must name a move the modeler can make, not just the symptom.
    await expect(shellError).toContainText(
      /thinner|reduce|change the thickness/i,
    );

    // And the LAST GOOD body is still on screen, unchanged.
    await expect(page.getByTestId("body-status-detail")).toContainText(
      "built to CornerFillets",
    );
    await expect
      .poll(() => volumeMm3(page), { timeout: 60_000 })
      .toBeCloseTo(14_400, 0);
  });
});

// ---------------------------------------------------------------------------
// G. A body-scope mirror after a revolve CUT (today's kernel fix).
// ---------------------------------------------------------------------------

test.describe("G — mirror after a subtractive revolve", () => {
  /**
   * KNOWN DEFECT, filed 2026-07-30 (docs/QA-REVIEW.md QA-1): when the recorded
   * cut STRADDLES the mirror plane the reflected tool can no longer reach the
   * body, `mirror_cut` falls back to `mirror_union`, and OCCT's fuse of the
   * body with its own reflection WELDS the two half-voids shut — 1,072.330 mm³
   * of material that is not in the model, with every feature reporting `ok` and
   * `Shape.is_valid` false. Marked `test.fail` so the suite stays honest: this
   * flips to a failure the moment the defect is fixed, which is the signal.
   */
  test("the mirrored half reflects the cut instead of filling it", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "QA mirror cut");
    // 40 x 40 x 10 block on XY, x/y in 0..40.
    const sketch = await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: rect(40, 40) },
      expected_tree_version: 0,
    });
    const extrude = await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    // A revolve CUT: a small square profile swept about a centerline on X,
    // carving an annular groove out of the block.
    const profile = await createFeature(page, account.token, part.id, {
      name: "Sketch2",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XZ" },
          entities: [
            {
              id: "axis",
              kind: "line",
              start: { x: 8, y: -5 },
              end: { x: 8, y: 20 },
              construction: true,
            },
            {
              id: "p1",
              kind: "line",
              start: { x: 12, y: 2 },
              end: { x: 16, y: 2 },
            },
            {
              id: "p2",
              kind: "line",
              start: { x: 16, y: 2 },
              end: { x: 16, y: 10 },
            },
            {
              id: "p3",
              kind: "line",
              start: { x: 16, y: 10 },
              end: { x: 12, y: 10 },
            },
            {
              id: "p4",
              kind: "line",
              start: { x: 12, y: 10 },
              end: { x: 12, y: 2 },
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: extrude.tree_version,
    });
    const revolve = await createFeature(page, account.token, part.id, {
      name: "Groove",
      feature: {
        type: "revolve",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: profile.feature.id },
          axis: { kind: "sketch_line", entity: "axis" },
          angle_deg: 360,
          operation: "cut",
        },
      },
      expected_tree_version: profile.tree_version,
    });
    await openPart(page, part.id, 4);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    const cutVolume = await volumeMm3(page);

    // Now mirror the WHOLE BODY about XZ (y = 0), which the block straddles.
    await createFeature(page, account.token, part.id, {
      name: "Mirror1",
      feature: {
        type: "mirror",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XZ" },
          scope: { kind: "body" },
        },
      },
      expected_tree_version: revolve.tree_version,
    });
    await page.reload();
    await expect(page.getByTestId("feature-row")).toHaveCount(5, {
      timeout: 60_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    // The mirrored body is exactly TWICE the cut body. If the reflection filled
    // the groove instead of reflecting it, the total would exceed 2x.
    await expect
      .poll(() => volumeMm3(page), { timeout: 60_000 })
      .toBeCloseTo(cutVolume * 2, -1);
  });
});
