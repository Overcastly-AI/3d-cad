import { expect, test, type Page } from "./fixtures";

import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * SKETCH-LINE-ANGLE (bike QA rounds 2 and 3: the Line box showed L only).
 *
 * As Fusion's Line does, the drawn line's box shows Length AND Angle. Typing
 * "450 Tab 73 Enter" makes a 450 mm line at 73° to the sketch X axis and
 * records both as dimensions; the angle is an ordinary `angle` constraint to
 * the X axis datum, so the SOLVER holds it (read back from /evaluate, which
 * every export consumes) and editing the 73 rotates the line. A segment that
 * continues a chain measures its angle from the segment before it.
 */

interface Point {
  x: number;
  y: number;
}
interface StoredLine {
  id: string;
  kind: string;
  start?: Point;
  end?: Point;
}
interface StoredSketch {
  entities: StoredLine[];
  constraints: Array<Record<string, unknown>>;
}

/** Below the solver's own satisfaction bound (1e-7), in degrees and mm. */
const EXACT = 1e-7;

const deg = (rad: number) => (rad * 180) / Math.PI;

async function press(page: Page, keys: string): Promise<void> {
  for (const key of keys) await page.keyboard.press(key);
}

async function click(page: Page, px: Point): Promise<void> {
  await page.mouse.move(px.x + 2, px.y + 2);
  await page.mouse.move(px.x, px.y);
  await page.mouse.click(px.x, px.y);
}

async function save(page: Page): Promise<void> {
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
}

async function stored(
  page: Page,
  token: string,
  partId: string,
): Promise<StoredSketch> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = (await response.json()) as {
    features: Array<{ feature: { params: Partial<StoredSketch> } }>;
  };
  const params = body.features[0]?.feature.params ?? {};
  return {
    entities: params.entities ?? [],
    constraints: params.constraints ?? [],
  };
}

/** The part's sketch as the SOLVER returns it (the geometry exports read). */
async function solved(
  page: Page,
  token: string,
  partId: string,
): Promise<{ status: string; lines: Map<string, StoredLine> }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    features: Array<{
      data: { status: string; entities: StoredLine[] } | null;
    }>;
  };
  const data = body.features[0]?.data;
  if (data == null) throw new Error("no solved sketch");
  return {
    status: data.status,
    lines: new Map(
      data.entities.filter((e) => e.kind === "line").map((e) => [e.id, e]),
    ),
  };
}

function lineOf(lines: Map<string, StoredLine>, id: string) {
  const line = lines.get(id);
  if (line?.start === undefined || line.end === undefined) {
    throw new Error(`no line ${id}`);
  }
  return {
    start: line.start,
    end: line.end,
    dx: line.end.x - line.start.x,
    dy: line.end.y - line.start.y,
  };
}

async function openSketch(page: Page, name: string) {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at: PlaneMapper = await calibratePlane(
    page,
    { x: 600, y: 400 },
    { x: 900, y: 600 },
  );
  return { token, partId: part.id, at };
}

test.use({ viewport: { width: 1600, height: 1000 } });

