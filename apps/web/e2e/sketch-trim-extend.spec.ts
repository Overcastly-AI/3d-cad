import { expect, test, type Page } from "./fixtures";

import { handClick } from "./hand";
import {
  calibratePlane,
  clickPlane,
  enterSketch,
  type PlaneMapper,
} from "./planeMap";
import {
  createPartViaApi,
  expectSketchEntities,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Sketch trim/extend (BACKLOG #2b, closes #2): the "draw rough, then clean up"
 * session tools, wired to the real stateless geometry endpoints
 * (`/geometry/sketch/trim`, `/geometry/sketch/extend`) through the gateway.
 * Real stack: gateway + documents + geometry, no mocks.
 */

interface SketchLine {
  id: string;
  kind: string;
  start: { x: number; y: number };
  end: { x: number; y: number };
}

/** Euclidean length of the line entity `id` (null when absent / not a line). */
function lineLength(
  entities: ReadonlyArray<Partial<SketchLine>>,
  id: string,
): number | null {
  const e = entities.find((x) => x.id === id);
  if (e === undefined || e.kind !== "line" || !e.start || !e.end) return null;
  return Math.hypot(e.end.x - e.start.x, e.end.y - e.start.y);
}

async function drawLine(
  page: Page,
  a: { x: number; y: number },
  b: { x: number; y: number },
): Promise<void> {
  await page.keyboard.press("l");
  await expect(page.getByTestId("tool-line")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(a.x, a.y);
  await page.mouse.move(b.x, b.y);
  await page.mouse.click(b.x, b.y);
}

test.describe("sketch trim / extend", () => {
  test("trim a crossing line at the intersection; the sketch still solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Trim plate");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // Two crossing lines: A horizontal (e1), B vertical (e2), meeting at (800,500).
    await drawLine(page, { x: 620, y: 500 }, { x: 980, y: 500 });
    await drawLine(page, { x: 800, y: 380 }, { x: 800, y: 620 });
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");

    // Arm Trim (J) — an empty-selection tool, like the draw tools.
    await page.keyboard.press("j");
    await expect(page.getByTestId("tool-trim")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Aim at the right half of A (past the crossing) — founder "before".
    await page.mouse.move(900, 500);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-trim-before.png` });

    // Click sends the whole sketch + target + raw pick to the geometry service.
    const trimResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/trim") &&
        r.request().method() === "POST",
    );
    await page.mouse.click(900, 500);
    const trim = await trimResponse;
    expect(trim.status()).toBe(200);

    const trimReq = trim.request().postDataJSON() as {
      target: string;
      entities: SketchLine[];
    };
    const trimBody = (await trim.json()) as { entities: SketchLine[] };
    const before = lineLength(trimReq.entities, trimReq.target);
    const after = lineLength(trimBody.entities, trimReq.target);
    // The picked segment is cut at the crossing: the target keeps its id and is
    // strictly SHORTER (or a split adds an entity; either proves the trim ran).
    expect(before).not.toBeNull();
    if (after !== null) {
      expect(after).toBeLessThan(before as number);
    } else {
      expect(trimBody.entities.length).toBeGreaterThan(trimReq.entities.length);
    }

    // The clean-up note is surfaced honestly (no silent solver mutation).
    await expect(page.getByTestId("sketch-edit-note")).toContainText("Trimmed");
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-trim-after.png` });

    // Save → the sketch persists and STILL SOLVES (no dangling reference).
    const featurePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/features`) &&
        r.request().method() === "POST",
    );
    const evalPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/evaluate`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    expect((await featurePromise).status()).toBe(201);
    const evalResponse = await evalPromise;
    expect(evalResponse.status()).toBe(200);
    const evalBody = (await evalResponse.json()) as {
      features: Array<{
        status: string;
        data: { kind: string } | null;
      }>;
    };
    expect(evalBody.features[0]?.status).toBe("ok");
    expect(evalBody.features[0]?.data?.kind).toBe("solved_sketch");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
  });

  test("extend a line to meet its neighbor; the endpoint moves and it solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Extend plate");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // Short line A (e1) and a vertical barrier B (e2) to the right; A's support
    // line (y = const) meets B at x = 1000 screen.
    await drawLine(page, { x: 620, y: 500 }, { x: 760, y: 500 });
    await drawLine(page, { x: 1000, y: 380 }, { x: 1000, y: 620 });
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");

    // Arm Extend (K); aim near A's right end so THAT end grows to the barrier.
    await page.keyboard.press("k");
    await expect(page.getByTestId("tool-extend")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.move(740, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-extend-before.png`,
    });

    const extendResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/extend") &&
        r.request().method() === "POST",
    );
    await page.mouse.click(740, 500);
    const extend = await extendResponse;
    expect(extend.status()).toBe(200);

    const extReq = extend.request().postDataJSON() as {
      target: string;
      entities: SketchLine[];
    };
    const extBody = (await extend.json()) as { entities: SketchLine[] };
    const before = lineLength(extReq.entities, extReq.target);
    const after = lineLength(extBody.entities, extReq.target);
    expect(before).not.toBeNull();
    expect(after).not.toBeNull();
    // The picked end grew: the extended line is strictly LONGER, id unchanged.
    expect(after as number).toBeGreaterThan(before as number);

    await expect(page.getByTestId("sketch-edit-note")).toContainText(
      "Extended",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-extend-after.png`,
    });

    // Save → persists and solves; no dangling-constraint error on evaluate.
    const evalPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/parts/${part.id}/evaluate`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sketch-save").click();
    const evalResponse = await evalPromise;
    expect(evalResponse.status()).toBe(200);
    const evalBody = (await evalResponse.json()) as {
      features: Array<{ status: string; data: { kind: string } | null }>;
    };
    expect(evalBody.features[0]?.status).toBe("ok");
    expect(evalBody.features[0]?.data?.kind).toBe("solved_sketch");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
  });
});

test.describe("sketch trim / extend — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("modify tools stay reachable; founder screenshot", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Trim laptop");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await drawLine(page, { x: 460, y: 420 }, { x: 780, y: 420 });
    await drawLine(page, { x: 620, y: 300 }, { x: 620, y: 540 });

    // The Trim/Extend tools live on the strip at this width.
    await expect(page.getByTestId("tool-trim")).toBeVisible();
    await expect(page.getByTestId("tool-extend")).toBeVisible();

    await page.keyboard.press("j");
    await page.mouse.move(700, 420);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sketch-trim-laptop.png` });
  });
});

