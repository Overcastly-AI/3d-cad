import { expect, test, type Page } from "./fixtures";

import {
  angleBetween,
  installSceneProbe,
  waitForCameraRest,
} from "./invariants";
import { createFeature, rectangleSketch, seedCube } from "./partSeed";
import {
  clickForReal,
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * UI-W2 — the PART half: Origin / Sketches / Bodies view control (founder:
 * *"what about the ability to enable planes, sketches and bodies? Similar to
 * fusion?"*; design `docs/design/ui-wave-tool-grade.md` Surface 2).
 *
 * The mandate's rule for this wave is 3c: a control that does not move a pixel
 * in the WebGL scene is a defect, not a stub. So the load-bearing assertions
 * here are PIXEL assertions taken off the real canvas of the real stack — the
 * same discipline the assembly half shipped with — and the DOM/aria state is
 * only ever the companion.
 *
 * Two probes, because the three categories draw in three different inks:
 *
 *  · a luminance-banded census for BODIES. BRIGHT (>110) is lit machined
 *    aluminum under the studio matcap; MID (45…110) is where a GHOSTED body
 *    lands (0.42 × body tone composited over the dark bench). Hiding drops
 *    BRIGHT without raising MID; ghosting drops BRIGHT and DOES raise MID.
 *  · an exact-ink census for ORIGIN. Datum sheets and axes draw their borders
 *    in the `sketch.planeEdge` token (`#5A6A7E`) through un-tonemapped line
 *    materials, so the token lands on the canvas at its exact hex — the same
 *    trick `countSketchInkPixels` uses for scribe ink.
 */

interface Bands {
  bright: number;
  mid: number;
}

/** Luminance-banded pixel census of the live WebGL canvas. */
async function canvasBands(page: Page): Promise<Bands> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return { bright: 0, mid: 0 };
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return { bright: 0, mid: 0 };
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let bright = 0;
    let mid = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      if (lum > 110) bright += 1;
      else if (lum > 45) mid += 1;
    }
    return { bright, mid };
  });
}

/**
 * Pixels at FULL-STRENGTH specular — the brightest ink a lit matcap face
 * produces (luminance > 210). The GHOST discriminator that survives the
 * sketcher's head-on camera, where {@link canvasBands} does not.
 *
 * Why a second instrument. The BRIGHT/MID bands separate ghost from solid at
 * the iso camera, where the matcap sweeps a wide luminance range across a
 * body seen at an angle. Parked normal to the sketch plane the body is one
 * flat face lit head-on, so ghost and solid BOTH sit in BRIGHT and the bands
 * barely move — measured on this exact frame, BRIGHT 26935 ghosted vs 27299
 * solid, a 1.3 % difference that no honest bound can be drawn through.
 *
 * The peak is categorical instead of marginal, and it follows from what a
 * ghost IS rather than from this frame: at `viewport.preview.surfaceOpacity`
 * (0.42) composited over the dark bench, a ghosted face CANNOT reach the
 * specular the same face reaches opaque. Measured, same frame, twice each:
 * ghosted 0 / 0, solid 525.
 */
async function peakLitPixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      const lum =
        0.2126 * (data[i] ?? 0) +
        0.7152 * (data[i + 1] ?? 0) +
        0.0722 * (data[i + 2] ?? 0);
      if (lum > 210) count += 1;
    }
    return count;
  });
}

/** Pixels drawn in the datum-edge token `sketch.planeEdge` (#5A6A7E). */
async function datumEdgePixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] ?? 0;
      const g = data[i + 1] ?? 0;
      const b = data[i + 2] ?? 0;
      if (
        Math.abs(r - 0x5a) <= 6 &&
        Math.abs(g - 0x6a) <= 6 &&
        Math.abs(b - 0x7e) <= 6
      ) {
        count += 1;
      }
    }
    return count;
  });
}

/**
 * Pixels drawn in the solved-sketch ink token `sketch.scribeSolved` (#C4D2DE).
 *
 * The shared `countSketchInkPixels` helper is deliberately NOT used here: its
 * filter ("bright and blue-leaning") also matches machined aluminum under the
 * studio matcap, which is fine on a body-less sketching frame and useless here,
 * where the whole question is whether ink appeared ON TOP of a solid. Solved
 * ink renders un-tonemapped through a line material, so it lands on its exact
 * token hex and a tight match separates it from the shaded body.
 */
