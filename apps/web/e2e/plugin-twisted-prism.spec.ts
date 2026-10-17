import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * PLUGIN-UI (RESEARCH §23), against the real stack: the twisted prism plugin
 * is an ordinary tool in the Build group, its dialog is generated from the
 * served manifest, its angle takes a formula over a part parameter, and it is
 * ONE tree row that unfolds into its members — edited, reloaded, deleted and
 * undone like any feature. A feature pinned to a version this server does not
 * have opens read-only with its version.
 */

const PLUGIN = "loft.twisted_prism";

interface Seeded {
  token: string;
  partId: string;
  sketchId: string;
  treeVersion: number;
}

/** A part with a 20 mm square sketch and an angle parameter `twist` = 45°. */
async function seedPart(page: Page, name: string): Promise<Seeded> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, name);
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const response = await page.request.put(
    `/api/v1/parts/${part.id}/parameters`,
    {
      data: {
        expected_tree_version: sketch.tree_version,
        parameters: [
          {
            id: "6f3f6b64-0000-4000-8000-00000000a1b2",
            name: "twist",
            expression: "45",
            unit: "angle",
            comment: "",
          },
        ],
      },
      headers: { Authorization: `Bearer ${account.token}` },
    },
  );
  expect(response.ok(), await response.text()).toBe(true);
  const table = (await response.json()) as { tree_version: number };
  return {
    token: account.token,
    partId: part.id,
    sketchId: sketch.feature.id,
    treeVersion: table.tree_version,
  };
}

interface StoredCustom {
  name: string;
  feature: {
    type: string;
    expressions?: Record<string, string> | null;
    params: {
      inputs: Record<string, unknown>;
      expansion: {
        role: string;
        feature: { params: Record<string, unknown> };
      }[];
    };
  };
}

async function customRows(page: Page, seeded: Seeded): Promise<StoredCustom[]> {
  const response = await page.request.get(
    `/api/v1/parts/${seeded.partId}/features`,
    { headers: { Authorization: `Bearer ${seeded.token}` } },
  );
  const tree = (await response.json()) as { features: StoredCustom[] };
  return tree.features.filter((f) => f.feature.type === "custom");
}

/** The stored sweep member's twist, i.e. what geometry builds. */
function sweepTwist(row: StoredCustom | undefined): unknown {
  return row?.feature.params.expansion.find((m) => m.role === "sweep")?.feature
    .params.twist_angle_deg;
}

/**
 * docs/screenshots/plugin-ui.png: the band AT REST (the Build group; an open
 * command folds the band to OK/Cancel, so it cannot share a frame with the
 * form) stacked over the workspace mid-edit (the generated form and the
 * unfolded tree node). Two real frames, never a composed fake state.
 */
async function saveFounderSheet(
  page: Page,
  band: Buffer,
  editing: Buffer,
): Promise<void> {
  if (!process.env.UPDATE_SCREENSHOTS) return;
  const sheet = await page.context().newPage();
  await sheet.setViewportSize({ width: 1600, height: 1102 });
  const img = (png: Buffer) =>
    `<img style="display:block" src="data:image/png;base64,${png.toString("base64")}">`;
  await sheet.setContent(
    `<body style="margin:0;background:#3a3f47">${img(band)}<div style="height:2px"></div>${img(editing)}</body>`,
  );
  await sheet.screenshot({ path: `${SCREENSHOT_DIR}/plugin-ui.png` });
  await sheet.close();
}

async function expectSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 45_000,
  });
}

