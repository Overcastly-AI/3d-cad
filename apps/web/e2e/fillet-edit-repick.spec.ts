/**
 * FILLET-EDIT-REPICK (reference run 2026-09-30): a fillet on the wrong edge
 * could only be fixed by deleting it and making it again (three cycles on the
 * enclosure). Fusion 360's Edit Feature rolls the timeline back to the feature
 * and lets you re-pick on the body it is built on, so:
 *
 *  - Edit on a fillet rolls the travel stop back to just before it: the
 *    viewport shows the fillet's INPUT body, and the stored picks are drawn as
 *    picked marks on it;
 *  - a click removes a pick, another click adds one;
 *  - Save writes the new edge refs, puts the stop back at the tip, and every
 *    feature after the fillet (a chamfer here) still resolves;
 *  - Cancel puts the stop back and leaves nothing of the edit behind: the
 *    stored refs are unchanged, a new fillet does not open seeded with the
 *    edit's picks, and Edit again shows the original picks.
 *
 * The part is the reference run's enclosure without its draft: 80 x 60 x 40,
 * shelled to a 2 mm wall with the top open. Fillet1 is made through the UI on
 * the outer AND the inner front rim (the reference run's mistake), then a
 * chamfer on the bottom front edge follows it.
 *
 * `SHOT_TAG=before` names the screenshots for a capture against the old tree;
 * they are taken before the assertions, so a red run still leaves its picture.
 */
import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, waitForCameraStill } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import {
  createPartViaApi,
  expectSeatsSettled,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

test.use({ viewport: { width: 1280, height: 800 } });

const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

const W = 80;
const D = 60;
const H = 40;
const WALL = 2;
// Under half the wall: the outer and inner rim fillets share the 2 mm rim face.
const R = 0.5;

/** Rows: Sketch1, Extrude1, Shell1, Fillet1, Chamfer1. */
const FILLET = 3;

const OUTER_FRONT = "40, 0, 40";
const INNER_FRONT = "40, 2, 40";
const OUTER_BACK = "40, 60, 40";
const BOTTOM_FRONT = "40, 0, 0";

interface Fixture {
  token: string;
  partId: string;
  shellId: string;
}

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

interface StoredTree {
  tree_version: number;
  rollback_feature_id: string | null;
  features: {
    id: string;
    name: string;
    feature: {
      params: {
        edges?: {
          kind: string;
          refs?: { selector: { signature: { midpoint: Vec3 } } }[];
        };
      };
    };
  }[];
}

async function readTree(page: Page, fx: Fixture): Promise<StoredTree> {
  const response = await page.request.get(
    `/api/v1/parts/${fx.partId}/features`,
    { headers: { Authorization: `Bearer ${fx.token}` } },
  );
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()) as StoredTree;
}

/** Fillet1's stored edge refs, as sorted "x, y, z" mid-spans. */
async function storedFilletEdges(page: Page, fx: Fixture): Promise<string[]> {
  const tree = await readTree(page, fx);
  const refs = tree.features[FILLET]?.feature.params.edges?.refs ?? [];
  return refs
    .map(({ selector }) => {
      const m = selector.signature.midpoint;
      return [m.x, m.y, m.z].map((v) => Math.round(v * 1000) / 1000).join(", ");
    })
    .sort();
}

interface Evaluated {
  statuses: string[];
  filletTier: string | null;
  volume: number;
}

async function evaluate(page: Page, fx: Fixture): Promise<Evaluated> {
  const response = await page.request.post(
    `/api/v1/parts/${fx.partId}/evaluate`,
    { headers: { Authorization: `Bearer ${fx.token}` } },
  );
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as {
    features: {
      status: string;
      subshape_resolution?: { worst_tier: string } | null;
    }[];
    properties: { volume: number } | null;
  };
  return {
    statuses: body.features.map((f) => f.status),
    filletTier: body.features[FILLET]?.subshape_resolution?.worst_tier ?? null,
    volume: body.properties?.volume ?? NaN,
  };
}