test("450 Tab 73 Enter draws a 450 mm line at 73° to X, dimensioned, and editing the 73 rotates it", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const { token, partId, at } = await openSketch(page, "Line angle");

  await page.keyboard.press("l");
  const origin = at({ x: 0, y: 0 });
  await click(page, origin);
  // The rubber band already reads both: Length and Angle.
  await page.mouse.move(origin.x + 120, origin.y - 150);
  await page.mouse.move(origin.x + 160, origin.y - 200);
  const box = page.getByTestId("draw-dimensions");
  await expect(box).toHaveAttribute("data-state", "live");
  await expect(box).toContainText("∠");
  await page.mouse.click(origin.x + 160, origin.y - 200);
  await expect(box).toHaveAttribute("data-state", "armed");
  const length = page.getByTestId("draw-dimension-length");
  const angle = page.getByTestId("draw-dimension-angle");
  await expect(angle).toHaveAccessibleName("Angle in degrees");
  // The as-drawn angle is the placeholder: about 51° (160 right, 200 up).
  const drawn = Number(await angle.getAttribute("placeholder"));
  expect(drawn).toBeGreaterThan(45);
  expect(drawn).toBeLessThan(57);

  await press(page, "450");
  await page.keyboard.press("Tab");
  await expect(angle).toBeFocused();
  await press(page, "73");
  await expect(length).toHaveValue("450");
  await expect(angle).toHaveValue("73");
  await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-line-angle.png` });
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-dimensions-error")).toHaveCount(0);

  // Editing the 73 rotates the line (the glyph opens the dimension box).
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  const glyph = page.locator('[data-kind="angle"]');
  await expect(glyph).toHaveCount(1);
  await expect(glyph).toHaveText("73°");
  await glyph.click();
  const cell = page.getByTestId("dimension-input");
  await expect(cell).toBeVisible();
  await cell.fill("60");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
  await expect(glyph).toHaveText("60°", { timeout: 15_000 });

  await save(page);
  const sketch = await stored(page, token, partId);
  expect(sketch.constraints).toContainEqual(
    expect.objectContaining({
      kind: "angle",
      a: "x-axis",
      b: "e1",
      value_deg: 60,
    }),
  );
  expect(sketch.constraints).toContainEqual(
    expect.objectContaining({ kind: "distance", entity: "e1", value_mm: 450 }),
  );
  // The inferred Horizontal/Vertical never fights the typed angle.
  expect(
    sketch.constraints.filter(
      (c) =>
        (c.kind === "horizontal" || c.kind === "vertical") && c.entity === "e1",
    ),
  ).toEqual([]);

  // The solver holds it exactly: 450 long, 60° above +X, from the origin.
  const solve = await solved(page, token, partId);
  expect(solve.status).toBe("converged");
  const e1 = lineOf(solve.lines, "e1");
  expect(Math.abs(e1.start.x)).toBeLessThan(EXACT);
  expect(Math.abs(e1.start.y)).toBeLessThan(EXACT);
  expect(Math.abs(Math.hypot(e1.dx, e1.dy) - 450)).toBeLessThan(EXACT);
  expect(Math.abs(deg(Math.atan2(e1.dy, e1.dx)) - 60)).toBeLessThan(EXACT);
});

test("a chained segment's angle is to the segment before it", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const { token, partId, at } = await openSketch(page, "Chained angle");

  await page.keyboard.press("l");
  const a = at({ x: 0, y: 0 });
  await click(page, a);
  await click(page, { x: a.x + 200, y: a.y });
  await click(page, { x: a.x + 200, y: a.y - 150 });
  const angle = page.getByTestId("draw-dimension-angle");
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  // Drawn square off the first segment: the joint reads 90.
  expect(Number(await angle.getAttribute("placeholder"))).toBeCloseTo(90, 0);
  await angle.click();
  await press(page, "120");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-dimensions-error")).toHaveCount(0);

  await save(page);
  const sketch = await stored(page, token, partId);
  expect(sketch.constraints).toContainEqual(
    expect.objectContaining({
      kind: "angle",
      a: "e1",
      b: "e2",
      value_deg: 120,
    }),
  );
  const solve = await solved(page, token, partId);
  // Solved, not fully defined: the two lengths are still free.
  expect(solve.status).toBe("underconstrained");
  const e1 = lineOf(solve.lines, "e1");
  const e2 = lineOf(solve.lines, "e2");
  // Interior angle at the joint, between e1 back along itself and e2.
  const interior = deg(
    Math.acos(
      (-e1.dx * e2.dx - e1.dy * e2.dy) /
        (Math.hypot(e1.dx, e1.dy) * Math.hypot(e2.dx, e2.dy)),
    ),
  );
  expect(Math.abs(interior - 120)).toBeLessThan(EXACT);
  // It leaned forward, on the side it was drawn (up).
  expect(e2.dy).toBeGreaterThan(0);
  expect(e2.dx).toBeGreaterThan(0);
});
