import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/**
 * THE BODIES PANEL AND EXPORT AGREE ABOUT WHAT EXISTS
 * (FAILED-EXTRUDE-BODIES-GHOST-1).
 *
 * The panel listed every body the TREE describes. A first extrude that failed
 * was still "Body 1", with a row to hide and recolour and a Combine picker
 * entry, while the export band said nothing was built. Both surfaces now read
 * the evaluate result: the panel lists the bodies the kernel's last-good state
 * holds, which is the state the exported file is written from.
 *
 * The failure is a real kernel refusal, not a mock: an extrude of an OPEN
 * sketch (one line) has no profile to sweep.
 */

async function seedExtrude(
  page: Page,
  token: string,
  partId: string,
  sketchId: string,
  expected: number,
  name: string,
  extra: Record<string, unknown>,
): Promise<number> {
  const made = await createFeature(page, token, partId, {
    name,
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketchId },
        distance_mm: 30,
        operation: "add",
        direction: "normal",
        ...extra,
      },
    },
    expected_tree_version: expected,
  });
  return made.tree_version;
}

async function seedSketch(
  page: Page,
  token: string,
  partId: string,
  expected: number,
  name: string,
  params: unknown,
) {
  return createFeature(page, token, partId, {
    name,
    feature: { type: "sketch", version: 1, params },
    expected_tree_version: expected,
  });
}

/** One line: nothing closed, so an extrude of it cannot build. */
const OPEN_LINE = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 40, y: 0 }, end: { x: 60, y: 0 } },
  ],
  constraints: [],
};

test.describe("a failed extrude is not a body", () => {
  test("the only body failed: no Bodies panel, and Export says no body", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Failed column");
    const open = await seedSketch(
      page,
      account.token,
      part.id,
      0,
      "Sketch1",
      OPEN_LINE,
    );
    await seedExtrude(
      page,
      account.token,
      part.id,
      open.feature.id,
      open.tree_version,
      "Extrude1",
      {},
    );
    await page.goto(`/parts/${part.id}`);

    const band = page.getByTestId("part-export-band-controls");
    await expect(band).toHaveAttribute("data-export-state", "no-body", {
      timeout: 60_000,
    });
    await expect(page.getByTestId("body-row")).toHaveCount(0);
    await expect(page.getByTestId("bodies-panel")).toHaveCount(0);
  });

  test("a second body failed: the panel keeps the one the file holds", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Two columns");
    const square = await seedSketch(
      page,
      account.token,
      part.id,
      0,
      "Sketch1",
      SQUARE_20,
    );
    const afterFirst = await seedExtrude(
      page,
      account.token,
      part.id,
      square.feature.id,
      square.tree_version,
      "Extrude1",
      {},
    );
    const open = await seedSketch(
      page,
      account.token,
      part.id,
      afterFirst,
      "Sketch2",
      OPEN_LINE,
    );
    await seedExtrude(
      page,
      account.token,
      part.id,
      open.feature.id,
      open.tree_version,
      "Extrude2",
      { merge: false },
    );
    await page.goto(`/parts/${part.id}`);

    const band = page.getByTestId("part-export-band-controls");
    await expect(band).toHaveAttribute("data-export-state", "feature-error", {
      timeout: 60_000,
    });
    const rows = page.getByTestId("body-row");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("Extrude1");
    await expect(page.getByTestId("bodies-section")).toContainText(
      "Bodies · 1",
    );
  });
});