async function scribeInkPixels(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (!canvas) return 0;
    const probe = document.createElement("canvas");
    probe.width = canvas.width;
    probe.height = canvas.height;
    const ctx = probe.getContext("2d");
    if (!ctx) return 0;
    ctx.drawImage(canvas, 0, 0);
    const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
    let count = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (
        Math.abs((data[i] ?? 0) - 0xc4) <= 4 &&
        Math.abs((data[i + 1] ?? 0) - 0xd2) <= 4 &&
        Math.abs((data[i + 2] ?? 0) - 0xde) <= 4
      ) {
        count += 1;
      }
    }
    return count;
  });
}

/**
 * Settle the on-demand render loop before sampling the drawing buffer: wait
 * for real PAINTS (`waitForFrames`), not for 450 ms of wall clock, which under
 * load can pass with nothing drawn — the sample would then be the pre-change
 * frame and the numeric assertions below have no auto-retry to save them
 * (docs/BACKLOG.md GATE-1a). Every call here follows a locator assertion that
 * the state change has already committed, so what remains to wait for is the
 * frame, which is exactly what this waits for.
 */
async function settled<T>(page: Page, probe: () => Promise<T>): Promise<T> {
  await waitForFrames(page);
  return probe();
}

/**
 * The settled view direction after the neighbour case's one orbit, measured on
 * this build. Pinned so a drifting camera fails the test rather than quietly
 * producing a before/after pair shot from two different viewpoints.
 */
const ORBITED_VIEW_DIR: [number, number, number] = [0.4093, -0.8521, -0.3262];

/** Press, travel in steps, release — the gesture a hand actually makes. */
async function drag(
  page: Page,
  button: "left" | "middle" | "right",
  from: { x: number; y: number },
  dx: number,
  dy: number,
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down({ button });
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 6 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 6 });
  await page.mouse.up({ button });
}

/** Seed a 20 mm cube part, open it and wait for the solid to render. */
async function openCubePart(page: Page): Promise<string> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Bracket");
  await seedCube(page, token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("viewport")).toHaveAttribute(
    "data-total-faces",
    /[1-9]/,
    { timeout: 30_000 },
  );
  return part.id;
}

