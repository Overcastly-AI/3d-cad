import { expect, test, type Page } from "./fixtures";

import { SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FB-4 — "I select a sketch do a cut it somehow misses everything going a
 * different way."
 *
 * A sketch seated on a model face inherits that face's OUTWARD normal (the
 * kernel's `resolve_face_plane`), so the old hardcoded `direction: "normal"`
 * default swept every cut straight OUT of the solid. The part came back
 * unchanged with a typed `cut_removed_nothing` error, which read as user error
 * for months while the default was ours.
 *
 * The gate is geometric, not cosmetic: a 20 mm cube (8 000 mm³) with a 10 × 10
 * pocket cut 5 mm deep from its top face must weigh in at exactly
 * 8 000 − 10 × 10 × 5 = 7 500 mm³. Measured here against the real stack, this
 * seed reproduces the founder's report exactly on the old default — the
 * `direction: "normal"` cut evaluates to `cut_removed_nothing` — so the spec
 * fails loudly if the default ever regresses.
 */

/** The 20 mm cube's top face: the seat the pocket sketch is authored on. */
const TOP_FACE_SIGNATURE = {
  subshape_type: "face",
  surface: "plane",
  normal: { x: 0, y: 0, z: 1 },
  centroid: { x: 10, y: 10, z: 20 },
  area_mm2: 400,
};

const CUBE_VOLUME_MM3 = 20 * 20 * 20;
const POCKET_VOLUME_MM3 = 10 * 10 * 5;

/** A closed rectangle at (x0,y0), w × h, on `plane` — exact, no solver drift. */
function rectangle(
  x0: number,
  y0: number,
  w: number,
  h: number,
  plane: unknown,
) {
  return {
    plane,
    entities: [
      {
        id: "e1",
        kind: "line",
        start: { x: x0, y: y0 },
        end: { x: x0 + w, y: y0 },
      },
      {
        id: "e2",
        kind: "line",
        start: { x: x0 + w, y: y0 },
        end: { x: x0 + w, y: y0 + h },
      },
      {
        id: "e3",
        kind: "line",
        start: { x: x0 + w, y: y0 + h },
        end: { x: x0, y: y0 + h },
      },
      {
        id: "e4",
        kind: "line",
        start: { x: x0, y: y0 + h },
        end: { x: x0, y: y0 },
      },
    ],
    constraints: [],
  };
}

/** The body volume (mm³) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

interface SeededPart {
  id: string;
  /** The face-seated pocket profile (the founder's case). */
  faceSketchId: string;
  /** A second profile on the XY origin datum — no material side to infer. */
  datumSketchId: string;
}

/**
 * A 20 mm cube with TWO pocket profiles: one on the cube's top face (through a
 * real `on_face` datum) and one on the XY origin datum. Seeded through the real
 * gateway so the geometry is exact and the spec pays browser time only for the
 * surface under test — the extrude editor.
 */
async function seedCubeWithProfiles(page: Page): Promise<SeededPart> {
  const account = await seedSession(page);
  const headers = { Authorization: `Bearer ${account.token}` };

  const partResponse = await page.request.post("/api/v1/parts", {
    data: { name: "Pocket in a face" },
    headers,
  });
  if (!partResponse.ok()) {
    throw new Error(`e2e create part failed: ${partResponse.status()}`);
  }
  const partId = ((await partResponse.json()) as { id: string }).id;

  const post = async (
    body: unknown,
  ): Promise<{ id: string; version: number }> => {
    const response = await page.request.post(
      `/api/v1/parts/${partId}/features`,
      { data: body, headers },
    );
    if (!response.ok()) {
      throw new Error(
        `e2e feature failed: ${response.status()} ${await response.text()}`,
      );
    }
    const json = (await response.json()) as {
      feature: { id: string };
      tree_version: number;
    };
    return { id: json.feature.id, version: json.tree_version };
  };

  const plateProfile = await post({
    name: "Plate profile",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangle(0, 0, 20, 20, { kind: "datum_plane", plane: "XY" }),
    },
    expected_tree_version: 0,
  });
  const plate = await post({
    name: "Plate",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: plateProfile.id },
        distance_mm: 20,
        operation: "add",
        direction: "normal",
        merge: true,
      },
    },
    expected_tree_version: plateProfile.version,
  });
  // The datum the sketch-on-face flow authors when you pick a face: its plane
  // adopts the face, normal and all.
  const datum = await post({
    name: "Plane1",
    feature: {
      type: "datum",
      version: 1,
      params: {
        kind: "on_face",
        face: {
          kind: "subshape",
          feature_id: plate.id,
          subshape_type: "face",
          selector: { selector_version: 1, signature: TOP_FACE_SIGNATURE },
        },
        offset_mm: 0,
      },
    },
    expected_tree_version: plate.version,
  });
  // Centred on the face origin (its centroid), so the pocket is well inside the
  // 20 × 20 top face and the closed-form volume holds.
  const datumProfile = await post({
    name: "Base pocket profile",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangle(5, 5, 10, 10, { kind: "datum_plane", plane: "XY" }),
    },
    expected_tree_version: datum.version,
  });
  const faceProfile = await post({
    name: "Face pocket profile",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangle(-5, -5, 10, 10, {
        kind: "feature",
        feature_id: datum.id,
      }),
    },
    expected_tree_version: datumProfile.version,
  });

  return {
    id: partId,
    faceSketchId: faceProfile.id,
    datumSketchId: datumProfile.id,
  };
}

