import { expect, test, type Page } from "./fixtures";

import { createFeature, rectangleSketch, seedCube } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * MATERIALS — the UI half (#57b, docs/design/materials.md §6), driven through
 * the real browser against the real stack (gateway + documents + geometry, no
 * mocks), so the mass on screen is one OCCT measured every time.
 *
 * What this pins is HONESTY, not a number: the panel refused to be titled MASS
 * PROPERTIES while it had no mass, the absence reads as absence rather than
 * `0 g`, the picker's options and the density come from `GET /api/v1/materials`
 * (nothing client-side may know a density), and a multi-body part with one
 * unassigned body NAMES that body instead of going quiet.
 *
 * The numbers are hand-derived from the library densities, never recorded
 * output: a 20 mm cube is 8000 mm³, so aluminium 6061 (2.70 g/cm³) weighs
 * 8000 × 2.7e-3 = 21.6 g and steel 1018 (7.87 g/cm³) weighs 62.96 g.
 */

const ALUMINIUM_G = 21.6;
const STEEL_G = 62.96;

/** Screenshot name prefix — overridden to capture the BEFORE shots at HEAD. */
const SHOT = process.env.LOFT_SHOT_PREFIX ?? "materials-after";

async function waitSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Seed a part with two NON-touching 20 mm cubes (a 10 mm gap on X). */
async function seedTwoBodies(
  page: Page,
): Promise<{ partId: string; token: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Two cubes");
  const sketchA = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, 20, 20),
    },
    expected_tree_version: 0,
  });
  const extrudeA = await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchA.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
    expected_tree_version: sketchA.tree_version,
  });
  const sketchB = await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(30, 0, 20, 20),
    },
    expected_tree_version: extrudeA.tree_version,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude2",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchB.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: false,
      },
    },
    expected_tree_version: sketchB.tree_version,
  });
  return { partId: part.id, token: account.token };
}

