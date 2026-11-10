import { expectSolved } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { seedSession } from "./support";

/**
 * ROOF-THROUGH-SHEATHING-UPDATE: B3's hip roof (`loft.roof` 1.3.0) on B2's
 * four walls (`loft.wall` 1.2.0, 7/16 OSB), picked. Its 22 rafter tails and
 * four hips pass through the OSB, sharing 33.2551 in^3 over 30 pairs (22 x
 * 1.22021484375 + 4 x 1.602597506, packages/loft-plugins/tests/
 * test_roof_sheathing.py), so the part counts it twice: 61 718.7499 in^3.
 * The roof's editor says so and offers "Update to 1.9.0" (the latest Roof;
 * a hip frames no ceiling joists or gable ends, so it builds as 1.5.0); nothing changes
 * until it is clicked. The update notches the OSB round every tail (61
 * 685.4948 in^3, the volume less the overlap), and Ctrl+Z restores the 1.3.0
 * roof and its warning.
 */

const IN = 25.4;
const BEFORE = 61718.749941;
const AFTER = 61685.494824;
/** B2's walls, clockwise, framing in: start x, start y, direction, length. */
const B2_WALLS: [number, number, number, number][] = [
  [144, 0, 180, 144],
  [0, 3.5, 90, 113],
  [0, 120, 0, 144],
  [144, 116.5, 270, 113],
];

interface Stored {
  id: string;
  feature: { params: { plugin_version?: string } };
}

async function roofVersion(
  page: Page,
  partId: string,
  token: string,
): Promise<string | undefined> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const { features } = (await response.json()) as { features: Stored[] };
  return features[4]?.feature.params.plugin_version;
}

async function partVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

async function seedHouse(page: Page, token: string): Promise<string> {
  const created = await page.request.post("/api/v1/parts", {
    data: { name: "B3 on B2, sheathed", length_unit: "in" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const part = (await created.json()) as { id: string; tree_version: number };
  let version = part.tree_version;
  const walls: string[] = [];
  for (const [i, [x, y, direction, length]] of B2_WALLS.entries()) {
    const wall = await createFeature(page, token, part.id, {
      name: `Wall ${i + 1}`,
      feature: {
        type: "custom",
        version: 1,
        params: {
          plugin_id: "loft.wall",
          plugin_version: "1.2.0",
          inputs: {
            start_x_mm: x * IN,
            start_y_mm: y * IN,
            direction_deg: direction,
            length_mm: length * IN,
            sheathing: "osb_7_16",
          },
        },
      },
      expected_tree_version: version,
    });
    walls.push(wall.feature.id);
    version = wall.tree_version;
  }
  await createFeature(page, token, part.id, {
    name: "Roof",
    feature: {
      type: "custom",
      version: 1,
      params: {
        plugin_id: "loft.roof",
        plugin_version: "1.3.0",
        inputs: {
          style: "hip",
          walls: walls.map((id) => ({ kind: "feature", feature_id: id })),
        },
      },
    },
    expected_tree_version: version,
  });
  return part.id;
}

test.describe("A stored roof through the sheathing", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("warns, updates to 1.9.0 on request, and Ctrl+Z restores it", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const partId = await seedHouse(page, account.token);

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(5);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 90_000 })
      .toBeCloseTo(BEFORE, 2);

    await page.getByTestId("feature-select-4").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Roof");
    const warning = page.getByTestId("plugin-warning");
    await expect(warning).toContainText("33.2551 in³");
    await expect(warning).toContainText("30 member and panel pairs");
    // Opening the roof changes nothing.
    expect(await roofVersion(page, partId, account.token)).toBe("1.3.0");

    await page.getByTestId("plugin-update").click();
    await expect(editor).toBeHidden({ timeout: 60_000 });
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 90_000 })
      .toBeCloseTo(AFTER, 2);
    expect(await roofVersion(page, partId, account.token)).toBe("1.9.0");
    await page.getByTestId("feature-select-4").click();
    await expect(page.getByTestId("plugin-version")).toHaveText("v1.9.0");
    await expect(page.getByTestId("plugin-warning")).toHaveCount(0);
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    await page.keyboard.press("Control+z");
    await expect
      .poll(() => partVolume(page), { timeout: 90_000 })
      .toBeCloseTo(BEFORE, 2);
    expect(await roofVersion(page, partId, account.token)).toBe("1.3.0");
    await page.getByTestId("feature-select-4").click();
    await expect(page.getByTestId("plugin-warning")).toContainText(
      "Update to 1.9.0",
    );
  });
});
