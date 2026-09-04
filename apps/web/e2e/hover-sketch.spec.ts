// The TOKENS subpath, not the package root: the root re-exports the Tailwind
// preset, whose `tailwindcss/plugin` import Node's ESM loader cannot resolve
// (that package has no `exports` map), so importing it here fails the whole
// spec file at collection with "No tests found".
import { proposal } from "@loft/design/tokens";

import { expect, test, type Page } from "./fixtures";
import {
  createPartViaApi,
  SCREENSHOT_DIR,
  seedSession,
  withStableSessionEmail,
} from "./support";

/**
 * FLOW-1 — hover a face, sketch on it (founder report 2026-08-14).
 *
 * The complaint: starting a sketch made you name the VERB before the NOUN.
 * Click Sketch, then hunt for the face. This suite drives the answer the way a
 * user meets it — rest the real pointer on a real face, and click the thing
 * that appears with a real mouse at its real centre.
 *
 * Two assertions here are deliberately awkward, and both are awkward on
 * purpose:
 *
 *  - the affordance is clicked with `page.mouse.click` at the box's centre and
 *    cross-checked with `elementFromPoint`, never `locator.click({force})`.
 *    A forced click skips the only check that asks whether a user could have
 *    hit the thing, and this repo has already shipped a control no real mouse
 *    could reach behind a 4/4-green spec.
 *  - the plane the proposal authors is compared BYTE-FOR-BYTE against the one
 *    the toolbar's Sketch -> pick-a-face flow authors for the same face. That
 *    the sketch "opened" is not the property that matters; that the two paths
 *    cannot silently drift into different geometry is.
 */

/** The chip's box, in page coordinates, or null when it is not on screen. */
async function proposalBox(page: Page) {
  return page.getByTestId("sketch-proposal").boundingBox();
}

/** Rest the pointer at a point — a move, a jiggle, then a settle. */
async function restAt(page: Page, x: number, y: number): Promise<void> {
  await page.mouse.move(x, y);
  await page.mouse.move(x + 1, y);
  await page.mouse.move(x, y);
}

/** The `body.faces()` ordinal the viewport says the pointer is addressing. */
async function hoveredFace(page: Page): Promise<string | null> {
  return page.getByTestId("viewport").getAttribute("data-hovered-face");
}

/**
 * A canvas point that lands on the body, found by asking the app rather than by
 * assuming where the camera framed it. Returns the point AND the face ordinal,
 * so a caller can tell "the pointer moved off the body" from "the same face".
 */
async function findBodyPoint(
  page: Page,
): Promise<{ x: number; y: number; ordinal: string }> {
  const frame = await page.getByTestId("viewport").boundingBox();
  if (frame === null) throw new Error("the viewport has no box");
  const cx = frame.x + frame.width / 2;
  const cy = frame.y + frame.height / 2;
  // Spiral out from the frame's centre: the fit framed the body there, and the
  // first hit is therefore near the middle of a large face rather than on an
  // edge, which is what makes the pick stable.
  for (const radius of [0, 30, 60, 90, 120]) {
    const offsets: readonly (readonly [number, number])[] = [
      [0, 0],
      [radius, 0],
      [0, radius],
      [-radius, 0],
      [0, -radius],
      [radius, radius],
      [-radius, -radius],
    ];
    for (const [dx, dy] of offsets) {
      const x = Math.round(cx + dx);
      const y = Math.round(cy + dy);
      await restAt(page, x, y);
      const ordinal = await hoveredFace(page);
      if (ordinal !== null) return { x, y, ordinal };
    }
  }
  throw new Error(
    "no canvas point addressed a face — the body never rendered, or the " +
      "body stopped being interactive at idle",
  );
}

/** Draw a rectangle (two clicks) and persist it; wait for the solve. */
async function sketchRectangleAndSave(page: Page): Promise<void> {
  await page.keyboard.press("r");
  await expect(page.getByTestId("tool-rect")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.mouse.click(650, 420);
  await page.mouse.move(980, 640);
  await page.mouse.click(980, 640);
  await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
  await page.getByTestId("sketch-save").click();
  await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Build a 10 mm base box on XY — a solid with six planar faces to rest on. */
async function buildBaseBox(page: Page): Promise<void> {
  await page.getByTestId("new-sketch").click();
  await page.getByTestId("plane-XY").click();
  await expect(page.getByTestId("sketch-step")).toHaveText("On XY");
  await sketchRectangleAndSave(page);
  await expect(page.getByTestId("new-extrude")).toBeEnabled({
    timeout: 30_000,
  });
  await page.getByTestId("new-extrude").click();
  await expect(page.getByTestId("extrude-distance")).toHaveValue("10");
  await page.getByTestId("extrude-distance").press("Enter");
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
    timeout: 30_000,
  });
}

/** Open a part workspace with a base box already built. */
async function openPartWithBox(page: Page): Promise<void> {
  const account = await seedSession(page);
  const part = await createPartViaApi(page, account.token, "Hover to sketch");
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("viewport")).toBeVisible();
  await buildBaseBox(page);
}

