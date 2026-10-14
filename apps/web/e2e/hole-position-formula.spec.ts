import { expect, test, type Page } from "./fixtures";

import { createFeature, rectangleSketch } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * HOLE-POSITION-FORMULA (docs/RESEARCH.md §20): a hole's X takes a formula,
 * as Fusion 360's hole placement offsets take expressions.
 *
 * A 120 x 40 x 10 plate, W = 100 in the table, a Ø10 through hole on the top
 * face. X typed as `W - 20` puts the hole at x = 80 and stores the formula at
 * `/face_x_mm`; W = 80 in the Parameters panel moves it to x = 60. The volume
 * is 120*40*10 - pi*5^2*10 = 48000 - 250*pi wherever the bore sits.
 */

const VOLUME = 48000 - 250 * Math.PI;

interface StoredFeature {
  feature: {
    type: string;
    expressions?: Record<string, string> | null;
    params: Record<string, unknown> & {
      position?: { x: number; y: number; z: number };
    };
  };
}

async function storedHole(
  page: Page,
  partId: string,
  token: string,
): Promise<StoredFeature["feature"] | undefined> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { features: StoredFeature[] };
  return body.features[2]?.feature;
}

async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

test("a hole's X typed as W - 20 follows W", async ({ page }) => {
  test.slow();
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Hole follows W");
  const auth = { Authorization: `Bearer ${account.token}` };
  const table = await page.request.put(`/api/v1/parts/${part.id}/parameters`, {
    data: {
      expected_tree_version: 0,
      parameters: [
        {
          id: "00000000-0000-4000-8000-0000000004a1",
          name: "W",
          expression: "100",
          unit: "length",
        },
      ],
    },
    headers: auth,
  });
  expect(table.ok(), await table.text()).toBe(true);
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 120, 40),
    },
    expected_tree_version: ((await table.json()) as { tree_version: number })
      .tree_version,
  });
  const extrude = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Hole1",
    feature: {
      type: "hole",
      version: 1,
      params: {
        face: {
          kind: "subshape",
          feature_id: extrude.feature.id,
          subshape_type: "face",
          selector: {
            selector_version: 1,
            signature: {
              subshape_type: "face",
              surface: "plane",
              normal: { x: 0, y: 0, z: 1 },
              centroid: { x: 60, y: 20, z: 10 },
              area_mm2: 4800,
            },
          },
        },
        position: { x: 60, y: 20, z: 10 },
        diameter_mm: 10,
        depth: { kind: "through_all" },
      },
    },
    expected_tree_version: extrude.tree_version,
  });

  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });

  // X = W - 20: marked fx, read as 80, and the hole drills there.
  await page.getByTestId("feature-select-2").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  const x = page.getByTestId("hole-position-x");
  await expect(x).toHaveValue("60");
  await x.fill("W - 20");
  await expect(x).toHaveAttribute("data-formula", "");
  await expect(page.getByTestId("hole-position-x-hint")).toHaveText("= 80 mm");
  await page.mouse.move(1400, 900);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/hole-position-formula-desktop.png`,
  });
  await page.getByTestId("hole-submit").click();
  await expect(page.getByTestId("hole-editor")).toHaveCount(0, {
    timeout: 30_000,
  });
  let hole = await storedHole(page, part.id, account.token);
  expect(hole?.expressions).toEqual({ "/face_x_mm": "W - 20" });
  expect(hole?.params.face_x_mm).toBe(80);
  expect(hole?.params.position).toEqual({ x: 80, y: 20, z: 10 });
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expect
    .poll(() => bodyVolume(page), { timeout: 45_000 })
    .toBeCloseTo(VOLUME, 0);

  // W = 80 in the table: the hole moves to x = 60, and the body is rebuilt
  // with it, healthy.
  await page.getByTestId("parameters-tool").click();
  const panel = page.getByTestId("parameters-panel");
  const cell = panel
    .locator('[data-testid="parameter-row"][data-name="W"]')
    .getByTestId("parameter-expression");
  await cell.fill("80");
  await cell.press("Enter");
  await expect(panel.getByTestId("parameters-saving")).toBeHidden({
    timeout: 30_000,
  });
  await expect
    .poll(
      async () =>
        (await storedHole(page, part.id, account.token))?.params.position,
      { timeout: 30_000 },
    )
    .toEqual({ x: 60, y: 20, z: 10 });
  hole = await storedHole(page, part.id, account.token);
  expect(hole?.params.face_x_mm).toBe(60);
  await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
  await expect
    .poll(() => bodyVolume(page), { timeout: 45_000 })
    .toBeCloseTo(VOLUME, 0);
  await page.getByTestId("parameters-close").click();

  // Re-opened, X shows the formula, and its value is the new 60.
  await page.getByTestId("feature-select-2").click();
  await expect(page.getByTestId("hole-position-x")).toHaveValue("W - 20");
  await expect(page.getByTestId("hole-position-x-hint")).toHaveText("= 60 mm");
});
