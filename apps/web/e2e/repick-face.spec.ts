import { expect, test, type Page } from "./fixtures";

import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * Re-pick repair affordance (FINDINGS #3 follow-up). The kernel now re-matches a
 * same-face reference resiliently, so a hole whose placement face is GENUINELY
 * unresolvable surfaces as a typed `subshape_unresolved` FeatureError. This spec
 * proves the frontend repair: the tree error row offers a one-click "Re-pick
 * face" that opens the hole editor AND re-arms its face pick, so the user can
 * re-attach the lost reference — verified against the real stack (no mocks).
 *
 * The unresolvable state is seeded directly: a hole feature carrying a bogus
 * planar-face signature (an area/centroid/normal that matches no face of the
 * cube), which the resolver cannot re-match → `subshape_unresolved`.
 */

/** A closed, fully-constrained 20×20 square on XY → a face that extrudes. */
const SQUARE_20 = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 20, y: 0 } },
    { id: "e2", kind: "line", start: { x: 20, y: 0 }, end: { x: 20, y: 20 } },
    { id: "e3", kind: "line", start: { x: 20, y: 20 }, end: { x: 0, y: 20 } },
    { id: "e4", kind: "line", start: { x: 0, y: 20 }, end: { x: 0, y: 0 } },
  ],
  constraints: [
    {
      kind: "coincident",
      a: { entity: "e1", point: "end" },
      b: { entity: "e2", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e2", point: "end" },
      b: { entity: "e3", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e3", point: "end" },
      b: { entity: "e4", point: "start" },
    },
    {
      kind: "coincident",
      a: { entity: "e4", point: "end" },
      b: { entity: "e1", point: "start" },
    },
    { kind: "horizontal", entity: "e1" },
    { kind: "vertical", entity: "e2" },
    { kind: "horizontal", entity: "e3" },
    { kind: "vertical", entity: "e4" },
    { kind: "distance", entity: "e1", value_mm: 20 },
    { kind: "distance", entity: "e2", value_mm: 20 },
    { kind: "fixed", point: { entity: "e1", point: "start" } },
  ],
};

async function createFeature(
  page: Page,
  token: string,
  partId: string,
  body: unknown,
): Promise<{ feature: { id: string }; tree_version: number }> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `e2e create feature failed: ${response.status()} ${await response.text()}`,
    );
  }
  return (await response.json()) as {
    feature: { id: string };
    tree_version: number;
  };
}

/**
 * Seed a 20 mm cube plus a hole whose placement face cannot be resolved.
 *
 * `position` is the stored world drill point. Its default is the bogus face's
 * own centre; T-22's test passes an OFF-CENTRE point so a repair that re-seeds
 * the placement is distinguishable from one that preserves it.
 */
