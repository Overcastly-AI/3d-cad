import { expectSolved, openBuildTool } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * BUILDING-OUTLINE: B7 (docs/reference-parts/buildings.md) from ONE outline
 * sketch, built in the real app the way Revit and Chief Architect build a
 * house: the floor and the walls pick the sketch, the openings pick their
 * wall by side ("Front", "Left"), the roof picks the walls that define its
 * slope. No line id and no corner coordinate is typed anywhere.
 *
 * Then BACKLOG's edit 1 as one action: the sketch's 288 dimension set to
 * 336, after which the floor, the walls and the roof follow (217 bodies,
 * then 234, as golden `b7-outline` and its 336 case pin them).
 *
 * The sketch is seeded as the Rectangle tool leaves it, dimensioned
 * `length` 288 and `width` 192 with a corner on the origin; drawing it is
 * the sketcher's own specs' business.
 */

const IN = 25.4;

function line(id: string, a: [number, number], b: [number, number]) {
  return {
    id,
    kind: "line",
    construction: false,
    start: { x: a[0] * IN, y: a[1] * IN },
    end: { x: b[0] * IN, y: b[1] * IN },
  };
}

const end = (entity: string, point: "start" | "end") => ({ entity, point });

/** B7's outline: 288 x 192 from the origin, fully defined. */
const OUTLINE = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    {
      id: "origin",
      kind: "point",
      construction: true,
      position: { x: 0, y: 0 },
    },
    line("e1", [0, 0], [288, 0]),
    line("e2", [288, 0], [288, 192]),
    line("e3", [288, 192], [0, 192]),
    line("e4", [0, 192], [0, 0]),
  ],
  constraints: [
    { kind: "fixed", point: { entity: "origin", point: "position" } },
    { kind: "horizontal", entity: "e1" },
    { kind: "coincident", a: end("e1", "end"), b: end("e2", "start") },
    { kind: "vertical", entity: "e2" },
    { kind: "coincident", a: end("e2", "end"), b: end("e3", "start") },
    { kind: "horizontal", entity: "e3" },
    { kind: "coincident", a: end("e3", "end"), b: end("e4", "start") },
    { kind: "vertical", entity: "e4" },
    { kind: "coincident", a: end("e4", "end"), b: end("e1", "start") },
    {
      kind: "coincident",
      a: end("e1", "start"),
      b: { entity: "origin", point: "position" },
    },
    { kind: "distance", entity: "e1", name: "length", value_mm: 288 * IN },
    { kind: "distance", entity: "e2", name: "width", value_mm: 192 * IN },
  ],
};

/**
 * B7's openings on the outline walls (test_building_outline.b7_openings):
 * side, distance from the wall end nearer the origin (OPENING-FROM-END, the
 * form's default), and a 36 x 48 unit where not the window's 24 x 36
 * default. The front wall runs from X 288 back to X 0, so its door and
 * windows read their X: 144, 60 and 228.
 */
const OPENINGS: [string, "Door" | "Window", string, string, boolean][] = [
  ["loft.door", "Door", "Front", "144", false],
  ["loft.window", "Window", "Front", "60", true],
  ["loft.window", "Window", "Front", "228", true],
  ["loft.window", "Window", "Back", "144", true],
  ["loft.window", "Window", "Left", "90.5", false],
  ["loft.window", "Window", "Right", "90.5", false],
];

async function submit(page: Page): Promise<void> {
  const editor = page.getByTestId("plugin-editor");
  const button = page.getByTestId("plugin-submit");
  // A save the last command started may still be landing.
  await expect(button).not.toHaveAttribute("aria-disabled", "true", {
    timeout: 90_000,
  });
  await button.click();
  await expect(editor).toBeHidden({ timeout: 60_000 });
}

