import { expectSolved } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { seedSession } from "./support";

/**
 * WALL-MEMBER-RENUMBER: a hole in B2's front-wall stud at 128 along the wall
 * stays in that stud when the door moves 24 in.
 *
 * The hole is how a multi-body part cuts one body (Fusion's Combine > Cut):
 * a 1 in circle extruded through the wall as a new body, subtracted by a
 * Boolean whose target is the stud by id. With `loft.wall` 1.1.0 the stud's
 * id is its layout slot (`stud/slot/8`), so the door 72 -> 48 leaves the
 * Boolean on it: the part loses the bore's 0.875 pi in^3 before and after.
 * With 1.0.0 the same id (`stud/6`) would pass to the end stud and the cut
 * would remove nothing (the wall would read 8 068.5 in^3); the save is
 * refused instead, naming the hole, and the door stays where it was.
 */

const IN = 25.4;
const BORE = 0.875 * Math.PI;
/** The front wall with its door at 72 (8 studs, 2 cripples), less the bore. */
const DOOR_72 = 8522.625 - BORE;
/** The door at 48 (7 studs, 3 cripples), less the bore. */
const DOOR_48 = 8068.5 - BORE;

interface Member {
  role: string;
  index: number;
  name?: string;
  id: string;
}

interface Stored {
  id: string;
  name: string;
  feature: {
    type: string;
    params: {
      expansion?: Member[];
      inputs?: Record<string, unknown>;
      target?: { feature_id: string };
    };
  };
}

async function features(
  page: Page,
  partId: string,
  token: string,
): Promise<Stored[]> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { features: Stored[] }).features;
}

async function partVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

/**
 * An inch part holding B2's front wall at *version*, its door at 72, and a
 * hole through the stud at 128 along the wall (world X 16, Z 48). Returns
 * the part id and the stud's member id.
 */
async function seedWall(
  page: Page,
  token: string,
  version: string,
): Promise<{ partId: string; studId: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("/api/v1/parts", {
    data: { name: `B2 front wall ${version}`, length_unit: "in" },
    headers: auth,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const part = (await created.json()) as { id: string; tree_version: number };
  const custom = (pluginId: string, inputs: Record<string, unknown>) => ({
    type: "custom",
    version: 1,
    params: {
      plugin_id: pluginId,
      plugin_version: pluginId === "loft.wall" ? version : "1.0.0",
      inputs,
    },
  });
  const wall = await createFeature(page, token, part.id, {
    name: "Front wall",
    feature: custom("loft.wall", {
      start_x_mm: 144 * IN,
      direction_deg: 180,
      length_mm: 144 * IN,
    }),
    expected_tree_version: part.tree_version,
  });
  const door = await createFeature(page, token, part.id, {
    name: "Door 1",
    feature: custom("loft.door", {
      host_wall: { kind: "feature", feature_id: wall.feature.id },
      offset_mm: 72 * IN,
    }),
    expected_tree_version: wall.tree_version,
  });
  const stored = await features(page, part.id, token);
  const studs = (stored[0]?.feature.params.expansion ?? []).filter(
    (m) => m.role === "stud",
  );
  const stud =
    version === "1.0.0"
      ? studs.find((m) => m.index === 6)
      : studs.find((m) => m.name === "slot/8");
  expect(stud).toBeDefined();
  const studId = stud?.id ?? "";

  const sketch = await createFeature(page, token, part.id, {
    name: "Hole sketch",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "datum_plane", plane: "XZ" },
        entities: [
          {
            id: "c1",
            kind: "circle",
            center: { x: 16 * IN, y: 48 * IN },
            radius: 0.5 * IN,
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: door.tree_version,
  });
  const tool = await createFeature(page, token, part.id, {
    name: "Hole tool",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 7 * IN,
        operation: "add",
        merge: false,
        extent: "symmetric",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await createFeature(page, token, part.id, {
    name: "Hole",
    feature: {
      type: "boolean",
      version: 1,
      params: {
        operation: "subtract",
        target: { kind: "feature", feature_id: studId },
        tool: { kind: "feature", feature_id: tool.feature.id },
      },
    },
    expected_tree_version: tool.tree_version,
  });
  return { partId: part.id, studId };
}

/** Open the door's editor and type its offset; the caller saves. */
async function moveDoor(page: Page, offset: string): Promise<void> {
  await page.getByTestId("feature-select-1").click();
  const editor = page.getByTestId("plugin-editor");
  await expect(editor).toContainText("Edit Door");
  const field = page.getByTestId("plugin-input-offset_mm");
  await expect(field).toHaveValue("72");
  await field.fill(offset);
  await page.getByTestId("plugin-submit").click();
}

test.describe("Wall members keep their names when an opening moves", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("Wall 1.1.0: the hole in the stud at 128 stays put when the door moves 24 in", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const { partId, studId } = await seedWall(page, account.token, "1.1.0");

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(5);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(DOOR_72, 2);

    await moveDoor(page, "48");
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 30_000,
    });
    await expectSolved(page);
    await expect(page.getByTestId("feature-error-4")).toHaveCount(0);
    // 8 068.5 in^3 would mean the bore was lost; it is still cut.
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(DOOR_48, 2);

    const stored = await features(page, partId, account.token);
    expect(stored[1]?.feature.params.inputs?.["offset_mm"]).toBeCloseTo(
      48 * IN,
      9,
    );
    expect(stored[4]?.feature.params.target?.feature_id).toBe(studId);
    const stud = stored[0]?.feature.params.expansion?.find(
      (m) => m.id === studId,
    );
    expect(stud?.name).toBe("slot/8");
  });

  test("Wall 1.0.0: moving the door is refused, naming the hole", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const { partId, studId } = await seedWall(page, account.token, "1.0.0");

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(5);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(DOOR_72, 2);

    await moveDoor(page, "48");
    const alert = page.getByTestId("plugin-error");
    await expect(alert).toContainText("'Hole'", { timeout: 30_000 });
    await expect(alert).toContainText("numbers its members in order");
    await expect(page.getByTestId("plugin-editor")).toBeVisible();
    await page.getByTestId("plugin-cancel").click();

    const stored = await features(page, partId, account.token);
    expect(stored[1]?.feature.params.inputs?.["offset_mm"]).toBeCloseTo(
      72 * IN,
      9,
    );
    expect(stored[4]?.feature.params.target?.feature_id).toBe(studId);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(DOOR_72, 2);
  });
});
