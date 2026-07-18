import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Sketcher constraints + solve feedback (BACKLOG #5): the design-doc §6
 * worked example driven end-to-end in a real browser against the real stack
 * — draw a 40 × 25 rectangle, apply the five benchmark constraints
 * (coincident / horizontal / vertical / distance 40 / distance 25), assert
 * the SOLVED corners from the intercepted evaluate payloads, then edit the
 * 40 dimension to 60 and watch the corners move. Plus the conflicting-
 * constraint diagnostic (never a silent failure).
 */

/** Assertion bound for solved coordinates (mm) — the solver benchmark's. */
const SOLVE_TOLERANCE_MM = 1e-6;

interface SolvedPoint {
  x: number;
  y: number;
}
interface SolvedEntity {
  id: string;
  kind: string;
  start?: SolvedPoint;
  end?: SolvedPoint;
  center?: SolvedPoint;
  radius?: number;
}
interface EvaluateBody {
  features: Array<{
    feature_id: string;
    status: string;
    error: { code: string; message: string } | null;
    data: {
      kind: string;
      status: string;
      dof: number | null;
      entities: SolvedEntity[];
      conflicting_constraints?: number[];
    } | null;
  }>;
}

/** Collect every evaluate response body for the part, newest last. */
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

/** Direction vector of a solved line (unnormalised), or null. */
function lineDir(
  entities: SolvedEntity[],
  id: string,
): { x: number; y: number } | null {
  const line = entities.find((e) => e.id === id);
  if (line?.start === undefined || line.end === undefined) return null;
  return { x: line.end.x - line.start.x, y: line.end.y - line.start.y };
}

/** Normalised angle-independent cross / dot of two solved line directions. */
function unitCrossDot(
  entities: SolvedEntity[],
  a: string,
  b: string,
): { cross: number; dot: number } | null {
  const u = lineDir(entities, a);
  const v = lineDir(entities, b);
  if (u === null || v === null) return null;
  const lu = Math.hypot(u.x, u.y);
  const lv = Math.hypot(v.x, v.y);
  if (lu === 0 || lv === 0) return null;
  const ux = u.x / lu;
  const uy = u.y / lu;
  const vx = v.x / lv;
  const vy = v.y / lv;
  return { cross: ux * vy - uy * vx, dot: ux * vx + uy * vy };
}

/** Perpendicular distance from a circle centre to a solved line (mm). */
function centreToLineGap(
  entities: SolvedEntity[],
  lineId: string,
  circleId: string,
): number | null {
  const line = entities.find((e) => e.id === lineId);
  const circle = entities.find((e) => e.id === circleId);
  if (line?.start === undefined || line.end === undefined) return null;
  if (circle?.center === undefined || circle.radius === undefined) return null;
  const { center } = circle;
  const dx = line.end.x - line.start.x;
  const dy = line.end.y - line.start.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return null;
  // |(p - a) × dir| / |dir|.
  const cross = (center.x - line.start.x) * dy - (center.y - line.start.y) * dx;
  return Math.abs(cross) / len;
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Build a plane-mm → screen-px mapper by reading the DRO at two screen
 * points with snap off (0.01 mm readings). With it, clicks land on EXACT
 * millimetre coordinates — the drawn rectangle IS 40 × 25, so the driving
 * dimensions solve with zero movement and every later click stays on target.
 */
async function calibratePlane(
  page: Page,
  s1: { x: number; y: number },
  s2: { x: number; y: number },
): Promise<(pt: { x: number; y: number }) => { x: number; y: number }> {
  // The camera eases to the normal-on pose after the plane pick; the DRO
  // only re-raycasts on pointer moves, so jiggle-poll the same screen point
  // until two consecutive readings agree — the camera has settled.
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
  ): Promise<{ x: number; y: number }> => {
    await page.mouse.move(sx, sy);
    // Poll until the DRO shows a fresh reading (not "—", not the previous
    // point's value) — the readout updates through the store, not the event.
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

async function clickPlane(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
  pt: { x: number; y: number },
) {
  const px = at(pt);
  await page.mouse.click(px.x, px.y);
}

test.describe("sketcher constraints", () => {
  test("worked example: 40×25 rectangle, five constraints, solved corners, 40→60 moves them", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Demo block");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");

    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // Draw the §6 rectangle exactly: (0,0) → (40,25), four CCW lines e1–e4.
    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.keyboard.press("Escape"); // back to the select tool

    // 1) Horizontal on the bottom line — the first constraint persists the
    //    sketch (POST) and starts the live solve loop.
    const created = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    await clickPlane(page, at, { x: 20, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("h");
    expect((await created).status()).toBe(201);
    await expect(page.getByTestId("glyph-0")).toHaveText("H");
    await expect(page.getByTestId("dro-solve")).toContainText(
      "UNDER-CONSTRAINED",
    );

    // 2) Vertical on the right line (PATCH from here on).
    await clickPlane(page, at, { x: 40, y: 12.5 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("v");
    await expect(page.getByTestId("glyph-1")).toHaveText("V");

    // 3) Coincident at the shared corner — two clicks cycle through the
    //    stacked endpoints (e1.end, then e2.start).
    await clickPlane(page, at, { x: 40, y: 0 });
    await clickPlane(page, at, { x: 40, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("c");
    await expect(page.getByTestId("glyph-2")).toHaveText("C");

    // 4) Distance 40 on the bottom line — the inline mm editor.
    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("d");
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("40"); // measured: the calibrated draw
    await input.fill("40");
    await input.press("Enter");
    await expect(page.getByTestId("glyph-3")).toHaveText("40");

    // 5) Distance 25 on the right line.
    await clickPlane(page, at, { x: 40, y: 12.5 });
    await page.keyboard.press("d");
    await expect(input).toBeVisible();
    await input.fill("25");
    await input.press("Enter");
    await expect(page.getByTestId("glyph-4")).toHaveText("25");
    await expect(page.getByTestId("selection-readout")).toContainText(
      "5 applied",
    );

    // The solved payload: all five constraints hold at the §6 coordinates.
    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data === null || sketch?.data === undefined) return null;
        return {
          constraintsHold:
            Math.abs((lineLength(sketch.data.entities, "e1") ?? 0) - 40) <
              SOLVE_TOLERANCE_MM &&
            Math.abs((lineLength(sketch.data.entities, "e2") ?? 0) - 25) <
              SOLVE_TOLERANCE_MM,
          status: sketch.data.status,
        };
      })
      .toEqual({ constraintsHold: true, status: "underconstrained" });
    const before = latestSketch(evaluations)?.data?.entities;
    const cornerBefore = before?.find((e) => e.id === "e1")?.end;
    expect(cornerBefore).toBeDefined();
    await expect(page.getByTestId("dro-solve")).toContainText(
      /DOF \d+ · UNDER-CONSTRAINED/,
    );

    // Founder screenshot: the constrained rectangle with its annotation
    // glyphs and the DRO SOLVE cell (desktop).
    await page.mouse.move(1400, 900); // park the cursor off the sketch
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketcher-constraints-desktop.png`,
    });

    // The worked-example edit: click the 40, type 60, Enter — re-solve
    // moves the corners.
    await page.getByTestId("glyph-3").click();
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("40");
    await input.fill("60");
    await input.press("Enter");
    await expect(page.getByTestId("glyph-3")).toHaveText("60");
    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data === null || sketch?.data === undefined) return null;
        return Math.abs((lineLength(sketch.data.entities, "e1") ?? 0) - 60);
      })
      .toBeLessThan(SOLVE_TOLERANCE_MM);
    const after = latestSketch(evaluations)?.data?.entities;
    const cornerAfter = after?.find((e) => e.id === "e1")?.end;
    expect(cornerAfter).toBeDefined();
    const moved = Math.hypot(
      (cornerAfter?.x ?? 0) - (cornerBefore?.x ?? 0),
      (cornerAfter?.y ?? 0) - (cornerBefore?.y ?? 0),
    );
    expect(moved).toBeGreaterThan(1); // the corner visibly moved (mm)
    // The coincident corner still holds after the edit.
    const e1End = after?.find((e) => e.id === "e1")?.end;
    const e2Start = after?.find((e) => e.id === "e2")?.start;
    expect(
      Math.hypot(
        (e1End?.x ?? 0) - (e2Start?.x ?? 0),
        (e1End?.y ?? 0) - (e2Start?.y ?? 1),
      ),
    ).toBeLessThan(SOLVE_TOLERANCE_MM);

    // Finish; everything persisted (5 constraints on the feature).
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    const treeResponse = await page.request.get(
      `/api/v1/parts/${part.id}/features`,
      { headers: { Authorization: `Bearer ${account.token}` } },
    );
    const treeBody = (await treeResponse.json()) as {
      features: Array<{
        feature: { params: { constraints: Array<{ kind: string }> } };
      }>;
    };
    expect(
      treeBody.features[0]?.feature.params.constraints.map((c) => c.kind),
    ).toEqual(["horizontal", "vertical", "coincident", "distance", "distance"]);
  });

  test("conflicting constraints: visible diagnostic, flagged glyph, recovery", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Conflict part");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // A 30 mm line with both endpoints fixed…
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 30, y: 0 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 pt");
    await page.keyboard.press("x");
    await expect(page.getByTestId("glyph-0")).toHaveText("FIX");
    await clickPlane(page, at, { x: 30, y: 0 });
    await page.keyboard.press("x");
    await expect(page.getByTestId("glyph-1")).toHaveText("FIX");

    // …then a 60 mm driving dimension: mutually unsatisfiable.
    await clickPlane(page, at, { x: 15, y: 0 });
    await page.keyboard.press("d");
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await input.fill("60");
    await input.press("Enter");

    // The failure is loud and located: diagnostic stamp, flag-ink DRO cell,
    // the offending dimension glyph flagged, the tree row failed.
    await expect(page.getByTestId("solve-diagnostic")).toContainText(
      "Solve conflict",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("dro-solve")).toHaveText("CONFLICT");
    await expect(page.getByTestId("glyph-2")).toHaveAttribute(
      "data-flagged",
      "true",
    );
    await expect(page.getByTestId("eval-status")).toHaveText("Failed");

    // Recovery: open the bad dimension, remove it — the sketch solves again
    // (both endpoints fixed = fully constrained, DOF 0).
    await page.getByTestId("glyph-2").click();
    await page.getByTestId("dimension-remove").click();
    await expect(page.getByTestId("dro-solve")).toHaveText(
      "DOF 0 · CONVERGED",
      {
        timeout: 15_000,
      },
    );
    await expect(page.getByTestId("solve-diagnostic")).toHaveCount(0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
  });
});

/**
 * Relational constraints (BACKLOG #3, frontend 3b): the three verbs that
 * relate two whole curves — P parallel (∥), L perpendicular (⊥), T tangent
 * (T). Each worked case draws deliberately UN-satisfying geometry, applies
 * the verb, and proves from the intercepted evaluate payload that the solver
 * MOVED the geometry to satisfy the relation, and that the glyph renders.
 */
test.describe("sketcher relational constraints", () => {
  /** Dimensionless bound for parallel/perpendicular (unit cross/dot). */
  const ANGLE_TOLERANCE = 1e-4;
  /** Millimetre bound for tangency (centre-to-line gap vs radius). */
  const TANGENT_TOLERANCE_MM = 1e-3;

  const displacement = (
    solved: SolvedEntity | undefined,
    start: SolvedPoint,
    end: SolvedPoint,
  ): number => {
    if (solved?.start === undefined || solved.end === undefined) return 0;
    return Math.max(
      Math.hypot(solved.start.x - start.x, solved.start.y - start.y),
      Math.hypot(solved.end.x - end.x, solved.end.y - end.y),
    );
  };

  test("two parallel lines: the slanted line rotates parallel", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Parallel part");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // e1 horizontal, e2 clearly slanted — not parallel.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 0 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 12 });
    await clickPlane(page, at, { x: 35, y: -3 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 20, y: 0 }); // e1 body
    await clickPlane(page, at, { x: 17.5, y: 4.5 }); // e2 body (midpoint)
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("p");
    await expect(page.getByTestId("glyph-0")).toHaveText("∥");

    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const cd = unitCrossDot(sketch.data.entities, "e1", "e2");
        const moved = displacement(
          sketch.data.entities.find((e) => e.id === "e2"),
          { x: 0, y: 12 },
          { x: 35, y: -3 },
        );
        return cd === null
          ? null
          : {
              parallel: Math.abs(cd.cross) < ANGLE_TOLERANCE,
              moved: moved > 1,
            };
      })
      .toEqual({ parallel: true, moved: true });
  });

  test("two perpendicular lines: the slanted line rotates to 90°", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Perp part");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // e1 horizontal, e2 slanted (not 90° to e1).
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 0 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 5 });
    await clickPlane(page, at, { x: 35, y: 25 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 20, y: 0 }); // e1 body
    await clickPlane(page, at, { x: 22.5, y: 15 }); // e2 body (midpoint)
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("l"); // L = perpendicular in the constraint vocab
    await expect(page.getByTestId("glyph-0")).toHaveText("⊥");

    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const cd = unitCrossDot(sketch.data.entities, "e1", "e2");
        const moved = displacement(
          sketch.data.entities.find((e) => e.id === "e2"),
          { x: 10, y: 5 },
          { x: 35, y: 25 },
        );
        return cd === null
          ? null
          : { perp: Math.abs(cd.dot) < ANGLE_TOLERANCE, moved: moved > 1 };
      })
      .toEqual({ perp: true, moved: true });
  });

  test("line + circle tangent: the line slides in to touch the circle; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tangent part");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // A circle (r10 at origin) and a vertical line 20 mm off — a 10 mm gap.
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 10, y: 0 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 20, y: -15 });
    await clickPlane(page, at, { x: 20, y: 15 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 20, y: 0 }); // e2 line body
    await clickPlane(page, at, { x: 0, y: 10 }); // e1 circle body (top)
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("t");
    await expect(page.getByTestId("glyph-0")).toHaveText("T");

    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const gap = centreToLineGap(sketch.data.entities, "e2", "e1");
        const line = sketch.data.entities.find((e) => e.id === "e2");
        const circle = sketch.data.entities.find((e) => e.id === "e1");
        if (gap === null || circle?.radius === undefined) return null;
        // Tangent: gap == radius. Moved: the line left x = 20.
        return {
          tangent: Math.abs(gap - circle.radius) < TANGENT_TOLERANCE_MM,
          moved: Math.abs((line?.start?.x ?? 20) - 20) > 1,
        };
      })
      .toEqual({ tangent: true, moved: true });

    // Founder screenshot: the tangent T glyph on the solved line-arc pair.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/constraints-tangent-perp-parallel-desktop.png`,
    });
  });
});

test.describe("sketcher relational constraints small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("perpendicular + tangent stay usable; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(
      page,
      account.token,
      "Relational laptop",
    );
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    // A perpendicular pair…
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 0 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 10, y: 5 });
    await clickPlane(page, at, { x: 35, y: 25 });
    await page.keyboard.press("Escape");
    await clickPlane(page, at, { x: 20, y: 0 });
    await clickPlane(page, at, { x: 22.5, y: 15 });
    await page.keyboard.press("l");
    await expect(page.getByTestId("glyph-0")).toHaveText("⊥");

    // …and a tangent line-arc, for a two-glyph founder shot.
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 30, y: -20 });
    await clickPlane(page, at, { x: 38, y: -20 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 5, y: -30 });
    await clickPlane(page, at, { x: 45, y: -30 });
    await page.keyboard.press("Escape");
    await clickPlane(page, at, { x: 25, y: -30 }); // line body
    await clickPlane(page, at, { x: 30, y: -12 }); // circle body (top)
    await page.keyboard.press("t");
    await expect(page.getByTestId("glyph-1")).toHaveText("T");

    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.mouse.move(1100, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/constraints-tangent-perp-parallel-laptop.png`,
    });
  });
});

test.describe("sketcher constraints small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("constraint flow stays usable; founder screenshot", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Demo block");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );

    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("h");
    await expect(page.getByTestId("glyph-0")).toHaveText("H");
    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("d");
    const input = page.getByTestId("dimension-input");
    await expect(input).toBeVisible();
    await input.fill("40");
    await input.press("Enter");
    await expect(page.getByTestId("glyph-1")).toHaveText("40");
    await expect(page.getByTestId("dro-solve")).toContainText(
      "UNDER-CONSTRAINED",
    );

    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.mouse.move(1100, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketcher-constraints-laptop.png`,
    });
  });
});