function mark(page: Page, at: string) {
  return page.locator(
    `[data-testid^="edge-pick-"][aria-label*="centred at ${at} millimetres"]`,
  );
}

/** Click the pick mark of the edge whose mid-span is `at`. */
async function clickMark(page: Page, at: string): Promise<void> {
  const node = mark(page, at);
  await expect(node).toHaveCount(1, { timeout: 30_000 });
  await expectSeatsSettled(page, `before clicking ${at}`);
  await node.click();
}

/** The top face's pick mark (the face a top-open shell leaves open). */
function topFace(page: Page) {
  return page.locator(
    `[data-testid^="shell-face-"][aria-label*="centred at ${W / 2}, ${D / 2}, ${H} millimetres"]`,
  );
}

async function waitSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 90_000,
  });
}

async function seedEnclosure(
  page: Page,
  { shellOnly = false }: { shellOnly?: boolean } = {},
): Promise<Fixture> {
  await installSceneProbe(page);
  const account = await seedSession(page);
  const token = account.token;
  const part = await createPartViaApi(page, token, "Enclosure housing");
  const sketch = await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, W, D),
    },
    expected_tree_version: 0,
  });
  const solid = await createFeature(page, token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: H,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  const shell = shellOnly
    ? null
    : await createFeature(page, token, part.id, {
        name: "Shell1",
        feature: {
          type: "shell",
          version: 1,
          params: {
            thickness_mm: WALL,
            faces: {
              kind: "faces",
              refs: [
                {
                  kind: "subshape",
                  feature_id: solid.feature.id,
                  subshape_type: "face",
                  selector: {
                    selector_version: 1,
                    signature: {
                      subshape_type: "face",
                      surface: "plane",
                      area_mm2: W * D,
                      centroid: { x: W / 2, y: D / 2, z: H },
                      normal: { x: 0, y: 0, z: 1 },
                    },
                  },
                },
              ],
            },
          },
        },
        expected_tree_version: solid.tree_version,
      });
  const fx = {
    token,
    partId: part.id,
    shellId: shell === null ? "" : shell.feature.id,
  };

  await page.goto(`/parts/${part.id}`);
  await waitSolved(page);
  await page.getByTestId("view-iso").click();
  await waitForCameraStill(page);
  if (shellOnly) {
    // Shell1 through the real editor, so its open face is the overlay's own.
    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill(String(WALL));
    const top = topFace(page);
    await expect(top).toHaveCount(1, { timeout: 30_000 });
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-face-mark-seats",
      "settled",
      { timeout: 60_000 },
    );
    await top.click();
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
    );
    await page.getByTestId("shell-submit").click();
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await waitSolved(page);
    return fx;
  }

  // Fillet1 on the outer AND the inner front rim, through the real editor.
  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await page.getByTestId("fillet-radius").fill(String(R));
  await page.getByTestId("fillet-mode-pick").click();
  await clickMark(page, OUTER_FRONT);
  await clickMark(page, INNER_FRONT);
  await expect(page.getByTestId("selected-count")).toHaveText("2 edges picked");
  await page.getByTestId("fillet-submit").click();
  await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
  await expect(page.getByTestId("feature-row")).toHaveCount(4);
  await waitSolved(page);

  // A feature AFTER the fillet, which must still resolve once it is edited.
  await page.getByTestId("new-chamfer").click();
  await page.getByTestId("chamfer-distance").fill("1");
  await page.getByTestId("chamfer-mode-pick").click();
  await clickMark(page, BOTTOM_FRONT);
  await page.getByTestId("chamfer-submit").click();
  await expect(page.getByTestId("chamfer-editor")).toHaveCount(0);
  await expect(page.getByTestId("feature-row")).toHaveCount(5);
  await waitSolved(page);
  await expect(page.getByTestId("timeline-position")).toHaveText("05/05");
  return fx;
}

