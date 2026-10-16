import { expect, test, type Page } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { createPartViaApi, seedSession } from "./support";

/**
 * ASM-FAILED-PART-API, the drawing half: a drawing of an assembly whose crank
 * arm (placed twice) failed to build draws the frame alone, and nothing on the
 * sheet says the arms are missing. The check strip names the part and the
 * bodies the views leave out, and its row opens the part.
 *
 * The arm is a part with no body (no features) — the bike's
 * `profile_unsupported` arm is the same to a drawing: its occurrences have no
 * body, so no view can draw them.
 */

type Auth = Record<string, string>;

/** An assembly of the frame (grounded) and two crank arms, via the gateway. */
async function bikeViaApi(
  page: Page,
  auth: Auth,
  frameId: string,
  armId: string,
): Promise<string> {
  const created = await page.request.post("/api/v1/assemblies", {
    data: { name: "Bike" },
    headers: auth,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const { id, doc_version } = (await created.json()) as {
    id: string;
    doc_version: number;
  };
  let version = doc_version;
  for (const [partId, name, grounded] of [
    [frameId, "Frame <1>", true],
    [armId, "Crank arm <1>", false],
    [armId, "Crank arm <2>", false],
  ] as const) {
    const added = await page.request.post(
      `/api/v1/assemblies/${id}/instances`,
      {
        data: {
          expected_version: version,
          ref_document_id: partId,
          ref_document_kind: "part",
          name,
          grounded,
        },
        headers: auth,
      },
    );
    expect(added.ok(), await added.text()).toBe(true);
    version = ((await added.json()) as { doc_version: number }).doc_version;
  }
  return id;
}

test.describe("an assembly drawing with a part that failed to build", () => {
  test("the check strip names the crank arm and opens it", async ({ page }) => {
    const { token } = await seedSession(page);
    const auth = { Authorization: `Bearer ${token}` };
    const frame = await createPlateWithHoleViaApi(page, token, "Frame");
    const arm = await createPartViaApi(page, token, "Crank arm");
    const assemblyId = await bikeViaApi(page, auth, frame.id, arm.id);

    await page.goto(`/assemblies/${assemblyId}`);
    await page.getByTestId("assembly-drawing").click();
    await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+\?source=/, {
      timeout: 30_000,
    });
    await page.getByTestId("drawing-autolayout").click();
    await expect(page.locator('[data-testid="drawing-view"]')).toHaveCount(4, {
      timeout: 60_000,
    });

    const strip = page.getByTestId("sheet-issue-strip");
    const row = strip.locator(
      '[data-testid="sheet-issue-row"][data-issue-code="part_failed"]',
    );
    await expect(row).toHaveCount(1, { timeout: 30_000 });
    await expect(row).toHaveAttribute("data-part-document-id", arm.id);
    await expect(row.getByTestId("sheet-issue-message")).toContainText(
      "Crank arm failed to build, so these views leave out 2 bodies",
    );
    await expect(row.getByTestId("sheet-issue-severity")).toHaveText("WARNING");

    await row.getByTestId("sheet-issue-open-part").click();
    await expect(page).toHaveURL(new RegExp(`/parts/${arm.id}`));
  });
});
