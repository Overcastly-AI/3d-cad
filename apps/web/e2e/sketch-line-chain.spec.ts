import { expect, test, type Page } from "./fixtures";

import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * LINE-CHAIN — the Line tool chains, as Fusion's and SolidWorks' do.
 *
 * The 2026-09-30 reference run built a pulley hub whose 12-segment section
 * took 24 clicks: every line started from scratch. Now each click ends one
 * segment and starts the next at that end, every joint carries a coincident,
 * and a click on the chain's first point closes the loop. Escape ends an open
 * chain with the tool still armed; a second Escape drops it. A typed point
 * (and a typed length) continues the chain.
 *
 * Every step is real browser input at calibrated millimetre coordinates; the
 * stored params are read back from the API, because the pixels of a chained
 * and an unchained profile are the same.
 */

interface Point {
  x: number;
  y: number;
}

interface Ref {
  entity: string;
  point: string;
}

interface StoredSketch {
  entities: Array<{ id: string; kind: string; start?: Point; end?: Point }>;
  constraints: Array<{ kind: string; a?: Ref | string; b?: Ref | string }>;
}

/**
 * The hub's half-section on XZ (u = X, v = Z): bore at 10, hub to 60, a web
 * 60..80 from v 8 to 32, rim to 100, 40 deep. Twelve vertices, twelve segments.
 */
const HUB: readonly Point[] = [
  { x: 10, y: 0 },
  { x: 60, y: 0 },
  { x: 60, y: 8 },
  { x: 80, y: 8 },
  { x: 80, y: 0 },
  { x: 100, y: 0 },
  { x: 100, y: 40 },
  { x: 80, y: 40 },
  { x: 80, y: 32 },
  { x: 60, y: 32 },
  { x: 60, y: 40 },
  { x: 10, y: 40 },
];

/** Pappus: 2 pi x (first moment of the section about the Z axis). */
const HUB_VOLUME =
  2 *
  Math.PI *
  (50 * 40 * 35 + // hub, 10..60 x 0..40
    20 * 24 * 70 + // web, 60..80 x 8..32
    20 * 40 * 90); // rim, 80..100 x 0..40

async function openPart(page: Page, name: string) {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  return { token, partId: part.id };
}

async function click(page: Page, at: PlaneMapper, pt: Point): Promise<void> {
  const px = at(pt);
  await page.mouse.move(px.x + 1, px.y + 1);
  await page.mouse.move(px.x, px.y);
  await page.mouse.click(px.x, px.y);
}

/** One key at a time, as a hand types a number it already knows. */
async function type(page: Page, text: string): Promise<void> {
  for (const key of text) await page.keyboard.press(key);
}

async function saveSketch(page: Page): Promise<void> {
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
}

