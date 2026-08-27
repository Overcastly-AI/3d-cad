import { expect, test } from "./fixtures";

import { createPlateWithHoleViaApi } from "./assemblyFlow";
import { seedSession } from "./support";

/**
 * Drafting an ASSEMBLY on a sheet, through the real UI.
 *
 * The wire has projected the solved assembly compound since 2026-07-24, and no
 * user could reach it: the drawing setup band offered PARTS only, so an
 * assembly-sourced sheet could not be created at all. This spec walks the path
 * a user walks — assembly workspace → Drawing → source picker → Lay out — and
 * insists on the two things that separate "the frame rendered" from "the
 * assembly was drafted":
 *
 *  - the picker OFFERS the assembly (grouped under "Assemblies") and arrives
 *    with it already selected from the workspace hand-off;
 *  - the placed front view carries REAL HLR EDGES. An assembly sheet composes
 *    down a different server path than a part sheet, and it runs no
 *    client-side evaluate at all, so an empty frame and a full one look the
 *    same to any assertion that only checks the view exists.
 */

test.describe("Drawings — an assembly on a sheet", () => {
  test("open a drawing from the assembly and lay out its standard views", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const partA = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Bracket plate",
    );
    const partB = await createPlateWithHoleViaApi(
      page,
      account.token,
      "Cover plate",
    );

    // --- An assembly of A x2 + B x1, built through the UI ------------------
    await page.goto("/assemblies");
    await page.getByTestId("create-assembly-name").fill("Drafted rig");
    await page.getByTestId("create-assembly-name").press("Enter");
    const row = page
      .getByTestId("assembly-row")
      .filter({ hasText: "Drafted rig" });
    await expect(row).toBeVisible();
    await row.getByTestId("assembly-open").click();
    await expect(page).toHaveURL(/\/assemblies\/[0-9a-f-]+$/);
    const assemblyId = new URL(page.url()).pathname.split("/").pop() as string;

    await page.getByTestId("add-instance").click();
    await expect(page.getByTestId("add-instance-panel")).toBeVisible();
    const cellA = page.getByTestId(`add-instance-part-${partA.id}`);
    const cellB = page.getByTestId(`add-instance-part-${partB.id}`);
    for (let n = 1; n <= 2; n++) {
      await cellA.click();
      await expect(page.getByTestId("instance-row")).toHaveCount(n, {
        timeout: 20_000,
      });
    }
    await cellB.click();
    await expect(page.getByTestId("instance-row")).toHaveCount(3, {
      timeout: 20_000,
    });
    await page.getByTestId("add-instance-done").click();

    // --- The way onto paper is ON the assembly band, not in a menu ---------
    const draft = page.getByTestId("assembly-drawing");
    await expect(draft).toBeEnabled();
    await draft.click();
    await expect(page).toHaveURL(/\/drawings\/[0-9a-f-]+\?source=/, {
      timeout: 20_000,
    });

    // --- The source picker offers BOTH registers, assembly pre-selected ----
    const picker = page.getByTestId("drawing-part-select");
    await expect(picker).toBeVisible();
    // Pre-selected from the hand-off: no hunting for the assembly you were
    // just looking at.
    await expect(picker).toHaveValue(assemblyId);
    // It OFFERS the assembly under its own heading, alongside the parts —
    // read from the DOM so a select that merely accepts the value (but never
    // showed it) cannot pass.
    const offered = await picker.evaluate((el) => {
      const select = el as HTMLSelectElement;
      return Array.from(select.querySelectorAll("optgroup")).map((group) => ({
        label: group.label,
        values: Array.from(group.querySelectorAll("option")).map(
          (option) => (option as HTMLOptionElement).value,
        ),
      }));
    });
    expect(offered.map((group) => group.label)).toEqual([
      "Parts",
      "Assemblies",
    ]);
    expect(offered[0]?.values).toEqual(
      expect.arrayContaining([partA.id, partB.id]),
    );
    expect(offered[1]?.values).toEqual([assemblyId]);

    // --- Lay out: the assembly compound is projected server-side -----------
    await page.getByTestId("drawing-autolayout").click();
    const front = page.locator('[data-testid="drawing-view"]').first();
    await expect(front).toBeVisible({ timeout: 60_000 });

    // REAL HLR EDGES, not an empty frame. The composer places `<line>` /
    // `<circle>` / `<polyline>` ink inside each view group; an assembly whose
    // solve or projection failed composes a view with none.
    const edgeCount = await front.evaluate(
      (group) => group.querySelectorAll("line, circle, polyline, path").length,
    );
    expect(edgeCount).toBeGreaterThan(8);
    // And the ink has real extent — a degenerate view would draw at a point.
    const box = await front.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(20);
    expect(box!.height).toBeGreaterThan(10);
    // The band's readout names the ASSEMBLY, so the sheet says what it drafts.
    await expect(page.getByTestId("drawing-part-readout")).toHaveText(
      "Drafted rig",
    );
    // And the Views panel counts what was actually DRAWN. An assembly sheet
    // runs no client-side evaluate, so this readout reported "0 edges" over a
    // sheet full of geometry until it learned to read the placed views — a
    // confidently wrong number is worse than no number (mandate 3a(c)).
    await expect(
      page.locator('[data-testid="drawing-view-row"][data-view="front"]'),
    ).toContainText(/[1-9]\d* edges/);
  });

  test.describe("the Drawing action fits the small-laptop band", () => {
    test.use({ viewport: { width: 1280, height: 800 } });

    test("the Document group is inside the frame and nothing scrolls sideways", async ({
      page,
    }) => {
      await seedSession(page);
      await page.goto("/assemblies");
      await page.getByTestId("create-assembly-name").fill("Narrow band");
      await page.getByTestId("create-assembly-name").press("Enter");
      const row = page
        .getByTestId("assembly-row")
        .filter({ hasText: "Narrow band" });
      await expect(row).toBeVisible();
      await row.getByTestId("assembly-open").click();

      const draft = page.getByTestId("assembly-drawing");
      await expect(draft).toBeVisible();
      const box = await draft.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(1280);
      // Adding a group must never make the app scroll horizontally — the whole
      // point of the band's measured label tier.
      const scroll = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(scroll.scrollWidth).toBeLessThanOrEqual(scroll.clientWidth);
    });
  });
});
