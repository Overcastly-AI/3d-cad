import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { seedSession } from "./support";

/**
 * FORMULA-BARE-UNIT: in an inch part a bare number added to a length reads
 * in inches, as in Fusion, against the real stack.
 *
 *  - An Extrude distance typed as `wall + 1/2` (wall = 5.5 in) echoes
 *    `= 6 in`, is stored as `wall + 1 in/2`, and the body is 6 in deep;
 *  - a formula stored before the rule (written while the part was mm) still
 *    builds as before and its field says so; "Read as in" makes it 6 in, and
 *    Ctrl+Z restores the old formula and depth.
 */

const IN = 25.4;

interface Api {
  page: Page;
  token: string;
}

async function call(
  api: Api,
  method: "post" | "put" | "patch",
  url: string,
  data: unknown,
): Promise<Record<string, unknown>> {
  const response = await api.page.request[method](url, {
    data,
    headers: { Authorization: `Bearer ${api.token}` },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()) as Record<string, unknown>;
}

/** A part with wall = 5.5 in and a 20 mm square sketch. */
async function seedPart(
  api: Api,
  unit: "in" | "mm",
): Promise<{ id: string; sketchId: string; version: number }> {
  const part = await call(api, "post", "/api/v1/parts", {
    name: `Bare ${unit}`,
    length_unit: unit,
  });
  const id = String(part.id);
  const table = await call(api, "put", `/api/v1/parts/${id}/parameters`, {
    expected_tree_version: 0,
    parameters: [
      {
        id: crypto.randomUUID(),
        name: "wall",
        expression: "5.5 in",
        unit: "length",
      },
    ],
  });
  const sketch = await createFeature(api.page, api.token, id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: table.tree_version,
  });
  return { id, sketchId: sketch.feature.id, version: sketch.tree_version };
}

/** The body's top, in inches, from the inspector's bounding box. */
async function topInches(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-bbox-max").innerText();
  const numbers = text.replace(/,(?=\d{3})/g, "").match(/-?\d+(?:\.\d+)?/g);
  return Number(numbers?.[2] ?? Number.NaN);
}

async function storedDistance(
  api: Api,
  partId: string,
): Promise<{ formula: string | undefined; mm: number }> {
  const response = await api.page.request.get(
    `/api/v1/parts/${partId}/features`,
    { headers: { Authorization: `Bearer ${api.token}` } },
  );
  const body = (await response.json()) as {
    features: {
      feature: {
        expressions?: Record<string, string>;
        params: { distance_mm?: number };
      };
    }[];
  };
  const extrude = body.features[1]?.feature;
  return {
    formula: extrude?.expressions?.["/distance_mm"],
    mm: extrude?.params.distance_mm ?? Number.NaN,
  };
}

test.describe("bare numbers in an inch part", () => {
  test("wall + 1/2 typed in an Extrude is 6 in deep", async ({ page }) => {
    const account = await seedSession(page);
    const api = { page, token: account.token };
    const part = await seedPart(api, "in");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    await page.getByTestId("new-extrude").click();
    const distance = page.getByTestId("extrude-distance");
    await distance.fill("wall + 1/2");
    await expect(page.getByTestId("extrude-distance-hint")).toHaveText(
      "= 6 in",
    );
    await distance.press("Enter");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => topInches(page), { timeout: 45_000 })
      .toBeCloseTo(6, 3);
    const stored = await storedDistance(api, part.id);
    expect(stored.formula).toBe("wall + 1 in/2");
    expect(stored.mm).toBeCloseTo(6 * IN, 6);

    // Re-opened, the field reads back what was stored, with no warning.
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-distance")).toHaveValue(
      "wall + 1 in/2",
    );
    await expect(page.getByTestId("extrude-distance-bare-unit")).toHaveCount(0);
    await page.getByTestId("extrude-cancel").click();
  });

  test("a stored bare formula is flagged, fixed in one click, and undone", async ({
    page,
  }) => {
    test.slow();
    const account = await seedSession(page);
    const api = { page, token: account.token };
    // Written while the part was mm: stored as typed, read as mm.
    const part = await seedPart(api, "mm");
    const created = await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: part.sketchId },
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
        expressions: { "/distance_mm": "wall + 1/2" },
      },
      expected_tree_version: part.version,
    });
    await call(api, "patch", `/api/v1/parts/${part.id}`, {
      length_unit: "in",
      expected_tree_version: created.tree_version,
    });
    const old = (5.5 * IN + 0.5) / IN;

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => topInches(page), { timeout: 45_000 })
      .toBeCloseTo(old, 3);

    await page.getByTestId("feature-select-1").click();
    const distance = page.getByTestId("extrude-distance");
    await expect(distance).toHaveValue("wall + 1/2");
    const notice = page.getByTestId("extrude-distance-bare-unit");
    await expect(notice).toContainText("1/2 in this formula is read as mm");
    await page.getByTestId("extrude-distance-bare-unit-fix").click();
    await expect(distance).toHaveValue("wall + 1 in/2");
    await expect(page.getByTestId("extrude-distance-hint")).toHaveText(
      "= 6 in",
    );
    await expect(notice).toHaveCount(0);
    await distance.press("Enter");
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect
      .poll(() => topInches(page), { timeout: 45_000 })
      .toBeCloseTo(6, 3);
    expect((await storedDistance(api, part.id)).formula).toBe("wall + 1 in/2");

    await page.keyboard.press("Control+z");
    await expect
      .poll(() => topInches(page), { timeout: 45_000 })
      .toBeCloseTo(old, 3);
    expect((await storedDistance(api, part.id)).formula).toBe("wall + 1/2");
  });
});
