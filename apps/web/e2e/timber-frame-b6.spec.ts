import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { installSceneProbe, waitForCameraStill } from "./invariants";
import { SCREENSHOT_DIR, seedSession, waitForFrames } from "./support";

/**
 * TIMBER-FRAME: B6's frame of docs/reference-parts/buildings.md from ONE
 * Timber frame feature, inserted from Build ▾.
 *
 * In an inch part: Build ▾ > Timber frame, on the form's B6 defaults, builds
 * 4 posts, 2 tie beams, 2 girts and 8 pegs (16 bodies); the cut list lists
 * them at their overall lengths (the beams with their tenons, as a weldment
 * cut list does). Then buildings.md B6's edit, width 12 -> 14 ft: tie beams
 * of 161 on 14 ft stock. A reload keeps the edit; a close-up of one corner
 * shows its two pegged joints.
 */

const PLUGIN = "loft.timber_frame";

type Row = [string, string, string, string, string];

/** buildings.md B6's cut list: member, profile, qty, overall length, stock. */
const B6_12: Row[] = [
  ["Post", "8x8", "4", "96", "8 ft"],
  ["Tie beam", "8x8", "2", "137", "12 ft"],
  ["Girt", "8x8", "2", "185", "16 ft"],
  ["Peg", "Ø1", "8", "7.5", "—"],
];
const B6_14: Row[] = [
  ["Post", "8x8", "4", "96", "8 ft"],
  ["Tie beam", "8x8", "2", "161", "14 ft"],
  ["Girt", "8x8", "2", "185", "16 ft"],
  ["Peg", "Ø1", "8", "7.5", "—"],
];

async function expectRows(page: Page, table: Row[]) {
  const panel = page.getByTestId("cut-list-panel");
  await expect(panel.getByTestId("cut-list-total")).toHaveText("16", {
    timeout: 90_000,
  });
  const rows = panel.getByTestId("cut-list-row");
  await expect(rows).toHaveCount(table.length);
  for (const [
    index,
    [member, profile, qty, length, stock],
  ] of table.entries()) {
    const row = rows.nth(index);
    await expect(row.getByTestId("cut-list-member")).toHaveText(member);
    await expect(row).toHaveAttribute("data-profile", profile);
    await expect(row.getByTestId("cut-list-qty")).toHaveText(qty);
    await expect(row.getByTestId("cut-list-length")).toHaveText(length);
    await expect(row.getByTestId("cut-list-stock")).toHaveText(stock);
  }
}

async function expectSolved(page: Page): Promise<void> {
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 90_000,
  });
}

async function openCutList(page: Page): Promise<void> {
  const tool = page.getByTestId("cut-list-tool");
  await expect(tool).toBeEnabled({ timeout: 30_000 });
  if ((await page.getByTestId("cut-list-panel").count()) === 0) {
    await tool.click();
  }
  await expect(page.getByTestId("cut-list-panel")).toBeVisible();
}

async function closeCutList(page: Page): Promise<void> {
  if ((await page.getByTestId("cut-list-panel").count()) > 0) {
    await page.getByTestId("cut-list-tool").click();
  }
  await expect(page.getByTestId("cut-list-panel")).toHaveCount(0);
}

interface Projected {
  x: number;
  y: number;
  /** View-space depth: larger is nearer the camera. */
  depth: number;
}

/** Part points (mm, the kernel's Z up) on the screen through the live
 * camera: the one whose position is the viewport's `data-camera-pos` stamp,
 * as projection.spec.ts picks it. The scene is Y up, so the kernel's
 * (x, y, z) is the scene's (x, z, -y). */
