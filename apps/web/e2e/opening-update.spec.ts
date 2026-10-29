import { expectSolved, openCutList } from "./buildFlow";
import { expect, type Page, test } from "./fixtures";
import { createFeature } from "./partSeed";
import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * OPENING-UPDATE: B7 as saved before HEADER-PLIES (golden `b7-outline`: walls
 * `loft.wall` 1.3.0, the door and five windows `loft.door`/`loft.window`
 * 1.1.0, the gable `loft.roof` 1.4.0, the floor 1.2.0), so its 2x6 headers
 * are two plies with a 2-1/2 in void. As Onshape marks a custom feature whose
 * Feature Studio is newer and Fusion badges stale content, each out-of-date
 * Build feature wears an Update badge (the floor, offered no update, none),
 * its editor says what "Update to 1.5.0" changes, and the tree offers one
 * "Update all Build features". That one step takes the headers to 18 plies
 * (was 12) and draws 12 spacers of 1/2 plywood, cut from one 4x8: 264 852.3789
 * + 1 769.625 + 1 179.75 = 267 801.7539 in³ (golden `b7-opening-update`).
 * Ctrl+Z restores 264 852.3789 and every pin.
 */

const IN = 25.4;
const BEFORE = 264852.378866;
const AFTER = 267801.753866;

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

const BIG = { width_mm: 36 * IN, height_mm: 48 * IN };

/** B7's openings: the front runs from X 288 to 0, so X 144, 228 and 60 sit
 * 288 - X from its start; the back window at X 144; each side's centred. */
const OPENINGS: [string, string, string, Record<string, number>][] = [
  ["Door", "loft.door", "e1", { offset_mm: 144 * IN }],
  ["Window 1", "loft.window", "e1", { offset_mm: 228 * IN, ...BIG }],
  ["Window 2", "loft.window", "e1", { offset_mm: 60 * IN, ...BIG }],
  ["Window 3", "loft.window", "e3", { offset_mm: 144 * IN, ...BIG }],
  ["Window 4", "loft.window", "e4", { offset_mm: 90.5 * IN }],
  ["Window 5", "loft.window", "e2", { offset_mm: 90.5 * IN }],
];

const custom = (
  plugin: string,
  version: string,
  inputs: Record<string, unknown>,
) => ({
  type: "custom",
  version: 1,
  params: { plugin_id: plugin, plugin_version: version, inputs },
});

