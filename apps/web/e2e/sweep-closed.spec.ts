import { expect, test, type Page } from "./fixtures";

import { calibratePlane, enterSketch } from "./planeMap";
import {
  createPartViaApi,
  distinctCanvasColors,
  SCREENSHOT_DIR,
  seedSession,
} from "./support";

/**
 * SWEEP-CLOSED-PATH through the real browser and the real stack: a tube ring,
 * the way Fusion 360, SolidWorks and Onshape sweep one. The r5 section is
 * seeded through the gateway (an XZ circle at x = 50, as the golden
 * `sweep-closed-torus-ring-R50-r5` has it); the CLOSED path is DRAWN in the
 * sketcher — the circle tool on XY, centre clicked onto the origin and the
 * diameter typed as 100 — and swept in the sweep editor, which takes a closed path as readily
 * as an open one. The body is the torus, 2 pi^2 R r^2 = 24 674.01 mm^3.
 */

const MAJOR_R = 50;
const MINOR_R = 5;
const TORUS_VOLUME = 2 * Math.PI ** 2 * MAJOR_R * MINOR_R ** 2;

async function seedSection(
  page: Page,
  token: string,
  partId: string,
): Promise<void> {
  const response = await page.request.post(`/api/v1/parts/${partId}/features`, {
    data: {
      name: "Section",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XZ" },
          entities: [
            {
              id: "c1",
              kind: "circle",
              center: { x: MAJOR_R, y: 0 },
              radius: MINOR_R,
            },
          ],
          constraints: [],
        },
      },
      expected_tree_version: 0,
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok()) {
    throw new Error(
      `seed section: ${response.status()} ${await response.text()}`,
    );
  }
}

/** The body volume (mm³) — the cell carries its label + unit, so parse. */
async function bodyVolume(page: Page): Promise<number> {
  const text = await page.getByTestId("prop-volume").innerText();
  const match = text.match(/[\d,]+(?:\.\d+)?/);
  return match ? Number.parseFloat(match[0].replace(/,/g, "")) : Number.NaN;
}

test.describe("sweep along a closed path", () => {
  test("draw a closed circle path, sweep a tube ring around it", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1512, height: 945 });
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Tube ring");
    await seedSection(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("feature-row")).toHaveCount(1, {
      timeout: 30_000,
    });

    // The CLOSED path: an R50 circle on XY. The rim click opens the size cell
    // (FB-16) and its diameter (100) is typed into it.
    await enterSketch(page, "XY");
    const at = await calibratePlane(
      page,
      { x: 700, y: 600 },
      { x: 1000, y: 400 },
    );
    await page.keyboard.press("c");
    await expect(page.getByTestId("tool-circle")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // Centre on the origin (it snaps to the origin point), rim anywhere.
    const origin = at({ x: 0, y: 0 });
    await page.mouse.move(origin.x, origin.y);
    await page.mouse.click(origin.x, origin.y);
    const rim = at({ x: 30, y: 10 });
    await page.mouse.move(rim.x, rim.y);
    await page.mouse.click(rim.x, rim.y);
    // The placed circle's size cell takes typing (armed).
    await expect(page.getByTestId("draw-dimensions")).toHaveAttribute(
      "data-state",
      "armed",
    );
    // The cell asks for the DIAMETER (QA-CIRCLE-DIAMETER-BOX).
    for (const key of String(2 * MAJOR_R)) await page.keyboard.press(key);
    await expect(page.getByTestId("draw-dimension-diameter")).toHaveValue(
      String(2 * MAJOR_R),
    );
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("draw-dimensions")).toHaveCount(0);
    await page.keyboard.press("Escape");
    const save = page.getByTestId("sketch-save");
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0);

    // The drawn path is exactly the R50 circle about the origin.
    const listed = await page.request.get(`/api/v1/parts/${part.id}/features`, {
      headers: { Authorization: `Bearer ${account.token}` },
    });
    const tree = (await listed.json()) as {
      features: Array<{
        feature: {
          params: {
            entities?: Array<{
              kind: string;
              center?: { x: number; y: number };
              radius?: number;
            }>;
          };
        };
      }>;
    };
    const drawn = (tree.features[1]?.feature.params.entities ?? []).filter(
      (e) => e.kind === "circle",
    );
    expect(drawn, JSON.stringify(drawn)).toHaveLength(1);
    expect(drawn[0]?.center).toEqual({ x: 0, y: 0 });
    expect(drawn[0]?.radius).toBeCloseTo(MAJOR_R, 9);

    // Sweep: Section as the profile, the drawn loop as the path.
    const sweepAction = page.getByTestId("new-sweep");
    await expect(sweepAction).toBeEnabled({ timeout: 30_000 });
    await sweepAction.click();
    const editor = page.getByTestId("sweep-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("sweep-path-note")).toContainText("closed");
    await page.getByTestId("sweep-profile").press("Enter");

    // One closed solid: the torus, 2 pi^2 R r^2.
    await expect(page.getByTestId("feature-row")).toHaveCount(3);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("body-inspector")).toBeVisible({
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
      .toBeGreaterThan(24);
    const volume = await bodyVolume(page);
    expect(Math.abs(volume - TORUS_VOLUME)).toBeLessThan(0.5);

    // The ring with its sweep editor open: the founder's picture.
    await page.getByTestId("feature-select-2").click();
    await expect(editor).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sweep-closed-ring-desktop.png`,
    });
  });
});
