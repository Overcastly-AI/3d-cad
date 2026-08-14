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
      const status = page.getByTestId("eval-status");
      await expect
        .poll(() => status.textContent(), { timeout: 60_000 })
        .not.toBe("Evaluating");
      const errors = await page
        .locator('[data-testid^="feature-error-"]')
        .allInnerTexts();

      if (hide) {
        await setBodyMode(page, rows.plate, "solid");
        await page.getByTestId("view-fit").click();
        await waitForFrames(page, 6);
      }
      const volumeAfter = (
        (await page.getByTestId("prop-volume").textContent()) ?? ""
      ).trim();
      const outcome: Outcome = {
        status: (await status.textContent()) ?? "",
        errors,
        promised,
        volumeBefore,
        volumeAfter,
      };
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
