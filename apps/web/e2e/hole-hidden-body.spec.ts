import { sketch, viewport as viewportTokens } from "@loft/design/tokens";

import { expect, test, type Page } from "./fixtures";

import { labelCentroid, setBodyMode } from "./occludedPlate";
import { seedBoredPlateAndBlock } from "./partSeed";
import { litPoints, type Point } from "./reachability";
import {
  countTokenPixels,
  createPartViaApi,
  SCREENSHOT_DIR,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * SEL-7 — THE HOLE PLACEMENT OVERLAY, WHEN ITS BODY IS SWITCHED OFF.
 *
 * SEL-6 closed the raycast half and SEL-6b closed the offer half for the face
 * marks, the edge band and the FacePatch. `HolePointOverlay` was the one
 * overlay left that never asked about visibility: it mounted its DOM snap
 * nodes and its datum crosshair on EDITOR state alone, so hiding the body
 * mid-command left diamonds floating in empty air that still drilled a real
 * hole into geometry nobody could see.
 *
 * The gate below is written against the acceptance clause verbatim — with the
 * placement body hidden, NO hole-point DOM node is mounted and NO crosshair is
 * drawn; showing it restores every one of them AT ITS PREVIOUS ORDINAL — plus
 * the three things that clause does not say and a green run would otherwise
 * not distinguish:
 *
 *   · the CONTROL. Hiding the OTHER body must change nothing. Without it, a
 *     "gate" that withheld the overlay whenever anything at all was hidden
 *     would pass, and that is a different (worse) product.
 *   · the STAMP. `useViewportPickStamp` runs above the early return, so a
 *     withheld overlay could leave `data-hole-point-hover` set on a body that
 *     is not on screen — the "stamp left set after the overlay unmounts"
 *     failure `pickStamp.ts` names, which would score 100 % for the two specs
 *     that read it. The hover is ARMED FIRST, over a real point on the face, so
 *     the assertion that it clears is at least not vacuous. Measured honesty:
 *     this leg is a GUARD, not the discriminator — with the gate reverted the
 *     stamp still cleared, because clicking the eye moves the pointer off the
 *     canvas and r3f's pointer-out clears the hover anyway. It covers the case
 *     no pointer event follows the hide (the `V` accelerator with the cursor
 *     parked on the face), which no other assertion here reaches.
 *   · the PIXELS. Absence of DOM nodes says nothing about the three `Segments`
 *     crosshairs, which are GL lines with `depthTest={false}` and would
 *     otherwise hang in the void. Counted by token ink, not by eye.
 *
 * Every number the run measures is printed, pass or fail.
 */

/** Print a measured number into the run log — evidence, not narration. */
function report(label: string, value: string): void {
  console.log(`    [SEL-7] ${label}: ${value}`);
}

/** The three DOM snap kinds the armed overlay mounts, as one selector. */
const SNAP_NODES =
  '[data-testid="hole-point-center"], [data-testid^="hole-point-vertex-"], [data-testid^="hole-point-circle-"]';

/**
 * The bored plate + a disjoint block, framed and pinned.
 *
 * Two bodies so one eye can be switched off while the other stays drawn, and
 * the bores so the placement face carries every snap kind (`partSeed.ts`).
 */
async function openBoredPlateAndBlock(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Plate and block");
  await seedBoredPlateAndBlock(page, account.token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("prop-volume")).toContainText(/\d/, {
    timeout: 30_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 30_000 })
    .toBeGreaterThan(24);
  const view = page.getByTestId("viewport");
  await view.evaluate((node) => {
    node.dataset["fitRect"] = "";
  });
  await page.getByTestId("view-fit").click();
  await expect(view).not.toHaveAttribute("data-fit-rect", "", {
    timeout: 20_000,
  });
  await waitForFrames(page, 6);
  // Both bodies have to be addressable, or every question below is unaskable.
  await expect(page.getByTestId("body-row")).toHaveCount(2, {
    timeout: 20_000,
  });
}

/**
 * A face on offer in the hole's FACE pick, located by its own accessible name.
 *
 * `setBodyMode` and `labelCentroid` come from `occludedPlate.ts` — the shared
 * two-body-occlusion module every "what does a HIDDEN body do to a pick" spec
 * draws on. They were local copies here while that file was another agent's
 * in-flight work (a commit cannot import a module its own tree may not
 * contain); it landed in `7ffac16`, so the copies are gone. Its `labelCentroid`
 * is the same regex plus a finiteness assertion, i.e. strictly stronger, and
 * the fixture below relies on nothing else it does.
 */
interface OfferedFace {
  testId: string;
  label: string;
  centroid: { x: number; y: number; z: number };
  /** The 60 × 60 plate lives at y = 0…60; the block at y = 80…100. */
  plate: boolean;
}

/** Every planar face currently offered by the armed face pick. */
async function offeredFaces(page: Page): Promise<OfferedFace[]> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const faces: OfferedFace[] = [];
  for (const node of await nodes.all()) {
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

/**
 * WHICH ROW IS THE PLATE — discovered, never hardcoded.
 *
 * The Bodies panel lists bodies in TREE order and the renderer assigns mesh
 * lumps to them in ordinal order; those agree today and neither is a contract,
 * so the row is found by measurement instead. The measurement is deliberately
 * NOT this item's subject: it hides each row in turn and reads which faces
 * leave the FACE pick's offer (SEL-6b, a shipped and separately gated
 * behaviour), classifying them by the centroid in their own accessible name.
 *
 * A silhouette count — the trick `occludedPlate.ts` uses — cannot answer it
 * here: hiding a body re-runs the fit, and this fixture's two bodies are both
 * squarish, so each fills the reframed viewport to about the same area.
 */
async function discoverPlateRow(page: Page): Promise<number> {
  const drawn = await offeredFaces(page);
  const plateFaces = drawn.filter((f) => f.plate).length;
  const blockFaces = drawn.length - plateFaces;
  expect(
    plateFaces,
    "the plate offers faces while it is drawn",
  ).toBeGreaterThan(0);
  expect(
    blockFaces,
    "the block offers faces while it is drawn",
  ).toBeGreaterThan(0);

  let plateRow: number | null = null;
  const seen: string[] = [];
  for (const row of [0, 1]) {
    await setBodyMode(page, row, "hidden");
    await waitForFrames(page, 6);
    const left = await offeredFaces(page);
    const plateLeft = left.filter((f) => f.plate).length;
    const blockLeft = left.length - plateLeft;
    seen.push(`row ${row} hidden → ${plateLeft} plate + ${blockLeft} block`);
    if (plateLeft === 0 && blockLeft > 0) plateRow = row;
    await setBodyMode(page, row, "solid");
    await waitForFrames(page, 6);
  }
  report(
    "which row owns the plate",
    `${plateFaces} plate + ${blockFaces} block faces drawn; ${seen.join("; ")}`,
  );
  expect(
    plateRow,
    `exactly one row must take the plate's faces out of the offer: ${seen.join("; ")}`,
  ).not.toBeNull();
  return plateRow as number;
}

/** The plate's TOP face — the one carrying the bolt circle (largest z). */
function plateTopFace(faces: readonly OfferedFace[]): OfferedFace {
  const plate = [...faces.filter((f) => f.plate)].sort(
    (a, b) => b.centroid.z - a.centroid.z,
  );
  const [top, next] = plate;
  expect(top, "the plate offers a face").toBeDefined();
  expect(next, "the plate offers more than one face").toBeDefined();
  if (top === undefined || next === undefined) {
    throw new Error("the plate's faces are not on offer");
  }
  expect(
    top.centroid.z - next.centroid.z,
    `the plate's top face must be unambiguous: ${plate.map((f) => `${f.testId}@z${f.centroid.z}`).join(" ")}`,
  ).toBeGreaterThan(1);
  return top;
}

/** Every snap node's test id, in document order — the overlay's current offer. */
async function snapIds(page: Page): Promise<string[]> {
  const ids: string[] = [];
  for (const node of await page.locator(SNAP_NODES).all()) {
    ids.push((await node.getAttribute("data-testid")) ?? "");
  }
  return ids.sort();
}

/**
 * The two crosshair inks on the canvas: the datum frame (etch) and the live
 * drill point (brass).
 *
 * EXACT match, tolerance 0, and that is load-bearing. `countTokenPixels`
 * defaults to ±6 per channel, which on the etch token also catches shaded
 * machined-aluminum: measured 1344 px of "datum ink" on a frame whose datum was
 * a hundred pixels of line, and the count then moved with the camera framing
 * rather than with the overlay. Line materials render un-tonemapped, so the
 * crosshair lands on the canvas at its literal hex and an exact match keeps
 * only the thing being measured (measured: floor 0, drawn 89 + 35, hidden 0).
 */
async function crosshairInk(
  page: Page,
): Promise<{ datum: number; point: number; total: number }> {
  const datum = await countTokenPixels(page, sketch.planeEdge, 0);
  const point = await countTokenPixels(page, viewportTokens.selection, 0);
  return { datum, point, total: datum + point };
}

/**
 * Park the pointer over a point on the placement face and confirm the free
 * placement stamp lit — so "the stamp cleared" later cannot pass for free.
 */
async function armHoverOnFace(page: Page): Promise<Point | null> {
  const view = page.getByTestId("viewport");
  const boxes = (
    await Promise.all(
      (await page.locator(SNAP_NODES).all()).map((n) => n.boundingBox()),
    )
  ).flatMap((b) => (b === null ? [] : [b]));
  const lit = await litPoints(page, { step: 12 });
  let tried = 0;
  for (const point of lit) {
    const clear = boxes.every(
      (b) =>
        point.x < b.x - 16 ||
        point.x > b.x + b.width + 16 ||
        point.y < b.y - 16 ||
        point.y > b.y + b.height + 16,
    );
    if (!clear) continue;
    tried += 1;
    await page.mouse.move(point.x, point.y);
    await waitForFrames(page, 2);
    if ((await view.getAttribute("data-hole-point-hover")) !== null) {
      report(
        "free-placement hover armed",
        `${Math.round(point.x)},${Math.round(point.y)} after ${tried} of ` +
          `${lit.length} lit points (${boxes.length} snap boxes avoided)`,
      );
      return point;
    }
  }
  report(
    "free-placement hover NOT armed",
    `${tried} candidates tried of ${lit.length} lit points, ${boxes.length} snap boxes`,
  );
  return null;
}

test.describe("SEL-7 — a hidden body withholds the hole placement overlay", () => {
  test("hiding the placement body withholds every node and crosshair; showing it restores them", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const view = page.getByTestId("viewport");
    await openBoredPlateAndBlock(page);

    /*
      THE INK FLOOR, measured before the command exists.

      "No crosshair is drawn" is asserted against a floor rather than against a
      literal zero, because a literal zero is a claim about the WHOLE canvas
      that this spec has no business making — anything else the scene draws in
      those two inks would fail it for an unrelated reason. Measured here with
      no hole command open, the floor is 0 px on this fixture (see the exact-
      match note on `crosshairInk`), so the later assertion is as strong as
      `=== 0` while staying honest about what it is comparing.
    */
    const inkFloor = await crosshairInk(page);
    report(
      "crosshair ink with no hole command open (the floor)",
      `datum ${inkFloor.datum} px + live point ${inkFloor.point} px`,
    );

    // --- Arm the command on the plate's top face ---------------------------
    await expect(page.getByTestId("new-hole")).toBeEnabled({ timeout: 30_000 });
    await page.getByTestId("new-hole").click();
    await expect(page.getByTestId("hole-editor")).toBeVisible();

    const plateRow = await discoverPlateRow(page);
    const blockRow = 1 - plateRow;
    const top = plateTopFace(await offeredFaces(page));
    report("placement face", `${top.testId} — ${top.label}`);
    await page.getByTestId(top.testId).click();
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );

    await page.getByTestId("hole-point-pick").click();
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    await waitForFrames(page, 6);

    // --- What is on offer while the body is DRAWN --------------------------
    const drawnIds = await snapIds(page);
    const circles = drawnIds.filter((id) =>
      id.startsWith("hole-point-circle-"),
    ).length;
    const corners = drawnIds.filter((id) =>
      id.startsWith("hole-point-vertex-"),
    ).length;
    report(
      "snap nodes with the plate drawn",
      `${drawnIds.length} total = 1 centre + ${corners} vertices + ${circles} bore centres`,
    );
    expect(drawnIds).toContain("hole-point-center");
    expect(
      corners,
      "the face's own corners are snappable",
    ).toBeGreaterThanOrEqual(4);
    expect(
      circles,
      "the seven bore centres are snappable — the fixture's whole point",
    ).toBe(7);
    await expect(page.getByTestId("hole-frame-origin")).toBeVisible();
    await expect(view).not.toHaveAttribute("data-hole-placement-hidden", /.*/);

    const inkDrawn = await crosshairInk(page);
    report(
      "crosshair ink, plate drawn",
      `datum ${inkDrawn.datum} px + live point ${inkDrawn.point} px`,
    );
    expect(
      inkDrawn.total - inkFloor.total,
      `the datum + point crosshairs are on the canvas to begin with (floor ${inkFloor.total} px)`,
    ).toBeGreaterThan(100);

    // The hover stamp, ARMED — so its clearing below is a measurement, not a
    // tautology satisfied by a pointer that was never over the face.
    const hovered = await armHoverOnFace(page);
    expect(
      hovered,
      "a point on the placement face that lights the free-placement stamp",
    ).not.toBeNull();
    await expect(view).toHaveAttribute("data-hole-point-hover", "1");

    // --- CONTROL: hide the OTHER body — nothing may change -----------------
    await setBodyMode(page, blockRow, "hidden");
    await waitForFrames(page, 6);
    expect(
      await snapIds(page),
      "hiding a body that does not own the placement face changes nothing",
    ).toEqual(drawnIds);
    await expect(page.getByTestId("hole-frame-origin")).toBeVisible();
    await expect(view).not.toHaveAttribute("data-hole-placement-hidden", /.*/);
    await expect(page.getByTestId("hole-placement-hidden-note")).toHaveCount(0);
    await setBodyMode(page, blockRow, "solid");
    await waitForFrames(page, 6);

    // --- THE CLAIM: hide the PLACEMENT body --------------------------------
    await setBodyMode(page, plateRow, "hidden");
    await waitForFrames(page, 6);

    /*
      FOUNDER EVIDENCE (design mandate #4), taken before the assertions rather
      than after them on purpose: the BEFORE half of the pair is this same line
      run against the reverted gate, and the pre-fix code never survives the
      assertions below. Written only under UPDATE_SCREENSHOTS=1 (e2e/fixtures).
    */
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sel7-hole-placement-hidden.png`,
    });

    // (a) no DOM node is mounted…
    await expect(page.locator(SNAP_NODES)).toHaveCount(0);
    await expect(page.getByTestId("hole-frame-origin")).toHaveCount(0);
    // (b) …and the overlay says it is withholding DELIBERATELY. Absence alone
    //     is satisfied by an editor that never opened.
    await expect(view).toHaveAttribute("data-hole-placement-hidden", "1");
    // (c) …the stamp did not survive the withholding.
    await expect(view).not.toHaveAttribute("data-hole-point-hover", /.*/);
    // (d) …no crosshair is drawn: the GL lines went with the nodes.
    const inkHidden = await crosshairInk(page);
    report(
      "crosshair ink, plate hidden",
      `datum ${inkHidden.datum} px + live point ${inkHidden.point} px`,
    );
    expect(
      inkHidden.total,
      `no crosshair may be drawn over the void ` +
        `(hidden: datum ${inkHidden.datum} px, point ${inkHidden.point} px; floor ${inkFloor.total} px; drawn ${inkDrawn.total} px)`,
    ).toBe(inkFloor.total);

    // (e) …and a click where a bore-centre diamond floated drills nothing.
    //     This is the reported defect in one action: under the old overlay the
    //     node was still there, still 24 px wide, and still wrote a position.
    const before = await page.getByTestId("hole-position").textContent();
    if (hovered !== null) await page.mouse.click(hovered.x, hovered.y);
    await waitForFrames(page, 4);
    expect(
      await page.getByTestId("hole-position").textContent(),
      "a click into the empty air a hidden body used to occupy places nothing",
    ).toBe(before);

    // (f) …the editor says WHY, as a view state and not as an alert, and the
    //     pick stays armed so showing the body needs no re-arming.
    await expect(page.getByTestId("hole-position")).toContainText(
      "Body hidden",
    );
    await expect(page.getByTestId("hole-placement-hidden-note")).toBeVisible();
    await expect(page.getByTestId("hole-point-pick")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("hole-pick-error")).toHaveCount(0);

    // --- …AND SHOWING IT RESTORES EVERY ONE OF THEM ------------------------
    await setBodyMode(page, plateRow, "solid");
    // The click in (e) counts as taking the camera by hand, which suppresses
    // the automatic refit on the way back — so the frame would still be the one
    // that suited the block alone, with the plate behind the camera and drei's
    // `Html` hiding marks it has correctly mounted. Re-framing is a real user
    // action and this gate is about the marks, not the camera.
    await page.getByTestId("view-fit").click();
    await waitForFrames(page, 6);
    await expect(page.getByTestId("hole-point-center")).toBeVisible({
      timeout: 20_000,
    });
    const restoredIds = await snapIds(page);
    report(
      "snap nodes after showing the plate again",
      `${restoredIds.length} restored`,
    );
    expect(
      restoredIds,
      "every snap comes back at its previous ordinal — same ids, same count",
    ).toEqual(drawnIds);
    await expect(page.getByTestId("hole-frame-origin")).toBeVisible();
    await expect(view).not.toHaveAttribute("data-hole-placement-hidden", /.*/);
    await expect(page.getByTestId("hole-placement-hidden-note")).toHaveCount(0);
    await expect(page.getByTestId("hole-position")).toContainText(
      "Centre of face",
    );

    const inkBack = await crosshairInk(page);
    report(
      "crosshair ink, plate shown again",
      `datum ${inkBack.datum} px + live point ${inkBack.point} px`,
    );
    expect(
      inkBack.total - inkFloor.total,
      `the crosshairs come back with the body (floor ${inkFloor.total} px)`,
    ).toBeGreaterThan(100);

    // The restored overlay is LIVE, not a corpse: a snap still writes a
    // position. `toHaveCount` on ids cannot tell a mounted node from a mounted
    // node whose handler was lost with the unmount.
    await page.getByTestId("hole-point-circle-0").click();
    await expect(page.getByTestId("hole-position")).toContainText("mm");
    await expect(page.getByTestId("hole-position")).not.toContainText(
      "Centre of face",
    );

    // The same withheld state on a small laptop — the note is the one piece of
    // NEW copy this item adds, and a pinned anchor block is where a narrow rail
    // runs out of room first (design mandate #5: responsive to 1280 × 800).
    await page.setViewportSize({ width: 1280, height: 800 });
    await setBodyMode(page, plateRow, "hidden");
    await waitForFrames(page, 6);
    await expect(page.getByTestId("hole-placement-hidden-note")).toBeVisible();
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/sel7-hole-placement-hidden-1280.png`,
    });
  });
});
