/**
 * CRAFT-6 — THE REFERENCE CUBE PERSISTS THROUGH AUTHORING, THE PROJECTION
 * CONTROL DOES NOT.
 *
 * The craft audit: "view navigation disappears in the two modes where
 * orientation matters most." `Viewport` mounts the cube, the view rail and the
 * nav cue under one `viewNav` prop, so entering a plane pick or a sketch took
 * all three away. Half of that was deliberate and stays — the rail carries
 * `view-projection`, and `ProjectionRig` pins the camera to perspective while
 * the sketch rig frames a plane by DISTANCE, so offering a projection toggle
 * there offers a mode the rig cannot honour. The cube is the other half: an
 * orientation readout, most valuable exactly when you are drawing on a plane
 * suspended in space.
 *
 * WHAT THIS SPEC IS BUILT NOT TO DO. A non-zero bounding box is worth very
 * little here — this repo has shipped three zero-area defects with three
 * unrelated causes (an SVG stroke `getBoundingClientRect` ignores, an
 * `sr-only` element clipped out of frame, a Tailwind utility that was never
 * generated), and `sr-only` returns TRUE from both `checkVisibility()` and
 * Playwright's `isVisible()`. A `<canvas>` reporting 300x150 is the
 * fingerprint of UN-styled, not mis-styled. So every claim below is made with
 * the user's own mechanism:
 *
 *   SIZE      against the token the seat is derived from, not a magic number,
 *             so an un-styled 300x150 canvas fails on both axes.
 *   PAINT     ink counted on `page.screenshot` — the COMPOSITED frame, which
 *             is the surface that was wrong in VIEWCUBE-1 — cropped to the
 *             cube's own rect. A canvas readback is explicitly NOT used: the
 *             audit measured that it returns ~270 label pixels whether or not
 *             the user can see the cube.
 *   REACH     `document.elementFromPoint` at the facet the test aims at, down
 *             to the TAG — an inert cube still has its host div under the
 *             pointer, so `CANVAS@view-cube` is the claim and `view-cube` is
 *             not. No `force: true` anywhere; it skips this exact check.
 *   RESPONSE  the facet lights brass under the pointer — the product's own
 *             statement that the pick surface received it, and a witness that
 *             shares no machinery with the camera one below.
 *   ACTION    a real `page.mouse.click`, asserted by a camera the test reads
 *             from the live three.js scene.
 *
 * Each of those was calibrated against a genuinely inert cube rather than
 * assumed, and the calibration cost three bad mutations first: an ancestor
 * with `display: contents` generates no box, so `pointer-events` on it reaches
 * nothing; `pointer-events: none` on the `<canvas>` ALONE changes nothing
 * either, because r3f listens on its container div, not the canvas. Both
 * "mutations" left the product fully interactive and were read, briefly, as
 * the assertions being weak. A mutation has to be shown to bite before a green
 * result under it means anything.
 *
 * AND THE INVARIANT THAT COMES WITH LETTING THE CLICK THROUGH. `requestDirection`
 * arms orthographic unconditionally, which is right in the part workspace and
 * unhonourable during authoring — so without a guard the preference is banked
 * and cashed at sketch exit, silently re-moding the camera the modeller is
 * handed back. Measured before the guard: enter in perspective, click one
 * facet, leave, and the stamp read `orthographic`. The last case pins it.
 */
import { viewCube } from "@loft/design/tokens";

import { expect, test, type Page } from "./fixtures";

import { angleBetween, cameraPose, installSceneProbe } from "./invariants";
import { createPartViaApi, seedSession, waitForFrames } from "./support";

