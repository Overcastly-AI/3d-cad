import { expect, test, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import {
  countLitPixels,
  countTokenPixels,
  createPartViaApi,
  distinctCanvasColors,
  seedSession,
  waitForFrames,
} from "./support";

/**
 * FOUNDER DEFECT, 2026-08-01: *"sketches should be more visible. I had an
 * extruded face then was trying to add a sketch and it was snapping back and I
 * couldn't see it."* The snapping half was fixed in `5bd4c46`; this spec gates
 * the VISIBILITY half, which had two independent causes and no coverage at all.
 *
 * A sketch seated on a model face is the one case no spec exercised: every
 * existing pixel census either draws in empty space (`sketcher`, `sketch-spline`
 * — nothing to fight) or measures a COMMITTED sketch that is supposed to be
 * occluded (`part-visibility`). Measured on the real stack before the fix, with
 * a rectangle drawn on the top face of a 20 mm cube:
 *
 *   · `sketch.scribe` ink on canvas: **0 px**, against ~880 px of line drawn.
 *     Coplanar with the face, the ink lost the depth fight everywhere — not
 *     dim, absent.
 *   · the face under it stayed lit machined aluminum, where white scribe
 *     measures **1.32:1** — so even the fragments that survived as MSAA blends
 *     were invisible by any standard.
 *
 * Both assertions below fail on the pre-fix build; the mutation log is at the
 * tail of this file.
 */

/**
 * Calibration baseline as a FRACTION of the canvas's shorter side. Absolute px
 * would walk off the bottom of a 1280x800 frame, which is a supported width.
 */
const CALIBRATION_FRACTION = 0.25;
/**
 * Half-side (mm) of the rectangle the test draws. 5 keeps a 10 mm square well
 * inside the 20 mm face at every zoom, which matters because entering a sketch
 * on a face can re-frame the camera (`5bd4c46` re-frames without re-orienting),
 * so the screen scale is NOT fixed run to run. Everything below is derived from
 * the measured scale rather than from screen constants for that reason.
 */
const RECT_HALF_MM = 5;

interface Point {
  x: number;
  y: number;
}

/** Where the sketch plane sits on screen, measured rather than assumed. */
interface PlaneFrame {
  /** Plane (0,0) — the picked face's centroid — in PAGE coordinates. */
  originPage: Point;
  /** The same point in CANVAS coordinates (what a pixel census indexes). */
  originCanvas: Point;
  /** Screen pixels per plane mm. */
  pxPerMm: number;
}

/** The DRO's live aim, in plane mm. */
async function readDro(page: Page): Promise<Point> {
  return {
    x: Number.parseFloat(await page.getByTestId("dro-x").innerText()),
    y: Number.parseFloat(await page.getByTestId("dro-y").innerText()),
  };
}

/**
 * Locate and scale the sketch plane on screen using the product's OWN readout:
 * park the pointer at three points and read the DRO, which gives the affine map
 * from screen px to plane mm, and invert it.
 *
 * Nothing here is assumed about the framing, deliberately. Entering a sketch on
 * a face can re-frame the camera asynchronously (`5bd4c46` re-frames without
 * re-orienting) and the zoom that lands is not stable run to run — an earlier
 * cut of this spec drew at fixed screen coordinates and passed for the WRONG
 * reason on a wide frame, because the rectangle spilled off the face onto empty
 * background, where there is no solid to lose a depth fight against. Deriving
 * everything from the measured map keeps the rectangle on the stock at any zoom.
 */
async function measurePlaneFrame(page: Page): Promise<PlaneFrame> {
  const box = await page
    .locator('[data-testid="viewport"] canvas')
    .boundingBox();
  expect(box).not.toBeNull();
  const rect = box as NonNullable<typeof box>;
  const probe = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  const span = Math.min(rect.width, rect.height) * CALIBRATION_FRACTION;

  await page.mouse.move(probe.x, probe.y);
  const at0 = await readDro(page);
  await page.mouse.move(probe.x + span, probe.y);
  const atX = await readDro(page);
  await page.mouse.move(probe.x, probe.y + span);
  const atY = await readDro(page);

  // Jacobian: mm moved per screen pixel along each screen axis.
  const a = (atX.x - at0.x) / span;
  const b = (atY.x - at0.x) / span;
  const c = (atX.y - at0.y) / span;
  const d = (atY.y - at0.y) / span;
  const det = a * d - b * c;
  expect(Math.abs(det)).toBeGreaterThan(1e-9);
  // Normal-on to the plane with `up` = the plane's v, so the plane's axes land
  // on the screen's. Asserted rather than assumed, because the census box below
  // is axis-aligned and a rotated frame would quietly mis-sample it.
  expect(Math.abs(b)).toBeLessThan(Math.abs(a) * 0.1);
  expect(Math.abs(c)).toBeLessThan(Math.abs(d) * 0.1);

  // Invert the map at the origin: page px of plane (0,0).
  const originPage = {
    x: probe.x + (d * -at0.x - b * -at0.y) / det,
    y: probe.y + (a * -at0.y - c * -at0.x) / det,
  };
  const pxPerMm = 1 / Math.hypot(a, c);
  expect(pxPerMm).toBeGreaterThan(1);

  return {
    originPage,
    originCanvas: { x: originPage.x - rect.x, y: originPage.y - rect.y },
    pxPerMm,
  };
}

/** Pick the body's TOP face by the centroid z in the pick node's a11y name. */
async function clickTopFace(page: Page): Promise<void> {
  const nodes = page.locator('[data-testid^="plane-pick-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 30_000 });
  const count = await nodes.count();
  let bestZ = -Infinity;
  let bestIndex = 0;
  for (let i = 0; i < count; i += 1) {
    const label = (await nodes.nth(i).getAttribute("aria-label")) ?? "";
    const nums = label.match(/-?\d+(?:\.\d+)?/g) ?? [];
    const z = Number.parseFloat(nums[nums.length - 1] as string);
    if (Number.isFinite(z) && z > bestZ) {
      bestZ = z;
      bestIndex = i;
    }
  }
  await nodes.nth(bestIndex).click();
}

/** Seed a 20 mm cube through the API and open it with the solid on screen. */
async function openCubePart(page: Page): Promise<void> {
  const { token } = await seedSession(page);
  const part = await createPartViaApi(page, token, "Scribe on stock");
  await seedCube(page, token, part.id);
  await page.goto(`/parts/${part.id}`);
  await expect(page.getByTestId("body-inspector")).toBeVisible({
    timeout: 60_000,
  });
  await expect
    .poll(() => distinctCanvasColors(page), { timeout: 20_000 })
    .toBeGreaterThan(24);
}

test.describe("a sketch on a model face is visible while you draw it", () => {
  test("scribe ink draws over the solid, on a blued ground", async ({
    page,
  }) => {
    await openCubePart(page);

    // The founder's flow: re-enter the sketcher on an existing body and seat
    // the new sketch on one of its faces.
    await page.getByTestId("new-sketch").click();
    await expect(page.getByTestId("plane-pick-face")).toBeVisible();
    await page.getByTestId("plane-pick-face").click();
    await clickTopFace(page);
    await expect(page.getByTestId("sketch-step")).toHaveText("On Face", {
      timeout: 30_000,
    });
    // The camera eases normal-on to the picked face; sample after it paints.
    await waitForFrames(page, 30);

    const frame = await measurePlaneFrame(page);
    const half = RECT_HALF_MM * frame.pxPerMm;
    const centre = frame.originPage;

    // Draw a 10 mm square ON the face — coplanar ink, the whole subject here.
    await page.keyboard.press("r");
    await expect(page.getByTestId("tool-rect")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.mouse.click(centre.x - half, centre.y - half);
    await page.mouse.move(centre.x + half, centre.y + half);
    await page.mouse.click(centre.x + half, centre.y + half);
    await expect(page.getByTestId("sketch-save")).toContainText("4 entities");
    // Park the pointer well off the rectangle so the crosshair and the hover
    // affordance are not part of what gets counted.
    await page.mouse.move(centre.x + half * 3, centre.y - half * 3);
    await waitForFrames(page, 20);

    // (1) DEPTH — the ink is on screen at its exact token hex. Scored against
    // the perimeter actually drawn, because the absolute count scales with the
    // framing and the framing is deliberately not fixed here.
    //
    // THE FLOOR WAS 30%, AND THE MODEL BEHIND IT WAS WRONG. The original note
    // claimed the exact-token fraction RISES as the view widens (49% at
    // 40 px/mm, 93% at 6.9 px/mm). Measured on this spec, it falls: **37.1% at
    // 35.5 px/mm, 22.9% at 26.6 px/mm**. The reason is that two of the three
    // things eating the count do not scale with zoom. A 1 px GL line lands on
    // the exact token only where it covers a WHOLE pixel — MSAA blends the rest
    // into the ground, and how much survives is a sub-pixel alignment lottery
    // that changes with every framing. On top of that the sheet's 1 mm grid is
    // fixed in MODEL space, so this 10 mm square is crossed at 40 points no
    // matter the zoom; each crossing blends a slice of scribe away, and 40
    // fixed crossings are a larger share of a SHORTER perimeter. Widening the
    // view therefore costs the count twice.
    //
    // That is why `6d8a8dd` (FB-22, the sketch origin) turned this red without
    // breaking anything: it settles the sketch camera squarely over the face
    // centre instead of off to one side, which is a BETTER framing and a wider
    // one — 35.5 px/mm before, 26.6 after. Nothing about the ink got worse.
    //
    // So the floor is restated around what this gate can actually discriminate.
    // Its power is not 23% vs 30%; it is HUNDREDS vs **ZERO**, which is what
    // the pre-fix build measured when coplanar ink lost the depth test against
    // the face it sits on — everywhere, not dimly. 12% sits at roughly half the
    // worst framing measured and still an order of magnitude clear of the
    // regression it exists to catch, and the absolute floor keeps a pathological
    // framing from satisfying the ratio with a handful of pixels.
    // Mutation-verified: restoring `depthTest` on the active ink drops this to
    // single digits and turns the case red.
    const perimeterPx = 8 * half;
    const ink = await countTokenPixels(page, "#E9F1F8");
    expect(ink).toBeGreaterThan(120);
    expect(ink).toBeGreaterThan(perimeterPx * 0.12);

    // (2) CONTRAST — the face under the sketch is blued, so the scribe has a
    // dark ground rather than a 1.32:1 one. Measured strictly INSIDE the
    // rectangle the modeler just drew (inset clear of its own ink and corner
    // handles), which is by construction a patch of the picked face.
    const inset = half * 0.6;
    const interior = {
      x: Math.round(frame.originCanvas.x - inset),
      y: Math.round(frame.originCanvas.y - inset),
      width: Math.round(inset * 2),
      height: Math.round(inset * 2),
    };
    const lit = await countLitPixels(page, 150, interior);
    expect(lit).toBeLessThan(interior.width * interior.height * 0.05);
  });

  test("a sketch you are NOT editing stays behind the solid", async ({
    page,
  }) => {
    // The other half of the rule: drawing the ACTIVE sketch on top must not
    // turn the viewport into stacked ghost profiles. `Sketch1` made this body,
    // so bringing it back puts it on the base face, under 20 mm of aluminum —
    // it may peek at the silhouette and no more.
    await openCubePart(page);
    const row = page.getByTestId(/^sketch-visibility-/).first();
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    await waitForFrames(page);

    const shown = await countTokenPixels(page, "#C4D2DE");
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "false");
    await waitForFrames(page);
    const hidden = await countTokenPixels(page, "#C4D2DE");

    // It is drawn (the control works)…
    expect(shown).toBeGreaterThan(hidden + 50);
    // …and it is still OCCLUDED: a 20 mm square profile drawn unclipped over
    // this framing is thousands of pixels of ink; a silhouette peek is not.
    expect(shown).toBeLessThan(1500);
  });
});

/**
 * MUTATION EVIDENCE (2026-08-01), measured against the real stack with the app
 * source reverted to the parent commit while this file and its `support.ts`
 * helpers stayed in place.
 *
 * Reverting the WHOLE change is the right control here, not flipping one prop:
 * pre-fix the ink and the body are both opaque and exactly coplanar, so which
 * one survives is decided by three's opaque-queue tie-break, and simply adding
 * a material elsewhere in the scene can flip it. (That was observed: two
 * pre-fix runs of an earlier cut of this spec put ink on screen where the next
 * run put none. A rendering result that depends on material creation order is
 * the argument FOR `depthTest: false`, not a reason to gate on the tie.)
 *
 *  · Assertion 1 (depth): pre-fix `ink = 0` of a 1 600 px perimeter; post-fix
 *    784, three runs identical. Floor 480.
 *  · Assertion 2 (contrast): pre-fix 56 728 lit px inside the 57 600 px
 *    interior box — the face stays bare aluminum end to end; post-fix 0, three
 *    runs identical. Ceiling 2 880.
 *  · Assertion 3 (occlusion, second test): passing `onTop` to `SolvedLayer`'s
 *    ink — the plausible over-reach of this change — draws the base profile
 *    unclipped and takes `shown` past 1 500.
 */