test.describe("materials — mass is claimed only once a material exists", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("assigning a material turns PROPERTIES into MASS PROPERTIES", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Mass cube");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await waitSolved(page);

    // BEFORE any material: the panel says what it actually shows, there is no
    // mass row at all, and nothing anywhere reads `0 g`.
    await expect(
      page.getByRole("group", { name: "Properties", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("group", { name: "Mass properties" }),
    ).toHaveCount(0);
    await expect(page.getByTestId("prop-mass")).toHaveCount(0);
    await expect(page.getByTestId("material-hint")).toContainText(
      "Assign a material",
    );
    await expect(page.getByTestId("body-inspector")).not.toContainText("0 g");

    // The picker's options are SERVED — the library route, not a client table.
    const picker = page.getByTestId("material-default-select");
    await expect(picker).toHaveValue("");
    await expect(picker.locator("option")).toContainText([
      "No material",
      "Steel (AISI 1018)",
    ]);

    // Assign aluminium: the material change invalidates the recorded evaluate,
    // so the part re-solves and the mass appears — 8000 mm³ × 2.70 g/cm³.
    await picker.selectOption("aluminium_6061");
    await waitSolved(page);
    await expect(
      page.getByRole("group", { name: "Mass properties" }),
    ).toBeVisible();
    await expect(page.getByTestId("prop-mass")).toContainText(
      String(ALUMINIUM_G),
      { timeout: 30_000 },
    );
    await expect(page.getByTestId("prop-mass")).toContainText("g");
    // The density behind that number, straight from the served library.
    await expect(page.getByTestId("material-density")).toContainText("2,700");
    // A single-material body's centre of mass IS its volume centroid — both are
    // reported, named apart, because on a mixed part they are not the same.
    await expect(page.getByTestId("prop-center-of-mass")).toContainText(
      "10, 10, 10",
    );
    await expect(page.getByTestId("prop-centroid")).toContainText("10, 10, 10");

    // Switch to steel: the SAME solid, a different mass — no client-side
    // arithmetic could produce this, it is the kernel re-deriving from density.
    await picker.selectOption("steel_1018");
    await waitSolved(page);
    await expect(page.getByTestId("prop-mass")).toContainText(String(STEEL_G), {
      timeout: 30_000,
    });

    // Clear it: mass becomes UNKNOWN again — absent, never zero.
    await picker.selectOption("");
    await waitSolved(page);
    await expect(page.getByTestId("prop-mass")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(
      page.getByRole("group", { name: "Mass properties" }),
    ).toHaveCount(0);
    await expect(page.getByTestId("body-inspector")).not.toContainText("0 g");
  });

  test("an inch document reads the mass in POUNDS", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Imperial cube");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await waitSolved(page);

    await page.getByTestId("document-unit-select").selectOption("in");
    await page
      .getByTestId("material-default-select")
      .selectOption("steel_1018");
    await waitSolved(page);
    // 62.96 g = 0.1388 lb — the derived unit follows the LENGTH unit, with no
    // second setting to keep in sync.
    const mass = page.getByTestId("prop-mass");
    await expect(mass).toContainText("0.1388", { timeout: 30_000 });
    await expect(mass).toContainText("lb");
  });

  test("a part with one unassigned body NAMES it instead of going quiet", async ({
    page,
  }) => {
    const { partId } = await seedTwoBodies(page);
    await page.goto(`/parts/${partId}`);
    await waitSolved(page);

    // Override body 1 only: the part total stays null, because a partial sum
    // would under-report while looking like a complete answer.
    await page
      .getByTestId("material-body-select-1")
      .selectOption("aluminium_6061");
    await waitSolved(page);
    await expect(page.getByTestId("prop-mass")).toHaveCount(0);
    await expect(page.getByTestId("material-unassigned")).toContainText(
      "Extrude2 has no material",
      { timeout: 30_000 },
    );
    // ...while the body that DOES have one still reports its own mass.
    await expect(page.getByTestId("material-body-mass-1")).toContainText(
      "21.6",
    );
    await expect(page.getByTestId("material-body-mass-2")).toContainText("—");

    // Give the second body a different material: the total appears, and the
    // centre of MASS parts company with the volume centroid.
    await page.getByTestId("material-body-select-2").selectOption("steel_1018");
    await waitSolved(page);
    await expect(page.getByTestId("prop-mass")).toContainText("84.56", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("material-unassigned")).toHaveCount(0);
    const centroid = await page.getByTestId("prop-centroid").innerText();
    const centreOfMass = await page
      .getByTestId("prop-center-of-mass")
      .innerText();
    expect(centreOfMass).not.toBe(centroid);
    // 34180/1057 = 32.3368 mm, where the volume centroid sits at 25 mm.
    expect(centreOfMass).toContain("32.34");
    expect(centroid).toContain("25");
  });
});

/**
 * Founder shots (design mandate #4). Deliberately assertion-light so the SAME
 * test can run against HEAD (with `LOFT_SHOT_PREFIX=materials-before`) to
 * capture the panel as it was — titled MASS PROPERTIES with no mass in it.
 */
test.describe("materials — founder shots", () => {
  for (const width of [1440, 1366] as const) {
    test(`panel shots at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 768 });
      const account = await seedSession(page);
      const part = await createPartViaApi(page, account.token, "Bracket");
      await seedCube(page, account.token, part.id);
      await page.goto(`/parts/${part.id}`);
      await waitSolved(page);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/${SHOT}-${width}.png`,
      });

      // The assigned state only exists after this slice; at HEAD there is no
      // picker to drive, so the second shot is skipped rather than faked.
      const picker = page.getByTestId("material-default-select");
      if ((await picker.count()) === 0) return;
      await picker.selectOption("aluminium_6061");
      await waitSolved(page);
      await expect(page.getByTestId("prop-mass")).toBeVisible({
        timeout: 30_000,
      });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/${SHOT}-assigned-${width}.png`,
      });
    });
  }

  test("mixed-material part", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const { partId } = await seedTwoBodies(page);
    await page.goto(`/parts/${partId}`);
    await waitSolved(page);
    const picker = page.getByTestId("material-default-select");
    if ((await picker.count()) === 0) return; // HEAD has no picker to drive.
    await picker.selectOption("aluminium_6061");
    await waitSolved(page);
    await page.getByTestId("material-body-select-2").selectOption("steel_1018");
    await waitSolved(page);
    await expect(page.getByTestId("prop-mass")).toContainText("84.56", {
      timeout: 30_000,
    });
    await page.screenshot({ path: `${SCREENSHOT_DIR}/${SHOT}-mixed-1440.png` });
  });
});
