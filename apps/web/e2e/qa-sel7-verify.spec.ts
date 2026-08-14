import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures";

import { labelCentroid, setBodyMode } from "./occludedPlate";
import { seedBoredPlateAndBlock } from "./partSeed";
import { litPoints, type Point } from "./reachability";
import {
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * SEL-7 QA VERIFICATION — written by qa-tester, independent of the builder.
 *
 * The builder's own gate (`hole-hidden-body.spec.ts`) is strong on the claim and
 * on the pixels. Five things it does not ask, and this file exists for those:
 *
 * 1. **WHICH row is the plate, decided WITHOUT the behaviour under test.** The
 *    builder's discovery hides each body in turn and reads which faces leave the
 *    FACE pick's offer — i.e. it depends on SEL-6b to find the subject of SEL-7,
 *    and it can only run once the Hole editor is already open. Here the row is
 *    read off the Bodies panel's own row text (the base feature's name, "Extrude1"
 *    for the plate and "Block" for the block), which is a fact about the fixture,
 *    costs no toggling, and works BEFORE any command exists — which leg 2 needs.
 *
 * 2. **The editor's NUMBERS across the round trip.** "Every node comes back at
 *    its previous ordinal" is asserted on ids; the state the modeller would lose
 *    is the drilled coordinate. This file records `hole-position-x` /
 *    `hole-position-y` and the SELECTED cue (`aria-pressed` on the node that was
 *    picked) before the hide and demands both survive it.
 *
 * 3. **A live CONTROL.** The builder hides the other body and re-reads the id
 *    list. That catches "unmount whenever anything is hidden" but not "leave the
 *    nodes mounted and dead", so the control here also COMPLETES a pick with the
 *    other body hidden and demands the position move.
 *
 * 4. **A hand.** No SEL-7 leg has ever tapped. A withheld DOM button that a
 *    finger still reaches is the half-shipped shape SEL-6's QA found; the touch
 *    leg taps a cluster around the pixel a bore-centre diamond occupied and
 *    demands the coordinates do not move.
 *
 * 5. **The stage BEFORE this one, and the stage AFTER it.** Hiding the plate
 *    before opening Hole must leave the FACE pick offering nothing on it
 *    (SEL-6b); and Create — which SEL-7 deliberately keeps reachable — must cost
 *    the command nothing, measured by running the whole flow twice and comparing.
 *
 * ## Mutation evidence — measured, one mutation per claim
 *
 * (Deliberately broken builds, all reverted; these are the numbers observed.)
 *
 * - **`|| placementHidden` removed from the early return** (the shipped gate):
 *   **23 snap nodes still mounted** with the plate hidden. Red on the claim leg,
 *   the keyboard leg and the TOUCH leg; the face-stage leg stays green, which is
 *   correct — that is SEL-6b's territory. Note `data-hole-placement-hidden` is
 *   still "1" under this mutation, because the stamp is written ABOVE the early
 *   return: a gate asserting only that attribute would pass a build with every
 *   diamond floating over the void, which is why the counts carry the claim.
 * - **…and with the count assertions softened so the taps run**: the nine-tap
 *   cluster reaches a diamond over the hidden body and drills — X 50 -> 0,
 *   Y 30 -> 60. The hand leg is load-bearing on its own, not only via the count.
 * - **The hover stamp reverted to `armed && hoverPoint !== null`, alone**: every
 *   leg GREEN, including the keyboard one. Honest reading: the guard is
 *   defence-in-depth; the `placementHidden -> setHoverPoint(null)` effect clears
 *   the hover by itself. Reverting BOTH (the guard and that effect) reddens the
 *   keyboard leg with `data-hole-point-hover="1"` sitting beside
 *   `data-hole-placement-hidden="1"` — the stale-stamp shape, which no
 *   pointer-driven leg can reach because clicking the eye moves the cursor off
 *   the canvas first.
 * - The builder's own `hole-hidden-body.spec.ts` was re-run against the first
 *   mutation too, and is red there (23 nodes): the shipped gate is load-bearing.
 */

/** Print a measured number into the run log — QA evidence, not narration. */
function report(label: string, value: string): void {
  console.log(`    [SEL-7 QA] ${label}: ${value}`);
}

/**
 * Every DOM node the OVERLAY mounts, stated as a prefix minus the editor's own
 * chrome rather than as a list of the three kinds.
 *
 * MEASURED, not assumed: a bare `[data-testid^="hole-point-"]` can never reach
 * 0 while the command is open, because the editor's arm button is
 * `hole-point-pick` and its disabled reason is `hole-point-pick-reason` — so
 * the acceptance clause taken literally is unsatisfiable (it resolved to 1
 * element with a face chosen and 2 without). Excluding that ONE prefix keeps
 * the property non-enumerated, so a FOURTH snap kind added later is inside this
 * gate by default — the enumerated form would silently stop covering it.
 */
const HOLE_POINT_NODES =
  '[data-testid^="hole-point-"]:not([data-testid^="hole-point-pick"])';
/** The three snap kinds the overlay mounts today, for the census. */
const SNAP_NODES =
  '[data-testid="hole-point-center"], [data-testid^="hole-point-vertex-"], [data-testid^="hole-point-circle-"]';