async function project(
  page: Page,
  points: [number, number, number][],
): Promise<Projected[]> {
  return page.evaluate((wanted: [number, number, number][]): Projected[] => {
    interface Cam {
      position: { x: number; y: number; z: number };
      projectionMatrix: { elements: number[] };
      matrixWorldInverse: { elements: number[] };
    }
    const w = window as unknown as Record<string, unknown>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
    const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
    const container = document.querySelector('[data-testid="viewport"]');
    const stamp = container?.getAttribute("data-camera-pos");
    const stamped = stamp ? stamp.split(",").map(Number) : [];
    let picked: Cam | null = null;
    for (const uuid of order) {
      const camera = cameras[uuid];
      if (camera === undefined) continue;
      const { x, y, z } = camera.position;
      if (
        stamped.length === 3 &&
        Math.abs(x - (stamped[0] as number)) < 0.2 &&
        Math.abs(y - (stamped[1] as number)) < 0.2 &&
        Math.abs(z - (stamped[2] as number)) < 0.2
      ) {
        picked = camera;
        break;
      }
    }
    const canvas = document.querySelector<HTMLCanvasElement>(
      '[data-testid="viewport"] canvas',
    );
    if (picked === null || canvas === null) {
      throw new Error("no stamped camera or viewport canvas");
    }
    const box = canvas.getBoundingClientRect();
    const p = picked.projectionMatrix.elements;
    const v = picked.matrixWorldInverse.elements;
    const at = (m: number[], i: number): number => m[i] as number;
    return wanted.map(([kx, ky, kz]) => {
      const [x, y, z] = [kx, kz, -ky];
      const vx = at(v, 0) * x + at(v, 4) * y + at(v, 8) * z + at(v, 12);
      const vy = at(v, 1) * x + at(v, 5) * y + at(v, 9) * z + at(v, 13);
      const vz = at(v, 2) * x + at(v, 6) * y + at(v, 10) * z + at(v, 14);
      const cx = at(p, 0) * vx + at(p, 4) * vy + at(p, 8) * vz + at(p, 12);
      const cy = at(p, 1) * vx + at(p, 5) * vy + at(p, 9) * vz + at(p, 13);
      const cw = at(p, 3) * vx + at(p, 7) * vy + at(p, 11) * vz + at(p, 15);
      const d = cw === 0 ? 1 : cw;
      return {
        x: box.x + (cx / d / 2 + 0.5) * box.width,
        y: box.y + (0.5 - cy / d / 2) * box.height,
        depth: vz,
      };
    });
  }, points);
}

/** Zoom in on the post nearest the camera at the tie beam's joint, and
 * screenshot the corner: both pegged joints of that post. */
