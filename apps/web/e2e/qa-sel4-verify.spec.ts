import { expect, test, type Page } from "./fixtures";

import { setupTwoInstances } from "./assemblyFlow";
import {
  createFeature,
  seedDenseHolePlate,
  seedOccludedEdgePlate,
} from "./partSeed";
import {
  clearOfSilhouette,
  litPoints,
  measureReachabilityWith,
  type Point,
} from "./reachability";
import {
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * SEL-4 QA VERIFICATION — the CHECKS the shipped `pick-affordance.spec.ts` does
 * not express. Written by qa-tester, independent of the builder.
 *
 * `pick-affordance.spec.ts` covers the fillet-edge anisotropy, the shell face
 * census, the measure vertex/edge precedence pair, the hidden-body occlusion
 * fix, the hole free-placement, and the mate census. It does NOT cover: the
 * DRAFT editor's half of the shared face overlay, the shell REFUSALS (non-planar
 * and hidden-body), the seven-distinct-ordinal claim on the bolt circle, the
 * sketch-on-face census on the dense fixture A2 actually names, the hole snap's
 * FULL PRECISION and its nearest-bore resolution, the `recede` rider, keyboard/
 * SR parity, and the unmount half of the stamp contract. Those are here.
 */

const DENSE = "Bolt circle plate";

async function openDensePlate(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, DENSE);
  await seedDenseHolePlate(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(24);
  const viewport = page.getByTestId("viewport");
  await viewport.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
}

/** Print a measured number into the run log — QA evidence, not narration. */
function report(label: string, value: string): void {
  console.log(`    [SEL-4 QA] ${label}: ${value}`);
}

/** Rest opacity of a PickNode's reticle — 60 % where the mark has receded. */
async function reticleOpacity(page: Page, testId: string): Promise<string> {
  return page
    .getByTestId(testId)
    .locator("span")
    .first()
    .evaluate((node) => getComputedStyle(node).opacity);
}

/**
 * Move the pointer and read the stamp ONCE IT HAS SETTLED.
 *
 * `page.mouse.move` resolves when the CDP event is dispatched, not when React
 * has re-rendered and the stamp effect has run, so a bare read returns the
 * PREVIOUS point's answer. In a census that is noise that averages out; for a
 * single-point decision it is a wrong answer, and it reads exactly like an app
 * bug — a first probe of this spec "found" a point the hole overlay refused on
 * hover and accepted on click, which was this race and not the overlay.
 */
async function stampAfterMove(
  page: Page,
  point: Point,
  attribute: string,
): Promise<string | null> {
  const viewport = page.getByTestId("viewport");
  await page.mouse.move(point.x, point.y);
  let last = await viewport.getAttribute(attribute);
  // Two agreeing reads across a rendered frame: the effect has flushed.
  for (let i = 0; i < 5; i += 1) {
    await waitForFrames(page, 1);
    const next = await viewport.getAttribute(attribute);
    if (next === last) return next;
    last = next;
  }
  return last;
}