interface Rows {
  plate: number;
  block: number;
}

/** The bored plate + the disjoint block, framed and pinned (`partSeed.ts`). */
async function openBoredPlateAndBlock(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Plate and block");
  await seedBoredPlateAndBlock(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 60_000 })
    .toBeGreaterThan(24);
  const view = page.getByTestId("viewport");
  await view.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(view).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 30_000,
  });
  await waitForFrames(page, 6);
  await expect(page.getByTestId("body-row")).toHaveCount(2, {
    timeout: 30_000,
  });
}

/**
 * WHICH ROW IS THE PLATE — from the rows' own text, not from the behaviour
 * under test.
 *
 * `BodiesPanel` prints each body's base-feature name beside its ordinal, and
 * the fixture names them: the plate's solid is `Extrude1`, the second body's is
 * `Block`. Exactly one row must carry each, or the fixture is not what this
 * file thinks it is and every measurement below is meaningless — hence the
 * assertion rather than a silent `find`.
 */
async function discoverRows(page: Page): Promise<Rows> {
  const rows = await page.getByTestId("body-row").allInnerTexts();
  report("body rows", rows.map((t) => JSON.stringify(t)).join(" | "));
  const plate = rows.findIndex((t) => t.includes("Extrude1"));
  const block = rows.findIndex((t) => t.includes("Block"));
  expect(
    plate,
    `a row naming the plate's solid in ${rows.join(" | ")}`,
  ).toBeGreaterThanOrEqual(0);
  expect(
    block,
    `a row naming the block in ${rows.join(" | ")}`,
  ).toBeGreaterThanOrEqual(0);
  expect(plate, "the plate and the block are different rows").not.toBe(block);
  return { plate, block };
}

interface OfferedFace {
  testId: string;
  label: string;
  centroid: { x: number; y: number; z: number };
  /** The 60 × 60 plate lives at OCCT y = 0…60; the block at y = 80…100. */
  plate: boolean;
}

/** Every planar face currently offered by the armed FACE pick. */
async function offeredFaces(page: Page): Promise<OfferedFace[]> {
  const faces: OfferedFace[] = [];
  for (const node of await page
    .locator('[data-testid^="plane-pick-face-"]')
    .all()) {
    const label = (await node.getAttribute("aria-label")) ?? "";
    const centroid = labelCentroid(label);
    faces.push({
      testId: (await node.getAttribute("data-testid")) ?? "",
      label,
      centroid,
      plate: centroid.y < 70,
    });
  }
  return faces;
}

/** The plate's TOP face — the one carrying the bolt circle (largest z). */
function plateTopFace(faces: readonly OfferedFace[]): OfferedFace {
  const plate = [...faces.filter((f) => f.plate)].sort(
    (a, b) => b.centroid.z - a.centroid.z,
  );
  const top = plate[0];
  expect(top, "the plate offers a face to drill").toBeDefined();
  if (top === undefined) throw new Error("no plate face on offer");
  return top;
}

/** Every snap node's test id, sorted — the overlay's offer, order-independent. */
async function snapIds(page: Page): Promise<string[]> {
  const ids: string[] = [];
  for (const node of await page.locator(SNAP_NODES).all()) {
    ids.push((await node.getAttribute("data-testid")) ?? "");
  }
  return ids.sort();
}

/** The editor's two coordinate cells, as typed. */
async function coordinates(page: Page): Promise<{ x: string; y: string }> {
  return {
    x: await page.getByTestId("hole-position-x").inputValue(),
    y: await page.getByTestId("hole-position-y").inputValue(),
  };
}

/** Open Hole and drill-arm the plate's top face; returns that face. */
async function armOnPlateTop(page: Page): Promise<OfferedFace> {
  await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 60_000 });
  await page.getByTestId("new-hole").click();
  await expect(page.getByTestId("hole-editor")).toBeVisible();
  await expect(
    page.locator('[data-testid^="plane-pick-face-"]').first(),
  ).toBeVisible({ timeout: 30_000 });
  const top = plateTopFace(await offeredFaces(page));
  report("placement face", `${top.testId} — ${top.label}`);
  await page.getByTestId(top.testId).click();
  await expect(page.getByTestId("hole-position")).toContainText(
    "Centre of face",
  );
  await page.getByTestId("hole-point-pick").click();
  await expect(page.getByTestId("hole-point-center")).toBeVisible({
    timeout: 30_000,
  });
  await waitForFrames(page, 6);
  return top;
}

/**
 * Park the pointer on the placement face, clear of every snap diamond, until
 * the free-placement stamp lights — so "the stamp cleared" after the hide is a
 * measurement and not a pointer that was never over the face.
 */
async function armHoverOnFace(page: Page): Promise<Point | null> {
  const view = page.getByTestId("viewport");
  const boxes = (
    await Promise.all(
      (await page.locator(SNAP_NODES).all()).map((n) => n.boundingBox()),
    )
  ).flatMap((b) => (b === null ? [] : [b]));
  const lit = await litPoints(page, { step: 12 });
  for (const point of lit) {
    const clear = boxes.every(
      (b) =>
        point.x < b.x - 16 ||
        point.x > b.x + b.width + 16 ||
        point.y < b.y - 16 ||
        point.y > b.y + b.height + 16,
    );
    if (!clear) continue;
    await page.mouse.move(point.x, point.y);
    await waitForFrames(page, 2);
    if ((await view.getAttribute("data-hole-point-hover")) !== null) {
      report(
        "free-placement hover armed at",
        `${Math.round(point.x)},${Math.round(point.y)} of ${lit.length} lit points`,
      );
      return point;
    }
  }
  return null;
}

