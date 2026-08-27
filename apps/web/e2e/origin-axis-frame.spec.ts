import { expect, test, type Page } from "./fixtures";

import { createPartViaApi, SCREENSHOT_DIR, seedSession } from "./support";

/**
 * FB-21 — the origin axis glyphs are labelled in KERNEL space but were drawn in
 * SCENE space, which the GLB rotation has already turned.
 *
 * Founder: *"check the axis. Turn on the axis and compare them to the view
 * cube."* The unit gate (`src/viewport/OriginGeometry.test.ts`) pins the
 * DERIVATION; this one settles what the ticket said could only be settled by
 * rendering — that the drawn glyphs, the drawn plane sheets and the camera's
 * named views agree once a real body of known dimensions is on screen.
 *
 * It is deliberately raster-free: every assertion reads the SCREEN POSITION of
 * a DOM label (drei's `Html`, projected by the real camera), never a pixel, so
 * it cannot flake on anti-aliasing and it fails for a reason you can read.
 *
 * It is also origin-free, which matters more than it sounds. The obvious
 * reference point — where the three axes meet — is not in the DOM, and the
 * canvas centre is NOT it (the camera frames the subject, and this subject's
 * centre is at kernel 10, 10, 10). So every assertion below is a relation
 * BETWEEN two labels, which needs no projection of a point nothing draws.
 *
 * WHAT IT ASSERTS, AND WHY NOT THE OBVIOUS THING. The tempting test is "the
 * axis you look down collapses onto the origin". Measured, it does not: the
 * triad is sized from the subject's bounding diagonal and overruns it, so in a
 * head-on view that axis' tip lands near — or behind — the perspective camera's
 * eye and its projection DIVERGES instead of collapsing (the Z label read
 * (-3546, 4521) on a 1280x800 frame). Divergence is not a stable thing to
 * assert on. What is stable, in every view, is WHICH GLYPH RUNS UP THE SCREEN:
 *
 *   FRONT (down the kernel's +Y) -> the part's height is up-screen, so Z is
 *   TOP   (down the kernel's +Z) -> the plan's up is +y, so kernel Y is
 *
 * Both invert under the defect, because the defect swapped exactly these two
 * axes: it drew the Z glyph along scene +Z (the kernel's −Y) and the Y glyph
 * along scene +Y (the kernel's +Z). That is what the founder saw without
 * measuring anything.
 */

/** A closed, fully-constrained 20x20 square on XY -> a 20 mm cube when extruded. */
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

/**
 * How far "clearly above" is. The observed margins are ~1,100–1,800 px (the
 * triad overruns the frame), so this is an order of magnitude of headroom over
 * the real signal while staying far above any label jitter.
 */
const APART_PX = 150;

interface Point {
  x: number;
  y: number;
}

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

/** A 20 mm cube: an XY sketch extruded +20 along that plane's own normal. */
async function seedCube(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Axis frame cube");
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
  return part.id;
}

/** Screen centre of an axis glyph's engraved letter. */
async function labelAt(page: Page, axis: "X" | "Y" | "Z"): Promise<Point> {
  const box = await page
    .getByTestId(`origin-axis-label-${axis}`)
    .boundingBox({ timeout: 20_000 });
  if (box === null) throw new Error(`no bounding box for the ${axis} label`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Snap to a named view and let the camera tween land. */
async function view(page: Page, key: "1" | "2"): Promise<void> {
  await page.keyboard.press(key);
  await page.waitForTimeout(1500);
}

/**
 * Park the pointer off the model before a capture.
 *
 * The viewport warms the body under the cursor, so a screenshot taken with the
 * mouse wherever the last click left it shows a hover state that is not what
 * the shot is about.
 */
async function restPointer(page: Page): Promise<void> {
  await page.mouse.move(4, 4);
  await page.waitForTimeout(400);
}

/**
 * NOTE FOR THE BOARD, found while capturing this evidence and NOT fixed here
 * (out of FB-21's scope): the triad is sized at `1.6 x` the subject's bounding
 * DIAGONAL and then overruns that by `AXIS_OVERRUN`, which puts every axis tip
 * ~2x outside the frame the camera fits to the subject. So the glyphs the
 * founder was asked to "turn on" are off-screen at the default fit for ANY part
 * — the ratio is scale-free, so no size of body escapes it. The labels are
 * reachable by zooming out; they should not have to be.
 */

test.describe("origin axis glyphs agree with the model and the ViewCube", () => {
  test.setTimeout(240_000);

  test("the glyph labelled Z runs along the part's height, in FRONT and in TOP", async ({
    page,
  }) => {
    const partId = await seedCube(page);
    await page.goto(`/parts/${partId}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    // A body of KNOWN dimensions, as the ticket insisted: 20^3.
    await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
      timeout: 30_000,
    });

    // Turn the triad on — the founder's own first step. The XY sheet comes with
    // it so the screenshots answer the ticket's open question about whether the
    // plane glyphs mislead the same way (they do not: `OriginPlane` builds from
    // `sceneOriginBasis`, and in FRONT the sheet reads edge-on under the cube).
    await page.getByTestId("origin-plane-XY").click();
    for (const axis of ["X", "Y", "Z"] as const) {
      await page.getByTestId(`origin-axis-${axis}`).click();
    }
    await expect(page.getByTestId("origin-axis-label-Z")).toBeVisible({
      timeout: 20_000,
    });

    // ── FRONT looks along the kernel's +Y, so the part's HEIGHT is up-screen.
    await view(page, "1");
    const frontX = await labelAt(page, "X");
    const frontY = await labelAt(page, "Y");
    const frontZ = await labelAt(page, "Z");

    // Z is the glyph that runs UP the screen — the same direction the 20 mm
    // extrude grew from its XY sketch. THIS is the acceptance criterion,
    // rendered. Under the defect the topmost glyph here was Y.
    expect(frontZ.y).toBeLessThan(frontX.y - APART_PX);
    expect(frontZ.y).toBeLessThan(frontY.y - APART_PX);
    // …and X runs ACROSS, to the right of Y — so a frame in which everything
    // happened to pile up cannot satisfy the two assertions above by accident.
    expect(frontX.x).toBeGreaterThan(frontY.x + APART_PX);

    // Evidence for the founder, taken AFTER the assertions so a capture step
    // can never influence them.
    await restPointer(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/origin-axis-front-desktop.png`,
    });

    // ── TOP looks straight down the kernel's +Z — the ViewCube face the
    // founder asked us to compare against. Z is now the axis pointing at the
    // eye (so its projection is not something to assert on, see the header);
    // the readable fact is that the PLAN's up-screen axis is the kernel's +Y,
    // which is the convention `upFor` states and every drawing sheet uses.
    await view(page, "2");
    const topX = await labelAt(page, "X");
    const topY = await labelAt(page, "Y");

    expect(topY.y).toBeLessThan(topX.y - APART_PX);
    expect(topX.x).toBeGreaterThan(topY.x + APART_PX);

    await restPointer(page);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/origin-axis-top-desktop.png`,
    });
  });
});
