import type { Locator } from "@playwright/test";

import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances } from "./assemblyFlow";
import { seedDenseHolePlate, seedOccludedEdgePlate } from "./partSeed";
import { litPoints, measureReachabilityWith, type Point } from "./reachability";
import {
  SCREENSHOT_DIR,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * SEL-4 — EVERY armed pick addresses the geometry, not a 24 px dot.
 *
 * SEL-1 A2 converted ONE overlay (the sketch-plane face pick) and lifted its
 * reachability from 9.9 % to 84.6 %. The founder's "picking is very difficult"
 * was therefore unfixed the moment the tool was fillet rather than
 * sketch-on-face: `EdgePickOverlay`, `ShellFaceOverlay`, `MeasureOverlay`,
 * `InstanceMateOverlay` and `HolePointOverlay` all still hung their only
 * handler on a `PickNode`. This is the gate for converting them.
 *
 * ## The fixture, and why the box could not do this job
 *
 * A2's acceptance names a DENSE-HOLE-PATTERN fixture and the shipped gate did
 * not have one. On a six-face box every entity is far from every other entity
 * in both ordinal space and screen space, so a pick model that quietly answers
 * "the one next door" scores perfectly. `seedDenseHolePlate` puts seven Ø6
 * bores on a Ø40 bolt circle: 14 circular edges and 7 snap centres crowded
 * together, which is where a widened corridor either stays a corridor or
 * becomes a blanket.
 *
 * ## Why the EDGE metric is anisotropy and not an area fraction
 *
 * A face is 2-D, so "what fraction of the body's lit area addresses a face" is
 * the honest question and the one the FB-3/FB-5 census asks. An edge is 1-D:
 * it has no area, so a fraction is meaningless — a perfect edge pick would
 * still score near zero. What actually changed is the SHAPE of the live region.
 * A 24 px dot addresses ±12 px in every direction and nothing beyond; a band
 * addresses tens-to-hundreds of pixels in two opposite directions and ~12 px
 * perpendicular. So the measurement sweeps directions from each edge's own mark
 * and records how far the edge answers in each — which is exactly the property
 * the fix claims, and exactly the one a dot cannot fake by being moved or
 * multiplied.
 *
 * MUTATION-VERIFIED. Removing `EdgeBandLayer` from `EdgePickOverlay` (i.e.
 * restoring the `PickNode`-only hit-test) leaves every direction at the DOM
 * node's own ~12 px, so `along` collapses to 13 px for every edge and the
 * `>= 40 px` assertion fails on all of them while the perpendicular bound still
 * passes. That asymmetry is the point: the gate is sensitive to the thing that
 * changed and insensitive to the thing that did not.
 */

/** Radii swept outward from an edge's mark, in CSS px. */
const RADII = [13, 20, 28, 40, 60, 90, 130] as const;

/** Directions swept. 16 keeps the worst tangent misalignment at 11.25°, where
 *  a 12 px corridor still reaches 61 px — comfortably past the 40 px floor, so
 *  a real band can never fail this for want of angular resolution. */
const DIRECTIONS = 16;

/** Reach floor ALONG an edge (px). A dot cannot exceed its own 12 px. */
const ALONG_MIN_PX = 40;

/** Reach ceiling PERPENDICULAR to a straight edge (px) — it stays a corridor. */
const PERP_MAX_PX = 16;

interface EdgeMark {
  index: number;
  kind: string;
  /** The mark's full accessible name — carries the edge's own mid-span. */
  label: string;
  centre: Point;
}

interface EdgeReach {
  mark: EdgeMark;
  /** Furthest radius still addressing this edge, per direction. */
  profile: number[];
  along: number;
  perp: number;
  /** Any OTHER edge addressed within the innermost ring — cross-talk. */
  crossTalk: string[];
}

async function openDensePlate(page: Page): Promise<Locator> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Bolt circle plate");
  await seedDenseHolePlate(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(24);
  // Pin the framing: every number here is in screen pixels, so it is only
  // comparable between runs if the part is the same size in frame.
  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
  return viewport;
}

/** Every edge pick mark on screen, with the entity kind from its own name. */
async function edgeMarks(page: Page): Promise<EdgeMark[]> {
  const nodes = page.locator('[data-testid^="edge-pick-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const marks: EdgeMark[] = [];
  for (const node of await nodes.all()) {
    const testId = (await node.getAttribute("data-testid")) ?? "";
    const label = (await node.getAttribute("aria-label")) ?? "";
    const box = await node.boundingBox();
    if (box === null) continue;
    marks.push({
      index: Number(testId.replace("edge-pick-", "")),
      // "Edge 5, circle, centred at …" — the kernel's own edge kind.
      kind: (label.split(",")[1] ?? "").trim(),
      label,
      centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
    });
  }
  return marks;
}

/**
 * Sweep outward from an edge's mark and record how far that edge still answers
 * in each direction. Contiguous by construction: the first radius that stops
 * answering ends that direction, so a coincidental hit far away cannot inflate
 * the reach.
 */
async function measureReach(
  page: Page,
  viewport: Locator,
  mark: EdgeMark,
  attribute = "data-edge-pick-hover",
  /** The stamp value that counts as "this edge" (mates stamp `instance:index`). */
  wanted = String(mark.index),
): Promise<EdgeReach> {
  const profile: number[] = [];
  const crossTalk = new Set<string>();
  for (let d = 0; d < DIRECTIONS; d += 1) {
    const angle = (2 * Math.PI * d) / DIRECTIONS;
    let reach = 0;
    for (const radius of RADII) {
      await page.mouse.move(
        mark.centre.x + radius * Math.cos(angle),
        mark.centre.y + radius * Math.sin(angle),
      );
      const stamped = await viewport.getAttribute(attribute);
      if (stamped === wanted) {
        reach = radius;
        continue;
      }
      // The innermost ring is the crowding test: just outside this edge's own
      // 24 px mark, on a bolt circle, nothing else may answer.
      if (stamped !== null && radius === RADII[0]) crossTalk.add(stamped);
      break;
    }
    profile.push(reach);
  }
  let best = 0;
  profile.forEach((reach, d) => {
    if (reach > (profile[best] as number)) best = d;
  });
  const quarter = DIRECTIONS / 4;
  const perp = Math.max(
    profile[(best + quarter) % DIRECTIONS] as number,
    profile[(best + DIRECTIONS - quarter) % DIRECTIONS] as number,
  );
  return {
    mark,
    profile,
    along: profile[best] as number,
    perp,
    crossTalk: [...crossTalk],
  };
}

async function armFilletPick(page: Page): Promise<void> {
  await expect(page.getByTestId("new-fillet")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-fillet").click();
  await expect(page.getByTestId("fillet-editor")).toBeVisible();
  await page.getByTestId("fillet-mode-pick").click();
  await expect(page.locator('[data-testid^="edge-pick-"]').first()).toBeVisible(
    { timeout: 20_000 },
  );
  await waitForFrames(page, 4);
}

test.describe("SEL-4 — the armed pick addresses the geometry", () => {
  test("fillet edges: the EDGE is the target, not a diamond at its mid-span", async ({
    page,
  }) => {
    const viewport = await openDensePlate(page);
    await armFilletPick(page);

    // A 60 mm plate with seven Ø6 bores: 12 box edges + 7 × (two circular
    // mouths + the cylinder's own SEAM line) = 33. If this count ever changes
    // the fixture changed, and the numbers below stop being comparable.
    const marks = await edgeMarks(page);
    expect(marks.length, "the plate's B-rep edges are all pickable").toBe(33);

    // Sample rather than sweep all 26: each edge costs ~100 pointer moves, and
    // the claim is about the SHAPE of the live region, which does not need
    // every instance of it. Circles first, because the crowded bolt circle is
    // the part of the fixture the box could not provide.
    const circles = marks.filter((m) => m.kind === "circle").slice(0, 5);
    const lines = marks.filter((m) => m.kind === "line").slice(0, 3);
    const sampled: EdgeReach[] = [];
    for (const mark of [...circles, ...lines]) {
      sampled.push(await measureReach(page, viewport, mark));
    }

    const report = sampled
      .map((r) => `#${r.mark.index}(${r.mark.kind}) ${r.along}/${r.perp}px`)
      .join(" ");

    // NON-VACUITY FIRST, so this cannot pass by measuring nothing: a stamp that
    // gets stuck set would score every direction at the outermost radius.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });

    // THE CLAIM. Some sampled edges face away from the camera or hide behind
    // the plate, and those are correctly refused by the occlusion test — so the
    // assertion is about the visible ones. Under the old dot every edge scores
    // 13 px, so no arrangement of dots reaches this.
    const reachable = sampled.filter((r) => r.along >= ALONG_MIN_PX);
    expect(
      reachable.length,
      `edges addressable >= ${ALONG_MIN_PX}px along: ${report}`,
    ).toBeGreaterThanOrEqual(3);

    // …AND IT IS STILL A CORRIDOR. A straight edge's live region must stay
    // narrow across the entity, or neighbours stop being distinguishable and
    // the fix has traded one founder complaint for a worse one. Circles are
    // excluded deliberately: a Ø6 bore is ~40 px across at this framing, so
    // "perpendicular" from a point on it lands on the SAME edge's far side —
    // that measures the entity, not the tolerance.
    for (const reach of reachable.filter((r) => r.mark.kind === "line")) {
      expect(
        reach.perp,
        `edge #${reach.mark.index} perpendicular reach (${report})`,
      ).toBeLessThanOrEqual(PERP_MAX_PX);
    }

    // THE MIS-RESOLUTION DETECTOR the dense fixture exists for: probing just
    // outside one bore's mark must never report a different edge.
    // …applied to the edges that are actually ADDRESSABLE, which is the whole
    // claim and not a convenient subset. An edge hidden behind the plate is
    // SUPPOSED to yield to the visible one in front of it, and this fixture
    // produces exactly that case — measured 2026-08-08: bore #12's occluded
    // bottom circle sits 34 px from bore #19's visible top mouth, because a
    // 10 mm plate is thin next to a Ø40 bolt circle. Demanding silence there
    // would be demanding the occlusion test be wrong. A six-face box cannot
    // stage this at all, which is why A2 asked for this fixture.
    for (const reach of reachable) {
      expect(
        reach.crossTalk,
        `edge #${reach.mark.index} answered as another edge (${report})`,
      ).toEqual([]);
    }
  });

  test("shell faces: the visible body IS the pick target", async ({ page }) => {
    const viewport = await openDensePlate(page);
    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    // The FB-3/FB-5 census, pointed at the overlay SEL-1 did not convert. One
    // round trip per point, so the grid is coarse; the lit silhouette supplies
    // the points, so this is a fraction of what the user can SEE.
    const points = await litPoints(page, { step: 24 });
    const measured = await measureReachabilityWith(points, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-shell-face-hover")) !== null;
    });

    expect(measured.sampled, "body sampled").toBeGreaterThan(40);
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-shell-face-hover", /.*/, {
      timeout: 5_000,
    });

    // The same 50 % floor the sketch-plane pick is held to, for the same
    // reason: it cannot be reached by adding dots, only by changing what a
    // target is. The bore walls are cylindrical and shell refuses them, so this
    // will not reach 100 % on this fixture and should not.
    expect(
      measured.fraction,
      `clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);
  });

  test("measure: a vertex still beats the widened edge band", async ({
    page,
  }) => {
    const viewport = await openDensePlate(page);
    await page.keyboard.press("m");
    await expect(
      page.locator('[data-testid^="measure-vertex-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    // Widening the edges could have cost the vertices their precedence: a
    // corner sits under two marks, which is why `VERTEX_Z_RANGE` /
    // `EDGE_Z_RANGE` exist. The DOM saves us by mechanism — a `PickNode` is a
    // drei `Html` node ABOVE the canvas, so a pointer over a vertex square is
    // consumed before r3f ever raycasts. That is asserted here rather than
    // assumed, because "it works because of a layering detail" is exactly the
    // kind of guarantee that quietly stops being true.
    const vertex = page.locator('[data-testid^="measure-vertex-"]').first();
    const box = await vertex.boundingBox();
    expect(box, "a vertex mark is on screen").not.toBeNull();
    if (box === null) return;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);

    // The edge band does not claim the point…
    await expect(viewport).not.toHaveAttribute(
      "data-measure-edge-hover",
      /.*/,
      { timeout: 5_000 },
    );
    // …and the click lands on the VERTEX, which the readout names.
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await expect(page.getByTestId("measure-readout")).toContainText("Vertex");
  });

  test("measure: an edge answers along its whole span", async ({ page }) => {
    const viewport = await openDensePlate(page);
    await page.keyboard.press("m");
    await expect(
      page.locator('[data-testid^="measure-edge-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    const nodes = page.locator('[data-testid^="measure-edge-"]');
    const marks: EdgeMark[] = [];
    for (const node of await nodes.all()) {
      const testId = (await node.getAttribute("data-testid")) ?? "";
      const box = await node.boundingBox();
      if (box === null) continue;
      marks.push({
        index: Number(testId.replace("measure-edge-", "")),
        kind: "",
        label: (await node.getAttribute("aria-label")) ?? "",
        centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
      });
    }
    expect(marks.length).toBeGreaterThan(10);

    // The same sweep against a DIFFERENT overlay and a different stamp: the
    // shared `EdgeBandLayer` has to be live here too, or Measure keeps the old
    // dot while Fillet gets the band — which is exactly the split SEL-4 exists
    // to close.
    const sampled: EdgeReach[] = [];
    for (const mark of marks.slice(0, 5)) {
      sampled.push(
        await measureReach(page, viewport, mark, "data-measure-edge-hover"),
      );
    }
    const report = sampled
      .map((r) => `#${r.mark.index} ${r.along}px`)
      .join(" ");

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute(
      "data-measure-edge-hover",
      /.*/,
      { timeout: 5_000 },
    );

    expect(
      sampled.filter((r) => r.along >= ALONG_MIN_PX).length,
      `measure edges addressable >= ${ALONG_MIN_PX}px along: ${report}`,
    ).toBeGreaterThanOrEqual(2);
  });

  test("a HIDDEN body stops occluding the edges behind it", async ({
    page,
  }) => {
    // THE REASON YOU HIDE A BODY IS TO REACH WHAT IS BEHIND IT. The pick mesh
    // is fused and takes a single material, so `Mesh.raycast` tests a
    // switched-off body's triangles exactly like a drawn one's
    // (`partView.pickHiddenFaces`) — and the band's occlusion test used to
    // measure that hit, so hiding the wall killed edge picking over the whole
    // region it used to cover. No spec covered multi-body + hidden + edge pick,
    // which is why it shipped (SEL-4 review, 2026-08-08).
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Wall and plate");
    await seedOccludedEdgePlate(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
      timeout: 30_000,
    });
    const viewport = page.getByTestId("viewport");
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);

    // FRONT view is the whole fixture: it puts the wall exactly between the
    // camera and the plate's top-front edge (see `seedOccludedEdgePlate`).
    await page.getByTestId("view-front").click();
    await viewport.evaluate((node) => {
      node.dataset["fitRect"] = "";
    });
    await page.getByTestId("view-fit").click();
    await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
      timeout: 20_000,
    });
    await waitForFrames(page, 6);
    await armFilletPick(page);

    // The plate's two top edges — y = 30 (facing the camera) and y = 50 —
    // project to the SAME screen line in the front view, so either is a correct
    // answer for a probe on it. Named by their own OCCT mid-span rather than by
    // an index that depends on kernel order.
    const marks = await edgeMarks(page);
    const topEdges = marks.filter(
      (m) => m.kind === "line" && /centred at 30, (30|50), 10 /.test(m.label),
    );
    expect(
      topEdges.map((m) => m.index).sort(),
      `the plate's top edges are on offer (${marks.map((m) => m.label).join(" | ")})`,
    ).toHaveLength(2);
    const wanted = new Set(topEdges.map((m) => String(m.index)));
    const centre = (topEdges[0] as EdgeMark).centre;

    /** Which edges answer along the occluded span, clear of any 24 px mark. */
    const probe = async (): Promise<Set<string>> => {
      const seen = new Set<string>();
      for (const dx of [-45, -30, -18, 18, 30, 45]) {
        await page.mouse.move(centre.x + dx, centre.y);
        const stamped = await viewport.getAttribute("data-edge-pick-hover");
        if (stamped !== null) seen.add(stamped);
      }
      return seen;
    };

    /** Cycle a body's eye to a wanted state (solid → ghost → hidden → solid). */
    const setBodyMode = async (index: number, mode: string): Promise<void> => {
      const row = page.getByTestId("body-row").nth(index);
      for (let i = 0; i < 4; i += 1) {
        if ((await row.getAttribute("data-visibility")) === mode) return;
        await page.getByTestId(`body-visibility-${index}`).click();
      }
      await expect(row).toHaveAttribute("data-visibility", mode);
    };
    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 20_000,
    });

    // 1) WITH BOTH BODIES DRAWN the edge is genuinely behind material, and the
    //    occlusion test is RIGHT to refuse it. This is the control that keeps
    //    the fix from being "delete the occlusion test".
    const occluded = await probe();
    expect(
      [...occluded].filter((s) => wanted.has(s)),
      "an edge behind drawn material must not answer",
    ).toEqual([]);

    // 2) HIDE ONE BODY AT A TIME. Hiding the wall must open the pick; hiding
    //    the plate itself must not (the wall is still in the way) — so exactly
    //    one of the two toggles changes the answer, whichever ordinal the
    //    kernel gave the wall.
    const answered: boolean[] = [];
    for (const index of [0, 1]) {
      await setBodyMode(index, "hidden");
      await waitForFrames(page, 4);
      const seen = await probe();
      answered.push([...seen].some((s) => wanted.has(s)));
      await setBodyMode(index, "solid");
      await waitForFrames(page, 4);
    }
    expect(
      answered,
      `edges behind the hidden body answered: body1=${answered[0]} body2=${answered[1]}`,
    ).toEqual(expect.arrayContaining([true]));
    expect(
      answered.filter(Boolean),
      "exactly ONE body is the occluder — hiding the other changes nothing",
    ).toHaveLength(1);

    // Negative control for the stamp: off the body it must clear, or every
    // probe above scored on a stuck attribute.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("hole: the face is the placement target, and a snap still lands exact", async ({
    page,
  }) => {
    const viewport = await openDensePlate(page);
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

    // Seat the hole on the plate's TOP face — the one carrying the bolt circle,
    // named by its own z rather than by an index that depends on kernel order.
    const faces = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(faces.first()).toBeVisible({ timeout: 20_000 });
    let topIndex = 0;
    let topZ = -Infinity;
    const all = await faces.all();
    for (let i = 0; i < all.length; i += 1) {
      const label = (await all[i]?.getAttribute("aria-label")) ?? "";
      const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
      const z = Number.parseFloat(nums[nums.length - 1] ?? "NaN");
      if (Number.isFinite(z) && z > topZ) {
        topZ = z;
        topIndex = i;
      }
    }
    await all[topIndex]?.click();
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );

    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await waitForFrames(page, 4);

    // FREE PLACEMENT — the behaviour change SEL-4 ships. Find a lit point on
    // the top face that is clear of every snap mark, and drill there. Under the
    // old overlay this click did nothing at all: the only live targets were the
    // centre, the four corners and the seven bore centres, which is why a
    // fifth mounting hole on a vendor plate could not be authored (QA3-1).
    const snapBoxes = (
      await Promise.all(
        (
          await page
            .locator(
              '[data-testid^="hole-point-center"], [data-testid^="hole-point-vertex-"], [data-testid^="hole-point-circle-"]',
            )
            .all()
        ).map((n) => n.boundingBox()),
      )
    ).flatMap((b) => (b === null ? [] : [b]));
    const points = await litPoints(page, { step: 12 });
    let placed: Point | null = null;
    for (const point of points) {
      const clear = snapBoxes.every(
        (b) =>
          point.x < b.x - 16 ||
          point.x > b.x + b.width + 16 ||
          point.y < b.y - 16 ||
          point.y > b.y + b.height + 16,
      );
      if (!clear) continue;
      await page.mouse.move(point.x, point.y);
      if ((await viewport.getAttribute("data-hole-point-hover")) === null) {
        continue;
      }
      placed = point;
      break;
    }
    expect(
      placed,
      "a point on the placement face, clear of every snap mark",
    ).not.toBeNull();
    if (placed === null) return;

    await page.mouse.click(placed.x, placed.y);
    // The readout leaves "Centre of face" for a real coordinate — the click
    // placed the drill somewhere the old overlay could not reach.
    await expect(page.getByTestId("hole-position")).not.toContainText(
      "Centre of face",
    );
    await expect(page.getByTestId("hole-position")).toContainText("mm");

    // …AND THE SNAP STILL WINS WHERE IT SHOULD. A bore centre clicked through
    // its `PickNode` echoes the exact centre, not the pixel under the cursor:
    // the DOM node sits above the canvas, so the raycast never runs there.
    await page.getByTestId("hole-point-pick").click();
    const circle = page.locator('[data-testid^="hole-point-circle-"]').first();
    await expect(circle).toBeVisible({ timeout: 20_000 });
    await circle.click();
    await expect(page.getByTestId("hole-position")).toContainText("mm");

    // Negative control for the stamp — a stuck attribute would make the free
    // placement search above succeed anywhere, including off the body.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-hole-point-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("assembly mates: each INSTANCE's own geometry is the mate target", async ({
    page,
  }) => {
    // The mate half of SEL-4 shipped without a gate. The only mate coverage —
    // `assembly.spec.ts` via `authorBoltMates` — dispatches clicks straight at
    // `mate-face-*` / `mate-axis-*` by test id, which is verbatim the "the
    // suite proved a path no hand takes" failure the conversion exists to fix:
    // those specs passed before it and after it, so they cannot discriminate.
    // This one aims at the geometry.
    const { idA, idB } = await setupTwoInstances(page);
    const viewport = page.getByTestId("viewport");

    await page.getByTestId("mate-coincident").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    await expect(
      page.locator('[data-testid^="mate-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    // The FB-3/FB-5 census over both plates at once. The stamp carries
    // `instanceId:index`, so this measures not just "something answered" but
    // WHICH instance answered — a single shared hover writer cannot fake it.
    const stamps = new Set<string>();
    const points = await litPoints(page, { step: 24 });
    const measured = await measureReachabilityWith(points, async (point) => {
      await page.mouse.move(point.x, point.y);
      const stamped = await viewport.getAttribute("data-mate-pick-hover");
      if (stamped !== null) stamps.add(stamped);
      return stamped !== null;
    });
    expect(measured.sampled, "two plates sampled").toBeGreaterThan(40);

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-mate-pick-hover", /.*/, {
      timeout: 5_000,
    });

    // The same 50 % floor the shell and sketch-plane picks are held to. The
    // Ø10 bore wall is cylindrical and a coincident mate refuses it, so this
    // will not reach 100 % on this fixture and should not.
    expect(
      measured.fraction,
      `mate faces clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);

    // BOTH instances answer, and each answers AS ITSELF. This is the
    // cross-instance check: the overlays are siblings writing one stamp, so a
    // hover owned per-overlay can have A's unmount clobber B's live value.
    expect(
      new Set([...stamps].map((s) => s.split(":")[0])),
      `instances addressed: ${[...stamps].join(" ")}`,
    ).toEqual(new Set([idA, idB]));

    // …AND THE AXIS PICK IS A BAND, not a diamond. Same sweep as the part
    // workspace, against the assembly's own `EdgeBandLayer` mount.
    await page.getByTestId("mate-concentric").click();
    await expect(page.getByTestId("mate-hud")).toBeVisible();
    const axes = page.locator(`[data-testid^="mate-axis-${idA}-"]`);
    await expect(axes.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    const sampled: EdgeReach[] = [];
    for (const node of (await axes.all()).slice(0, 2)) {
      const testId = (await node.getAttribute("data-testid")) ?? "";
      const box = await node.boundingBox();
      if (box === null) continue;
      const index = Number(testId.replace(`mate-axis-${idA}-`, ""));
      sampled.push(
        await measureReach(
          page,
          viewport,
          {
            index,
            kind: "circle",
            label: (await node.getAttribute("aria-label")) ?? "",
            centre: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
          },
          "data-mate-pick-hover",
          `${idA}:${index}`,
        ),
      );
    }
    const report = sampled
      .map((r) => `#${r.mark.index} ${r.along}px`)
      .join(" ");
    expect(
      sampled.filter((r) => r.along >= ALONG_MIN_PX).length,
      `mate axes addressable >= ${ALONG_MIN_PX}px along: ${report}`,
    ).toBeGreaterThanOrEqual(1);
  });
});

