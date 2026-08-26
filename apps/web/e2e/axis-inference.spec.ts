import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

/**
 * SNAP-5 — a line drawn along an axis SAYS so, through the real solver.
 *
 * THE DEFECT, in the user's terms. `shapeRigidity` gives a RECTANGLE two
 * horizontals and two verticals, because a rectangle is axis-aligned by
 * construction. A line drawn line-by-line — which is how anything that is not
 * a rectangle gets drawn — carried no axis constraint at all, so a profile
 * that LOOKED orthogonal solved with every edge still free to rotate, and
 * every later edit paid for the slack. Measured on the four-edge box this spec
 * draws, against the same planegcs the geometry service runs: DOF 7 before,
 * DOF 3 after, with one driving dimension in both cases.
 *
 * WHY A SPEC AND NOT ONLY UNIT TESTS. `store.test.ts` proves the constraints
 * reach the buffer; only this proves they reach the SERVER, survive the solve
 * and come back in the DOF the DRO reports. An inference the payload never
 * carries would pass every unit test in the repo.
 *
 * WHAT ELSE IT PINS, because an inference that fires on geometry the user
 * deliberately drew at an angle is a worse defect than the one being fixed
 * (RECT-1 in reverse): the sloped line in the second test gets NOTHING, and
 * the count of horizontal glyphs does not move when it is drawn.
 *
 * Checked by mutation, not assumed: with the `axis` term dropped from the
 * store's `placeAt`, the first test fails at the DOF readout —
 * `"DOF 3 · UNDER-CONSTRAINED"` becomes `"DOF 7 · UNDER-CONSTRAINED"` — and
 * the second fails at the glyph count.
 */

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

interface Plane2D {
  x: number;
  y: number;
}

interface PlaneMap {
  at: (pt: Plane2D) => Plane2D;
  /** Plane mm per screen pixel — the scale the snap radius is quoted in. */
  mmPerPx: number;
}

/**
 * Build a plane-mm → screen-px mapper by reading the DRO at two screen points
 * with the grid off, exactly as `constraints.spec.ts` and
 * `rect-rigidity.spec.ts` do. The scale comes back with it because SNAP-5's
 * deviation rule is quoted in SCREEN pixels (the snap radius), so a spec that
 * wants to draw a line a known fraction of that radius off-axis has to know
 * what a pixel is worth here.
 */
async function calibratePlane(
  page: Page,
  s1: Plane2D,
  s2: Plane2D,
): Promise<PlaneMap> {
  await page.keyboard.press("g"); // grid off for raw readings
  {
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
  }
  const read = async (
    sx: number,
    sy: number,
    distinctFromX?: number,
  ): Promise<Plane2D> => {
    await page.mouse.move(sx, sy);
    await expect
      .poll(async () => {
        const value = Number.parseFloat(
          await page.getByTestId("dro-x").innerText(),
        );
        return (
          Number.isFinite(value) &&
          (distinctFromX === undefined ||
            Math.abs(value - distinctFromX) > 1e-9)
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
  await page.keyboard.press("g"); // grid back on
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return {
    at: (pt) => ({
      x: s1.x + (pt.x - p1.x) * kx,
      y: s1.y + (pt.y - p1.y) * ky,
    }),
    mmPerPx: 1 / Math.abs(kx),
  };
}

const clickPlane = async (page: Page, map: PlaneMap, pt: Plane2D) => {
  const px = map.at(pt);
  await page.mouse.click(px.x, px.y);
};

const glyph = (page: Page, kind: string) =>
  page.locator(`[data-testid^="glyph-"][data-kind="${kind}"]`);

/**
 * Draw the closed outline one two-click line at a time — the ordinary
 * line-by-line gesture, with the tool re-armed for each edge exactly as a user
 * does it (the line tool completes on the second click).
 */
async function drawOutline(page: Page, map: PlaneMap, points: Plane2D[]) {
  for (let i = 0; i < points.length; i += 1) {
    const from = points[i] as Plane2D;
    const to = points[(i + 1) % points.length] as Plane2D;
    await page.keyboard.press("l");
    await clickPlane(page, map, from);
    await clickPlane(page, map, to);
    // Escape ends the command and takes the size cells with it (nothing
    // typed — the "I'll dimension it later" path). It is also what keeps the
    // NEXT edge's first click on the canvas: the cells are drawn at the line's
    // end, which is exactly where the next edge starts.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
  }
}

test.describe("SNAP-5 — line-by-line drawing states its axes", () => {
  test("an axis-aligned profile reaches the solver at the DOF it looks like", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Axis inference");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const map = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // A 40 x 30 box, four separate lines. Placed clear of the origin so the
    // frame's own grounding constraint (SNAP-2) does not enter the DOF count
    // this test is about.
    await drawOutline(page, map, [
      { x: 20, y: 20 },
      { x: 60, y: 20 },
      { x: 60, y: 50 },
      { x: 20, y: 50 },
    ]);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // Two horizontals and two verticals, on geometry no rectangle tool touched.
    await expect(glyph(page, "horizontal")).toHaveCount(2);
    await expect(glyph(page, "vertical")).toHaveCount(2);
    expect(await glyph(page, "coincident").count()).toBeGreaterThanOrEqual(4);

    // One driving dimension binds the sketch, so it persists and solves. The
    // DOF is the whole claim: 4 lines = 16 unknowns, less 4 joins (8), the 4
    // inferred axes (4) and the dimension (1) = 3 — where the same twelve
    // clicks used to leave 7. Measured against planegcs directly before it was
    // asserted here.
    await clickPlane(page, map, { x: 40, y: 20 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("d");
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await input.fill("40");
    await input.press("Enter");

    await expect(page.getByTestId("dro-solve")).toContainText("DOF 3", {
      timeout: 30_000,
    });
  });

  test("a line drawn at an angle keeps its angle, and says nothing", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Sloped line");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const map = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // The NEAR miss the inference exists for, with the grid off so the aim is
    // continuous: half the snap radius (12 px) of rise over a run long enough
    // to keep it inside the 3-degree ceiling. Both numbers are derived from
    // the measured scale rather than guessed at this zoom.
    await page.keyboard.press("g");
    const riseMm = 6 * map.mmPerPx;
    await page.keyboard.press("l");
    await clickPlane(page, map, { x: 20, y: 20 });
    await clickPlane(page, map, { x: 20 + riseMm * 40, y: 20 + riseMm });
    await expect(glyph(page, "horizontal")).toHaveCount(1);
    // …and it SAYS so, rather than applying a constraint the user cannot see.
    await expect(page.getByTestId("constraint-hint")).toContainText(
      "Horizontal inferred",
    );

    // The slope the user clearly meant: 20 degrees off horizontal. Nothing is
    // inferred for it — the horizontal count does not move — and no vertical
    // appears either.
    await page.keyboard.press("Escape");
    await page.keyboard.press("l");
    await clickPlane(page, map, { x: 20, y: 40 });
    await clickPlane(page, map, { x: 60, y: 54.6 });
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
    await expect(glyph(page, "horizontal")).toHaveCount(1);
    await expect(glyph(page, "vertical")).toHaveCount(0);
    await expect(page.getByTestId("constraint-hint")).toHaveCount(0);
  });
});
