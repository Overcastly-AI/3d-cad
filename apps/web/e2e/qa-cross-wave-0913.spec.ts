/**
 * CROSS-ITEM QA, 2026-09-13 — three frontend waves landed in parallel, each
 * independently reviewed and each green on its own. This file holds the
 * defects that only exist in the ASSEMBLED product, which per-item review
 * cannot find by construction: every reviewer sees one item.
 *
 * The three surfaces that interfere:
 *
 *  · W2 put a brass EXTRUDE PROPOSAL CHIP on a solved profile
 *    (`viewport/ProposalNote.tsx`), placed from the profile's projected
 *    centroid by `viewport/sketchProposal.ts`.
 *  · The REFERENCE CUBE has always owned the frame's bottom-right corner in
 *    the part workspace, and CRAFT-6 extended it through plane pick and
 *    sketch (`components/AuthoringViewCube.tsx`).
 *  · W2 also gave the command band a NEXT-STEP DOT after a build.
 *
 * Neither placement knows about the other. `loopAnchor`'s only frame rule is
 * `proposal.margin` (12 px from the edge); the cube's seat is 108 px square
 * inset 42 px. The whole of that 108x108 square is therefore a legal home for
 * a chip, and the chip is the LATER sibling in the HUD layer, so it paints
 * and hit-tests ABOVE the cube.
 *
 * WHY THE FAILING CASES ARE `test.fail()` RATHER THAN DELETED: they are the
 * record of a defect nobody has fixed yet, and a case that starts PASSING is
 * the signal that it has been. Do not "fix" one by loosening it.
 *
 * Nothing here uses `click({ force: true })`. Every reachability claim is made
 * with `document.elementFromPoint` at a control's own centre and, where a
 * click is asserted, with a real `page.mouse.click` at real coordinates.
 */
import { expect, test, type Page } from "./fixtures";
import { createFeature, seedCube, SQUARE_20 } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";

/** Evidence in the log: the reason an expected failure failed, in numbers. */
function report(what: string, value: string): void {
  console.log(`    [XWAVE] ${what}: ${value}`);
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A named element's box in frame coordinates, or null when it is not drawn. */
async function boxOf(page: Page, testId: string): Promise<Box | null> {
  const box = await page.getByTestId(testId).boundingBox();
  return box === null
    ? null
    : { x: box.x, y: box.y, w: box.width, h: box.height };
}

/** What a real pointer aimed at `(x, y)` would actually land on. */
async function resolvesAt(page: Page, x: number, y: number): Promise<string> {
  return page.evaluate(
    ({ x, y }) => {
      const hit = document.elementFromPoint(x, y);
      if (hit === null) return "nothing";
      const tagged = hit.closest("[data-testid]");
      return tagged?.getAttribute("data-testid") ?? hit.tagName.toLowerCase();
    },
    { x, y },
  );
}

/**
 * How much of the cube's own seat a real pointer can still reach — a 7x7 grid
 * of its box, counted by what `elementFromPoint` resolves to.
 *
 * A COUNT rather than a boolean because the interesting answer is "most of it,
 * but not the middle": the cube reads as working right up until the facet you
 * aimed at was the one under the chip.
 */
async function cubeGrid(
  page: Page,
  cube: Box,
): Promise<Record<string, number>> {
  return page.evaluate(
    ({ cube }) => {
      const out: Record<string, number> = {};
      for (let i = 1; i < 8; i += 1) {
        for (let j = 1; j < 8; j += 1) {
          const hit = document.elementFromPoint(
            cube.x + (cube.w * i) / 8,
            cube.y + (cube.h * j) / 8,
          );
          const id =
            hit?.closest("[data-testid]")?.getAttribute("data-testid") ??
            "none";
          out[id] = (out[id] ?? 0) + 1;
        }
      }
      return out;
    },
    { cube },
  );
}

/** Right-drag the camera from `from` to `to` — the app's own pan gesture. */
async function pan(
  page: Page,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down({ button: "right" });
  for (let i = 1; i <= 12; i += 1) {
    await page.mouse.move(
      from.x + ((to.x - from.x) * i) / 12,
      from.y + ((to.y - from.y) * i) / 12,
    );
  }
  await page.mouse.up({ button: "right" });
  await page.waitForTimeout(400);
}

/** Draw a rectangle in the open sketcher and save it, all by hand. */
async function drawRectangleAndSave(page: Page): Promise<void> {
  const frame = await page.getByTestId("viewport").boundingBox();
  if (frame === null) throw new Error("the viewport has no box");
  const at = (fx: number, fy: number) => ({
    x: Math.round(frame.x + frame.width * fx),
    y: Math.round(frame.y + frame.height * fy),
  });
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const start = at(0.4, 0.38);
  const end = at(0.58, 0.6);
  await page.mouse.click(start.x, start.y);
  await page.mouse.move(end.x, end.y);
  await page.mouse.click(end.x, end.y);
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/**
 * An empty part, panned so that the origin sits on the cube's seat, then
 * sketched and solved — so the solve offer's DERIVED anchor lands under the
 * cube. The pan is an ordinary right-drag, not a contrivance: a modeller
 * working on the left of a large part puts their profile here routinely.
 */
async function chipOverTheCube(page: Page): Promise<Box> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Chip over cube");
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("viewport")).toBeVisible();
  const frame = await boxOf(page, "viewport");
  const cube = await boxOf(page, "view-cube");
  if (frame === null || cube === null) throw new Error("no frame or cube");

  await pan(
    page,
    { x: frame.x + frame.w / 2, y: frame.y + frame.h / 2 },
    { x: cube.x + 42, y: cube.y + 96 },
  );
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await drawRectangleAndSave(page);
  await expect(page.getByTestId("extrude-proposal")).toBeVisible({
    timeout: 30_000,
  });
  return cube;
}

