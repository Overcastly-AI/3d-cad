/**
 * EDGE-MARK-OVERLAP (reference run 2026-09-30): on a thin wall, the outer and
 * inner rim edges run a few pixels apart on screen, and so did their 24 px
 * pick marks. The later mark covered the earlier one, so clicking the outer
 * back rim's visible mark picked the INNER edge, and the editor only said
 * "4 edges picked". The enclosure's first fillet went on two inner edges.
 *
 * The part is the reference run's enclosure without its draft: an 80 x 60 x 40
 * box shelled to a 2 mm wall with the top open. Its eight rim edges are four
 * parallel pairs 2 mm apart, which is the whole defect.
 *
 * What this pins, in the order a user meets it:
 *
 *  1. every rim mark is live (drawn, not a buried ghost) and is the topmost
 *     element at its own centre (`elementFromPoint`), so the mark you can see
 *     is the mark you click;
 *  2. with the marks out of the way, the pointer on each rim edge highlights
 *     THAT edge, not its twin 2 mm away (the band resolves nearest to the
 *     cursor, as Fusion 360 and SolidWorks pre-highlight);
 *  3. real clicks on the four outer marks pick exactly the four outer edges.
 */
import { expect, test, type Page } from "./fixtures";

import { installSceneProbe, waitForCameraStill } from "./invariants";
import { createFeature, rectangleSketch } from "./partSeed";
import {
  createPartViaApi,
  distinctCanvasColors,
  expectSeatsSettled,
  seedSession,
  waitForFrames,
} from "./support";

test.use({ viewport: { width: 1280, height: 800 } });

const W = 80;
const D = 60;
const H = 40;
const WALL = 2;

async function seedEnclosure(page: Page, token: string, partId: string) {
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
interface Mark {
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

async function readMarks(page: Page): Promise<Mark[]> {
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

const near = (a: number, b: number) => Math.abs(a - b) < 0.2;

/** The eight rim edges: z = H, on the outer or the inner rectangle. */
function rimMarks(marks: readonly Mark[]): { outer: Mark[]; inner: Mark[] } {
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

async function openArmedEnclosure(page: Page): Promise<void> {
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
  await page.getByTestId("view-iso").click();
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

/**
 * Evidence for the founder, written only when `EDGE_MARK_SHOTS` names a file:
 * the pointer rests on the outer back rim's mark, so the frame shows which
 * edge that mark highlights.
 */
async function captureEvidence(page: Page, mark: Mark): Promise<void> {
  const path = process.env["EDGE_MARK_SHOTS"];
  if (path === undefined || path === "") return;
  await page.mouse.move(4, 4);
  await waitForFrames(page, 1);
  await page.mouse.move(mark.cx, mark.cy);
  await waitForFrames(page, 3);
  await page.screenshot({ path });
  await page.mouse.move(4, 4);
  await waitForFrames(page, 1);
}

test("EDGE-MARK-OVERLAP: every rim mark on a 2 mm wall is on top at its own centre and picks its own edge", async ({
  page,
}) => {
  test.setTimeout(300_000);
  await openArmedEnclosure(page);

  const { outer, inner } = rimMarks(await readMarks(page));
  expect(outer.length, "four outer rim marks").toBe(4);
  expect(inner.length, "four inner rim marks").toBe(4);
  const rim = [...outer, ...inner];
  const back = outer.find((m) => near(m.mid[1], D));
  if (back !== undefined) await captureEvidence(page, back);

  // 1. Every rim edge is in plain view from the iso camera (each bounds the
  //    visible rim face), so every rim mark must be live and on top.
  expect(
    rim
      .filter((m) => m.buried || m.top !== m.id)
      .map(
        (m) =>
          `${m.id} (${m.mid.join(",")}) @ (${Math.round(m.cx)},` +
          `${Math.round(m.cy)}) buried=${m.buried} top=${m.top}`,
      ),
    "a rim mark is buried, or another element covers its own centre",
  ).toEqual([]);

  // 2. The pointer on the edge itself highlights that edge. The marks are
  //    muted so the band answers, and each mark's centre is a point ON its
  //    own edge, so this probes every rim edge a few px from its twin.
  await page.evaluate(() => {
    const host = document.querySelector<HTMLElement>(
      '[data-testid="pick-mark-layer"]',
    );
    if (host !== null) host.style.visibility = "hidden";
  });
  const wrongHover: string[] = [];
  for (const mark of rim) {
    await page.mouse.move(4, 4);
    await expect(page.getByTestId("viewport")).not.toHaveAttribute(
      "data-edge-pick-hover",
      /./,
    );
    await page.mouse.move(mark.cx, mark.cy);
    const hover = await expect
      .poll(
        () => page.getByTestId("viewport").getAttribute("data-edge-pick-hover"),
        { timeout: 2_000 },
      )
      .not.toBeNull()
      .then(
        () => page.getByTestId("viewport").getAttribute("data-edge-pick-hover"),
        () => null,
      );
    if (hover !== String(mark.index)) {
      wrongHover.push(`${mark.id} (${mark.mid.join(",")}) hovers ${hover}`);
    }
  }
  await page.evaluate(() => {
    const host = document.querySelector<HTMLElement>(
      '[data-testid="pick-mark-layer"]',
    );
    if (host !== null) host.style.visibility = "";
  });
  expect(
    wrongHover,
    "the pointer on a rim edge highlights a different edge",
  ).toEqual([]);

  // 3. Real clicks on the four outer marks pick exactly the four outer edges.
  //    Each mark is re-read before its click: a pick mounts the radius gauge
  //    and the marks re-seat around it.
  for (const target of outer) {
    await page.mouse.move(4, 4);
    await waitForFrames(page, 1);
    await expectSeatsSettled(page, `before clicking ${target.id}`);
    const now = (await readMarks(page)).find((m) => m.id === target.id);
    expect(now, `${target.id} is still drawn`).toBeDefined();
    if (now === undefined) return;
    expect(now.top, `${target.id} is on top at its own centre`).toBe(now.id);
    await page.mouse.click(now.cx, now.cy);
    await expect(page.getByTestId(target.id)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await waitForCameraStill(page);
  }
  const pressed = await page.evaluate(() =>
    [
      ...document.querySelectorAll(
        '[data-testid^="edge-pick-"][aria-pressed="true"]',
      ),
    ]
      .map((el) => el.getAttribute("data-testid") ?? "")
      .sort(),
  );
  expect(pressed).toEqual(outer.map((m) => m.id).sort());
});
