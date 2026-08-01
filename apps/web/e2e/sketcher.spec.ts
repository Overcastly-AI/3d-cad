import { expect, test, type Page } from "./fixtures";

import {
  countSketchInkPixels,
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Sketcher v1 (BACKLOG #4): plane pick → entity authoring → save → the
 * SOLVED sketch rendered from the evaluate payload → reload persists.
 * Real stack: gateway + documents + geometry, no mocks.
 */

/** Solved scribe ink along a ~1000 px rectangle perimeter, AA-discounted. */
const MIN_INK_PIXELS = 200;

async function drawRectangle(
  page: Page,
  a: { x: number; y: number },
  b: { x: number; y: number },
): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(a.x, a.y);
  await page.mouse.move(b.x, b.y);
  await page.mouse.click(b.x, b.y);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
}

test.describe("sketcher", () => {
  test("plane pick → rectangle → save → solved render → reload persists", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bracket plate");
    await page.goto(`/parts/${part.id}`);

    await expect(page.getByTestId("part-name")).toHaveText("Bracket plate");
    await expect(page.getByTestId("feature-row")).toHaveCount(0);

    // Enter sketch mode; pick the XY plane via the keyboard-path cells.
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await expect(page.getByTestId("sketch-dro")).toBeVisible();

    // Draw a rectangle (two clicks, live DRO readout in between).
    await page.keyboard.press("r");
    await page.mouse.click(650, 420);
    await page.mouse.move(950, 620);
    await expect(page.getByTestId("dro-x")).toHaveText(/^[+-]\d+\.\d{2}$/);
    await expect(page.getByTestId("dro-y")).toHaveText(/^[+-]\d+\.\d{2}$/);
    await page.mouse.click(950, 620);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");

    // Save: the feature write (201) and the evaluate round-trip, intercepted.
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
        data: { kind: string; entities: Array<{ kind: string }> } | null;
      }>;
    };
    expect(evalBody.features).toHaveLength(1);
    expect(evalBody.features[0]?.status).toBe("ok");
    expect(evalBody.features[0]?.data?.kind).toBe("solved_sketch");
    expect(evalBody.features[0]?.data?.entities).toHaveLength(4);
    expect(
      evalBody.features[0]?.data?.entities.every((e) => e.kind === "line"),
    ).toBe(true);

    // Sketch mode exited; the tree shows the persisted, solved feature.
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(1);
    await expect(page.getByTestId("feature-row")).toContainText("Sketch1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");

    // The canvas really shows the solved scribe ink (pixel check).
    await expect
      .poll(() => countSketchInkPixels(page), { timeout: 15_000 })
      .toBeGreaterThan(MIN_INK_PIXELS);

    // Reload: the sketch persisted and re-solves through the real API.
    await page.reload();
    await expect(page.getByTestId("feature-row")).toContainText("Sketch1");
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect
      .poll(() => countSketchInkPixels(page), { timeout: 15_000 })
      .toBeGreaterThan(MIN_INK_PIXELS);
  });

  test("keyboard-first: tool shortcuts, snap toggle, Escape cascade", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Keyboard part");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XZ").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XZ");

    // L/R/C/A arm tools.
    for (const [key, tool] of [
      ["l", "line"],
      ["c", "circle"],
      ["a", "arc"],
      ["r", "rect"],
    ] as const) {
      await page.keyboard.press(key);
      await expect(page.getByTestId(`tool-${tool}`)).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    }

    // G toggles the 1 mm grid snap.
    await expect(page.getByTestId("dro-snap")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.keyboard.press("g");
    await expect(page.getByTestId("dro-snap")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await page.keyboard.press("g");

    // Escape cascade: placement → tool → exit.
    await page.mouse.click(800, 500); // rect corner pending
    await page.keyboard.press("Escape"); // cancels the placement
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.keyboard.press("Escape"); // back to select
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    // Nothing was ever committed here, so this sketch has no work to lose and
    // Escape still backs out of it (FB-13: with entities drawn it would not).
    await page.keyboard.press("Escape"); // exits the empty sketch
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  });

  test("founder screenshot: sketch mode with entities drawn (desktop)", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bracket plate");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await drawRectangle(page, { x: 650, y: 420 }, { x: 950, y: 620 });

    // A circle mid-placement: brass rubber band + crosshair in the frame.
    await page.keyboard.press("c");
    await page.mouse.click(1060, 420);
    await page.mouse.move(1130, 470);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketcher-v1-desktop.png`,
    });
  });
});

test.describe("sketcher small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("sketch mode stays viewport-dominant; founder screenshot", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Bracket plate");
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await drawRectangle(page, { x: 560, y: 340 }, { x: 820, y: 520 });
    await page.keyboard.press("c");
    await page.mouse.click(920, 350);
    await page.mouse.move(970, 390);

    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sketcher-v1-laptop.png` });
  });
});
