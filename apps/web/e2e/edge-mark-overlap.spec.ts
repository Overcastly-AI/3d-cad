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

import {
  cameraPose,
  installSceneProbe,
  waitForCameraStill,
} from "./invariants";
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

/**
 * `iso` looks down into the box, where every rim edge is visible. `below` is
 * the front view in PERSPECTIVE, which the below-rim test then orbits down
 * so the camera looks UP at the rim: the inner front rim is hidden behind the
 * front wall, 2 mm behind it, which is less than the band's body-scale
 * occlusion bias (the review finding on this fix).
 */
async function openArmedEnclosure(
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

test("EDGE-MARK-OVERLAP, from below the rim: the hidden inner rim never takes the visible outer rim's pick", async ({
  page,
}) => {
  test.setTimeout(300_000);
  await openArmedEnclosure(page, "below");

  const isOuterFront = (m: Mark) =>
    near(m.mid[0], W / 2) && near(m.mid[1], 0) && near(m.mid[2], H);
  const isInnerFront = (m: Mark) =>
    near(m.mid[0], W / 2) && near(m.mid[1], WALL) && near(m.mid[2], H);

  // ORBIT DOWN. Level with the box's mid-height, the two front rims project
  // under a pixel apart, inside the band's depth tie, so depth decides and
  // the defect cannot show (and zoom is clamped well before that changes).
  // Tipping the camera down below the part opens the angle between the rims
  // to a few pixels while the box stays framed. A drag, like a user's orbit.
  const box = await page.getByTestId("viewport").boundingBox();
  if (box === null) throw new Error("no viewport box");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  for (let step = 1; step <= 3; step += 1) {
    await page.mouse.move(cx, cy - step * 10);
  }
  await page.mouse.up();
  await page.mouse.move(4, 4);
  await waitForCameraStill(page);
  await expectSeatsSettled(page, "orbited below the rim");
  await waitForCameraStill(page);
  const pose = await cameraPose(page);
  console.log(
    `    [below] camera at scene (${pose.position.map((v) => v.toFixed(1)).join(", ")})`,
  );
  // Scene coordinates: the front face is z = 0, the rim is y = 40.
  expect(pose.position[1], "the camera is below the rim").toBeLessThan(H);

  const marks = await readMarks(page);
  const outerFront = marks.find(isOuterFront);
  const innerFront = marks.find(isInnerFront);
  expect(outerFront, "the outer front rim is offered").toBeDefined();
  expect(innerFront, "the inner front rim is offered").toBeDefined();
  if (outerFront === undefined || innerFront === undefined) return;

  // The outer front rim is in plain view: live, and on top at its centre.
  expect(outerFront.buried, "the visible outer front rim is live").toBe(false);
  expect(outerFront.top).toBe(outerFront.id);
  // The inner front rim is behind the front wall from here, so no seat on it
  // is addressable: its mark is a buried ghost, not a live control.
  expect(
    innerFront.buried,
    "the inner front rim is hidden behind the wall and must be drawn buried",
  ).toBe(true);

  // THE REVIEW CASES. With the marks hidden, sweep the pointer through the
  // outer rim's corridor at its mark's column, and 12 px past it on either
  // side: every row that answers at all must answer the outer rim, never its
  // hidden twin 2 mm behind the wall. Past the corridor is where the twin is
  // the ONLY edge in range and used to win on the occlusion slack alone
  // (EDGE-HIDDEN-LONE).
  await page.evaluate(() => {
    const host = document.querySelector<HTMLElement>(
      '[data-testid="pick-mark-layer"]',
    );
    if (host !== null) host.style.visibility = "hidden";
  });
  const viewport = page.getByTestId("viewport");
  const answers: string[] = [];
  let answered = 0;
  for (let dy = -24; dy <= 24; dy += 1) {
    await page.mouse.move(4, 4);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /./);
    await page.mouse.move(outerFront.cx, outerFront.cy + dy);
    await waitForFrames(page, 2);
    const hover = await expect
      .poll(() => viewport.getAttribute("data-edge-pick-hover"), {
        timeout: 1_000,
      })
      .not.toBeNull()
      .then(
        () => viewport.getAttribute("data-edge-pick-hover"),
        () => null,
      );
    if (hover !== null) answered += 1;
    if (hover !== null && hover !== String(outerFront.index)) {
      answers.push(`dy=${dy}: ${hover}`);
    }
  }
  expect(answered, "the sweep must cross the outer rim's band").toBeGreaterThan(
    3,
  );
  expect(
    answers,
    `a row in or beside the outer front rim's corridor answered another edge ` +
      `(inner front rim is ${innerFront.index})`,
  ).toEqual([]);
});