/** Open Fillet1's editor from the tree. */
async function editFillet(page: Page): Promise<void> {
  await page.getByTestId(`feature-select-${FILLET}`).click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
}

async function expectRolledBack(page: Page, fx: Fixture): Promise<void> {
  // The stop sits after Shell1, the fillet's input, as Fusion's Edit Feature
  // rolls the timeline marker back to the feature.
  await expect(page.getByTestId("timeline-position")).toHaveText("03/05", {
    timeout: 30_000,
  });
  expect((await readTree(page, fx)).rollback_feature_id).toBe(fx.shellId);
  await waitSolved(page);
}

test("editing a fillet rolls back to its input body; a re-pick saves and everything after it resolves", async ({
  page,
}) => {
  test.setTimeout(360_000);
  const fx = await seedEnclosure(page);
  expect(await storedFilletEdges(page, fx)).toEqual(
    [OUTER_FRONT, INNER_FRONT].sort(),
  );
  const before = await evaluate(page, fx);
  expect(before.statuses).toEqual(["ok", "ok", "ok", "ok", "ok"]);

  await editFillet(page);
  if (SHOT_TAG === "before") {
    await page.waitForTimeout(4_000);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/fillet-edit-repick-1280-${SHOT_TAG}.png`,
    });
  }
  await expectRolledBack(page, fx);

  // The stored picks are drawn as picked marks on the input body.
  await expect(page.getByTestId("selected-count")).toHaveText("2 edges picked");
  await expect(mark(page, OUTER_FRONT)).toHaveAttribute("aria-pressed", "true");
  await expect(mark(page, INNER_FRONT)).toHaveAttribute("aria-pressed", "true");
  await expect(mark(page, OUTER_BACK)).toHaveAttribute("aria-pressed", "false");
  await expectSeatsSettled(page, "fillet edit armed");
  await page.mouse.move(4, 4);
  if (SHOT_TAG !== "before") {
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/fillet-edit-repick-1280-${SHOT_TAG}.png`,
    });
  }

  // Remove the wrong (inner) edge, add the outer back rim.
  await clickMark(page, INNER_FRONT);
  await expect(mark(page, INNER_FRONT)).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await clickMark(page, OUTER_BACK);
  await expect(mark(page, OUTER_BACK)).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("selected-count")).toHaveText("2 edges picked");

  await page.getByTestId("fillet-submit").click();
  await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
  await expect(page.getByTestId("timeline-position")).toHaveText("05/05", {
    timeout: 30_000,
  });
  await waitSolved(page);

  // The stored refs are the new picks, the stop is back at the tip, and the
  // chamfer after the fillet still resolves.
  expect(await storedFilletEdges(page, fx)).toEqual(
    [OUTER_FRONT, OUTER_BACK].sort(),
  );
  expect((await readTree(page, fx)).rollback_feature_id).toBeNull();
  const after = await evaluate(page, fx);
  expect(after.statuses).toEqual(["ok", "ok", "ok", "ok", "ok"]);
  expect(after.filletTier).toBe("exact");
  // The result: a straight r fillet between two square faces, ending on
  // square faces, removes a (1 - pi/4) r^2 prism. The inner front rim is 76 mm
  // long, the outer back rim 80 mm, so the body gains the one and loses the
  // other.
  const prism = (1 - Math.PI / 4) * R * R;
  const expected = before.volume + prism * (W - 2 * WALL) - prism * W;
  expect(after.volume).toBeCloseTo(expected, 2);

  // Chamfer edits the same way: rolled back to its input (the re-picked
  // fillet), its stored pick drawn picked; Escape puts the stop back.
  await page.getByTestId(`feature-select-${FILLET + 1}`).click();
  await expect(page.getByTestId("chamfer-editor")).toBeVisible();
  await expect(page.getByTestId("timeline-position")).toHaveText("04/05", {
    timeout: 30_000,
  });
  await expect(page.getByTestId("selected-count")).toHaveText("1 edge picked");
  await expect(mark(page, BOTTOM_FRONT)).toHaveAttribute(
    "aria-pressed",
    "true",
    { timeout: 30_000 },
  );
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("chamfer-editor")).toHaveCount(0);
  await expect(page.getByTestId("timeline-position")).toHaveText("05/05", {
    timeout: 30_000,
  });
});