test.describe("the proposal chip and the reference cube share one corner", () => {
  test("the chip must not take the cube's clickable face", async ({ page }) => {
    const cube = await chipOverTheCube(page);
    const chip = await boxOf(page, "extrude-proposal");
    if (chip === null) throw new Error("no chip");

    const overlap =
      Math.max(
        0,
        Math.min(chip.x + chip.w, cube.x + cube.w) - Math.max(chip.x, cube.x),
      ) *
      Math.max(
        0,
        Math.min(chip.y + chip.h, cube.y + cube.h) - Math.max(chip.y, cube.y),
      );

    const grid = await cubeGrid(page, cube);
    const stolen = grid["extrude-proposal"] ?? 0;

    // Evidence first: a screenshot beats prose for a placement defect.
    await page.screenshot({
      path: "test-results/qa-cross-chip-over-cube.png",
    });

    report(
      "chip box vs cube box",
      `chip ${JSON.stringify(chip)} cube ${JSON.stringify(cube)}`,
    );
    report(
      "cube seat, 49 sampled points",
      Object.entries(grid)
        .map(([k, v]) => `${k}=${v}`)
        .join(" "),
    );
    expect(
      { overlapPx: Math.round(overlap), stolenOf49: stolen },
      "the solve offer's chip is placed with no knowledge of the reference " +
        "cube's seat, so it lands on top of it and takes its clicks",
    ).toEqual({ overlapPx: 0, stolenOf49: 0 });
  });

  test("a click aimed at the cube must reach the cube", async ({ page }) => {
    const cube = await chipOverTheCube(page);
    // The point a user aims at when they want the block: its centre.
    const cx = cube.x + cube.w / 2;
    const cy = cube.y + cube.h / 2;
    const landsOn = await resolvesAt(page, cx, cy);
    report("cube centre resolves to", landsOn);
    // A REAL click there, so the outcome is the user's outcome and not a
    // property of `elementFromPoint`.
    await page.mouse.click(cx, cy);
    await page.waitForTimeout(600);
    report(
      "a click on the cube's centre opened the extrude editor",
      String((await page.getByTestId("extrude-editor").count()) > 0),
    );
    expect(
      landsOn,
      "a pointer aimed at the reference cube's centre lands somewhere else",
    ).toBe("view-cube");
  });

  /**
   * THE SECOND HALF OF THE SAME DEFECT, and the one a placement fix alone
   * leaves standing: the offer is ONE-SHOT and `seen` is recorded at write
   * time, so a viewport pointerdown that lands on the cube used to spend a
   * sketch's extrude offer for the whole session — re-opening that sketch and
   * re-solving it then offered nothing.
   *
   * Reaching for the reference cube to look at the profile you just solved is
   * PREPARATION for taking the offer, not an abandonment of it, and this note's
   * anchor re-projects per frame so it stays truthful across the view change.
   * The rule is therefore about the TARGET, not about the camera: a gesture on
   * something carrying `data-viewport-chrome` is a click on a control that
   * floats over the scene, not a gesture on the scene. Orbiting, wheel-zooming
   * and clicking geometry all still withdraw it.
   */
  test("a click on the cube steers the camera and keeps the offer", async ({
    page,
  }) => {
    const cube = await chipOverTheCube(page);
    const view = page.getByTestId("viewport");
    const before = await view.getAttribute("data-camera-pos");
    // The settle below waits for THIS stamp, so it must not already read it —
    // otherwise the wait would be satisfied before the click was made.
    expect(
      await view.getAttribute("data-view"),
      "no cube pick has happened yet, so no `direction` settle may be stamped",
    ).not.toBe("direction");

    // A facet, not the seat's dead centre: the point of the case is that the
    // camera really moved, so the click has to be one the cube acts on.
    const fx = cube.x + cube.w / 2;
    const fy = cube.y + cube.h * 0.22;
    expect(
      await resolvesAt(page, fx, fy),
      "the facet this case clicks must belong to the cube",
    ).toBe("view-cube");
    await page.mouse.click(fx, fy);

    // THE NAMED SETTLE. A cube pick EASES the camera to a `direction` pose, and
    // `data-view` / `data-camera-pos` are stamped only when that ease LANDS
    // (`CameraRig.onSettle`). This used to be a fixed `waitForTimeout(800)`,
    // which read the stamp mid-ease whenever the frame loop ran slow — the
    // camera was moving, the stamp had not been written yet, and the case
    // reported "the click did not steer" (~2 runs in 8; 7 of 8 under four
    // CPU-burning processes). Waiting for the stamp the ease itself writes
    // is the property; a clock was a guess at how long the ease takes.
    await expect
      .poll(() => view.getAttribute("data-view"), {
        message: "the cube pick's camera ease never landed (no settle stamp)",
        timeout: 20_000,
      })
      .toBe("direction");

    const after = await view.getAttribute("data-camera-pos");
    report("camera before -> after", `${before} -> ${after}`);
    report(
      "chip after a cube click",
      String(await page.getByTestId("extrude-proposal").count()),
    );
    expect(
      after,
      "the click must actually steer the camera, or this case proves nothing",
    ).not.toBe(before);
    await expect(
      page.getByTestId("extrude-proposal"),
      "a click aimed at the camera widget spent the sketch's one-shot offer",
    ).toHaveCount(1);
  });
});