test.describe("SEL-7 QA — the hole placement overlay against a hidden body", () => {
  test("claim, control, and the editor state across the round trip", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const view = page.getByTestId("viewport");
    await openBoredPlateAndBlock(page);
    const rows = await discoverRows(page);
    await armOnPlateTop(page);

    // --- NON-VACUITY: what is on offer while everything is drawn ------------
    const drawnIds = await snapIds(page);
    const centres = drawnIds.filter((id) => id === "hole-point-center").length;
    const corners = drawnIds.filter((id) =>
      id.startsWith("hole-point-vertex-"),
    ).length;
    const circles = drawnIds.filter((id) =>
      id.startsWith("hole-point-circle-"),
    ).length;
    report(
      "snap nodes, everything drawn",
      `${drawnIds.length} = ${centres} centre + ${corners} vertices + ${circles} bore centres`,
    );
    expect(centres, "the face centre is snappable").toBe(1);
    expect(corners, "the face's corners are snappable").toBeGreaterThanOrEqual(
      4,
    );
    expect(circles, "the seven bore centres are snappable").toBe(7);
    expect(
      drawnIds.length,
      "the fixture carries at least the 12 snaps the acceptance counts",
    ).toBeGreaterThanOrEqual(12);
    await expect(page.getByTestId("hole-frame-origin")).toBeVisible();
    await expect(view).not.toHaveAttribute("data-hole-placement-hidden", /.*/);

    // --- THE CONTROL: hide the OTHER body -----------------------------------
    // A gate that unmounted whenever ANY body was hidden would pass the claim
    // leg below and fail here, which is what makes the claim leg mean anything.
    await setBodyMode(page, rows.block, "hidden");
    await waitForFrames(page, 6);
    expect(
      await snapIds(page),
      "hiding a body that does not carry the placement face changes nothing",
    ).toEqual(drawnIds);
    await expect(page.getByTestId("hole-frame-origin")).toBeVisible();
    await expect(view).not.toHaveAttribute("data-hole-placement-hidden", /.*/);
    await expect(page.getByTestId("hole-placement-hidden-note")).toHaveCount(0);

    // …and the nodes are LIVE, not merely mounted: a snap still writes.
    const beforeControlPick = await coordinates(page);
    await page.getByTestId("hole-point-circle-0").click();
    await waitForFrames(page, 2);
    const afterControlPick = await coordinates(page);
    report(
      "control pick with the OTHER body hidden",
      `X ${beforeControlPick.x} -> ${afterControlPick.x}, Y ${beforeControlPick.y} -> ${afterControlPick.y}`,
    );
    expect(
      `${afterControlPick.x},${afterControlPick.y}`,
      "a snap still completes a pick while an unrelated body is hidden",
    ).not.toBe(`${beforeControlPick.x},${beforeControlPick.y}`);
    await setBodyMode(page, rows.block, "solid");
    await waitForFrames(page, 6);

    // Completing a pick DISARMS it (measured: the snap nodes unmount on the
    // click), so the round trip below is set up by re-arming — which is also
    // the state a modeller is in when they reach for the eye.
    await expect(page.locator(SNAP_NODES)).toHaveCount(0);
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 30_000,
    });
    await waitForFrames(page, 4);
    expect(
      await snapIds(page),
      "re-arming after a completed pick offers the same set",
    ).toEqual(drawnIds);

    // The state the round trip must preserve: the coordinates, and WHICH node
    // wears the selected cue.
    const picked = await coordinates(page);
    await expect(page.getByTestId("hole-point-circle-0")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    report("coordinates before the hide", `X ${picked.x}, Y ${picked.y}`);

    // The hover census stamp, ARMED over the face — the state a stale stamp
    // would be left in. Without this the "no stamp afterwards" assertion is
    // satisfied by a pointer that never touched the face.
    const hovered = await armHoverOnFace(page);
    expect(
      hovered,
      "a point on the placement face that lights the free-placement stamp",
    ).not.toBeNull();
    await expect(view).toHaveAttribute("data-hole-point-hover", "1");

    // --- THE CLAIM: hide the body carrying the placement face ---------------
    await setBodyMode(page, rows.plate, "hidden");
    await waitForFrames(page, 6);

    // (a) NOT MOUNTED — count, not visibility: an invisible-but-mounted
    //     PickNode is still clickable and still a hole.
    await expect(page.locator(HOLE_POINT_NODES)).toHaveCount(0);
    await expect(page.getByTestId("hole-frame-origin")).toHaveCount(0);
    // (b) …and the overlay is mounted and WITHHOLDING, not simply never opened.
    await expect(view).toHaveAttribute("data-hole-placement-hidden", "1");
    // (c) the census stamp cannot be scored on a body that is not on screen —
    //     swept AFTER the hide, so a stale stamp has every chance to survive.
    const box = await view.boundingBox();
    expect(box, "the viewport has a box to sweep").not.toBeNull();
    if (box !== null) {
      for (const t of [0.3, 0.4, 0.5, 0.6, 0.7]) {
        await page.mouse.move(box.x + box.width * t, box.y + box.height * t);
        await waitForFrames(page, 1);
      }
    }
    await expect(view).not.toHaveAttribute("data-hole-point-hover", /.*/);

    // NON-VACUITY of the claim: the editor is still open and the OTHER body is
    // still listed — "no node is mounted" must not be free.
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(page.getByTestId("body-row")).toHaveCount(2);
    await expect(page.getByTestId("hole-point-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("hole-position")).toContainText(
      "Body hidden",
    );

    // --- RESTORATION AT THE PREVIOUS ORDINAL --------------------------------
    await setBodyMode(page, rows.plate, "solid");
    await waitForFrames(page, 6);
    const restoredIds = await snapIds(page);
    report(
      "snap nodes after showing the plate again",
      `${restoredIds.length} restored`,
    );
    expect(
      restoredIds,
      "the same ids come back — a renumbered vertex-N passes a count check",
    ).toEqual(drawnIds);
    await expect(view).not.toHaveAttribute("data-hole-placement-hidden", /.*/);
    await expect(page.getByTestId("hole-placement-hidden-note")).toHaveCount(0);

    const after = await coordinates(page);
    report("coordinates after the round trip", `X ${after.x}, Y ${after.y}`);
    expect(after, "the drilled coordinate survives hiding its body").toEqual(
      picked,
    );
    await expect(page.getByTestId("hole-point-circle-0")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    /*
      ON SCREEN, not merely in the DOM — and the measurement of the gap between
      those two, which is a finding rather than a SEL-7 defect: hiding a body
      refits the scene to what is left, and showing it again does NOT refit
      back, so every restored mark can be mounted at its previous ordinal and
      still be `display: none` (drei's `Html` hides a point behind the camera).
      Reported, then re-framed, because the acceptance clause is about the marks.
    */
    const visibleBeforeFit = await page
      .getByTestId("hole-point-center")
      .isVisible();
    report(
      "restored marks on screen WITHOUT re-framing",
      visibleBeforeFit ? "yes" : "no — the frame stayed on what was left",
    );
    await page.getByTestId("view-fit").click();
    await waitForFrames(page, 6);
    await expect(page.getByTestId("hole-frame-origin")).toBeVisible();
    await expect(page.getByTestId("hole-point-center")).toBeVisible();
  });

  test("hiding the plate BEFORE opening Hole leaves the FACE pick nothing on it", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await openBoredPlateAndBlock(page);
    const rows = await discoverRows(page);
    await setBodyMode(page, rows.plate, "hidden");
    await waitForFrames(page, 6);

    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 60_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();
    await expect(
      page.locator('[data-testid^="plane-pick-face-"]').first(),
    ).toBeVisible({ timeout: 30_000 });
    await waitForFrames(page, 4);

    const offered = await offeredFaces(page);
    const plateFaces = offered.filter((f) => f.plate);
    const blockFaces = offered.filter((f) => !f.plate);
    report(
      "face pick with the plate hidden",
      `${plateFaces.length} plate + ${blockFaces.length} block faces offered`,
    );
    expect(
      blockFaces.length,
      "the drawn body still offers its faces — the pick is alive",
    ).toBeGreaterThan(0);
    expect(
      plateFaces.map((f) => f.label),
      "a hidden body offers no face to drill (SEL-6b, the stage before this one)",
    ).toEqual([]);
    // …and no placement overlay exists to withhold, since no face is chosen.
    await expect(page.locator(HOLE_POINT_NODES)).toHaveCount(0);
  });

  /**
   * THE STAMP, ON THE ONE PATH THAT CAN LEAVE IT STALE.
   *
   * Hiding by CLICKING the eye moves the pointer off the canvas first, so r3f's
   * pointer-out clears the free-placement hover before the body is ever hidden
   * — measured: with the stamp's `!placementHidden` guard reverted, the main leg
   * above still passes. The `V` accelerator hides the ADDRESSED row from the
   * keyboard with the cursor parked on the face, which is the only way to reach
   * "hidden while hovering", and therefore the only leg that can tell a real
   * guard from a coincidence. Two things clear it there (the guard and the
   * hover-reset effect); this asks for the observable, not for either mechanism.
   */
  test("the census stamp cannot be scored on a body hidden from the keyboard", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const view = page.getByTestId("viewport");
    await openBoredPlateAndBlock(page);
    const rows = await discoverRows(page);
    await armOnPlateTop(page);

    // ADDRESS the plate's row without leaving it hidden — `V` acts on the row
    // whose eye was last touched.
    await setBodyMode(page, rows.plate, "hidden");
    await setBodyMode(page, rows.plate, "solid");
    // Re-frame after the round trip: hiding a body refits the scene to what is
    // left, and showing it again does not undo that, so the marks come back
    // mounted but off-frame (see the finding in the QA report). This leg is
    // about the stamp, so it puts the camera back rather than measuring that.
    await page.getByTestId("view-fit").click();
    await waitForFrames(page, 6);
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 30_000,
    });

    const hovered = await armHoverOnFace(page);
    expect(hovered, "a hovered point on the placement face").not.toBeNull();
    await expect(view).toHaveAttribute("data-hole-point-hover", "1");

    // …and now hide it WITHOUT moving the pointer.
    await page.keyboard.press("v");
    await waitForFrames(page, 6);
    await expect(
      page.getByTestId("body-row").nth(rows.plate),
      "the accelerator hid the plate's row",
    ).toHaveAttribute("data-visibility", "hidden");

    await expect(view).toHaveAttribute("data-hole-placement-hidden", "1");
    await expect(page.locator(HOLE_POINT_NODES)).toHaveCount(0);
    await expect(
      view,
      "a stamp left set would score a census on a body that is not on screen",
    ).not.toHaveAttribute("data-hole-point-hover", /.*/);
  });

  /**
   * NOT A DEAD END — the flow half of the claim, driven all the way to Create.
   *
   * SEL-7 deliberately keeps the pick armed and Create reachable while the body
   * is off, on the argument that a hole is legitimate geometry whose visibility
   * is a view decision. No SEL-7 gate ever presses Create, so nothing measured
   * whether the withheld state COSTS the command anything. This runs the whole
   * flow twice on two fresh parts — once with the plate drawn, once with it
   * hidden — and demands the two outcomes be IDENTICAL: same eval verdict, same
   * per-feature errors, same stored coordinates.
   *
   * The assertion is a COMPARISON rather than `toHaveText("Solved")` because
   * the drawn run does not solve either. That is a separate, pre-existing
   * multi-body defect this pass found and filed (a Hole only ever drills the
   * ACTIVE body, while the face pick offers every body's faces: on this fixture
   * the plate's own top face returns `HOLE_OFF_BODY`, and the identical hole on
   * the identical face SOLVES when the plate is the only body). Asserting
   * "Solved" here would make this file red for somebody else's bug and hide the
   * SEL-7 property inside it; comparing the two runs measures exactly the SEL-7
   * property and keeps passing once the other defect is fixed.
   */
  test("Create costs nothing: the withheld run matches the drawn one", async ({
    page,
  }) => {
    test.setTimeout(420_000);

    interface Outcome {
      status: string;
      errors: string[];
      promised: { x: string; y: string };
      volumeBefore: string;
      volumeAfter: string;
    }

    const run = async (hide: boolean): Promise<Outcome> => {
      const what = hide ? "HIDDEN" : "drawn";
      await openBoredPlateAndBlock(page);
      const rows = await discoverRows(page);
      await armOnPlateTop(page);

      // The face CENTRE, clear of all seven bores — a hole concentric with an
      // existing one is a different question.
      await page.getByTestId("hole-point-center").click();
      await waitForFrames(page, 2);
      const promised = await coordinates(page);
      const volumeBefore = (
        (await page.getByTestId("prop-volume").textContent()) ?? ""
      ).trim();

      if (hide) {
        await setBodyMode(page, rows.plate, "hidden");
        await waitForFrames(page, 6);
        await expect(page.locator(HOLE_POINT_NODES)).toHaveCount(0);
      }
      // The withheld state must not disable the command it says it is keeping.
      await expect(page.getByTestId("hole-submit")).toBeEnabled();
      await page.getByTestId("hole-submit").click();

      await expect(
        page.getByTestId("feature-row").filter({ hasText: "Hole1" }),
      ).toBeVisible({ timeout: 60_000 });

      /*
        WAIT FOR A STATE THE PRODUCT CAN ACTUALLY BE IN.

        This wait used to read `.not.toBe("Evaluating")`, and "Evaluating" is
        not in the SOLVE cell's vocabulary: `solveSummary` in
        `src/features/partBuild.ts` returns exactly one of "Solving…" | "—" |
        "Failed" | "Solved" (cited by NAME, not by line: the gate at the foot
        of this file re-reads that function every run, so the four strings
        cannot go stale here without the gate saying so). The predicate was
        therefore satisfied by the FIRST sample and the wait was worth
        nothing, so the two arms below sampled whatever the page happened to
        be showing — which is how a load-correlated `toEqual` failure got in
        (QA7-1).

        The terminal states are the two verdicts. "—" is reachable and is NOT
        one: the evaluation query is keyed on the tree version, so creating
        Hole1 swaps the key and its data is briefly `undefined` — the exact
        window this regex refuses to accept as an answer.
      */
      const status = page.getByTestId("eval-status");
      await expect(status).toHaveText(/Solved|Failed/, { timeout: 120_000 });

      /*
        BOTH ARMS ARE SAMPLED HERE — at the same point in run(), BEFORE the
        arm-specific restore below. Sampling the verdict and the volume after
        the hidden arm's re-show + re-fit (six frames and two round trips
        later than the drawn arm reaches the same line) makes the comparison
        measure that skew rather than the SEL-7 property.
      */
      const settled = (await status.textContent()) ?? "";
      const errors = await page
        .locator('[data-testid^="feature-error-"]')
        .allInnerTexts();
      const volumeAfter = (
        (await page.getByTestId("prop-volume").textContent()) ?? ""
      ).trim();
      const outcome: Outcome = {
        status: settled,
        errors,
        promised,
        volumeBefore,
        volumeAfter,
      };

      if (hide) {
        // Put the body back — and ASSERT on it, so this is a measurement and
        // not a step that runs for scenery: visibility is a view decision, so
        // showing the plate again must not move the number the model reports.
        await setBodyMode(page, rows.plate, "solid");
        await page.getByTestId("view-fit").click();
        await waitForFrames(page, 6);
        expect(
          ((await page.getByTestId("prop-volume").textContent()) ?? "").trim(),
          "showing the body again does not change the reported volume",
        ).toBe(volumeAfter);
      }
      report(
        `Create ${what}`,
        `X ${promised.x}, Y ${promised.y} → ${outcome.status}` +
          `${errors.length > 0 ? ` [${errors.join(" | ")}]` : ""}; ` +
          `volume ${volumeBefore} → ${volumeAfter}`,
      );
      return outcome;
    };

    const drawn = await run(false);
    const hidden = await run(true);
    expect(
      hidden,
      "hiding the placement body changes NOTHING about what Create does",
    ).toEqual(drawn);
  });
});