async function storedSketch(
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

/** Each coincident as "e1.end=e2.start" (sides sorted). */
const joints = (sketch: StoredSketch): string[] =>
  sketch.constraints
    .filter((c) => c.kind === "coincident")
    .map((c) =>
      [c.a, c.b]
        .map((ref) =>
          typeof ref === "object" ? `${ref.entity}.${ref.point}` : "?",
        )
        .sort()
        .join("="),
    )
    .sort();

/** The joints of a closed chain of `n` segments e1..en, sorted like `joints`. */
const closedJoints = (n: number): string[] =>
  Array.from({ length: n }, (_, i) =>
    [`e${String(i + 1)}.end`, `e${String(((i + 1) % n) + 1)}.start`]
      .sort()
      .join("="),
  ).sort();

test.use({ viewport: { width: 1280, height: 800 } });

test("the hub's 12-segment section is 13 clicks, closes on its start, and revolves", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const { token, partId } = await openPart(page, "Chained hub");
  await enterSketch(page, "XZ");
  const at = await calibratePlane(page, { x: 400, y: 560 }, { x: 900, y: 300 });

  await page.keyboard.press("l");
  for (const pt of HUB) await click(page, at, pt);
  await expect(page.getByTestId("sketch-save")).toContainText("11 entities");
  // The thirteenth click, on the first point, closes the section.
  await click(page, at, HUB[0] as Point);
  await expect(page.getByTestId("sketch-save")).toContainText("12 entities");
  // The chain is over and the tool still armed: the next click starts afresh
  // rather than drawing a thirteenth segment from the start point.
  await expect(page.getByTestId("tool-line")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.move(at({ x: 130, y: 60 }).x, at({ x: 130, y: 60 }).y);
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/line-chain-hub-section-1280.png`,
  });

  await saveSketch(page);
  const sketch = await storedSketch(page, token, partId);
  const lines = sketch.entities.filter((e) => e.kind === "line");
  expect(lines, JSON.stringify(lines)).toHaveLength(12);
  // Each segment starts exactly where the last ended, the loop included.
  lines.forEach((line, i) => {
    expect(line.start).toEqual(HUB[i]);
    expect(line.end).toEqual(HUB[(i + 1) % HUB.length]);
  });
  expect(joints(sketch)).toEqual(closedJoints(12));

  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  const revolve = page.getByTestId("new-revolve");
  await expect(revolve).toBeEnabled({ timeout: 30_000 });
  await revolve.click();
  await expect(page.getByTestId("revolve-axis")).toHaveValue("origin:Z");
  await page.getByTestId("revolve-angle").press("Enter");
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("body-inspector")).toBeVisible();
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
  const text = await page.getByTestId("prop-volume").innerText();
  const volume = Number.parseFloat(
    (text.match(/[\d,]+(?:\.\d+)?/)?.[0] ?? "NaN").replace(/,/g, ""),
  );
  expect(volume).toBeGreaterThan(HUB_VOLUME * 0.995);
  expect(volume).toBeLessThan(HUB_VOLUME * 1.005);
});

test("clicks, a typed length and a typed point make one chain, closed by a click", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token, partId } = await openPart(page, "Mixed chain");
  await enterSketch(page, "XY");
  const at = await calibratePlane(page, { x: 400, y: 560 }, { x: 900, y: 300 });

  await page.keyboard.press("l");
  await click(page, at, { x: 10, y: 10 });
  await click(page, at, { x: 35, y: 10 });
  // The clicked segment's length cell takes the typing (FB-16)...
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  await type(page, "30");
  await page.keyboard.press("Enter");
  // ...and the chain goes on from where that end now is, so the typed point
  // is the second segment's end.
  await type(page, "40");
  await page.keyboard.press("Tab");
  await type(page, "30");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("point-entry")).toHaveCount(0);
  // (No entity count from here: the typed length bound the sketch, and a
  // bound sketch's save chip says "edits save live". The API read says it.)
  await click(page, at, { x: 10, y: 30 });
  await click(page, at, { x: 10, y: 10 }); // the start: closes the loop

  await saveSketch(page);
  const sketch = await storedSketch(page, token, partId);
  const lines = sketch.entities.filter((e) => e.kind === "line");
  expect(
    lines.map((l) => [l.start, l.end]),
    JSON.stringify(lines),
  ).toEqual([
    [
      { x: 10, y: 10 },
      { x: 40, y: 10 },
    ],
    [
      { x: 40, y: 10 },
      { x: 40, y: 30 },
    ],
    [
      { x: 40, y: 30 },
      { x: 10, y: 30 },
    ],
    [
      { x: 10, y: 30 },
      { x: 10, y: 10 },
    ],
  ]);
  expect(joints(sketch)).toEqual(closedJoints(4));
});

test("Escape ends the chain with the Line tool armed; a second Escape leaves it", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token, partId } = await openPart(page, "Escaped chain");
  await enterSketch(page, "XY");
  const at = await calibratePlane(page, { x: 400, y: 560 }, { x: 900, y: 300 });
  const lineTool = page.getByTestId("tool-line");

  await page.keyboard.press("l");
  await click(page, at, { x: 10, y: 10 });
  await click(page, at, { x: 40, y: 10 });
  await click(page, at, { x: 40, y: 30 });
  await page.keyboard.press("Escape");
  await expect(lineTool).toHaveAttribute("aria-pressed", "true");
  // A new chain: its first click is a fresh start, joined to nothing.
  await click(page, at, { x: 60, y: 10 });
  await click(page, at, { x: 60, y: 30 });
  await expect(page.getByTestId("sketch-save")).toContainText("3 entities");
  await page.keyboard.press("Escape");
  await expect(lineTool).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await expect(lineTool).toHaveAttribute("aria-pressed", "false");

  await saveSketch(page);
  const sketch = await storedSketch(page, token, partId);
  const lines = sketch.entities.filter((e) => e.kind === "line");
  expect(lines[2], JSON.stringify(lines)).toMatchObject({
    start: { x: 60, y: 10 },
    end: { x: 60, y: 30 },
  });
  expect(joints(sketch)).toEqual(["e1.end=e2.start"]);
});