async function shootNearestCorner(
  page: Page,
  width: number,
  name: string,
): Promise<void> {
  const IN = 25.4;
  const length = 192;
  const corners: [number, number, number][] = [
    [3.75, 3.75],
    [width - 3.75, 3.75],
    [3.75, length - 3.75],
    [width - 3.75, length - 3.75],
  ].map(([x, y]) => [x! * IN, y! * IN, 76 * IN]);
  const seen = await project(page, corners);
  const nearest = seen.reduce((a, b) => (b.depth > a.depth ? b : a));
  await page.mouse.move(nearest.x, nearest.y);
  console.log(
    JSON.stringify(seen),
    await page.getByTestId("viewport").getAttribute("data-camera-pos"),
  );
  for (let notch = 0; notch < 10; notch += 1) {
    await page.mouse.wheel(0, -120);
    await waitForFrames(page, 2);
  }
  console.log(
    await page.getByTestId("viewport").getAttribute("data-camera-pos"),
  );
  await page.mouse.move(4, 4);
  await waitForCameraStill(page);
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png` });
}

test.describe("Timber frame — B6 from one feature", () => {
  test.use({ viewport: { width: 1600, height: 1000 } });

  test("insert a Timber frame from Build ▾, list its members, edit the width, see a joint", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const account = await seedSession(page);
    const auth = { Authorization: `Bearer ${account.token}` };
    const created = await page.request.post("/api/v1/parts", {
      data: { name: "B6 timber frame", length_unit: "in" },
      headers: auth,
    });
    expect(created.ok(), await created.text()).toBe(true);
    const part = (await created.json()) as { id: string };

    await installSceneProbe(page);
    await page.goto(`/parts/${part.id}`);
    const rows = page.getByTestId("feature-row");
    await expect(rows).toHaveCount(0);

    // Build ▾ > Timber frame: the generated form, B6's frame by default.
    await page.getByTestId("build-more").click();
    const tool = page.getByTestId(`plugin-tool-${PLUGIN}`);
    await expect(tool).toBeEnabled({ timeout: 30_000 });
    await expect(tool).toHaveAccessibleName(/^Timber frame/);
    await tool.click();
    const editor = page.getByTestId("plugin-editor");
    await expect(editor).toContainText("New Timber frame");
    await expect(page.getByTestId("plugin-input-width_mm")).toHaveValue("144");
    await expect(page.getByTestId("plugin-input-length_mm")).toHaveValue("192");
    await expect(page.getByTestId("plugin-input-bent_count")).toHaveValue("2");
    await expect(page.getByTestId("plugin-input-girt_height_mm")).toHaveValue(
      "60",
    );
    const posts = page.getByTestId("plugin-input-post_profile");
    await expect(posts.locator("option:checked")).toHaveText("8x8");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });

    // ONE tree row; it unfolds into its members, drawn by the plugin.
    await expect(rows).toHaveCount(1);
    await expect(rows.nth(0)).toContainText("Timber frame 1");
    await expectSolved(page);
    await page.getByTestId("feature-unfold-0").click();
    const members = page.getByTestId("feature-member-row");
    await expect(members.and(page.locator('[data-role="post"]'))).toHaveCount(
      4,
    );
    await expect(
      members.and(page.locator('[data-role="tie_beam"]')),
    ).toHaveCount(2);
    await expect(members.and(page.locator('[data-role="girt"]'))).toHaveCount(
      2,
    );
    await expect(members.and(page.locator('[data-role="peg"]'))).toHaveCount(8);
    await expect(members.filter({ hasText: "Tie beam 2" })).toHaveCount(1);
    await page.getByTestId("feature-unfold-0").click();
    await expect(page.getByTestId("body-row")).toHaveCount(16);

    await openCutList(page);
    await expectRows(page, B6_12);
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timber-frame-b6-12x16.png`,
    });

    // buildings.md B6's edit: width 12 -> 14 ft.
    await page.getByTestId("feature-select-0").click();
    await expect(editor).toContainText("Edit Timber frame");
    await page.getByTestId("plugin-input-width_mm").fill("14 ft");
    await page.getByTestId("plugin-submit").click();
    await expect(editor).toBeHidden({ timeout: 30_000 });
    await expectSolved(page);
    await openCutList(page);
    await expectRows(page, B6_14);
    await page.mouse.move(800, 990);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/timber-frame-b6-14x16.png`,
    });

    // A reload keeps the edit, pinned to 1.0.0.
    await page.reload();
    await expect(rows).toHaveCount(1);
    await expectSolved(page);
    await openCutList(page);
    await expectRows(page, B6_14);
    const tree = await page.request.get(`/api/v1/parts/${part.id}/features`, {
      headers: auth,
    });
    const frame = (
      (await tree.json()) as {
        features: {
          feature: {
            params: { plugin_version: string; inputs: Record<string, unknown> };
          };
        }[];
      }
    ).features[0]?.feature.params;
    expect(frame?.plugin_version).toBe("1.0.0");
    expect(frame?.inputs.width_mm).toBeCloseTo(168 * 25.4, 6);

    // A close-up of one corner: the tie beam's and the girt's joints,
    // their shoulders on the post and the pegs' ends flush with its faces.
    await closeCutList(page);
    await page.getByTestId("view-fit").click();
    await waitForFrames(page, 30);
    await shootNearestCorner(page, 168, "timber-frame-joint-corner");
  });
});