test.describe("SEL-4 QA — shell and draft refusals, and the draft half", () => {
  test("draft: the shared overlay's OTHER prefix is a surface pick too", async ({
    page,
  }) => {
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");

    await expect(page.getByTestId("new-draft")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-draft").click();
    await expect(page.getByTestId("draft-editor")).toBeVisible();
    // Draft needs a neutral plane before its face pick arms.
    await page.getByTestId("draft-angle").fill("5");
    await expect(
      page.locator('[data-testid^="draft-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

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
    report(
      "draft face reachability",
      `${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    );
    expect(
      measured.fraction,
      `draft faces clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);
  });

  test("shell: a far-from-centroid click TOGGLES the face, and the patch follows the hover", async ({
    page,
  }) => {
    await openDensePlate(page);
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill("2");
    const marks = page.locator('[data-testid^="shell-face-"]');
    await expect(marks.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    // A point on SOME face, at least 60 px from every shell mark — the "not
    // just within 24 px of its centroid" half of A2, stated as a click.
    const boxes = (
      await Promise.all((await marks.all()).map((n) => n.boundingBox()))
    ).flatMap((b) => (b === null ? [] : [b]));
    const points = await litPoints(page, { step: 12 });
    let far: { point: Point; ordinal: string } | null = null;
    for (const point of points) {
      const clear = boxes.every(
        (b) =>
          point.x < b.x - 60 ||
          point.x > b.x + b.width + 60 ||
          point.y < b.y - 60 ||
          point.y > b.y + b.height + 60,
      );
      if (!clear) continue;
      const ordinal = await stampAfterMove(
        page,
        point,
        "data-shell-face-hover",
      );
      if (ordinal === null) continue;
      far = { point, ordinal };
      break;
    }
    expect(far, "a hovered point ≥60 px from every shell mark").not.toBeNull();
    if (far === null) return;

    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
    );
    await page.mouse.click(far.point.x, far.point.y);
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
    );
    // The mark for THAT ordinal is the one that went selected — the pick
    // resolved the face under the cursor, not a neighbour.
    await expect(page.getByTestId(`shell-face-${far.ordinal}`)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("shell: a NON-PLANAR face is refused, not snapped to its neighbour", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    // A CYLINDER, not the bolt-circle plate, and the reason is measured. On
    // the dense plate a Ø6 through bore's visible wall is a sliver: of 40
    // sampled wall pixels, ZERO had all four ±3 px neighbours still on the
    // same face, so every sample was a rim pixel and the check could only ever
    // have measured tessellation noise between the drawn mesh and the pick
    // mesh. A Ø40 × 20 cylinder puts a large, unambiguous non-planar face on
    // screen, which is what the claim needs.
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Shell cylinder");
    const sketch = await createFeature(page, account.token, part.id, {
      name: "Disc",
      feature: {
        type: "sketch",
        version: 1,
        params: {
          plane: { kind: "datum_plane", plane: "XY" },
          entities: [
            { id: "c1", kind: "circle", center: { x: 0, y: 0 }, radius: 20 },
          ],
          constraints: [],
        },
      },
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
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
      timeout: 30_000,
    });
    await expect
      .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
      .toBeGreaterThan(24);
    const viewport = page.getByTestId("viewport");
    await viewport.evaluate((node) => {
      node.dataset["fitRect"] = "";
    });
    await page.getByTestId("view-fit").click();
    await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
      timeout: 20_000,
    });
    await waitForFrames(page, 6);

    // GROUND TRUTH from a source that is not the thing under test: `ModelMesh`
    // publishes `data-hovered-face` for EVERY face it raycasts, cylinders
    // included (SEL-1 A1), so an idle sweep says which face each pixel is.
    //
    // The sweep — INCLUDING the interior test — must happen while the viewport
    // is IDLE. `ModelMesh`'s hover is deliberately suppressed the moment an
    // overlay arms (asserted separately in this file), so asking it "what face
    // is this really?" with shell open returns null for every pixel; a first
    // cut did exactly that and reported zero interior pixels on a face that
    // fills a third of the frame.
    const STEP = 12;
    const points = await litPoints(page, { step: STEP });
    const truth = new Map<string, string>();
    for (const point of points) {
      const ordinal = await stampAfterMove(page, point, "data-hovered-face");
      if (ordinal !== null) {
        truth.set(`${Math.round(point.x)},${Math.round(point.y)}`, ordinal);
      }
    }
    expect(truth.size, "points whose true face is known").toBeGreaterThan(50);

    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill("2");
    const marks = page.locator('[data-testid^="shell-face-"]');
    await expect(marks.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);
    const planar = new Set<string>();
    for (const node of await marks.all()) {
      const testId = (await node.getAttribute("data-testid")) ?? "";
      planar.add(testId.replace("shell-face-", ""));
    }
    // A cylinder: two planar caps on offer, and the lateral face is not.
    expect(planar.size, `planar faces on offer: ${[...planar].join(",")}`).toBe(
      2,
    );

    // INTERIOR cylinder pixels: the pixel and all four grid neighbours are the
    // same non-planar face. A rim pixel is ambiguous by construction — the
    // drawn mesh and the pick mesh are separately tessellated, so either side
    // of the boundary triangle is a defensible answer there.
    const walls: { point: Point; ordinal: string }[] = [];
    for (const [key, ordinal] of truth) {
      if (planar.has(ordinal)) continue;
      const [px, py] = key.split(",").map((n) => Number.parseFloat(n));
      const x = px ?? 0;
      const y = py ?? 0;
      const surrounded = (
        [
          [STEP, 0],
          [-STEP, 0],
          [0, STEP],
          [0, -STEP],
        ] as const
      ).every(
        ([dx, dy]) =>
          truth.get(`${Math.round(x + dx)},${Math.round(y + dy)}`) === ordinal,
      );
      if (surrounded) walls.push({ point: { x, y }, ordinal });
    }
    expect(
      walls.length,
      `INTERIOR pixels genuinely on the cylindrical face (of ${truth.size} known)`,
    ).toBeGreaterThan(5);

    const wrong: string[] = [];
    let firstWall: Point | null = null;
    for (const wall of walls.slice(0, 40)) {
      if (firstWall === null) firstWall = wall.point;
      const stamped = await stampAfterMove(
        page,
        wall.point,
        "data-shell-face-hover",
      );
      if (stamped !== null) {
        wrong.push(
          `${wall.point.x},${wall.point.y} is face ${wall.ordinal} -> ${stamped}`,
        );
      }
    }
    report(
      "cylinder wall refusal",
      `${Math.min(walls.length, 40)} interior non-planar pixels probed, ${wrong.length} answered with a planar face`,
    );
    expect(
      wrong.length,
      `interior cylinder pixels the shell pick snapped to a PLANAR neighbour: ${wrong.join(" | ")} (of ${Math.min(walls.length, 40)} probed)`,
    ).toBe(0);

    // …AND NO TOGGLE EITHER. "No hover" would be cold comfort if the click
    // still opened a face nobody addressed.
    expect(firstWall).not.toBeNull();
    if (firstWall === null) return;
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
    );
    await page.mouse.click(firstWall.x, firstWall.y);
    await waitForFrames(page, 4);
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
    );
  });

  test("shell: a HIDDEN body's face is not pickable", async ({ page }) => {
    test.setTimeout(180_000);
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
    await viewport.evaluate((node) => {
      node.dataset["fitRect"] = "";
    });
    await page.getByTestId("view-fit").click();
    await expect(viewport).not.toHaveAttribute("data-fit-rect", "", {
      timeout: 20_000,
    });
    await waitForFrames(page, 6);

    await expect(page.getByTestId("body-row")).toHaveCount(2, {
      timeout: 20_000,
    });
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    const census = async (): Promise<number> => {
      const points = await litPoints(page, { step: 24 });
      let hits = 0;
      for (const point of points) {
        await page.mouse.move(point.x, point.y);
        if ((await viewport.getAttribute("data-shell-face-hover")) !== null) {
          hits += 1;
        }
      }
      return hits;
    };
    const before = await census();
    expect(before, "faces answer with both bodies drawn").toBeGreaterThan(0);

    // Hide body 0. Its ordinals must stop answering; the census over the
    // REMAINING lit silhouette must not include any hidden-body face.
    const row = page.getByTestId("body-row").nth(0);
    for (let i = 0; i < 4; i += 1) {
      if ((await row.getAttribute("data-visibility")) === "hidden") break;
      await page.getByTestId("body-visibility-0").click();
    }
    await expect(row).toHaveAttribute("data-visibility", "hidden");
    await waitForFrames(page, 6);

    // Sweep the FULL canvas, not just the lit silhouette: the hidden body's
    // triangles are still in the fused pick mesh, so if the refusal is missing
    // the pointer picks up faces over empty bench where the body used to draw.
    //
    // INTERIOR unlit points only — the pixel AND its neighbours must be dark.
    // `isLit` is a luminance threshold, and a threshold cannot tell "off the
    // body" from "on the body's anti-aliased silhouette": measured 2026-08-08
    // at (692, 600), luminance **23** two pixels from body at **135**. That
    // pixel is ON the still-drawn plate, so the shell pick naming its face is
    // correct, and counting it as a ghost is the proxy's error, not the app's.
    // It only started mattering with SEL-6: before the fix the hidden wall's
    // triangle swallowed the ray there, so the sweep passed for the wrong
    // reason — the pointer was dead over the drawn plate, which is the defect
    // SEL-6 exists to close. Same reasoning as the cylinder-wall check above,
    // which already refuses to judge rim pixels.
    const box = await viewport.boundingBox();
    expect(box).not.toBeNull();
    if (box === null) return;
    const HALO = 8;
    let ghostHits = 0;
    const ghosts: string[] = [];
    // The grid, then ONE readback to keep the points that are unlit AND clear
    // of the silhouette by HALO. This was a per-point probe nested two deep —
    // one full-frame canvas copy for the point and up to four more for its
    // neighbours, ~1000-2500 copies for a 544-point grid.
    //
    // Stated carefully, because the sibling case in this pass taught it the
    // hard way: removing those copies is NOT what makes this test affordable.
    // Measured elsewhere on 2026-08-29, canvas readbacks were 0.6 % of a test
    // that looked like it was drowning in them, and the real cost is the
    // SEQUENTIAL round trips — here the 523 surviving points each get a
    // `stampAfterMove`. This change is a redundancy removal and a DRY one
    // (`clearOfSilhouette` is the shared form of exactly this halo), not a
    // speed fix; do not credit it with headroom it did not buy.
    //
    // It asks the SAME question (luminance > 110, same HALO) over the whole
    // square rather than four axis samples, so it is strictly stricter: it can
    // only discard more points, never admit one the old code rejected.
    // Measured after: 523-525 points survive, against a floor of 20.
    const grid: Point[] = [];
    for (let y = box.y + 20; y < box.y + box.height - 20; y += 48) {
      for (let x = box.x + 20; x < box.x + box.width - 20; x += 48) {
        grid.push({ x, y });
      }
    }
    const interior = await clearOfSilhouette(page, grid, { marginPx: HALO });
    const unlitProbed = interior.length;
    for (const point of interior) {
      const stamped = await stampAfterMove(
        page,
        point,
        "data-shell-face-hover",
      );
      if (stamped !== null) {
        ghostHits += 1;
        ghosts.push(`${point.x},${point.y}->${stamped}`);
      }
    }
    report(
      "hidden-body ghost picks",
      `${unlitProbed} interior-unlit points probed after hiding a body`,
    );
    expect(unlitProbed, "interior-unlit points probed").toBeGreaterThan(20);
    void ghosts;
    expect(
      ghostHits,
      `unlit points clear of the drawn silhouette that still answer with a face (a hidden body's): ${ghosts.join(" ")}`,
    ).toBe(0);
  });
});

