import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #5 (5b): the revolve authoring UI. The revolve params need PRECISE,
 * offset-from-axis geometry to make a clean annular body (an annulus is the
 * canonical revolve — a rectangle spun about a parallel axis it clears), so the
 * profile sketch is seeded through the real gateway API — the same seam
 * `extrude-body.spec.ts` uses — and everything that is #5b (the axis pick, the
 * angle, add/cut, the edit → live rebuild, the error surfacing) is driven
 * through the real browser against the real stack (gateway + documents +
 * geometry, no mocks).
 */

/** A vertical construction line at x=0 plus a rectangle offset from it. */
function annulusSketchParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      { id: "e1", kind: "line", start: { x: 10, y: 0 }, end: { x: 20, y: 0 } },
      { id: "e2", kind: "line", start: { x: 20, y: 0 }, end: { x: 20, y: 15 } },
      {
        id: "e3",
        kind: "line",
        start: { x: 20, y: 15 },
        end: { x: 10, y: 15 },
      },
      { id: "e4", kind: "line", start: { x: 10, y: 15 }, end: { x: 10, y: 0 } },
      {
        id: "axis",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: 0, y: 15 },
        construction: true,
      },
    ],
    constraints: [],
  };
}

/** A rectangle straddling the x=0 axis — revolving it self-intersects. */
function straddlingSketchParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      { id: "e1", kind: "line", start: { x: -5, y: 0 }, end: { x: 5, y: 0 } },
      { id: "e2", kind: "line", start: { x: 5, y: 0 }, end: { x: 5, y: 15 } },
      { id: "e3", kind: "line", start: { x: 5, y: 15 }, end: { x: -5, y: 15 } },
      { id: "e4", kind: "line", start: { x: -5, y: 15 }, end: { x: -5, y: 0 } },
      {
        id: "axis",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: 0, y: 15 },
        construction: true,
      },
    ],
    constraints: [],
  };
}

/**
 * A HALF-PROFILE open ONLY along the axis, closed by the construction
 * centerline (the SolidWorks/Fusion idiom the geometry `1605a11` shipped): the
 * three REAL edges e1..e3 form an open chain touching sketch x=0 at both ends,
 * and the construction line `axis` (0,20)→(0,0) closes it. Revolving 360° about
 * that centerline yields a SOLID cylinder r12 h20 — matching the geometry
 * golden `revolve-centerline-cylinder-r12-h20`. This is the case the annulus
 * (already fully closed) does NOT exercise: here the CENTERLINE is load-bearing.
 */
function halfProfileSketchParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 12, y: 0 } },
      { id: "e2", kind: "line", start: { x: 12, y: 0 }, end: { x: 12, y: 20 } },
      { id: "e3", kind: "line", start: { x: 12, y: 20 }, end: { x: 0, y: 20 } },
      {
        id: "axis",
        kind: "line",
        start: { x: 0, y: 20 },
        end: { x: 0, y: 0 },
        construction: true,
      },
    ],
    constraints: [],
  };
}

/** An open profile (three edges) offset from the axis — no closed wire. */
function openSketchParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      { id: "e1", kind: "line", start: { x: 10, y: 0 }, end: { x: 20, y: 0 } },
      { id: "e2", kind: "line", start: { x: 20, y: 0 }, end: { x: 20, y: 15 } },
      {
        id: "e3",
        kind: "line",
        start: { x: 20, y: 15 },
        end: { x: 10, y: 15 },
      },
      {
        id: "axis",
        kind: "line",
        start: { x: 0, y: 0 },
        end: { x: 0, y: 15 },
        construction: true,
      },
    ],
    constraints: [],
  };
}

/** POST one feature at the tree tip via the real gateway. */
async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/** Seed a part carrying only the profile sketch (the revolve is authored in-UI). */
async function seedSketchedPart(
  page: Page,
  name: string,
  sketchParams: unknown,
): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: sketchParams },
    expected_tree_version: 0,
  });
  return part;
}

