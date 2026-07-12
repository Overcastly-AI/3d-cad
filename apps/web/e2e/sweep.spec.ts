import { expect, test, type Page } from "@playwright/test";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * BACKLOG #7 (7b): the sweep authoring UI, driven through the real browser
 * against the real stack (gateway + documents + geometry, no mocks). Sweep is
 * the first feature that references TWO earlier sketches by id — a closed
 * PROFILE and an open PATH — so both sketches are seeded through the real
 * gateway API (the seam revolve-ui.spec.ts uses) and the sweep itself is
 * authored in-UI: pick the profile + path in the ref selectors, add → the
 * swept solid renders and the feature lands in the tree. The geometry matches
 * the committed golden `sweep-circle-r8-h30` (an r8 circle on XY swept up a
 * 30 mm vertical path on XZ → a cylinder, V = pi*64*30).
 */

/** An r8 circle on XY — the closed profile the golden sweeps. */
function circleProfileParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [{ id: "c1", kind: "circle", center: { x: 0, y: 0 }, radius: 8 }],
    constraints: [],
  };
}

/** A vertical open line up +Z (drawn on XZ) — a valid single OPEN path wire. */
function openPathParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XZ" },
    entities: [
      { id: "p1", kind: "line", start: { x: 0, y: 0 }, end: { x: 0, y: 30 } },
    ],
    constraints: [],
  };
}

/** A CLOSED circle on XZ — illegal as a path (a path must be an open wire). */
function closedPathParams(): unknown {
  return {
    plane: { kind: "datum_plane", plane: "XZ" },
    entities: [
      { id: "p1", kind: "circle", center: { x: 0, y: 20 }, radius: 10 },
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

/** Seed a part carrying a profile sketch + a path sketch; the sweep is in-UI. */
async function seedSweepPart(
  page: Page,
  name: string,
  pathParams: unknown,
): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: circleProfileParams() },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: pathParams },
    expected_tree_version: 1,
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

// Cylinder r8, L30: V = pi*r^2*L = pi*64*30 ≈ 6031.86 mm³.
const CYLINDER_VOLUME = Math.PI * 64 * 30;

test.describe("sweep authoring", () => {
  test("pick profile + path → swept body renders and lands in the tree", async ({
    page,
  }) => {
    const part = await seedSweepPart(page, "Shaft", openPathParams());
    await page.goto(`/parts/${part.id}`);

    // Sweep lights up once two sketches have solved.
    const sweepAction = page.getByTestId("new-sweep");
    await expect(sweepAction).toBeEnabled({ timeout: 30_000 });
    await sweepAction.click();

    // The ref picker defaults: Sketch1 (the circle) as profile, Sketch2 (the
    // open path) as path, add selected. Enter creates — keyboard-first.
    const editor = page.getByTestId("sweep-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("sweep-op-add")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByTestId("sweep-profile").press("Enter");

    // The swept cylinder renders and its mass properties reach the inspector —
    // a real pi*64*30 mm³ body from the evaluate→mesh path.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    const volume = await bodyVolume(page);
    expect(volume).toBeGreaterThan(CYLINDER_VOLUME * 0.98);
    expect(volume).toBeLessThan(CYLINDER_VOLUME * 1.02);

    // The sweep is editable: its row re-opens the editor with its refs seeded.
    await page.getByTestId("feature-select-2").click();
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("sweep-profile")).toHaveValue(/./);
    await expect(page.getByTestId("sweep-path")).toHaveValue(/./);
  });

  test("a closed sketch as the path surfaces sweep_path_closed", async ({
    page,
  }) => {
    const part = await seedSweepPart(page, "Bad path", closedPathParams());
    await page.goto(`/parts/${part.id}`);

    await page.getByTestId("new-sweep").click();
    await expect(page.getByTestId("sweep-editor")).toBeVisible();
    // The path note is honest about the constraint before the user even commits.
    await expect(page.getByTestId("sweep-path-note")).toContainText("open");
    await page.getByTestId("sweep-submit").click();

    // The create succeeds; the rebuild fails, loud and located under the row.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const error = page.getByTestId("feature-error-2");
    await expect(error).toBeVisible();
    await expect(error).toContainText("sweep_path_closed");
    await expect(page.getByTestId("body-inspector")).toBeHidden({
      timeout: 30_000,
    });
  });

  test("founder screenshot: swept body + sweep editor (desktop)", async ({
    page,
  }) => {
    const part = await seedSweepPart(page, "Shaft", openPathParams());
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sweep").click();
    await page.getByTestId("sweep-profile").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);
    // Re-open the editor on the sweep so the form, the body, and the tree are
    // all in one frame.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("sweep-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sweep-desktop.png` });
  });
});

test.describe("sweep authoring small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("form + tree stay usable at laptop width; founder screenshot", async ({
    page,
  }) => {
    const part = await seedSweepPart(page, "Shaft", openPathParams());
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("new-sweep").click();
    await page.getByTestId("sweep-profile").press("Enter");
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expectRenderedBody(page);

    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(560);

    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("sweep-editor")).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/sweep-laptop.png` });
  });
});
