import { expect, test, type Page } from "./fixtures";

import { createFeature } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * OBJECTS TO CUT (CUT-OBJECTS-TO-CUT): an extrude cut removes material from
 * every body its tool meets, as Fusion 360's Objects To Cut and SolidWorks'
 * Feature Scope do, and the dialog's list narrows it.
 *
 * Before, a cut removed material from the ACTIVE (last-built) body only, so a
 * notch drawn across a framed wall cut its top plate and left the studs
 * whole. The gate is geometric: a 200 x 200 mm wall of four members (bottom
 * plate, two studs, top plate; 40 mm thick, each its own body) and a
 * 180 x 180 mm notch cut 10 mm into its face. The notch removes 180 x 10 x 10
 * from each plate and 20 x 10 x 160 from each stud, 100 000 mm^3 of the
 * wall's 576 000; unticking a stud leaves its 32 000 in place.
 */

const WALL_MM3 = 2 * 200 * 40 * 20 + 2 * 20 * 40 * 160;
const PLATE_NOTCH_MM3 = 180 * 10 * 10;
const STUD_NOTCH_MM3 = 20 * 10 * 160;
const XZ = { kind: "datum_plane", plane: "XZ" };

/** A closed rectangle at (x0,y0), w x h, on `plane`: exact, no solver drift. */
function rectangle(x0: number, y0: number, w: number, h: number) {
  const c = [
    [x0, y0],
    [x0 + w, y0],
    [x0 + w, y0 + h],
    [x0, y0 + h],
  ] as const;
  return {
    plane: XZ,
    entities: c.map((p, i) => {
      const q = c[(i + 1) % 4] as readonly [number, number];
      return {
        id: `e${i + 1}`,
        kind: "line",
        start: { x: p[0], y: p[1] },
        end: { x: q[0], y: q[1] },
      };
    }),
    constraints: [],
  };
}

interface Wall {
  partId: string;
  token: string;
  /** Base feature id of each member, in tree order. */
  members: string[];
}

/**
 * Four members drawn in elevation on XZ (sketch y is world Z) and extruded
 * 40 mm into +Y, each a new body; then the notch profile. Seeded through the
 * real gateway, so the spec pays browser time only for the cut dialog.
 */
async function seedWall(page: Page): Promise<Wall> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Notched wall");
  const members: string[] = [];
  let version = 0;
  const outlines: [string, number, number, number, number][] = [
    ["Bottom plate", 0, 0, 200, 20],
    ["Stud A", 20, 20, 20, 160],
    ["Stud B", 160, 20, 20, 160],
    ["Top plate", 0, 180, 200, 20],
  ];
  for (const [name, x0, z0, w, h] of outlines) {
    const sketch = await createFeature(page, account.token, part.id, {
      name: `${name} outline`,
      feature: { type: "sketch", version: 1, params: rectangle(x0, z0, w, h) },
      expected_tree_version: version,
    });
    const member = await createFeature(page, account.token, part.id, {
      name,
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 40,
          operation: "add",
          direction: "reverse",
          merge: members.length === 0,
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    members.push(member.feature.id);
    version = member.tree_version;
  }
  await createFeature(page, account.token, part.id, {
    name: "Notch",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangle(10, 10, 180, 180),
    },
    expected_tree_version: version,
  });
  return { partId: part.id, token: account.token, members };
}

/** The part volume (mm^3) the inspector reads out. */
async function partVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

/** The stored params of the tree's last feature. */
async function lastParams(
  page: Page,
  wall: Wall,
): Promise<Record<string, unknown>> {
  const response = await page.request.get(
    `/api/v1/parts/${wall.partId}/features`,
    { headers: { Authorization: `Bearer ${wall.token}` } },
  );
  const tree = (await response.json()) as {
    features: { feature: { params: Record<string, unknown> } }[];
  };
  const last = tree.features.at(-1);
  if (last === undefined) throw new Error("e2e: empty tree");
  return last.feature.params;
}

