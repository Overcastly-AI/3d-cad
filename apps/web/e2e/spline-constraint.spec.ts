import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Constrainable splines v1.1 (BACKLOG): a spline's fit points are now solver
 * points a constraint can reference (`EntityPointRef { entity, point: "fitN" }`,
 * zero-based). This spec drives the frontend leg end-to-end against the real
 * stack: draw a spline, pick its FIRST fit point, make it coincident to a fixed
 * line endpoint, and prove from the intercepted evaluate payload that the solver
 * MOVED the fit point onto the endpoint — the spline visibly reshapes. The
 * fit-point handle (a keyboard-focusable, testid'd DOM affordance) appears when
 * the spline is engaged. Real gateway + documents + geometry, no mocks.
 */

interface Pt {
  x: number;
  y: number;
}
interface SolvedEntity {
  id: string;
  kind: string;
  points?: Pt[];
  start?: Pt;
  end?: Pt;
}
interface EvaluateBody {
  features: Array<{
    status: string;
    data: {
      kind: string;
      status: string;
      dof: number | null;
      entities: SolvedEntity[];
    } | null;
  }>;
}

/** Bound for solved coordinates (mm) — the fit point lands on the endpoint. */
const SOLVE_TOLERANCE_MM = 1e-3;

function collectEvaluations(page: Page, partId: string): EvaluateBody[] {
  const bodies: EvaluateBody[] = [];
  page.on("response", (response) => {
    if (
      response.url().includes(`/parts/${partId}/evaluate`) &&
      response.request().method() === "POST" &&
      response.status() === 200
    ) {
      void response
        .json()
        .then((body: EvaluateBody) => bodies.push(body))
        .catch(() => undefined);
    }
  });
  return bodies;
}

const latestSketch = (bodies: EvaluateBody[]) =>
  bodies.length > 0 ? (bodies[bodies.length - 1]?.features[0] ?? null) : null;

const splinePoints = (entities: SolvedEntity[]): Pt[] | null =>
  entities.find((e) => e.kind === "spline")?.points ?? null;

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ" = "XY") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/** Plane-mm → screen-px mapper (read the DRO at two points with snap off). */
async function calibratePlane(
  page: Page,
  s1: Pt,
  s2: Pt,
): Promise<(pt: Pt) => Pt> {
  await page.keyboard.press("g"); // snap off for raw readings
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
  ): Promise<Pt> => {
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
  await page.keyboard.press("g"); // snap back on for drawing
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(page: Page, at: (pt: Pt) => Pt, pt: Pt) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/**
 * Shift-click: ADD this pick to the standing selection (FB-14) — a plain click
 * replaces, so a two-point coincident is authored with the modifier held.
 */
async function addPlane(page: Page, at: (pt: Pt) => Pt, pt: Pt) {
  await page.keyboard.down("Shift");
  await clickPlane(page, at, pt);
  await page.keyboard.up("Shift");
}

/**
 * Draw the shared scene: a vertical line whose lower endpoint is FIXED at
 * (30, −10), and an S-curve spline whose FIRST fit point sits far off at
 * (−25, 0). Returns the calibration mapper. Leaves the select tool active.
 */
async function buildLineAndSpline(
  page: Page,
  partId: string,
  at: (pt: Pt) => Pt,
) {
  // The line e1: (30, 25) → (30, −10).
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: 30, y: 25 });
  await clickPlane(page, at, { x: 30, y: -10 });
  await page.keyboard.press("Escape"); // back to select

  // Fix the lower endpoint — the first constraint persists the sketch (POST)
  // and starts the live solve loop, so the fit point has a fixed anchor to
  // land on.
  const created = page.waitForResponse(
    (r) =>
      r.url().includes(`/parts/${partId}/features`) &&
      r.request().method() === "POST",
  );
  await clickPlane(page, at, { x: 30, y: -10 });
  await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
  await page.keyboard.press("x");
  expect((await created).status()).toBe(201);
  await expect(page.getByTestId("glyph-0")).toHaveText("FIX");

  // The spline e2: an open S-curve, fit0 far off at (−25, 0).
  await page.keyboard.press("s");
  for (const fit of [
    { x: -25, y: 0 },
    { x: -8, y: 12 },
    { x: 8, y: -8 },
    { x: 25, y: 6 },
  ]) {
    await clickPlane(page, at, fit);
  }
  await expect(page.getByTestId("spline-count")).toContainText("4 fit points");
  await page.keyboard.press("Enter");
  // Enter commits the spline: the pending set clears, so the fit-point count
  // detaches (the sketch is already bound, so the save cell reads "edits save
  // live" — no entity count to check there).
  await expect(page.getByTestId("spline-count")).toHaveCount(0);
  await page.keyboard.press("Escape"); // spline tool → select
}