/** The lit aluminium solid + B-rep edges paint far more shades than ground. */
async function expectRenderedBody(page: Page): Promise<void> {
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

/** The body volume (mm³) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

// Annulus r10–20, h15: V(360°) = π·(20² − 10²)·15 = 4500π ≈ 14137.17 mm³.
const FULL_VOLUME = 4500 * Math.PI;

// Half-profile cylinder r12, h20: V(360°) = π·12²·20 = 2880π ≈ 9047.79 mm³.
const CYLINDER_VOLUME = 2880 * Math.PI;

test.describe("revolve authoring", () => {
  test("pick axis → body; edit angle 360 → 180 → body halves", async ({
    page,
  }) => {
    const part = await seedSketchedPart(page, "Washer", annulusSketchParams());
    await page.goto(`/parts/${part.id}`);

    // The Revolve action lights up once the sketch has solved.
    const revolveAction = page.getByTestId("new-revolve");
    await expect(revolveAction).toBeEnabled({ timeout: 30_000 });
    await revolveAction.click();

    // The keyboard-first form: the construction centerline is the default axis,
    // the angle is focused at 360°, add is selected. Enter creates.
    const editor = page.getByTestId("revolve-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("revolve-axis")).toHaveValue("axis");
    await expect(page.getByTestId("revolve-angle")).toHaveValue("360");
    await expect(page.getByTestId("revolve-op-add")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("revolve-angle").press("Enter");

    // The revolved annular solid renders and its mass properties reach the
    // inspector — a real 4500π mm³ body from the evaluate→mesh path.
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    const volume360 = await bodyVolume(page);
    expect(volume360).toBeGreaterThan(FULL_VOLUME * 0.98);
    expect(volume360).toBeLessThan(FULL_VOLUME * 1.02);

    // Edit the revolve: select its tree row, retarget the editor, 360 → 180.
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("revolve-angle")).toHaveValue("360");
    await page.getByTestId("revolve-angle").fill("180");
    await page.getByTestId("revolve-angle").press("Enter");

    // The body updates live — a half turn is half the material.
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBeLessThan(FULL_VOLUME * 0.6);
    await expectRenderedBody(page);
    expect(await bodyVolume(page)).toBeGreaterThan(FULL_VOLUME * 0.4);
  });

  test("construction centerline closes a half-profile → solid cylinder", async ({
    page,
  }) => {
    // The capability geometry `1605a11` shipped, proven end-to-end in-app: the
    // profile's real edges are OPEN along sketch x=0; only the construction
    // centerline closes them. If the axis picker excluded construction lines
    // this half-profile could never be revolved — so this is the regression
    // guard that the centerline is a first-class (in fact default) axis choice.
    const part = await seedSketchedPart(
      page,
      "Spindle",
      halfProfileSketchParams(),
    );
    await page.goto(`/parts/${part.id}`);

    const revolveAction = page.getByTestId("new-revolve");
    await expect(revolveAction).toBeEnabled({ timeout: 30_000 });
    await revolveAction.click();

    const editor = page.getByTestId("revolve-editor");
    await expect(editor).toBeVisible();
    // The construction centerline is the DEFAULT axis, and its label names it.
    const axis = page.getByTestId("revolve-axis");
    await expect(axis).toHaveValue("axis");
    await expect(axis.locator("option[value='axis']")).toContainText(
      "construction",
    );
    await expect(page.getByTestId("revolve-angle")).toHaveValue("360");
    await page.getByTestId("revolve-angle").press("Enter");

    // The half-profile, closed by the centerline, sweeps a full solid cylinder.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    const volume = await bodyVolume(page);
    expect(volume).toBeGreaterThan(CYLINDER_VOLUME * 0.98);
    expect(volume).toBeLessThan(CYLINDER_VOLUME * 1.02);
  });

  test("axis through the profile surfaces axis_intersects_profile", async ({
    page,
  }) => {
    const part = await seedSketchedPart(
      page,
      "Straddle",
      straddlingSketchParams(),
    );
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-revolve").click();
    await page.getByTestId("revolve-angle").press("Enter");

    // The create succeeds; the rebuild fails, loud and located under the row.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const error = page.getByTestId("feature-error-1");
    await expect(error).toBeVisible();
    await expect(error).toContainText("axis_intersects_profile");
    await expect(page.getByTestId("body-inspector")).toBeHidden({
      timeout: 30_000,
    });
  });

  test("open profile surfaces profile_not_closed", async ({ page }) => {
    const part = await seedSketchedPart(page, "Open turn", openSketchParams());
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-revolve").click();
    await page.getByTestId("revolve-angle").press("Enter");

    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const error = page.getByTestId("feature-error-1");
    await expect(error).toBeVisible();
    await expect(error).toContainText("profile_not_closed");
  });

  test("founder screenshot: revolved body + revolve editor (desktop)", async ({
    page,
  }) => {
    const part = await seedSketchedPart(page, "Washer", annulusSketchParams());
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-revolve").click();
    await page.getByTestId("revolve-angle").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    // Re-open the editor on the revolve so the form, the body, and the tree are
    // all in one frame.
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("revolve-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/revolve-desktop.png` });
  });
});

test.describe("revolve authoring small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("form + tree stay usable at laptop width; founder screenshot", async ({
    page,
  }) => {
    const part = await seedSketchedPart(page, "Washer", annulusSketchParams());
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-revolve").click();
    await page.getByTestId("revolve-angle").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);

    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);

    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("revolve-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/revolve-laptop.png` });
  });
});

/**
 * Founder before/after of the marquee capability: a HALF-PROFILE closed by a
 * construction centerline, revolved about that centerline. "Before" is the
 * open half-profile with the centerline visible in the viewport (no body yet);
 * "after" is the solid cylinder with the revolve editor open on its
 * construction-line axis. Captured at 1440 and 1280×800.
 */
for (const width of [1440, 1280] as const) {
  test.describe(`revolve construction-centerline founder shots (${width})`, () => {
    test.use({ viewport: { width, height: width === 1280 ? 800 : 900 } });

    test("half-profile + centerline → revolved cylinder", async ({ page }) => {
      const part = await seedSketchedPart(
        page,
        "Spindle",
        halfProfileSketchParams(),
      );
      await page.goto(`/parts/${part.id}`);

      // BEFORE — the open half-profile with its construction centerline drawn on
      // the axis; the sketch layer renders while no body exists yet.
      const revolveAction = page.getByTestId("new-revolve");
      await expect(revolveAction).toBeEnabled({ timeout: 30_000 });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/revolve-centerline-sketch-${width}.png`,
      });

      // AFTER — revolve about the construction centerline, then re-open the
      // editor so the axis pick, the solid, and the tree share one frame.
      await revolveAction.click();
      await expect(page.getByTestId("revolve-axis")).toHaveValue("axis");
      await page.getByTestId("revolve-angle").press("Enter");
      await expect(page.getByTestId("body-inspector")).toBeVisible();
      await expectRenderedBody(page);
      await page.getByTestId("feature-select-1").click();
      await expect(page.getByTestId("revolve-editor")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/revolve-centerline-body-${width}.png`,
      });
    });
  });
}
