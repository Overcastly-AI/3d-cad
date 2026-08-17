import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * CAN THE USER GET A 3MF AND A GLB OUT? — EXPORT-2, driven against the real
 * stack (founder, 2026-08-17: *"are we only going to accept one file format as
 * an export?"*).
 *
 * A new format is only shipped when a user can click it and open what lands in
 * their Downloads, so this spec does the thing the unit tests deliberately
 * cannot: it clicks the real cells in the real command band, takes the real
 * bytes off the wire, and PARSES them. Not a magic-number check — a 3MF must be
 * an OPC zip whose central directory contains `3D/3dmodel.model`, and a GLB must
 * be a well-formed glTF 2.0 container whose declared length matches the file and
 * whose JSON chunk names a mesh. A stub that returned four `glTF` bytes and a
 * zip header would pass a magic check and fail here.
 *
 * The kernel-side units gate (extents in mm / metres over the whole golden
 * inventory) lives in `services/geometry/tests/test_export_mesh_formats.py`;
 * what is under test HERE is reachability and the wire.
 */

/** A 3MF is an OPC package: assert the container, not the extension. */
function assertRealThreeMf(bytes: Buffer, label: string): void {
  expect(bytes.subarray(0, 2).toString("latin1"), `${label}: zip magic`).toBe(
    "PK",
  );
  // The central directory holds the member names in plain bytes; a package
  // without the model part is not a 3MF whatever its magic says.
  expect(bytes.includes(Buffer.from("3D/3dmodel.model")), label).toBe(true);
  expect(bytes.byteLength).toBeGreaterThan(500);
}

/** A GLB is a chunked container: walk it rather than sniffing four bytes. */
function assertRealGlb(bytes: Buffer, label: string): void {
  expect(bytes.subarray(0, 4).toString("latin1"), `${label}: glTF magic`).toBe(
    "glTF",
  );
  expect(bytes.readUInt32LE(4), `${label}: glTF version`).toBe(2);
  expect(bytes.readUInt32LE(8), `${label}: declared length`).toBe(
    bytes.byteLength,
  );
  const jsonLength = bytes.readUInt32LE(12);
  expect(bytes.subarray(16, 20).toString("latin1"), `${label}: chunk 0`).toBe(
    "JSON",
  );
  const document: unknown = JSON.parse(
    bytes.subarray(20, 20 + jsonLength).toString("utf-8"),
  );
  const gltf = document as { asset?: { version?: string }; meshes?: unknown[] };
  expect(gltf.asset?.version, label).toBe("2.0");
  expect(gltf.meshes?.length ?? 0, `${label}: meshes`).toBeGreaterThan(0);
}

/** Click a band cell and return the downloaded bytes. */
async function download(page: Page, testId: string): Promise<Buffer> {
  const pending = page.waitForEvent("download");
  await page.getByTestId(testId).click();
  const file = await pending;
  return readFile(await file.path());
}

async function seedCubePart(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Vent bracket");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
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
  return part.id;
}

test.describe("3MF and GLB export", () => {
  test("a part writes both new formats, and they parse", async ({ page }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("part-export-band-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
      { timeout: 30_000 },
    );

    // Both cells are present and enabled before either is clicked — the verb is
    // discoverable, not hidden behind a menu.
    await expect(page.getByTestId("part-export-band-3mf")).toBeEnabled();
    await expect(page.getByTestId("part-export-band-glb")).toBeEnabled();

    assertRealThreeMf(await download(page, "part-export-band-3mf"), "part 3mf");
    assertRealGlb(await download(page, "part-export-band-glb"), "part glb");

    // Nothing failed on the way: a silent failure would leave the strip's
    // status cell saying so.
    await expect(page.getByTestId("part-export-error")).toHaveCount(0);
  });

  test("the panel strip offers the same two, and downloads them", async ({
    page,
  }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
      { timeout: 30_000 },
    );

    // The panel strip is the second mount of the same catalogue (EXPORT-2 folded
    // its private list away); this is that claim, checked against the real DOM.
    const cell = page.getByTestId("part-export-3mf");
    await expect(cell).toBeVisible();
    await expect(cell).toHaveAccessibleName(/slicers/);

    const bytes = await download(page, "part-export-3mf");
    assertRealThreeMf(bytes, "panel 3mf");
  });

  test("named download files carry the new extensions", async ({ page }) => {
    const partId = await seedCubePart(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("part-export-band-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
      { timeout: 30_000 },
    );

    for (const [testId, extension] of [
      ["part-export-band-3mf", ".3mf"],
      ["part-export-band-glb", ".glb"],
    ] as const) {
      const pending = page.waitForEvent("download");
      await page.getByTestId(testId).click();
      const file = await pending;
      // Named after the DOCUMENT (audit N4), with the format's extension — the
      // server's Content-Disposition is authoritative, so this checks the wire.
      expect(file.suggestedFilename()).toBe(`vent-bracket${extension}`);
    }
  });

  test("an assembly writes both new formats too", async ({ page }) => {
    const partId = await seedCubePart(page);

    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Vent stack");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page
      .getByTestId("assembly-row")
      .filter({ hasText: "Vent stack" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);

    await page.getByTestId("add-instance").click();
    await page.getByTestId(`add-instance-part-${partId}`).click();
    await expect(page.getByTestId("instance-row")).toHaveCount(1, {
      timeout: 30_000,
    });
    await page.getByTestId("add-instance-done").click();

    const threeMf = page.getByTestId("assembly-export-band-3mf");
    await expect(threeMf).toBeEnabled({ timeout: 30_000 });
    assertRealThreeMf(
      await download(page, "assembly-export-band-3mf"),
      "assembly 3mf",
    );
    assertRealGlb(
      await download(page, "assembly-export-band-glb"),
      "assembly glb",
    );
  });
});