test.describe("SEL-4 QA — the bolt circle resolves seven DISTINCT bores", () => {
  test("seven bores, seven ordinals, no neighbour answers", async ({
    page,
  }) => {
    /*
      180 s, matching this file's other census tests. The default 60 s was never
      sized against what this test does: 14 circular marks x 12 angles x 3 radii
      = 504 SEQUENTIAL pointer moves, each followed by a stamp read. Unlike the
      canvas readbacks elsewhere in this pass, that work cannot be batched away
      — the browser must hit-test each pointer position, and the hit test IS the
      measurement.

      Measured on a 4-core box (CI-4 headroom pass, 2026-08-29): quiet 37.0-56.9
      s across seven runs, and 0 of 7 completing under two CPU spinners, always
      as a bare "Test timeout of 60000ms exceeded". Nothing here is a race that
      can be won — it is 504 round trips whose cost scales with the machine.
    */
    test.setTimeout(180_000);
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");
    await expect(page.getByTestId("new-fillet")).toBeEnabled({
      timeout: 30_000,
    });
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await page.getByTestId("fillet-mode-pick").click();
    const nodes = page.locator('[data-testid^="edge-pick-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    // Every circular edge mark, with the ordinal its own test id names.
    const circles: { index: number; centre: Point }[] = [];
    for (const node of await nodes.all()) {
      const testId = (await node.getAttribute("data-testid")) ?? "";
      const label = (await node.getAttribute("aria-label")) ?? "";
      if (!label.includes("circle")) continue;
      const bbox = await node.boundingBox();
      if (bbox === null) continue;
      circles.push({
        index: Number(testId.replace("edge-pick-", "")),
        centre: { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 },
      });
    }
    // 7 bores × 2 mouths = 14 circular edges.
    expect(circles.length, "circular edges on the bolt circle").toBe(14);

    // Probe AROUND each circle's mark — the bore's own rim, ~20 px out. Record
    // which ordinal answers. A band that became a blanket answers with a
    // neighbour's ordinal here; the fixture is built so neighbours are close.
    const answeredBy = new Map<number, Set<number>>();
    for (const circle of circles) {
      const seen = new Set<number>();
      for (let d = 0; d < 12; d += 1) {
        const angle = (2 * Math.PI * d) / 12;
        for (const radius of [14, 20, 26]) {
          await page.mouse.move(
            circle.centre.x + radius * Math.cos(angle),
            circle.centre.y + radius * Math.sin(angle),
          );
          const stamped = await viewport.getAttribute("data-edge-pick-hover");
          if (stamped !== null) seen.add(Number(stamped));
        }
      }
      answeredBy.set(circle.index, seen);
    }

    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });

    // The claim: probing a bore's rim addresses circular edges, and the seven
    // VISIBLE bores are told apart — at least seven distinct circular ordinals
    // are addressable across the pattern.
    const circleOrdinals = new Set(circles.map((c) => c.index));
    const addressed = new Set<number>();
    for (const seen of answeredBy.values()) {
      for (const index of seen) {
        if (circleOrdinals.has(index)) addressed.add(index);
      }
    }
    report(
      "distinct circular edges addressed from bore rims",
      `${addressed.size} of 14 (${[...addressed].sort((a, b) => a - b).join(",")})`,
    );
    expect(
      addressed.size,
      `distinct circular edges addressed from bore rims: ${[...addressed].sort((a, b) => a - b).join(",")}`,
    ).toBeGreaterThanOrEqual(7);
  });
});

