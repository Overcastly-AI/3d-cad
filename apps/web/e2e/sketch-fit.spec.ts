import { expect, test, type Page } from "./fixtures";

import { handClick } from "./hand";
import {
  installSceneProbe,
  waitForCameraStill,
  type CameraPose,
} from "./invariants";
import { createFeature, seedCube } from "./partSeed";
import { calibratePlane, enterSketch, type PlaneMapper } from "./planeMap";
import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * F-11 — THE SKETCHER HAD NO FIT (product audit 2026-09-16).
 *
 * The audit's measurement: re-entering a sketch to edit it, 4 of its 11 glyphs
 * were outside the frame — the 80 mm dimension at x = 1856 on a 1600 px frame —
 * and there was nothing on screen, and no key, to get the view back. The part
 * workspace's view rail (and its `0` = Fit) was unmounted with the rest of the
 * view navigation the moment the sketcher took the camera.
 *
 * The fixture reproduces that shape deterministically: an 80 x 40 rectangle
 * seated 60 mm off the origin on XY. The sketcher parks its camera on the
 * PLANE's origin at a fixed standoff, so on re-open the rectangle's far end is
 * past the right edge of the frame. The precondition asserts exactly that, so
 * this spec cannot pass on a fixture that happens to fit already.
 *
 * WHAT "IN FRAME" IS MEASURED WITH. The four corners of the drawn profile are
 * projected through the LIVE scene camera (the scene probe hooks three.js at
 * construction — no product hook), in world coordinates derived from the
 * sketch's own numbers. That is the property; the constraint glyphs are the
 * audit's own instrument and are checked as a second, independent reading.
 */

/** The profile, in sketch-plane mm: an 80 x 40 plate from x = 60 to x = 140. */
const X0 = 60;
const X1 = 140;
const Y0 = 0;
const Y1 = 40;
const CORNERS: readonly [number, number][] = [
  [X0, Y0],
  [X1, Y0],
  [X1, Y1],
  [X0, Y1],
];

function offsetPlate() {
  const line = (id: string, a: [number, number], b: [number, number]) => ({
    id,
    kind: "line",
    start: { x: a[0], y: a[1] },
    end: { x: b[0], y: b[1] },
  });
  const joint = (a: string, b: string) => ({
    kind: "coincident",
    a: { entity: a, point: "end" },
    b: { entity: b, point: "start" },
  });
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [
      line("e1", [X0, Y0], [X1, Y0]),
      line("e2", [X1, Y0], [X1, Y1]),
      line("e3", [X1, Y1], [X0, Y1]),
      line("e4", [X0, Y1], [X0, Y0]),
    ],
    constraints: [
      joint("e1", "e2"),
      joint("e2", "e3"),
      joint("e3", "e4"),
      joint("e4", "e1"),
      { kind: "horizontal", entity: "e1" },
      { kind: "vertical", entity: "e2" },
      { kind: "horizontal", entity: "e3" },
      { kind: "vertical", entity: "e4" },
      { kind: "distance", entity: "e1", value_mm: X1 - X0 },
      { kind: "distance", entity: "e2", value_mm: Y1 - Y0 },
      { kind: "fixed", point: { entity: "e1", point: "start" } },
    ],
  };
}

interface Projected {
  x: number;
  y: number;
}

/**
 * Project sketch-plane points on origin XY through the live scene camera, to
 * page pixels. XY is the kernel's ground plane; the renderer is Y-up, so the
 * kernel point (x, y, 0) is the scene point (x, 0, -y) (`sketch/plane.ts`,
 * `occtToSceneBasis`).
 *
 * The camera is chosen as the one PERSPECTIVE camera with the viewport's 40°
 * field: during a sketch the projection rig holds the scene camera in
 * perspective, while the reference cube renders through an orthographic one.
 */
