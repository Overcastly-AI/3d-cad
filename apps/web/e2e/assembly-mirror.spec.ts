import { expect, test, type Page } from "./fixtures";

import { waitForSolved } from "./assemblyFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * ASM-MIRROR-COMPONENT — mirror components, end to end (the backlog's
 * acceptance on a crank arm).
 *
 * The right crank arm is an L (60 x 30, 10 thick), grounded at (10, 0, 0).
 *  1. Mirrored as a COPY about the XY plane offset to z = 20 (the arm is
 *     symmetric about its own mid-thickness, so the copy is a mirror image):
 *     the left arm sits at z = 2 * 20 - 10 = 30, and the BOM counts the crank
 *     arm twice.
 *  2. The source is edited to 14 thick: after a reload the copy follows, to
 *     z = 40 - 14 = 26.
 *  3. The mirror is edited to an OPPOSITE HAND about the YZ plane: the twin
 *     sits at x = -(10 + 60) = -70 with its own (reflected) mesh, and the BOM
 *     reads 1 crank arm + 1 crank arm (opposite hand). It survives a reload.
 */

interface XY {
  x: number;
  y: number;
}

const L_ARM: XY[] = [
  { x: 0, y: 0 },
  { x: 60, y: 0 },
  { x: 60, y: 10 },
  { x: 10, y: 10 },
  { x: 10, y: 30 },
  { x: 0, y: 30 },
];

function sketchFeature(points: XY[]) {
  return {
    type: "sketch",
    version: 1,
    params: {
      plane: { kind: "datum_plane", plane: "XY" },
      entities: points.map((start, i) => ({
        id: `e${i + 1}`,
        kind: "line",
        start,
        end: points[(i + 1) % points.length],
        construction: false,
      })),
      constraints: [],
    },
  };
}

function extrudeFeature(profile: string, depth: number) {
  return {
    type: "extrude",
    version: 1,
    params: {
      profile: { kind: "feature", feature_id: profile },
      distance_mm: depth,
      operation: "add",
      direction: "normal",
    },
  };
}

