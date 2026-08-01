import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Sketch dimension EXPRESSIONS + driving/driven (BACKLOG: dimension
 * expressions). The design-doc worked example driven end-to-end against the
 * real stack:
 *
 *  1. `width = 20` (a NAMED driving dimension) and `height = width/2` (an
 *     EXPRESSION dimension) — assert the height solves to **10** in the readout
 *     and in the intercepted evaluate payload.
 *  2. A DRIVEN (reference) dimension — measured, excluded from the solver, so it
 *     can't over-constrain; editing the geometry updates its parenthesised
 *     readout while the sketch keeps solving.
 *  3. A bad expression surfaces the `sketch_invalid` diagnostic (never silent).
 */

const SOLVE_TOLERANCE_MM = 1e-3;

interface SolvedPoint {
  x: number;
  y: number;
}
interface SolvedEntity {
  id: string;
  kind: string;
  start?: SolvedPoint;
  end?: SolvedPoint;
}
interface SolvedDimension {
  constraint_index: number;
  name: string | null;
  driving: boolean;
  value_mm: number;
  expression?: string | null;
}
interface EvaluateBody {
  features: Array<{
    feature_id: string;
    status: string;
    error: { code: string; message: string } | null;
    data: {
      kind: string;
      status: string;
      entities: SolvedEntity[];
      dimensions?: SolvedDimension[];
    } | null;
  }>;
}

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

function lineLength(entities: SolvedEntity[], id: string): number | null {
  const line = entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/** Plane-mm → screen-px mapper, read from the DRO with snap off (see constraints.spec). */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  await page.keyboard.press("g");
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
  ): Promise<{ x: number; y: number }> => {
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
  await page.keyboard.press("g");
  const kx = (s2.x - s1.x) / (p2.x - p1.x);
  const ky = (s2.y - s1.y) / (p2.y - p1.y);
  return (pt) => ({
    x: s1.x + (pt.x - p1.x) * kx,
    y: s1.y + (pt.y - p1.y) * ky,
  });
}

async function clickPlane(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
  pt: { x: number; y: number },
) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

/**
 * Shift-click: ADD this pick to the standing selection (FB-14) — a plain click
 * replaces, so relating two entities holds the modifier from the second pick.
 */
async function addPlane(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
  pt: { x: number; y: number },
) {
  await page.keyboard.down("Shift");
  await clickPlane(page, at, pt);
  await page.keyboard.up("Shift");
}