async function seedB7(page: Page, token: string): Promise<string> {
  const created = await page.request.post("/api/v1/parts", {
    data: { name: "B7 saved before header plies", length_unit: "in" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const partId = ((await created.json()) as { id: string }).id;
  let version = 0;
  const add = async (name: string, feature: unknown): Promise<string> => {
    const row = await createFeature(page, token, partId, {
      name,
      feature,
      expected_tree_version: version,
    });
    version = row.tree_version;
    return row.feature.id;
  };
  const ref = (id: string) => ({ kind: "feature", feature_id: id });
  const sketch = await add("Outline", {
    type: "sketch",
    version: 1,
    params: OUTLINE,
  });
  const floor = await add(
    "Floor",
    custom("loft.floor", "1.2.0", {
      outline: ref(sketch),
      joist_profile: "us_2x10",
    }),
  );
  const walls = await add(
    "Walls",
    custom("loft.wall", "1.3.0", {
      outline: ref(sketch),
      floor: ref(floor),
      stud_profile: "us_2x6",
      sheathing: "osb_7_16",
    }),
  );
  for (const [name, plugin, segment, raw] of OPENINGS) {
    await add(
      name,
      custom(plugin, "1.1.0", {
        host_wall: ref(walls),
        wall_segment: [segment],
        ...raw,
      }),
    );
  }
  await add(
    "Roof",
    custom("loft.roof", "1.4.0", {
      walls: [ref(walls)],
      slope_walls: ["e1", "e3"],
      rafter_profile: "us_2x8",
      ridge_profile: "us_2x10",
    }),
  );
  return partId;
}

async function pins(
  page: Page,
  partId: string,
  token: string,
): Promise<Record<string, string>> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const { features } = (await response.json()) as {
    features: {
      name: string;
      feature: { type: string; params: { plugin_version?: string } };
    }[];
  };
  return Object.fromEntries(
    features
      .filter((f) => f.feature.type === "custom")
      .map((f) => [f.name, f.feature.params.plugin_version ?? ""]),
  );
}

async function partVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

const NAMES = ["Door", ...[1, 2, 3, 4, 5].map((n) => `Window ${n}`)];
const STORED = {
  Floor: "1.2.0",
  Walls: "1.3.0",
  ...Object.fromEntries(NAMES.map((n) => [n, "1.1.0"])),
  Roof: "1.4.0",
};
const UPDATED = {
  Floor: "1.2.0",
  Walls: "1.4.0",
  ...Object.fromEntries(NAMES.map((n) => [n, "1.5.0"])),
  Roof: "1.6.0",
};

test.describe("Updating B7's out-of-date Build features", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("badges them, updates all in one step to 18 plies and 12 spacers, and Ctrl+Z restores", async ({
    page,
  }) => {
    test.setTimeout(420_000);
    const account = await seedSession(page);
    const partId = await seedB7(page, account.token);

    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(10);
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(BEFORE, 2);

    // Every out-of-date Build feature is badged; the floor is not.
    const strip = page.getByTestId("feature-update-strip");
    await expect(strip).toContainText("8 Build features out of date");
    await expect(page.getByTestId("feature-update-badge-1")).toHaveCount(0);
    for (const index of [2, 3, 4, 5, 6, 7, 8, 9]) {
      await expect(
        page.getByTestId(`feature-update-badge-${index}`),
      ).toBeVisible();
    }
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-update-tree.png`,
    });

    // A window's editor says what its update changes; opening it changes
    // nothing.
    await page.getByTestId("feature-select-4").click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("Edit Window");
    const notice = page.getByTestId("plugin-update-notice");
    await expect(notice).toContainText("Update available");
    await expect(notice).toContainText("1/2 in");
    await expect(page.getByTestId("plugin-update")).toHaveText(
      "Update to 1.5.0",
    );
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-update-editor.png`,
    });
    await page.getByTestId("plugin-cancel").click();
    await expect(editor).toBeHidden();
    expect(await pins(page, partId, account.token)).toEqual(STORED);

    // Update all: one step.
    await page.getByTestId("feature-update-all").click();
    await expect(strip).toBeHidden({ timeout: 90_000 });
    await expectSolved(page);
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(AFTER, 2);
    expect(await pins(page, partId, account.token)).toEqual(UPDATED);

    // The cut list: 18 header plies and the spacers cut from one sheet.
    await openCutList(page);
    const panel = page.getByTestId("cut-list-panel");
    const headers = panel.locator(
      '[data-testid="cut-list-row"][data-member="Header"]',
    );
    await expect(headers).toHaveCount(3, { timeout: 90_000 });
    const quantities = await headers
      .getByTestId("cut-list-qty")
      .allInnerTexts();
    expect(quantities.map(Number).sort((a, b) => a - b)).toEqual([3, 6, 9]);
    const spacers = panel.locator(
      '[data-testid="cut-list-row"][data-member="Spacer"]',
    );
    await expect(spacers).toHaveCount(1);
    await expect(spacers).toHaveAttribute("data-system", "walls");
    await expect(spacers).toHaveAttribute("data-profile", "1/2 plywood");
    await expect(spacers.getByTestId("cut-list-qty")).toHaveText("12");
    await expect(spacers.getByTestId("cut-list-stock")).toHaveText("1 × 4x8");
    await spacers.scrollIntoViewIfNeeded();
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/opening-update-cut-list.png`,
    });

    // One Ctrl+Z restores every pin and the volume.
    await page.getByTestId("feature-select-1").click();
    await page.getByTestId("plugin-cancel").click();
    await page.keyboard.press("Control+z");
    await expect
      .poll(() => partVolume(page), { timeout: 120_000 })
      .toBeCloseTo(BEFORE, 2);
    expect(await pins(page, partId, account.token)).toEqual(STORED);
    await expect(strip).toContainText("8 Build features out of date");
  });
});