/** Open the part and wait for the seeded cube to render + report itself. */
async function openPart(page: Page, part: SeededPart): Promise<void> {
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expect
    .poll(() => bodyVolume(page), { timeout: 30_000 })
    .toBe(CUBE_VOLUME_MM3);
}

/** Open the extrude editor and point it at `profileName`. */
async function openExtrudeOn(page: Page, profileName: string): Promise<void> {
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible();
  await page
    .getByTestId("extrude-profile")
    .selectOption({ label: profileName });
}

test.describe("a cut goes INTO the material (FB-4)", () => {
  test("cutting a face-seated profile removes exactly the pocket", async ({
    page,
  }) => {
    const part = await seedCubeWithProfiles(page);
    await openPart(page, part);
    await openExtrudeOn(page, "Face pocket profile");

    // An ADD off a face still builds outward — the seat only reverses a cut.
    await expect(page.getByTestId("extrude-op-add")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("extrude-dir-normal")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // Choose Cut: the direction follows the operation, into the material.
    await page.getByTestId("extrude-op-cut").click();
    await expect(page.getByTestId("extrude-dir-reverse")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // …and the editor SAYS so, before anything is committed.
    await expect(page.getByTestId("extrude-direction-hint")).toContainText(
      "Cuts into the part",
    );
    // The live ghost sweeps the resolved direction, so the pocket is visible in
    // the viewport before Save (design mandate: flow — see the next step from
    // the current state).
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-direction",
      "reverse",
    );

    await page.getByTestId("extrude-distance").fill("5");
    await page.getByTestId("extrude-distance").press("Enter");

    // THE PROOF: 8 000 − 10 × 10 × 5 = 7 500 mm³. On the old hardcoded
    // "normal" default this same cut evaluates to `cut_removed_nothing` and the
    // volume never moves off 8 000.
    await expect
      .poll(() => bodyVolume(page), { timeout: 30_000 })
      .toBe(CUBE_VOLUME_MM3 - POCKET_VOLUME_MM3);
    // The typed guard is untouched and stayed quiet — it fires on a genuinely
    // empty cut, not on every cut we authored badly.
    await expect(page.getByTestId("extrude-error")).toHaveCount(0);
  });

  test("a datum-plane profile keeps its direction — no material side", async ({
    page,
  }) => {
    const part = await seedCubeWithProfiles(page);
    await openPart(page, part);
    await openExtrudeOn(page, "Base pocket profile");

    // A free-standing plane cannot say which way the material is, so the
    // default stays put rather than guessing (and the caption names the axis
    // instead of claiming a side).
    await page.getByTestId("extrude-op-cut").click();
    await expect(page.getByTestId("extrude-dir-normal")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("extrude-direction-hint")).toHaveText(
      "Along the plane normal.",
    );
  });

  test("a direction the user picked survives an operation switch", async ({
    page,
  }) => {
    const part = await seedCubeWithProfiles(page);
    await openPart(page, part);
    await openExtrudeOn(page, "Face pocket profile");

    // The user reaches for Reverse first (an add into the part), then switches
    // to Cut: their choice stands, and the caption tracks it.
    await page.getByTestId("extrude-dir-reverse").click();
    await page.getByTestId("extrude-op-cut").click();
    await expect(page.getByTestId("extrude-dir-reverse")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // The other way round is the one that used to bite: overriding back to
    // Normal on a cut is honoured, and the editor warns rather than silently
    // producing an empty cut.
    await page.getByTestId("extrude-dir-normal").click();
    await expect(page.getByTestId("extrude-direction-hint")).toContainText(
      "nothing to remove",
    );
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-direction",
      "normal",
    );
  });

  /**
   * Founder shots, same part and camera, one click apart. `before` is what the
   * old hardcoded default produced — a cut sweeping OUT of the face, which
   * committed to `cut_removed_nothing` — reached now by overriding the
   * direction back to Normal (so the new caption is visible in it; the ghost is
   * the subject). `after` is what Cut now resolves to on its own.
   */
  test("founder shots: which way the cut goes (1600)", async ({ page }) => {
    const part = await seedCubeWithProfiles(page);
    await openPart(page, part);
    await openExtrudeOn(page, "Face pocket profile");
    await page.getByTestId("extrude-op-cut").click();
    await expect(page.getByTestId("extrude-dir-reverse")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.waitForTimeout(400); // let the debounced ghost settle
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-cut-direction-after-desktop.png`,
    });

    await page.getByTestId("extrude-dir-normal").click();
    await expect(page.getByTestId("extrude-preview-active")).toHaveAttribute(
      "data-direction",
      "normal",
    );
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-cut-direction-before-desktop.png`,
    });

    // Small-laptop width: the caption is one more line in a panel that already
    // has to fit there, so it is checked at 1280 as well as at 1600.
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.getByTestId("extrude-dir-reverse").click();
    await expect(page.getByTestId("extrude-direction-hint")).toContainText(
      "Cuts into the part",
    );
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/extrude-cut-direction-after-1280.png`,
    });
  });
});