/**
 * A part wearing BOTH non-modal offers at once: the band's next-step dot from a
 * build, and the extrude chip from a sketch that has just solved. This is the
 * state one Escape used to clear entirely.
 */
async function chipAndBandDot(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Escape");
  const first = await createFeature(page, account.token, part.id, {
    name: "Sketch1",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: 0,
  });
  await createFeature(page, account.token, part.id, {
    name: "Sketch2",
    feature: { type: "sketch", version: 1, params: SQUARE_20 },
    expected_tree_version: first.tree_version,
  });
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("viewport")).toBeVisible();
  await expect(page.getByTestId("feature-row")).toHaveCount(2);

  // A BUILD, so the band wears its next-step dot…
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-editor")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("extrude-submit").click();
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("next-step-dot")).toHaveCount(1, {
    timeout: 15_000,
  });

  // …and a solve on a sketch that has never offered, so a chip is up too.
  await page.getByTestId("feature-row").nth(1).click({ button: "right" });
  await page.getByTestId("tree-ctx-edit").click();
  await expect(page.getByTestId("sketch-strip")).toBeVisible();
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("extrude-proposal")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("next-step-dot")).toHaveCount(1);
}

test.describe("one Escape backs out ONE step", () => {
  /**
   * Three cancel listeners now sit on `window` for the same key: the proposal
   * note (capture, `preventDefault` only), the feature-tree row drag (capture,
   * `preventDefault` + `stopPropagation`) and the band's next-step accent
   * (bubble). None of them claims the key exclusively — `stopPropagation` on
   * `window` does not stop a SIBLING listener on `window`, which needs
   * `stopImmediatePropagation` — so one Escape runs two of them.
   *
   * CLOSED by the cancel cascade in `lib/modalGate.ts`: the order is declared
   * (`drag` > `offer` > `mark`, under the modal layer) and exactly one rung
   * runs. `<body data-cancel-rungs>` publishes what is standing, so the count
   * below can be read against what the cascade actually had to choose from.
   */
  test("a chip and a band dot are not both withdrawn by one key", async ({
    page,
  }) => {
    await chipAndBandDot(page);

    // What the cascade had to choose from, before it chose — so "the dot
    // survived" is read against a cascade that was holding both, not against
    // a frame where the chip was the only thing listening.
    report(
      "cancel rungs standing",
      String(await page.locator("body").getAttribute("data-cancel-rungs")),
    );
    expect(
      await page.locator("body").getAttribute("data-cancel-rungs"),
      "both the offer and the mark must be standing, or this case is not the one",
    ).toBe("offer mark");

    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    report(
      "after ONE Escape",
      `chip ${await page.getByTestId("extrude-proposal").count()}, ` +
        `band dot ${await page.getByTestId("next-step-dot").count()}`,
    );
    // ONE step back means the frontmost offer goes and the band keeps its mark.
    await expect(page.getByTestId("extrude-proposal")).toHaveCount(0);
    await expect(
      page.getByTestId("next-step-dot"),
      "one Escape withdrew the chip AND the band's proposal — two steps",
    ).toHaveCount(1);

    // …and the SECOND Escape takes the next step, so nothing is stranded.
    await page.keyboard.press("Escape");
    await expect(
      page.getByTestId("next-step-dot"),
      "the band's mark must still be reachable by the next Escape",
    ).toHaveCount(0);
    report(
      "cancel rungs after both keys",
      String(await page.locator("body").getAttribute("data-cancel-rungs")),
    );
  });

  /**
   * QA's third row, which is the one that showed the mechanism: the drag's
   * `stopPropagation()` killed the band's BUBBLE listener but not the note's
   * SIBLING capture listener on the same target, so the drag was abandoned AND
   * the chip withdrawn while the dot survived. Always exactly two, never one.
   *
   * A gesture in progress is the cascade's strongest rung, so it goes alone.
   */
  test("a live row drag is the ONE thing a key abandons", async ({ page }) => {
    await chipAndBandDot(page);

    // Take hold of a row — a real press and move, so the drag is genuinely in
    // flight and not a state flag set by a test. The grip is the SELECTED
    // row's ordinal promoted, and the setup's context-menu edit already left
    // that row selected — so no extra click is needed, which matters: a click
    // anywhere else withdraws the offers this case needs standing.
    const grip = page.getByTestId("feature-grip-1");
    const gripBox = await grip.boundingBox();
    const lastRow = await page.getByTestId("feature-row").last().boundingBox();
    if (gripBox === null || lastRow === null) throw new Error("no rows");
    await page.mouse.move(
      gripBox.x + gripBox.width / 2,
      gripBox.y + gripBox.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      gripBox.x + gripBox.width / 2,
      lastRow.y + lastRow.height / 2,
      { steps: 6 },
    );
    await expect(page.getByTestId("reorder-seat")).toHaveCount(1);

    const standing = await page
      .locator("body")
      .getAttribute("data-cancel-rungs");
    report("cancel rungs with a drag in flight", String(standing));
    expect(
      standing,
      "all three rungs must be standing, or this case is not the one QA hit",
    ).toBe("drag offer mark");

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("reorder-seat")).toHaveCount(0);
    await page.mouse.up();
    report(
      "after ONE Escape with a drag in flight",
      `chip ${await page.getByTestId("extrude-proposal").count()}, ` +
        `band dot ${await page.getByTestId("next-step-dot").count()}`,
    );
    await expect(
      page.getByTestId("extrude-proposal"),
      "abandoning the drag also withdrew the chip — two steps",
    ).toHaveCount(1);
    await expect(page.getByTestId("next-step-dot")).toHaveCount(1);
  });
});

