import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Audit N1/N2, the FRONTEND half — the product used to tell the truth on the
 * PRINT and not on the SCREEN. Geometry has shipped all three facts for a while
 * and the app dropped every one of them:
 *
 *  * a re-anchored dimension (`MeasuredDimension.anchor.tier == "durable"`) —
 *    the reference moved when the part changed and geometry re-measured from the
 *    edge that is actually there — read on screen exactly like an untouched one;
 *  * `ComposedSheet.layout_issues` — two views that collide — appeared on the
 *    exported PDF/DXF/SVG as a stamped banner and NOWHERE in the app, so an
 *    unreadable sheet looked fine right up until the shop opened the file.
 *
 * Both are driven here through a real browser against the real stack (no mocks),
 * and the load-bearing assertion is the one the backlog item names: a
 * DIMENSIONED part is resized and the new value is read IN-APP.
 */

/** Build a `width` x 60 x 10 plate with a Ø10 hole, and return the ids needed to
 * edit it again (the sketch is what a resize rewrites). */
async function createPlateViaApi(
  page: Page,
  token: string,
  name: string,
  width: number,
): Promise<{ id: string; sketchId: string; treeVersion: number }> {
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
          ...plate(width),
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
          distance_mm: 10,
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
  const extrudeBody = (await extrude.json()) as { tree_version: number };
  return {
    id: partId,
    sketchId: sketchBody.feature.id,
    treeVersion: extrudeBody.tree_version,
  };
}

/** The plate profile: a `width` x 60 rectangle around a Ø10 hole. */
function plate(width: number) {
  const pts: [number, number][] = [
    [0, 0],
    [width, 0],
    [width, 60],
    [0, 60],
  ];
  return {
    entities: [
      ...pts.map((p, i) => {
        const next = pts[(i + 1) % pts.length] as [number, number];
        return {
          id: `e${i + 1}`,
          kind: "line",
          construction: false,
          start: { x: p[0], y: p[1] },
          end: { x: next[0], y: next[1] },
        };
      }),
      {
        id: "e5",
        kind: "circle",
        construction: false,
        center: { x: 30, y: 30 },
        radius: 5,
      },
    ],
    constraints: [],
  };
}

/** Rewrite the plate's sketch to a new overall width — the one-number edit the
 * 2026-07-30 product audit made, and the one that used to destroy exactly the
 * dimension measuring what changed. */
async function widenPlate(
  page: Page,
  token: string,
  part: { id: string; sketchId: string; treeVersion: number },
  width: number,
): Promise<void> {
  const response = await page.request.patch(
    `/api/v1/parts/${part.id}/features/${part.sketchId}`,
    {
      data: {
        feature: {
          type: "sketch",
          version: 1,
          params: {
            plane: { kind: "datum_plane", plane: "XY" },
            ...plate(width),
          },
        },
        expected_tree_version: part.treeVersion,
      },
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!response.ok()) {
    throw new Error(
      `widen failed: ${response.status()} ${await response.text()}`,
    );
  }
}

/** Create a drawing through the register UI and lay out its standard views. */
async function seedLaidOutDrawing(
  page: Page,
  partId: string,
  name: string,
): Promise<string> {
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
  return new URL(page.url()).pathname.split("/").pop() ?? "";
}

/** The widest horizontal line pick-target in a view (the overall-length edge). */
async function longestHorizontalEdge(page: Page, view: string) {
  const edges = page.locator(
    `[data-testid="drawing-pick-edge"][data-view="${view}"][data-primitive="line"]`,
  );
  const count = await edges.count();
  let best = 0;
  let bestWidth = 0;
  for (let i = 0; i < count; i += 1) {
    const box = await edges.nth(i).boundingBox();
    if (!box) continue;
    if (box.width > box.height && box.width > bestWidth) {
      bestWidth = box.width;
      best = i;
    }
  }
  return edges.nth(best);
}

test.describe("drawings — a resized part, said on screen", () => {
  test("resize a dimensioned part: the sheet re-measures and says it re-anchored", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    const account = await seedSession(page);
    const part = await createPlateViaApi(page, account.token, "Plate", 100);
    await seedLaidOutDrawing(page, part.id, "Plate — resize");

    // Dimension the 100 mm overall length in the top view.
    const edge = await longestHorizontalEdge(page, "top");
    await edge.click({ force: true });
    await expect(page.getByTestId("dimension-author-menu")).toBeVisible();
    await page.getByTestId("dimension-type-linear").click();
    // REACH-3: choosing the type now opens the PLACE stage (the ghost tracks
    // the pointer). Enter commits it UNMOVED, which sends no placement at all —
    // so this flow is the auto-placed dimension it has always been.
    await page.keyboard.press("Enter");
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="100.000"]',
      ),
    ).toHaveCount(1, { timeout: 30_000 });

    // The reference matched verbatim, so the panel says nothing about it.
    const row = page.locator(
      '[data-testid="dimension-row"][data-dimension-type="linear"]',
    );
    await expect(row).toHaveAttribute("data-anchor-tier", "exact", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("dimension-reanchored")).toHaveCount(0);

    // Founder BEFORE frame — the dimensioned sheet at its authored width.
    await page.mouse.move(20, 980);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-reanchor-before-1600.png`,
    });

    // The one-number edit: widen the plate 100 -> 120 and re-project.
    await widenPlate(page, account.token, part, 120);
    await page.getByTestId("drawing-reproject").click();

    // THE ACCEPTANCE: the new value is read IN-APP, on the sheet and in the
    // panel — not a bare `!` marker, and not the stale authored number.
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="120.000"]',
      ),
    ).toHaveCount(1, { timeout: 30_000 });
    await expect(row.getByTestId("dimension-row-value")).toHaveText("120.000");

    // ...and the app SAYS the reference moved, which it never used to.
    await expect(row).toHaveAttribute("data-anchor-tier", "durable", {
      timeout: 30_000,
    });
    await expect(row.getByTestId("dimension-reanchored")).toBeVisible();
    await expect(page.getByTestId("dimension-reanchored-note")).toContainText(
      "Confirm to store the new reference",
    );

    // Founder AFTER frame — re-measured, and honest about why.
    await page.mouse.move(20, 980);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-reanchor-after-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(row.getByTestId("dimension-reanchored")).toBeVisible();
    await page.mouse.move(20, 980);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-reanchor-after-1280.png`,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });

    // One click stores the signature geometry landed on: the dimension keeps its
    // value and its reference is exact again, so the badge retires itself.
    await row.getByTestId("dimension-heal").click();
    const healed = page.locator(
      '[data-testid="dimension-row"][data-dimension-type="linear"]',
    );
    await expect(healed).toHaveAttribute("data-anchor-tier", "exact", {
      timeout: 30_000,
    });
    await expect(healed.getByTestId("dimension-row-value")).toHaveText(
      "120.000",
    );
    await expect(page.getByTestId("dimension-reanchored")).toHaveCount(0);
    // Exactly one dimension survives the append-then-delete heal.
    await expect(page.getByTestId("dimension-row")).toHaveCount(1);
    await expect(
      page.locator(
        '[data-testid="drawing-dimension"][data-dimension-value="120.000"]',
      ),
    ).toHaveCount(1);
  });
});

