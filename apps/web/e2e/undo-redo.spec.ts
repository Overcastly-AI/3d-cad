import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Undo/redo UR2 (docs/design/undo-redo.md) — the frontend controls, driven
 * through the real stack. History is SERVER-side snapshot state, so the API
 * seeding below populates the same ring the UI walks: sketch → extrude →
 * fillet, then undo all the way to the empty baseline and redo all the way
 * back, mixing the toolbar buttons and every keyboard chord (Ctrl+Z,
 * Ctrl+Shift+Z, Ctrl+Y — button/keyboard parity). The redo leg proves the
 * load-bearing UR1 property from the user's seat: the restored fillet still
 * binds the restored extrude (ids verbatim), so the body re-solves rounded —
 * not a rebuild error over an orphaned reference.
 */

/** A 20×20 rectangle fixed at the origin on XY — a clean 20 mm cube extruded. */
const SQUARE_20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 20, y: 0 } },
    { id: "e2", kind: "line", start: { x: 20, y: 0 }, end: { x: 20, y: 20 } },
    { id: "e3", kind: "line", start: { x: 20, y: 20 }, end: { x: 0, y: 20 } },
    { id: "e4", kind: "line", start: { x: 0, y: 20 }, end: { x: 0, y: 0 } },
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
    { kind: "distance", entity: "e1", value_mm: 20 },
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

/**
 * Seed sketch → extrude (20 mm cube) → fillet (all edges, r5): three history
 * steps whose baseline snapshot is the empty tree.
 */
async function seedFilletedCube(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "History cube");
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
      params: { edges: { kind: "all_edges" }, radius_mm: 5 },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

/** The body volume (mm³) parsed from the mass-properties readout. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const nums = text.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat(nums[0] ?? "NaN");
}

/** Both history buttons settled (re-enabled per the server's gates). */
async function expectHistoryGates(
  page: Page,
  gates: { undo: boolean; redo: boolean },
): Promise<void> {
  const undo = page.getByTestId("undo-button");
  const redo = page.getByTestId("redo-button");
  await (gates.undo ? expect(undo).toBeEnabled() : expect(undo).toBeDisabled());
  await (gates.redo ? expect(redo).toBeEnabled() : expect(redo).toBeDisabled());
}

test.describe("undo/redo", () => {
  test("walks the whole history down and back — buttons + every chord, fillet re-bound", async ({
    page,
  }) => {
    const partId = await seedFilletedCube(page);
    await page.goto(`/parts/${partId}`);

    // The seeded chain renders: three features, a rounded cube (< 8,000 mm³).
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(8000);

    // Accessible names + gates: undo lights up (history exists), redo is
    // honestly disabled at the ring's top — and, aria-disabled, still focusable
    // to explain itself.
    await expect(
      page.getByRole("button", { name: "Undo", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Redo", exact: true }),
    ).toBeVisible();
    await expectHistoryGates(page, { undo: true, redo: false });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/undo-redo-band-desktop.png`,
    });

    // Undo #1 (button): the fillet leaves the tree AND the body un-rounds.
    await page.getByTestId("undo-button").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });
    await expectHistoryGates(page, { undo: true, redo: true });

    // Undo #2 (Ctrl+Z): the extrude goes too — no body left to inspect, the
    // viewport drops the solid (export strip shows its honest idle state).
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("part-export-idle")).toBeVisible({
      timeout: 30_000,
    });
    await expectHistoryGates(page, { undo: true, redo: true });

    // Undo #3 (button): back to the empty baseline — undo pins disabled at
    // the ring's floor.
    await page.getByTestId("undo-button").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("empty-viewport-hint")).toBeVisible();
    await expectHistoryGates(page, { undo: false, redo: true });

    // A chord at the floor is a clean no-op, never an error: still empty.
    await page.keyboard.press("Control+z");
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // Redo #1 (Ctrl+Shift+Z): the sketch returns.
    await page.keyboard.press("Control+Shift+z");
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expectHistoryGates(page, { undo: true, redo: true });

    // Redo #2 (Ctrl+Y — the Windows chord): the cube is back at 8,000 mm³.
    await page.keyboard.press("Control+y");
    await expect(page.getByTestId("feature-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });
    await expectHistoryGates(page, { undo: true, redo: true });

    // Redo #3 (button): the fillet returns STILL BOUND to the restored
    // extrude — the tree solves and the volume drops below the cube's again
    // (an orphaned reference would rebuild-error, not round the body).
    await page.getByTestId("redo-button").click();
    await expect(page.getByTestId("feature-row")).toHaveCount(3, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-row").nth(1)).toContainText(
      "extrude",
    );
    await expect(page.getByTestId("feature-row").nth(2)).toContainText(
      "fillet",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(8000);

    // Back at the ring's top: redo pins disabled again.
    await expectHistoryGates(page, { undo: true, redo: false });
  });
});
