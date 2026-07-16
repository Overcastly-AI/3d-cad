import { expect, test, type Page } from "./fixtures";

import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
} from "./support";

/**
 * Makeover Batch 3 — "in-command depth" (UI-REVIEW 2026-07-16, items 10, 11,
 * 13). Three user-facing guarantees, driven against the REAL stack:
 *   10. an open editor RECEDES the band to the active command + OK/Cancel; OK
 *       runs the editor's own validated submit, Cancel closes it.
 *   11. the body gives selection/hover feedback: hovering it glows (data-hook
 *       "hover"), selecting its feature in the tree warms it ("selected").
 *   13. a blank part shows a first-run call to action, gone the moment work
 *       begins.
 */

/** A 10×20 rectangle fixed at the origin on XY — solves to clean corners. */
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
    {
      id: "e3",
      kind: "line",
      start: { x: 10.2, y: 20.4 },
      end: { x: -0.3, y: 19.7 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.3, y: 19.5 },
      end: { x: -0.2, y: 0.5 },
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

/** Seed a part whose body is a 10×20×30 box (a solved sketch AND a solid). */
async function seedBoxPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Batch3 box");
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

/** Wait for the body to render (volume + a shaded canvas). */
async function waitForBody(page: Page): Promise<void> {
  await expect(page.getByTestId("prop-volume")).toContainText("6,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("item 10 — in-command band", () => {
  test("open editor recedes the band; OK commits, Cancel closes", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBody(page);
    const rows = await page.getByTestId("feature-row").count();

    // Open the Datum command — the band recedes to the in-command bar.
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await expect(page.getByTestId("in-command")).toBeVisible();
    await expect(page.getByTestId("in-command-name")).toHaveText(/Datum plane/);
    await expect(page.getByTestId("in-command-ok")).toBeVisible();
    await expect(page.getByTestId("in-command-cancel")).toBeVisible();
    // The tool groups have receded out of the visual band (kept in the a11y
    // tree + still locked, but sr-only so the band reads as in-command).
    await expect(page.getByTestId("tool-groups")).toHaveClass(/sr-only/);
    await expect(page.getByTestId("new-fillet")).toBeDisabled();

    // OK runs the editor's OWN validated submit — a Plane feature is created.
    await page.getByTestId("in-command-ok").click();
    await expect(page.getByTestId("datum-editor")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(rows + 1);
    await expect(page.getByTestId("feature-row").last()).toContainText("Plane");

    // Reopen a command and Cancel from the band — the editor closes, band restores.
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("in-command-name")).toHaveText(/Fillet/);
    await page.getByTestId("in-command-cancel").click();
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await expect(page.getByTestId("in-command")).toHaveCount(0);
    await expect(page.getByTestId("new-fillet")).toBeVisible();
  });

  test("the band OK reads its true state — disabled while the form is invalid", async ({
    page,
  }) => {
    // Mandate 3a: chrome reads its real state. The band OK must be honestly
    // disabled on an invalid form, not look actionable and silently no-op.
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBody(page);

    // Draft opens with zero picked faces — an invalid form (no_draft_faces).
    await page.getByTestId("new-draft").click();
    await expect(page.getByTestId("draft-editor")).toBeVisible();
    const ok = page.getByTestId("in-command-ok");
    await expect(ok).toBeDisabled();
    await expect(ok).toContainText("Finish the form");

    // A command that is valid by default (Datum) shows OK enabled + its Enter hint.
    await page.getByTestId("in-command-cancel").click();
    await expect(page.getByTestId("draft-editor")).toHaveCount(0);
    await page.getByTestId("tool-datum").click();
    await expect(page.getByTestId("datum-editor")).toBeVisible();
    await expect(ok).toBeEnabled();
    await expect(ok).toContainText("Enter");
  });
});

test.describe("item 11 — body selection/hover feedback", () => {
  test("hovering the body glows; selecting its feature warms it", async ({
    page,
  }) => {
    const part = await seedBoxPart(page);
    await page.goto(`/parts/${part.id}`);
    await waitForBody(page);

    const viewport = page.getByTestId("viewport");
    await expect(viewport).toHaveAttribute("data-body-highlight", "none");

    // Hover the centre of the frame (the auto-fit seats the body there).
    const box = await viewport.boundingBox();
    if (box === null) throw new Error("no viewport box");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expect(viewport).toHaveAttribute("data-body-highlight", "hover", {
      timeout: 10_000,
    });

    // Selecting the extrude row warms the body (the tree→geometry link).
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await expect(viewport).toHaveAttribute("data-body-highlight", "selected");
  });
});

test.describe("item 13 — empty part call to action", () => {
  test("a blank part invites a first sketch, then the hint clears", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Blank part");
    await page.goto(`/parts/${part.id}`);

    await expect(page.getByTestId("empty-viewport-hint")).toBeVisible();
    await expect(page.getByTestId("empty-viewport-hint")).toContainText(
      "Start with a",
    );

    // The moment a sketch begins the hint is gone (work has started).
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("empty-viewport-hint")).toHaveCount(0);
  });
});

/**
 * Founder before/after gallery for Batch 3 (gated behind UPDATE_SCREENSHOTS —
 * see e2e/fixtures.ts). The in-command band, the selected body, and the empty
 * part's call to action.
 */
async function captureBatch3(page: Page, width: "desktop" | "laptop") {
  const part = await seedBoxPart(page);
  await page.goto(`/parts/${part.id}`);
  await waitForBody(page);

  // 1) In-command: the band receded to Fillet + OK/Cancel.
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch3-in-command-${width}.png`,
  });
  await page.getByTestId("in-command-cancel").click();

  // 2) Selection feedback: the extrude's body warmed by a tree pick.
  await page.getByTestId("feature-select-1").click();
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-body-highlight",
    "selected",
  );
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch3-selected-${width}.png`,
  });

  // 3) Empty part call to action.
  const account = await seedSession(page);
  const blank = await createPartViaApi(page, account.token, "Blank part");
  await page.goto(`/parts/${blank.id}`);
  await expect(page.getByTestId("empty-viewport-hint")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/makeover-batch3-empty-${width}.png`,
  });
}

test.describe("founder gallery — Batch 3", () => {
  test("desktop states (in-command, selected, empty)", async ({ page }) => {
    await captureBatch3(page, "desktop");
  });

  test.describe("small laptop (1280×800)", () => {
    test.use({ viewport: { width: 1280, height: 800 } });
    test("laptop states (in-command, selected, empty)", async ({ page }) => {
      await captureBatch3(page, "laptop");
    });
  });
});
