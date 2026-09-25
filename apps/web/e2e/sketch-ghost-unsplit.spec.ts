import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, waitForCameraStill } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import {
  clickForReal,
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * GHOST-1's REMAINING HOLE — a part whose mesh cannot be split per body stayed
 * OPAQUE over the sketch you were editing (product audit: "the solid body is
 * drawn opaque on top of the sketch").
 *
 * Ghosting for an open sketch is decided per BODY (`partView.bodyView`), and the
 * per-body face sets are recovered from the ONE fused mesh the evaluate ships
 * (`bodyPartition.bodyFaceSets`). When that arithmetic does not line up, the
 * split is withheld — correctly: an eye that hides the wrong solid is worse
 * than none — and `ModelMesh` used to return BEFORE ghosting anything, so the
 * whole part stayed solid while you drew on it.
 *
 * THE REPRODUCTION, and why it is a real part and not a contrivance: two
 * bodies that TOUCH. Body 1 is a 40 x 30 plate extruded up; Body 2 is a
 * separate body (`merge: false`) extruded DOWN from the same profile, so the two
 * meet face to face at z = 0 — the shape of a mould's two halves, or a boss
 * modelled as its own body on a plate. The mesh is welded by coordinate, so the
 * shared corners join both solids into ONE connected component while the
 * evaluate reports two bodies of one lump each: 1 component, 2 declared, and
 * the split refuses. The precondition asserts the refusal through the product's
 * own tell — the Bodies eye is disabled with "This mesh cannot be split per
 * body" — so this case cannot pass on a fixture that splits.
 */

/**
 * THE PIXEL WITNESS — the fraction of a patch INSIDE the plate's top face that
 * is bright (luminance > 180). An opaque body under the studio matcap fills the
 * patch with it; a ghosted one lets the dark bench and the sketch grid through
 * and cannot reach it. Measured on this fixture at both widths: 1.0 before
 * the fix, 0.0 after, so the 0.2 bound has room either way.
 *
 * The patch is placed by projecting a point of the top face through the LIVE
 * scene camera (the scene probe; no product hook), away from the origin ring
 * and the constraint glyphs, so it samples the face and nothing else. The
 * data attributes say which faces the material split ghosted; this says what
 * reached the screen, which is the claim the audit made.
 */
async function brightFraction(page: Page): Promise<number> {
  return page.evaluate(() => {
    interface Vec {
      constructor: new (x: number, y: number, z: number) => Vec;
      project: (camera: unknown) => Vec;
      x: number;
      y: number;
    }
    interface Cam {
      isPerspectiveCamera?: boolean;
      fov?: number;
      position: Vec;
      updateMatrixWorld: () => void;
    }
    const w = window as unknown as Record<string, unknown>;
    const camera = Object.values(
      (w["__loftCameras"] ?? {}) as Record<string, Cam>,
    ).find((c) => c.isPerspectiveCamera === true && c.fov === 40);
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (camera === undefined || canvas === null) return Number.NaN;
    camera.updateMatrixWorld();
    // Kernel (-12, -8, 12) on the plate's top face -> scene (x, z, -y).
    const V = camera.position.constructor;
    const ndc = new V(-12, 12, 8).project(camera);
    // Device pixels: the drawing buffer can be larger than the CSS box.
    const cx = Math.round(((ndc.x + 1) / 2) * canvas.width);
    const cy = Math.round(((1 - ndc.y) / 2) * canvas.height);
    const half = Math.round(10 * (canvas.width / canvas.clientWidth));
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return Number.NaN;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(cx - half, cy - half, 2 * half, 2 * half);
    let bright = 0;
    for (let i = 0; i < data.length; i += 4) {
      // The canvas is TRANSPARENT (the bench gradient is CSS behind it), and a
      // ghost is drawn at low alpha, so its colour alone can read bright while
      // almost none of it reaches the eye. Weight by alpha: composited over a
      // dark bench, what is seen is at most colour x alpha.
      const lum =
        (0.2126 * (data[i] ?? 0) +
          0.7152 * (data[i + 1] ?? 0) +
          0.0722 * (data[i + 2] ?? 0)) *
        ((data[i + 3] ?? 0) / 255);
      if (lum > 180) bright += 1;
    }
    return bright / (data.length / 4);
  });
}

async function seedTouchingBodies(page: Page): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Mould halves");
  const sketch = await createFeature(page, token, part.id, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(-20, -15, 40, 30),
    },
    expected_tree_version: 0,
  });
  const upper = await createFeature(page, token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 12,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await createFeature(page, token, part.id, {
    name: "Extrude2",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 8,
        operation: "add",
        direction: "reverse",
        merge: false,
      },
    },
    expected_tree_version: upper.tree_version,
  });
  return part.id;
}

const SIZES = [
  { label: "1280", width: 1280, height: 800 },
  { label: "1440", width: 1440, height: 900 },
] as const;

for (const size of SIZES) {
  test(`a part whose mesh cannot be split per body still ghosts while a sketch is open (${size.width}x${size.height})`, async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: size.width, height: size.height });
    await installSceneProbe(page);
    const partId = await seedTouchingBodies(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    const viewport = page.getByTestId("viewport");
    // Two boxes, six faces each: every claim below is "all twelve", which is
    // vacuous if the part never built.
    await expect(viewport).toHaveAttribute("data-total-faces", "12", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-row")).toHaveCount(2);

    // PRECONDITION: the split really is unavailable — the product withholds
    // the per-body eye and says why.
    const eye = page.getByTestId("body-visibility-0");
    await expect(eye).toBeDisabled();
    await expect(eye).toHaveAttribute(
      "title",
      "This mesh cannot be split per body",
    );
    await expect(viewport).toHaveAttribute("data-drawn-faces", "12");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");

    // Open the plate's sketch, the way a modeler does.
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await clickForReal(page, "tree-ctx-edit");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    // The camera eases into the sketch park; the pixel census below needs it
    // to have LANDED, so the settle is named rather than inherited — and it is
    // a POSITION settle, because the park also changes the distance.
    await waitForCameraStill(page);
    await page.mouse.move(size.width - 60, size.height / 2);
    // Captured BEFORE the assertions, so a run against the pre-fix tree (a
    // failing run by construction) still writes its frame — that is how the
    // committed `sketch-ghost-unsplit-before-*` half of the pair was made.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-ghost-unsplit-after-${size.label}.png`,
    });
    // FIRST, what reached the SCREEN: the plate's top face no longer paints
    // the opaque matcap band over the sketch. Asserted before the attributes
    // so this witness is the one that reddens on its own.
    expect(
      await brightFraction(page),
      "the patch inside the plate's top face is still opaque-bright",
    ).toBeLessThan(0.2);
    // The whole mesh went see-through: every face ghosted, none drawn solid.
    await expect(viewport).toHaveAttribute("data-ghost-faces", "12");
    await expect(viewport).toHaveAttribute("data-drawn-faces", "0");
    // The rows agree with the pixels — both bodies read GHOST.
    for (const index of [0, 1]) {
      await expect(page.getByTestId("body-row").nth(index)).toHaveAttribute(
        "data-visibility",
        "ghost",
      );
    }

    // Leaving the sketch lapses the default: solid again, all twelve drawn.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(viewport).toHaveAttribute("data-drawn-faces", "12");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");
  });
}
