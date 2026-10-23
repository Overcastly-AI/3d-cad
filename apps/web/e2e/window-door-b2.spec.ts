import {
  type CutRow,
  expectSolved,
  expectTable,
  openBuildTool,
  openCutList,
} from "./buildFlow";
import { expect, test } from "./fixtures";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * WINDOW-DOOR: B2's door and window of docs/reference-parts/buildings.md,
 * placed from Build ▾ into walls they name as host, as Revit and Chief
 * Architect host them. The WALLS frame the openings (kings, jacks, a doubled
 * 2x6 header, cripples, the window's sill; the door cuts the bottom plate).
 *
 * In an inch part holding B2's four walls: Build ▾ > Door in the front wall
 * at 72 and Build ▾ > Window in the right side wall at 56.5 give the spec's
 * wall cut list (64 members). Then the spec's first edit: the door's distance
 * from the X 0 end 72 -> 96 (OPENING-FROM-END: a new opening measures from
 * the end nearer the origin) regenerates the front wall with 7 layout studs
 * and 3 top cripples, and the bottom plate cut moves.
 */

const IN = 25.4;

/** B2's walls, clockwise: name, start x, start y, direction, length (in). */
const WALLS: [string, number, number, number, number][] = [
  ["Front wall", 144, 0, 180, 144],
  ["Left wall", 0, 3.5, 90, 113],
  ["Back wall", 0, 120, 0, 144],
  ["Right wall", 144, 116.5, 270, 113],
];

/** buildings.md B2's wall cut list, in tree order (kings are studs). */
const DOOR_WINDOW: CutRow[] = [
  ["Stud", "36", "92.625", "8 ft"],
  ["Jack", "4", "81", "8 ft"],
  ["Header", "2", "27.5", "8 ft"],
  ["Header", "2", "41", "8 ft"],
  ["Cripple", "4", "6.125", "8 ft"],
  ["Cripple", "2", "43", "8 ft"],
  ["Top plate", "4", "113", "10 ft"],
  ["Top plate", "4", "144", "12 ft"],
  ["Bottom plate", "2", "53", "8 ft"],
  ["Bottom plate", "2", "113", "10 ft"],
  ["Bottom plate", "1", "144", "12 ft"],
  ["Sill", "1", "24.5", "8 ft"],
];

/** "Door moved 24 in": 7 layout studs and 3 top cripples on the front wall. */
const DOOR_MOVED: CutRow[] = [
  ["Stud", "35", "92.625", "8 ft"],
  ["Jack", "4", "81", "8 ft"],
  ["Header", "2", "27.5", "8 ft"],
  ["Header", "2", "41", "8 ft"],
  ["Cripple", "5", "6.125", "8 ft"],
  ["Cripple", "2", "43", "8 ft"],
  ["Top plate", "4", "113", "10 ft"],
  ["Top plate", "4", "144", "12 ft"],
  ["Bottom plate", "1", "29", "8 ft"],
  ["Bottom plate", "1", "77", "8 ft"],
  ["Bottom plate", "2", "113", "10 ft"],
  ["Bottom plate", "1", "144", "12 ft"],
  ["Sill", "1", "24.5", "8 ft"],
];

test.describe("Window and Door — hosted openings framed by B2's walls", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("place the door and window from Build, see the cut list, move the door", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B2 shed walls", length_unit: "in" },
      headers: auth,
    });
    expect(created.ok(), await created.text()).toBe(true);
    const part = (await created.json()) as { id: string; tree_version: number };
    let version = part.tree_version;
    for (const [name, x, y, direction, length] of WALLS) {
      const response = await page.request.post(
        `/api/v1/parts/${part.id}/features`,
        {
          data: {
            name,
            expected_tree_version: version,
            feature: {
              type: "custom",
              version: 1,
              params: {
                plugin_id: "loft.wall",
                plugin_version: "1.0.0",
                inputs: {
                  start_x_mm: x * IN,
                  start_y_mm: y * IN,
                  direction_deg: direction,
                  length_mm: length * IN,
                },
              },
            },
          },
          headers: auth,
        },
      );
      expect(response.ok(), await response.text()).toBe(true);
      version = ((await response.json()) as { tree_version: number })
        .tree_version;
    }

    await page.goto(`/parts/${part.id}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(4);
    await expectSolved(page);
    const editor = page.getByTestId("plugin-editor");

    // Build ▾ > Door: hosted in the front wall, centred 72 from an end (the middle).
    await openBuildTool(page, "loft.door", "Door");
    const host = page.getByTestId("plugin-input-host_wall");
    // Only walls are offered as hosts.
    await expect(host.locator("option")).toHaveText(WALLS.map((w) => w[0]));
    await host.selectOption({ label: "Front wall" });
    await expect(page.getByTestId("plugin-input-offset_mm")).toHaveValue("72");
    // OPENING-UNITS: B2's 36 x 80 door is the default 3068; its unit is
    // left out, so the list is the framing's.
    await expect(page.getByTestId("plugin-input-size")).toHaveValue(
      "door_3068",
    );
    await page.getByTestId("plugin-input-draw_unit").selectOption("none");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expect(rows).toHaveCount(5);
    await expect(rows.nth(4)).toContainText("Door 1");

    // Build ▾ > Window: the right side wall, centred on Y 60 (local 56.5).
    await openBuildTool(page, "loft.window", "Window");
    await page
      .getByTestId("plugin-input-host_wall")
      .selectOption({ label: "Right wall" });
    await page.getByTestId("plugin-input-offset_mm").fill("56.5");
    await expect(page.getByTestId("plugin-input-head_height_mm")).toHaveValue(
      "82.5",
    );
    // B2's 24 x 36 window is a 2030, its unit left out.
    await page.getByTestId("plugin-input-size").selectOption("window_2030");
    await page.getByTestId("plugin-input-draw_unit").selectOption("none");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expect(rows).toHaveCount(6);
    await expectSolved(page);

    await openCutList(page);
    await expectTable(page, DOOR_WINDOW, "64");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/window-door-b2.png` });

    // The spec's edit: the door 24 in along its wall regenerates the wall.
    await page.getByTestId("feature-select-4").click();
    await expect(editor).toContainText("Edit Door");
    const offset = page.getByTestId("plugin-input-offset_mm");
    await expect(offset).toHaveValue("72");
    // Measured from the front wall's X 0 end (the end nearer the origin,
    // OPENING-FROM-END): X 72 -> 96, golden b2-walls-door-moved-24's place.
    await expect(page.getByTestId("plugin-input-measure_from")).toHaveValue(
      "end",
    );
    await offset.fill("96");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, DOOR_MOVED, "64");
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.filter({ hasText: "Cripple" })).toHaveCount(3);
    await page.getByTestId("feature-unfold-0").click();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/window-door-b2-door-moved.png`,
    });

    // A reload keeps it, from the stored walls.
    await page.reload();
    await expect(rows).toHaveCount(6);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, DOOR_MOVED, "64");
  });
});