test.describe("hover a face to sketch on it", () => {
  test("rests propose, sweeps do not, and a real click accepts", async ({
    page,
  }) => {
    await openPartWithBox(page);

    // --- nothing is armed, and the pointer is off the body ------------------
    await expect(page.getByTestId("sketch-proposal")).toHaveCount(0);

    const spot = await findBodyPoint(page);

    // --- a SWEEP proposes nothing -------------------------------------------
    // The dwell is the whole reason this affordance does not fight the
    // viewport. Cross the body without stopping and no note may be written.
    for (let i = 0; i < 12; i += 1) {
      await page.mouse.move(spot.x - 60 + i * 10, spot.y);
    }
    await expect(page.getByTestId("sketch-proposal")).toHaveCount(0);

    // --- a REST proposes -----------------------------------------------------
    await restAt(page, spot.x, spot.y);
    const chip = page.getByTestId("sketch-proposal");
    await expect(chip).toBeVisible({ timeout: 5_000 });

    // It addresses the face the viewport says is under the pointer — not "a"
    // face. A note that named a different face than the one lit would be worse
    // than no note at all.
    await expect(chip).toHaveAttribute("data-face-index", spot.ordinal);

    // --- the box is REAL ----------------------------------------------------
    // Measured, not assumed. Three separate zero-area defects this month each
    // presented as "the control is there and cannot be touched", and every one
    // of them passed a `toBeVisible()`.
    const box = await proposalBox(page);
    expect(box, "the proposal has no box at all").not.toBeNull();
    if (box === null) return;
    expect(box.width, `chip width: ${JSON.stringify(box)}`).toBeGreaterThan(0);
    expect(box.height, `chip height: ${JSON.stringify(box)}`).toBeGreaterThan(
      0,
    );
    // The dense target floor (WCAG 2.2 SC 2.5.8), met by SIZE.
    expect(box.height).toBeGreaterThanOrEqual(proposal.chipHeight);
    expect(box.width).toBeGreaterThanOrEqual(proposal.chipWidth);

    // --- it is NEAR THE CURSOR ----------------------------------------------
    // The acceptance criterion, as a number: the chip's nearest edge sits one
    // short move from the pointer, never across the frame.
    const nearestX =
      box.x > spot.x ? box.x - spot.x : spot.x - (box.x + box.width);
    const nearestY =
      box.y > spot.y ? box.y - spot.y : spot.y - (box.y + box.height);
    expect(
      Math.max(nearestX, nearestY),
      `chip ${JSON.stringify(box)} vs cursor ${spot.x},${spot.y}`,
    ).toBeLessThanOrEqual(proposal.offset + 1);
    // ...and never UNDER the cursor, which would occlude the face it describes.
    const underCursor =
      spot.x >= box.x &&
      spot.x <= box.x + box.width &&
      spot.y >= box.y &&
      spot.y <= box.y + box.height;
    expect(underCursor, "the chip sits under the cursor").toBe(false);

    // --- a REAL pointer can reach it ----------------------------------------
    const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    const reached = await page.evaluate(({ x, y }) => {
      const hit = document.elementFromPoint(x, y);
      return hit === null
        ? "(nothing)"
        : (hit.closest("[data-testid]")?.getAttribute("data-testid") ??
            hit.tagName);
    }, centre);
    expect(
      reached,
      "elementFromPoint at the chip's centre resolves to something else, so a " +
        "real mouse cannot hit it however green a forced click would be",
    ).toBe("sketch-proposal");

    // --- accept it, with the user's own mechanism ---------------------------
    const datumWrite = page
      .waitForResponse(
        (r) => r.url().includes("/features") && r.request().method() === "POST",
        { timeout: 30_000 },
      )
      .catch(() => null);
    await page.mouse.click(centre.x, centre.y);
    const response = await datumWrite;
    expect(
      response,
      "a real click at the chip's centre produced no on_face datum write",
    ).not.toBeNull();
    expect(response?.status()).toBe(201);

    // The sketch is open, seated on the face that was hovered.
    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 30_000,
    });
    // ...and the proposal is gone: a command is open, so nothing may be offered.
    await expect(page.getByTestId("sketch-proposal")).toHaveCount(0);
  });

  test("Enter accepts the showing proposal, as the chip says it does", async ({
    page,
  }) => {
    await openPartWithBox(page);
    const spot = await findBodyPoint(page);
    await restAt(page, spot.x, spot.y);

    const chip = page.getByTestId("sketch-proposal");
    await expect(chip).toBeVisible({ timeout: 5_000 });
    // The chip PRINTS the key, which is the only reason a mouse user would
    // ever learn it. If the glyph and the binding drift apart, the affordance
    // is teaching a key that does nothing — so assert the glyph, not just the
    // behaviour.
    await expect(chip).toContainText("↵");

    const datumWrite = page
      .waitForResponse(
        (r) => r.url().includes("/features") && r.request().method() === "POST",
        { timeout: 30_000 },
      )
      .catch(() => null);
    await page.keyboard.press("Enter");
    const response = await datumWrite;
    expect(
      response,
      "the chip advertises Enter and Enter did nothing",
    ).not.toBeNull();
    expect(response?.status()).toBe(201);
    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 30_000,
    });
  });

  test("the plane it authors is byte-identical to Sketch then pick that face", async ({
    page,
  }) => {
    await openPartWithBox(page);

    /** The `params` of the next `on_face` datum POST. */
    const nextDatumParams = async (
      act: () => Promise<void>,
    ): Promise<unknown> => {
      const pending = page.waitForRequest(
        (r) => r.url().includes("/features") && r.method() === "POST",
        { timeout: 30_000 },
      );
      await act();
      const request = await pending;
      const body = request.postDataJSON() as {
        feature: { type: string; params: unknown };
      };
      expect(body.feature.type).toBe("datum");
      return body.feature.params;
    };

    const spot = await findBodyPoint(page);

    // --- (1) the established path: Sketch -> Pick a face -> click the face ---
    // Driven through the pick overlay's own node for the SAME ordinal the
    // pointer was addressing, so both flows name one face.
    const viaToolbar = await nextDatumParams(async () => {
      await page.getByTestId("new-sketch").click();
      await page.getByTestId("plane-pick-face").click();
      await page
        .getByTestId(`plane-pick-face-${spot.ordinal}`)
        .click({ timeout: 20_000 });
    });
    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 30_000,
    });

    // Back out without saving, so the second flow starts from model idle.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("sketch-strip")).toHaveCount(0, {
      timeout: 20_000,
    });

    // --- (2) the proposal ----------------------------------------------------
    const again = await findBodyPoint(page);
    expect(
      again.ordinal,
      "the camera moved between the two flows, so they would be comparing " +
        "different faces and the identity assertion would be vacuous",
    ).toBe(spot.ordinal);

    const viaProposal = await nextDatumParams(async () => {
      await restAt(page, again.x, again.y);
      const chip = page.getByTestId("sketch-proposal");
      await expect(chip).toBeVisible({ timeout: 5_000 });
      const box = await chip.boundingBox();
      if (box === null) throw new Error("the proposal has no box");
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    });

    // THE assertion. Not "a sketch opened" — that is true of a wrong plane too.
    expect(JSON.stringify(viaProposal)).toBe(JSON.stringify(viaToolbar));
  });
});