test.describe("Objects To Cut (CUT-OBJECTS-TO-CUT)", () => {
  test("a cut across a wall cuts all four members; unticking one leaves it whole", async ({
    page,
  }) => {
    const wall = await seedWall(page);
    await page.goto(`/parts/${wall.partId}`);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBe(WALL_MM3);

    // New Extrude Cut on the notch: a new cut cuts every body it meets, and
    // the dialog says so before anything is built.
    await expect(page.getByTestId("new-extrude")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-extrude").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.getByTestId("extrude-profile").selectOption({ label: "Notch" });
    await page.getByTestId("extrude-op-cut").click();
    await page.getByTestId("extrude-dir-reverse").click();
    await expect(page.getByTestId("objects-to-cut-every")).toHaveText(
      "Every body the cut meets.",
    );
    await page.getByTestId("extrude-distance").fill("10");
    await page.getByTestId("extrude-distance").press("Enter");

    // All four members are notched: the active body alone (the top plate)
    // would have left 576 000 - 18 000.
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBe(WALL_MM3 - 2 * PLATE_NOTCH_MM3 - 2 * STUD_NOTCH_MM3);
    expect((await lastParams(page, wall))["cut_bodies"]).toBe("all");

    // Edit the cut: Objects To Cut lists the four bodies it met, ticked.
    await page.getByTestId("feature-select-9").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    const list = page.getByRole("list", { name: "Objects To Cut" });
    await expect(list.getByRole("checkbox")).toHaveCount(4, {
      timeout: 30_000,
    });
    await expect(list.getByRole("checkbox")).toHaveText([
      "Body 1 · Bottom plate",
      "Body 2 · Stud A",
      "Body 3 · Stud B",
      "Body 4 · Top plate",
    ]);
    for (const box of await list.getByRole("checkbox").all()) {
      await expect(box).toHaveAttribute("aria-checked", "true");
    }
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/objects-to-cut-wall-desktop.png`,
    });

    // Untick Stud A and save: it is left whole, the other three stay cut.
    const studA = wall.members[1] as string;
    await page.getByTestId(`objects-to-cut-${studA}`).click();
    await expect(page.getByTestId(`objects-to-cut-${studA}`)).toHaveAttribute(
      "aria-checked",
      "false",
    );
    await page.getByTestId("extrude-submit").click();
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBe(WALL_MM3 - 2 * PLATE_NOTCH_MM3 - STUD_NOTCH_MM3);
    expect((await lastParams(page, wall))["cut_bodies"]).toEqual(
      [0, 2, 3].map((i) => ({
        kind: "feature",
        feature_id: wall.members[i],
      })),
    );

    // Edit the NARROWED cut: it lists the three bodies it cuts. Unticking
    // Stud B and ticking it back keeps the cut narrowed (every row ticked is
    // not every body: Stud A, left out, is not a row), so the Save changes
    // nothing and Stud A stays whole.
    const narrowed = [0, 2, 3].map((i) => ({
      kind: "feature",
      feature_id: wall.members[i],
    }));
    await page.getByTestId("feature-select-9").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await expect(list.getByRole("checkbox")).toHaveCount(3, {
      timeout: 30_000,
    });
    const studB = wall.members[2] as string;
    await page.getByTestId(`objects-to-cut-${studB}`).click();
    await expect(page.getByTestId(`objects-to-cut-${studB}`)).toHaveAttribute(
      "aria-checked",
      "false",
    );
    await page.getByTestId(`objects-to-cut-${studB}`).click();
    await page.getByTestId("extrude-submit").click();
    await expect(page.getByTestId("extrude-editor")).toHaveCount(0, {
      timeout: 30_000,
    });
    expect((await lastParams(page, wall))["cut_bodies"]).toEqual(narrowed);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBe(WALL_MM3 - 2 * PLATE_NOTCH_MM3 - STUD_NOTCH_MM3);

    // "Cut every body it meets" is the one way back: Stud A is cut again.
    await page.getByTestId("feature-select-9").click();
    await expect(page.getByTestId("extrude-editor")).toBeVisible();
    await page.getByTestId("objects-to-cut-all").click();
    await page.getByTestId("extrude-submit").click();
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBe(WALL_MM3 - 2 * PLATE_NOTCH_MM3 - 2 * STUD_NOTCH_MM3);
    expect((await lastParams(page, wall))["cut_bodies"]).toBe("all");
  });

  test("the Hole dialog's Feature Scope warns rather than drop a scope at Blind", async ({
    page,
  }) => {
    const wall = await seedWall(page);
    await page.goto(`/parts/${wall.partId}`);
    await expect
      .poll(() => partVolume(page), { timeout: 60_000 })
      .toBe(WALL_MM3);
    await expect(page.getByTestId("new-hole")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-hole").click();
    const scope = page.getByRole("list", { name: "Feature Scope" });
    await expect(scope.getByRole("checkbox")).toHaveCount(4);
    const studB = wall.members[2] as string;
    await page.getByTestId(`hole-scope-${studB}`).click();
    await page.getByTestId("hole-depth-blind").click();
    await expect(page.getByTestId("hole-scope-note")).toContainText(
      "1 scoped body is kept, not cut",
    );
    // Back to through-all: the scope is still ticked, not dropped.
    await page.getByTestId("hole-depth-through").click();
    await expect(page.getByTestId(`hole-scope-${studB}`)).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await page.getByTestId("hole-depth-blind").click();
    await page.mouse.move(1400, 900);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/hole-feature-scope-blind-desktop.png`,
    });
  });
});
