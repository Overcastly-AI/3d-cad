import { expect, test, type Page } from "./fixtures";

import {
  clickRefusedControl,
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * PICK-2 — a pick mode is never armed with nothing to pick.
 *
 * THE DEFECT, as the founder met it (AUDIT-PRODUCT R-10): five clicks, two
 * camera angles, nothing happens. The cause is not a raycast that misses — it
 * is an EMPTY SCENE. Every pick overlay in `PartPage` is fetched by a query
 * carrying the identical `meshGlbId !== null` guard (face pick, datum face
 * pick, hole, edge, shell, measure), so when the tip feature builds no body all
 * six go `enabled: false`, `FacePickOverlay` receives `faces === null` and
 * renders nothing at all: no `PickSurface`, no `PickNode`. The panel went on
 * offering the pick anyway, because the armed state is local React state that
 * nothing reset.
 *
 * The state is reached here the way a modeller reaches it: suppress the only
 * body-affecting feature of a part whose hole depends on it. The evaluation
 * then publishes `mesh_glb_id: null` — measured directly against the geometry
 * service — and the hole fails `references_suppressed`.
 *
 * The spec asserts BOTH arms, because a refusal that also refuses the healthy
 * case is not a fix:
 *   - healthy body  → the face pick arms exactly as before (regression guard);
 *   - no built body → the control is present, DISABLED, and carries the reason.
 */

/** A closed, fully-constrained 20x20 square on XY -> a face that extrudes. */
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

/** The exact sentence the refusal states — copy is part of the contract here. */
const REASON =
  "Nothing to pick — the part has no built body. Clear the error in the feature tree, then pick again.";

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

/** A 20 mm cube with a Ø5 through hole on its real top face — all three build. */
async function seedCubeWithHole(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Pick target plate");
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
            // The cube's REAL top face: 20x20 at z = 20, normal +Z. This one
            // resolves, so the healthy arm of the spec is genuinely healthy.
            signature: {
              subshape_type: "face",
              surface: "plane",
              area_mm2: 400,
              centroid: { x: 10, y: 10, z: 20 },
              normal: { x: 0, y: 0, z: 1 },
            },
          },
        },
        position: { x: 10, y: 10, z: 20 },
        diameter_mm: 5,
        depth: { kind: "through_all" },
      },
    },
    expected_tree_version: extrude.tree_version,
  });
  return part.id;
}

test.describe("pick modes refuse to arm with nothing to pick (PICK-2)", () => {
  // Two full evaluations of a cube + through hole, plus a suppress round trip.
  // The default 60 s is not headroom for that under CI load, and a gate that
  // times out on the machine rather than the code teaches nothing.
  test.setTimeout(240_000);

  test("a suppressed body feature disables the face pick and says why", async ({
    page,
  }) => {
    const partId = await seedCubeWithHole(page);
    await page.goto(`/parts/${partId}`);

    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // ── Healthy arm: with a built body the pick arms exactly as it always did.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    const facePick = page.getByTestId("hole-face-pick");
    await expect(facePick).not.toHaveAttribute("aria-disabled", "true");
    await facePick.click();
    await expect(facePick).toHaveAttribute("aria-pressed", "true");
    // …and the overlay it arms really does populate: pickable faces exist.
    await expect(
      page.locator('[data-testid^="plane-pick-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    // Stand the pick down before changing the tree under it.
    await facePick.click();
    await expect(facePick).toHaveAttribute("aria-pressed", "false");
    await page.getByTestId("hole-cancel").click();

    // ── Take the body away: suppressing Extrude1 leaves the evaluation with no
    // body at all (`mesh_glb_id: null`), so no overlay can populate.
    await page.getByTestId("feature-suppress-1").click();
    await expect(page.getByTestId("eval-status")).toHaveText("Failed", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("feature-error-2")).toContainText(
      "references_suppressed",
    );

    // The hole is still inspectable — the editor opens on a failed feature, and
    // that is exactly where the refusal has to be legible.
    await page.getByTestId("feature-select-2").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

    // THE FIX. The control is still there (a vanished affordance teaches
    // nothing), it is disabled, and it carries the reason in its accessible
    // name and on screen.
    const blockedPick = page.getByTestId("hole-face-pick");
    await expect(blockedPick).toBeVisible();
    await expect(blockedPick).toHaveAttribute("aria-disabled", "true");
    await expect(blockedPick).toHaveAccessibleName(
      `Pick the planar face to drill into — ${REASON}`,
    );
    await expect(page.getByTestId("hole-face-pick-reason")).toHaveText(REASON);

    // Clicking it does NOT arm: no `Picking` badge over an overlay that can
    // never populate — the founder's five-clicks-and-nothing-happens state.
    // FORCED on purpose. `aria-disabled` already makes this un-clickable by
    // Playwright's actionability rules (a plain `.click()` waits forever on
    // "element is not enabled"), so an ordinary click would prove the ARIA
    // attribute a second time and never reach the handler. Forcing the event
    // through is what tests the refusal itself, which is the thing that has to
    // hold if the styling ever changes. `clickRefusedControl` adds the half
    // `force` throws away: that a pointer aimed at this control's centre really
    // lands on it, so the refusal below is the app's and not a stray click's.
    await clickRefusedControl(page, blockedPick, "hole-face-pick");
    await expect(blockedPick).toHaveAttribute("aria-pressed", "false");
    await expect(blockedPick).toHaveText("Change");

    // And the scene really is empty of pick targets, which is why arming was
    // refused: the assertion above would be cosmetic without this one.
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      0,
    );

    await page.screenshot({
      path: `${SCREENSHOT_DIR}/pick-no-body-refused-desktop.png`,
    });
  });
});