test.describe("SEL-7 QA — with a finger", () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 768 } });

  test("a tap where a bore-centre diamond stood drills nothing", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const view = page.getByTestId("viewport");
    await openBoredPlateAndBlock(page);
    const rows = await discoverRows(page);
    await armOnPlateTop(page);

    // Where the diamond IS, while the body is drawn — the pixel a finger would
    // aim at a moment before the body is switched off.
    const target = page.getByTestId("hole-point-circle-0");
    const diamond = await target.boundingBox();
    expect(diamond, "the bore-centre diamond has a box to tap").not.toBeNull();
    if (diamond === null) throw new Error("no diamond box");
    const tap = {
      x: diamond.x + diamond.width / 2,
      y: diamond.y + diamond.height / 2,
    };

    // Prove the tap lands on a real target FIRST, or "nothing happened" below
    // is satisfied by a finger that missed.
    const before = await coordinates(page);
    await page.touchscreen.tap(tap.x, tap.y);
    await waitForFrames(page, 2);
    const drilled = await coordinates(page);
    report(
      "tap with the plate DRAWN",
      `${Math.round(tap.x)},${Math.round(tap.y)} — X ${before.x} -> ${drilled.x}, Y ${before.y} -> ${drilled.y}`,
    );
    expect(
      `${drilled.x},${drilled.y}`,
      "the tap reaches the diamond while the body is drawn",
    ).not.toBe(`${before.x},${before.y}`);

    // Re-arm: completing a pick disarms it, and a disarmed overlay mounts no
    // snap nodes at all, which would satisfy every assertion below for free.
    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 30_000,
    });
    await waitForFrames(page, 4);
    const armedCount = await page.locator(SNAP_NODES).count();
    report("snap nodes re-armed, plate drawn", `${armedCount}`);
    expect(armedCount, "the diamonds are back before the hide").toBeGreaterThan(
      0,
    );

    // …now hide the body and tap the same region.
    await setBodyMode(page, rows.plate, "hidden");
    await waitForFrames(page, 6);
    await expect(page.locator(HOLE_POINT_NODES)).toHaveCount(0);
    await expect(view).toHaveAttribute("data-hole-placement-hidden", "1");

    /*
      A CLUSTER, not a single pixel — because hiding a body RE-FRAMES the scene
      (the fit key changes), so the pixel a diamond occupied is not where that
      3-D point projects a moment later. One tap at the remembered spot would
      therefore be a coin flip against a build that left the nodes mounted: it
      might simply miss. Nine taps across a ±64 px block around it cover a 24 px
      target however the refit moved it, and every one of them must be inert.
    */
    const taps: { x: number; y: number }[] = [];
    for (const dx of [-64, 0, 64]) {
      for (const dy of [-64, 0, 64]) {
        taps.push({ x: tap.x + dx, y: tap.y + dy });
      }
    }
    for (const point of taps) {
      await page.touchscreen.tap(point.x, point.y);
      await waitForFrames(page, 2);
    }
    const afterHiddenTap = await coordinates(page);
    report(
      "taps with the plate HIDDEN",
      `${taps.length} taps around ${Math.round(tap.x)},${Math.round(tap.y)} — ` +
        `X ${drilled.x} -> ${afterHiddenTap.x}, Y ${drilled.y} -> ${afterHiddenTap.y}`,
    );
    expect(
      afterHiddenTap,
      "a tap into the air a hidden body used to occupy drills nothing",
    ).toEqual(drilled);
    await expect(page.getByTestId("hole-position")).toContainText(
      "Body hidden",
    );
    await expect(page.locator(HOLE_POINT_NODES)).toHaveCount(0);

    // And the withheld state is not a dead end on a touch frame: showing the
    // body brings the marks back and the coordinate with them.
    await setBodyMode(page, rows.plate, "solid");
    await waitForFrames(page, 6);
    await expect(page.getByTestId("hole-point-center")).toHaveCount(1);
    expect(await coordinates(page)).toEqual(drilled);
  });
});

