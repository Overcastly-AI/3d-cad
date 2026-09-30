import { expect, test, type Page } from "./fixtures";

import { createFeature, evaluateViaApi, rectangleSketch } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * TWIST-TO-SWEEP, web half: twist lives on Sweep ("twist along path", as in
 * Fusion 360 and SolidWorks), not on Extrude. Driven through the real browser
 * against the real stack:
 *
 *  1. a twisted sweep along a straight path, typed in the Sweep editor's
 *     Twist field, lands in the stored row and builds the twisted solid;
 *  2. the same twist along an ARC path is refused (`twist_path_unsupported`)
 *     and the refusal reads in the Sweep editor, in its error slot;
 *  3. DATA SAFETY: a stored legacy twisted extrude (a twist and its axis
 *     point) keeps both, byte for byte, when its distance is edited in the
 *     Extrude editor, which shows the twist as a read-only legacy note.
 *
 * The profile is the golden's 20 mm square centred on the origin; the paths
 * are the goldens' (a 30 mm line up +Z, and the r40 quarter arc on XZ).
 */

test.use({ viewport: { width: 1280, height: 800 } });

/** A 20 mm square centred on the XY origin: the path pierces its centre. */
const SQUARE_20_CENTRED = rectangleSketch(-10, -10, 20, 20);

/** One straight line up +Z from the profile's centre (drawn on XZ). */
const PATH_UP_30 = {
  plane: { kind: "datum_plane", plane: "XZ" },
  entities: [
    { id: "p1", kind: "line", start: { x: 0, y: 0 }, end: { x: 0, y: 30 } },
  ],
  constraints: [],
};

/** The refusal golden's quarter arc, r40 on XZ, leaving the origin along +Z. */
const ARC_PATH_R40 = {
  plane: { kind: "datum_plane", plane: "XZ" },
  entities: [
    {
      id: "a1",
      kind: "arc",
      center: { x: 40, y: 0 },
      start: { x: 40, y: 40 },
      end: { x: 0, y: 0 },
    },
  ],
  constraints: [],
};

interface FeatureRow {
  id: string;
  feature: { type: string; params: Record<string, unknown> };
}

async function rows(
  page: Page,
  token: string,
  partId: string,
): Promise<FeatureRow[]> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return ((await response.json()) as { features: FeatureRow[] }).features;
}

async function paramsOf(
  page: Page,
  token: string,
  partId: string,
  type: string,
): Promise<Record<string, unknown> | null> {
  const row = (await rows(page, token, partId)).find(
    (f) => f.feature.type === type,
  );
  return row?.feature.params ?? null;
}

/** The first number in an inspector cell (it carries its label and unit). */
async function firstNumber(page: Page, testId: string): Promise<number> {
  const text = await page.getByTestId(testId).innerText();
  const match = text.match(/-?\d[\d,]*(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

/** Seed the square profile and a path sketch; the sweep is authored in-UI. */
async function seedProfileAndPath(
  page: Page,
  name: string,
  path: unknown,
): Promise<{ partId: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  const profile = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20_CENTRED },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: path },
    expected_tree_version: profile.tree_version,
  });
  return { partId: part.id, token: account.token };
}

/** Open a new sweep (Sketch1 profile, Sketch2 path) with a typed twist. */
async function openSweepWithTwist(page: Page, twist: string): Promise<void> {
  const action = page.getByTestId("new-sweep");
  await expect(action).toBeEnabled({ timeout: 30_000 });
  await action.click();
  await expect(page.getByTestId("sweep-editor")).toBeVisible();
  const field = page.getByTestId("sweep-twist");
  await expect(field).toHaveValue("");
  await field.fill(twist);
}

