import { expect, test, type Page } from "./fixtures";

import {
  authorBoltMates,
  balloonX,
  pickDispatch,
  setupTwoInstances,
  waitForSolved,
} from "./assemblyFlow";
import { distinctCanvasColors, SCREENSHOT_DIR } from "./support";

/**
 * Assemblies v1 #6 — the assembly viewport + mate authoring exit gate. Driven
 * end to end through a real browser against the real stack (gateway +
 * documents + geometry, no mocks): a plate-with-a-hole part is built once via
 * the API, instanced twice into a fresh assembly through the UI, the first
 * auto-grounded, and the free instance is seeded APART. Then a Coincident mate
 * (a face on each) and a Concentric mate (a hole edge on each) are authored by
 * picking geometry in the viewport; each re-solve is asserted, and the free
 * instance is asserted to have MOVED from its authored seed to the solved
 * (bolted) pose — the snap-on-solve. This is "bolt two parts together and see
 * it," the v1 MVP DoD. (The seeding/authoring plumbing lives in
 * `assemblyFlow.ts`, shared with the assembly undo/redo spec.)
 */

async function runAssemblyFlow(
  page: Page,
  seedShot?: string,
): Promise<{ idA: string; idB: string }> {
  const { idA, idB, seedX } = await setupTwoInstances(page);

  // Founder before-shot: the two parts seeded APART, pre-mate.
  if (seedShot) {
    await page.mouse.move(1400, 900);
    await page.screenshot({ path: seedShot });
  }

  // 3) Coincident (flush) + Concentric (bolt axes) authored in the viewport.
  await authorBoltMates(page, idA, idB);

  // 4) The signature assertion: the free instance MOVED from its seed to the
  //    solved (bolted) pose — the snap-on-solve. The concentric solve pulls the
  //    free plate's hole axis onto the grounded plate's, so its x collapses from
  //    the seed (~80) toward the bolt (~20). Poll so the async re-solve lands
  //    (both mates leave the status "Under constrained", so we watch the pose,
  //    not the label).
  await expect
    .poll(() => balloonX(page, idB), { timeout: 30_000 })
    .toBeLessThan(seedX - 20);

  // The solve is not broken (never conflicting / not converged for this bolt;
  // a single coincident+concentric correctly leaves one spin DOF about the axis).
  const status = await waitForSolved(page);
  expect(status).not.toMatch(/Conflicting|Not converged/);

  // Two plates still render at the solved poses.
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);

  return { idA, idB };
}

test.describe("Assemblies v1 — bolt two parts and see it", () => {
  test("instance twice, mate coincident + concentric, snap to solved", async ({
    page,
  }) => {
    await runAssemblyFlow(
      page,
      `${SCREENSHOT_DIR}/assembly-seed-apart-desktop.png`,
    );
    // Founder after-shot: the bolted assembly, tree + viewport + solve title block.
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-bolted-desktop.png`,
    });
  });
});

test.describe("Assemblies v1 — parametric mates (distance / angle)", () => {
  test("distance mate: pick two faces, set a value, commit, re-solve", async ({
    page,
  }) => {
    const { idA, idB } = await setupTwoInstances(page);

    // Arm the distance tool and pick a face on each part (the same face pair a
    // coincident collects — the residual reads the normals + a point on each).
    await page.getByTestId("mate-distance").click();
    await expect(page.getByTestId("mate-hud")).toHaveAttribute(
      "data-mate-tool",
      "distance",
    );
    await pickDispatch(
      page,
      `[data-testid^="mate-face-${idA}-"][aria-label*="12.5, 10 "]`,
    );
    await pickDispatch(
      page,
      `[data-testid^="mate-face-${idB}-"][aria-label*="12.5, 0 "]`,
    );

    // The value field appears (not auto-committed) with the sensible default,
    // and is editable before commit — keyboard-first.
    const value = page.getByTestId("mate-value");
    await expect(value).toBeVisible();
    await expect(value).toHaveValue("10");
    await value.fill("20");
    await page.getByTestId("mate-commit").click();

    // The distance mate lands in the tree and the assembly re-solves cleanly.
    const mateRow = page
      .getByTestId("mate-row")
      .filter({ hasText: "Distance" });
    await expect(mateRow).toHaveCount(1, { timeout: 30_000 });
    const status = await waitForSolved(page);
    expect(status).not.toMatch(/Conflicting|Not converged/);
    // Both plates still render at their solved poses.
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);
  });
});

test.describe("Assemblies v1 — small laptop (1280×800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the bolt holds at 1280×800; founder screenshot", async ({ page }) => {
    await runAssemblyFlow(
      page,
      `${SCREENSHOT_DIR}/assembly-seed-apart-laptop.png`,
    );
    const box = await page.getByTestId("viewport").boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(480);
    // Park clear of the bottom-right reference cube (viewport makeover).
    await page.mouse.move(1080, 770);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/assembly-bolted-laptop.png`,
    });
  });
});