/* ==========================================================================
   THE GATE ON THE GATE — static, no browser, no stack.

   QA7-1: the wait in `run()` above shipped reading `.not.toBe("Evaluating")`,
   and "Evaluating" is a word the SOLVE cell has never rendered. An assertion
   whose expected value is outside the product's vocabulary cannot fail for the
   reason it was written, so it is satisfied by the first sample and everything
   that depends on it runs against an unsettled page. Same defect class as a CI
   grep that matches its own prose.

   The reported failure was load-correlated, so REVERTING the vacuous wait is
   not a reliable way to reproduce it — one green run would prove nothing. What
   IS deterministic is the vocabulary mismatch, so that is what is gated: the
   allowed strings are read out of `solveSummary` in the product source rather
   than copied here, and every assertion in this file that names the SOLVE cell
   must claim one of them.
   ========================================================================== */

/** `src/features/partBuild.ts` — the SOLVE cell's only vocabulary. */
const PART_BUILD_URL = new URL("../src/features/partBuild.ts", import.meta.url);
/** This file, read as text: the gate's subject is its own source. */
const THIS_SPEC_URL = new URL(import.meta.url);

/**
 * The line as it shipped, kept verbatim as the gate's NEGATIVE CONTROL.
 *
 * A fixture in the wrong shape is a gate that cannot fail for the reason you
 * care about, so the control is not a paraphrase: it is the statement the
 * scanner has to be able to see, in the formatting prettier gave it.
 */
