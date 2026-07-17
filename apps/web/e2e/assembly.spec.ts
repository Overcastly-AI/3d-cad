import { expect, test, type Page } from "./fixtures";

import { distinctCanvasColors, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Assemblies v1 #6 — the assembly viewport + mate authoring exit gate. Driven
 * end to end through a real browser against the real stack (gateway +
 * documents + geometry, no mocks): a plate-with-a-hole part is built once via
 * the API, instanced twice into a fresh assembly through the UI, the first
 * auto-grounded, and the free instance is seeded APART. Then a Coincident mate
 * (a face on each) and a Concentric mate (a hole edge on each) are authored by
 * picking geometry in the viewport; each re-solve is asserted, and the free
 * instance is asserted to have MOVED from its authored seed to the solved
 * (bolted) pose — the snap-on-solve. This is "bolt two parts together and see
 * it," the v1 MVP DoD.
 */

/** Build a 40×25×10 plate with a Ø10 through hole via the real gateway. */
async function createPlateWithHoleViaApi(
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

  // A closed rectangle (outer loop) + a circle (inner loop) → a plate with a
  // hole when extruded (multi-loop closed profile, Phase 2).
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
              end: { x: 40, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 40, y: 0 },
              end: { x: 40, y: 25 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 40, y: 25 },
              end: { x: 0, y: 25 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 25 },
              end: { x: 0, y: 0 },
            },
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
  return { id: partId };
}

/** The solved scene-space x of an instance's balloon (== solved OCCT world x). */
async function balloonX(page: Page, instanceId: string): Promise<number> {
  const value = await page
    .locator(`[data-testid="assembly-balloon-${instanceId}"]`)
    .getAttribute("data-solved-x");
  return Number.parseFloat(value ?? "NaN");
}

/** Wait until the assembly solve readout has settled (not "Solving…"). */
async function waitForSolved(page: Page): Promise<string> {
  const status = page.getByTestId("assembly-solve-status");
  await expect
    .poll(async () => (await status.innerText()).trim(), { timeout: 30_000 })
    .not.toMatch(/Solving|^—$/);
  return (await status.innerText()).trim();
}

/** Dispatch a click straight to a pick node (bypasses in-canvas occlusion). */
async function pickDispatch(page: Page, selector: string): Promise<void> {
  const node = page.locator(selector).first();
  await expect(node).toHaveCount(1, { timeout: 20_000 });
  await node.dispatchEvent("click");
}

/**
 * Seed a session, build the hole-plate part, open a fresh assembly, and add two
 * instances (A auto-grounded, B seeded apart at x ≈ 80). Shared by every mate
 * flow so each test only authors its own mate.
 */
async function setupTwoInstances(
  page: Page,
): Promise<{ idA: string; idB: string; seedX: number }> {
  const account = await seedSession(page);
  const part = await createPlateWithHoleViaApi(
    page,
    account.token,
    "Hole plate",
  );

  // 1) Create the assembly from the register UI.
  await page.goto("/assemblies");
  await expect(page.getByTestId("create-assembly-name")).toBeVisible();
  await page.getByTestId("create-assembly-name").fill("Bolted plates");
  await page.getByTestId("create-assembly-name").press("Enter");
  const row = page
    .getByTestId("assembly-row")
    .filter({ hasText: "Bolted plates" });
  await expect(row).toBeVisible();
  await row.getByTestId("assembly-open").click();
  await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
  await expect(page.getByTestId("assembly-name")).toHaveText("Bolted plates");

  // 2) Add two instances of the part through the add-part panel (first is
  //    auto-grounded; the second seeds apart at x = 80).
  await page.getByTestId("add-instance").click();
  await expect(page.getByTestId("add-instance-panel")).toBeVisible();
  const partCell = page.getByTestId(`add-instance-part-${part.id}`);
  await partCell.click();
  await expect(page.getByTestId("instance-row")).toHaveCount(1, {
    timeout: 15_000,
  });
  await partCell.click();
  await expect(page.getByTestId("instance-row")).toHaveCount(2, {
    timeout: 15_000,
  });
  await page.getByTestId("add-instance-done").click();

  // The two instance ids in tree order (A grounded, B free).
  const ids = await page
    .getByTestId("instance-row")
    .evaluateAll((rows) =>
      rows.map((r) => (r as HTMLElement).dataset.instanceId ?? ""),
    );
  const [idA, idB] = ids;
  if (!idA || !idB) throw new Error("expected two instance ids");

  // Both instances render (two lit plates paint many shades).
  await waitForSolved(page);
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  // The free instance sits at its authored seed (x ≈ 80) before any mate.
  const seedX = await balloonX(page, idB);
  expect(seedX).toBeGreaterThan(60);

  return { idA, idB, seedX };
}