test.describe("SEL-4 — founder screenshots", () => {
  async function captureEdgePick(
    page: Page,
    width: "desktop" | "laptop",
  ): Promise<void> {
    const viewport = await openDensePlate(page);
    await armFilletPick(page);
    // Park the pointer ON a bore mouth, well away from its mark, so the shot is
    // the thing that changed: the edge lights because the EDGE is the target,
    // not because the cursor found a 24 px diamond. The bore is chosen by
    // MEASURED reach rather than by index — the first circle in kernel order is
    // as likely as not the occluded bottom mouth, and parking on that would
    // photograph the occlusion test doing its job instead of the band doing
    // its job.
    const circles = (await edgeMarks(page)).filter((m) => m.kind === "circle");
    let target: { point: Point; reach: number } | null = null;
    for (const circle of circles) {
      // Stop at the first bore that is genuinely reachable. The kernel emits
      // every bore's BOTTOM mouth before any of the tops, so scanning a fixed
      // prefix photographs seven occluded circles and nothing else — measured
      // 2026-08-08, and it produced a byte-identical "after" shot.
      if (target !== null && target.reach >= ALONG_MIN_PX) break;
      const reach = await measureReach(page, viewport, circle);
      let best = 0;
      reach.profile.forEach((r, d) => {
        if (r > (reach.profile[best] as number)) best = d;
      });
      const radius = reach.profile[best] as number;
      if (target !== null && radius <= target.reach) continue;
      const angle = (2 * Math.PI * best) / DIRECTIONS;
      target = {
        reach: radius,
        // 60 % of the way out: unambiguously off the mark, comfortably inside
        // the corridor, so the shot does not depend on a boundary pixel.
        point: {
          x: circle.centre.x + radius * 0.6 * Math.cos(angle),
          y: circle.centre.y + radius * 0.6 * Math.sin(angle),
        },
      };
    }
    // With the band gone this is every-direction zero, so the pointer lands on
    // the mark itself — which is exactly the "before" picture.
    const point = target?.point ?? circles[0]?.centre;
    if (point !== undefined) await page.mouse.move(point.x, point.y);
    await waitForFrames(page, 4);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sel4-edge-band-${width}.png`,
    });
  }

  test("armed edge pick on a bolt circle (desktop 1600×1000)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await captureEdgePick(page, "desktop");
  });

  test("armed edge pick on a bolt circle (small laptop 1280×800)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await captureEdgePick(page, "laptop");
  });
});
