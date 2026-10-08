import { readFile } from "node:fs/promises";
import { inflateRawSync } from "node:zlib";

import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * THE .LOFT ROUND TRIP, in the browser (docs/FILE-FORMAT.md): Export .loft from
 * the part's export strip, Open .loft from the parts register, and land on a NEW
 * part whose tree.json is identical to the one that was written and whose
 * rebuilt volume matches the volume the file recorded.
 *
 * The bytes are parsed, not sniffed: the zip's members are read out of the
 * downloaded file, and the tree is compared member to member after the copy is
 * exported in turn — ids aside, since importing into the same install
 * re-mints them.
 */

/** The members of a zip, read straight from its central directory. */
function unzip(bytes: Buffer): Map<string, Buffer> {
  const members = new Map<string, Buffer>();
  const eocd = bytes.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  const count = bytes.readUInt16LE(eocd + 10);
  let at = bytes.readUInt32LE(eocd + 16);
  for (let index = 0; index < count; index++) {
    const method = bytes.readUInt16LE(at + 10);
    const compressed = bytes.readUInt32LE(at + 20);
    const nameLength = bytes.readUInt16LE(at + 28);
    const extraLength = bytes.readUInt16LE(at + 30);
    const commentLength = bytes.readUInt16LE(at + 32);
    const local = bytes.readUInt32LE(at + 42);
    const name = bytes.subarray(at + 46, at + 46 + nameLength).toString();
    const dataStart =
      local +
      30 +
      bytes.readUInt16LE(local + 26) +
      bytes.readUInt16LE(local + 28);
    const raw = bytes.subarray(dataStart, dataStart + compressed);
    members.set(name, method === 8 ? inflateRawSync(raw) : Buffer.from(raw));
    at += 46 + nameLength + extraLength + commentLength;
  }
  return members;
}

async function seedCube(
  page: Page,
): Promise<{ partId: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Loft bracket");
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
  return { partId: part.id, token: account.token };
}

async function exportLoft(
  page: Page,
): Promise<{ bytes: Buffer; name: string }> {
  const pending = page.waitForEvent("download");
  await page.getByTestId("part-export-loft").click();
  const file = await pending;
  return {
    bytes: await readFile(await file.path()),
    name: file.suggestedFilename(),
  };
}

type Tree = { features: { id?: string; params: Record<string, unknown> }[] };

/** tree.json without the ids an import into the same install re-mints. */
function withoutIds(tree: Tree, name: string): unknown {
  const ids = tree.features.map((feature) => feature.id ?? "");
  let text = JSON.stringify({ ...tree, name });
  ids.forEach((id, index) => {
    text = text.split(id).join(`#${index}`);
  });
  return JSON.parse(text);
}

test.describe(".loft export and import", () => {
  test("a part round-trips through a .loft file", async ({ page }) => {
    const { partId } = await seedCube(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
      { timeout: 30_000 },
    );

    const exported = await exportLoft(page);
    expect(exported.name).toBe("loft-bracket.loft");
    const members = unzip(exported.bytes);
    expect([...members.keys()]).toEqual([
      "manifest.json",
      "tree.json",
      "cache/body.step",
    ]);
    const manifest = JSON.parse(members.get("manifest.json")!.toString()) as {
      cache: { properties: { volume_mm3: number } };
    };
    const volume = manifest.cache.properties.volume_mm3;
    expect(volume).toBeCloseTo(8000, 6);

    await page.goto("/");
    await expect(page.getByTestId("import-loft-button")).toBeEnabled();
    await page.getByTestId("import-loft-input").setInputFiles({
      name: exported.name,
      mimeType: "application/octet-stream",
      buffer: exported.bytes,
    });

    // A NEW part, opened from the register.
    await page.waitForURL(
      (url) =>
        /^\/parts\/[^/]+$/.test(url.pathname) && !url.pathname.endsWith(partId),
      { timeout: 30_000 },
    );
    const copyId = new URL(page.url()).pathname.split("/").pop()!;
    expect(copyId).not.toBe(partId);
    await expect(page.getByTestId("feature-row")).toHaveCount(2, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("loft-import-warnings")).toHaveCount(0);
    await expect(page.getByTestId("part-export-controls")).toHaveAttribute(
      "data-export-state",
      "ready",
      { timeout: 30_000 },
    );

    // Its rebuilt volume is the one the file recorded (kernel tolerance).
    const copy = unzip((await exportLoft(page)).bytes);
    const copyManifest = JSON.parse(copy.get("manifest.json")!.toString()) as {
      cache: { properties: { volume_mm3: number } };
    };
    expect(
      Math.abs(copyManifest.cache.properties.volume_mm3 - volume),
    ).toBeLessThanOrEqual(1e-7 * volume);

    // And its tree.json is the same tree, ids and the "copy" name aside.
    const original = JSON.parse(members.get("tree.json")!.toString()) as Tree;
    const again = JSON.parse(copy.get("tree.json")!.toString()) as Tree;
    expect(withoutIds(again, "")).toEqual(withoutIds(original, ""));
  });
});