test.describe("sketch dimension expressions (desktop 1440)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("width=20, height=width/2 solves to 10; driven reference updates without over-constraining", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Expr block");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // e1: the width reference line. e2: the expression-driven line. e3: a line
    // tied EQUAL to e2, so its length tracks e2 — it will carry a driven readout.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -15 });
    await clickPlane(page, at, { x: 30, y: -15 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -30 });
    await clickPlane(page, at, { x: 25, y: -30 });
    await page.keyboard.press("Escape");

    // Horizontal on e1 — the first constraint persists the sketch (POST).
    await clickPlane(page, at, { x: 10, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    // Selecting one line surfaces the dimension affordance (FINDINGS #12):
    // the status bar now teaches select-then-D instead of leaving it invisible.
    const dimHint = page.getByTestId("dimension-hint");
    await expect(dimHint).toBeVisible();
    await expect(dimHint).toContainText("D");
    await expect(dimHint).toContainText("dimension");
    await page.keyboard.press("h");
    await expect(page.getByTestId("glyph-0")).toHaveText("H");

    // width = 20, NAMED so the expression can reference it.
    await clickPlane(page, at, { x: 10, y: 0 });
    await page.keyboard.press("d");
    const value = page.getByTestId("dimension-input");
    const name = page.getByTestId("dimension-name");
    await expect(value).toBeVisible();
    await value.fill("20");
    await name.fill("width");
    await page.getByTestId("dimension-apply").click();
    await expect(page.getByTestId("glyph-1")).toHaveText("20");

    // height = width/2 — an EXPRESSION dimension on e2.
    await clickPlane(page, at, { x: 15, y: -15 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("d");
    await expect(value).toBeVisible();
    await value.fill("width/2");
    await page.getByTestId("dimension-apply").click();

    // THE ACCEPTANCE: height resolves to 10 — in the readout and the payload.
    await expect(page.getByTestId("glyph-2")).toHaveText("10", {
      timeout: 15_000,
    });
    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const len = lineLength(sketch.data.entities, "e2");
        const dim = sketch.data.dimensions?.find(
          (d) => d.constraint_index === 2,
        );
        return len === null || dim === undefined
          ? null
          : {
              solvedTo10: Math.abs(len - 10) < SOLVE_TOLERANCE_MM,
              readout10: Math.abs(dim.value_mm - 10) < SOLVE_TOLERANCE_MM,
              expr: dim.expression,
            };
      })
      .toEqual({ solvedTo10: true, readout10: true, expr: "width/2" });

    // Re-open the expression dimension: the editor echoes its resolved value.
    await page.getByTestId("glyph-2").click();
    await expect(value).toHaveValue("width/2");
    await expect(page.getByTestId("dimension-editor")).toContainText("= 10 mm");
    await page.mouse.move(1360, 840);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/dimension-expression-editor-desktop.png`,
    });
    await value.press("Escape");
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);

    // Tie e3 EQUAL to e2, so e3's length tracks the expression (both = 10).
    await clickPlane(page, at, { x: 15, y: -15 }); // e2 body
    await addPlane(page, at, { x: 12, y: -30 }); // + e3 body
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("e");
    await expect(page.getByTestId("glyph-3")).toHaveText("=");

    // ---- Driven (reference) dimension: measured, can't over-constrain. ----
    // e3's length is already determined (equal → e2 → width/2), so a DRIVING
    // distance on e3 would over-constrain it. Author this one DRIVEN instead:
    // excluded from the solver, it just measures — the sketch keeps solving.
    await clickPlane(page, at, { x: 12, y: -30 });
    await page.keyboard.press("d");
    await expect(page.getByTestId("dimension-editor")).toBeVisible();
    await page.getByTestId("dimension-driven").click();
    await page.getByTestId("dimension-apply").click();
    await expect(page.getByTestId("dimension-editor")).toHaveCount(0);

    // The reference dimension reads (10) in quiet ink; the solve is healthy.
    await expect(page.getByTestId("glyph-4")).toHaveText("(10)");
    await expect(page.getByTestId("glyph-4")).toHaveAttribute(
      "data-driven",
      "true",
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
    await expect(page.getByTestId("dro-solve")).not.toContainText(
      "OVER-CONSTRAINED",
    );

    // Edit the geometry: bump width 20 → 40. The expression re-evaluates to 20,
    // equal carries it to e3, and the DRIVEN readout re-measures — parentheses
    // track the geometry.
    await page.getByTestId("glyph-1").click();
    await expect(value).toHaveValue("20");
    await value.fill("40");
    await page.getByTestId("dimension-apply").click();
    await expect(page.getByTestId("glyph-2")).toHaveText("20", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("glyph-4")).toHaveText("(20)");
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);

    await page.mouse.move(1360, 840);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/dimension-expression-solved-desktop.png`,
    });

    // A bad expression is loud, not silent: the invalid diagnostic appears.
    await page.getByTestId("glyph-2").click();
    await expect(value).toBeVisible();
    await value.fill("nope/0");
    await page.getByTestId("dimension-apply").click();
    await expect(page.getByTestId("solve-diagnostic")).toContainText(
      "Dimension expression",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("dro-solve")).toContainText("INVALID");
  });
});

test.describe("sketch dimension expressions (laptop 1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("expression + driven readouts stay usable; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Expr laptop");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 620, y: 520 },
      { x: 900, y: 360 },
    );

    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: -15 });
    await clickPlane(page, at, { x: 30, y: -15 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 10, y: 0 });
    await page.keyboard.press("h");
    const value = page.getByTestId("dimension-input");
    await clickPlane(page, at, { x: 10, y: 0 });
    await page.keyboard.press("d");
    await value.fill("20");
    await page.getByTestId("dimension-name").fill("width");
    await page.getByTestId("dimension-apply").click();
    await expect(page.getByTestId("glyph-1")).toHaveText("20");

    await clickPlane(page, at, { x: 15, y: -15 });
    await page.keyboard.press("d");
    await value.fill("width/2");
    await page.getByTestId("dimension-apply").click();
    await expect(page.getByTestId("glyph-2")).toHaveText("10", {
      timeout: 15_000,
    });

    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    // Park clear of the bottom-right reference cube (viewport makeover).
    await page.mouse.move(1080, 770);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/dimension-expression-solved-laptop.png`,
    });
  });
});
