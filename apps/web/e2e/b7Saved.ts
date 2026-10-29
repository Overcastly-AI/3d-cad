import { expect, type Page } from "./fixtures";

import { createFeature } from "./partSeed";

/**
 * B7 as saved at batch48's releases (golden `b7-outline`): its 288 x 192
 * outline sketch, the floor `loft.floor` 1.2.0, the walls `loft.wall` 1.3.0
 * on it, the door and five windows `loft.door`/`loft.window` 1.1.0 and the
 * gable `loft.roof` 1.4.0, seeded through the real gateway. Shared by the
 * specs that update it (OPENING-UPDATE, PLUGIN-UPDATE-ALL): two copies of
 * "B7 as saved" drifting apart would be a debugging trap.
 */

const IN = 25.4;

/** b7-outline's volume (in³): what the saved tree builds. */
export const B7_SAVED_IN3 = 264852.378866;

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

/** The openings' row names, in tree order. */
export const OPENING_NAMES = OPENINGS.map(([name]) => name);

/** Every Build feature's pin as saved. */
export const B7_SAVED_PINS: Record<string, string> = {
  Floor: "1.2.0",
  Walls: "1.3.0",
  ...Object.fromEntries(OPENING_NAMES.map((n) => [n, "1.1.0"])),
  Roof: "1.4.0",
};

const custom = (
  plugin: string,
  version: string,
  inputs: Record<string, unknown>,
) => ({
  type: "custom",
  version: 1,
  params: { plugin_id: plugin, plugin_version: version, inputs },
});

/** Seed B7 as saved; the part's id. */
export async function seedSavedB7(
  page: Page,
  token: string,
  name = "B7 saved at batch48's releases",
): Promise<string> {
  const created = await page.request.post("/api/v1/parts", {
    data: { name, length_unit: "in" },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const partId = ((await created.json()) as { id: string }).id;
  let version = 0;
  const add = async (row: string, feature: unknown): Promise<string> => {
    const made = await createFeature(page, token, partId, {
      name: row,
      feature,
      expected_tree_version: version,
    });
    version = made.tree_version;
    return made.feature.id;
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
  for (const [row, plugin, segment, raw] of OPENINGS) {
    await add(
      row,
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

/** A stored row, as the tree returns it. */
export interface StoredRow {
  readonly id: string;
  readonly name: string;
  readonly feature: {
    readonly type: string;
    readonly params: {
      readonly plugin_version?: string;
      readonly inputs?: Record<string, unknown>;
      readonly expansion?: unknown[];
    };
  };
  readonly plugin_update?: { readonly to_version: string } | null;
}

/** The part's stored rows, by name. */
export async function storedRows(
  page: Page,
  partId: string,
  token: string,
): Promise<Record<string, StoredRow>> {
  const response = await page.request.get(`/api/v1/parts/${partId}/features`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBe(true);
  const { features } = (await response.json()) as { features: StoredRow[] };
  return Object.fromEntries(features.map((f) => [f.name, f]));
}

/** Every Build feature's pin, by row name. */
export async function storedPins(
  page: Page,
  partId: string,
  token: string,
): Promise<Record<string, string>> {
  const rows = await storedRows(page, partId, token);
  return Object.fromEntries(
    Object.values(rows)
      .filter((f) => f.feature.type === "custom")
      .map((f) => [f.name, f.feature.params.plugin_version ?? ""]),
  );
}

/** The properties panel's volume (in³). */
export async function partVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}
