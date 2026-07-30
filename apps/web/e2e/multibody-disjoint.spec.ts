import { expect, test, type Page } from "./fixtures";

import { rectangleSketch } from "./partSeed";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * MB-4c (docs/design/multi-body.md §MB-4): a boolean between two bodies that do
 * NOT touch would produce more than one disconnected lump. By default that's a
 * `boolean_disjoint` rebuild error (the "operands must touch" safety), but the
 * Combine editor's "Keep as one body" opt-in threads `allow_disjoint` so the
 * result is kept as ONE multi-lump body (a Compound). This spec proves BOTH
 * paths against the real stack — the up-front opt-in, and the guided recovery
 * from the failing error row.
 *
 * Two 20 mm cubes with a 10 mm gap on X (A at x[0,20], B at x[30,50]) never
 * touch → a plain union fails; a disjoint union keeps both = 8000 + 8000 =
 * 16000 mm³, two shells (matches the golden `boolean-union-two-disjoint-cubes`).
 */

/** POST one feature at the tree tip via the real gateway. */
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

/** Seed a part with two NON-touching 20 mm cubes (a 10 mm gap on X). */
async function seedTwoDisjointBodies(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(
    page,
    account.token,
    "Two disjoint cubes",
  );

  const sketchA = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 20, 20),
    },
    expected_tree_version: 0,
  });
  const extrudeA = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchA.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
    expected_tree_version: sketchA.tree_version,
  });

  // Body B — offset 30 mm on X (a 10 mm gap after A's far face at x=20), a new
  // body via merge: false.
  const sketchB = await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(30, 0, 20, 20),
    },
    expected_tree_version: extrudeA.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude2",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchB.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: false,
      },
    },
    expected_tree_version: sketchB.tree_version,
  });
  return part;
}

/** The lit solids + B-rep edges paint far more shades than the empty ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("multi-body disjoint union (MB-4c)", () => {
  test("the opt-in unions non-touching bodies into one multi-lump body", async ({
    page,
  }) => {
    const part = await seedTwoDisjointBodies(page);
    await page.goto(`/parts/${part.id}`);

    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // Each cube is a single connected solid → the Bodies panel shows NO lump badge.
    await expect(page.getByTestId("body-lumps-0")).toHaveCount(0);
    await expect(page.getByTestId("body-lumps-1")).toHaveCount(0);

    await page.getByTestId("new-combine").click();
    await expect(page.getByTestId("combine-editor")).toBeVisible();

    // Turn on "Keep as one body" up front, then union.
    const optIn = page.getByTestId("combine-allow-disjoint");
    await expect(optIn).toHaveAttribute("aria-checked", "false");
    await optIn.click();
    await expect(optIn).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("combine-submit").click();

    // ONE multi-lump body remains; the two 8000 mm³ cubes total 16,000 mm³.
    await expect(page.getByTestId("combine-editor")).toBeHidden();
    await expect(page.getByTestId("body-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("16,000", {
      timeout: 30_000,
    });
    // The surviving body is a disjoint TWO-solid union — the Bodies panel flags it
    // with a quiet multi-solid badge (§MB-4c frontend half).
    await expect(page.getByTestId("body-lumps-0")).toHaveText("2 solids", {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // Founder frame — the Bodies panel's quiet "2 solids" badge on the union.
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.getByTestId("bodies-panel")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/multibody-lump-badge-desktop.png`,
    });
  });

  test("a plain union fails boolean_disjoint, then the guided recovery fixes it", async ({
    page,
  }) => {
    const part = await seedTwoDisjointBodies(page);
    await page.goto(`/parts/${part.id}`);

    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });

    // Union without the opt-in — the create succeeds, the rebuild does not.
    await page.getByTestId("new-combine").click();
    await expect(page.getByTestId("combine-editor")).toBeVisible();
    await page.getByTestId("combine-submit").click();
    await expect(page.getByTestId("combine-editor")).toBeHidden();

    // The tree surfaces the honest boolean_disjoint error AND the recovery.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const recover = page.getByRole("button", { name: "Keep as one body" });
    await expect(recover).toBeVisible({ timeout: 30_000 });

    // One click re-runs the boolean with allow_disjoint on → one multi-lump body.
    await recover.click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-volume")).toContainText("16,000", {
      timeout: 30_000,
    });
    await expect(recover).toBeHidden();
    await expectRenderedBody(page);
  });

  test("founder screenshot: keep-as-one-body opt-in + guided recovery (desktop)", async ({
    page,
  }) => {
    const part = await seedTwoDisjointBodies(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await expectRenderedBody(page);

    // Shot 1 — the Combine editor with the "Keep as one body" opt-in visible.
    await page.getByTestId("new-combine").click();
    await expect(page.getByTestId("combine-allow-disjoint")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/multibody-disjoint-optin-desktop.png`,
    });

    // Shot 2 — the guided recovery in the tree after a plain union fails.
    await page.getByTestId("combine-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await expect(
      page.getByRole("button", { name: "Keep as one body" }),
    ).toBeVisible({ timeout: 30_000 });
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/multibody-disjoint-recovery-desktop.png`,
    });
  });
});
