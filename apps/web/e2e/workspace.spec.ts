import { expect, test } from "./fixtures";

import {
  createPartViaApi,
  openRowActions,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * WORKSPACE MANAGEMENT — the drawer on your tenth document, driven through a
 * real browser against the real stack (gateway + documents, no mocks).
 *
 * The four verbs a register needs once you have more than one thing in it —
 * SEARCH, RENAME, DUPLICATE, DELETE — plus SORT. Each assertion is aimed at the
 * defect class this repo keeps re-finding, "a surface asserting something it
 * does not know", rather than at the happy path:
 *
 *  - the count readout is checked AGAINST the rows actually on screen, so a
 *    "4 of 12" that disagreed with the list would fail;
 *  - the rename is re-read from a RELOADED page, so a row that painted the
 *    typed name locally without the server accepting it would fail;
 *  - the duplicate is checked to have really copied the tree (the copy's own
 *    feature list is fetched from the API) and to have been named by the
 *    server, not the client;
 *  - the delete refusal is checked to NAME the referring assembly, because
 *    "in use" is not an actionable refusal.
 */

/** Every register row's visible name, in the order they are drawn. */
async function rowNames(page: import("@playwright/test").Page) {
  return page.getByTestId("part-open").allTextContents();
}

test.describe("workspace management", () => {
  test("searches, sorts, renames, duplicates and refuses an unsafe delete", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    // Filed in this order, so FILED ascending is a known order and NAME
    // ascending is a different one.
    await createPartViaApi(page, token, "Rib 10");
    await createPartViaApi(page, token, "Rib 2");
    await createPartViaApi(page, token, "Bracket plate");

    await page.goto("/");
    await expect(page.getByTestId("parts-table")).toBeVisible();
    await expect(page.getByTestId("part-row")).toHaveCount(3);
    await expect(page.getByTestId("parts-count")).toHaveText("3 parts");

    // --- SEARCH ----------------------------------------------------------
    await page.getByTestId("parts-filter").fill("rib");
    await expect(page.getByTestId("part-row")).toHaveCount(2);
    // The readout is a fraction of the WHOLE drawer, and it agrees with the
    // rows on screen — an empty-looking register is legible, not alarming.
    await expect(page.getByTestId("parts-count")).toHaveText("2 of 3 parts");

    await page.getByTestId("parts-filter").fill("nothing-matches-this");
    await expect(page.getByTestId("part-row")).toHaveCount(0);
    await expect(page.getByTestId("parts-count")).toHaveText("0 of 3 parts");
    await expect(page.getByTestId("parts-no-matches")).toContainText(
      "No parts match",
    );
    await page.getByTestId("parts-no-matches-clear").click();
    await expect(page.getByTestId("part-row")).toHaveCount(3);

    // --- SORT ------------------------------------------------------------
    // Default is FILED ascending: the order documents returned them in.
    expect(await rowNames(page)).toEqual(["Rib 10", "Rib 2", "Bracket plate"]);
    await page.getByTestId("parts-sort-name").click();
    // Numeric collation — "Rib 2" before "Rib 10", which lexical sorting gets
    // backwards and a drawer of numbered parts would never forgive.
    expect(await rowNames(page)).toEqual(["Bracket plate", "Rib 2", "Rib 10"]);
    await expect(page.getByTestId("parts-sort-name-header")).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    await page.getByTestId("parts-sort-name").click();
    expect(await rowNames(page)).toEqual(["Rib 10", "Rib 2", "Bracket plate"]);
    await expect(page.getByTestId("parts-sort-name-header")).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    await page.getByTestId("parts-sort-filed").click();

    // --- RENAME ----------------------------------------------------------
    const bracketRow = page
      .getByTestId("part-row")
      .filter({ hasText: "Bracket plate" });
    await openRowActions(bracketRow);
    await bracketRow.getByTestId("part-rename").click();
    await bracketRow.getByTestId("part-rename-name").fill("Bracket plate v2");
    await bracketRow.getByTestId("part-rename-name").press("Enter");
    await expect(
      page.getByTestId("part-row").filter({ hasText: "Bracket plate v2" }),
    ).toHaveCount(1);

    // Re-read from a fresh load: the name is on the SERVER, not painted locally.
    await page.reload();
    await expect(
      page.getByTestId("part-row").filter({ hasText: "Bracket plate v2" }),
    ).toHaveCount(1);
    await expect(
      page.getByTestId("part-row").filter({ hasText: /^Bracket plate$/ }),
    ).toHaveCount(0);
  });

  test("duplicates a part with its whole tree, named by the server", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const auth = { Authorization: `Bearer ${token}` };
    const part = await createPartViaApi(page, token, "Plate");
    // One feature, so "copied the TREE" is a checkable claim rather than a
    // header copy that looks the same in the register.
    const sketch = await page.request.post(
      `/api/v1/parts/${part.id}/features`,
      {
        headers: auth,
        data: {
          name: "Sketch1",
          expected_tree_version: 0,
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
              ],
              constraints: [],
            },
          },
        },
      },
    );
    expect(sketch.ok()).toBeTruthy();

    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(1);
    await openRowActions(page);
    await page.getByTestId("part-duplicate").click();

    // The SERVER names the copy; the register renders what came back.
    await expect(page.getByTestId("part-row")).toHaveCount(2);
    const copyRow = page
      .getByTestId("part-row")
      .filter({ hasText: "Plate copy" });
    await expect(copyRow).toHaveCount(1);
    // A brand-new document has never been built, and the register says so
    // rather than inheriting the original's verdict.
    await expect(copyRow.getByTestId("part-health")).toHaveAttribute(
      "data-health",
      "never",
    );

    // ...and the copy really carries the tree, with its own feature id.
    const copyId = await copyRow.getAttribute("data-part-id");
    const copyTree = await page.request.get(
      `/api/v1/parts/${copyId}/features`,
      { headers: auth },
    );
    const copied = (await copyTree.json()) as {
      features: { id: string; name: string }[];
    };
    expect(copied.features.map((f) => f.name)).toEqual(["Sketch1"]);
    const sourceTree = (await (
      await page.request.get(`/api/v1/parts/${part.id}/features`, {
        headers: auth,
      })
    ).json()) as { features: { id: string }[] };
    expect(copied.features[0]!.id).not.toBe(sourceTree.features[0]!.id);

    // Duplicating again counts up, so two copies never collide.
    const firstRow = page.getByTestId("part-row").first();
    await openRowActions(firstRow);
    await firstRow.getByTestId("part-duplicate").click();
    await expect(
      page.getByTestId("part-row").filter({ hasText: "Plate copy 2" }),
    ).toHaveCount(1);
  });

  test("refuses to delete a part an assembly uses, and names the assembly", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const auth = { Authorization: `Bearer ${token}` };
    const part = await createPartViaApi(page, token, "Plate");
    const assembly = await page.request.post("/api/v1/assemblies", {
      headers: auth,
      data: { name: "gearbox" },
    });
    expect(assembly.ok()).toBeTruthy();
    const assemblyId = ((await assembly.json()) as { id: string }).id;
    const instance = await page.request.post(
      `/api/v1/assemblies/${assemblyId}/instances`,
      {
        headers: auth,
        data: {
          expected_version: 0,
          ref_document_id: part.id,
          ref_document_kind: "part",
          name: "Plate <1>",
          grounded: true,
        },
      },
    );
    expect(instance.ok()).toBeTruthy();

    await page.goto("/");
    await openRowActions(page);
    await page.getByTestId("part-delete").click();
    await page.getByTestId("part-delete-confirm").click();

    const blocked = page.getByTestId("part-blocked");
    await expect(blocked).toBeVisible();
    // NAMED, not summarised: the user's next action is to open that assembly.
    await expect(blocked.getByTestId("part-dependent")).toHaveText(["gearbox"]);
    await expect(blocked.getByTestId("part-dependent")).toHaveAttribute(
      "data-dependent-kind",
      "assembly",
    );
    // Nothing was deleted, and the register still holds the part.
    await page.getByTestId("part-delete-cancel").click();
    await page.reload();
    await expect(page.getByTestId("part-row")).toHaveCount(1);
  });

  test("founder shot — the register with search, sort and row verbs", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    for (const name of [
      "Bracket plate",
      "Motor mount",
      "Rib 2",
      "Rib 10",
      "Spacer — 4 mm",
    ]) {
      await createPartViaApi(page, token, name);
    }
    await page.goto("/");
    await expect(page.getByTestId("part-row")).toHaveCount(5);

    for (const width of [1440, 1366]) {
      await page.setViewportSize({ width, height: 900 });
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/workspace-register-${width}.png`,
      });
    }

    // ...and the same drawer with the filter narrowing it, so the fraction
    // readout is in the record beside the unfiltered tally.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByTestId("parts-filter").fill("rib");
    await expect(page.getByTestId("parts-count")).toHaveText("2 of 5 parts");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/workspace-register-filtered-1440.png`,
    });
  });
});
