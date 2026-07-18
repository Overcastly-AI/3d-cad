import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

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