test.describe("plugin UI: the twisted prism", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert from Build, drive the angle with twist*2, reload, delete and undo", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const seeded = await seedPart(page, "Plugin prism");
    await page.goto(`/parts/${seeded.partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(1);

    // The Build group lists the plugin as a tool, titled from its manifest,
    // in BUILD ▾ (the row holds the building generators).
    const build = page.getByTestId("build-tools");
    await expect(build).toBeVisible();
    await page.getByTestId("build-more").click();
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled();
    await expect(tool).toHaveAccessibleName(/^Twisted prism/);
    await tool.click();

    // The generated dialog: every input from the manifest, at its default.
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toBeVisible();
    await expect(editor).toContainText("New Twisted prism");
    await expect(page.getByTestId("plugin-input-profile")).toHaveValue(
      seeded.sketchId,
    );
    await expect(page.getByTestId("plugin-input-distance_mm")).toHaveValue(
      "10",
    );
    await expect(page.getByTestId("plugin-input-twist_angle_deg")).toHaveValue(
      "30",
    );
    // A bound is refused on the field before any round trip.
    await page.getByTestId("plugin-input-distance_mm").fill("0");
    await expect(editor).toContainText("Must be more than 0 mm.");
    await expect(page.getByTestId("plugin-submit")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await page.getByTestId("plugin-input-distance_mm").fill("20");
    // Twist about the square's centre: the path then sits on an offset plane,
    // the plugin's third member.
    await page.getByTestId("plugin-input-axis_x_mm").fill("10");
    await page.getByTestId("plugin-input-axis_y_mm").fill("10");
    await page.getByTestId("plugin-submit").click();

    // ONE row, named by the plugin, that builds.
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(1)).toContainText("Twisted prism 1");
    await expect(rows.nth(1)).toContainText("twisted prism");
    await expectSolved(page);
    await expect(rows.nth(1)).toContainText("OK");
    expect(sweepTwist((await customRows(page, seeded))[0])).toBe(30);

    // It unfolds into its members, read-only.
    await page.getByTestId("feature-unfold-1").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members).toHaveCount(3);
    await expect(members.nth(0)).toContainText("Axis plane");
    await expect(members.nth(1)).toContainText("Path");
    await expect(members.nth(2)).toContainText("Twisted sweep");
    await expect(members.nth(2)).toContainText("OK");
    // The band at rest, Build group and all, for the founder sheet below.
    await expect(build).toBeVisible();
    const band = await page.screenshot({
      clip: { x: 0, y: 0, width: 1600, height: 100 },
    });

    // Edit it like any feature: the angle takes a formula over `twist`.
    await page.getByTestId("feature-select-1").click();
    await expect(editor).toContainText("Edit Twisted prism");
    const twist = page.getByTestId("plugin-input-twist_angle_deg");
    await twist.fill("twist*2");
    await expect(twist).toHaveAttribute("data-formula", "");
    await expect(
      page.getByTestId("plugin-input-twist_angle_deg-hint"),
    ).toHaveText("= 90°");
    // The tree shares the column with the open card: bring its members up.
    await members.nth(2).scrollIntoViewIfNeeded();
    await saveFounderSheet(page, band, await page.screenshot());
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);

    // It regenerated: the formula is stored and the member twists 90°.
    const [edited] = await customRows(page, seeded);
    expect(edited?.feature.expressions).toEqual({
      "/inputs/twist_angle_deg": "twist*2",
    });
    expect(edited?.feature.params.inputs.twist_angle_deg).toBe(90);
    expect(sweepTwist(edited)).toBe(90);

    // A reload keeps it, formula and all.
    await page.reload();
    await expect(rows).toHaveCount(2);
    await expectSolved(page);
    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("plugin-input-twist_angle_deg")).toHaveValue(
      "twist*2",
    );
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();

    // Delete it, then undo: the one row comes back with its members.
    await rows.nth(1).click({ button: "right" });
    await page.getByTestId("tree-ctx-delete").click();
    await page.getByTestId("feature-delete-confirm-action").click();
    await expect(rows).toHaveCount(1, { timeout: 30_000 });
    await page.getByTestId("undo-button").click();
    await expect(rows).toHaveCount(2, { timeout: 30_000 });
    await expect(rows.nth(1)).toContainText("Twisted prism 1");
    await expectSolved(page);
    expect(sweepTwist((await customRows(page, seeded))[0])).toBe(90);
  });

  test("a feature pinned to a version this server lacks is read-only", async ({
    page,
  }) => {
    const seeded = await seedPart(page, "Plugin prism read-only");
    await createFeature(page, seeded.token, seeded.partId, {
      name: "Prism from elsewhere",
      feature: {
        type: "custom",
        version: 1,
        params: {
          plugin_id: PLUGIN,
          plugin_version: "1.0.0",
          inputs: {
            profile: { kind: "feature", feature_id: seeded.sketchId },
            distance_mm: 15,
            twist_angle_deg: 45,
            axis_x_mm: 0,
            axis_y_mm: 0,
            direction: "normal",
            operation: "add",
            body: "merge",
          },
        },
      },
      expected_tree_version: seeded.treeVersion,
    });
    // This server's catalog moved on: only 2.0.0 is installed, so the stored
    // 1.0.0 feature rebuilds from its members and cannot be edited here.
    await page.route("**/api/v1/plugins", async (route) => {
      const response = await route.fetch();
      const catalog = (await response.json()) as {
        plugins: { id: string; version: string }[];
      };
      await route.fulfill({
        response,
        json: {
          plugins: catalog.plugins.map((m) =>
            m.id === PLUGIN ? { ...m, version: "2.0.0" } : m,
          ),
        },
      });
    });
    await page.goto(`/parts/${seeded.partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(2);
    await expectSolved(page);
    const badge = page.getByTestId("feature-read-only-1");
    await expect(badge).toContainText("Read-only");
    await expect(badge).toContainText("v1.0.0");

    await page.getByTestId("feature-select-1").click();
    await expect(page.getByTestId("plugin-read-only")).toBeVisible();
    await expect(page.getByTestId("plugin-missing")).toContainText(
      `${PLUGIN} v1.0.0 is not installed`,
    );
    await expect(page.getByTestId("plugin-submit")).toHaveCount(0);
    await page.getByTestId("plugin-cancel").click();
    await expect(page.getByTestId("plugin-editor")).toBeHidden();
  });
});
