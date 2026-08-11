import type { Locator } from "@playwright/test";

import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances } from "./assemblyFlow";
import {
  labelIsWall,
  litAfterHiding,
  openOccludedPlate,
  setBodyMode,
} from "./occludedPlate";
import { seedDenseHolePlate } from "./partSeed";
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

/** The band's half-width — `edgeBand.EDGE_BAND_TOLERANCE_PX`, in CSS px. */
const EDGE_CORRIDOR_PX = 12;

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

/** The edge marks on offer, split by the body each one belongs to. */
async function splitEdgeMarks(page: Page): Promise<{
  marks: EdgeMark[];
  wall: EdgeMark[];
  plate: EdgeMark[];
}> {
  const marks = await edgeMarks(page);
  return {
    marks,
    wall: marks.filter((m) => labelIsWall(m.label)),
    plate: marks.filter((m) => !labelIsWall(m.label)),
  };
}

/** How many shell face marks each body currently offers. */
async function splitFaceMarks(
  page: Page,
): Promise<{ wall: number; plate: number }> {
  const nodes = page.locator('[data-testid^="shell-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  let wall = 0;
  let plate = 0;
  for (const node of await nodes.all()) {
    const label = (await node.getAttribute("aria-label")) ?? "";
    if (labelIsWall(label)) wall += 1;
    else plate += 1;
  }
  return { wall, plate };
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
    // is fused, and three's raycaster never reads `material.visible` — only
    // `material.side` — so `Mesh.raycast` tests a switched-off body's triangles
    // exactly like a drawn one's (`partView.pickHiddenFaces`), and the band's
    // occlusion test used to measure that hit, so hiding the wall killed edge
    // picking over the whole region it used to cover. No spec covered
    // multi-body + hidden + edge pick, which is why it shipped (SEL-4 review,
    // 2026-08-08).
    const viewport = await openOccludedPlate(page);
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
      await setBodyMode(page, index, "hidden");
      await waitForFrames(page, 4);
      const seen = await probe();
      answered.push([...seen].some((s) => wanted.has(s)));
      await setBodyMode(page, index, "solid");
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

  test("SEL-6 — a hidden body in FRONT no longer eats the pick for the body behind it", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // THE HEADLINE NUMBER. SEL-4's shell pick refused a hidden body's face —
    // correctly — but could only ever REFUSE it: three's raycaster ignores
    // `material.visible`, r3f keeps ONE hit per object, so the nearest triangle
    // was the hidden wall's and the DRAWN plate behind it was never offered.
    // Measured on this fixture before the fix: 8.5 % of the plate's lit pixels
    // could address a face with the wall hidden, against 98 % with both bodies
    // drawn — i.e. hiding the thing in your way, which is the whole reason to
    // hide it, took the pick with it, and it did so BELOW the >= 50 % floor
    // SEL-4 itself establishes for this overlay a few tests above.
    const viewport = await openOccludedPlate(page);

    // WHICH ROW IS THE WALL, discovered rather than assumed — a kernel ordinal
    // is not a contract. See `litAfterHiding`.
    const litWithout = [
      await litAfterHiding(page, 0),
      await litAfterHiding(page, 1),
    ];
    const wall = (litWithout[0] as number) < (litWithout[1] as number) ? 0 : 1;
    const plate = 1 - wall;
    expect(
      Math.max(...litWithout) / Math.max(1, Math.min(...litWithout)),
      `the two bodies must be tellable apart by silhouette: ${litWithout.join(" vs ")} lit points`,
    ).toBeGreaterThan(1.5);

    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    /** The FB-3/FB-5 census, over whatever is currently lit. */
    const census = async () => {
      const points = await litPoints(page, { step: 24 });
      return measureReachabilityWith(points, async (point) => {
        await page.mouse.move(point.x, point.y);
        return (await viewport.getAttribute("data-shell-face-hover")) !== null;
      });
    };
    const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

    const bothDrawn = await census();
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const wallHidden = await census();
    await setBodyMode(page, wall, "solid");
    await waitForFrames(page, 6);
    await setBodyMode(page, plate, "hidden");
    await waitForFrames(page, 6);
    const plateHidden = await census();
    await setBodyMode(page, plate, "solid");
    await waitForFrames(page, 6);

    const report =
      `both drawn ${bothDrawn.reachable}/${bothDrawn.sampled} = ${pct(bothDrawn.fraction)}; ` +
      `WALL (row ${wall}) hidden ${wallHidden.reachable}/${wallHidden.sampled} = ${pct(wallHidden.fraction)}; ` +
      `plate (row ${plate}) hidden ${plateHidden.reachable}/${plateHidden.sampled} = ${pct(plateHidden.fraction)}`;

    for (const leg of [bothDrawn, wallHidden, plateHidden]) {
      expect(leg.sampled, `body sampled (${report})`).toBeGreaterThan(40);
    }

    // NON-VACUITY: a stamp that got stuck set would score every leg at 100 %.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-shell-face-hover", /.*/, {
      timeout: 5_000,
    });

    // The two CONTROLS first, so a regression in either is not mistaken for the
    // claim: nothing about hiding a body behind, or hiding nothing at all,
    // should move the number.
    expect(
      bothDrawn.fraction,
      `control, both drawn (${report})`,
    ).toBeGreaterThanOrEqual(0.5);
    expect(
      plateHidden.fraction,
      `control, the body BEHIND hidden (${report})`,
    ).toBeGreaterThanOrEqual(0.5);

    // THE CLAIM, against the same floor SEL-4 set at `pick-affordance.spec.ts`'s
    // shell census: with the occluder switched off, the body you switched it off
    // to reach is a pick target. Measured 8.5 % before the fix.
    expect(
      wallHidden.fraction,
      `the WALL is hidden and the plate behind it must be pickable — ${report}`,
    ).toBeGreaterThanOrEqual(0.5);
  });

  test("SEL-6 — and the occlusion test still applies BEHIND a hidden body", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // THE OPPOSITE FACE OF THE SAME BUG, and the reason this fix is not "delete
    // the occlusion test". While a hidden wall was the nearest surface hit,
    // `edgeBand` discarded it and left `surfaceDistance` null — so BEHIND a
    // hidden body every edge was accepted, including edges buried inside the
    // still-DRAWN plate. Both faces close together, because the hidden
    // triangle now never reaches the intersection list at all.
    const viewport = await openOccludedPlate(page);
    const litWithout = [
      await litAfterHiding(page, 0),
      await litAfterHiding(page, 1),
    ];
    const wall = (litWithout[0] as number) < (litWithout[1] as number) ? 0 : 1;
    expect(
      Math.max(...litWithout) / Math.max(1, Math.min(...litWithout)),
      `the two bodies must be tellable apart by silhouette: ${litWithout.join(" vs ")} lit points`,
    ).toBeGreaterThan(1.5);

    await armFilletPick(page);

    /**
     * The plate's BACK-BOTTOM edge and its visible y = 30 twin, named by their
     * own OCCT mid-spans rather than by kernel indices.
     *
     * That edge is the one entity of this fixture that is unambiguously INSIDE
     * the solid from the front: the plate's underside faces away from the
     * camera, and under perspective the far edge projects ~29 px ABOVE its near
     * twin — outside the 12 px corridor, so IT and not the visible edge is the
     * nearest band hit on its own line. A probe there is a probe on material
     * you cannot see, with drawn plate in the way.
     */
    const buriedPair = async () => {
      const marks = await edgeMarks(page);
      const buried = marks.find((m) => /centred at 30, 50, 0 /.test(m.label));
      const twin = marks.find((m) => /centred at 30, 30, 0 /.test(m.label));
      expect(
        buried,
        `the plate's back-bottom edge is on offer (${marks.map((m) => m.label).join(" | ")})`,
      ).toBeDefined();
      expect(twin, "its visible y = 30 twin is on offer too").toBeDefined();
      if (buried === undefined || twin === undefined) {
        throw new Error("the plate's bottom edges are not on offer");
      }
      expect(
        Math.abs(buried.centre.y - twin.centre.y),
        "the twins must be further apart than the 12 px corridor, or this probe measures the VISIBLE edge",
      ).toBeGreaterThan(EDGE_CORRIDOR_PX);
      return { marks, buried };
    };

    /** Which edges answer along a mark's own line, clear of its 24 px mark. */
    const probe = async (mark: EdgeMark): Promise<Set<string>> => {
      const seen = new Set<string>();
      for (const dx of [-45, -30, -18, 18, 30, 45]) {
        await page.mouse.move(mark.centre.x + dx, mark.centre.y);
        const stamped = await viewport.getAttribute("data-edge-pick-hover");
        if (stamped !== null) seen.add(stamped);
      }
      return seen;
    };

    // 1) BOTH BODIES DRAWN — refused, which is the pre-existing behaviour.
    const drawn = await buriedPair();
    const drawnSeen = await probe(drawn.buried);
    expect(
      [...drawnSeen],
      `an edge inside the solid must not answer with both bodies drawn (answered: ${[...drawnSeen].join(",") || "nothing"})`,
    ).not.toContain(String(drawn.buried.index));

    // 2) WALL HIDDEN — the case that regressed. The plate is still drawn and
    //    the edge is still buried inside it, so the answer must not change.
    //    Before the fix it DID: the hidden wall's hit was discarded,
    //    `surfaceDistance` stayed null, and the buried edge answered.
    //
    //    The marks are RE-READ rather than reused: the framing follows the
    //    visible bounds, so hiding the wall moves every mark on screen (~29 px
    //    here) and a stale coordinate would probe empty space.
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const behind = await buriedPair();
    const behindSeen = await probe(behind.buried);
    expect(
      [...behindSeen],
      `hiding the wall must not make the plate transparent (answered: ${[...behindSeen].join(",") || "nothing"})`,
    ).not.toContain(String(behind.buried.index));

    // …AND THE FIX IS NOT "REFUSE EVERYTHING". The plate's own VISIBLE top edge
    // answers over the span the hidden wall used to cover — the claim of the
    // census above, stated on the edge overlay, and the non-vacuity guard for
    // the two refusals: a dead stamp would satisfy both of them.
    const topFront = behind.marks.find((m) =>
      /centred at 30, 30, 10 /.test(m.label),
    );
    expect(
      topFront,
      "the plate's visible front-top edge is on offer",
    ).toBeDefined();
    if (topFront === undefined) return;
    const live = await probe(topFront);
    expect(
      [...live],
      `the visible top edge over the hidden wall's span (answered: ${[...live].join(",") || "nothing"})`,
    ).toContain(String(topFront.index));

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("SEL-6 — the default face hover sees past a hidden body too", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // `ModelMesh`'s own face-grain hover (SEL-1 A1) had the same defect on the
    // same mechanism: the nearest triangle won even when its body was switched
    // off, so `data-hovered-face` went silent over the region the wall covered
    // instead of naming the plate's face behind it.
    const viewport = await openOccludedPlate(page);
    const litWithout = [
      await litAfterHiding(page, 0),
      await litAfterHiding(page, 1),
    ];
    const wall = (litWithout[0] as number) < (litWithout[1] as number) ? 0 : 1;

    // Where the wall DRAWS today — the region whose picks it used to eat.
    const covered = await litPoints(page, { step: 24 });
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const stillLit = await litPoints(page, { step: 24 });
    const litKeys = new Set(
      stillLit.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`),
    );
    const nowEmpty = covered.filter(
      (p) => !litKeys.has(`${Math.round(p.x)},${Math.round(p.y)}`),
    );
    expect(stillLit.length, "the plate is still on screen").toBeGreaterThan(20);
    expect(
      nowEmpty.length,
      "the wall really did cover part of the frame",
    ).toBeGreaterThan(20);

    const answered = await measureReachabilityWith(stillLit, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-hovered-face")) !== null;
    });
    const ghost = await measureReachabilityWith(nowEmpty, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-hovered-face")) !== null;
    });

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-hovered-face", /.*/, {
      timeout: 5_000,
    });

    // The drawn plate names a face…
    expect(
      answered.fraction,
      `hovered faces over the still-drawn plate: ${answered.reachable}/${answered.sampled}`,
    ).toBeGreaterThanOrEqual(0.5);
    // …and the vacated region names nothing, which is the guard that seeing
    // PAST the hidden body did not make it pickable.
    expect(
      ghost.reachable,
      `points over the vacated region that still name a face: ${ghost.reachable}/${ghost.sampled}`,
    ).toBe(0);
  });

  test("SEL-6 — a hidden body stops OFFERING picks, not only eating them", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // THE MIRROR HALF, and the gap the first SEL-6 pass left open (review,
    // 2026-08-08). `/overlay` describes the WHOLE part with no notion of
    // visibility, so a switched-off body kept every one of its entities on
    // offer: its edges hoverable and clickable through the full 24 px
    // `EdgeBandLayer` corridor (a 24 px dot before SEL-4 widened it), its faces
    // selectable through their centroid marks, and a brass `FacePatch` painted
    // over the empty space where the body used to be. The previous gate here
    // hid the plate and asserted only that the WALL still occludes — it never
    // asked whether the hidden plate had left the offer.
    const viewport = await openOccludedPlate(page);

    // The lit silhouette with BOTH bodies drawn, captured before anything is
    // armed: the region the wall covers is where its entities live on screen.
    const covered = await litPoints(page, { step: 24 });

    await armFilletPick(page);
    const both = await splitEdgeMarks(page);
    expect(
      [both.wall.length, both.plate.length],
      `both bodies' edges are on offer (${both.marks.map((m) => m.label).join(" | ")})`,
    ).toEqual([12, 12]);

    // WHICH ROW IS THE WALL, discovered rather than assumed — a kernel ordinal
    // is not a contract. Hiding one body must remove exactly ITS edges from
    // the offer and leave the other's untouched, so the two rows answer
    // symmetrically and neither ordering needs to be known in advance.
    const afterHiding: { wall: number; plate: number }[] = [];
    for (const row of [0, 1]) {
      await setBodyMode(page, row, "hidden");
      await waitForFrames(page, 6);
      const split = await splitEdgeMarks(page);
      afterHiding.push({ wall: split.wall.length, plate: split.plate.length });
      await setBodyMode(page, row, "solid");
      await waitForFrames(page, 6);
    }
    const report = afterHiding
      .map((r, i) => `row ${i}: ${r.wall} wall + ${r.plate} plate edges`)
      .join("; ");
    // Before the fix BOTH rows read "12 wall + 12 plate" — hiding a body
    // removed nothing from the offer.
    expect(
      afterHiding.map((r) => `${r.wall}/${r.plate}`).sort(),
      `exactly the hidden body's edges leave the offer (${report})`,
    ).toEqual(["0/12", "12/0"]);
    const wall = afterHiding[0]?.wall === 0 ? 0 : 1;

    // …AND THE CORRIDOR GOES WITH THEM. A mark can be gone from the DOM while
    // the band still answers along the edge, which is the half SEL-4 made
    // bigger: the sweep is over the region the wall VACATED, and no probe
    // there may report an edge the wall owned. Plate edges may legitimately
    // answer here — their corridor is 12 px wide and the bodies are close — so
    // the assertion names the wall's indices rather than demanding silence.
    const wallEdges = new Set(both.wall.map((m) => String(m.index)));
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const stillLit = await litPoints(page, { step: 24 });
    const litKeys = new Set(
      stillLit.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`),
    );
    const nowEmpty = covered.filter(
      (p) => !litKeys.has(`${Math.round(p.x)},${Math.round(p.y)}`),
    );
    expect(
      nowEmpty.length,
      "the wall really did cover part of the frame",
    ).toBeGreaterThan(20);
    const stamped = new Set<string>();
    for (const point of nowEmpty) {
      await page.mouse.move(point.x, point.y);
      const value = await viewport.getAttribute("data-edge-pick-hover");
      if (value !== null) stamped.add(value);
    }
    expect(
      [...stamped].filter((s) => wallEdges.has(s)),
      `edges of the hidden wall still answering over the space it vacated (all stamps: ${[...stamped].join(",") || "none"})`,
    ).toEqual([]);

    // NON-VACUITY, two ways: the stamp clears off the body (so the sweep was
    // not reading a dead attribute), and showing the wall again brings its 12
    // edges back — the filter is a view of the state, not a one-way sink.
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
    await setBodyMode(page, wall, "solid");
    await waitForFrames(page, 6);
    const restored = await splitEdgeMarks(page);
    expect(
      [restored.wall.length, restored.plate.length],
      "showing the body puts its edges back on offer",
    ).toEqual([12, 12]);

    // THE FACE HALF, on the overlay whose only DOM target is a centroid mark.
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("new-shell")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    const facesDrawn = await splitFaceMarks(page);
    expect(
      [facesDrawn.wall, facesDrawn.plate],
      "both bodies' faces are on offer",
    ).toEqual([6, 6]);
    await setBodyMode(page, wall, "hidden");
    await waitForFrames(page, 6);
    const facesHidden = await splitFaceMarks(page);
    expect(
      [facesHidden.wall, facesHidden.plate],
      `the hidden body's faces leave the offer (${facesHidden.wall} wall + ${facesHidden.plate} plate)`,
    ).toEqual([0, 6]);
    await setBodyMode(page, wall, "solid");
    await waitForFrames(page, 6);
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
