import { expect, test, type Locator, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * SKETCH-PLANE-PICK (merges SKETCH-STALE-FACE and SKETCH-ON-FACE-CLICK), the
 * Fusion convention: Create Sketch uses the face selected NOW, else waits for a
 * click on an origin plane or a planar face.
 *
 *  1. With nothing selected, New Sketch opens the plane picker.
 *  2. A pick from a cancelled command is never a pre-selection. Before, a face
 *     picked in a Shell that was then cancelled seated every later New Sketch
 *     on it (the enclosure's five sketches on an inner wall).
 *  3. A click on a visible planar face sketches on that face, with no "Pick a
 *     face" step. Before, the click fell through the body to the origin sheet
 *     behind it (the bracket's boss sketch landed on XY at z = 0).
 *
 * The cube is 20 mm, so its top face is the only face centred at z = 20.
 */

const TOP_Z = 20;

async function openCube(page: Page): Promise<string> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Plane pick cube");
  await seedCube(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText("8,000", {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
  return part.id;
}

/** The z of a pick mark's "centred at x, y, z millimetres" name. */
async function markZ(node: Locator): Promise<number> {
  const label = (await node.getAttribute("aria-label")) ?? "";
  const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
  return Number.parseFloat((nums[nums.length - 1] ?? "NaN") as string);
}

/** The mark whose face is the cube's top (the greatest centroid z). */
async function topMark(page: Page, prefix: string): Promise<Locator> {
  const nodes = page.locator(`[data-testid^="${prefix}"]`);
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const count = await nodes.count();
  for (let i = 0; i < count; i += 1) {
    if ((await markZ(nodes.nth(i))) === TOP_Z) return nodes.nth(i);
  }
  throw new Error(`no ${prefix} mark at z = ${TOP_Z} among ${count}`);
}

/** Count every feature POST from here on (a sketch seat writes a datum). */
function countFeatureWrites(page: Page, partId: string): () => number {
  let writes = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().includes(`/parts/${partId}/features`)
    ) {
      writes += 1;
    }
  });
  return () => writes;
}

/** New Sketch, and prove it waits on the plane picker and writes nothing. */
async function expectPlanePicker(
  page: Page,
  writes: () => number,
): Promise<void> {
  const before = writes();
  await page.getByTestId("new-sketch").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
  // Long enough for a seeded on_face datum to have POSTed (it starts at once).
  await waitForFrames(page, 10);
  await page.waitForTimeout(500);
  await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
  expect(writes(), "New Sketch wrote a datum nobody picked").toBe(before);
}

/**
 * A point ON THE CANVAS (not on the face's DOM mark) where the armed surface
 * says the pointer is over face `ordinal`: a ring around the mark, outside it.
 */
async function canvasPointOnFace(
  page: Page,
  mark: Locator,
  ordinal: string,
): Promise<{ x: number; y: number }> {
  const box = await mark.boundingBox();
  if (box === null) throw new Error("the top face's mark has no box");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const viewport = page.getByTestId("viewport");
  const seen: string[] = [];
  for (const radius of [36, 28, 48, 20]) {
    for (let step = 0; step < 12; step += 1) {
      const angle = (step / 12) * 2 * Math.PI;
      const x = Math.round(cx + radius * Math.cos(angle));
      const y = Math.round(cy + radius * Math.sin(angle));
      const onCanvas = await page.evaluate(
        ([px, py]) => document.elementFromPoint(px, py)?.tagName === "CANVAS",
        [x, y] as const,
      );
      if (!onCanvas) {
        seen.push(`${x},${y}:dom`);
        continue;
      }
      await page.mouse.move(x, y);
      await waitForFrames(page, 2);
      const hovered = await viewport.getAttribute("data-face-pick-hover");
      if (hovered === ordinal) return { x, y };
      seen.push(`${x},${y}:${hovered}`);
    }
  }
  throw new Error(
    `no canvas point near the mark (${cx},${cy}) addresses face ${ordinal}: ` +
      seen.join(" "),
  );
}

test.describe("SKETCH-PLANE-PICK", () => {
  test("nothing selected: New Sketch opens the plane picker", async ({
    page,
  }) => {
    const partId = await openCube(page);
    const writes = countFeatureWrites(page, partId);
    await expectPlanePicker(page, writes);
    // Escape still leaves the picker in one press (stolen-Escape family).
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);
  });

  test("a face picked in a cancelled Shell is not a pre-selection", async ({
    page,
  }) => {
    const partId = await openCube(page);
    const writes = countFeatureWrites(page, partId);

    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await (await topMark(page, "shell-face-")).click();
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
    );
    await page.getByTestId("shell-cancel").click();
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);

    // The cancelled pick is not lit as a selection either.
    await expect(page.getByTestId("viewport")).not.toHaveAttribute(
      "data-body-highlight",
      "feature",
    );
    await expectPlanePicker(page, writes);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);

    // The same holds after an Escape-cancelled Shell (the band's CANCEL ESC).
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await (await topMark(page, "shell-face-")).click();
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
    );
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shell-editor")).toHaveCount(0);
    await expectPlanePicker(page, writes);
  });

  test("a click on a visible planar face sketches on that face", async ({
    page,
  }) => {
    const partId = await openCube(page);
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("Pick a plane");
    // Never armed: no "Pick a face" step, and the origin planes stay offered.
    await expect(page.getByTestId("plane-pick-face")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(page.getByTestId("face-pick-prompt")).toHaveCount(0);
    await expect(page.getByTestId("plane-XY")).toBeVisible();

    const mark = await topMark(page, "plane-pick-face-");
    const testid = (await mark.getAttribute("data-testid")) ?? "";
    const ordinal = testid.replace("plane-pick-face-", "");
    await expect(page.getByTestId("viewport")).toHaveAttribute(
      "data-face-mark-seats",
      "settled",
      { timeout: 60_000 },
    );
    const point = await canvasPointOnFace(page, mark, ordinal);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-plane-pick-2026-10-09/hover-top-face.png`,
    });

    const datumWrite = page.waitForRequest(
      (r) =>
        r.method() === "POST" && r.url().includes(`/parts/${partId}/features`),
      { timeout: 30_000 },
    );
    // A real canvas click: the ray meets the top face before any origin sheet.
    await page.mouse.click(point.x, point.y);
    const body = (await datumWrite).postDataJSON() as {
      feature: {
        type: string;
        params: {
          kind: string;
          face: { selector: { signature: { centroid: { z: number } } } };
        };
      };
    };
    expect(body.feature.type).toBe("datum");
    expect(body.feature.params.kind).toBe("on_face");
    expect(body.feature.params.face.selector.signature.centroid.z).toBeCloseTo(
      TOP_Z,
      3,
    );

    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("dro-plane")).toHaveText("Face");
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sketch-plane-pick-2026-10-09/on-top-face.png`,
    });
  });
});
