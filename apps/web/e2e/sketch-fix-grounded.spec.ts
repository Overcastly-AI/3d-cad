import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * SNAP-4: Fix on a point the draw already grounded is refused.
 *
 * Start a line on the origin and SNAP-3 authors the coincident that grounds its
 * start point. Pressing X (Fix) on that point used to add a second pin, and the
 * sketch then read OVER-CONSTRAINED over a constraint the user never meant to
 * duplicate. SolidWorks and Fusion refuse a redundant relation instead of
 * authoring it, and so does Loft now: the verb answers "Already grounded on the
 * Origin." and authors nothing, while Fix on a free point still pins it.
 *
 * Driven with the user's own gestures (mouse clicks at coordinates read off the
 * live DRO, real key presses), and checked against the persisted params so the
 * refusal is shown to author nothing rather than merely to say so.
 */

interface Point {
  x: number;
  y: number;
}

type Mapper = (pt: Point) => Point;

interface Ref {
  entity: string;
  point: string;
}

interface ConstraintRow {
  kind: string;
  point?: Ref;
  a?: Ref;
  b?: Ref;
}

async function enterSketch(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm to screen-px, read off the DRO at two points. The grid is turned
 * OFF first so the first click can only land on zero through the origin
 * magnet, which is what authors the coincident under test.
 */
async function calibratePlane(
  page: Page,
  s1: Point,
  s2: Point,
): Promise<Mapper> {
  await page.keyboard.press("g");
  // The camera eases into the plane-normal pose; wait until two consecutive
  // DRO readings of the same pixel agree.
  let last: number | null = null;
  await expect
    .poll(
      async () => {
        await page.mouse.move(s1.x + 2, s1.y);
        await page.mouse.move(s1.x, s1.y);
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        const stable =
          last !== null && Number.isFinite(value) && value === last;
        last = value;
        return stable;
      },
      { timeout: 15_000 },
    )
    .toBe(true);
  const read = async (
    sx: number,
    sy: number,
    notX?: number,
  ): Promise<Point> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (notX === undefined || Math.abs(value - notX) > 1e-9)
        );
      })
      .toBe(true);
    return {
      x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
      y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
    };
  };
  const p1 = await read(s1.x, s1.y);
  const p2 = await read(s2.x, s2.y, p1.x);
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(page: Page, at: Mapper, pt: Point): Promise<void> {
  const px = at(pt);
  await page.mouse.move(px.x, px.y);
  await page.mouse.click(px.x, px.y);
}

async function sketchConstraints(
  page: Page,
  token: string,
  partId: string,
): Promise<ConstraintRow[]> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    features: { feature: { type: string; params: unknown } }[];
  };
  const sketch = body.features.find((row) => row.feature.type === "sketch");
  if (sketch === undefined) throw new Error("no sketch feature on the part");
  return (sketch.feature.params as { constraints: ConstraintRow[] })
    .constraints;
}

const glyphsOf = (page: Page, kind: string) =>
  page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);

test("SNAP-4: Fix on a point grounded on the origin is refused, not over-constrained", async ({
  page,
}) => {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Grounded fix");
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page);
  const at = await calibratePlane(
    page,
    { x: 700, y: 620 },
    { x: 1000, y: 420 },
  );

  // A line from the origin. Aimed a few tenths off zero with the grid off, so
  // only the origin snap can land it, and at ~37 deg so no H/V is inferred.
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: 0.3, y: -0.2 });
  await clickPlane(page, at, { x: 40.4, y: 30.4 });
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape"); // and leave the Line tool
  await expect(glyphsOf(page, "coincident")).toHaveCount(1);

  // Fix on that start point.
  await clickPlane(page, at, { x: 0, y: 0 });
  await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
  await page.keyboard.press("x");

  await expect(page.getByTestId("constraint-hint")).toHaveText(
    "Already grounded on the Origin.",
  );
  await expect(glyphsOf(page, "fixed")).toHaveCount(0);
  // The keystroke still binds the sketch, so the solve runs and answers. Wait
  // for the whole cell: asserting only the absence of the banner would pass in
  // the debounce gap before the reply.
  await expect(page.getByTestId("dro-solve")).toHaveText(
    "DOF 2 · UNDER-CONSTRAINED",
    { timeout: 30_000 },
  );
  await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

  // Fix on a point that is not grounded still works, and fully defines the line.
  await page.keyboard.press("Escape");
  await clickPlane(page, at, { x: 40.4, y: 30.4 });
  await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
  await page.keyboard.press("x");
  await expect(glyphsOf(page, "fixed")).toHaveCount(1);
  await expect(page.getByTestId("dro-solve")).toHaveText("DOF 0 · CONVERGED", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });

  // Exactly one user pin (the far end), the frame's own pin, and the join the
  // draw recorded: the refusal did not quietly replace it.
  const constraints = await sketchConstraints(page, token, part.id);
  const pins = constraints.filter((c) => c.kind === "fixed");
  expect(pins.filter((c) => c.point?.entity !== "origin")).toEqual([
    { kind: "fixed", point: { entity: "e1", point: "end" } },
  ]);
  expect(pins.filter((c) => c.point?.entity === "origin")).toHaveLength(1);
  expect(
    constraints.filter(
      (c) =>
        c.kind === "coincident" &&
        [c.a?.entity, c.b?.entity].includes("origin") &&
        [c.a?.entity, c.b?.entity].includes("e1"),
    ),
  ).toHaveLength(1);
});