async function ok(response: {
  ok(): boolean;
  text(): Promise<string>;
  json(): Promise<unknown>;
}): Promise<unknown> {
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

/** The twin's scene pose (x, y-up, z) for the seed `seedId`. */
async function pose(page: Page, seedId: string): Promise<number[]> {
  await waitForSolved(page);
  const twin = page.locator(
    `[data-group-id="${seedId}"][data-pattern-copy="true"]`,
  );
  await expect(twin).toHaveCount(1, { timeout: 30_000 });
  return Promise.all(
    ["x", "y", "z"].map(async (k) =>
      Number(await twin.getAttribute(`data-solved-${k}`)),
    ),
  );
}

async function bom(page: Page): Promise<[string, string][]> {
  await page.getByTestId("inspector-view-bom").click();
  await expect(page.getByTestId("bom-total")).toBeVisible({ timeout: 30_000 });
  const rows = await page
    .getByTestId("bom-row")
    .evaluateAll((all) =>
      all.map((r) => [
        (r.querySelector('[data-testid="bom-name"]')?.textContent ?? "").trim(),
        (
          r.querySelector('[data-testid="bom-quantity"]')?.textContent ?? ""
        ).trim(),
      ]),
    );
  await page.getByTestId("inspector-view-solve").click();
  return rows as [string, string][];
}

test.describe("Assemblies — mirror components", () => {
  test("a crank arm mirrored as a copy follows its edit; as an opposite hand it bills 1 + 1", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const { token } = await seedSession(page);
    const headers = { Authorization: `Bearer ${token}` };

    const part = (await ok(
      await page.request.post("/api/v1/parts", {
        data: { name: "Crank arm" },
        headers,
      }),
    )) as { id: string };
    const sketch = (await ok(
      await page.request.post(`/api/v1/parts/${part.id}/features`, {
        data: {
          name: "Sketch1",
          feature: sketchFeature(L_ARM),
          expected_tree_version: 0,
        },
        headers,
      }),
    )) as { feature: { id: string }; tree_version: number };
    const extrude = (await ok(
      await page.request.post(`/api/v1/parts/${part.id}/features`, {
        data: {
          name: "Extrude1",
          feature: extrudeFeature(sketch.feature.id, 10),
          expected_tree_version: sketch.tree_version,
        },
        headers,
      }),
    )) as { feature: { id: string }; tree_version: number };
    const assembly = (await ok(
      await page.request.post("/api/v1/assemblies", {
        data: { name: "Crankset" },
        headers,
      }),
    )) as { id: string };
    const arm = (await ok(
      await page.request.post(`/api/v1/assemblies/${assembly.id}/instances`, {
        data: {
          expected_version: 0,
          ref_document_id: part.id,
          ref_document_kind: "part",
          name: "Crank arm <1>",
          grounded: true,
          placement: {
            position: { x: 10, y: 0, z: 0 },
            orientation: { x: 0, y: 0, z: 0, w: 1 },
          },
        },
        headers,
      }),
    )) as { instance: { id: string } };
    const armId = arm.instance.id;

    await page.goto(`/assemblies/${assembly.id}`);
    await waitForSolved(page);

    // ——— 1. A mirrored copy about XY at z = 20 ——————————————————————————
    await page.getByTestId("mirror-components").click();
    await expect(page.getByTestId("mirror-dialog")).toBeVisible();
    await page.getByTestId(`mirror-seed-${armId}`).check();
    await page.getByTestId("mirror-plane").selectOption("xy");
    await page.getByTestId("mirror-offset").fill("2 * 10 mm");
    await expect(page.getByTestId("mirror-offset-reading")).toHaveText(
      "= 20 mm",
    );
    await page.getByTestId("mirror-ok").click();
    await expect(page.getByTestId("mirror-dialog")).toBeHidden({
      timeout: 30_000,
    });
    await expect(page.getByTestId("mirror-row")).toHaveCount(1);
    // Scene is Y-up: kernel (x, y, z) -> scene (x, z, -y).
    expect(await pose(page, armId)).toEqual([10, 30, 0]);
    await expect(page.getByTestId("mirror-warning")).toHaveCount(0);
    expect(await bom(page)).toEqual([["Crank arm", "2"]]);

    // ——— 2. Edit the source: 14 thick. The copy follows ————————————————
    const edit = await page.request.patch(
      `/api/v1/parts/${part.id}/features/${extrude.feature.id}`,
      {
        data: {
          expected_tree_version: extrude.tree_version,
          feature: extrudeFeature(sketch.feature.id, 14),
        },
        headers,
      },
    );
    expect(edit.ok(), await edit.text()).toBe(true);
    await page.reload();
    await expect(page.getByTestId("mirror-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect.poll(async () => (await pose(page, armId))[1]).toBe(26);

    // ——— 3. Make it an opposite hand about YZ ——————————————————————————
    await page.getByTestId("mirror-row").dblclick();
    await expect(page.getByTestId("mirror-dialog")).toBeVisible();
    await page.getByTestId("mirror-plane").selectOption("yz");
    await page.getByTestId("mirror-offset").fill("0 mm");
    await page.getByTestId(`mirror-opposite-${armId}`).check();
    await page.getByTestId("mirror-ok").click();
    await expect(page.getByTestId("mirror-dialog")).toBeHidden({
      timeout: 30_000,
    });
    await expect.poll(async () => (await pose(page, armId))[0]).toBe(-70);
    expect(await bom(page)).toEqual([
      ["Crank arm", "1"],
      ["Crank arm (opposite hand)", "1"],
    ]);

    await page.reload();
    await expect(page.getByTestId("mirror-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("mirror-row")).toContainText(
      "Crank arm <1> (opposite hand)",
    );
    expect(await pose(page, armId)).toEqual([-70, 0, 0]);
    expect(await bom(page)).toEqual([
      ["Crank arm", "1"],
      ["Crank arm (opposite hand)", "1"],
    ]);

    await page.setViewportSize({ width: 1600, height: 1000 });
    await waitForSolved(page);
    await page.getByTestId("mirror-row").click();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/asm-mirror.png` });
  });
});
