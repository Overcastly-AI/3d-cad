/**
 * The EDGE-MARK-OVERLAP fixture, shared by its specs: the reference run's
 * enclosure without its draft, an 80 x 60 x 40 box shelled to a 2 mm wall
 * with the top open, plus the readers for its rim edge marks.
 */
import { expect, type Page } from "./fixtures";

import { installSceneProbe, waitForCameraStill } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  expectSeatsSettled,
  seedSession,
} from "./support";

export const W = 80;
export const D = 60;
export const H = 40;
export const WALL = 2;

export async function seedEnclosure(page: Page, token: string, partId: string) {
  const sketch = await createFeature(page, token, partId, {
    name: "Sketch1",
    feature: {
      type: "sketch",
      version: 1,
      params: rectangleSketch(0, 0, W, D),
    },
    expected_tree_version: 0,
  });
  const solid = await createFeature(page, token, partId, {
    name: "Extrude1",
    feature: {
      type: "extrude",
      version: 1,
      params: {
        profile: { kind: "feature", feature_id: sketch.feature.id },
        distance_mm: H,
        operation: "add",
        direction: "normal",
      },
    },
    expected_tree_version: sketch.tree_version,
  });
  await createFeature(page, token, partId, {
    name: "Shell1",
    feature: {
      type: "shell",
      version: 1,
      params: {
        thickness_mm: WALL,
        faces: {
          kind: "faces",
          refs: [
            {
              kind: "subshape",
              feature_id: solid.feature.id,
              subshape_type: "face",
              selector: {
                selector_version: 1,
                signature: {
                  subshape_type: "face",
                  surface: "plane",
                  area_mm2: W * D,
                  centroid: { x: W / 2, y: D / 2, z: H },
                  normal: { x: 0, y: 0, z: 1 },
                },
              },
            },
          ],
        },
      },
    },
    expected_tree_version: solid.tree_version,
  });
}

/** One edge mark as the page draws it. */
export interface Mark {
  id: string;
  index: number;
  /** OCCT mid-span parsed from the accessible name. */
  mid: [number, number, number];
  cx: number;
  cy: number;
  buried: boolean;
  /** The `data-testid` owning the element on top of the mark's own centre. */
  top: string;
}

export async function readMarks(page: Page): Promise<Mark[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('[data-testid^="edge-pick-"]')].map((el) => {
      const r = el.getBoundingClientRect();
      const cx = (r.left + r.right) / 2;
      const cy = (r.top + r.bottom) / 2;
      const hit = document.elementFromPoint(cx, cy);
      const id = el.getAttribute("data-testid") ?? "?";
      const at = /centred at (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)/.exec(
        el.getAttribute("aria-label") ?? "",
      );
      return {
        id,
        index: Number(id.slice("edge-pick-".length)),
        mid: (at === null
          ? [NaN, NaN, NaN]
          : [Number(at[1]), Number(at[2]), Number(at[3])]) as [
          number,
          number,
          number,
        ],
        cx,
        cy,
        buried: el.getAttribute("data-buried") === "true",
        top:
          hit?.closest("[data-testid]")?.getAttribute("data-testid") ??
          hit?.tagName ??
          "(none)",
      };
    }),
  );
}

export const near = (a: number, b: number) => Math.abs(a - b) < 0.2;

/** The eight rim edges: z = H, on the outer or the inner rectangle. */
export function rimMarks(marks: readonly Mark[]): {
  outer: Mark[];
  inner: Mark[];
} {
  const outer: Mark[] = [];
  const inner: Mark[] = [];
  for (const mark of marks) {
    const [x, y, z] = mark.mid;
    if (!near(z, H)) continue;
    const onX = near(y, D / 2) && (near(x, 0) || near(x, W));
    const onY = near(x, W / 2) && (near(y, 0) || near(y, D));
    const inX = near(y, D / 2) && (near(x, WALL) || near(x, W - WALL));
    const inY = near(x, W / 2) && (near(y, WALL) || near(y, D - WALL));
    if (onX || onY) outer.push(mark);
    else if (inX || inY) inner.push(mark);
  }
  return { outer, inner };
}

/**
 * `iso` looks down into the box, where every rim edge is visible. `below` is
 * the front view in PERSPECTIVE, which the below-rim test then orbits down
 * so the camera looks UP at the rim: the inner front rim is hidden behind the
 * front wall, 2 mm behind it, which is less than the band's body-scale
 * occlusion bias (the review finding on this fix).
 */
export async function openArmedEnclosure(
  page: Page,
  pose: "iso" | "below" = "iso",
): Promise<void> {
  await installSceneProbe(page);
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Enclosure housing");
  await seedEnclosure(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(16);
  if (pose === "below") {
    const projection = page.getByTestId("view-projection");
    if (
      (await projection.getAttribute("aria-label")) ===
      "Projection: orthographic"
    ) {
      await projection.click();
    }
    await expect(projection).toHaveAttribute(
      "aria-label",
      "Projection: perspective",
    );
  }
  await page.getByTestId(pose === "iso" ? "view-iso" : "view-front").click();
  await waitForCameraStill(page);
  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-mode-pick").click();
  await expect(
    page.locator('[data-testid^="edge-pick-"]').first(),
  ).toBeAttached({ timeout: 20_000 });
  await waitForCameraStill(page);
  await expectSeatsSettled(page, "fillet armed on the enclosure");
  await waitForCameraStill(page);
}