/** The model alone: no selection highlight, the pointer off the canvas. */
async function frameShot(page: Page, name: string): Promise<void> {
  // Measure on and off drops the feature selection, and with it the
  // highlight a just-saved feature leaves on the whole house.
  const measure = page.getByTestId("measure-tool");
  await measure.click();
  await measure.click();
  await page.getByTestId("view-fit").click();
  await page.mouse.move(800, 990);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` });
}

async function expectBodies(page: Page, count: number): Promise<void> {
  await expect(page.getByTestId("bodies-section")).toContainText(
    `Bodies · ${count}`,
    { timeout: 120_000 },
  );
}

/** A choice input: a segmented control for a few short options, else a select. */
async function choose(page: Page, input: string, value: string): Promise<void> {
  const segment = page.getByTestId(`plugin-input-${input}-${value}`);
  if ((await segment.count()) > 0) await segment.click();
  else await page.getByTestId(`plugin-input-${input}`).selectOption(value);
}

/** Open the outline sketch, set its *from* length dimension, save it. */
async function editLength(page: Page, from: string, typed: string) {
  await page.getByTestId("feature-select-0").click();
  await expect(page.getByTestId("sketch-save")).toBeVisible({
    timeout: 30_000,
  });
  await page
    .locator('[data-testid^="glyph-"][data-kind="distance"]')
    .filter({ hasText: new RegExp(`^${from}$`) })
    .click();
  const cell = page.getByTestId("dimension-input");
  await expect(cell).toHaveValue(from);
  await cell.fill(typed);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("dimension-editor")).toHaveCount(0);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expectSolved(page);
}

/** One side of a side pick, by the name the form gives it. */
function side(page: Page, input: string, name: string) {
  return page
    .getByTestId(`plugin-input-${input}`)
    .getByRole("button", { name, exact: true });
}

test.describe("B7 from one outline sketch", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("floor, walls, openings and roof pick the outline; 288 -> 336 is one dimension edit", async ({
    page,
  }) => {
    test.setTimeout(600_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 outline", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;
    const sketch = await createFeature(page, account.token, partId, {
      name: "Outline",
      feature: { type: "sketch", version: 1, params: OUTLINE },
      expected_tree_version: 0,
    });
    const sketchId = sketch.feature.id;

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(1);
    await expectSolved(page);

    // FLOOR: its Outline field is live; the sketch is picked from the
    // browser, and the typed rectangle goes away.
    await openBuildTool(page, "loft.floor", "Floor");
    const outline = page.getByTestId("plugin-input-outline");
    await expect(outline).toHaveAttribute("data-armed", "true");
    await expect(page.getByTestId("plugin-input-width_mm")).toBeVisible();
    // A part holding only the sketch opens framed on it.
    await expect(page.getByTestId(`outline-pick-${sketchId}`)).toBeInViewport();
    await page.getByTestId("feature-select-0").click();
    await expect(outline).toHaveValue(sketchId);
    await expect(page.getByTestId("plugin-editor")).toContainText("New Floor");
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveCount(0);
    await expect(page.getByTestId("plugin-input-start_x_mm")).toHaveCount(0);
    await choose(page, "joist_profile", "us_2x10");
    await submit(page);
    await expect(rows).toHaveCount(2);
    await expectSolved(page);

    // WALLS: the Outline picked on the model (a click on any of its lines,
    // which run round the floor's edge), standing on the floor.
    const wallTool = page.getByTestId("plugin-tool-loft.wall");
    await expect(wallTool).toBeEnabled({ timeout: 30_000 });
    await wallTool.click();
    await expect(page.getByTestId("plugin-editor")).toContainText("New Wall");
    await expect(outline).toHaveAttribute("data-armed", "true");
    await page.getByTestId(`outline-pick-${sketchId}`).click();
    await expect(outline).toHaveValue(sketchId);
    await expect(page.getByTestId("plugin-input-length_mm")).toHaveCount(0);
    await page
      .getByTestId("plugin-input-floor")
      .selectOption({ label: "Floor 1" });
    await expect(page.getByTestId("plugin-input-elevation_mm")).toHaveCount(0);
    await choose(page, "stud_profile", "us_2x6");
    await choose(page, "sheathing", "osb_7_16");
    await submit(page);
    await expect(rows).toHaveCount(3);
    await expectSolved(page);

    // OPENINGS: each picks its wall of the outline by side. The door's is
    // picked on the model, the windows' in the list.
    for (const [
      index,
      [plugin, title, wall, offset, large],
    ] of OPENINGS.entries()) {
      await openBuildTool(page, plugin, title);
      await expect(page.getByTestId("plugin-input-host_wall")).toHaveValue(
        /.+/,
      );
      const pick = page.getByTestId("plugin-input-wall_segment");
      await expect(pick).toHaveAttribute("data-armed", "true");
      await expect(pick).not.toContainText(/\be\d\b/);
      if (index === 0) {
        await page.getByRole("button", { name: `${wall} wall` }).click();
      } else {
        await side(page, "wall_segment", wall).click();
      }
      await expect(
        page.getByRole("button", { name: `Wall: ${wall}` }),
      ).toBeVisible();
      if (index === 0) {
        await page.mouse.move(800, 990);
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/outline-door-wall-pick.png`,
        });
      }
      await page.getByTestId("plugin-input-offset_mm").fill(offset);
      if (large) {
        await page.getByTestId("plugin-input-width_mm").fill("36");
        await page.getByTestId("plugin-input-height_mm").fill("48");
      }
      await submit(page);
      await expect(rows).toHaveCount(4 + index);
    }

    // ROOF: pick the outline wall, then the eave walls that define the
    // slope (a gable on the front and back); its typed bearing goes away.
    await openBuildTool(page, "loft.roof", "Roof");
    await expect(page.getByTestId("plugin-input-span_mm")).toBeVisible();
    await page
      .getByTestId("plugin-input-walls-pick")
      .filter({ hasText: "Wall 1" })
      .click();
    await expect(page.getByTestId("plugin-input-span_mm")).toHaveCount(0);
    await expect(page.getByTestId("plugin-input-plate_height_mm")).toHaveCount(
      0,
    );
    const slope = page.getByTestId("plugin-input-slope_walls");
    await expect(slope).toHaveAttribute("data-armed", "true");
    await side(page, "slope_walls", "Front").click();
    await page.getByRole("button", { name: "Back wall" }).click();
    await expect(
      page.getByRole("button", { name: "Defines slope: Front, Back" }),
    ).toBeVisible();
    await choose(page, "rafter_profile", "us_2x8");
    await choose(page, "ridge_profile", "us_2x10");
    await page.mouse.move(800, 990);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/outline-roof-slope.png` });
    await submit(page);
    await expect(rows).toHaveCount(10);
    await expectSolved(page);
    await expectBodies(page, 217);
    await page.getByTestId("view-iso").click();
    await frameShot(page, "outline-b7-288");

    // EDIT 1, one action: the sketch's 288 dimension set to 336, read and
    // typed in the part's inches as every length field is.
    await editLength(page, "288", "336");
    await expectBodies(page, 234);
    await frameShot(page, "outline-b7-336");

    // The same dimension as a FORMULA over the sketch's own names: the walls
    // follow what it evaluates to (width + 96 in = 288 in), back to 217.
    await editLength(page, "336", "width + 96 in");
    await expectBodies(page, 217);

    // Stored: the openings and the roof name their walls by line, not by
    // anything the edit moved.
    const tree = await page.request.get(`/api/v1/parts/${partId}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const features = (
      (await tree.json()) as {
        features: {
          name: string;
          feature: { params: { inputs?: Record<string, unknown> } };
        }[];
      }
    ).features;
    const roof = features.find((f) => f.name.startsWith("Roof"));
    expect(roof?.feature.params.inputs?.slope_walls).toEqual(["e1", "e3"]);
    const door = features.find((f) => f.name.startsWith("Door"));
    expect(door?.feature.params.inputs?.wall_segment).toEqual(["e1"]);
  });
});