async function project(
  page: Page,
  points: readonly [number, number][],
): Promise<Projected[]> {
  return page.evaluate((pts) => {
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
    const cameras = Object.values(
      (w["__loftCameras"] ?? {}) as Record<string, Cam>,
    );
    const camera = cameras.find(
      (c) => c.isPerspectiveCamera === true && c.fov === 40,
    );
    if (camera === undefined) throw new Error("no scene camera captured");
    camera.updateMatrixWorld();
    const canvas = document.querySelector(
      '[data-testid="viewport"] canvas',
    ) as HTMLCanvasElement;
    const rect = canvas.getBoundingClientRect();
    const V = camera.position.constructor;
    return pts.map(([x, y]) => {
      const ndc = new V(x, 0, -y).project(camera);
      return {
        x: rect.left + ((ndc.x + 1) / 2) * rect.width,
        y: rect.top + ((1 - ndc.y) / 2) * rect.height,
      };
    });
  }, points);
}

async function canvasBox(page: Page) {
  const box = await page
    .locator('[data-testid="viewport"] canvas')
    .first() // the scene; the reference cube's own canvas follows it
    .boundingBox();
  expect(box, "the viewport canvas has a box").not.toBeNull();
  return box!;
}

function inside(
  p: Projected,
  r: { x: number; y: number; width: number; height: number },
): boolean {
  return (
    p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height
  );
}

/** The glyphs' centres — the audit's own instrument (drei `Html` anchors). */
async function glyphCentres(
  page: Page,
): Promise<(Projected & { id: string })[]> {
  return page.locator('[data-testid^="glyph-"]').evaluateAll((nodes) =>
    nodes.map((node) => {
      const r = node.getBoundingClientRect();
      return {
        id: node.getAttribute("data-testid") ?? "",
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
      };
    }),
  );
}

const SIZES = [
  { label: "1280", width: 1280, height: 800 },
  { label: "1440", width: 1440, height: 900 },
] as const;

for (const size of SIZES) {
  test(`F-11 — Fit frames the open sketch at ${size.width}x${size.height}, from the key and from the bar`, async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: size.width, height: size.height });
    await installSceneProbe(page);
    const { token } = await seedSession(page);
    const part = await createPartViaApi(page, token, "Sketch fit");
    await createFeature(page, token, part.id, {
      name: "Sketch1",
      feature: { type: "sketch", version: 1, params: offsetPlate() },
      expected_tree_version: 0,
    });

    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // Re-open the saved sketch — the audit's own path into the defect.
    await page.getByTestId("feature-row").first().click({ button: "right" });
    await page.getByTestId("tree-ctx-edit").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await expect(page.locator('[data-testid^="glyph-"]')).toHaveCount(11);
    await waitForCameraStill(page);

    // PRECONDITION: the fixture reproduces the defect — part of the profile
    // is outside the frame the sketcher opened at.
    const frame = await canvasBox(page);
    const before = await project(page, CORNERS);
    const outBefore = before.filter((p) => !inside(p, frame));
    expect(
      outBefore.length,
      `precondition: some corner must start off-frame (corners ${JSON.stringify(before)})`,
    ).toBeGreaterThan(0);
    await page.mouse.move(frame.x + 12, frame.y + frame.height / 2);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-fit-entry-${size.label}.png`,
    });

    // The control is ON SCREEN while drawing, names what it frames, and
    // carries the same key as the model's Fit.
    // (The accessible name is `ToolButton`'s "label — key".)
    const fit = page.getByRole("button", { name: "Fit sketch — 0" });
    await expect(fit).toBeVisible();

    // (1) THE KEY. `0`, from the canvas, with nothing typed.
    await page.keyboard.press("0");
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-view",
      "fit-sketch",
      { timeout: 10_000 },
    );
    await waitForCameraStill(page);
    const afterKey = await project(page, CORNERS);
    for (const corner of afterKey) {
      expect(
        inside(corner, frame),
        `after Fit (key) every corner is in frame: ${JSON.stringify(afterKey)}`,
      ).toBe(true);
    }
    // ...and framed INTO the visible viewport, not merely onto the canvas.
    const fitRect = (
      (await page.getByTestId("viewport").getAttribute("data-fit-rect")) ?? ""
    )
      .split(",")
      .map(Number);
    expect(fitRect, "the fit stamped the rect it framed into").toHaveLength(4);
    const free = {
      x: frame.x + fitRect[0]!,
      y: frame.y + fitRect[1]!,
      width: fitRect[2]!,
      height: fitRect[3]!,
    };
    for (const corner of afterKey) {
      expect(
        inside(corner, free),
        `after Fit every corner is inside the unobstructed rect ${JSON.stringify(free)}: ${JSON.stringify(corner)}`,
      ).toBe(true);
    }
    // ...and it FRAMES the profile rather than merely backing away from it: a
    // zoom-out to an empty-scene standoff also puts every corner "in frame",
    // with the plate a speck. Framing means it spans most of the free rect on
    // its tighter axis.
    const xs = afterKey.map((p) => p.x);
    const ys = afterKey.map((p) => p.y);
    const fill = Math.max(
      (Math.max(...xs) - Math.min(...xs)) / free.width,
      (Math.max(...ys) - Math.min(...ys)) / free.height,
    );
    expect(
      fill,
      "the fitted profile spans at least half of the free rect",
    ).toBeGreaterThan(0.5);
    // Second, independent reading: the audit's own — every glyph in frame.
    for (const glyph of await glyphCentres(page)) {
      expect(inside(glyph, frame), `${glyph.id} in frame`).toBe(true);
    }
    await page.mouse.move(frame.x + 12, frame.y + frame.height / 2);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-fit-after-${size.label}.png`,
    });

    // (2) THE BAR. Lose the view again by hand — a right-drag PAN (the
    // sketcher's pan button) slides the profile off the right edge — and
    // click Fit.
    const midY = frame.y + frame.height / 2;
    await page.mouse.move(frame.x + frame.width * 0.3, midY);
    await page.mouse.down({ button: "right" });
    await page.mouse.move(frame.x + frame.width * 0.85, midY, { steps: 12 });
    await page.mouse.up({ button: "right" });
    await waitForCameraStill(page);
    const lost = await project(page, CORNERS);
    expect(
      lost.some((p) => !inside(p, frame)),
      `zooming in lost part of the profile: ${JSON.stringify(lost)}`,
    ).toBe(true);
    await fit.click();
    await waitForCameraStill(page);
    const afterClick = await project(page, CORNERS);
    for (const corner of afterClick) {
      expect(
        inside(corner, frame),
        `after Fit (click) every corner is in frame: ${JSON.stringify(afterClick)}`,
      ).toBe(true);
    }
  });
}