test.describe("the cube during a face pick (CRAFT-6)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("every offered face mark stays reachable", async ({ page }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Face pick");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport")).toBeVisible();
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    const marks = page.locator('[data-testid^="plane-pick-face-"]');
    await expect(marks.first()).toBeVisible({ timeout: 30_000 });

    const frame = await boxOf(page, "viewport");
    const cube = await boxOf(page, "view-cube");
    if (frame === null || cube === null) {
      throw new Error(
        "CRAFT-6 mounts the cube during a face pick; it is not here",
      );
    }

    // Pan the body under the cube — the gesture a modeller makes to look at
    // the far side of a part without losing the near one off the left edge.
    const first = await marks.first().boundingBox();
    if (first === null) throw new Error("no pick mark");
    await pan(
      page,
      { x: first.x + first.width / 2, y: first.y + first.height / 2 },
      { x: cube.x + cube.w / 2, y: cube.y + cube.h / 2 },
    );

    // The yield is a STATE, printed whichever way it goes: a reachability
    // number with no stamp beside it cannot tell "the cube stood aside" from
    // "no mark happened to land on it".
    report(
      "cube pick-yield stamp",
      String(
        await page.getByTestId("view-cube").getAttribute("data-pick-yield"),
      ),
    );

    const unreachable: string[] = [];
    for (const mark of await marks.all()) {
      const id = (await mark.getAttribute("data-testid")) ?? "?";
      const box = await mark.boundingBox();
      if (box === null) continue;
      const lands = await resolvesAt(
        page,
        box.x + box.width / 2,
        box.y + box.height / 2,
      );
      if (lands !== id) unreachable.push(`${id} -> ${lands}`);
    }
    report(
      "face pick marks under the cube",
      `${unreachable.length} of ${(await marks.all()).length} — ${unreachable.join("; ")}`,
    );
    await page.screenshot({ path: "test-results/qa-cross-face-pick.png" });
    expect(
      unreachable,
      "a face the user must pick is under the reference cube, which CRAFT-6 " +
        "mounted into this mode; before it, this corner was free",
    ).toEqual([]);

    /*
      AND THE PICK ACTUALLY COMPLETES. `elementFromPoint` resolving to the mark
      says the pointer reaches it; only a real click says the flow does. A mark
      under the cube is chosen deliberately — the whole point is the corner the
      cube had taken — and the sketcher opening is the user's own outcome.
    */
    let underCube: { id: string; x: number; y: number } | null = null;
    for (const mark of await marks.all()) {
      const box = await mark.boundingBox();
      if (box === null) continue;
      const x = box.x + box.width / 2;
      const y = box.y + box.height / 2;
      if (
        x >= cube.x &&
        x <= cube.x + cube.w &&
        y >= cube.y &&
        y <= cube.y + cube.h
      ) {
        underCube = {
          id: (await mark.getAttribute("data-testid")) ?? "?",
          x,
          y,
        };
        break;
      }
    }
    report(
      "a mark seated inside the cube's rect",
      underCube === null
        ? "none — the pan did not reach the corner"
        : underCube.id,
    );
    expect(
      underCube,
      "the pan must actually put a pick mark on the cube's seat, or this " +
        "case is measuring an empty corner",
    ).not.toBeNull();
    if (underCube !== null) {
      await page.mouse.click(underCube.x, underCube.y);
      await expect(
        page.getByTestId("sketch-strip"),
        "a real click on the mark the cube was sitting on must open the sketcher",
      ).toBeVisible({ timeout: 30_000 });
    }
  });

  /**
   * THE OTHER HALF OF THE YIELD: it is temporary. A cube that stayed inert
   * after the pick would be the same defect wearing the opposite sign — an
   * instrument the user can see and cannot use — and a spec that only proved
   * the corner was pickable would score full marks on it.
   */
  test("the cube is a control again once the pick is over", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Yield ends");
    await seedCube(page, account.token, part.id);
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    const view = page.getByTestId("viewport");
    const cubeEl = page.getByTestId("view-cube");

    await expect(cubeEl).not.toHaveAttribute("data-pick-yield", /.*/);

    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-pick-face").click();
    await expect(
      page.locator('[data-testid^="plane-pick-face-"]').first(),
    ).toBeVisible({ timeout: 30_000 });
    await expect(
      cubeEl,
      "the cube yields while the tool is asking for a pick",
    ).toHaveAttribute("data-pick-yield", "1");

    // Esc backs out of the pick — the cube must come back as a control.
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-testid^="plane-pick-face-"]')).toHaveCount(
      0,
      { timeout: 15_000 },
    );
    await expect(
      cubeEl,
      "the yield outlived the pick that caused it",
    ).not.toHaveAttribute("data-pick-yield", /.*/);

    // …and it steers, which is the claim the stamp stands for.
    const cube = await boxOf(page, "view-cube");
    if (cube === null) throw new Error("no cube");
    const before = await view.getAttribute("data-camera-pos");
    await page.mouse.click(cube.x + cube.w / 2, cube.y + cube.h * 0.22);
    await page.waitForTimeout(800);
    const after = await view.getAttribute("data-camera-pos");
    report("camera after the pick ended", `${before} -> ${after}`);
    expect(after).not.toBe(before);
  });
});

