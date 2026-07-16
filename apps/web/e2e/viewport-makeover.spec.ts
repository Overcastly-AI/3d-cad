import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Makeover Batch 1 — "the scene is a place" (UI-REVIEW 2026-07-16, P0-1/2/3/4
 * + the assembly fit race). Functional coverage for the view navigation that
 * landed with it, plus the founder before/after evidence captures:
 *
 *  - the view rail + numeric snaps + Home drive the REAL camera (asserted via
 *    the rig's `data-view` / `data-camera-pos` settle stamps on the viewport);
 *  - the full-bleed shell: the canvas spans the workspace and the tree +
 *    inspector float over it (collapsible);
 *  - the assembly opens FRAMED: the fit waits for loaded geometry (no race).
 */

const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

/** Build a 40×25×10 plate with a Ø10 through hole via the real gateway. */
async function createPlateWithHoleViaApi(
  page: Page,
  token: string,
  name: string,
): Promise<{ id: string }> {
  const part = await page.request.post("/api/v1/parts", {
    data: { name },
    headers: auth(token),
  });
  if (!part.ok()) {
    throw new Error(`create part failed: ${part.status()}`);
  }
  const partId = ((await part.json()) as { id: string }).id;
  const sketch = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            {
              id: "e1",
              kind: "line",
              start: { x: 0, y: 0 },
              end: { x: 40, y: 0 },
            },
            {
              id: "e2",
              kind: "line",
              start: { x: 40, y: 0 },
              end: { x: 40, y: 25 },
            },
            {
              id: "e3",
              kind: "line",
              start: { x: 40, y: 25 },
              end: { x: 0, y: 25 },
            },
            {
              id: "e4",
              kind: "line",
              start: { x: 0, y: 25 },
              end: { x: 0, y: 0 },
            },
            {
              id: "e5",
              kind: "circle",
              center: { x: 20, y: 12.5 },
              radius: 5,
              construction: false,
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: auth(token),
  });
  if (!sketch.ok()) {
    throw new Error(`sketch failed: ${sketch.status()}`);
  }
  const sketchBody = (await sketch.json()) as {
    feature: { id: string };
    tree_version: number;
  };
  const extrude = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketchBody.feature.id },
          distance_mm: 10,
          operation: "add",
          direction: "normal",
        },
      },
      expected_tree_version: sketchBody.tree_version,
    },
    headers: auth(token),
  });
  if (!extrude.ok()) {
    throw new Error(`extrude failed: ${extrude.status()}`);
  }
  return { id: partId };
}

/** The settled camera position from the rig's QA stamp. */
async function cameraPos(page: Page): Promise<[number, number, number]> {
  const raw =
    (await page.getByTestId("viewport").getAttribute("data-camera-pos")) ?? "";
  const parts = raw.split(",").map((v) => Number.parseFloat(v));
  return [parts[0] ?? NaN, parts[1] ?? NaN, parts[2] ?? NaN];
}

async function settledView(page: Page): Promise<string> {
  return (await page.getByTestId("viewport").getAttribute("data-view")) ?? "";
}