/**
 * `0` IS A DIGIT. From the instant a shape is placed, a digit typed anywhere is
 * the shape's SIZE (FLOW-A1) — and a size can start with 0 ("0.5"). So the Fit
 * key must yield while a size is being typed, or the first keystroke of "0.5"
 * re-frames the view and is swallowed, and the plate comes out 5 mm.
 *
 * The existing FLOW-A1 specs cannot see this: every size they type starts with
 * a non-zero digit, and once the first character has moved focus into the cell
 * every later `0` goes to a text field, where no global key fires. Only a size
 * that OPENS with 0 reaches the Fit key, so that is the one typed here.
 */
test("F-11 — a size typed as 0.5 goes into the size cell, not to Fit", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Fit yields");
  await page.goto(`/parts/${part.id}`);
  await enterSketch(page, "XY");
  // The Fit is ON SCREEN while drawing — which is exactly why its key has to
  // know when it is not wanted.
  await expect(page.getByTestId("sketch-view-fit")).toBeVisible();
  const at = await calibratePlane(
    page,
    { x: 700, y: 600 },
    { x: 1000, y: 400 },
  );
  await page.getByTestId("tool-rect").click();
  const a = at({ x: 0, y: 0 });
  const b = at({ x: 43, y: 27 });
  await handClick(page, a.x, a.y);
  await page.mouse.move(b.x, b.y);
  await handClick(page, b.x, b.y);
  await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
    "data-state",
    "armed",
  );
  const width = page.getByTestId("draw-dimension-width");
  await expect(width).toBeVisible();
  const viewport = page.getByTestId("viewport");
  expect(await viewport.getAttribute("data-view")).not.toBe("fit-sketch");

  for (const key of ["0", ".", "5"]) await page.keyboard.press(key);

  await expect(width).toHaveValue("0.5");
  // And the view did not re-frame: a Fit stamps `fit-sketch` when it lands.
  // The settle is named — thirty rendered frames is longer than a Fit's wait
  // plus its ease at this size.
  await waitForFrames(page, 30);
  await expect(viewport).not.toHaveAttribute("data-view", "fit-sketch");
});