async function runAssemblyFlow(
  page: Page,
  seedShot?: string,
): Promise<{ idA: string; idB: string }> {
  const { idA, idB, seedX } = await setupTwoInstances(page);

  // Founder before-shot: the two parts seeded APART, pre-mate.
  if (seedShot) {
    await page.mouse.move(1400, 900);
    await page.screenshot({ path: seedShot });
  }

  // 3a) Coincident: A's top face (z = 10) ↔ B's bottom face (z = 0), flush.
  await page.getByTestId("mate-coincident").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
  );
  await pickDispatch(
    page,
    `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
  );
  await expect(page.getByTestId("mate-row")).toHaveCount(1, {
    timeout: 30_000,
  });
  await waitForSolved(page);

  // 3b) Concentric: a hole edge on each — the axes align, the plates bolt up.
  await page.getByTestId("mate-concentric").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(page, `[data-testid^="mate-axis-${idA}-"]`);
  await pickDispatch(page, `[data-testid^="mate-axis-${idB}-"]`);
  await expect(page.getByTestId("mate-row")).toHaveCount(2, {
    timeout: 30_000,
  });

  // 4) The signature assertion: the free instance MOVED from its seed to the
  //    solved (bolted) pose — the snap-on-solve. The concentric solve pulls the
  //    free plate's hole axis onto the grounded plate's, so its x collapses from
  //    the seed (~80) toward the bolt (~20). Poll so the async re-solve lands
  //    (both mates leave the status "Under constrained", so we watch the pose,
  //    not the label).
  await expect
    .poll(() => balloonX(page, idB), { timeout: 30_000 })
    .toBeLessThan(seedX - 20);

  // The solve is not broken (never conflicting / not converged for this bolt;
  // a single coincident+concentric correctly leaves one spin DOF about the axis).
  const status = await waitForSolved(page);
  expect(status).not.toMatch(/Conflicting|Not converged/);

  // Two plates still render at the solved poses.
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  return { idA, idB };
}

test.describe("Assemblies v1 — bolt two parts and see it", () => {
  test("instance twice, mate coincident + concentric, snap to solved", async ({
    page,
  }) => {
    await runAssemblyFlow(
      page,
      `${SCREENSHOT_DIR}/assembly-seed-apart-desktop.png`,
    );
    // Founder after-shot: the bolted assembly, tree + viewport + solve title block.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-bolted-desktop.png`,
    });
  });
});

test.describe("Assemblies v1 — parametric mates (distance / angle)", () => {
  test("distance mate: pick two faces, set a value, commit, re-solve", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);

    // Arm the distance tool and pick a face on each part (the same face pair a
    // coincident collects — the residual reads the normals + a point on each).
    await page.getByTestId("mate-distance").click();
    await expect(page.getByTestId("mate-hud")).toHaveAttribute(
      "data-mate-tool",
      "distance",
    );
    await pickDispatch(
      page,
      `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
    );
    await pickDispatch(
      page,
      `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
    );

    // The value field appears (not auto-committed) with the sensible default,
    // and is editable before commit — keyboard-first.
    const value = page.getByTestId("mate-value");
    await expect(value).toBeVisible();
    await expect(value).toHaveValue("10");
    await value.fill("20");
    await page.getByTestId("mate-commit").click();

    // The distance mate lands in the tree and the assembly re-solves cleanly.
    const mateRow = page
      .getByTestId("mate-row")
      .filter({ hasText: "Distance" });
    await expect(mateRow).toHaveCount(1, { timeout: 30_000 });
    const status = await waitForSolved(page);
    expect(status).not.toMatch(/Conflicting|Not converged/);
    // Both plates still render at their solved poses.
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);
  });
});

test.describe("Assemblies v1 — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the bolt holds at 1280×800; founder screenshot", async ({ page }) => {
    await runAssemblyFlow(
      page,
      `${SCREENSHOT_DIR}/assembly-seed-apart-laptop.png`,
    );
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(480);
    // Park clear of the bottom-right reference cube (viewport makeover).
    await page.mouse.move(1080, 770);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-bolted-laptop.png`,
    });
  });
});
