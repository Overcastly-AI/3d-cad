import { expect, test, type Page } from "./fixtures";

import { seedCube } from "./partSeed";
import {
  countLitPixels,
  countTokenPixels,
  createPartViaApi,
  distinctCanvasColors,
  measureInkCoverage,
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
    // The camera eases normal-on to the picked face; sample after it renders.
    const eased = await waitForFrames(page, 30);

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
    const settled = await waitForFrames(page, 20);

    // (1) DEPTH — the ink is on screen at its exact token hex.
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
    // the build measures the moment coplanar ink loses the depth test against
    // the face it sits on — everywhere, not dimly.
    //
    // ONE INSTRUMENT, AND A CALIBRATION GUARD (code review, 2026-08-06). This
    // used to assert BOTH an absolute floor of 120 and `perimeterPx * 0.12`,
    // which at the framing that actually ships is 128 — so the ratio decided
    // nothing the floor had not already decided, and the "12 %" model was
    // decoration on an absolute number. Worse, the ratio is what made the gate
    // framing-COUPLED, and the framing is deliberately free here: `6d8a8dd`
    // (FB-22) improved the sketch camera and turned this red without breaking
    // anything, because a better framing is a wider one and a wider one prints
    // less exact-token ink.
    //
    // The fix is to say out loud what the floor is calibrated AGAINST. The
    // scale is asserted first, in a band, so the next framing change fails HERE
    // with a message naming the reason instead of failing below as a
    // mysteriously thin scribe. Inside the band the absolute count is the whole
    // instrument, and it is the honest one: it is what the defect drives to
    // zero.
    //
    // MEASURED 2026-08-06 on the real stack at 1600x1000: 26.63 px/mm, a
    // 1 065 px perimeter, ink = 244. The mutation — the served
    // `SketchScene.tsx` module rewritten in flight so the active ink's
    // `depthTest: false` becomes `true` — gives **ink = 0**, not the "single
    // digits" an earlier note here claimed. Zero is also what the commit
    // message and the roadmap entry said; this comment was the odd one out.
    expect(
      frame.pxPerMm,
      "the sketch camera re-framed: this gate's ink floor is calibrated for " +
        "~20-40 px/mm (26.6 measured 2026-08-06). Re-measure the floor above " +
        "rather than relaxing this band.",
    ).toBeGreaterThan(20);
    expect(frame.pxPerMm).toBeLessThan(40);
    // THE CENSUS IS BY COVERAGE, NOT BY EXACT EQUALITY (SPEC-4). `ink` below
    // is the exact-token count this gate used to assert on, kept only as
    // evidence: measured 10 times at HEAD on 2026-08-11 it came back ZERO on 5
    // of them with the scribe plainly on screen, because a 1 px GL line lands
    // on its literal token only where it happens to cover a whole pixel. The
    // assertion now sums estimated coverage along the ground→token axis, which
    // anti-aliasing conserves — see `measureInkCoverage`. The box is the
    // rectangle the modeler just drew, so what is counted is ink ON the picked
    // face and nothing else on the canvas.
    const ink = await countTokenPixels(page, "#E9F1F8");
    const margin = half * 1.15;
    const scribeBox = {
      x: Math.round(frame.originCanvas.x - margin),
      y: Math.round(frame.originCanvas.y - margin),
      width: Math.round(margin * 2),
      height: Math.round(margin * 2),
    };
    const scribe = await measureInkCoverage(page, "#E9F1F8", {
      box: scribeBox,
    });

    // INSTRUMENT, NOT DECORATION (CI-4). This census came back ZERO on CI
    // `c6b6c6d` and the run held nothing that could say WHY: ink = 0 with
    // hundreds of canvas colours is a rendering defect, ink = 0 with ~1 colour
    // is a blank readback, and ink = 0 with no renders behind the waits is the
    // harness sampling early. Every number is now recorded on every run — green
    // ones included, because a reading with no baseline proves nothing.
    //
    // `inkNearToken` is the fourth discriminator, and it is the one that
    // settles THIS assertion. Reproduced locally at HEAD on 2026-08-11, 2 runs
    // in 5 in a quiet window: exact-token ink = 0 while the scribe is plainly
    // drawn over the solid, its pixels landing at (190,197,204) — the token
    // blended at ~0.74 coverage over the blued face, i.e. a 1 px GL line that
    // straddles the pixel grid instead of filling it. So a zero here has TWO
    // causes that look identical: the ink losing the depth fight (nothing near
    // the token either) and an anti-aliasing phase miss (hundreds near it).
    // Recording both makes a future red say which, instead of being argued.
    // `ink` and `inkNearToken` stay recorded now that the ASSERTION has moved
    // to `scribe.coverage`: they are the history the new floor was calibrated
    // from, and the pair is what proves a future zero is a phase miss.
    //
    // `scribe` now also carries `axisLength` / `noise` / `noiseT` (REV-1(a)) —
    // the SEPARATION between the ground this box actually has and the token,
    // measured on the same frame. A green run records them for the same reason
    // it records everything else here: noiseT 0.0060 on the blued face is the
    // baseline that makes a future 0.3 legible as "the bluing never landed"
    // instead of an argument (bare lit aluminium measures 0.307 on the harness
    // fixture). `measureInkCoverage` throws above 0.125, so a red run on
    // that path never reaches this attachment — the numbers below are the
    // healthy history it will be read against.
    const census = {
      pxPerMm: frame.pxPerMm,
      ink,
      inkNearToken: await countTokenPixels(page, "#E9F1F8", 48),
      scribe,
      distinctColors: await distinctCanvasColors(page),
      easeWait: eased,
      settleWait: settled,
    };
    await test.info().attach("scribe-census.json", {
      body: JSON.stringify(census, null, 2),
      contentType: "application/json",
    });
    if (process.env.LOFT_CENSUS_LOG) console.log(JSON.stringify(census));

    // THE FLOOR, stated only in the units it was measured in. An earlier draft
    // argued "120 -> 400, so the floor went UP and is NOT relaxed": that
    // compares incommensurable numbers (an exact-token pixel COUNT against a
    // coverage SUM) and, taken as a fraction of the healthy reading, it went
    // the other way — 120/244 = 49 % becomes 400/1168 = 34 %. The comparison is
    // dropped rather than re-argued, because the old floor's apparent
    // strictness was noise anyway: it returned 0 on 5 of 10 HEALTHY runs. The
    // honest argument for this floor is the mutant separation below, nothing else.
    //
    // THE MUTANT IS NOT ZERO, AND THE FIRST DRAFT OF THIS COMMENT SAID IT WAS.
    // Measured 2026-08-12 by flipping BOTH `depthTest: false` sites in
    // `SketchScene.tsx` to `true` and running this spec against the real stack:
    //
    //   healthy   coverage 1168.32   (ink 244, inkNearToken 736, offAxis  99)
    //   depthTest coverage  212.49   (ink   0, inkNearToken   0, offAxis  65)
    //
    // So the exact census and the near-token count BOTH collapse to 0, but
    // coverage does NOT: about a fifth of the ink still reaches the frame,
    // because a coplanar sketch under `depthTest: true` z-fights rather than
    // disappearing, and some fragments win. The separation this gate actually
    // has is 1168 vs 212 — 5.5x end to end — not the "hundreds versus zero" the
    // exact census had.
    //
    // THE FLOOR IS NOT CENTRED, AND A PREVIOUS VERSION OF THIS COMMENT SAID IT
    // WAS ("~2.9x clear of each side", "below ~250 would pass the mutant").
    // Both numbers were wrong. 1168.32 / 400 = 2.92 above; 400 / 212.49 = 1.88
    // below. Geometrically centred would be 498. And the number that matters to
    // a re-calibrator is the MUTANT, 212.49: anything below ~213 passes it, so
    // a 230 floor would still redden. Quote 213, not 250.
    //
    // The floor stays correctly SIGNED across the whole 20-40 px/mm band this
    // spec permits (at 40: mutant ~319 < 400 < healthy ~1755; at 20: 160 < 400
    // < 877), but the margin on the mutant side is only ~1.25x at the top of
    // that band. That is reachable solely by editing source, so it is a
    // calibration note rather than a defect — but do not tighten the band
    // without re-deriving this.
    //
    // AND THE MUTANT IS NOT ONE NUMBER — IT IS A LOTTERY, re-measured 2026-08-13
    // while landing REV-1(a). Four fresh runs at the SAME 26.625 px/mm, mutated
    // by rewriting the served `SketchScene.tsx` in flight (`page.route`, both
    // `depthTest: false` sites → `true`):
    //
    //   coverage 349.48 / 244.09 / 194.00 / 154.55   (offAxis 58 / 65 / 33 / 67)
    //
    // — with 154.55 measured under the PRE-REV-1 helper, i.e. the spread is the
    // product's, not the instrument's. A z-fight decides per fragment which
    // surface wins, and that is not stable run to run, so 212.49 was one draw
    // from this distribution rather than "the mutant reading". The floor still
    // separates every draw (400 / 349.48 = 1.14x at the worst one), but the
    // honest margin is 1.14x, not 1.88x. Healthy re-measured twice on the same
    // day and the same stack: **1168.32** and 1169.30 — the 2026-08-12 record
    // to 0.08 %, which is what proves the separation floor `measureInkCoverage`
    // now applies changed no reading here (it reads noiseT 0.006 on this frame
    // against a 0.125 floor, i.e. it is 20x from firing).
    // Do not quote a single mutant number; quote the worst draw, ~350.
    expect(
      scribe.coverage,
      `the scribe is not on the picked face: ${JSON.stringify(census)}`,
    ).toBeGreaterThan(400);
    // THERE IS NO `offAxis` ASSERTION HERE ANY MORE, AND THAT IS THE FIX
    // (REV-1(b)). This line used to read
    // `expect(scribe.offAxis).toBeLessThan(scribe.pixels)`, which cannot fire:
    // `pixels` is many hundreds whenever `coverage > 400` passes above, and
    // `offAxis` measures 99 on a healthy frame. An `expect` that no reachable
    // frame can redden is not coverage — it is a line the next reader COUNTS as
    // coverage, which is worse than nothing.
    //
    // An absolute ceiling (400, ~4x the healthy 99) was tried in its place and
    // ALSO failed falsification, so it is not here either. Measured 2026-08-13
    // on the real stack, mutating the served `tokens.ts` in flight so the whole
    // scribe draws in brass (#E9F1F8 → #C08A2E) — precisely the "a foreign hue
    // got into the box" defect such a ceiling would defend against:
    //
    //   healthy         offAxis  99   coverage 1168.32
    //   brass scribe    offAxis 101   coverage  257.97   ← the WHOLE ink foreign
    //   depthTest x4    offAxis 33-67
    //
    // 101. A TOTAL hue swap moves the number by two, because `offAxis` only
    // counts pixels that project past `INK_MIN_COVERAGE` along the ground→token
    // axis, and a foreign hue projects SHORT: brass lands at t = 0.295 at full
    // pixel coverage, so every antialiased pixel of it falls under the 0.25
    // floor and is never examined at all. A ceiling low enough to catch that
    // (~150) would sit inside healthy run-to-run noise. And the frame is caught
    // regardless — by `coverage > 400`, at 257.97 — so the ceiling would have
    // been decoration on an assertion that already fires.
    //
    // `offAxis` stays in the census attachment above, where an unfalsifiable
    // number is honest evidence rather than a gate that cannot fail.

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
    // so bringing it back puts it on the base face, under 20 mm of aluminum.
    //
    // IT IS NOW FULLY HIDDEN, AND THAT IS THE FIX, NOT A REGRESSION (FB-7c,
    // 2026-08-06). This used to assert `shown > hidden + 50` — a "silhouette
    // peek" — and the peek was the DEFECT: the origin-datum plane bases were
    // stated in the kernel's Z-up frame while the scene renders Y-up, so
    // Sketch1's ink stood VERTICALLY through the body it had made instead of
    // lying on its base face, and the part sticking out was what this counted.
    // With the frames reconciled the ink is exactly coplanar with the bottom
    // face, which the solid covers completely: 0 px, every time.
    //
    // So the control's non-vacuity is proven where it is actually visible —
    // with the body out of the way — instead of by an artefact of a bug.
    await openCubePart(page);
    const row = page.getByTestId(/^sketch-visibility-/).first();
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    await waitForFrames(page);

    // (1) OCCLUDED: under 20 mm of aluminum, a 20 mm profile prints nothing.
    const overSolid = await countTokenPixels(page, "#C4D2DE");
    expect(overSolid).toBeLessThan(1500);

    // (2) DRAWN: hide the body and the same ink is right there. Without this
    // the assertion above would pass just as happily on a row that does
    // nothing at all.
    await page.getByTestId("body-visibility-0").click();
    await waitForFrames(page);
    const uncovered = await countTokenPixels(page, "#C4D2DE");
    expect(uncovered).toBeGreaterThan(overSolid + 50);

    // (3) …and it is THIS row that draws it: turn the sketch off with the body
    // still hidden and the ink goes with it.
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "false");
    await waitForFrames(page);
    expect(await countTokenPixels(page, "#C4D2DE")).toBeLessThan(
      uncovered - 50,
    );
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
 *    784, three runs identical. (Floor was 480 at THAT framing; the sketch
 *    camera has since been improved and widened — see the calibration guard in
 *    the test. Re-measured 2026-08-06 at 26.63 px/mm: post-fix 244, and the
 *    depth-test mutation still gives exactly 0. Floor 120.)
 *  · Assertion 2 (contrast): pre-fix 56 728 lit px inside the 57 600 px
 *    interior box — the face stays bare aluminum end to end; post-fix 0, three
 *    runs identical. Ceiling 2 880.
 *  · Assertion 3 (occlusion, second test): passing `onTop` to `SolvedLayer`'s
 *    ink — the plausible over-reach of this change — draws the base profile
 *    unclipped and takes `shown` past 1 500.
 */