test.describe("what the assembled surfaces DO agree about", () => {
  test.use({ hasTouch: true, viewport: { width: 1280, height: 800 } });

  test("the chip is a real tap target on a touch viewport", async ({
    page,
  }) => {
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Touch");
    await page.goto(`/parts/${part.id}`);
    await expect(page.getByTestId("viewport")).toBeVisible();
    await page.getByTestId("new-sketch").click();
    await page.getByTestId("plane-XY").click();
    await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
    await drawRectangleAndSave(page);

    const chip = page.getByTestId("extrude-proposal");
    await expect(chip).toBeVisible({ timeout: 30_000 });
    const box = await chip.boundingBox();
    if (box === null) throw new Error("no chip");
    // WCAG 2.2 SC 2.5.8 asks 24x24; the chip meets it by SIZE, not by spacing.
    expect(box.height).toBeGreaterThanOrEqual(24);
    expect(box.width).toBeGreaterThanOrEqual(24);
    const lands = await resolvesAt(
      page,
      box.x + box.width / 2,
      box.y + box.height / 2,
    );
    expect(lands).toBe("extrude-proposal");
    // A real TAP, not a click: a chip that only answers a mouse is not a
    // touch affordance however green a `.click()` would be.
    await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
    await expect(page.getByTestId("extrude-editor")).toBeVisible({
      timeout: 15_000,
    });
  });
});
