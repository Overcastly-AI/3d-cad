import { expectSolved, openBuildTool } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { seedSession } from "./support";

/**
 * OPENING-FROM-END (docs/BACKLOG.md): a window is measured from the end of
 * its wall nearer the part origin, as Revit's and Chief Architect's
 * temporary dimensions read from a wall end. B7's front wall runs from
 * X 288 back to X 0 (the outline walked clockwise), so a new window there
 * measures from its END: typing 60 puts it at X 60, and moving it to X 84 is
 * one field, 60 -> 84. When the house grows to 336 the window stays at X 84,
 * where loft.window 1.1.0 measured from the start (X 336) and moved 48.
 *
 * The window's place is read from what the wall frames for it: its sill's
 * section, drawn in plan in world millimetres.
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

interface Stored {
  id: string;
  name: string;
  feature: {
    params: {
      inputs?: Record<string, unknown>;
      expansion?: {
        role: string;
        name: string | null;
        feature: {
          type: string;
          params: { entities?: { start: { x: number } }[] };
        };
      }[];
    };
  };
}

async function tree(page: Page, token: string, partId: string) {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { features: Stored[] }).features;
}

/** The window's centre X (in): the middle of its sill's section in plan. */
async function windowX(page: Page, token: string, partId: string) {
  const features = await tree(page, token, partId);
  const window = features.find((f) => f.name.startsWith("Window"));
  const walls = features.find((f) => f.name.startsWith("Walls"));
  const sill = walls?.feature.params.expansion?.find(
    (m) =>
      m.role === "section" &&
      (m.name ?? "").includes(`sill/opening/${window?.id ?? "-"}/`),
  );
  const xs = (sill?.feature.params.entities ?? []).map((e) => e.start.x / IN);
  expect(xs.length).toBe(4);
  return (Math.min(...xs) + Math.max(...xs)) / 2;
}

async function submit(page: Page): Promise<void> {
  const button = page.getByTestId("plugin-submit");
  await expect(button).not.toHaveAttribute("aria-disabled", "true", {
    timeout: 90_000,
  });
  await button.click();
  await expect(page.getByTestId("plugin-editor")).toBeHidden({
    timeout: 60_000,
  });
}

test.describe("Openings measured from the wall end nearer the origin", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("a window 60 from the left end is at X 60, 84 is one field, and it stays when the house grows", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B7 front wall", length_unit: "in" },
      headers: { Authorization: `Bearer ${account.token}` },
    });
    expect(created.ok(), await created.text()).toBe(true);
    const partId = ((await created.json()) as { id: string }).id;
    const sketch = await createFeature(page, account.token, partId, {
      name: "Outline",
      feature: { type: "sketch", version: 1, params: OUTLINE },
      expected_tree_version: 0,
    });
    await createFeature(page, account.token, partId, {
      name: "Walls",
      feature: {
        type: "custom",
        version: 1,
        params: {
          plugin_id: "loft.wall",
          plugin_version: "1.3.0",
          inputs: {
            outline: { kind: "feature", feature_id: sketch.feature.id },
            stud_profile: "us_2x6",
          },
        },
      },
      expected_tree_version: sketch.tree_version,
    });

    await page.goto(`/parts/${partId}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(2);
    await expectSolved(page);

    // A new window on the front wall: Measured from proposes the end nearer
    // the origin, and 60 is read from it.
    await openBuildTool(page, "loft.window", "Window");
    await expect(page.getByTestId("plugin-input-host_wall")).toHaveValue(/.+/);
    await page
      .getByTestId("plugin-input-wall_segment")
      .getByRole("button", { name: "Front", exact: true })
      .click();
    const from = page.getByTestId("plugin-input-measure_from");
    await expect(from).toHaveValue("nearer");
    await expect(from.locator("option:checked")).toHaveText(
      "Nearer the origin",
    );
    await page.getByTestId("plugin-input-offset_mm").fill("60");
    await page.getByTestId("plugin-input-width_mm").fill("36");
    await page.getByTestId("plugin-input-height_mm").fill("48");
    await submit(page);
    await expect(rows).toHaveCount(3);
    await expectSolved(page);
    const stored = (await tree(page, account.token, partId)).find((f) =>
      f.name.startsWith("Window"),
    );
    expect(stored?.feature.params.inputs?.measure_from).toBe("end");
    expect(await windowX(page, account.token, partId)).toBeCloseTo(60, 6);

    // Moving it 24 in is one field: the distance from the left end, 60 -> 84.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("plugin-editor")).toContainText(
      "Edit Window",
    );
    await expect(from).toHaveValue("end");
    const distance = page.getByTestId("plugin-input-offset_mm");
    await expect(distance).toHaveValue("60");
    await distance.fill("84");
    await submit(page);
    await expectSolved(page);
    await expect
      .poll(() => windowX(page, account.token, partId), { timeout: 30_000 })
      .toBeCloseTo(84, 6);

    // The house grows at its far end (288 -> 336): the window stays at X 84.
    const grown = structuredClone(OUTLINE);
    const length = grown.constraints.find(
      (c) => "name" in c && c.name === "length",
    ) as { value_mm: number };
    length.value_mm = 336 * IN;
    const features = await tree(page, account.token, partId);
    const parts = await page.request.get(`/api/v1/parts/${partId}`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const version = ((await parts.json()) as { tree_version: number })
      .tree_version;
    const patched = await page.request.patch(
      `/api/v1/parts/${partId}/features/${features[0]?.id ?? ""}`,
      {
        data: {
          feature: { type: "sketch", version: 1, params: grown },
          expected_tree_version: version,
        },
        headers: { Authorization: `Bearer ${account.token}` },
      },
    );
    expect(patched.ok(), await patched.text()).toBe(true);
    expect(await windowX(page, account.token, partId)).toBeCloseTo(84, 6);
    const front = (await tree(page, account.token, partId))
      .find((f) => f.name.startsWith("Walls"))
      ?.feature.params.expansion?.filter(
        (m) => m.role === "section" && (m.name ?? "").startsWith("e1/"),
      )
      .flatMap((m) => (m.feature.params.entities ?? []).map((e) => e.start.x));
    expect(Math.max(...(front ?? [0])) / IN).toBeCloseTo(336, 6);
  });
});