test.describe("UI-W2 part half — the browser controls what is drawn", () => {
  test("origin planes and axes render on demand and nothing else moves", async ({
    page,
  }) => {
    await openCubePart(page);

    // Fusion's default, and ours: origin geometry starts OFF, so a part that
    // needs no datum work is not permanently cluttered.
    const xy = page.getByTestId("origin-plane-XY");
    await expect(xy).toHaveAttribute("aria-pressed", "false");
    const before = await settled(page, () => datumEdgePixels(page));
    const bodyBefore = await canvasBands(page);

    await xy.click();
    await expect(xy).toHaveAttribute("aria-pressed", "true");
    const withPlane = await settled(page, () => datumEdgePixels(page));
    // The sheet's scribed border is hundreds of pixels of exact token ink.
    expect(withPlane).toBeGreaterThan(before + 150);

    // The axes are independent rows, and each adds its own ink.
    await page.getByTestId("origin-axis-X").click();
    await page.getByTestId("origin-axis-Y").click();
    const withAxes = await settled(page, () => datumEdgePixels(page));
    expect(withAxes).toBeGreaterThan(withPlane);
    await expect(page.getByTestId("origin-axis-label-X")).toBeVisible();

    // Datum geometry is not a solid: the body census is untouched by it.
    const bodyAfter = await canvasBands(page);
    expect(Math.abs(bodyAfter.bright - bodyBefore.bright)).toBeLessThan(
      bodyBefore.bright * 0.1,
    );

    // And switching it back off leaves no residue.
    await xy.click();
    await page.getByTestId("origin-axis-X").click();
    await page.getByTestId("origin-axis-Y").click();
    const off = await settled(page, () => datumEdgePixels(page));
    expect(off).toBeLessThan(before + 60);
  });

  test("a sketch can be brought back with the body on screen", async ({
    page,
  }) => {
    await openCubePart(page);

    // The default, unchanged: the body is the hero and the profile that made it
    // recedes. What is NEW is that this is now a stop the modeler can answer.
    const row = page.getByTestId(/^sketch-visibility-/).first();
    await expect(row).toHaveAttribute("aria-pressed", "false");
    const inkBefore = await settled(page, () => scribeInkPixels(page));

    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    const inkOverSolid = await settled(page, () => scribeInkPixels(page));

    // The profile sits ON the body's base face, so the solid it made covers it
    // COMPLETELY. This used to expect "a silhouette peek" of >50 px, and the
    // peek was the defect: the origin-datum plane bases were stated in the
    // kernel's Z-up frame while the scene renders Y-up, so the ink stood
    // vertically THROUGH the body instead of lying on its base face, and the
    // part sticking out was what got counted (FB-7c, 2026-08-06).
    //
    // So the row's effect is proven where the ink can actually be seen — with
    // the body out of the way. Without this the "occluded" reading would pass
    // just as happily on a control that does nothing.
    await page.getByTestId("body-visibility-0").click();
    const inkUncovered = await settled(page, () => scribeInkPixels(page));
    expect(inkUncovered).toBeGreaterThan(inkOverSolid + 50);

    // …and it is THIS row that draws it: off again, with the body still hidden.
    await row.click();
    const inkOff = await settled(page, () => scribeInkPixels(page));
    expect(inkOff).toBeLessThan(inkUncovered / 2);
    expect(inkBefore).toBeLessThan(inkUncovered / 2);
  });

  test("hide and ghost a body change what the viewport draws", async ({
    page,
  }) => {
    await openCubePart(page);
    const viewport = page.getByTestId("viewport");
    const solid = await settled(page, () => canvasBands(page));
    expect(solid.bright).toBeGreaterThan(0);

    // --- HIDE (the eye) ------------------------------------------------
    // Driving the EYE (not the row's name) is the point: touching the eye
    // addresses the row and discloses its stops WITHOUT opening the base
    // feature's editor.
    const eye = page.getByTestId("body-visibility-0");
    await eye.click();
    await expect(eye).toHaveAttribute("aria-pressed", "false");
    const hidden = await settled(page, () => canvasBands(page));
    // Nothing drawn: no lit surface AND no translucent one either — the mesh,
    // its B-rep edge overlay and its pick target all go.
    expect(hidden.bright).toBeLessThan(solid.bright * 0.02);
    await expect(viewport).toHaveAttribute("data-drawn-faces", "0");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");

    // The way back is on screen, derived, and works.
    const stamp = page.getByTestId("visibility-stamp");
    await expect(stamp).toBeVisible();
    await expect(stamp).toHaveAttribute("data-hidden-count", "1");

    // --- GHOST ---------------------------------------------------------
    await page.getByTestId("body-opacity-ghost").click();
    const ghosted = await settled(page, () => canvasBands(page));
    // Translucent, not dim: lit pixels drop OUT of the BRIGHT band and land in
    // MID, which is what tells ghost apart from hide (hide drops both). The
    // same bands and bounds the assembly half asserts on.
    expect(ghosted.bright).toBeLessThan(solid.bright * 0.8);
    expect(ghosted.mid).toBeGreaterThan(solid.mid * 1.1);
    expect(ghosted.mid).toBeGreaterThan(hidden.mid);
    await expect(viewport).toHaveAttribute("data-ghost-faces", /[1-9]/);

    await page.getByTestId("body-opacity-solid").click();
    const restored = await settled(page, () => canvasBands(page));
    expect(restored.bright).toBeGreaterThan(solid.bright * 0.8);
    await expect(stamp).toHaveCount(0);
  });

  /**
   * GHOST-1 — the solid gets out of the way while you sketch.
   *
   * A flow defect, not a missing capability: the GHOST stop has existed since
   * UI-W2 and the sketcher simply never used it, so opening a sketch on a part
   * that already has a body left the modeler drawing white ink onto a lit
   * aluminum face. Fusion and Onshape both ghost on entry.
   *
   * It ships as a DERIVED DEFAULT rather than an entry/exit override, and most
   * of what these two cases assert is that distinction: nothing is written on
   * the way in, so nothing has to be restored on the way out, and a stop the
   * modeler set themselves is never touched in either direction.
   *
   * MEASUREMENT NOTE, because it invalidated the obvious assertion. A canvas
   * luminance census CANNOT be compared across sketch entry or exit: the
   * sketcher parks the camera normal to the plane and exiting leaves it there.
   * Measured — TOP view after exit, BRIGHT 310289 -> 24675, with
   * `data-drawn-faces` 6 and `data-ghost-faces` 0 at BOTH ends and unchanged
   * after a further 2 s, i.e. the body is drawn solid the whole time and only
   * the framing moved. So the pixel witness has to be an A/B taken at ONE
   * camera, inside the sketch, and the entry/exit claims rest on the state
   * attributes plus a face-count floor that an empty scene cannot satisfy.
   */
  test("a body ghosts itself while a sketch is open, and un-ghosts on exit", async ({
    page,
  }) => {
    await openCubePart(page);
    const viewport = page.getByTestId("viewport");
    const bodyRow = page.getByTestId("body-row");

    // ADDRESS the row without touching its stop, so the opacity control is
    // disclosed later when the pixel A/B needs it. Right-click addresses and
    // opens the menu; Escape closes the menu and leaves the row addressed. The
    // eye would address it too, and would also hide the body, which is exactly
    // the explicit stop this case must not have.
    await bodyRow.click({ button: "right" });
    await expect(page.getByTestId("body-context-menu")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("body-opacity-0")).toBeVisible();

    // --- BEFORE: solid, and the row says so ----------------------------
    await expect(viewport).toHaveAttribute("data-drawn-faces", "6");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");
    await expect(bodyRow).toHaveAttribute("data-visibility", "solid");

    // --- ENTER the sketch, the way a modeler does ----------------------
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await clickForReal(page, "tree-ctx-edit");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();

    // EVERY face is ghosted, not just the one being sketched on: occlusion is
    // a property of the camera and the plane, not of which face was picked.
    // `data-drawn-faces` counts SOLID faces only, so 0 means "all six went
    // see-through", and the ghost count says the same thing from the far side.
    await expect(viewport).toHaveAttribute("data-ghost-faces", "6");
    await expect(viewport).toHaveAttribute("data-drawn-faces", "0");
    // The row agrees with the pixels. It has to: a row reading SOLID over a
    // see-through solid is the eye disagreeing with the scene.
    await expect(bodyRow).toHaveAttribute("data-visibility", "ghost");

    await page.mouse.move(1400, 900); // park the cursor off the model
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/ghost1-sketch-open-after.png`,
    });

    // --- EXIT: back to solid, with nothing to restore ------------------
    // Nothing was written on entry, so this is a derived default lapsing, not
    // a saved value being put back — there is no restore step that can go
    // wrong. The face-count floor is what keeps the claim honest:
    // `data-ghost-faces` of "0" is also true of a scene with no body in it.
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(viewport).toHaveAttribute("data-drawn-faces", "6");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");
    await expect(bodyRow).toHaveAttribute("data-visibility", "solid");

    // --- AND IT IS A LIVE DERIVATION, not a one-shot on first entry ----
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await clickForReal(page, "tree-ctx-edit");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();
    await expect(viewport).toHaveAttribute("data-ghost-faces", "6");

    // THE PIXEL WITNESS, at one fixed camera. An attribute alone would pass on
    // a control that moves no pixel (mandate 3c), and `data-ghost-faces` is
    // derived from the same state the material split reads, so it cannot be
    // the only witness. Overriding to SOLID here changes exactly one thing —
    // the ghost — with camera, framing and sketch ink all held, which is the
    // only way to compare pixels at all inside the sketcher (see the note
    // above). The instrument is the specular peak, not the BRIGHT band: see
    // `peakLitPixels` for why the bands cannot see this frame.
    const ghosted = await settled(page, () => peakLitPixels(page));
    await clickForReal(page, "body-opacity-solid");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");
    const opaque = await settled(page, () => peakLitPixels(page));
    // Translucent, and provably so: the opaque face reaches full specular and
    // the ghosted one cannot. Measured 525 vs 0; the bounds carry real slack
    // in both directions so this asserts the physics, not the frame.
    expect(opaque).toBeGreaterThan(150);
    expect(ghosted).toBeLessThan(opaque / 4);
  });

  test("a body the modeler set SOLID is not ghosted by opening a sketch", async ({
    page,
  }) => {
    await openCubePart(page);
    const viewport = page.getByTestId("viewport");
    const bodyRow = page.getByTestId("body-row");

    // Address the row (the eye, which does not open the base feature's editor)
    // and state SOLID deliberately. This is the case the ticket warned about:
    // a stop the modeler chose must not be silently overridden on the way in
    // and silently restored on the way out.
    await clickForReal(page, "body-visibility-0");
    await clickForReal(page, "body-opacity-solid");
    await expect(bodyRow).toHaveAttribute("data-visibility", "solid");

    await page.getByTestId("feature-row").first().click({ button: "right" });
    await clickForReal(page, "tree-ctx-edit");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();

    // Still solid — and non-vacuously so: all six faces are still being drawn
    // at full opacity, which a scene with nothing in it could not claim.
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");
    await expect(viewport).toHaveAttribute("data-drawn-faces", "6");
    await expect(bodyRow).toHaveAttribute("data-visibility", "solid");

    // And the manual control still works INSIDE the sketch — the derived
    // default is a default, not a lock. Setting GHOST here is the modeler's
    // word, so it also survives the sketch closing rather than being quietly
    // reverted, which is the other half of "never silently restored".
    await clickForReal(page, "body-opacity-ghost");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "6");
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(viewport).toHaveAttribute("data-ghost-faces", "6");
    await expect(bodyRow).toHaveAttribute("data-visibility", "ghost");
  });

  /**
   * GHOST-1, the case the DECISION was actually made for: a NEIGHBOUR body is
   * what stands between the eye and the sketch.
   *
   * The two cases above use a single cube, where the only solid in the way is
   * the sketch's own. That is the least interesting configuration, and it
   * cannot distinguish "ghost the host" from "ghost everything" — which is the
   * choice `bodyView` documents. Here the host body is extruded the OTHER way
   * (`direction: "reverse"`), so it sits BEHIND the sketch plane and occludes
   * nothing, while a second, separate body (`merge: false`) stands in front of
   * it across the right of the profile. A build that ghosted only the sketch's
   * own body would leave this frame exactly as broken as the bug report, and
   * would still pass both cases above.
   *
   * It is also the founder frame: the profile's horizontal edges run under the
   * neighbour, so BEFORE they stop dead at it and AFTER they carry straight
   * through — a difference that needs no caption.
   */
  test("a NEIGHBOUR body ghosts too, not just the sketch's own", async ({
    page,
  }) => {
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Bracket");
    // Host: a 70 x 46 profile on XY, extruded DOWNWARD so that from the
    // sketch's own side of the sheet it covers nothing.
    //
    // Both numbers are sized to the sketch camera rather than chosen for
    // realism, and both were measured. CENTRED on the origin: the camera parks
    // there, so a profile anchored at the origin sits entirely in one quadrant
    // and runs off the frame (the first capture did). 70 mm rather than the
    // 170 mm first tried: the sheet's 1 mm grid moires badly once ~170 cells
    // span the frame, and the plate overflowed it — 70 keeps the grid legible
    // while still filling far more of the frame than the 20 mm cube above.
    const sketch = await createFeature(page, token, part.id, {
      name: "Sketch1",
      feature: {
        type: "sketch",
        version: 1,
        params: rectangleSketch(-35, -23, 70, 46),
      },
      expected_tree_version: 0,
    });
    const host = await createFeature(page, token, part.id, {
      name: "Extrude1",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: sketch.feature.id },
          distance_mm: 8,
          operation: "add",
          direction: "reverse",
        },
      },
      expected_tree_version: sketch.tree_version,
    });
    // Neighbour: a bar across the right of the profile, standing UP off the
    // sheet and overhanging it in y, so it crosses both horizontal edges — the
    // continuity of those edges through it is what the founder pair shows.
    const bar = await createFeature(page, token, part.id, {
      name: "Sketch2",
      feature: {
        type: "sketch",
        version: 1,
        params: rectangleSketch(8, -30, 22, 60),
      },
      expected_tree_version: host.tree_version,
    });
    await createFeature(page, token, part.id, {
      name: "Extrude2",
      feature: {
        type: "extrude",
        version: 1,
        params: {
          profile: { kind: "feature", feature_id: bar.feature.id },
          distance_mm: 26,
          operation: "add",
          direction: "normal",
          merge: false,
        },
      },
      expected_tree_version: bar.tree_version,
    });

    // BEFORE the goto: `addInitScript` only applies to loads that follow it.
    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 60_000,
    });
    const viewport = page.getByTestId("viewport");
    // Two boxes, six faces each — and the count is asserted because every
    // claim below is "all twelve", which is vacuous if the part never built.
    await expect(viewport).toHaveAttribute("data-total-faces", "12", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-row")).toHaveCount(2);

    // Address the NEIGHBOUR's row (Body 2) so its opacity stops are disclosed
    // in the frame: with two bodies the panel is the only place a reader can
    // see that BOTH went see-through, and one visible control says it.
    await page.getByTestId("body-row").nth(1).click({ button: "right" });
    await expect(page.getByTestId("body-context-menu")).toBeVisible();
    await page.keyboard.press("Escape");

    await expect(viewport).toHaveAttribute("data-drawn-faces", "12");
    await expect(viewport).toHaveAttribute("data-ghost-faces", "0");
    for (const index of [0, 1]) {
      await expect(page.getByTestId("body-row").nth(index)).toHaveAttribute(
        "data-visibility",
        "solid",
      );
    }

    // Open the HOST's sketch. The neighbour is not this sketch's body and has
    // no stop of its own — it ghosts because it is in the way, which is the
    // whole argument for the scope `bodyView` chose.
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await clickForReal(page, "tree-ctx-edit");
    await expect(page.getByTestId("sketch-strip")).toBeVisible();

    // ORBIT OFF THE SKETCH NORMAL (VP-1's middle-drag). The sketcher parks the
    // camera square-on to the plane, where two boxes and a rectangle all read
    // as flat overlapping quads — true, and useless as evidence. One orbit puts
    // the solids in three-quarter view while the sketch stays legible, which is
    // the frame a modeler actually works in.
    //
    // Let the sketcher finish easing into its normal-on pose FIRST. Dragging
    // into a live ease loses the orbit: measured, the settled direction came
    // back 0.02 deg from straight down — the ease simply re-parked the camera
    // afterwards, and a zero turn reads exactly like an unbound button.
    await expect(page.getByTestId("sketch-dro")).toBeVisible();
    await waitForCameraRest(page);
    // Both axes matter: parked normal-on, a purely horizontal drag is a small
    // roll about the view axis and looks like nothing happened. The magnitude
    // is a THIRD of `sketch-orbit.spec.ts`'s (150, -110) on purpose — that one
    // turns 72 deg, which puts the camera nearly edge-on to the sheet and was
    // unreadable; measured here, (62, -46) settles at 31.56 deg.
    await drag(page, "middle", { x: 800, y: 500 }, 62, -46);
    // A coarser rest tolerance than the default 0.05 deg, and deliberately: the
    // orbit's damping coast decays per RENDERED FRAME, so on a demand-render
    // canvas it approaches zero without reaching 0.05 deg inside any sane
    // budget — measured, `waitForCameraRest` timed out at 15 s still reporting
    // motion. 0.3 deg is far below the 2 deg the pin allows, so the frames stay
    // a matched pair either way.
    const pose = await waitForCameraRest(page, {
      epsilonDeg: 0.3,
      timeoutMs: 40_000,
    });
    // PIN the viewpoint. The founder frames below are a matched pair captured in
    // two separate runs (the "before" needs the auto-ghost mutated out), so they
    // are only comparable if the camera lands in the same place both times —
    // and an orbit coasts under damping, which is exactly the kind of thing that
    // drifts silently. Asserting the settled direction makes a drifted pair a
    // test failure instead of a misleading screenshot.
    expect(
      angleBetween(pose.direction, ORBITED_VIEW_DIR),
      `the orbited viewpoint drifted (settled at ${pose.direction
        .map((v) => v.toFixed(3))
        .join(
          ", ",
        )}) — the before/after founder frames would no longer share a camera`,
    ).toBeLessThan(2);

    // Captured BEFORE the ghost assertions, so that a run with the auto-ghost
    // mutated out still writes its frame — that run is how the "before" half of
    // the founder pair is produced, and it is a FAILING run by construction.
    await page.mouse.move(1400, 900); // park the cursor off the model
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/ghost1-neighbour-after.png`,
    });

    await expect(viewport).toHaveAttribute("data-ghost-faces", "12");
    await expect(viewport).toHaveAttribute("data-drawn-faces", "0");
    for (const index of [0, 1]) {
      await expect(page.getByTestId("body-row").nth(index)).toHaveAttribute(
        "data-visibility",
        "ghost",
      );
    }
  });

  test("V and shift+V drive the addressed row from the keyboard", async ({
    page,
  }) => {
    await openCubePart(page);
    const solid = await settled(page, () => canvasBands(page));

    // Address the body by its eye (which also hides it), then drive the rest
    // from the keyboard — no pointer, no editor opened.
    await page.getByTestId("body-visibility-0").click();
    const hidden = await settled(page, () => canvasBands(page));
    expect(hidden.bright).toBeLessThan(solid.bright * 0.02);

    // Shift+V is the way BACK whenever anything is hidden, so the one
    // accelerator can never strand a modeler in an empty scene.
    await page.keyboard.press("Shift+V");
    const restored = await settled(page, () => canvasBands(page));
    expect(restored.bright).toBeGreaterThan(solid.bright * 0.8);

    // …and plain V hides the same addressed row again.
    await page.keyboard.press("v");
    const again = await settled(page, () => canvasBands(page));
    expect(again.bright).toBeLessThan(solid.bright * 0.02);
  });

  test("view state changes nothing the document knows", async ({ page }) => {
    await openCubePart(page);
    const volume = await page.getByTestId("prop-volume").textContent();

    await page.getByTestId("body-visibility-0").click();
    await page.getByTestId("origin-plane-XZ").click();

    // The solve, the tree and the export gate are untouched: this is VIEW
    // state, client-only, unversioned.
    await expect(page.getByTestId("eval-status")).toHaveText("Solved");
    await expect(page.getByTestId("feature-row")).toHaveCount(2);
    await expect(page.getByTestId("part-export-step")).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(await page.getByTestId("prop-volume").textContent()).toBe(volume);
  });

  // Founder evidence at both widths the quality floor names. The 1440 frames
  // are captured inside the functional tests above (a screenshot of a state no
  // assertion reached is a screenshot of nothing); these are the small-laptop
  // twins, where a browser that grew two sections has the least room to spare.
  for (const width of [1440, 1366]) {
    test(`founder shots — the part browser at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openCubePart(page);

      // XZ + YZ read against a solid far better than XY, which lies in the
      // base face of anything sitting on the bench.
      await page.getByTestId("origin-plane-XZ").click();
      await page.getByTestId("origin-plane-YZ").click();
      await page.getByTestId("origin-axis-Z").click();
      await page
        .getByTestId(/^sketch-visibility-/)
        .first()
        .click();
      await page.waitForTimeout(600);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-part-origin-after-${width}.png`,
      });

      await page.getByTestId("body-visibility-0").click();
      await page.waitForTimeout(600);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-part-hidden-after-${width}.png`,
      });

      await page.getByTestId("body-opacity-ghost").click();
      await page.waitForTimeout(600);
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/uiw2-part-ghost-after-${width}.png`,
      });
    });
  }
});