test.describe("SEL-4 QA — A2's literal wording on A2's own fixture", () => {
  test("sketch-on-face: the census on the dense plate, and a BOUNDARY click seats the sketch", async ({
    page,
  }) => {
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");

    await page.getByTestId("new-sketch").click();
    // The plane chooser opens on datum planes; the FACE tab is what arms the
    // face pick this check is about.
    await page.getByTestId("plane-pick-face").click();
    const marks = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(marks.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    const points = await litPoints(page, { step: 24 });
    const measured = await measureReachabilityWith(points, async (point) => {
      await page.mouse.move(point.x, point.y);
      return (await viewport.getAttribute("data-face-pick-hover")) !== null;
    });
    expect(measured.sampled, "body sampled").toBeGreaterThan(40);
    await page.mouse.move(5, 5);
    await expect(viewport).not.toHaveAttribute("data-face-pick-hover", /.*/, {
      timeout: 5_000,
    });
    report(
      "sketch-on-face reachability (dense plate)",
      `${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    );
    expect(
      measured.fraction,
      `sketch-plane faces clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}%`,
    ).toBeGreaterThanOrEqual(0.5);

    // A2 VERBATIM: click near a face's EDGE, far from its centroid. Walk the
    // top face's hovered region outward until the next step stops answering —
    // that point is ON the boundary — then click it and require the sketch to
    // seat on the face that was hovered there.
    const boxes = (
      await Promise.all((await marks.all()).map((n) => n.boundingBox()))
    ).flatMap((b) => (b === null ? [] : [b]));
    const fine = await litPoints(page, { step: 6 });
    let boundary: { point: Point; ordinal: string } | null = null;
    for (const point of fine) {
      // Far from EVERY centroid mark, by A2's own words.
      const far = boxes.every(
        (b) =>
          Math.hypot(
            point.x - (b.x + b.width / 2),
            point.y - (b.y + b.height / 2),
          ) > 70,
      );
      if (!far) continue;
      const ordinal = await stampAfterMove(page, point, "data-face-pick-hover");
      if (ordinal === null) continue;
      // Is it near the face's boundary? Step 6 px in some direction and see
      // whether the same face still answers; if not, this is an edge point.
      let onBoundary = false;
      for (const [dx, dy] of [
        [7, 0],
        [-7, 0],
        [0, 7],
        [0, -7],
      ] as const) {
        const neighbour = await stampAfterMove(
          page,
          { x: point.x + dx, y: point.y + dy },
          "data-face-pick-hover",
        );
        if (neighbour !== ordinal) {
          onBoundary = true;
          break;
        }
      }
      if (!onBoundary) continue;
      boundary = { point, ordinal };
      break;
    }
    expect(
      boundary,
      "a hovered point on a face's boundary, >70 px from every centroid mark",
    ).not.toBeNull();
    if (boundary === null) return;

    await page.mouse.click(boundary.point.x, boundary.point.y);
    // The sketcher opens, seated on the face that was under the cursor.
    await expect(page.getByTestId("sketch-strip")).toBeVisible({
      timeout: 20_000,
    });
  });
});

test.describe("SEL-4 QA — the hole snap is EXACT and picks the nearest bore", () => {
  test("a snapped centre is the nearest bore's, to full precision", async ({
    page,
  }) => {
    await openDensePlate(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

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

    const circles = page.locator('[data-testid^="hole-point-circle-"]');
    await expect(circles.first()).toBeVisible({ timeout: 20_000 });
    expect(
      await circles.count(),
      "one snap ring per bore on the bolt circle",
    ).toBe(7);
    await waitForFrames(page, 4);

    // The bolt circle is Ø40 about (30,30): every bore centre is 20 mm from the
    // face centre, at 2π k/7. The frame's origin is the face centre, so the
    // readout's X/Y must land EXACTLY on one of those seven, and specifically
    // on the one whose mark was clicked — not a neighbour 17.4 mm away.
    // WHERE THE FRAME'S ZERO IS, measured not assumed: the seeded placement is
    // the face CENTRE, so the X/Y cells right now ARE the centre in frame
    // coordinates. Every bore is 20 mm from it on a Ø40 circle, whatever
    // rotation the kernel gave the frame. (A first cut assumed the origin was
    // the centroid; it is the face's own corner, and 50/30 read as a defect.)
    const originX = Number.parseFloat(
      (await page.getByTestId("hole-position-x").inputValue()).replace(
        /,/g,
        "",
      ),
    );
    const originY = Number.parseFloat(
      (await page.getByTestId("hole-position-y").inputValue()).replace(
        /,/g,
        "",
      ),
    );
    expect(Number.isFinite(originX) && Number.isFinite(originY)).toBe(true);

    // Every ring's own accessible name carries its exact OCCT centre. Clicking
    // one must dial THAT centre into the X/Y cells — the check's "full
    // precision, not the raycast point", and "the nearest bore's, never a
    // neighbour's": on a Ø40 circle the neighbours are 17.4 mm away, so a
    // mis-resolved ordinal cannot hide inside a rounding tolerance.
    const centres: { index: number; occt: number[] }[] = [];
    for (let i = 0; i < 7; i += 1) {
      const label = (await circles.nth(i).getAttribute("aria-label")) ?? "";
      const nums = (label.match(/-?\d+(?:\.\d+)?/g) ?? [])
        .slice(-3)
        .map((n) => Number.parseFloat(n));
      centres.push({ index: i, occt: nums });
    }
    // Non-vacuity for the fixture itself: seven DISTINCT centres, all on the
    // Ø40 bolt circle about the face centre (30, 30).
    const radii = centres.map((c) =>
      Math.hypot((c.occt[0] ?? 0) - 30, (c.occt[1] ?? 0) - 30),
    );
    for (const r of radii) expect(r).toBeCloseTo(20, 2);
    expect(
      new Set(centres.map((c) => c.occt.join(","))).size,
      "seven distinct bore centres",
    ).toBe(7);

    for (const index of [0, 3, 6]) {
      // Re-arm ONLY if the previous pick disarmed it — `hole-point-pick` is a
      // TOGGLE, so clicking it while armed unmounts every snap mark.
      if ((await circles.count()) === 0) {
        await page.getByTestId("hole-point-pick").click();
      }
      await expect(circles.nth(index)).toBeVisible({ timeout: 20_000 });
      await circles.nth(index).click();
      const cellX = await page.getByTestId("hole-position-x").inputValue();
      const cellY = await page.getByTestId("hole-position-y").inputValue();
      const fx = Number.parseFloat(cellX.replace(/,/g, ""));
      const fy = Number.parseFloat(cellY.replace(/,/g, ""));
      const wanted = centres[index];
      expect(wanted).toBeDefined();
      if (wanted === undefined) return;

      // The X/Y cells are the face-frame coordinates of the clicked centre.
      // The frame's rotation is the kernel's business, so assert the two
      // invariants that pin the POINT regardless of it: the radius from the
      // frame origin, and the fact that no OTHER bore shares that radius+angle.
      expect(
        Math.hypot(fx - originX, fy - originY),
        `bore ${index}: X/Y cells "${cellX}", "${cellY}" against the face centre (${originX}, ${originY})`,
      ).toBeCloseTo(20, 3);

      // …and the world readout is that bore's own centre, not a neighbour's.
      const readout = await page.getByTestId("hole-position").innerText();
      const got = (readout.match(/-?\d+(?:\.\d+)?/g) ?? []).map((n) =>
        Number.parseFloat(n),
      );
      const distances = centres.map((c) =>
        Math.hypot(
          (got[0] ?? 0) - (c.occt[0] ?? 0),
          (got[1] ?? 0) - (c.occt[1] ?? 0),
        ),
      );
      let nearest = 0;
      distances.forEach((d, i) => {
        if (d < (distances[nearest] as number)) nearest = i;
      });
      expect(
        nearest,
        `clicked bore ${index}, readout "${readout}" is nearest to bore ${nearest} (distances ${distances.map((d) => d.toFixed(2)).join(",")})`,
      ).toBe(index);
    }
  });

  test("a click on a DIFFERENT face does not move the drill point", async ({
    page,
  }) => {
    await openDensePlate(page);
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

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
    const placementLabel =
      (await all[topIndex]?.getAttribute("aria-label")) ?? "";
    await all[topIndex]?.click();
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await waitForFrames(page, 4);

    const seeded = await page.getByTestId("hole-position").innerText();

    // Find a lit point where the placement overlay does NOT answer — i.e. a
    // point on some OTHER face of the plate — and click it. The drill point
    // must be unchanged: a raycast that resolved "any face" would move it.
    const points = await litPoints(page, { step: 10 });
    let other: Point | null = null;
    for (const point of points) {
      if (
        (await stampAfterMove(page, point, "data-hole-point-hover")) !== null
      ) {
        continue;
      }
      // Confirm it is on the BODY (lit) and not on a DOM mark.
      const onMark = await page.evaluate(
        ({ x, y }) =>
          document
            .elementFromPoint(x, y)
            ?.closest("[data-testid]")
            ?.getAttribute("data-testid")
            ?.startsWith("hole-point-") ?? false,
        point,
      );
      if (onMark) continue;
      other = point;
      break;
    }
    expect(
      other,
      `a lit point off the placement face (placement = "${placementLabel}")`,
    ).not.toBeNull();
    if (other === null) return;

    await page.mouse.click(other.x, other.y);
    await waitForFrames(page, 4);
    await expect(page.getByTestId("hole-position")).toHaveText(seeded);
  });
});

test.describe("SEL-4 QA — the recede rider, stated per overlay", () => {
  test("every CONVERTED mark rests at 60 %, and returns on hover and focus", async ({
    page,
  }) => {
    await openDensePlate(page);

    // (a) fillet edge marks
    await page.getByTestId("new-fillet").click();
    await page.getByTestId("fillet-mode-pick").click();
    const edge = page.locator('[data-testid^="edge-pick-"]').first();
    await expect(edge).toBeVisible({ timeout: 20_000 });
    const edgeId = (await edge.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, edgeId), "edge mark rests").toBe("0.6");
    await edge.hover();
    await expect
      .poll(() => reticleOpacity(page, edgeId), { timeout: 5_000 })
      .toBe("1");
    // FOCUS. `:focus-visible` is modality-dependent in Chromium, so establish
    // the keyboard modality first — a bare programmatic `focus()` after a mouse
    // hover does NOT match it, which is browser behaviour and not an app bug.
    await page.mouse.move(5, 5);
    await page.keyboard.press("Tab");
    await edge.focus();
    await expect
      .poll(() => reticleOpacity(page, edgeId), { timeout: 5_000 })
      .toBe("1");
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("fillet-editor")).toBeHidden();

    // (b) shell face marks
    await page.getByTestId("new-shell").click();
    const shell = page.locator('[data-testid^="shell-face-"]').first();
    await expect(shell).toBeVisible({ timeout: 20_000 });
    const shellId = (await shell.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, shellId), "shell mark rests").toBe("0.6");
    await page.getByTestId("shell-cancel").click();
    await expect(page.getByTestId("shell-editor")).toBeHidden();

    // (c) draft face marks — the same overlay under its other prefix
    await page.getByTestId("new-draft").click();
    await page.getByTestId("draft-angle").fill("5");
    const draft = page.locator('[data-testid^="draft-face-"]').first();
    await expect(draft).toBeVisible({ timeout: 20_000 });
    const draftId = (await draft.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, draftId), "draft mark rests").toBe("0.6");
    await page.getByTestId("draft-cancel").click();
    await expect(page.getByTestId("draft-editor")).toBeHidden();

    // (d) hole placement marks — centre, corners and bore rings
    await page.getByTestId("new-hole").click();
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
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    // The seeded placement IS the face centre, so that one mark is `selected`
    // and correctly at full strength. A bore ring is the unselected case.
    const ring = page.locator('[data-testid^="hole-point-circle-"]').first();
    const ringId = (await ring.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, ringId), "bore ring rests").toBe("0.6");
    await page.getByTestId("hole-cancel").click();
    await expect(page.getByTestId("hole-editor")).toBeHidden();

    // (e) MEASURE: edges recede, VERTICES DELIBERATELY DO NOT. A later blanket
    // recede would dim the only hit-test a projected point has.
    await expect(page.getByTestId("measure-tool")).toBeEnabled({
      timeout: 20_000,
    });
    await page.getByTestId("measure-tool").click();
    const mEdge = page.locator('[data-testid^="measure-edge-"]').first();
    await expect(mEdge).toBeVisible({ timeout: 20_000 });
    const mEdgeId = (await mEdge.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, mEdgeId), "measure edge rests").toBe(
      "0.6",
    );
    const mVertex = page.locator('[data-testid^="measure-vertex-"]').first();
    await expect(mVertex).toBeVisible({ timeout: 20_000 });
    const mVertexId = (await mVertex.getAttribute("data-testid")) ?? "";
    expect(
      await reticleOpacity(page, mVertexId),
      "measure VERTEX must NOT recede — it is still its own sole hit-test",
    ).toBe("1");
  });

  test("assembly mate marks recede too", async ({ page }) => {
    await setupTwoInstances(page);
    await page.getByTestId("mate-coincident").click();
    const face = page.locator('[data-testid^="mate-face-"]').first();
    await expect(face).toBeVisible({ timeout: 20_000 });
    const faceId = (await face.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, faceId), "mate face mark rests").toBe(
      "0.6",
    );

    await page.getByTestId("mate-concentric").click();
    const axis = page.locator('[data-testid^="mate-axis-"]').first();
    await expect(axis).toBeVisible({ timeout: 20_000 });
    const axisId = (await axis.getAttribute("data-testid")) ?? "";
    expect(await reticleOpacity(page, axisId), "mate axis mark rests").toBe(
      "0.6",
    );
  });
});

test.describe("SEL-4 QA — keyboard/SR parity and the stamp contract", () => {
  test("a converted mark is Tab-reachable and FOCUS fires the same hover", async ({
    page,
  }) => {
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");
    await page.getByTestId("new-shell").click();
    const shell = page.locator('[data-testid^="shell-face-"]').first();
    await expect(shell).toBeVisible({ timeout: 20_000 });
    const shellId = (await shell.getAttribute("data-testid")) ?? "";
    const ordinal = shellId.replace("shell-face-", "");

    // Accessible name preserved (spec §5).
    await expect(shell).toHaveAttribute("aria-label", /face/i);

    // FOCUS fires the same hover a pointer would — the keyboard user gets the
    // same preview, which is what makes the mark a real fallback.
    await shell.focus();
    await expect(viewport).toHaveAttribute("data-shell-face-hover", ordinal, {
      timeout: 5_000,
    });
    await shell.blur();
    await expect(viewport).not.toHaveAttribute("data-shell-face-hover", /.*/, {
      timeout: 5_000,
    });

    // …and it is genuinely in the tab order.
    const reachable = await shell.evaluate(
      (node) => node.tabIndex >= 0 && !(node as HTMLButtonElement).disabled,
    );
    expect(reachable, "the mark is Tab-reachable").toBe(true);
  });

  test("every stamp is ABSENT once its overlay unmounts", async ({ page }) => {
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");

    await page.getByTestId("new-shell").click();
    const shell = page.locator('[data-testid^="shell-face-"]').first();
    await expect(shell).toBeVisible({ timeout: 20_000 });
    await shell.hover();
    await expect(viewport).toHaveAttribute("data-shell-face-hover", /\d/, {
      timeout: 5_000,
    });
    // Close the editor: the overlay unmounts with the stamp still SET, which is
    // the case the cleanup exists for — without it the census scores 100 % on a
    // body that is not being picked at all.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("shell-editor")).toBeHidden();
    await expect(viewport).not.toHaveAttribute("data-shell-face-hover", /.*/, {
      timeout: 5_000,
    });

    await page.getByTestId("new-fillet").click();
    await page.getByTestId("fillet-mode-pick").click();
    const edge = page.locator('[data-testid^="edge-pick-"]').first();
    await expect(edge).toBeVisible({ timeout: 20_000 });
    await edge.hover();
    await expect(viewport).toHaveAttribute("data-edge-pick-hover", /\d/, {
      timeout: 5_000,
    });
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("fillet-editor")).toBeHidden();
    await expect(viewport).not.toHaveAttribute("data-edge-pick-hover", /.*/, {
      timeout: 5_000,
    });
  });

  test("ModelMesh's own face hover stays quiet while a pick is armed", async ({
    page,
  }) => {
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");
    const points = await litPoints(page, { step: 40 });
    const some = points[Math.floor(points.length / 2)];
    expect(some).toBeDefined();
    if (some === undefined) return;

    // Idle: the model's own hover answers (SEL-1 A1 — the pointer says which
    // FACE, not which solid).
    await page.mouse.move(some.x, some.y);
    const idle = await viewport.getAttribute("data-hovered-face");

    await page.getByTestId("new-shell").click();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);
    await page.mouse.move(some.x + 1, some.y + 1);
    await page.mouse.move(some.x, some.y);
    const armed = await viewport.getAttribute("data-hovered-face");
    expect(
      armed,
      `ModelMesh hover while shell is armed (idle was ${String(idle)})`,
    ).toBeNull();
  });
});

test.describe("SEL-4 QA — the mount audit", () => {
  test("exactly ONE armed pick answers at a time", async ({ page }) => {
    // The perf half of the rider, stated the only way the DOM can state it: a
    // second `PickSurface` in the scene would show up as a second overlay
    // answering the same pointer. Each armed editor must own the pointer
    // alone, and the ones that are not armed must be silent.
    await openDensePlate(page);
    const viewport = page.getByTestId("viewport");
    const stamps = [
      "data-face-pick-hover",
      "data-shell-face-hover",
      "data-edge-pick-hover",
      "data-measure-edge-hover",
      "data-hole-point-hover",
    ] as const;

    const answering = async (point: Point): Promise<string[]> => {
      await page.mouse.move(point.x, point.y);
      await waitForFrames(page, 2);
      const live: string[] = [];
      for (const stamp of stamps) {
        if ((await viewport.getAttribute(stamp)) !== null) live.push(stamp);
      }
      return live;
    };

    const points = await litPoints(page, { step: 24 });
    const probe = points[Math.floor(points.length / 2)];
    expect(probe).toBeDefined();
    if (probe === undefined) return;

    // Idle: nothing armed, nothing answers.
    expect(await answering(probe), "idle").toEqual([]);

    // Shell armed: the shell face pick, and only it.
    await page.getByTestId("new-shell").click();
    await expect(
      page.locator('[data-testid^="shell-face-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);
    expect(await answering(probe), "shell armed").toEqual([
      "data-shell-face-hover",
    ]);
    await page.getByTestId("shell-cancel").click();
    await expect(page.getByTestId("shell-editor")).toBeHidden();

    // Fillet armed: the edge pick, and only it. (Measure shares the band
    // implementation, so a stray mount would show up here.)
    await page.getByTestId("new-fillet").click();
    await page.getByTestId("fillet-mode-pick").click();
    await expect(
      page.locator('[data-testid^="edge-pick-"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);
    const filletLive = await answering(probe);
    expect(
      filletLive.filter((s) => s !== "data-edge-pick-hover"),
      `fillet armed also lit: ${filletLive.join(",")}`,
    ).toEqual([]);
    await page.getByTestId("fillet-cancel").click();
    await expect(page.getByTestId("fillet-editor")).toBeHidden();

    // The hole editor's two steps hand the pointer over rather than sharing
    // it: the FACE pick answers while it is armed, the POINT pick after.
    await page.getByTestId("new-hole").click();
    const faces = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(faces.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);
    expect(await answering(probe), "hole FACE step").toEqual([
      "data-face-pick-hover",
    ]);

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
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await waitForFrames(page, 4);
    const pointLive = await answering(probe);
    expect(
      pointLive.includes("data-face-pick-hover"),
      `hole POINT step still runs the FACE pick: ${pointLive.join(",")}`,
    ).toBe(false);
  });
});

test.describe("SEL-4 QA — TOUCH", () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 768 } });

  test("a tap on the drawn face toggles the shell face, off any mark", async ({
    page,
  }) => {
    await openDensePlate(page);
    await page.getByTestId("new-shell").click();
    await expect(page.getByTestId("shell-editor")).toBeVisible();
    await page.getByTestId("shell-thickness").fill("2");
    const marks = page.locator('[data-testid^="shell-face-"]');
    await expect(marks.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 6);

    const boxes = (
      await Promise.all((await marks.all()).map((n) => n.boundingBox()))
    ).flatMap((b) => (b === null ? [] : [b]));
    const points = await litPoints(page, { step: 12 });
    let far: Point | null = null;
    for (const point of points) {
      const clear = boxes.every(
        (b) =>
          point.x < b.x - 50 ||
          point.x > b.x + b.width + 50 ||
          point.y < b.y - 50 ||
          point.y > b.y + b.height + 50,
      );
      if (!clear) continue;
      if (
        (await stampAfterMove(page, point, "data-shell-face-hover")) === null
      ) {
        continue;
      }
      far = point;
      break;
    }
    expect(far, "a face point ≥50 px from every mark").not.toBeNull();
    if (far === null) return;

    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
    );
    await page.touchscreen.tap(far.x, far.y);
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
      { timeout: 10_000 },
    );
  });

  test("a tap along an edge picks it for a fillet, off the diamond", async ({
    page,
  }) => {
    await openDensePlate(page);
    await page.getByTestId("new-fillet").click();
    await expect(page.getByTestId("fillet-editor")).toBeVisible();
    await page.getByTestId("fillet-mode-pick").click();
    const nodes = page.locator('[data-testid^="edge-pick-"]');
    await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
    await waitForFrames(page, 4);

    // Find a LINE edge and a point ≥40 px along it from its own diamond.
    let hit: { index: string; point: Point } | null = null;
    for (const node of await nodes.all()) {
      const label = (await node.getAttribute("aria-label")) ?? "";
      if (!label.includes("line")) continue;
      const testId = (await node.getAttribute("data-testid")) ?? "";
      const index = testId.replace("edge-pick-", "");
      const box = await node.boundingBox();
      if (box === null) continue;
      const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      for (let d = 0; d < 16 && hit === null; d += 1) {
        const angle = (2 * Math.PI * d) / 16;
        const point = {
          x: centre.x + 44 * Math.cos(angle),
          y: centre.y + 44 * Math.sin(angle),
        };
        if (
          (await stampAfterMove(page, point, "data-edge-pick-hover")) === index
        ) {
          hit = { index, point };
        }
      }
      if (hit !== null) break;
    }
    expect(
      hit,
      "a line edge addressable 44 px from its own mark",
    ).not.toBeNull();
    if (hit === null) return;

    await page.touchscreen.tap(hit.point.x, hit.point.y);
    await expect(page.getByTestId("selected-count")).toHaveText(
      "1 edge picked",
      { timeout: 10_000 },
    );
  });
});