/**
 * Helical-gear gap G3 — AN EDIT MUST NEVER MOVE THE SKETCH VIEW.
 *
 * The product test (docs/qa/helical-gear-2026-09-24.md, step 8): zoomed in to
 * 0.0183 mm/px to close a 0.3 um gap, the modeller applied a coincident and the
 * view jumped back to the sketcher's entry framing (0.1646 mm/px) within 4 s.
 * The same happened after a typed rectangle size and after a trim. Every
 * detail action cost a ~30 s re-zoom.
 *
 * The cause is not the edit itself but what follows it: an edit of a sketch
 * that is already a feature is synced, the part re-evaluates, a fresh mesh
 * lands, and the sketcher's camera park re-ran on the new mesh and flew the
 * camera back to the plane's default standoff. So the fixture needs a BODY on
 * screen (a cube) and a sketch that is already a FEATURE (re-opened from the
 * tree) — without either, nothing re-evaluates and the defect cannot show.
 *
 * The property: after zooming in by hand, each of the three edits the product
 * test named leaves the camera POSITION where it was, within 0.01 mm, settled
 * on position (`waitForCameraStill`), not direction. The settle is taken
 * after the part's re-evaluation has landed and the scene has drawn it.
 */

/** Sketch2's fixture geometry, sketch-plane mm on XY, clear of the cube. */
const E1 = { start: { x: 28, y: -8 }, end: { x: 48, y: -8 } };
/** A free line whose start sits 1.2 mm from E1's end: the coincident pair. */
const E2 = { start: { x: 49, y: -7.2 }, end: { x: 60, y: -2 } };
/** A crossing pair for the trim: E3 horizontal, E4 vertical, meet at (40,-18). */
const E3 = { start: { x: 28, y: -18 }, end: { x: 54, y: -18 } };
const E4 = { start: { x: 40, y: -26 }, end: { x: 40, y: -12 } };

function detailSketch() {
  const line = (
    id: string,
    l: { start: { x: number; y: number }; end: { x: number; y: number } },
  ) => ({ id, kind: "line", start: l.start, end: l.end });
  return {
    plane: { kind: "datum_plane", plane: "XY" },
    entities: [line("e1", E1), line("e2", E2), line("e3", E3), line("e4", E4)],
    constraints: [],
  };
}

async function seedDetailPart(page: Page): Promise<string> {
  await installSceneProbe(page);
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Detail zoom");
  const version = await seedCube(page, token, part.id);
  await createFeature(page, token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: detailSketch() },
    expected_tree_version: version,
  });
  return part.id;
}

/**
 * Open the part, re-open Sketch2 from the tree (a sketch that is already a
 * feature, so every edit syncs and re-evaluates), zoom in by hand toward the
 * detail and return the calibrated map at the zoomed scale plus the settled
 * pose.
 */