/**
 * Size/shape constraints (BACKLOG #4, frontend 4b): the trio that completes
 * the six-constraint vocabulary — E equal (=), S symmetric (⟷ about an axis),
 * O concentric (◎). Each worked case draws deliberately un-satisfying
 * geometry, applies the verb, and proves from the intercepted evaluate
 * payload that the solver MOVED the geometry to satisfy the relation, and
 * that the glyph renders.
 */
const SIZE_TOLERANCE_MM = 1e-3;

const circleRadius = (entities: SolvedEntity[], id: string): number | null =>
  entities.find((e) => e.id === id)?.radius ?? null;

const circleCenter = (
  entities: SolvedEntity[],
  id: string,
): SolvedPoint | null => entities.find((e) => e.id === id)?.center ?? null;

/** Reflect point `p` across the infinite line through `a`–`b`. */
function reflectAcrossLine(
  p: SolvedPoint,
  a: SolvedPoint,
  b: SolvedPoint,
): SolvedPoint {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return p;
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  return { x: 2 * (a.x + t * dx) - p.x, y: 2 * (a.y + t * dy) - p.y };
}

const gap = (a: SolvedPoint, b: SolvedPoint): number =>
  Math.hypot(a.x - b.x, a.y - b.y);

test.describe("sketcher size/shape constraints", () => {
  test("equal-radius circles: two different radii converge", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Equal part");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // e1: r10 at the origin. e2: r5, well clear to the right.
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 10, y: 0 });
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 35, y: 0 });
    await clickPlane(page, at, { x: 40, y: 0 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 0, y: 10 }); // e1 body (top)
    await clickPlane(page, at, { x: 35, y: 5 }); // e2 body (top)
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("e");
    await expect(page.getByTestId("glyph-0")).toHaveText("=");

    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const r1 = circleRadius(sketch.data.entities, "e1");
        const r2 = circleRadius(sketch.data.entities, "e2");
        if (r1 === null || r2 === null) return null;
        return {
          equal: Math.abs(r1 - r2) < SIZE_TOLERANCE_MM,
          moved: Math.abs(r2 - 5) > 0.1, // the r5 circle grew
        };
      })
      .toEqual({ equal: true, moved: true });
  });

  test("concentric circles: two offset centers share one point", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Concentric part");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // e1: r10 at the origin. e2: r6 with an offset centre at (30, 5).
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 10, y: 0 });
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 30, y: 5 });
    await clickPlane(page, at, { x: 36, y: 5 });
    await page.keyboard.press("Escape");

    await clickPlane(page, at, { x: 0, y: 10 }); // e1 body (top)
    await clickPlane(page, at, { x: 30, y: 11 }); // e2 body (top)
    await expect(page.getByTestId("selection-readout")).toContainText("2 ent");
    await page.keyboard.press("o");
    await expect(page.getByTestId("glyph-0")).toHaveText("◎");

    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const c1 = circleCenter(sketch.data.entities, "e1");
        const c2 = circleCenter(sketch.data.entities, "e2");
        if (c1 === null || c2 === null) return null;
        return {
          shared: gap(c1, c2) < SIZE_TOLERANCE_MM,
          moved: gap(c2, { x: 30, y: 5 }) > 1, // the offset centre moved in
        };
      })
      .toEqual({ shared: true, moved: true });
  });

  test("symmetric rectangle about a construction centerline: corners mirror", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Symmetric part");
    const evaluations = collectEvaluations(page, part.id);
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );

    // A 40×20 rectangle (e1..e4), and a vertical centerline at x=15 (e5),
    // deliberately OFF the rectangle's own centre (x=20).
    await page.keyboard.press("r");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 40, y: 20 });
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 15, y: -30 });
    await clickPlane(page, at, { x: 15, y: -5 });
    await page.keyboard.press("Escape");

    // Make the centerline construction (reference-only axis) — the clean way
    // to carry a mirror line, straight from the #2 construction vocabulary.
    await clickPlane(page, at, { x: 15, y: -17 });
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("n");

    // Symmetric: the bottom edge's two corners about the centerline.
    await clickPlane(page, at, { x: 0, y: 0 }); // e1.start (bottom-left)
    await clickPlane(page, at, { x: 40, y: 0 }); // e1.end (bottom-right)
    await clickPlane(page, at, { x: 15, y: -17 }); // the centerline axis
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    await page.keyboard.press("s");
    await expect(page.getByTestId("glyph-0")).toHaveText("⟷");

    await expect
      .poll(() => {
        const sketch = latestSketch(evaluations);
        if (sketch?.data == null) return null;
        const es = sketch.data.entities;
        const e1 = es.find((e) => e.id === "e1");
        const axis = es.find((e) => e.id === "e5");
        if (
          e1?.start === undefined ||
          e1.end === undefined ||
          axis?.start === undefined ||
          axis.end === undefined
        ) {
          return null;
        }
        const mirrored = reflectAcrossLine(e1.start, axis.start, axis.end);
        // Displacement of every involved endpoint from where it was drawn.
        const moved = Math.max(
          gap(e1.start, { x: 0, y: 0 }),
          gap(e1.end, { x: 40, y: 0 }),
          gap(axis.start, { x: 15, y: -30 }),
          gap(axis.end, { x: 15, y: -5 }),
        );
        return {
          symmetric: gap(mirrored, e1.end) < SIZE_TOLERANCE_MM,
          moved: moved > 1,
        };
      })
      .toEqual({ symmetric: true, moved: true });
  });
});

