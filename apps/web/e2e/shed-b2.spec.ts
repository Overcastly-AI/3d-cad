import { expect, test } from "./fixtures";
import {
  type CutRow,
  expectSolved,
  expectTable,
  openBuildTool,
  openCutList,
} from "./buildFlow";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * B2-E2E: the whole B2 shed of docs/reference-parts/buildings.md, built in
 * the real app from Build features only, as a framer would in Chief
 * Architect: four walls from the Build row, the door and window from
 * Build ▾ hosted in their walls, and the gable roof from Build ▾ at its
 * defaults (B2). Nothing is posted to the API but the empty part.
 *
 * The part's cut list is then buildings.md's B2 wall and roof lists, member
 * by member, and its volume the two goldens' sum (b2-walls-door-window
 * 231537/8 in³ + b2-roof-6-12 10 702.408 in³). A reload reads it again.
 * The slab (B2-SLAB) is an ordinary sketch and extrude and is left out: it
 * is not lumber and would only add an unclassified row.
 */

/** B2's walls, clockwise: start x, start y, direction, length (in). */
const WALLS: [number, number, number, number][] = [
  [144, 0, 180, 144], // front, Y 0..3.5
  [0, 3.5, 90, 113], // left, X 0..3.5
  [0, 120, 0, 144], // back, Y 116.5..120
  [144, 116.5, 270, 113], // right, X 140.5..144
];

/** buildings.md B2's wall cut list (kings are studs), then its roof's. */
const SHED: CutRow[] = [
  ["Stud", "36", "92.625", "8 ft"],
  ["Jack", "4", "81", "8 ft"],
  ["Header", "2", "41", "8 ft"],
  ["Cripple", "4", "6.125", "8 ft"],
  ["Top plate", "4", "144", "12 ft"],
  ["Bottom plate", "2", "53", "8 ft"],
  ["Top plate", "4", "113", "10 ft"],
  ["Bottom plate", "2", "113", "10 ft"],
  ["Bottom plate", "1", "144", "12 ft"],
  ["Header", "2", "27.5", "8 ft"],
  ["Sill", "1", "24.5", "8 ft"],
  ["Cripple", "2", "43", "8 ft"],
  ["Rafter", "14", "82.4099", "8 ft"],
  ["Ridge", "1", "144", "12 ft"],
];

/** 64 wall members + 14 rafters + 1 ridge. */
const PIECES = "79";

/** 231537/8 + 10702.4084562 in³ = 39 644.5334562, at the inch readout. */
const VOLUME = "39,644.5335";

test.describe("B2 shed — from Build features only", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("four walls, a door, a window and a roof give B2's cut list, and keep it on reload", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B2 shed", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);
    const editor = page.getByTestId("plugin-editor");

    // The Build row's Wall, four times, drawn clockwise round the slab.
    for (const [index, [x, y, direction, length]] of WALLS.entries()) {
      const tool = page.getByTestId("plugin-tool-loft.wall");
      await expect(tool).toBeEnabled({ timeout: 30_000 });
      await tool.click();
      await expect(editor).toContainText("New Wall");
      await page.getByTestId("plugin-input-start_x_mm").fill(String(x));
      await page.getByTestId("plugin-input-start_y_mm").fill(String(y));
      await page
        .getByTestId("plugin-input-direction_deg")
        .fill(String(direction));
      await page.getByTestId("plugin-input-length_mm").fill(String(length));
      await expect(page.getByTestId("plugin-input-height_mm")).toHaveValue(
        "97.125",
      );
      await page.getByTestId("plugin-submit").click();
      await expect(editor).toBeHidden({ timeout: 30_000 });
      await expect(rows).toHaveCount(index + 1);
      await expect(rows.nth(index)).toContainText(`Wall ${index + 1}`);
    }
    await expectSolved(page);

    // Build ▾ > Door: the front wall (Wall 1), centred 72 from its start.
    await openBuildTool(page, "loft.door", "Door");
    const host = page.getByTestId("plugin-input-host_wall");
    await expect(host.locator("option")).toHaveText([
      "Wall 1",
      "Wall 2",
      "Wall 3",
      "Wall 4",
    ]);
    await host.selectOption({ label: "Wall 1" });
    await expect(page.getByTestId("plugin-input-offset_mm")).toHaveValue("72");
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveValue("36");
    await expect(page.getByTestId("plugin-input-height_mm")).toHaveValue("80");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expect(rows).toHaveCount(5);

    // Build ▾ > Window: the right side wall (Wall 4), centred on Y 60.
    await openBuildTool(page, "loft.window", "Window");
    await page
      .getByTestId("plugin-input-host_wall")
      .selectOption({ label: "Wall 4" });
    await page.getByTestId("plugin-input-offset_mm").fill("56.5");
    await expect(page.getByTestId("plugin-input-head_height_mm")).toHaveValue(
      "82.5",
    );
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expect(rows).toHaveCount(6);

    // Build ▾ > Roof: B2's 6/12 gable on the front and back walls, at the
    // form's defaults (span 120, length 144, plate 97.125 x 3.5).
    await openBuildTool(page, "loft.roof", "Roof");
    await expect(page.getByTestId("plugin-input-span_mm")).toHaveValue("120");
    await expect(page.getByTestId("plugin-input-length_mm")).toHaveValue("144");
    await expect(page.getByTestId("plugin-input-plate_height_mm")).toHaveValue(
      "97.125",
    );
    await expect(
      page.getByTestId("plugin-input-pitch").locator("option:checked"),
    ).toHaveText("6/12");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expect(rows).toHaveCount(7);
    await expectSolved(page);

    await openCutList(page);
    await expectTable(page, SHED, PIECES);
    await expect(page.getByTestId("prop-volume")).toContainText(VOLUME, {
      timeout: 60_000,
    });

    // The finished shed, whole, from the front-right corner. True iso looks
    // straight down a 6/12 back slope's rafters (they project onto the
    // ridge), so the camera turns a little off it to show both slopes.
    await page.keyboard.press("Escape");
    await page.getByTestId("view-iso").click();
    // Let the view's ease land first: a drag into it loses the turn.
    await page.waitForTimeout(1_000);
    // A click on empty floor clears the roof's selection highlight.
    await page.mouse.click(450, 900);
    await page.mouse.move(760, 170);
    await page.mouse.down();
    await page.mouse.move(775, 165, { steps: 6 });
    await page.mouse.move(790, 160, { steps: 6 });
    await page.mouse.up();
    await page.getByTestId("view-fit").click();
    await page.mouse.move(800, 990);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/b2-shed.png` });

    // A reload rebuilds it from the stored tree.
    await page.reload();
    await expect(rows).toHaveCount(7);
    await expectSolved(page);
    await openCutList(page);
    await expectTable(page, SHED, PIECES);
    await expect(page.getByTestId("prop-volume")).toContainText(VOLUME, {
      timeout: 60_000,
    });
  });
});
