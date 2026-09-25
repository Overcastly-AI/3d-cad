import { expect, test, type Page } from "./fixtures";

import { createFeature, SQUARE_20 } from "./partSeed";
import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * EDGE-RESOLVE-WARN-1, the web half: a fillet whose picked edge MOVED says so.
 *
 * The kernel re-finds a picked edge in tiers: exactly, by a durable invariant,
 * or as the edge its two stored neighbouring faces share ("adjacent"). Only the
 * first is certain. The adjacent tier can land on the wrong edge without an
 * error, and until this item nothing on screen changed when it fired: the tree
 * row read OK either way.
 *
 * The fixture is the smallest real case. A 20 mm cube with a fillet on its
 * vertical edge at (20, 0) is widened to 30 mm, so that edge moves onto a
 * parallel line and is re-found only by adjacency (measured through the API:
 * `worst_tier: "adjacent"`, `adjacent: 1`). The fillet is BUILT through the UI,
 * so the fresh create is covered too: it resolves exactly and must say nothing.
 *
 * `SHOT_TAG=before` names the screenshots for a capture against the old tree.
 * They are taken before the assertions, so a red run still leaves its picture.
 */
const SHOT_TAG = process.env["SHOT_TAG"] ?? "after";

/** The fillet is the third row: Sketch1, Extrude1, Fillet1. */
const FILLET = 2;

interface Fixture {
  token: string;
  partId: string;
  sketchId: string;
}

async function seedCube(page: Page): Promise<Fixture> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Moved edge");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return { token: account.token, partId: part.id, sketchId: sketch.feature.id };
}

/** Click the pick node of the edge whose mid-span is at (x, y, z). */
async function pickEdgeAt(page: Page, x: number, y: number, z: number) {
  const node = page.locator(
    `[data-testid^="edge-pick-"][aria-label*="centred at ${x}, ${y}, ${z} millimetres"]`,
  );
  await expect(node).toHaveCount(1, { timeout: 20_000 });
  await node.click();
}

async function waitSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
}

/** Fillet the vertical edge at (20, 0) through the real editor. */
async function filletTheCorner(page: Page): Promise<void> {
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-radius").fill("3");
  await page.getByTestId("fillet-mode-pick").click();
  await pickEdgeAt(page, 20, 0, 10);
  await expect(page.getByTestId("selected-count")).toHaveText("1 edge picked");
  await page.getByTestId("fillet-submit").click();
  await expect(page.getByTestId("feature-row")).toHaveCount(3);
  await waitSolved(page);
}

/** The upstream edit: the sketch's width 20 -> 30, through the API. */
async function widenTheSketch(page: Page, fx: Fixture): Promise<void> {
  const tree = await page.request.get(`/api/v1/parts/${fx.partId}/features`, {
    headers: { Authorization: `Bearer ${fx.token}` },
  });
  const { tree_version } = (await tree.json()) as { tree_version: number };
  const widened = structuredClone(SQUARE_20);
  for (const c of widened.constraints) {
    if (c.kind === "distance" && c.entity === "e1") c.value_mm = 30;
  }
  const response = await page.request.patch(
    `/api/v1/parts/${fx.partId}/features/${fx.sketchId}`,
    {
      data: {
        feature: { type: "sketch", version: 1, params: widened },
        expected_tree_version: tree_version,
      },
      headers: { Authorization: `Bearer ${fx.token}` },
    },
  );
  expect(response.ok(), await response.text()).toBe(true);
}

/** What the kernel reports for the fillet, read off the wire. */
async function filletTier(page: Page, fx: Fixture): Promise<string | null> {
  const response = await page.request.post(
    `/api/v1/parts/${fx.partId}/evaluate`,
    { headers: { Authorization: `Bearer ${fx.token}` } },
  );
  const body = (await response.json()) as {
    features: { subshape_resolution?: { worst_tier: string } | null }[];
  };
  return body.features[FILLET]?.subshape_resolution?.worst_tier ?? null;
}

for (const size of [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
]) {
  test(`a fillet on a moved edge says so, and re-picks, at ${size.width}`, async ({
    page,
  }) => {
    test.setTimeout(180_000);
    await page.setViewportSize(size);
    const fx = await seedCube(page);
    await page.goto(`/parts/${fx.partId}`);
    await waitSolved(page);

    // A FRESH create resolves exactly, and says nothing.
    await filletTheCorner(page);
    expect(await filletTier(page, fx)).toBe("exact");
    await expect(page.getByTestId(`feature-resolution-${FILLET}`)).toHaveCount(
      0,
    );

    // The upstream edit moves the edge; the kernel re-finds it by adjacency.
    await widenTheSketch(page, fx);
    expect(await filletTier(page, fx)).toBe("adjacent");
    await page.reload();
    await waitSolved(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/edge-resolve-warn-tree-${size.width}-${SHOT_TAG}.png`,
    });

    if (SHOT_TAG === "before") {
      // The old tree has no notice to follow: open the fillet the plain way,
      // to show what its editor said about the moved edge (nothing).
      await page.getByTestId(`feature-select-${FILLET}`).click();
      await expect(page.getByTestId("fillet-editor")).toBeVisible();
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/edge-resolve-warn-editor-${size.width}-${SHOT_TAG}.png`,
      });
    }

    // The tree row says it, names the count, and does not claim an error.
    const notice = page.getByTestId(`feature-resolution-${FILLET}`);
    await expect(notice).toBeVisible();
    await expect(notice).toContainText(
      "1 of 1 picked edges moved in an earlier edit",
    );
    await expect(page.getByTestId(`feature-error-${FILLET}`)).toHaveCount(0);

    // Re-pick: the editor opens with the moved pick dropped, ready to pick.
    await page.getByTestId(`feature-repick-edges-${FILLET}`).click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await expect(page.getByTestId("edge-resolution-notice")).toBeVisible();
    await expect(page.getByTestId("selected-count")).toHaveText(
      "No edges picked",
    );
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/edge-resolve-warn-editor-${size.width}-${SHOT_TAG}.png`,
    });
    // The edge where it is now, on the body the fillet is built on.
    await pickEdgeAt(page, 30, 0, 10);
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
    );
    await page.getByTestId("fillet-submit").click();
    await expect(page.getByTestId("fillet-editor")).toHaveCount(0);
    await waitSolved(page);

    // The repair holds: the kernel re-finds the new pick exactly, and the
    // notice is gone.
    expect(await filletTier(page, fx)).toBe("exact");
    await expect(page.getByTestId(`feature-resolution-${FILLET}`)).toHaveCount(
      0,
    );
  });
}

test("the notice can be dismissed, and stays dismissed for that edit", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const fx = await seedCube(page);
  await page.goto(`/parts/${fx.partId}`);
  await waitSolved(page);
  await filletTheCorner(page);
  await widenTheSketch(page, fx);
  await page.reload();
  await waitSolved(page);

  const notice = page.getByTestId(`feature-resolution-${FILLET}`);
  await expect(notice).toBeVisible();
  await page.getByTestId(`feature-resolution-dismiss-${FILLET}`).click();
  await expect(notice).toHaveCount(0);
  // Selecting another row re-renders the tree; the dismissal holds.
  await page.getByTestId("feature-select-1").click();
  await expect(notice).toHaveCount(0);
});