test.describe("twist along path (TWIST-TO-SWEEP)", () => {
  test("a twisted sweep on a straight path: stored, built, and re-opened", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { partId, token } = await seedProfileAndPath(
      page,
      "Twisted bar",
      PATH_UP_30,
    );
    await page.goto(`/parts/${partId}`);
    await openSweepWithTwist(page, "30");
    await expect(page.getByTestId("sweep-twist-note")).toContainText(
      "Right-hand",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/twist-to-sweep-sweep-editor-after-1280.png`,
    });
    await page.getByTestId("sweep-twist").press("Enter");

    // The row carries the signed angle the field held, and nothing else new.
    await expect
      .poll(
        async () =>
          (await paramsOf(page, token, partId, "sweep"))?.["twist_angle_deg"],
      )
      .toBe(30);
    expect(await evaluateViaApi(page, token, partId)).toEqual([
      "ok",
      "ok",
      "ok",
    ]);

    // The solid: a twist turns every slice of the square about the path, so
    // the volume is the straight bar's (20 x 20 x 30) while the footprint
    // grows past 20 (the turned top's corners stand outside the square).
    await expect(page.getByTestId("body-inspector")).toBeVisible();
    await expect
      .poll(() => firstNumber(page, "prop-volume"), { timeout: 30_000 })
      .toBeCloseTo(12_000, 0);
    expect(await firstNumber(page, "prop-extents")).toBeGreaterThan(20.5);

    // Re-open: the field shows the stored twist, exactly.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("sweep-twist")).toHaveValue("30");
    await expect(page.getByTestId("sweep-rebuild-error")).toHaveCount(0);
  });

  test("the same twist on an ARC path is refused, and the editor says why", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const { partId, token } = await seedProfileAndPath(
      page,
      "Bent twist",
      ARC_PATH_R40,
    );
    await page.goto(`/parts/${partId}`);
    await openSweepWithTwist(page, "45");
    await page.getByTestId("sweep-twist").press("Enter");

    // Saved as asked (the row is the user's), refused at rebuild with the
    // typed code; the kernel's own sentence reads at the editor seat.
    await expect
      .poll(
        async () =>
          (await paramsOf(page, token, partId, "sweep"))?.["twist_angle_deg"],
      )
      .toBe(45);
    const evaluated = await page.request.post(
      `/api/v1/parts/${partId}/evaluate`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const body = (await evaluated.json()) as {
      features: { status: string; error?: { code: string } | null }[];
    };
    expect(body.features[2]?.status).toBe("error");
    expect(body.features[2]?.error?.code).toBe("twist_path_unsupported");
    await expect(page.getByTestId("rebuild-notice")).toContainText(
      /perpendicular/i,
      { timeout: 30_000 },
    );

    // Open the sweep: the reason is in ITS card, in the flag slot, naming
    // both cures.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("sweep-twist")).toHaveValue("45");
    const alert = page.getByTestId("sweep-rebuild-error");
    await expect(alert).toBeVisible();
    await expect(alert).toHaveAttribute("role", "alert");
    await expect(alert).toContainText("A twist needs a straight path");
    await expect(alert).toContainText("set the twist to 0");

    // Following the advice cures it: twist 0 is an untwisted arc sweep,
    // which builds (the golden's body).
    await page.getByTestId("sweep-twist").fill("0");
    await expect(alert).toHaveCount(0);
    await page.getByTestId("sweep-twist").press("Enter");
    await expect
      .poll(async () =>
        Object.keys((await paramsOf(page, token, partId, "sweep")) ?? {}),
      )
      .not.toContain("twist_angle_deg");
    expect(await evaluateViaApi(page, token, partId)).toEqual([
      "ok",
      "ok",
      "ok",
    ]);
  });

  test("a legacy twisted extrude keeps its twist and axis when its distance is edited", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Legacy twist");
    const profile = await createFeature(page, account.token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: SQUARE_20_CENTRED },
      expected_tree_version: 0,
    });
    const legacy = {
      profile: { kind: "feature", feature_id: profile.feature.id },
      distance_mm: 30,
      operation: "add",
      direction: "normal",
      merge: true,
      twist_angle_deg: 30,
      twist_center: { x: 1.25, y: -2.5 },
    };
    await createFeature(page, account.token, part.id, {
      name: "Extrude1",
      feature: { type: "extrude", version: 1, params: legacy },
      expected_tree_version: profile.tree_version,
    });
    await page.goto(`/parts/${part.id}`);
    await page.getByTestId("feature-select-1").click({ timeout: 30_000 });
    await expect(page.getByTestId("extrude-editor")).toBeVisible();

    // No Twist field, no axis control; the stored twist is said, read-only.
    await expect(page.getByTestId("extrude-twist")).toHaveCount(0);
    await expect(page.getByTestId("extrude-twist-centre-origin")).toHaveCount(
      0,
    );
    await expect(page.getByRole("slider", { name: /twist/i })).toHaveCount(0);
    await expect(page.getByTestId("extrude-legacy-twist")).toHaveText(
      "Twisted 30° about (1.25, -2.5) mm (legacy). Use Sweep for new twists.",
    );
    // The ghost still turns the way the rebuild will.
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-twist-deg",
      "30",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/twist-to-sweep-extrude-editor-after-1280.png`,
    });

    // Edit the distance, save: both twist fields come back unchanged.
    const distance = page.getByTestId("extrude-distance");
    await distance.fill("40");
    await distance.press("Enter");
    await expect
      .poll(
        async () =>
          (await paramsOf(page, account.token, part.id, "extrude"))?.[
            "distance_mm"
          ],
      )
      .toBe(40);
    expect(await paramsOf(page, account.token, part.id, "extrude")).toEqual({
      ...legacy,
      distance_mm: 40,
    });
    expect(await evaluateViaApi(page, account.token, part.id)).toEqual([
      "ok",
      "ok",
    ]);
  });
});