test.describe("spline fit-point constraints", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a fit point made coincident to a fixed endpoint moves onto it — the spline reshapes", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spline cam");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 720, y: 560 },
      { x: 960, y: 340 },
    );

    await buildLineAndSpline(page, part.id, at);

    // Pick the spline's first fit point (−25, 0). Selecting it engages the
    // spline, so its fit-point handles wake — the testid'd, focusable affordance.
    await clickPlane(page, at, { x: -25, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await expect(page.getByTestId("fit-handle-e2-0")).toBeVisible();
    await expect(page.getByTestId("fit-handle-e2-0")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // BEFORE: the drawn S-curve, fit0 still off at (−25, 0), handle selected.
    await page.mouse.move(1360, 840); // park the cursor off the sketch
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/spline-constraint-before-desktop.png`,
    });

    // Add the second point — the fixed line endpoint — and make them coincident.
    await addPlane(page, at, { x: 30, y: -10 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    await expect(page.getByTestId("glyph-1")).toHaveText("C");

    // The DOF readout reflects the now-constrained fit point.
    await expect(page.getByTestId("dro-solve")).toContainText(/DOF \d+/);

    // On solve the fit point lands on the fixed endpoint (30, −10): the solver
    // reshaped the spline through its moved first fit point.
    await expect
      .poll(
        () => {
          const sketch = latestSketch(evaluations);
          if (sketch?.data == null) return null;
          const points = splinePoints(sketch.data.entities);
          const fit0 = points?.[0];
          if (fit0 === undefined) return null;
          return {
            onTarget:
              Math.hypot(fit0.x - 30, fit0.y - -10) < SOLVE_TOLERANCE_MM,
            moved: Math.hypot(fit0.x - -25, fit0.y - 0) > 1,
          };
        },
        { timeout: 20_000 },
      )
      .toEqual({ onTarget: true, moved: true });

    // AFTER: the reshaped spline, fit0 pulled onto the fixed endpoint.
    await page.mouse.move(1360, 840);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/spline-constraint-after-desktop.png`,
    });
  });
});

test.describe("spline fit-point constraints — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("fit-point constrain + reshape stays usable; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spline laptop");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 560, y: 500 },
      { x: 800, y: 320 },
    );

    await buildLineAndSpline(page, part.id, at);

    await clickPlane(page, at, { x: -25, y: 0 });
    await expect(page.getByTestId("fit-handle-e2-0")).toBeVisible();
    await addPlane(page, at, { x: 30, y: -10 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    await expect(page.getByTestId("glyph-1")).toHaveText("C");

    await expect
      .poll(
        () => {
          const sketch = latestSketch(evaluations);
          if (sketch?.data == null) return null;
          const fit0 = splinePoints(sketch.data.entities)?.[0];
          return fit0 === undefined
            ? null
            : Math.hypot(fit0.x - 30, fit0.y - -10) < SOLVE_TOLERANCE_MM;
        },
        { timeout: 20_000 },
      )
      .toBe(true);

    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.mouse.move(1100, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/spline-constraint-laptop.png`,
    });
  });
});
