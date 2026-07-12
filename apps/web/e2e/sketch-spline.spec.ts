import { expect, test, type Page } from "@playwright/test";

import {
  countSketchInkPixels,
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Sketch spline draw tool (BACKLOG #6, closes #6): the free-form fit-point
 * curve. Click to place fit points, Enter or double-click to finish. The
 * client renders a centripetal Catmull-Rom through the fit points (a smooth
 * VISUAL approximation); the server-authoritative C2 B-spline profile edge,
 * mesh, and export come from the geometry service. v1 splines are non-
 * constrained fixed geometry, but a spline edge CAN close an extrude profile.
 * Real stack: gateway + documents + geometry, no mocks.
 */

interface Pt {
  x: number;
  y: number;
}

async function enterSketch(page: Page, plane: "XY" | "XZ" | "YZ" = "XY") {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId(`plane-${plane}`).click();
  await expect(page.getByTestId("sketch-step")).toHaveText(`On ${plane}`);
  await expect(page.getByTestId("sketch-dro")).toBeVisible();
}

/**
 * Plane-mm → screen-px mapper: read the DRO at two points with snap off so
 * later clicks land on exact millimetre coordinates (same technique as the
 * mirror/constraints specs).
 */
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

async function dblclickPlane(page: Page, at: (pt: Pt) => Pt, pt: Pt) {
  const px = at(pt);
  await page.mouse.dblclick(px.x, px.y);
}

test.describe("sketch spline", () => {
  test("place fit points → Enter finishes → a smooth spline persists and solves", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spline cam");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );

    // Arm the spline tool (S) — its guide appears in the viewport.
    await page.keyboard.press("s");
    await expect(page.getByTestId("tool-spline")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("spline-prompt")).toHaveAttribute(
      "data-phase",
      "collecting",
    );

    // Place four fit points — an open S-curve.
    const fits: Pt[] = [
      { x: -20, y: 0 },
      { x: -6, y: 14 },
      { x: 8, y: -12 },
      { x: 22, y: 4 },
    ];
    for (const fit of fits) {
      await clickPlane(page, at, fit);
    }
    // Two-plus points → the prompt offers the keyboard-first finish.
    await expect(page.getByTestId("spline-prompt")).toHaveAttribute(
      "data-phase",
      "ready",
    );
    await expect(page.getByTestId("spline-count")).toContainText(
      "4 fit points",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-spline-drawing.png`,
    });

    // Enter commits the spline — one entity now in the buffer.
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");

    // Save: the feature write (201) + evaluate round-trip carry the spline.
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
        data: {
          kind: string;
          entities: Array<{ kind: string; points?: Pt[] }>;
        } | null;
      }>;
    };
    expect(evalBody.features[0]?.status).toBe("ok");
    expect(evalBody.features[0]?.data?.kind).toBe("solved_sketch");
    const entities = evalBody.features[0]?.data?.entities ?? [];
    expect(entities).toHaveLength(1);
    expect(entities[0]?.kind).toBe("spline");
    expect(entities[0]?.points).toHaveLength(4);

    // The solved spline ink actually paints the canvas.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
    await expect
      .poll(() => countSketchInkPixels(page), { timeout: 15_000 })
      .toBeGreaterThan(40);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-spline-solved.png`,
    });

    // Reload: the spline persisted and re-solves through the real API.
    await page.reload();
    await expect(page.getByTestId("feature-row")).toContainText("Sketch1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => countSketchInkPixels(page), { timeout: 15_000 })
      .toBeGreaterThan(40);
  });

  test("a closed profile with a spline edge extrudes into a body", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spline boss");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 360 },
      { x: 940, y: 600 },
    );

    // Bottom edge: a spline hump from (0,0) to (40,0). Double-click finishes
    // (the 4th click both places its point and commits the curve).
    await page.keyboard.press("s");
    await clickPlane(page, at, { x: 0, y: 0 });
    await clickPlane(page, at, { x: 13, y: 6 });
    await clickPlane(page, at, { x: 27, y: 6 });
    await dblclickPlane(page, at, { x: 40, y: 0 });
    await expect(page.getByTestId("sketch-save")).toContainText("1 entity");

    // Close the loop with three lines back to the spline's start.
    await page.keyboard.press("l");
    await clickPlane(page, at, { x: 40, y: 0 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await clickPlane(page, at, { x: 40, y: 25 });
    await clickPlane(page, at, { x: 0, y: 25 });
    await clickPlane(page, at, { x: 0, y: 25 });
    await clickPlane(page, at, { x: 0, y: 0 });
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // Persist the profile, then extrude it via the UI.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    const extrudeAction = page.getByTestId("new-extrude");
    await expect(extrudeAction).toBeEnabled();
    await extrudeAction.click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.getByTestId("extrude-distance").press("Enter");

    // The spline-bounded solid renders and reaches the inspector.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);
    const volume = await page.getByTestId("prop-volume").innerText();
    expect(Number.parseFloat(volume.replace(/[^\d.]/g, ""))).toBeGreaterThan(0);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-spline-extrude.png`,
    });
  });
});

test.describe("sketch spline — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("spline tool stays reachable; founder screenshot", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Spline laptop");
    await page.goto(`/parts/${part.id}`);

    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 520, y: 320 },
      { x: 760, y: 540 },
    );
    await expect(page.getByTestId("tool-spline")).toBeVisible();
    await page.keyboard.press("s");
    await clickPlane(page, at, { x: -18, y: 0 });
    await clickPlane(page, at, { x: -4, y: 12 });
    await clickPlane(page, at, { x: 10, y: -10 });
    await clickPlane(page, at, { x: 22, y: 4 });
    await expect(page.getByTestId("spline-count")).toContainText(
      "4 fit points",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-spline-laptop.png`,
    });
  });
});
