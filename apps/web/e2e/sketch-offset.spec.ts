import { expect, test, type Page } from "@playwright/test";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * Sketch offset (BACKLOG #3, closes #3): the rib/web/wall-profile tool. Offset
 * ADDS a parallel copy of a target curve at a signed distance, wired to the
 * real stateless geometry endpoint (`/geometry/sketch/offset`) through the
 * gateway. Real stack: gateway + documents + geometry, no mocks.
 *
 * Contrast with trim/extend: offset never rewrites the source — the result
 * carries ONLY the new entity, which the client APPENDS (source unchanged).
 */

interface Pt {
  x: number;
  y: number;
}
interface SketchLine {
  id: string;
  kind: string;
  start: Pt;
  end: Pt;
}

/** Perpendicular distance of point `q` from the infinite line through a→b. */
function perpDistance(a: Pt, b: Pt, q: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return Number.NaN;
  // |(q − a) × dir| — signed magnitude off the directed line.
  return Math.abs(((q.x - a.x) * dy - (q.y - a.y) * dx) / len);
}

async function drawLine(page: Page, a: Pt, b: Pt): Promise<void> {
  await page.keyboard.press("l");
  await expect(page.getByTestId("tool-line")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(a.x, a.y);
  await page.mouse.move(b.x, b.y);
  await page.mouse.click(b.x, b.y);
}

async function drawCircle(page: Page, center: Pt, rim: Pt): Promise<void> {
  await page.keyboard.press("c");
  await expect(page.getByTestId("tool-circle")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(center.x, center.y);
  await page.mouse.move(rim.x, rim.y);
  await page.mouse.click(rim.x, rim.y);
}

test.describe("sketch offset", () => {
  test("offset a line +2 mm; a NEW parallel line is appended and the sketch solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Offset plate");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // One horizontal line (e1).
    await drawLine(page, { x: 620, y: 500 }, { x: 980, y: 500 });
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");

    // Arm Offset (F) — an empty-selection tool, like trim/extend.
    await page.keyboard.press("f");
    await expect(page.getByTestId("tool-offset")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Aim at the line, then click to open the inline signed-distance editor —
    // founder "before".
    await page.mouse.move(800, 500);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-offset-before.png`,
    });
    await page.mouse.click(800, 500);
    await expect(page.getByTestId("offset-editor")).toBeVisible();

    // Enter a signed distance and confirm → one POST to the geometry service.
    await page.getByTestId("offset-input").fill("2");
    const offsetResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/offset") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("offset-apply").click();
    const offset = await offsetResponse;
    expect(offset.status()).toBe(200);

    const req = offset.request().postDataJSON() as {
      target: string;
      distance: number;
      entities: SketchLine[];
    };
    const body = (await offset.json()) as { entities: SketchLine[] };
    // The result carries ONLY the new entity (source NOT echoed).
    expect(body.entities).toHaveLength(1);
    const source = req.entities.find((e) => e.id === req.target) as SketchLine;
    const created = body.entities[0] as SketchLine;
    expect(created.kind).toBe("line");
    expect(created.id).not.toBe(source.id); // fresh id, no collision
    // The new line runs parallel at the offset distance (|distance| = 2 mm).
    expect(perpDistance(source.start, source.end, created.start)).toBeCloseTo(
      2,
      1,
    );
    expect(perpDistance(source.start, source.end, created.end)).toBeCloseTo(
      2,
      1,
    );

    // Appended, not swapped: the buffer grew from 1 → 2 and the note is honest.
    await expect(page.getByTestId("sketch-edit-note")).toContainText("Offset");
    await expect(page.getByTestId("sketch-save")).toContainText("2 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-offset-after.png`,
    });

    // Save → the sketch persists and STILL SOLVES.
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

  test("offsetting a circle inward past its radius reads as a clean message, not a crash", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Offset ring");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");

    // A small circle (e1); rim at angle 0 for an easy pick.
    await drawCircle(page, { x: 800, y: 500 }, { x: 830, y: 500 });
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");

    // Offset inward (+distance shrinks a CCW circle) by far more than the
    // radius → the radius collapses to ≤ 0.
    await page.keyboard.press("f");
    await page.mouse.click(830, 500);
    await expect(page.getByTestId("offset-editor")).toBeVisible();
    await page.getByTestId("offset-input").fill("500");

    const offsetResponse = page.waitForResponse(
      (r) =>
        r.url().includes("/geometry/sketch/offset") &&
        r.request().method() === "POST",
    );
    await page.getByTestId("offset-apply").click();
    const offset = await offsetResponse;
    expect(offset.status()).toBe(422);

    // The degenerate result surfaces as a legible hint — no append, no crash.
    const hint = page.getByTestId("constraint-hint");
    await expect(hint).toBeVisible();
    await expect(hint).not.toBeEmpty();
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-offset-degenerate.png`,
    });
  });
});

test.describe("sketch offset — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("offset tool stays reachable; founder screenshot", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Offset laptop");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await drawLine(page, { x: 460, y: 420 }, { x: 780, y: 420 });

    await expect(page.getByTestId("tool-offset")).toBeVisible();
    await page.keyboard.press("f");
    await page.mouse.click(620, 420);
    await expect(page.getByTestId("offset-editor")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-offset-laptop.png`,
    });
  });
});