test("Cancel on a fillet edit restores its picks exactly and puts the timeline back", async ({
  page,
}) => {
  test.setTimeout(360_000);
  const fx = await seedEnclosure(page);
  const storedBefore = await storedFilletEdges(page, fx);
  const versionBefore = (await readTree(page, fx)).tree_version;

  await editFillet(page);
  await expectRolledBack(page, fx);
  await expect(mark(page, INNER_FRONT)).toHaveAttribute("aria-pressed", "true");
  await clickMark(page, INNER_FRONT);
  await clickMark(page, OUTER_BACK);
  await expect(mark(page, INNER_FRONT)).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(mark(page, OUTER_BACK)).toHaveAttribute("aria-pressed", "true");

  await page.getByTestId("fillet-cancel").click();
  await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
  await expect(page.getByTestId("timeline-position")).toHaveText("05/05", {
    timeout: 30_000,
  });
  await waitSolved(page);

  // Nothing was written but the stop, and the stop is back at the tip.
  const tree = await readTree(page, fx);
  expect(tree.rollback_feature_id).toBeNull();
  expect(await storedFilletEdges(page, fx)).toEqual(storedBefore);
  // Two stop moves (out and back), no feature write.
  expect(tree.tree_version).toBe(versionBefore + 2);

  // The cancelled picks do not seed the next command.
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/fillet-edit-cancel-1280-${SHOT_TAG}.png`,
  });
  await expect(page.getByTestId("fillet-edges")).toBeVisible();
  await expect(page.getByTestId("selected-count")).toHaveCount(0);
  await page.getByTestId("fillet-cancel").click();
  await expect(page.getByTestId("fillet-editor")).toHaveCount(0);

  // Edit again: the original picks, exactly.
  await editFillet(page);
  await expectRolledBack(page, fx);
  await expect(page.getByTestId("selected-count")).toHaveText("2 edges picked");
  await expect(mark(page, OUTER_FRONT)).toHaveAttribute("aria-pressed", "true");
  await expect(mark(page, INNER_FRONT)).toHaveAttribute("aria-pressed", "true");
  await expect(mark(page, OUTER_BACK)).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
  await expect(page.getByTestId("timeline-position")).toHaveText("05/05", {
    timeout: 30_000,
  });
});

test("editing a shell rolls back to its input body and shows its open face picked", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const fx = await seedEnclosure(page, { shellOnly: true });
  const shellParams = JSON.stringify(
    (await readTree(page, fx)).features[2]?.feature.params,
  );
  await expect(page.getByTestId("timeline-position")).toHaveText("03/03");

  await page.getByTestId("feature-select-2").click();
  await expect(page.getByTestId("shell-editor")).toBeVisible();
  // At the tip the open top face is gone (it is what the shell removed); on
  // the input body it is there, and drawn picked.
  await expect(page.getByTestId("timeline-position")).toHaveText("02/03", {
    timeout: 30_000,
  });
  await waitSolved(page);
  const top = topFace(page);
  await expect(top).toHaveCount(1, { timeout: 30_000 });
  await expect(top).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("shell-open-count")).toHaveText("1 face open");

  await page.getByTestId("shell-cancel").click();
  await expect(page.getByTestId("shell-editor")).toHaveCount(0);
  await expect(page.getByTestId("timeline-position")).toHaveText("03/03", {
    timeout: 30_000,
  });
  const tree = await readTree(page, fx);
  expect(tree.rollback_feature_id).toBeNull();
  expect(JSON.stringify(tree.features[2]?.feature.params)).toBe(shellParams);
});