const THE_QA7_1_DEFECT = `await expect
        .poll(() => status.textContent(), { timeout: 60_000 })
        .not.toBe("Evaluating");`;

/** Skip a string/template literal; returns the index of its closing quote. */
function skipStringLiteral(src: string, open: number): number {
  const quote = src[open];
  for (let i = open + 1; i < src.length; i += 1) {
    if (src[i] === "\\") {
      i += 1;
      continue;
    }
    if (src[i] === quote) return i;
  }
  return src.length - 1;
}

/** Skip a `//` or a block comment; returns the index of its last character. */
function skipComment(src: string, open: number): number {
  if (src.startsWith("//", open)) {
    const end = src.indexOf("\n", open);
    return end === -1 ? src.length - 1 : end - 1;
  }
  const end = src.indexOf("*/", open + 2);
  return end === -1 ? src.length - 1 : end + 1;
}

/**
 * Every `expect…;` statement in a source text.
 *
 * Bracket-balanced and literal-aware, for two reasons that both bite here:
 * assertion messages carry parentheses of their own ("(SEL-6b, the stage
 * before this one)") so a naive scan ends a statement in the middle of one;
 * and the negative-control fixture above is an `expect` statement living
 * inside a template literal in THIS file, which must not be mistaken for a
 * real assertion when the gate reads its own source.
 */
