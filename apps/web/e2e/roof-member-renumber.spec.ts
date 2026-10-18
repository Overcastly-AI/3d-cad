import { expectSolved } from "./buildFlow";
import { expect, test, type Page } from "./fixtures";
import { createFeature } from "./partSeed";
import { seedSession } from "./support";

/**
 * ROOF-MEMBER-RENUMBER: a hole in B3's front ridge-end common (X 59.25 ..
 * 60.75) stays in that common when the roof is lengthened by one spacing.
 *
 * The hole is a 1 in circle on a YZ datum at X 60, 20 in from the front wall
 * at Z 110, extruded through the common as a new body and subtracted by a
 * Boolean whose target is the common by id. With `loft.roof` 1.3.0 the
 * common's id is its place (`common/front/ridge/start`), so 144 -> 168 leaves
 * the Boolean on it: the part loses the bore's 0.375 pi in^3 before and
 * after (the goldens b3-hip-v1.3-hole-common and -168-hole-common). With
 * 1.2.0 the same id (`common/3`) would pass to the left king common; the save
 * is refused instead, naming the hole, and the roof keeps its length.
 */

const IN = 25.4;
const BORE = 0.375 * Math.PI;
/** B3 at 1.3.0 (b3-hip-6-12 less its four ripped hip tails), less the bore. */
const ROOF_144 = 13606.888612434248 - BORE;
/** Lengthened 24: plus a pair of commons and 24 in of ridge, less the bore. */
const ROOF_168 = 15173.089820458343 - BORE;

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
 * An inch part holding B3's hip roof (typed bearing) at *version* and a hole
 * through its front ridge-end common. Returns the part id and the common's
 * member id.
 */
async function seedRoof(
  page: Page,
  token: string,
  version: string,
): Promise<{ partId: string; commonId: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const created = await page.request.post("/api/v1/parts", {
    data: { name: `B3 roof ${version}`, length_unit: "in" },
    headers: auth,
  });
  expect(created.ok(), await created.text()).toBe(true);
  const part = (await created.json()) as { id: string; tree_version: number };
  const roof = await createFeature(page, token, part.id, {
    name: "Roof 1",
    feature: {
      type: "custom",
      version: 1,
      params: {
        plugin_id: "loft.roof",
        plugin_version: version,
        inputs: { style: "hip" },
      },
    },
    expected_tree_version: part.tree_version,
  });
  const stored = await features(page, part.id, token);
  const commons = (stored[0]?.feature.params.expansion ?? []).filter(
    (m) => m.role === "common",
  );
  const common =
    version === "1.3.0"
      ? commons.find((m) => m.name === "front/ridge/start")
      : commons.find((m) => m.index === 3);
  expect(common).toBeDefined();
  const commonId = common?.id ?? "";

  const datum = await createFeature(page, token, part.id, {
    name: "Hole plane",
    feature: {
      type: "datum",
      version: 1,
      params: { kind: "offset", base: "YZ", offset_mm: 60 * IN },
    },
    expected_tree_version: roof.tree_version,
  });
  const sketch = await createFeature(page, token, part.id, {
    name: "Hole sketch",
    feature: {
      type: "sketch",
      version: 1,
      params: {
        plane: { kind: "feature", feature_id: datum.feature.id },
        entities: [
          {
            id: "c1",
            kind: "circle",
            center: { x: 20 * IN, y: 110 * IN },
            radius: 0.5 * IN,
          },
        ],
        constraints: [],
      },
    },
    expected_tree_version: datum.tree_version,
  });
  const tool = await createFeature(page, token, part.id, {
    name: "Hole tool",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 3 * IN,
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
        target: { kind: "feature", feature_id: commonId },
        tool: { kind: "feature", feature_id: tool.feature.id },
      },
    },
    expected_tree_version: tool.tree_version,
  });
  return { partId: part.id, commonId };
}

/** Open the roof's editor and type its length; the caller saves. */
async function lengthen(page: Page, length: string): Promise<void> {
  await page.getByTestId("feature-select-0").click();
  const editor = page.getByTestId("plugin-editor");
  await expect(editor).toContainText("Edit Roof");
  const field = page.getByTestId("plugin-input-length_mm");
  await expect(field).toHaveValue("144");
  await field.fill(length);
  await page.getByTestId("plugin-submit").click();
}

test.describe("Roof members keep their names when the roof is lengthened", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("Roof 1.3.0: the hole in the front ridge-end common stays put at 168", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const { partId, commonId } = await seedRoof(page, account.token, "1.3.0");

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(5);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(ROOF_144, 2);

    await lengthen(page, "168");
    await expect(page.getByTestId("plugin-editor")).toBeHidden({
      timeout: 30_000,
    });
    await expectSolved(page);
    await expect(page.getByTestId("feature-error-4")).toHaveCount(0);
    // ROOF_168 + BORE would mean the bore was lost; it is still cut.
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(ROOF_168, 2);

    const stored = await features(page, partId, account.token);
    expect(stored[0]?.feature.params.inputs?.["length_mm"]).toBeCloseTo(
      168 * IN,
      9,
    );
    expect(stored[4]?.feature.params.target?.feature_id).toBe(commonId);
    const common = stored[0]?.feature.params.expansion?.find(
      (m) => m.id === commonId,
    );
    expect(common?.name).toBe("front/ridge/start");
  });

  test("Roof 1.2.0: lengthening is refused, naming the hole", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const account = await seedSession(page);
    const { partId, commonId } = await seedRoof(page, account.token, "1.2.0");

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(5);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(ROOF_144, 2);

    await lengthen(page, "168");
    const alert = page.getByTestId("plugin-error");
    await expect(alert).toContainText("'Hole'", { timeout: 30_000 });
    await expect(alert).toContainText("numbers its members in order");
    await expect(page.getByTestId("plugin-editor")).toBeVisible();
    await page.getByTestId("plugin-cancel").click();

    const stored = await features(page, partId, account.token);
    expect(stored[0]?.feature.params.inputs?.["length_mm"]).toBeCloseTo(
      144 * IN,
      9,
    );
    expect(stored[4]?.feature.params.target?.feature_id).toBe(commonId);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBeCloseTo(ROOF_144, 2);
  });
});
