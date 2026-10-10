import { expect, test, type Locator, type Page } from "./fixtures";

import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import {
  createPartViaApi,
  expectSketchEntities,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * QA-RECT-BOX-NAMES + QA-CIRCLE-DIAMETER-BOX, against the real stack.
 *
 * The QA pass typed `W` into a rectangle's draw-time size box and got nothing
 * (Enter applied no dimension, said nothing); typing `W` while the rectangle
 * was still being dragged switched to the Point tool and dropped it; and the
 * circle's box asked for a radius where Fusion's centre-diameter circle asks
 * for a diameter. Fusion's draw boxes take a parameter and own the keyboard
 * while the shape is being dragged, so:
 *
 *  - parameters W = 80, H = 50, D = 24;
 *  - a rectangle dragged out and typed `W` Tab `H` Enter MID-DRAG is placed
 *    80 x 50 with dimensions driven by W and H, and `W` never reaches the
 *    tool shortcuts;
 *  - a circle typed `Q` says on its box that Q is not defined and applies
 *    nothing; retyped `D` it gets a Ø24 dimension driven by D;
 *  - W = 100 in the Parameters panel re-drives the rectangle to 100 wide.
 */

interface SolvedEntity {
  id: string;
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
  radius?: number;
}

async function putParameters(
  page: Page,
  token: string,
  partId: string,
  rows: Array<[string, string]>,
): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const url = `/api/v1/parts/${partId}/parameters`;
  const current = await page.request.get(url, { headers });
  expect(current.ok()).toBe(true);
  const { tree_version } = (await current.json()) as { tree_version: number };
  const response = await page.request.put(url, {
    headers,
    data: {
      expected_tree_version: tree_version,
      parameters: rows.map(([name, expression]) => ({
        id: crypto.randomUUID(),
        name,
        expression,
        unit: "length",
        comment: "",
      })),
    },
  });
  expect(response.ok(), await response.text()).toBe(true);
}

/** The first sketch's solved entities, from a fresh evaluate. */
async function solvedEntities(
  page: Page,
  token: string,
  partId: string,
): Promise<SolvedEntity[]> {
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    features: Array<{ data: { entities?: SolvedEntity[] } | null }>;
  };
  return body.features[0]?.data?.entities ?? [];
}

const lengthOf = (entities: SolvedEntity[], id: string): number | null => {
  const line = entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);
};

/** Press the first point of a gesture and pull the rubber band out. */
async function startDrag(
  page: Page,
  at: PlaneMapper,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  const a = at(from);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.waitForTimeout(90);
  await page.mouse.up();
  const b = at(to);
  await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2);
  await page.mouse.move(b.x, b.y);
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "live",
  );
}

function glyphs(page: Page, kind: string): Locator {
  return page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);
}

test("draw boxes take parameters: W Tab H mid-drag, a Ø typed as D, and the shape follows the table", async ({
  page,
}) => {
  test.slow();
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Box names");
  await putParameters(page, account.token, part.id, [
    ["W", "80"],
    ["H", "50"],
    ["D", "24"],
  ]);
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at = await calibratePlane(
    page,
    { x: 700, y: 600 },
    { x: 1000, y: 400 },
  );

  // --- the rectangle, sized by name while it is still being dragged ---------
  await page.keyboard.press("r");
  const rectTool = page.getByTestId("tool-rect");
  await expect(rectTool).toHaveAttribute("aria-pressed", "true");
  await startDrag(page, at, { x: 10, y: 10 }, { x: 40, y: 30 });

  await page.keyboard.press("W");
  // The size box took it: the tool did not change, and the rubber band lives.
  await expect(rectTool).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("tool-point")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "typing",
  );
  const width = page.getByTestId("draw-dimension-width");
  await expect(width).toHaveValue("W");
  await expect(width).toBeFocused();
  await expect(page.getByTestId("draw-dimension-width-hint")).toHaveText(
    "= 80 mm",
  );
  await page.keyboard.press("Tab");
  await page.keyboard.type("H");
  await expect(page.getByTestId("draw-dimension-height")).toHaveValue("H");
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sketch-draw-box-formulas-typing.png`,
  });
  await page.keyboard.press("Enter");

  await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  await expectSketchEntities(page, 4);
  await expect
    .poll(async () =>
      (await glyphs(page, "distance").allInnerTexts())
        .map((text) => text.trim())
        .sort(),
    )
    .toEqual(["50", "80"]);
  await expect(glyphs(page, "distance").first()).toHaveAttribute(
    "data-expression",
    /^[WH]$/,
  );
  await expect(
    page.locator('[data-testid^="glyph-"][data-expression="W"]'),
  ).toHaveText("80");
  await expect(
    page.locator('[data-testid^="glyph-"][data-expression="H"]'),
  ).toHaveText("50");

  // --- the circle: a diameter box, an unknown name refused on it ------------
  await page.keyboard.press("c");
  await expect(page.getByTestId("tool-circle")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await startDrag(page, at, { x: -30, y: 20 }, { x: -22, y: 20 });
  await expect(page.getByTestId("draw-dimension-diameter")).toHaveCount(0);
  await page.keyboard.press("Q");
  const diameter = page.getByTestId("draw-dimension-diameter");
  await expect(diameter).toHaveValue("Q");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-dimensions-error")).toContainText("Q");
  await expect(diameter).toHaveAttribute("aria-invalid", "true");
  // Nothing was placed: the circle is still being dragged, its box still up.
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "typing",
  );
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/sketch-draw-box-formulas-unknown.png`,
  });
  await page.keyboard.press("Backspace");
  await page.keyboard.type("D");
  await expect(page.getByTestId("draw-dimensions-error")).toHaveCount(0);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  const ring = page.locator('[data-testid^="glyph-"][data-kind="diameter"]');
  await expect(ring).toHaveText("⌀24", { timeout: 30_000 });
  await expect(ring).toHaveAttribute("data-expression", "D");

  // --- save, then W = 100 in the table: the rectangle follows ---------------
  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  let entities = await solvedEntities(page, account.token, part.id);
  expect(lengthOf(entities, "e1")).toBeCloseTo(80, 6);
  expect(lengthOf(entities, "e2")).toBeCloseTo(50, 6);
  expect(entities.find((e) => e.id === "e5")?.radius).toBeCloseTo(12, 6);

  await page.getByTestId("parameters-tool").click();
  const panel = page.getByTestId("parameters-panel");
  await expect(panel).toBeVisible();
  const cell = panel
    .locator('[data-testid="parameter-row"][data-name="W"]')
    .getByTestId("parameter-expression");
  await cell.fill("100");
  await cell.press("Enter");
  await expect(panel.getByTestId("parameters-saving")).toBeHidden({
    timeout: 30_000,
  });
  await expect
    .poll(
      async () => {
        entities = await solvedEntities(page, account.token, part.id);
        return lengthOf(entities, "e1");
      },
      { timeout: 30_000 },
    )
    .toBeCloseTo(100, 6);
  expect(lengthOf(entities, "e2")).toBeCloseTo(50, 6);
});