/**
 * Helical-gear gap G7 — CLEANING UP A SKETCH.
 *
 * The product test (docs/qa/helical-gear-2026-09-24.md, step 10) tried to cut
 * a keyway into one loop: Trim cut the circle's top, then "did nothing" on the
 * rectangle's bottom edge and side stubs, and Delete/Backspace removed only
 * constraints, so a stray entity could never be deleted.
 *
 * The geometry service trims those shapes correctly (probed directly: the
 * bottom edge is deleted, each stub is cut at the arc's end, a T-junction
 * splits). What undid the trims was the SKETCH: the constraints on the
 * trimmed curve survived the cut and the next solve pulled it straight back.
 * The rectangle's typed 3.4 mm height re-stretched the stub; a stem drawn onto
 * a line's midpoint carries a midpoint constraint that re-centred the line.
 * So every trim assertion here reads the SOLVED sketch the evaluate returns,
 * never the trim response: the trim response was right all along.
 */
interface SolvedLine {
  id: string;
  kind: string;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

/**
 * Finish the sketch, then read what the SOLVER made of it.
 *
 * Finish is the UI's own verb; the read is a diagnostic evaluate through the
 * API, taken once the strip has left (the write chain has drained). Waiting on
 * the evaluate Finish itself triggers would race: a sketch bound by a typed
 * size saves live, so its last evaluate can land before the click.
 */
async function finishAndSolve(page: Page, partId: string, token: string) {
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  const response = await page.request.post(`/api/v1/parts/${partId}/evaluate`, {
    data: {},
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as {
    features: Array<{
      status: string;
      data: { kind: string; entities: SolvedLine[] } | null;
    }>;
  };
  expect(body.features[0]?.status).toBe("ok");
  return body.features[0]?.data?.entities ?? [];
}

async function openSketch(page: Page, name: string) {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, name);
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  const at = await calibratePlane(
    page,
    { x: 700, y: 600 },
    { x: 1000, y: 400 },
  );
  return { partId: part.id, token, at };
}

async function lineThrough(
  page: Page,
  at: PlaneMapper,
  a: { x: number; y: number },
  b: { x: number; y: number },
) {
  await page.keyboard.press("l");
  await clickPlane(page, at, a);
  await clickPlane(page, at, b);
  await page.keyboard.press("Escape"); // end the chain
  await page.keyboard.press("Escape"); // back to Select
}

async function trimAt(
  page: Page,
  at: PlaneMapper,
  pt: { x: number; y: number },
) {
  await page.keyboard.press("j");
  await expect(page.getByTestId("tool-trim")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const trimmed = page.waitForResponse(
    (r) => r.url().includes("/geometry/sketch/trim") && r.status() === 200,
  );
  const px = at(pt);
  await handClick(page, px.x, px.y);
  await trimmed;
  await expect(page.getByTestId("sketch-edit-note")).toContainText("Trimmed");
  await page.keyboard.press("Escape");
}

const lengthOf = (line: SolvedLine | undefined): number =>
  line?.start === undefined || line.end === undefined
    ? NaN
    : Math.hypot(line.end.x - line.start.x, line.end.y - line.start.y);

/** The solved line lying along y = `y` (both ends), if there is one. */
const lineAlong = (entities: SolvedLine[], y: number) =>
  entities.find(
    (l) =>
      l.kind === "line" &&
      Math.abs((l.start?.y ?? NaN) - y) < 1e-6 &&
      Math.abs((l.end?.y ?? NaN) - y) < 1e-6,
  );

test.describe("helical-gear G7: sketch clean-up", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  /**
   * The gear's own keyway, scaled x4 so a hand can hit it at the default zoom:
   * a circle R20 about the origin and a typed 12 x 13.6 rectangle over its
   * top. Trim the circle's top (the arc's ends now sit ON the rectangle's
   * sides: two T-junctions), the bottom edge (no crossings: deleted whole),
   * then each side stub below its T. One loop is left: the arc, two short
   * sides and the top.
   */
  test("the keyway loop: trims at T-junctions keep their cut through the solve", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const { partId, token, at } = await openSketch(page, "Keyway loop");
    await page.keyboard.press("c");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 20, y: 0 });
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("r");
    await clickPlane(page, at, { x: -6, y: 12 });
    await clickPlane(page, at, { x: 6, y: 26 });
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "armed",
    );
    for (const key of ["1", "2", "Tab", "1", "3", ".", "6"]) {
      await page.keyboard.press(key);
    }
    await page.keyboard.press("Enter");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expectSketchEntities(page, 5);

    await trimAt(page, at, { x: 0, y: 20 }); // the circle's top
    await trimAt(page, at, { x: 0, y: 12 }); // the bottom edge, whole
    await trimAt(page, at, { x: 6, y: 15 }); // the right stub, below its T
    await trimAt(page, at, { x: -6, y: 15 }); // the left stub
    await page.mouse.move(1200, 700);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-gear-fix-g7-keyway-after.png`,
    });

    const solved = await finishAndSolve(page, partId, token);
    // Where the circle crosses x = +-6.
    const tee = Math.sqrt(20 * 20 - 6 * 6);
    for (const x of [6, -6]) {
      const side = solved.find(
        (l) =>
          l.kind === "line" &&
          Math.abs((l.start?.x ?? NaN) - x) < 1e-6 &&
          Math.abs((l.end?.x ?? NaN) - x) < 1e-6,
      );
      const low = Math.min(side?.start?.y ?? NaN, side?.end?.y ?? NaN);
      expect(
        low,
        `the side at x = ${x} stays cut at its T, y = ${tee.toFixed(4)} (solved ${JSON.stringify(solved)})`,
      ).toBeCloseTo(tee, 6);
    }
    expect(
      lineAlong(solved, 12),
      "the bottom edge stays deleted",
    ).toBeUndefined();
    // One loop is left: the arc, the two short sides and the top.
    expect(
      solved
        .filter((e) => e.kind === "line" || e.kind === "arc")
        .map((e) => e.kind)
        .sort(),
    ).toEqual(["arc", "line", "line", "line"]);
  });

  test("trim of a dimensioned line keeps the cut through the solve", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { partId, token, at } = await openSketch(page, "Trim a dimension");
    // A 40 mm line whose length was TYPED (a driving distance), and a cutter.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 0, y: 10 });
    await clickPlane(page, at, { x: 30, y: 10 });
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "armed",
    );
    for (const key of ["4", "0"]) await page.keyboard.press(key);
    await page.keyboard.press("Enter");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await lineThrough(page, at, { x: 25, y: 0 }, { x: 25, y: 20 });
    await trimAt(page, at, { x: 34, y: 10 });

    const solved = await finishAndSolve(page, partId, token);
    expect(
      lengthOf(lineAlong(solved, 10)),
      `the trimmed line is 25 mm, not pulled back to its typed 40 (solved ${JSON.stringify(solved)})`,
    ).toBeCloseTo(25, 6);
  });

  test("Delete removes a line, an arc and a spline with their constraints; Undo brings one back", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { at } = await openSketch(page, "Delete entities");
    // A horizontal line (the draw infers its H), a quarter arc and a spline.
    await lineThrough(page, at, { x: -20, y: -10 }, { x: 20, y: -10 });
    await page.keyboard.press("a");
    await clickPlane(page, at, { x: -30, y: 20 }); // centre
    await clickPlane(page, at, { x: -20, y: 20 }); // start
    await clickPlane(page, at, { x: -30, y: 30 }); // end direction
    await page.keyboard.press("Escape");
    await page.keyboard.press("s");
    await clickPlane(page, at, { x: 10, y: 20 });
    await clickPlane(page, at, { x: 20, y: 20 });
    await clickPlane(page, at, { x: 30, y: 20 });
    await page.keyboard.press("Enter");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expectSketchEntities(page, 3);
    const horizontal = page.locator(
      '[data-testid^="glyph-"][data-kind="horizontal"]',
    );
    await expect(horizontal).toHaveCount(1);

    // Select the LINE (a real click on its body) and press Delete.
    const onLine = at({ x: 10, y: -10 });
    await handClick(page, onLine.x, onLine.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await expect(page.getByTestId("sketch-delete")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-gear-fix-g7-delete-after.png`,
    });
    await page.keyboard.press("Delete");
    await expectSketchEntities(page, 2, "Delete removed the selected line");
    await expect(horizontal, "its H went with it").toHaveCount(0);

    // Undo brings the line AND its constraint back.
    await page.keyboard.press("Control+z");
    await expectSketchEntities(page, 3, "Undo restored the line");
    await expect(horizontal).toHaveCount(1);

    // The arc, by its body at 45 degrees, with Delete…
    const onArc = at({
      x: -30 + 10 * Math.SQRT1_2,
      y: 20 + 10 * Math.SQRT1_2,
    });
    await handClick(page, onArc.x, onArc.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("Delete");
    await expectSketchEntities(page, 2, "Delete removed the arc");

    // …and the spline, between its fit points, with Backspace.
    const onSpline = at({ x: 15, y: 20 });
    await handClick(page, onSpline.x, onSpline.y);
    await expect(page.getByTestId("selection-readout")).toContainText("1 ent");
    await page.keyboard.press("Backspace");
    await expectSketchEntities(page, 1, "Backspace removed the spline");
  });
});