async function zoomIntoDetail(
  page: Page,
  partId: string,
): Promise<{ at: PlaneMapper; pose: CameraPose }> {
  await page.goto(`/parts/${partId}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  await page
    .getByTestId("feature-row")
    .filter({ hasText: "Sketch2" })
    .click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await waitForCameraStill(page);

  const coarse = await calibratePlane(
    page,
    { x: 500, y: 600 },
    { x: 800, y: 400 },
  );
  const focus = coarse({ x: 40, y: -12 });
  await page.mouse.move(focus.x, focus.y);
  for (let notch = 0; notch < 16; notch += 1) {
    await page.mouse.wheel(0, -120);
    await waitForFrames(page, 2);
  }
  await waitForCameraStill(page);
  // Re-calibrate at the zoomed scale, near the detail, so every click below
  // lands where the sketch actually is.
  const at = await calibratePlane(
    page,
    { x: focus.x - 120, y: focus.y + 100 },
    { x: focus.x + 120, y: focus.y - 100 },
  );
  const zoomedPxPerMm = Math.abs(
    (at({ x: 10, y: 0 }).x - at({ x: 0, y: 0 }).x) / 10,
  );
  const coarsePxPerMm = Math.abs(
    (coarse({ x: 10, y: 0 }).x - coarse({ x: 0, y: 0 }).x) / 10,
  );
  // PRECONDITION: the wheel really zoomed in (px per mm grew), so a reset to
  // the entry framing is a measurable move and not a no-op.
  expect(
    zoomedPxPerMm,
    `the wheel zoomed in (px/mm ${coarsePxPerMm.toFixed(2)} -> ${zoomedPxPerMm.toFixed(2)})`,
  ).toBeGreaterThan(coarsePxPerMm * 1.8);
  return { at, pose: await waitForCameraStill(page) };
}

/**
 * Wait until the edit has been synced and the part re-evaluated, then settle
 * the camera on POSITION and return it.
 */
async function settleAfterEdit(
  page: Page,
  evaluated: Promise<unknown>,
): Promise<CameraPose> {
  await evaluated;
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
  // The re-park this gate exists for eased over several hundred ms after the
  // mesh landed; 30 painted frames covers the mesh swap and the start of any
  // ease, and the position settle then waits the ease out.
  await waitForFrames(page, 30);
  return waitForCameraStill(page);
}

function nextEvaluate(page: Page, partId: string): Promise<unknown> {
  return page.waitForResponse(
    (r) =>
      r.url().includes(`/parts/${partId}/evaluate`) &&
      r.request().method() === "POST",
    { timeout: 30_000 },
  );
}

function expectSamePosition(
  before: CameraPose,
  after: CameraPose,
  what: string,
): void {
  const moved = Math.hypot(
    after.position[0] - before.position[0],
    after.position[1] - before.position[1],
    after.position[2] - before.position[2],
  );
  expect(
    moved,
    `${what} moved the camera ${moved.toFixed(3)} mm ` +
      `(${before.position.map((v) => v.toFixed(2)).join(",")} -> ` +
      `${after.position.map((v) => v.toFixed(2)).join(",")})`,
  ).toBeLessThanOrEqual(0.01);
}

test.describe("helical-gear G3: a sketch edit keeps the user's zoom", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a coincident constraint does not re-frame the zoomed view", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const partId = await seedDetailPart(page);
    const { at, pose } = await zoomIntoDetail(page, partId);

    const a = at(E1.end);
    const b = at(E2.start);
    await handClick(page, a.x, a.y);
    await page.keyboard.down("Shift");
    await handClick(page, b.x, b.y);
    await page.keyboard.up("Shift");
    await expect(page.getByTestId("selection-readout")).toContainText("2 pts");
    const evaluated = nextEvaluate(page, partId);
    await page.keyboard.press("c");
    const after = await settleAfterEdit(page, evaluated);
    // Founder pair (UPDATE_SCREENSHOTS only): the frame the modeller is left
    // looking at once the coincident has been synced and the part rebuilt.
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-gear-fix-g3-after.png`,
    });
    expectSamePosition(pose, after, "a coincident");
  });

  test("a typed rectangle size does not re-frame the zoomed view", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const partId = await seedDetailPart(page);
    const { at, pose } = await zoomIntoDetail(page, partId);

    await page.keyboard.press("r");
    const a = at({ x: 32, y: -14.5 });
    const b = at({ x: 36, y: -12.5 });
    await handClick(page, a.x, a.y);
    await page.mouse.move(b.x, b.y);
    await handClick(page, b.x, b.y);
    const width = page.getByTestId("draw-dimension-width");
    await expect(width).toBeVisible();
    for (const key of ["3", ".", "5"]) await page.keyboard.press(key);
    await expect(width).toHaveValue("3.5");
    const evaluated = nextEvaluate(page, partId);
    await page.keyboard.press("Enter");
    const after = await settleAfterEdit(page, evaluated);
    expectSamePosition(pose, after, "a typed rectangle size");
  });

  test("a trim does not re-frame the zoomed view", async ({ page }) => {
    test.setTimeout(120_000);
    const partId = await seedDetailPart(page);
    const { at, pose } = await zoomIntoDetail(page, partId);

    await page.keyboard.press("j");
    await expect(page.getByTestId("tool-trim")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const evaluated = nextEvaluate(page, partId);
    const target = at({ x: 48, y: -18 }); // E3, right of the crossing
    await handClick(page, target.x, target.y);
    await expect(page.getByTestId("sketch-edit-note")).toContainText("Trimmed");
    const after = await settleAfterEdit(page, evaluated);
    expectSamePosition(pose, after, "a trim");
  });
});