/**
 * Founder shots. BEFORE is not a mock: it is this same build with the pointer
 * on the face and the dwell not yet elapsed, which is pixel-for-pixel the state
 * the product was in before this change — the face lit, nothing offered.
 */
function captureAt(width: number, height: number, slug: string) {
  test.describe(`founder capture ${width}x${height}`, () => {
    test.use({ viewport: { width, height } });

    test(`hover-to-sketch, ${slug}`, async ({ page }) => {
      // Outside the email swap: it edits the rendered header text, and a
      // `page.goto` in between would throw the swap away.
      await openPartWithBox(page);
      // Iso, then fit — through the view rail's own buttons. The build leaves
      // the camera in the sketch's plan view, where a box photographs as a flat
      // rectangle and "rest on a FACE" is exactly what the picture cannot show.
      await page.getByTestId("view-iso").click();
      await page.waitForTimeout(1200);
      await page.getByTestId("view-fit").click();
      await page.waitForTimeout(1200);
      await expect(page.getByTestId("view-cube")).toBeVisible();
      await withStableSessionEmail(page, async () => {
        const spot = await findBodyPoint(page);
        await restAt(page, spot.x, spot.y);
        await expect(page.getByTestId("sketch-proposal")).toBeVisible({
          timeout: 5_000,
        });

        /**
         * The pair is captured from ONE frame, with only the new layer
         * switched off for the BEFORE. Two reasons, and the second is the
         * important one.
         *
         * (a) Determinism. Capturing "before" by racing the dwell is a race,
         *     and it lost: the 1600x1000 leg failed on `toHaveCount(0)`
         *     because the note had already been written by the search that
         *     found the face.
         * (b) Honesty. Hiding exactly the new element and nothing else gives a
         *     pixel-aligned pair where the ONLY difference is the change under
         *     review — same camera, same lit face, same chrome. A "before"
         *     shot from a different camera would flatter the diff, and one
         *     with the pointer off the body would attribute the pre-existing
         *     face highlight (SEL-1) to this change.
         *
         * This is the same posture `withStableSessionEmail` already takes: a
         * DOM tweak for the frame, not a mock of the product.
         */
        const setLayer = async (display: string) => {
          await page.evaluate((value) => {
            const layer = document.querySelector<HTMLElement>(
              '[data-testid="sketch-proposal-layer"]',
            );
            if (layer !== null) layer.style.display = value;
          }, display);
        };

        await setLayer("none");
        await expect(page.getByTestId("sketch-proposal")).toBeHidden();
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/hover-sketch-before-${slug}.png`,
        });

        await setLayer("");
        await expect(page.getByTestId("sketch-proposal")).toBeVisible();
        await page.screenshot({
          path: `${SCREENSHOT_DIR}/hover-sketch-after-${slug}.png`,
        });
      });
    });
  });
}

captureAt(1280, 800, "1280x800");
captureAt(1600, 1000, "1600x1000");
