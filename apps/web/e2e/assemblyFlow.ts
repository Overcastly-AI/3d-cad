import { expect, type Page } from "./fixtures";

import { distinctCanvasColors, seedSession } from "./support";

/**
 * Shared assembly-workspace e2e plumbing (extracted from `assembly.spec.ts`
 * when the undo/redo spec became its second consumer — the DRY rule): build
 * the hole-plate part via the real gateway, stand up a two-instance assembly
 * through the UI, and author the coincident + concentric "bolt" pair by
 * picking geometry in the viewport.
 */

/** Build a 40×25×10 plate with a Ø10 through hole via the real gateway. */
export async function createPlateWithHoleViaApi(
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
export async function balloonX(
  page: Page,
  instanceId: string,
): Promise<number> {
  const value = await page
    .locator(`[data-testid="assembly-balloon-${instanceId}"]`)
    .getAttribute("data-solved-x");
  return Number.parseFloat(value ?? "NaN");
}

/** Wait until the assembly solve readout has settled (not "Solving…"). */
export async function waitForSolved(page: Page): Promise<string> {
  const status = page.getByTestId("assembly-solve-status");
  await expect
    .poll(async () => (await status.innerText()).trim(), { timeout: 30_000 })
    .not.toMatch(/Solving|^—$/);
  return (await status.innerText()).trim();
}

/** Dispatch a click straight to a pick node (bypasses in-canvas occlusion). */
export async function pickDispatch(
  page: Page,
  selector: string,
): Promise<void> {
  const node = page.locator(selector).first();
  await expect(node).toHaveCount(1, { timeout: 20_000 });
  await node.dispatchEvent("click");
}

/**
 * Seed a session, build the hole-plate part, open a fresh assembly, and add two
 * instances (A auto-grounded, B seeded apart at x ≈ 80). Shared by every mate
 * flow so each test only authors its own mate.
 */
export async function setupTwoInstances(page: Page): Promise<{
  idA: string;
  idB: string;
  seedX: number;
  token: string;
  assemblyId: string;
}> {
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

  const assemblyId = page.url().split("/").pop() ?? "";

  return { idA, idB, seedX, token: account.token, assemblyId };
}

/**
 * Author the "bolt" mate pair in the viewport: Coincident (A's top face z=10 ↔
 * B's bottom face z=0, flush) then Concentric (a hole edge on each — the axes
 * align and the plates bolt up). Asserts each mate lands in the tree.
 */
export async function authorBoltMates(
  page: Page,
  idA: string,
  idB: string,
): Promise<void> {
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

  await page.getByTestId("mate-concentric").click();
  await expect(page.getByTestId("mate-hud")).toBeVisible();
  await pickDispatch(page, `[data-testid^="mate-axis-${idA}-"]`);
  await pickDispatch(page, `[data-testid^="mate-axis-${idB}-"]`);
  await expect(page.getByTestId("mate-row")).toHaveCount(2, {
    timeout: 30_000,
  });
}
