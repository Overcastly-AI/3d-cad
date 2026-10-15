import { expect, test, type Page } from "./fixtures";

import { calibratePlane, enterSketch } from "./planeMap";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * LINE-LENGTH-TAB (docs/reference-parts/bike.md finding 3). Editing the
 * bike's path sketch, a tester drew a line from the origin and typed the end
 * point "426.562 Tab 450.469 Enter". The stored line was (0,0)-(450.469, 0).
 *
 * Reproduced: typed BEFORE the end is clicked, those keys open the X / Y
 * cells and the end lands exactly (both on XY and on an angled datum). Typed
 * AFTER the end is clicked, they go to the drawn line's one-cell LENGTH box:
 * Tab left the box for the next focusable button (the Horizontal glyph), and
 * the second number was then appended to the first ("426.562450.469"), a
 * formula error that named no cause. Retyping the second number there, as a
 * user does, stores the horizontal line at length 450.469.
 *
 * Now, as Fusion's draw boxes do, Tab never leaves the box. In a one-cell box
 * it says the box takes one value, the length, and how to type an end point
 * instead, and Enter refuses a second number typed after it.
 */

interface PersistedLine {
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

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
    throw new Error(`create feature: ${response.status()}`);
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

async function press(page: Page, keys: string): Promise<void> {
  for (const key of keys) await page.keyboard.press(key);
}

async function saveAndReadLines(
  page: Page,
  token: string,
  partId: string,
): Promise<PersistedLine[]> {
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{
      feature: { type: string; params: { entities?: PersistedLine[] } };
    }>;
  };
  const sketches = body.features.filter((f) => f.feature.type === "sketch");
  const entities = sketches[sketches.length - 1]?.feature.params.entities;
  return (entities ?? []).filter((e) => e.kind === "line");
}

test.use({ viewport: { width: 1600, height: 1000 } });

test("x Tab y in a drawn line's length box applies nothing and says the box is the length", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Line length tab");
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at = await calibratePlane(page, { x: 600, y: 400 }, { x: 900, y: 600 });

  // A line from the origin, its end clicked along +X (Horizontal inferred).
  await page.keyboard.press("l");
  const origin = at({ x: 0, y: 0 });
  await page.mouse.move(origin.x + 3, origin.y + 3);
  await page.mouse.move(origin.x, origin.y);
  await page.mouse.click(origin.x, origin.y);
  await page.mouse.move(origin.x + 150, origin.y + 1);
  await page.mouse.move(origin.x + 200, origin.y);
  await page.mouse.click(origin.x + 200, origin.y);
  const box = page.getByTestId("draw-dimensions");
  await expect(box).toHaveAttribute("data-state", "armed");
  const length = page.getByTestId("draw-dimension-length");
  const drawnMm = Number(await length.getAttribute("placeholder"));
  expect(drawnMm).toBeGreaterThan(0);

  await press(page, "426.562");
  await page.keyboard.press("Tab");
  // Tab stays in the box and says what the box is.
  await expect(length).toBeFocused();
  await expect(page.getByTestId("draw-dimensions-error")).toContainText(
    "one value, the length",
  );
  await press(page, "450.469");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-dimensions-error")).toContainText(
    "type X Tab Y before you click",
  );
  await expect(length).toBeFocused();
  await page.screenshot({ path: `${SCREENSHOT_DIR}/line-entry-after.png` });

  // The length typed alone applies.
  await length.fill("426.562");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-dimensions-error")).toHaveCount(0);

  const lines = await saveAndReadLines(page, token, part.id);
  expect(lines, JSON.stringify(lines)).toHaveLength(1);
  expect(lines[0]?.start).toEqual({ x: 0, y: 0 });
  expect(lines[0]?.end?.x).toBeCloseTo(426.562, 6);
  expect(lines[0]?.end?.y).toBeCloseTo(0, 9);
});

test("on an angled datum, x Tab y typed before the click places the end exactly", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Line entry angled");
  const datum = await createFeature(page, token, part.id, {
    name: "Plane1",
    feature: {
      type: "datum",
      version: 1,
      params: {
        kind: "angle",
        line: { kind: "origin_axis", axis: "Y" },
        reference: { kind: "datum_plane", plane: "XY" },
        angle_deg: 46.32,
      },
    },
    expected_tree_version: 0,
  });
  await createFeature(page, token, part.id, {
    name: "Sketch3",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "feature", feature_id: datum.feature.id },
        entities: [],
        constraints: [],
      },
    },
    expected_tree_version: datum.tree_version,
  });
  await page.goto(`/parts/${part.id}`);
  await page.getByTestId("feature-row").last().click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-dro")).toBeVisible();

  await page.keyboard.press("l");
  await page.mouse.move(1000, 250);
  for (const [x, y] of [
    ["0", "0"],
    ["426.562", "450.469"],
  ] as const) {
    await press(page, x);
    await page.keyboard.press("Tab");
    await press(page, y);
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("point-entry")).toHaveCount(0);
  }

  const lines = await saveAndReadLines(page, token, part.id);
  expect(lines, JSON.stringify(lines)).toHaveLength(1);
  expect(lines[0]?.start).toEqual({ x: 0, y: 0 });
  expect(lines[0]?.end).toEqual({ x: 426.562, y: 450.469 });
});