test.describe("view navigation (Batch 1, P0-2)", () => {
  test("view rail, numeric snaps and Home drive the camera", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Nav plate",
    );
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    // The initial auto-fit stamps the rig's settle hook.
    await expect
      .poll(() => settledView(page), { timeout: 20_000 })
      .toBe("fit-auto");
    await expect(page.getByTestId("view-bar")).toBeVisible();

    // FRONT from the rail: the camera settles on the +Z axis of the subject.
    await page.getByTestId("view-front").click();
    await expect
      .poll(() => settledView(page), { timeout: 10_000 })
      .toBe("front");
    const front = await cameraPos(page);
    expect(front[2]).toBeGreaterThan(Math.abs(front[0]));
    expect(front[2]).toBeGreaterThan(Math.abs(front[1]));

    // TOP from the keyboard (2): the camera settles above the subject.
    await page.keyboard.press("2");
    await expect.poll(() => settledView(page), { timeout: 10_000 }).toBe("top");
    const top = await cameraPos(page);
    expect(top[1]).toBeGreaterThan(Math.abs(top[0]));
    expect(top[1]).toBeGreaterThan(Math.abs(top[2]));

    // RIGHT (3): dominant +X.
    await page.keyboard.press("3");
    await expect
      .poll(() => settledView(page), { timeout: 10_000 })
      .toBe("right");
    const right = await cameraPos(page);
    expect(right[0]).toBeGreaterThan(Math.abs(right[1]));
    expect(right[0]).toBeGreaterThan(Math.abs(right[2]));

    // HOME: back to the studio iso; FIT (0) re-frames without changing view.
    await page.keyboard.press("Home");
    await expect
      .poll(() => settledView(page), { timeout: 10_000 })
      .toBe("home");
    await page.keyboard.press("0");
    await expect.poll(() => settledView(page), { timeout: 10_000 }).toBe("fit");

    // The keys never fire while typing in a field (dimension entry is safe).
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.getByTestId("extrude-distance").click();
    await page.keyboard.press("1");
    expect(await settledView(page)).toBe("fit");
  });

  test("panels float over a full-bleed canvas and collapse", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Shell plate",
    );
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });

    // Full bleed: the canvas spans (nearly) the whole window width.
    const viewportBox = await page.getByTestId("viewport").boundingBox();
    const window = page.viewportSize();
    expect(viewportBox?.width ?? 0).toBeGreaterThanOrEqual(
      (window?.width ?? 0) - 2,
    );

    // The tree collapses to a corner tab and comes back.
    await page.getByTestId("panel-collapse-tree").click();
    await expect(page.getByTestId("feature-tree")).toHaveCount(0);
    await page.getByTestId("panel-expand-tree").click();
    await expect(page.getByTestId("feature-tree")).toBeVisible();

    // The inspector collapses too.
    await page.getByTestId("panel-collapse-inspector").click();
    await expect(page.getByTestId("body-inspector")).toHaveCount(0);
    await page.getByTestId("panel-expand-inspector").click();
    await expect(page.getByTestId("body-inspector")).toBeVisible();
  });
});

test.describe("assembly fit (Batch 1, P1)", () => {
  test("the assembly opens framed once meshes load", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Fit plate",
    );
    const created = await page.request.post("/api/v1/assemblies", {
      data: { name: "Framed" },
      headers: auth(account.token),
    });
    expect(created.ok()).toBe(true);
    const assemblyId = ((await created.json()) as { id: string }).id;
    // Two instances, the second seeded 80 mm apart — the combined bounds are
    // 120 mm wide, the case the stale-bounds fit race used to clip.
    for (const [index, x] of [0, 80].entries()) {
      const instance = await page.request.post(
        `/api/v1/assemblies/${assemblyId}/instances`,
        {
          data: {
            name: `Fit plate <${index + 1}>`,
            ref_document_id: part.id,
            ref_document_kind: "part",
            grounded: index === 0,
            placement: {
              position: { x, y: 0, z: 0 },
              orientation: { w: 1, x: 0, y: 0, z: 0 },
            },
            expected_version: index,
          },
          headers: auth(account.token),
        },
      );
      expect(instance.ok()).toBe(true);
    }

    await page.goto(`/assemblies/${assemblyId}`);
    await expect(page.getByTestId("instance-row")).toHaveCount(2, {
      timeout: 20_000,
    });
    // The fit key is the LOADED-geometry set: the camera re-frames when the
    // meshes land, so the settled radius covers the 120 mm span (a fit of a
    // single plate would settle ≈ 85 mm out; the pair needs > 150).
    await expect
      .poll(() => settledView(page), { timeout: 30_000 })
      .toBe("fit-auto");
    await expect
      .poll(
        async () => {
          const [x, y, z] = await cameraPos(page);
          return Math.hypot(x - 60, y, z);
        },
        { timeout: 20_000 },
      )
      .toBeGreaterThan(150);
    // Both balloons on-screen (the audit shot had instance 2 clipped off).
    const balloons = page.locator('[data-testid^="assembly-balloon-"]');
    await expect(balloons).toHaveCount(2, { timeout: 20_000 });
    const size = page.viewportSize();
    for (let i = 0; i < 2; i += 1) {
      const box = await balloons.nth(i).boundingBox();
      expect(box).not.toBeNull();
      expect(box?.x ?? -1).toBeGreaterThan(0);
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThan(size?.width ?? 0);
    }
  });
});