/** The 40x25 rectangle every body-rendering spec starts from. */
const RECTANGLE_SKETCH = {
  plane: { kind: "datum_plane", plane: "XY" },
  entities: [
    { id: "e1", kind: "line", start: { x: 0, y: 0 }, end: { x: 38, y: 1 } },
    { id: "e2", kind: "line", start: { x: 39, y: 0.5 }, end: { x: 41, y: 24 } },
    {
      id: "e3",
      kind: "line",
      start: { x: 40.5, y: 26 },
      end: { x: -1, y: 25.5 },
    },
    {
      id: "e4",
      kind: "line",
      start: { x: 0.5, y: 24.5 },
      end: { x: -0.5, y: 1 },
    },
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
    { kind: "distance", entity: "e1", value_mm: 40 },
    { kind: "distance", entity: "e2", value_mm: 25 },
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
 * A part with a real body and a FULL inspector. The inspector's content is not
 * incidental: VIEWCUBE-1 only appeared once that column had enough to scroll,
 * so a bare part reproduces nothing and would make every case below vacuous.
 */
async function seedExtrudedPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Authoring cube");
  const sketch = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: RECTANGLE_SKETCH },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: 10,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  return part;
}

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Engraved-label pixels inside the cube's own rect, counted on the COMPOSITED
 * frame. Labels are `viewport.gizmo.text` (#DDE4EB) on an anvil face; nothing
 * else that reaches this corner — bench gradient, grid, ground shadow, the
 * sketch sheet — comes near this threshold.
 *
 * The whole viewport is captured and cropped afterwards, NEVER
 * `screenshot({ clip })`: a clipped capture re-rasterises its region and shows
 * the cube even in the state where the user cannot see it, i.e. it passes on
 * the broken build. That is the measurement VIEWCUBE-1 was diagnosed with.
 */
async function cubeInk(page: Page, rect: Rect): Promise<number> {
  const png = await page.screenshot();
  return page.evaluate(
    async ({ bytes, box }) => {
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      const bitmap = await createImageBitmap(blob);
      const scratch = document.createElement("canvas");
      scratch.width = Math.round(box.width);
      scratch.height = Math.round(box.height);
      const ctx = scratch.getContext("2d");
      if (ctx === null) return 0;
      ctx.drawImage(
        bitmap,
        Math.round(box.x),
        Math.round(box.y),
        scratch.width,
        scratch.height,
        0,
        0,
        scratch.width,
        scratch.height,
      );
      bitmap.close();
      const { data } = ctx.getImageData(0, 0, scratch.width, scratch.height);
      let ink = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        if (r > 170 && g > 180 && b > 185) ink += 1;
      }
      return ink;
    },
    { bytes: Array.from(png), box: rect },
  );
}

/**
 * What the USER's pointer would actually hit here — the check
 * `click({ force: true })` skips, and the reason 26 picks in this suite were
 * once unproven.
 *
 * Reported as `TAG@testid`, and the TAG half is load-bearing. A cube whose
 * pick surface is inert still has its host `<div>` under the pointer, so
 * resolving only the testid answers "is anything of the cube here" when the
 * question is "is the SURFACE THAT PICKS here". Measured against a genuinely
 * inert cube: the testid-only form still said `view-cube`, while this form
 * separates `CANVAS@view-cube` (live) from `CANVAS@viewport` (inert — the
 * pointer falls straight through to the scene behind).
 */
async function topmostTarget(
  page: Page,
  x: number,
  y: number,
): Promise<string> {
  return page.evaluate(
    ([px, py]) => {
      const el = document.elementFromPoint(px as number, py as number);
      if (el === null) return "(nothing)";
      const owner = el.closest("[data-testid]");
      return `${el.tagName}@${owner?.getAttribute("data-testid") ?? "(untagged)"}`;
    },
    [x, y],
  );
}

/**
 * Brass pixels (`viewport.gizmo.hover`) inside the cube's rect.
 *
 * The cube's hover response is the SECOND, independently-derived witness that
 * it is live, and it is the one that does not go through the camera at all: a
 * facet lighting up is the product's own statement that the pointer reached
 * the block. Keeping a witness that shares no machinery with the first is what
 * this repo keeps paying to relearn — a wrong reading verifies happily against
 * itself when both readings come from the same place.
 *
 * Measured cold/hot at the facet: 0/157 in plane pick, 0/420 while drawing,
 * and 0/0 against an inert cube. Nothing else in this corner is brass — the
 * bench, grid and ground shadow are all cool and dark.
 */