async function seedUnresolvableHole(
  page: Page,
  position: { x: number; y: number; z: number } = { x: 500, y: 500, z: 500 },
): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Re-pick plate");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  const extrude = await createFeature(page, account.token, part.id, {
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
  await createFeature(page, account.token, part.id, {
    name: "Hole1",
    feature: {
      type: "hole",
      version: 1,
      params: {
        face: {
          kind: "subshape",
          feature_id: extrude.feature.id,
          subshape_type: "face",
          selector: {
            selector_version: 1,
            signature: {
              subshape_type: "face",
              surface: "plane",
              // Deliberately off the body: no face of the cube has this
              // area/centroid/normal, so the resilient resolver still can't
              // match it → subshape_unresolved.
              area_mm2: 987654,
              centroid: { x: 500, y: 500, z: 500 },
              normal: { x: 0, y: 0, z: 1 },
            },
          },
        },
        position,
        diameter_mm: 5,
        depth: { kind: "through_all" },
      },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

/**
 * Click the body's TOP face pick node — chosen by the greatest z in the node's
 * accessible name, so it never depends on screen projection or a face index.
 */
async function clickTopFaceNode(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

test.describe("re-pick repair — a lost face reference is re-attachable", () => {
  test("subshape_unresolved offers Re-pick face → arms the hole face pick", async ({
    page,
  }) => {
    const partId = await seedUnresolvableHole(page);
    await page.goto(`/parts/${partId}`);

    // The tree evaluates and the Hole row (index 2) reports the typed error.
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    const errorRow = page.getByTestId("feature-error-2");
    await expect(errorRow).toBeVisible();
    await expect(errorRow).toContainText("subshape_unresolved");

    // The last-good body (the extrude) still renders — wait for it so the frame
    // captures the lit solid, not a pre-paint flash.
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);

    // Before: the honest error with its one-click repair affordance.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/repick-face-error-desktop.png`,
    });

    // The repair is offered and re-arms the face pick for the hole feature.
    const repick = page.getByTestId("feature-repick-face-2");
    await expect(repick).toBeVisible();
    await repick.click();

    // The hole editor opens with its FACE pick armed — the user can now re-pick.
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(page.getByTestId("hole-face-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // After: the hole editor open, face selection re-armed.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/repick-face-armed-desktop.png`,
    });
  });

  /**
   * T-22 — the repair must not destroy what it repairs. `Re-pick face` used to
   * fold the new face in through the same path a BRAND NEW hole takes, which
   * re-seeds the drill point to the face's centroid: a hole authored off-centre
   * came back at 0, 0 with its own parameters overwritten and nothing in the UI
   * to recover them from, and the next rebuild failed `hole_off_body`.
   *
   * The stored hole here sits at face-frame (14.5, 5.5) on a plane the resolver
   * cannot match. Re-picking the cube's real top face must move it to that
   * face's plane and NOTHING else — same in-face coordinates, same diameter,
   * same depth — so the rebuild succeeds where the audit's ended in an error.
   */
  test("Re-pick face preserves the hole's position — only the anchor changes", async ({
    page,
  }) => {
    // Face frame on a +Z face is origin-at-part-origin with u = +X, v = +Y, so
    // this stored point reads as (14.5, 5.5) in the editor's X/Y cells — well
    // off the 20 mm cube's top-face centre of (10, 10), which is what a
    // re-seeding repair would produce.
    const partId = await seedUnresolvableHole(page, {
      x: 14.5,
      y: 5.5,
      z: 500,
    });
    await page.goto(`/parts/${partId}`);

    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toContainText(
      "subshape_unresolved",
    );

    await page.getByTestId("feature-repick-face-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

    // The feature's OWN parameters, as stored — the baseline the repair must
    // not move.
    const x = page.getByTestId("hole-position-x");
    const y = page.getByTestId("hole-position-y");
    await expect(x).toHaveValue("14.5");
    await expect(y).toHaveValue("5.5");
    await expect(page.getByTestId("hole-diameter")).toHaveValue("5");

    // Re-attach the reference: click the cube's real top face (z = 20).
    await clickTopFaceNode(page);

    // Only the anchor changed. Under the defect these read "10" and "10".
    await expect(x).toHaveValue("14.5");
    await expect(y).toHaveValue("5.5");
    await expect(page.getByTestId("hole-diameter")).toHaveValue("5");

    // And the repaired hole rebuilds: 20^3 less a Ø5 through-all bore.
    await page.getByTestId("hole-submit").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toHaveCount(0);
    await expect(page.getByTestId("prop-volume")).toContainText("7,607", {
      timeout: 30_000,
    });

    // Reopening the feature shows the values survived the write, which is how
    // the audit confirmed the loss in the first place.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(page.getByTestId("hole-position-x")).toHaveValue("14.5");
    await expect(page.getByTestId("hole-position-y")).toHaveValue("5.5");

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/repick-face-preserved-desktop.png`,
    });
  });

  /**
   * The other half of T-22, and the case its sibling `pick-anchor.spec.ts` used
   * to exercise BY ACCIDENT: preserving the placement is right, and a preserved
   * placement can still miss the face the user just picked (they re-attached the
   * hole to a face the point was never over). The two ways to make that go away
   * are both defects — silently re-seeding the point destroys the feature's own
   * parameters (the audit T-22 fixed), and silently writing it builds a part
   * with no hole in it. So the tool SAYS SO, twice and in the user's terms:
   *
   * - before the write, the live material check on the face calls it out, with
   *   the fix in the message ("move it onto the face") and the coordinates still
   *   sitting there in the X/Y cells to be corrected;
   * - if they save anyway, the rebuild names `hole_off_body` on the row rather
   *   than pretending the hole exists.
   *
   * The check WARNS and never blocks (see `features/facePlacement`): the kernel
   * is the authority on what is on the body, and the client's coplanar-edge
   * approximation must not be able to veto a hole the kernel would accept.
   */
  test("a preserved placement that misses the re-picked face is called out, not silently written", async ({
    page,
  }) => {
    // A stored point on no body at all — face-frame (500, 500) once re-anchored
    // onto the cube's top face, which is 20 mm across.
    const partId = await seedUnresolvableHole(page, { x: 500, y: 500, z: 500 });
    await page.goto(`/parts/${partId}`);

    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toContainText(
      "subshape_unresolved",
    );

    await page.getByTestId("feature-repick-face-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await clickTopFaceNode(page);

    // The placement is PRESERVED — the repair did not quietly move the hole.
    await expect(page.getByTestId("hole-position-x")).toHaveValue("500");
    await expect(page.getByTestId("hole-position-y")).toHaveValue("500");

    // And the editor says, in place, that it no longer lands on the face.
    const check = page.getByTestId("hole-position-check");
    await expect(check).toHaveAttribute("data-verdict", "outside");
    await expect(check).toContainText("Off the face outline");

    // Advisory, not a veto: the write is still offered (the kernel decides).
    const submit = page.getByTestId("hole-submit");
    await expect(submit).toBeEnabled();

    // Saving anyway is honest about the outcome — a named, actionable rebuild
    // error on the row, never a silent "solved" over a part with no hole in it.
    // The row's error CODE is what is asserted, not `eval-status`: the tree was
    // already Failed on `subshape_unresolved`, so "still Failed" would pass
    // without the write ever landing. The code CHANGING is the state change.
    await submit.click();
    await expect(page.getByTestId("hole-editor")).toHaveCount(0);
    const errorRow = page.getByTestId("feature-error-2");
    await expect(errorRow).toContainText("hole_off_body", { timeout: 30_000 });
    await expect(errorRow).toContainText("Move the point onto solid material");
  });
});