function expectStatements(src: string): string[] {
  const out: string[] = [];
  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i] ?? "";
    if (ch === '"' || ch === "'" || ch === "`") {
      i = skipStringLiteral(src, i);
      continue;
    }
    if (ch === "/" && (src[i + 1] === "/" || src[i + 1] === "*")) {
      i = skipComment(src, i);
      continue;
    }
    if (!src.startsWith("expect", i)) continue;
    const before = i === 0 ? " " : (src[i - 1] ?? " ");
    // Prettier breaks a long chain right after `expect`, which is exactly how
    // the QA7-1 line was formatted — so the next MEANINGFUL character is what
    // decides, not the next character. (The negative control caught this: an
    // `after = src[i + 6]` test found 0 statements in the shipped defect.)
    let k = i + "expect".length;
    while (k < src.length && /\s/.test(src[k] ?? "")) k += 1;
    const after = src[k] ?? "";
    // `expect(` or `expect.poll(` only — not `expected`, not `.expect`.
    if (/[\w$.]/.test(before) || (after !== "(" && after !== ".")) continue;
    let depth = 0;
    let j = i;
    for (; j < src.length; j += 1) {
      const c = src[j] ?? "";
      if (c === '"' || c === "'" || c === "`") {
        j = skipStringLiteral(src, j);
      } else if (c === "/" && (src[j + 1] === "/" || src[j + 1] === "*")) {
        j = skipComment(src, j);
      } else if (c === "(" || c === "[" || c === "{") {
        depth += 1;
      } else if (c === ")" || c === "]" || c === "}") {
        depth -= 1;
      } else if (c === ";" && depth === 0) {
        break;
      }
    }
    out.push(src.slice(i, j));
    i = j;
  }
  return out;
}

/** The source text of the first argument of the call opening at `open`. */
function firstArgument(src: string, open: number): string {
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    const c = src[i] ?? "";
    if (c === '"' || c === "'" || c === "`") {
      i = skipStringLiteral(src, i);
    } else if (c === "/" && (src[i + 1] === "/" || src[i + 1] === "*")) {
      i = skipComment(src, i);
    } else if (c === "(" || c === "[" || c === "{") {
      depth += 1;
    } else if (c === ")" || c === "]" || c === "}") {
      depth -= 1;
      if (depth === 0) return src.slice(open + 1, i).trim();
    } else if (c === "," && depth === 1) {
      return src.slice(open + 1, i).trim();
    }
  }
  return src.slice(open + 1).trim();
}

/**
 * The text(s) a matcher argument CLAIMS the cell can read, or `[]` when the
 * argument is an expression the gate cannot evaluate (a variable, another
 * locator's text) and therefore says nothing about.
 */