/**
 * The founder shot: one sketch carrying two of the new marks at once — a
 * concentric pair (◎) and a symmetric line about a construction centerline
 * (⟷) — captured at both widths.
 */
async function buildSizeShapeShowcase(
  page: Page,
  at: (pt: { x: number; y: number }) => { x: number; y: number },
) {
  // Concentric: a ring and an off-centre smaller circle.
  await page.keyboard.press("c");
  await clickPlane(page, at, { x: 0, y: 0 });
  await clickPlane(page, at, { x: 12, y: 0 });
  await page.keyboard.press("c");
  await clickPlane(page, at, { x: 5, y: 3 });
  await clickPlane(page, at, { x: 11, y: 3 });
  await page.keyboard.press("Escape");
  await clickPlane(page, at, { x: 0, y: 12 }); // e1 body (top)
  await clickPlane(page, at, { x: 5, y: 9 }); // e2 body (top of r6)
  await page.keyboard.press("o");
  await expect(page.locator('[data-kind="concentric"]')).toHaveText("◎");

  // Symmetric: a line whose ends mirror about a construction centerline.
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: -20, y: -30 });
  await clickPlane(page, at, { x: 30, y: -30 });
  await page.keyboard.press("l");
  await clickPlane(page, at, { x: 0, y: -55 });
  await clickPlane(page, at, { x: 0, y: -18 });
  await page.keyboard.press("Escape");
  await clickPlane(page, at, { x: 0, y: -42 }); // centerline body
  await page.keyboard.press("n"); // construction
  await clickPlane(page, at, { x: -20, y: -30 }); // e3 start
  await clickPlane(page, at, { x: 30, y: -30 }); // e3 end
  await clickPlane(page, at, { x: 0, y: -42 }); // centerline axis
  await page.keyboard.press("s");
  await expect(page.locator('[data-kind="symmetric"]')).toHaveText("⟷");
}

test.describe("sketcher size/shape constraints — founder screenshot", () => {
  test("desktop: concentric ◎ + symmetric ⟷ about a centerline", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Showcase");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 620 },
      { x: 1000, y: 420 },
    );
    await buildSizeShapeShowcase(page, at);
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/constraints-equal-symmetric-concentric-desktop.png`,
    });
  });
});

test.describe("sketcher size/shape constraints small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("laptop: the new glyphs stay usable; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Showcase laptop");
    await page.goto(`/parts/${part.id}`);
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 640, y: 560 },
      { x: 940, y: 380 },
    );
    await buildSizeShapeShowcase(page, at);
    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.mouse.move(1100, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/constraints-equal-symmetric-concentric-laptop.png`,
    });
  });
});