test.describe("drawings — an overlapping sheet says so", () => {
  test("colliding views raise the sheet check strip, and one click fixes it", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const part = await createPlateViaApi(page, account.token, "Plate", 100);
    const drawingId = await seedLaidOutDrawing(page, part.id, "Plate — layout");

    // A clean auto-laid-out sheet says nothing at all (the additive posture).
    await expect(page.getByTestId("sheet-issue-strip")).toHaveCount(0);
    await expect(page.getByTestId("drawing-layout-issue")).toHaveCount(0);

    // Founder BEFORE frame — the clean sheet.
    await page.mouse.move(20, 980);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-layout-check-before-1600.png`,
    });

    // Hand-place the front and top views on top of one another. An authored
    // position is INTENT: the composer honours it verbatim and REPORTS the
    // collision rather than silently re-flowing it.
    const tree = (await (
      await page.request.get(`/api/v1/drawings/${drawingId}`, { headers: auth })
    ).json()) as {
      doc_version: number;
      sheets: { views: { id: string; projection: string }[] }[];
    };
    let version = tree.doc_version;
    const views = tree.sheets[0]?.views ?? [];
    for (const projection of ["front", "top"]) {
      const view = views.find((v) => v.projection === projection);
      if (!view) throw new Error(`no ${projection} view`);
      const response = await page.request.patch(
        `/api/v1/drawings/${drawingId}/views/${view.id}`,
        {
          data: {
            expected_version: version,
            position: { x_mm: 150, y_mm: 150 },
            auto_place: false,
          },
          headers: auth,
        },
      );
      if (!response.ok()) {
        throw new Error(
          `place ${projection} failed: ${response.status()} ${await response.text()}`,
        );
      }
      version = ((await response.json()) as { doc_version: number })
        .doc_version;
    }

    await page.reload();
    await expect(page.getByTestId("drawing-sheet")).toBeVisible({
      timeout: 30_000,
    });

    // The strip appears beside the paper, in the composer's own words...
    const strip = page.getByTestId("sheet-issue-strip");
    await expect(strip).toBeVisible({ timeout: 30_000 });
    await expect(strip).toHaveAttribute("data-severity", "error");
    // Stacking two views collides them with each other AND with whatever the
    // auto-layout left in that quadrant, so several pairs are reported — the
    // one under test is the pair that was hand-placed.
    const overlapRows = page.locator(
      '[data-testid="sheet-issue-row"][data-issue-code="views_overlap"]',
    );
    expect(await overlapRows.count()).toBeGreaterThan(0);
    const overlapRow = overlapRows.filter({ hasText: "FRONT / TOP" }).first();
    await expect(overlapRow.getByTestId("sheet-issue-message")).toContainText(
      "VIEWS OVERLAP BY",
    );
    // ...and the SAME banner is stamped on the paper, so the SVG you see is the
    // SVG you export (the server serializers use this exact hook).
    const banner = page.getByTestId("drawing-layout-issue").first();
    await expect(banner).toHaveText(/^LAYOUT ERROR: /);

    // Founder AFTER frame — the sheet that used to be silent.
    await page.mouse.move(20, 980);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-layout-check-after-1600.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(strip).toBeVisible();
    await page.mouse.move(20, 980);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/drawing-layout-check-after-1280.png`,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });

    // The row's action is real: it returns both hand-placed views to
    // auto-layout, and the sheet goes quiet again.
    await expect(
      overlapRow.getByTestId("sheet-issue-autoplace"),
    ).toHaveAttribute(
      "aria-label",
      "Return the Front and Top views to auto-layout",
    );
    await overlapRow.getByTestId("sheet-issue-autoplace").click();
    await expect(page.getByTestId("sheet-issue-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("drawing-layout-issue")).toHaveCount(0);
  });
});