function claimedTexts(arg: string): string[] {
  // Backticks count: `toHaveText(\`Evaluating\`)` is the same defect wearing
  // different quotes. An INTERPOLATED template is an expression, not a claim.
  const literal = /^(["'`])([\s\S]*)\1$/.exec(arg);
  if (literal !== null) {
    const text = literal[2] ?? "";
    if (literal[1] === "`" && text.includes("${")) return [];
    return [text.replace(/\\(.)/g, "$1")];
  }
  const pattern = /^\/([\s\S]+)\/[dgimsuvy]*$/.exec(arg);
  if (pattern === null) return [];
  // `/Solved|Failed/` and `/(Solved|Failed)/` are the two shapes written here;
  // anything richer falls through to alternatives the vocabulary will refuse,
  // which is the loud direction to fail in.
  const body = (pattern[1] ?? "").replace(/^\((?:\?:)?([\s\S]*)\)$/, "$1");
  return body
    .split("|")
    .map((alt) => alt.replace(/^\^/, "").replace(/\$$/, ""))
    .map((alt) => alt.replace(/\\(.)/g, "$1"));
}

const SOLVE_MATCHERS =
  /\.(?:not\.)?(?:toBe|toEqual|toHaveText|toContainText|toMatch)\(/;

/** Every text an `expect…` statement claims of the thing it asserts on. */
function statementClaims(statement: string): string[] {
  const claims: string[] = [];
  const re = new RegExp(SOLVE_MATCHERS.source, "g");
  for (let m = re.exec(statement); m !== null; m = re.exec(statement)) {
    const open = m.index + m[0].length - 1;
    claims.push(...claimedTexts(firstArgument(statement, open)));
  }
  return claims;
}

/** The `expect…` statements in `src` that assert on the SOLVE cell. */
function solveCellStatements(src: string): string[] {
  const bound: string[] = [];
  const binding = /const (\w+) = page\.getByTestId\("eval-status"\)/g;
  for (let m = binding.exec(src); m !== null; m = binding.exec(src)) {
    bound.push(m[1] ?? "");
  }
  const names = bound.filter((n) => n.length > 0);
  return expectStatements(src).filter(
    (s) =>
      s.includes('"eval-status"') ||
      names.some((n) => new RegExp(`(?<![\\w$.])${n}\\b`).test(s)),
  );
}

test.describe("SEL-7 QA — the gate on the gate (QA7-1)", () => {
  test("no assertion here names a SOLVE state the product cannot render", async () => {
    // (1) THE VOCABULARY, read from the product — never copied into the spec,
    //     so a fifth verdict is inside this gate the day it lands.
    const productSource = await readFile(PART_BUILD_URL, "utf8");
    const fn = /export function solveSummary\([\s\S]*?\n}/.exec(productSource);
    expect(fn, "solveSummary() in src/features/partBuild.ts").not.toBeNull();
    const vocabulary: string[] = [];
    const returns = /return "([^"]*)"/g;
    const body = fn?.[0] ?? "";
    for (let m = returns.exec(body); m !== null; m = returns.exec(body)) {
      vocabulary.push(m[1] ?? "");
    }
    report("SOLVE vocabulary", vocabulary.map((v) => `"${v}"`).join(" | "));
    // Non-vacuity of the vocabulary itself: an extractor that found NOTHING
    // would refuse every claim (loud), but one that found the wrong thing
    // could bless anything — so name the two verdicts this file waits on.
    expect(vocabulary.length, "solveSummary returns literals").toBeGreaterThan(
      1,
    );
    expect(vocabulary).toContain("Solved");
    expect(vocabulary).toContain("Failed");

    // (2) THE NEGATIVE CONTROL, run before the subject: the scanner must be
    //     able to SEE the statement that shipped, and the vocabulary must
    //     refuse it. Without this, "0 violations" is indistinguishable from
    //     "the scanner matched nothing" — the all([]) trap.
    const controlStatements = solveCellStatements(
      `const status = page.getByTestId("eval-status");\n${THE_QA7_1_DEFECT}`,
    );
    expect(
      controlStatements.length,
      "the scanner sees the statement QA7-1 was filed against",
    ).toBe(1);
    const controlClaims = controlStatements.flatMap(statementClaims);
    expect(controlClaims, "…and reads its expected value").toEqual([
      "Evaluating",
    ]);
    expect(
      vocabulary,
      "…and the product's vocabulary refuses it — the gate can go red",
    ).not.toContain("Evaluating");

    // (3) THE SUBJECT: this file.
    const specSource = await readFile(THIS_SPEC_URL, "utf8");
    const statements = solveCellStatements(specSource);
    expect(
      statements.length,
      "this file asserts on the SOLVE cell at all",
    ).toBeGreaterThan(0);
    const claims = statements.flatMap(statementClaims);
    report(
      "SOLVE-cell assertions",
      `${statements.length} statement(s) claiming ${claims
        .map((c) => `"${c}"`)
        .join(", ")}`,
    );
    expect(
      claims.length,
      "…and at least one of them names an expected state",
    ).toBeGreaterThan(0);
    for (const claim of claims) {
      expect(
        vocabulary,
        `the SOLVE cell can render "${claim}" (solveSummary, partBuild.ts)`,
      ).toContain(claim);
    }
  });
});
