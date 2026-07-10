import { expect, test } from "@playwright/test";

import { expectRenderedModel, SCREENSHOT_DIR, seedSession } from "./support";

// The modeler now lives behind sign-in; every spec gets a fresh session.
test.beforeEach(async ({ page }) => {
  await seedSession(page);
});

test.describe("first light", () => {
  test("renders the OCCT-tessellated cube with real mass properties (desktop)", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page.getByTestId("status-chip")).toHaveText("First light");
    await expect(page.getByRole("heading", { name: "LOFT" })).toBeVisible();

    // Real properties for the 10×20×30 mm box, from the X-Loft-Properties header.
    await expect(page.getByTestId("prop-volume")).toContainText("6,000");
    await expect(page.getByTestId("prop-area")).toContainText("2,200");
    await expect(page.getByTestId("prop-centroid")).toContainText("5, 10, 15");
    await expect(page.getByTestId("prop-extents")).toContainText(
      "10 × 20 × 30",
    );
    await expect(page.getByTestId("prop-faces")).toContainText("6");
    await expect(page.getByTestId("prop-triangles")).toContainText("12");

    await expectRenderedModel(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/first-light-desktop.png`,
    });
  });

  test("re-tessellates when dimensions are edited (keyboard-first)", async ({
    page,
  }) => {
    await page.goto("/");
    await expectRenderedModel(page);

    // Per-keystroke typing into the dimension cells, then Enter to apply.
    for (const [axis, value] of [
      ["x", "40"],
      ["y", "12"],
      ["z", "8"],
    ] as const) {
      const field = page.getByTestId(`dim-${axis}`);
      await field.click();
      await field.fill("");
      await field.pressSequentially(value, { delay: 40 });
    }
    await page.getByTestId(`dim-z`).press("Enter");

    // 40 × 12 × 8 = 3840 mm³, tessellated server-side and re-rendered.
    await expect(page.getByTestId("prop-volume")).toContainText("3,840", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("prop-extents")).toContainText("40 × 12 × 8");
    await expectRenderedModel(page);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/first-light-edited.png` });
  });

  test("rejects invalid dimensions with a visible message", async ({
    page,
  }) => {
    await page.goto("/");
    const field = page.getByTestId("dim-x");
    await field.click();
    await field.fill("");
    await field.pressSequentially("-5", { delay: 40 });
    await page.getByTestId("dim-apply").click();
    await expect(page.getByRole("alert")).toHaveText(
      "Enter a value above 0 mm",
    );
  });
});

test.describe("small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("shell stays viewport-dominant at 1280×800", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("prop-volume")).toContainText("6,000");
    await expectRenderedModel(page);
    const viewport = page.getByTestId("viewport");
    const box = await viewport.boundingBox();
    expect(box).not.toBeNull();
    // The model owns the pixels: viewport > half the window width.
    expect(box?.width ?? 0).toBeGreaterThan(640);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/first-light-laptop.png` });
  });
});