async function cubeBrass(page: Page, rect: Rect): Promise<number> {
  const png = await page.screenshot();
  return page.evaluate(
    async ({ bytes, box }) => {
      const bitmap = await createImageBitmap(
        new Blob([new Uint8Array(bytes)], { type: "image/png" }),
      );
      const scratch = document.createElement("canvas");
      scratch.width = Math.round(box.width);
      scratch.height = Math.round(box.height);
      const ctx = scratch.getContext("2d");
      if (ctx === null) return -1;
      ctx.drawImage(
        bitmap,
        Math.round(box.x),
        Math.round(box.y),
        scratch.width,
        scratch.height,
        0,
        0,
        scratch.width,
        scratch.height,
      );
      bitmap.close();
      const { data } = ctx.getImageData(0, 0, scratch.width, scratch.height);
      let brass = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        if (r > 130 && g > 95 && g < 190 && b < 110 && r - b > 55) brass += 1;
      }
      return brass;
    },
    { bytes: Array.from(png), box: rect },
  );
}

/**
 * The cube's rect, asserted to be the block the tokens describe rather than
 * merely non-empty.
 *
 * `viewCube.size` is the square the DOM host takes (the ISO silhouette is the
 * space diagonal, `face * sqrt(3)`, plus stroke clearance). Deriving the
 * expectation from the same token the component is seated by means a 300x150
 * un-styled canvas — the fingerprint of a Tailwind utility that was never
 * generated — fails on BOTH axes, and so does a zero-area one.
 */
async function cubeRect(page: Page, where: string): Promise<Rect> {
  const cube = page.getByTestId("view-cube");
  await expect(cube, `the cube is mounted in ${where}`).toBeVisible();
  const box = await cube.boundingBox();
  expect(box, `the cube has a rect in ${where}`).not.toBeNull();
  const rect = box!;
  expect(rect.width, `cube width in ${where}`).toBe(viewCube.size);
  expect(rect.height, `cube height in ${where}`).toBe(viewCube.size);
  return rect;
}

/** The FRONT facet of the block at a resting iso attitude — lower-left. */
function facetPoint(rect: Rect): [number, number] {
  return [rect.x + rect.width * 0.34, rect.y + rect.height * 0.62];
}

/**
 * Click a cube facet for real and return how far the camera turned.
 *
 * Read from the live three.js camera through the scene probe, not from
 * `data-camera-pos`: that stamp is written by `CameraRig.onSettle`, and the
 * point of this spec is the mode where the part rig is NOT the one framing.
 */
async function steerByFacet(page: Page, rect: Rect): Promise<number> {
  const before = await cameraPose(page);
  const [x, y] = facetPoint(rect);
  await page.mouse.click(x, y);
  await waitForFrames(page, 12);
  // The move eases; poll the turn rather than sampling one frame into it.
  let moved = 0;
  for (let i = 0; i < 40; i += 1) {
    const now = await cameraPose(page);
    moved = angleBetween(before.direction, now.direction);
    if (moved > 5) break;
    await waitForFrames(page, 6);
  }
  return moved;
}

/** Degrees of camera turn that can only be a facet pick, not damping coast. */
const STEERED_DEG = 20;

/** Brass pixels that can only be a lit facet. Cold measures exactly 0. */
const LIT_BRASS = 40;

/**
 * The cube is LIVE at this point: the pointer reaches its pick surface, and
 * the block lights up under it. Asserted before any click, so a failure says
 * "the user could not have addressed this" rather than "the camera did not
 * move", which are different defects with different fixes.
 */
async function expectFacetLive(
  page: Page,
  rect: Rect,
  where: string,
): Promise<void> {
  const [x, y] = facetPoint(rect);
  expect(
    await topmostTarget(page, x, y),
    `the facet the user aims at in ${where} is the cube's own pick surface`,
  ).toBe("CANVAS@view-cube");

  // Park the pointer away from the block first: "lights up" is a CHANGE, and
  // a hot reading alone cannot tell a hover response from something brass
  // that was already sitting in this corner.
  await page.mouse.move(5, 5);
  await waitForFrames(page, 10);
  expect(
    await cubeBrass(page, rect),
    `nothing is already brass in the cube's corner in ${where}`,
  ).toBeLessThan(LIT_BRASS);

  await page.mouse.move(x, y);
  await waitForFrames(page, 12);
  expect(
    await cubeBrass(page, rect),
    `the facet lights up under the pointer in ${where}`,
  ).toBeGreaterThan(LIT_BRASS);
}