test.describe("founder evidence — Batch 1 after-shots", () => {
  async function captureBoth(
    page: Page,
    name: string,
    prepare: (page: Page) => Promise<void>,
  ): Promise<void> {
    await page.setViewportSize({ width: 1440, height: 900 });
    await prepare(page);
    // Park over empty bench — never a toolbar button (a hover tooltip in a
    // founder shot) and clear of the view rail / reference cube.
    await page.mouse.move(480, 720);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/viewport-makeover-${name}-desktop.png`,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/viewport-makeover-${name}-laptop.png`,
    });
  }

  test("empty part — the scene reads as a place", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Fresh part");
    await captureBoth(page, "empty", async () => {
      await page.goto(`/parts/${part.id}`);
      await expect(page.getByTestId("feature-tree")).toBeVisible();
      await expect(page.getByTestId("view-bar")).toBeVisible();
      await page.waitForTimeout(600);
    });
  });

  test("body — studio shading + grid to the horizon", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Bracket plate",
    );
    await captureBoth(page, "body", async () => {
      await page.goto(`/parts/${part.id}`);
      await expect(page.getByTestId("body-inspector")).toBeVisible({
        timeout: 30_000,
      });
      await expect
        .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
        .toBeGreaterThan(24);
    });
  });

  test("sketch mode — full-bleed sheet", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Sketch part");
    await captureBoth(page, "sketch", async (p) => {
      await p.goto(`/parts/${part.id}`);
      await p.getByTestId("new-sketch").click();
      await p.getByTestId("plane-XY").click();
      await expect(p.getByTestId("sketch-step")).toHaveText("On XY");
      await p.keyboard.press("r");
      await p.mouse.click(650, 420);
      await p.mouse.move(980, 640);
      await p.mouse.click(980, 640);
      await expect(p.getByTestId("sketch-save")).toContainText("4 entities");
    });
    // Leave sketch mode cleanly so the teardown never races the auto-save.
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
  });

  test("assembly — two instances framed", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPlateWithHoleViaApi(page, account.token, "Plate");
    const created = await page.request.post("/api/v1/assemblies", {
      data: { name: "Two plates" },
      headers: auth(account.token),
    });
    const assemblyId = ((await created.json()) as { id: string }).id;
    for (const [index, x] of [0, 80].entries()) {
      await page.request.post(`/api/v1/assemblies/${assemblyId}/instances`, {
        data: {
          name: `Plate <${index + 1}>`,
          ref_document_id: part.id,
          ref_document_kind: "part",
          grounded: index === 0,
          placement: {
            position: { x, y: 0, z: 0 },
            orientation: { w: 1, x: 0, y: 0, z: 0 },
          },
          expected_version: index,
        },
        headers: auth(account.token),
      });
    }
    await captureBoth(page, "assembly", async (p) => {
      await p.goto(`/assemblies/${assemblyId}`);
      await expect(p.getByTestId("instance-row")).toHaveCount(2, {
        timeout: 20_000,
      });
      await expect
        .poll(() => settledView(p), { timeout: 30_000 })
        .toBe("fit-auto");
      await expect
        .poll(() => distinctCanvasColors(p), { timeout: 20_000 })
        .toBeGreaterThan(24);
    });
  });
});
