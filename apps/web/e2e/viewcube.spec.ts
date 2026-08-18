/**
 * VIEWCUBE-1 — the reference cube is PRESENT, PAINTED and OPERABLE at every
 * frame the responsive floor covers, not just the tall ones.
 *
 * The defect this pins: the cube was drawn through drei's `<GizmoHelper>`/
 * `<Hud>`, a second `gl.render` into the main canvas, and Chromium dropped that
 * pass from the composited frame whenever the inspector column was scrolling —
 * which is exactly what it does below a canvas height of ~742 px. So the cube
 * was there at 1600x1000 / 1440x900 / 1280x900 and gone at 1400x800 /
 * 1280x800 / 1366x768: the three commonest laptop frames, including the
 * 1280x800 the founder screenshots are captured at.
 *
 * THREE ASSERTIONS, and each one is here because the other two can pass while
 * the product is broken:
 *
 *  1. INK IN THE COMPOSITED FRAME. Counted on `page.screenshot`, never on a
 *     canvas readback — the audit measured that a `drawImage` census returns
 *     ~270 label pixels whether the user can see the cube or not, because the
 *     drawing buffer was never the thing that was wrong. Sampling the wrong
 *     surface is how this defect survived a "cube renders" check for weeks.
 *  2. AT THE CUBE'S OWN RECT, not the corner in the abstract, so a cube that
 *     drifts out of its seat fails rather than being found by a lucky crop.
 *  3. AN ACTUAL VIEW CHANGE from clicking a face. Presence is not operability:
 *     a cube painted behind a panel, or one whose picks stopped routing to the
 *     view-command store, satisfies (1) and (2) and is still useless.
 */
import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, seedSession } from "./support";

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
 * A part whose inspector is FULL — mass properties, bounding box, topology,
 * status and the export strip. That matters: the defect only appeared once the
 * inspector column had enough content to scroll, so a bare part would have
 * reproduced nothing.
 */
async function seedExtrudedPart(page: Page): Promise<{ id: string }> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Cube probe");
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

/**
 * Engraved-label pixels inside the cube's own rect, counted on the COMPOSITED
 * frame. The labels are set in `viewport.gizmo.text` (`#DDE4EB`) on an anvil
 * face, so nothing else in that corner of the scene — grid, ground shadow, the
 * bench gradient — comes near this threshold; the lit aluminium body does, but
 * the fit keeps it out of the cube's charged rect.
 */
async function cubeInk(page: Page): Promise<number> {
  const box = await page.getByTestId("view-cube").boundingBox();
  if (box === null) throw new Error("view cube has no rect");
  // A WHOLE-VIEWPORT capture, cropped afterwards — NOT `screenshot({ clip })`.
  // Measured while diagnosing VIEWCUBE-1: a small clipped capture re-rasterises
  // its region and shows the cube even in the state where the user cannot see
  // it, so a clip-based oracle passes on the broken build. The full capture is
  // the surface the founder screenshots come from and the one that reddens.
  const png = await page.screenshot();
  return page.evaluate(
    async ({ bytes, rect }) => {
      const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
      const bitmap = await createImageBitmap(blob);
      const scratch = document.createElement("canvas");
      scratch.width = Math.round(rect.width);
      scratch.height = Math.round(rect.height);
      const ctx = scratch.getContext("2d");
      if (ctx === null) return 0;
      ctx.drawImage(
        bitmap,
        Math.round(rect.x),
        Math.round(rect.y),
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
    { bytes: Array.from(png), rect: box },
  );
}

/**
 * The three frames the cube was ABSENT on, and the three it already worked on.
 * The second group is the regression half: a fix that only serves short frames
 * is half a fix.
 */
const FRAMES = [
  { width: 1280, height: 800, wasBroken: true },
  { width: 1366, height: 768, wasBroken: true },
  { width: 1400, height: 800, wasBroken: true },
  { width: 1280, height: 900, wasBroken: false },
  { width: 1440, height: 900, wasBroken: false },
  { width: 1600, height: 1000, wasBroken: false },
];

for (const frame of FRAMES) {
  const label = `${frame.width}x${frame.height}${frame.wasBroken ? " (was absent)" : ""}`;
  test.describe(`view cube at ${label}`, () => {
    test.use({ viewport: { width: frame.width, height: frame.height } });

    test("is painted and steers the camera", async ({ page }) => {
      const part = await seedExtrudedPart(page);
      await page.goto(`/parts/${part.id}`);
      await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
        timeout: 30_000,
      });

      const cube = page.getByTestId("view-cube");
      await expect(cube).toBeVisible();

      // The cube's seat: inside the frame, clear of the timeline, bottom-right.
      const box = await cube.boundingBox();
      expect(box).not.toBeNull();
      const rect = box!;
      expect(rect.width).toBeGreaterThan(80);
      expect(rect.height).toBeGreaterThan(80);
      expect(rect.x + rect.width).toBeLessThanOrEqual(frame.width);
      expect(rect.y + rect.height).toBeLessThanOrEqual(frame.height);

      // (1)+(2) — ink, in the composited frame, at the cube's own rect.
      await expect
        .poll(() => cubeInk(page), { timeout: 15_000 })
        .toBeGreaterThan(60);

      // (3) — operability. The viewport stamps the settled pose; the opening
      // fit stamps `fit-auto`, and ONLY a reference-cube pick stamps
      // `direction` (the ViewBar's buttons stamp their own names), so the
      // transition is unambiguous evidence that the click reached the block and
      // routed through the view-command store.
      const viewport = page.getByTestId("viewport");
      await expect(viewport).toHaveAttribute("data-view", "fit-auto", {
        timeout: 20_000,
      });
      const before = await viewport.getAttribute("data-camera-pos");
      // The FRONT facet: lower-left of the block at the resting iso attitude.
      await page.mouse.click(
        rect.x + rect.width * 0.34,
        rect.y + rect.height * 0.62,
      );
      await expect(viewport).toHaveAttribute("data-view", "direction", {
        timeout: 20_000,
      });
      // …and the camera actually MOVED. A stamp without a move would be a
      // command that fired into a rig that ignored it.
      await expect
        .poll(() => viewport.getAttribute("data-camera-pos"), {
          timeout: 20_000,
        })
        .not.toBe(before);
    });
  });
}