test.use({ viewport: { width: 1280, height: 800 } });

test.describe("CRAFT-6 reference cube through authoring", () => {
  test("persists and steers in part, plane-pick and sketch modes", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const part = await seedExtrudedPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    // ---- PART MODE — the baseline both other modes are judged against -----
    const partRect = await cubeRect(page, "part mode");
    expect(
      await cubeInk(page, partRect),
      "cube ink in part mode",
    ).toBeGreaterThan(60);
    await expect(
      page.getByTestId("view-projection"),
      "the projection control belongs to the part workspace",
    ).toHaveCount(1);

    // ---- PLANE PICK -------------------------------------------------------
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toBeVisible({
      timeout: 10_000,
    });
    await waitForFrames(page, 30);

    const planeRect = await cubeRect(page, "plane pick");
    expect(
      await cubeInk(page, planeRect),
      "cube ink in plane pick — a mounted cube that paints nothing is the defect",
    ).toBeGreaterThan(60);
    await expect(
      page.getByTestId("view-projection"),
      "the projection control stays hidden while the sketch rig holds perspective",
    ).toHaveCount(0);

    await expectFacetLive(page, planeRect, "plane pick");
    expect(
      await steerByFacet(page, planeRect),
      "a facet click steers the camera during plane pick",
    ).toBeGreaterThan(STEERED_DEG);

    // ---- SKETCH (draw) ----------------------------------------------------
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY", {
      timeout: 10_000,
    });
    await waitForFrames(page, 30);

    const drawRect = await cubeRect(page, "sketch");
    expect(
      await cubeInk(page, drawRect),
      "cube ink while drawing — orientation matters most here",
    ).toBeGreaterThan(60);
    await expect(
      page.getByTestId("view-projection"),
      "the projection control stays hidden while drawing",
    ).toHaveCount(0);

    await expectFacetLive(page, drawRect, "sketch");
    expect(
      await steerByFacet(page, drawRect),
      "a facet click steers the camera while drawing",
    ).toBeGreaterThan(STEERED_DEG);
  });

  test("a facet click during a sketch does not re-mode the camera on exit", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const part = await seedExtrudedPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    const viewport = page.getByTestId("viewport");
    // The modeller's own projection, established before anything is authored.
    await expect(viewport).toHaveAttribute("data-projection", "perspective", {
      timeout: 20_000,
    });

    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toBeVisible({
      timeout: 10_000,
    });
    await waitForFrames(page, 30);

    // Steering during authoring is allowed and expected...
    const rect = await cubeRect(page, "plane pick");
    expect(await steerByFacet(page, rect)).toBeGreaterThan(STEERED_DEG);
    // ...and must not have moved the camera to a parallel projection, which
    // `ProjectionRig` is holding at perspective for the sketch rig's sake.
    await expect(
      viewport,
      "the rig still holds perspective while it owns the camera",
    ).toHaveAttribute("data-projection", "perspective");

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("view-projection")).toHaveCount(1, {
      timeout: 20_000,
    });
    await waitForFrames(page, 30);

    // THE LEAK. Before the guard this read `orthographic`: a preference banked
    // during authoring and cashed against the CAMRESTORE-1 pose the modeller
    // was handed back — a projection they never asked for, applied to a view
    // they did not choose it for.
    await expect(
      viewport,
      "leaving a sketch gives back the projection the modeller left with",
    ).toHaveAttribute("data-projection", "perspective");
  });

  test("the cube does not cost the sketcher its drawing gesture", async ({
    page,
  }) => {
    const part = await seedExtrudedPart(page);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY", {
      timeout: 10_000,
    });

    // The cube occupies a real 108 px corner of a canvas that is otherwise a
    // drawing surface. Everything outside it must still draw — this is the
    // regression that would make the whole item a net loss.
    await page.keyboard.press("r");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.click(430, 330);
    await page.mouse.move(760, 520);
    await page.mouse.click(760, 520);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  });
});
