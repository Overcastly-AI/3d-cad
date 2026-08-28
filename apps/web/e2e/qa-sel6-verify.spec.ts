import { expect, test, type Page } from "./fixtures";

import {
  bodyScreenRects,
  containsPoint,
  discoverWallRow,
  insetRect,
  labelCentroid,
  labelIsWall,
  openOccludedPlate,
  setBodyMode,
  type ScreenRect,
} from "./occludedPlate";
import { VIEWPORT_CANVAS } from "./perception";
import { litPoints, type Point } from "./reachability";
import { waitForFrames } from "./support";

/**
 * SEL-6 QA VERIFICATION — written by qa-tester, independent of the builder.
 *
 * The builder's own gate (`pick-affordance.spec.ts`) asks a BOOLEAN of every
 * sample point — "did anything answer?" — against a >= 50 % floor, and prints
 * nothing when it passes. Three things that gate cannot see, and this file
 * exists for those three:
 *
 * 1. **WHICH face answered.** "Something answered" is satisfied by the wrong
 *    face just as happily as by the right one. `nearestDrawnHit` is a MINIMUM
 *    over the surviving triangles, and reversing it costs the boolean census
 *    NOTHING — measured, not argued: with it returning the farthest survivor
 *    the census still reads 96.7 % / 94.8 % / 99.2 %, identical to green, while
 *    a fifth of the picks made with both bodies drawn go THROUGH the wall to
 *    the plate behind it. So every leg here records the stamped ordinal, and
 *    the assertions are about the tally: which face dominates, and what share
 *    the occluded body takes. Every face is identified from the marks' own
 *    accessible names, never from a kernel ordinal.
 *
 * 2. **The size of the win.** A gate that only says ">= 50 %" passes at 51 %
 *    after a regression that cost it 45 points — and 50 % is a floor the
 *    OVERHANGS alone could nearly reach on this fixture: the wall covers the
 *    middle 40 mm of a 60 mm plate, so a fix that restored only the unoccluded
 *    third would land around 33 %. The claim being verified is that the
 *    OCCLUDED span answers, so this file holds the same measurement to 85 %
 *    (measured 94.8 % under perspective, 98.2 % since ORTHO-1) and prints the
 *    number whether it passes or fails.
 *
 * 3. **A hand.** No SEL-6 gate ever completed a pick: they all read a hover
 *    stamp. The touch leg here taps where the wall used to be and demands the
 *    shell editor actually OPEN the plate's near face — and that the pick
 *    survives switching the wall back on, which is the cross-surface question
 *    a hover stamp cannot ask.
 *
 * The refusal (SEL-6b — a switched-off body stops OFFERING picks) is restated
 * here without the luminance proxy `qa-sel4-verify.spec.ts` uses, because the
 * SEL-6 commit had to widen that proxy's exclusion zone: loosening a guard in
 * the same change that could break it is the shape that hides a defect. The
 * version below never reads a pixel — it learns the wall's own face ordinals
 * while the wall is drawn and then demands that no point ANYWHERE on the canvas
 * answers with one of them.
 *
 * ## Mutation evidence — every claim here has been SEEN to fail
 *
 * An assertion nobody has watched go red is a hope, so each was run against a
 * deliberately broken build (all reverted; the numbers are from those runs):
 *
 * - **Pre-SEL-6** (`drawnSurfaceRaycast` refuses a hidden nearest hit instead of
 *   seeing past it): census 11.1 %, canvas sweep 10 answers of 1710, touch span
 *   25.0 %. All three legs red, each at the assertion carrying its claim.
 * - **Pre-SEL-6b** (`hiddenPickFilter` -> `OFFER_EVERYTHING`): the wall's six
 *   marks return; the canvas sweep names hidden faces at three points and the
 *   touch leg's offer check fails. The census leg does NOT notice — see the note
 *   in it.
 * - **Farthest drawn hit instead of nearest**: every fraction unchanged; caught
 *   only by the control that scopes its claim to the region the wall covers.
 *   Under perspective that control was a whole-frame SHARE (20 % against a 5 %
 *   ceiling); ORTHO-1 made the share stop meaning what it stood for and it is
 *   now the region itself — see the long note at the assertion. Re-measured
 *   under the same mutation on 2026-08-28: **173 of 838** answers inside the
 *   wall's rect name the plate, against **0 of 841** on the correct build.
 * - **The fix applied to half the model** (see-past only left of scene x = 30):
 *   51.9 % — clears the >= 50 % acceptance floor, caught by the 85 % one.
 * - **Double-sided pick surface + farthest hit**: 94.8 %, controls all green,
 *   caught only by "the dominant face is the plate's NEAR one" (it read the
 *   BACK face, ordinal 8).
 */

/** Print a measured number into the run log — QA evidence, not narration. */
function report(label: string, value: string): void {
  console.log(`    [SEL-6 QA] ${label}: ${value}`);
}

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

/**
 * How far INSIDE the wall's own screen rect a point must be to count as a point
 * the wall covers.
 *
 * One census grid step. Not slack for a wobbly measurement — the rect is known
 * to 0.2 px — but for the one class of answer that is genuinely ambiguous: a
 * ray at the wall's silhouette GRAZES it, and whether the triangle at the very
 * edge is struck is a sub-pixel question the pick is not being asked to settle.
 * It costs almost nothing: the wall covers the plate over 751 x 189 px, so the
 * inset still leaves ~29 x 7 grid points of overlap for a depth-order defect to
 * show up in, and 841 of 1003 answers survive it (measured).
 */
const WALL_INSET_PX = 24;

/** Sub-pixel tolerance when asking whether a point is inside a rect at all. */
const BOUNDARY_PX = 4;

/** A shell face mark on offer, with the position its own label carries. */
interface OfferedFace {
  /** The B-rep ordinal, as the stamp reports it. */
  ordinal: string;
  label: string;
  /** OCCT y of the centroid — the wall is y = 0…20, the plate y = 30…50. */
  y: number;
  wall: boolean;
}

/**
 * Move the pointer and read the stamp ONCE IT HAS SETTLED.
 *
 * `page.mouse.move` resolves when the CDP event is dispatched, not when React
 * has re-rendered and the stamp effect has run. In a census that lag averages
 * out; for a single-point verdict it is a wrong answer.
 */
async function stampAfterMove(
  page: Page,
  point: Point,
  attribute: string,
): Promise<string | null> {
  const viewport = page.getByTestId("viewport");
  await page.mouse.move(point.x, point.y);
  let last = await viewport.getAttribute(attribute);
  for (let i = 0; i < 5; i += 1) {
    await waitForFrames(page, 1);
    const next = await viewport.getAttribute(attribute);
    if (next === last) return next;
    last = next;
  }
  return last;
}

/**
 * Arm the shell pick and wait for its face marks.
 *
 * Every intermediate wait carries an explicit generous timeout, including the
 * ones a fast machine answers instantly. Default 5 s waits are what turn a
 * loaded box into a phantom regression: this leg died twice at
 * `openOccludedPlate`/`armShellPick` while a sibling agent's Playwright run had
 * the CPU, at a DIFFERENT step each time (the tell for contention, per
 * CLAUDE.md), and passed in the next quiet window unchanged.
 */
async function armShellPick(page: Page): Promise<void> {
  await expect(page.getByTestId("new-shell")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("new-shell").click();
  await expect(page.getByTestId("shell-editor")).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.locator('[data-testid^="shell-face-"]').first(),
  ).toBeVisible({ timeout: 20_000 });
  await waitForFrames(page, 6);
}

/** Every shell face ordinal currently on offer, located by its own label. */
async function offeredFaces(page: Page): Promise<OfferedFace[]> {
  const nodes = page.locator('[data-testid^="shell-face-"]');
  await expect(nodes.first()).toBeVisible({ timeout: 20_000 });
  const faces: OfferedFace[] = [];
  for (const node of await nodes.all()) {
    const label = (await node.getAttribute("aria-label")) ?? "";
    const ordinal = ((await node.getAttribute("data-testid")) ?? "").replace(
      "shell-face-",
      "",
    );
    faces.push({
      ordinal,
      label,
      y: labelCentroid(label).y,
      wall: labelIsWall(label),
    });
  }
  return faces;
}

/**
 * The plate's NEAR face — the one a front-view ray reaches first.
 *
 * `openOccludedPlate` frames the part from the FRONT, which looks along +y, so
 * "nearest" is "smallest centroid y" and nothing about the kernel's ordering is
 * assumed. The pick is only a decision if the winner is unambiguous, so the
 * runner-up must be a clear distance behind (the plate's faces sit at y = 30,
 * 40 and 50).
 */
function nearestPlateFace(faces: readonly OfferedFace[]): OfferedFace {
  const plate = [...faces.filter((f) => !f.wall)].sort((a, b) => a.y - b.y);
  const [near, next] = plate;
  expect(near, "the plate offers at least one face").toBeDefined();
  expect(next, "the plate offers more than one face").toBeDefined();
  if (near === undefined || next === undefined) {
    throw new Error("the plate's faces are not on offer");
  }
  expect(
    next.y - near.y,
    `the nearest plate face must be unambiguous: ${plate.map((f) => `${f.ordinal}@y${f.y}`).join(" ")}`,
  ).toBeGreaterThan(1);
  return near;
}

interface StampAnswer {
  point: Point;
  ordinal: string;
}

interface StampCensus {
  sampled: number;
  answered: number;
  fraction: number;
  /** How many points each ordinal absorbed — WHICH face answered, not whether. */
  tally: Map<string, number>;
  /**
   * WHERE each answer was made, kept so a claim can be scoped to a REGION of
   * the frame rather than to the whole of it. A whole-frame share cannot tell
   * "the plate answered past the wall's edge" from "the plate answered through
   * the wall"; a coordinate can.
   */
  answers: StampAnswer[];
}

/** The most-answered ordinal, or null when nothing answered. */
function dominant(census: StampCensus): string | null {
  let best: string | null = null;
  let bestCount = 0;
  for (const [ordinal, count] of census.tally) {
    if (count > bestCount) {
      best = ordinal;
      bestCount = count;
    }
  }
  return best;
}

function describeCensus(census: StampCensus): string {
  const byCount = [...census.tally].sort((a, b) => b[1] - a[1]);
  return (
    `${census.answered}/${census.sampled} = ${pct(census.fraction)} ` +
    `{${byCount.map(([o, n]) => `face ${o}: ${n}`).join(", ") || "nothing answered"}}`
  );
}

/**
 * Sweep the lit silhouette and record WHICH ordinal answers at each point.
 *
 * One round trip per point, which is what the boolean census already costs —
 * reading the attribute's value rather than its nullness is free.
 */
async function stampCensus(
  page: Page,
  points: readonly Point[],
): Promise<StampCensus> {
  const viewport = page.getByTestId("viewport");
  const tally = new Map<string, number>();
  const answers: StampAnswer[] = [];
  let answered = 0;
  for (const point of points) {
    await page.mouse.move(point.x, point.y);
    const stamped = await viewport.getAttribute("data-shell-face-hover");
    if (stamped === null) continue;
    answered += 1;
    tally.set(stamped, (tally.get(stamped) ?? 0) + 1);
    answers.push({ point, ordinal: stamped });
  }
  return {
    sampled: points.length,
    answered,
    fraction: points.length === 0 ? 0 : answered / points.length,
    tally,
    answers,
  };
}

/** `x,y->ordinal`, the form every region-scoped failure message reports in. */
function describeAnswer(answer: StampAnswer): string {
  return `${Math.round(answer.point.x)},${Math.round(answer.point.y)}->${answer.ordinal}`;
}

function describeRect(rect: ScreenRect): string {
  const r = (n: number) => Math.round(n);
  return `x ${r(rect.x0)}..${r(rect.x1)} y ${r(rect.y0)}..${r(rect.y1)}`;
}

/** The stamp must clear off the body, or every census above scored for free. */
async function expectStampClears(page: Page): Promise<void> {
  await page.mouse.move(5, 5);
  await expect(page.getByTestId("viewport")).not.toHaveAttribute(
    "data-shell-face-hover",
    /.*/,
    { timeout: 5_000 },
  );
}

test.describe("SEL-6 QA — the census, and WHICH face answered", () => {
  test("hiding the occluder hands the pick to the plate's NEAR face", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    await openOccludedPlate(page);
    const rows = await discoverWallRow(page);
    report(
      "silhouette after hiding each row",
      `row0 ${rows.lit[0]} lit, row1 ${rows.lit[1]} lit → the WALL is row ${rows.wall}`,
    );

    await armShellPick(page);
    const faces = await offeredFaces(page);
    const wallOrdinals = new Set(
      faces.filter((f) => f.wall).map((f) => f.ordinal),
    );
    const plateOrdinals = new Set(
      faces.filter((f) => !f.wall).map((f) => f.ordinal),
    );
    const near = nearestPlateFace(faces);
    report(
      "faces on offer, both bodies drawn",
      `wall {${[...wallOrdinals].join(",")}} plate {${[...plateOrdinals].join(",")}}; ` +
        `the plate's NEAR face is ${near.ordinal} (${near.label})`,
    );
    expect(wallOrdinals.size, "the wall's faces are on offer").toBeGreaterThan(
      0,
    );

    const census = async () =>
      stampCensus(page, await litPoints(page, { step: 24 }));

    const bothDrawn = await census();
    await setBodyMode(page, rows.wall, "hidden");
    await waitForFrames(page, 6);
    const wallHidden = await census();
    await setBodyMode(page, rows.wall, "solid");
    await waitForFrames(page, 6);
    await setBodyMode(page, rows.plate, "hidden");
    await waitForFrames(page, 6);
    const plateHidden = await census();
    await setBodyMode(page, rows.plate, "solid");
    await waitForFrames(page, 6);

    const legs = [
      ["both drawn", bothDrawn],
      ["WALL (in front) hidden", wallHidden],
      ["plate (behind) hidden", plateHidden],
    ] as const;
    for (const [name, leg] of legs)
      report(`census, ${name}`, describeCensus(leg));
    const record = legs
      .map(([name, leg]) => `${name} ${pct(leg.fraction)}`)
      .join("; ");

    // NON-VACUITY: a stuck stamp would score every leg at 100 %.
    await expectStampClears(page);
    for (const [name, leg] of legs) {
      expect(leg.sampled, `${name}: points sampled`).toBeGreaterThan(40);
    }

    // THE CONTROLS. Neither hiding nothing nor hiding the body BEHIND may move
    // the number, and while both bodies are drawn the face answering over most
    // of the frame is the WALL's — it is the body in front.
    expect(
      bothDrawn.fraction,
      `control, both drawn (${record})`,
    ).toBeGreaterThanOrEqual(0.5);
    const bothDrawnTop = dominant(bothDrawn);
    expect(
      bothDrawnTop !== null && wallOrdinals.has(bothDrawnTop),
      `control, both drawn: the face answering most often must be the WALL's, got ${bothDrawnTop} — ${describeCensus(bothDrawn)}`,
    ).toBe(true);
    // …AND THE OCCLUSION ITSELF, which the dominant ordinal is too blunt to
    // state. `nearestDrawnHit` is a MINIMUM over the survivors; make it return
    // the farthest instead and the pick starts addressing the plate THROUGH the
    // wall standing in front of it — a hit nobody could see they had made —
    // while the wall's own face still wins the count, because the wall is 40 mm
    // tall against the plate's 10 mm and dominates the frame either way
    // (measured under exactly that mutation: face 0 still took 723 of 935
    // answers, so the dominant assertion above passes).
    //
    // THIS WAS A WHOLE-FRAME SHARE UNTIL 2026-08-28, AND THE SHARE WAS A PROXY
    // FOR A REGION. It read "the plate takes < 5 % of all answers", calibrated
    // against 0.6 % measured under the PERSPECTIVE front view this fixture used
    // to open in — where the nearer wall was magnified enough to cover all but a
    // ~0.8 mm sliver of the 60 mm plate, so "the plate answered" and "the plate
    // answered through the wall" were nearly the same statement. ORTHO-1
    // (`9a04a6a`) made named views orthographic and a parallel projection has no
    // magnification, so the plate's two 10 mm overhangs are their true size and
    // legitimately answer: 68 of 1003 points, 6.8 %, against a 5 % ceiling. The
    // app was right and the ceiling was stale — measured here, every one of
    // those 68 lies OUTSIDE the wall's own screen rect (left group max x 420 vs
    // the wall's edge at 424.7; right group min x 1188 vs 1175.3), and ZERO lie
    // inside it at any inset.
    //
    // So the claim is now made where it belongs, over the region the wall
    // covers: inside the wall's rect, every answer must be one of the WALL's
    // faces. That is projection-independent (the region is re-derived from the
    // live frame each run), it needs no calibrated number, and its correct value
    // is zero rather than "small". It is also STRICTLY stronger than the share:
    // the share watched one ordinal, this rejects ANY face of the body behind —
    // including the plate's BACK face, which is the mutation the old control
    // could not see and "the dominant face is the NEAR one" had to catch.
    const regions = await bodyScreenRects(page);
    const covered = insetRect(regions.wall, WALL_INSET_PX);
    report(
      "the region the wall covers",
      `wall ${describeRect(regions.wall)}, plate ${describeRect(regions.plate)}, ` +
        `front/back parallax ${regions.parallaxPx.toFixed(2)} px; probing ${describeRect(covered)}`,
    );
    // The rect is a bounding box of the wall's own face-mark centres, so before
    // any claim is made ON it, check it really is where the wall is: every point
    // the WALL answered at must lie inside it. Not circular — that is the
    // CONVERSE of the claim below, and it holds under the mutation the claim
    // catches (the wall keeps answering over the span with nothing behind it).
    const wallAnsweredOutside = bothDrawn.answers.filter(
      (a) =>
        wallOrdinals.has(a.ordinal) &&
        !containsPoint(insetRect(regions.wall, -BOUNDARY_PX), a.point),
    );
    expect(
      wallAnsweredOutside.map(describeAnswer),
      `the derived rect must be where the wall IS: ${describeRect(regions.wall)}`,
    ).toEqual([]);
    const insideCovered = bothDrawn.answers.filter((a) =>
      containsPoint(covered, a.point),
    );
    // NON-VACUITY: "nothing behind answers here" is free if nothing is sampled
    // here. Measured 841 of the 1003 answers land inside the inset rect.
    expect(
      insideCovered.length,
      `answers sampled inside the wall's own rect — with none, the claim below is free (${describeCensus(bothDrawn)})`,
    ).toBeGreaterThan(400);
    const throughTheWall = insideCovered.filter(
      (a) => !wallOrdinals.has(a.ordinal),
    );
    expect(
      throughTheWall.map(describeAnswer),
      `control: nothing BEHIND the wall may answer where the wall covers it — ` +
        `${throughTheWall.length} of ${insideCovered.length} answers inside ` +
        `${describeRect(covered)} name a face behind it; ${describeCensus(bothDrawn)}`,
    ).toEqual([]);
    expect(
      plateHidden.fraction,
      `control, the body BEHIND hidden (${record})`,
    ).toBeGreaterThanOrEqual(0.5);

    // NOT ASSERTED HERE: "no hidden body's face ever answers". It is the SEL-6b
    // claim and it belongs in the refusal leg below, which sweeps the whole
    // canvas. Restating it over the LIT SILHOUETTE cannot fail: a hidden body's
    // marks sit where the body is not drawn, so the lit grid never visits them
    // — verified by running this leg against `hiddenPickFilter` stubbed to
    // OFFER_EVERYTHING (the pre-SEL-6b behaviour), where the wall's six marks
    // came back and this census still read `{face 6: 128}`. A line no mutation
    // can turn red is false comfort, not a gate.

    // THE CLAIM, three ways the boolean census cannot state it.
    //
    // (a) The acceptance floor SEL-4 set for this overlay, which SEL-6 measured
    //     at 8.5 % before the fix.
    expect(
      wallHidden.fraction,
      `the >= 50 % floor with the occluder hidden (${record})`,
    ).toBeGreaterThanOrEqual(0.5);
    // (b) …and a floor that actually means "the OCCLUDED span answers". The
    //     wall covers the middle 40 mm of a 60 mm plate, so restoring only the
    //     unoccluded overhangs would score around a third and still clear 50 %
    //     on a generous framing. Measured after the fix: 94.8 % under the
    //     perspective front view, 98.2 % since ORTHO-1 made it orthographic.
    expect(
      wallHidden.fraction,
      `the occluded span itself must answer, not just the overhangs (${record})`,
    ).toBeGreaterThanOrEqual(0.85);
    // (c) …with the NEAREST drawn face, not merely a drawn one. Today the pick
    //     surface is FrontSide, so once the occluder is out of the way the
    //     plate's near face is the only candidate a ray can strike and this
    //     reads as a characterisation — but it is the assertion that fails the
    //     moment either half of that changes. Verified by mutation: with the
    //     pick material double-sided and `nearestDrawnHit` returning the
    //     farthest survivor, the census reads `{face 8: 67, face 10: 48, …}` —
    //     the plate's BACK face, addressed straight through its front, at an
    //     unchanged 94.8 % that (a) and (b) both wave through.
    expect(
      dominant(wallHidden),
      `the plate's NEAR face ${near.ordinal} (${near.label}) must be the one that answers — ${describeCensus(wallHidden)}`,
    ).toBe(near.ordinal);
  });
});

test.describe("SEL-6 QA — the refusal, without a luminance proxy", () => {
  test("a hidden body's ordinals answer at NO point on the canvas", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // The `qa-sel4-verify` version of this asks "is this pixel dark, and are
    // its neighbours dark" and then requires the dark points to answer with
    // nothing. That proxy had to be loosened by the SEL-6 commit itself. This
    // one never reads a pixel: it learns the WALL's own face ordinals while the
    // wall is still drawn, hides it, and then sweeps the WHOLE canvas — lit,
    // unlit, silhouette, bench, all of it — demanding that none of those
    // ordinals is ever the answer. Seeing PAST a hidden body must not make the
    // hidden body pickable.
    const viewport = page.getByTestId("viewport");
    await openOccludedPlate(page);
    const rows = await discoverWallRow(page);
    await armShellPick(page);

    const faces = await offeredFaces(page);
    const wallOrdinals = new Set(
      faces.filter((f) => f.wall).map((f) => f.ordinal),
    );
    const plateSet = new Set(
      faces.filter((f) => !f.wall).map((f) => f.ordinal),
    );
    report(
      "face ordinals on offer with both bodies drawn",
      `wall {${[...wallOrdinals].join(",")}} plate {${[...plateSet].join(",")}}`,
    );
    expect(
      wallOrdinals.size,
      "the wall's own planar faces are on offer while it is drawn",
    ).toBeGreaterThan(0);
    expect(
      plateSet.size,
      "the plate's own planar faces are on offer",
    ).toBeGreaterThan(0);
    for (const ordinal of wallOrdinals) {
      expect(
        plateSet.has(ordinal),
        `ordinal ${ordinal} cannot belong to both bodies`,
      ).toBe(false);
    }

    await setBodyMode(page, rows.wall, "hidden");
    await waitForFrames(page, 6);

    /*
      The sweep is over the CANVAS's own rect, not the viewport container's.

      Not tidiness: `litPoints` reads the canvas rect, so a spec that sweeps the
      container silently measures a different region the moment the canvas is
      not flush with it — and the mutation runs proved that happens. Under the
      pre-SEL-6b mutation (every body's marks on offer) the container sweep found
      0 answers in 1710 points, because a hidden body's off-frame `Html` marks
      move the canvas inside its container; the census leg, which reads the
      canvas rect, was unaffected in the same run. A sweep that can be pointed at
      empty space by an unrelated layout shift is not a refusal gate — it is a
      gate that passes for free.
    */
    // `.first()`: the viewport holds TWO canvases since VIEWCUBE-1 — the
    // scene, then the reference cube's own. The scene is first in DOM order.
    const box = await page.locator(VIEWPORT_CANVAS).first().boundingBox();
    expect(box, "the viewport canvas is on screen").not.toBeNull();
    if (box === null) return;
    report(
      "canvas rect swept",
      `${Math.round(box.width)} x ${Math.round(box.height)} at ${Math.round(box.x)},${Math.round(box.y)}`,
    );

    let probed = 0;
    let answered = 0;
    const wallAnswers: string[] = [];
    const plateOrdinals = new Set<string>();
    for (let y = box.y + 12; y < box.y + box.height - 12; y += 28) {
      for (let x = box.x + 12; x < box.x + box.width - 12; x += 28) {
        probed += 1;
        await page.mouse.move(x, y);
        const stamped = await viewport.getAttribute("data-shell-face-hover");
        if (stamped === null) continue;
        answered += 1;
        if (wallOrdinals.has(stamped)) {
          // Re-read with the settle loop before calling it a defect: a bare
          // read can lag one point behind the pointer.
          const settled = await stampAfterMove(
            page,
            { x, y },
            "data-shell-face-hover",
          );
          if (settled !== null && wallOrdinals.has(settled)) {
            wallAnswers.push(`${Math.round(x)},${Math.round(y)}->${settled}`);
          }
        } else {
          plateOrdinals.add(stamped);
        }
      }
    }
    report(
      "full-canvas sweep with the WALL hidden",
      `${probed} points probed, ${answered} answered, ` +
        `${wallAnswers.length} named a HIDDEN wall face, ` +
        `drawn-plate ordinals seen {${[...plateOrdinals].join(",")}}`,
    );

    await expectStampClears(page);

    expect(probed, "points swept across the whole canvas").toBeGreaterThan(500);
    // Non-vacuity: the sweep has to be able to find SOMETHING, or "no wall
    // ordinal answered" is satisfied by a dead pointer.
    expect(
      answered,
      "points that answered with any face at all — a dead stamp passes the refusal for free",
    ).toBeGreaterThan(40);
    expect(
      plateOrdinals.size,
      "the still-drawn plate answers with at least one of its own faces",
    ).toBeGreaterThan(0);
    expect(
      wallAnswers,
      `points naming a HIDDEN body's face: ${wallAnswers.slice(0, 12).join(" ")}`,
    ).toEqual([]);
  });
});

test.describe("SEL-6 QA — TOUCH", () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 768 } });

  test("a TAP where the wall stood opens the plate's face, and the pick survives showing the wall again", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    // A viewport pick that only answers a mouse is half-shipped, and no SEL-6
    // gate ever completed a pick at all — they read a hover stamp. The fix
    // lives inside `raycast`, which a tap reaches through the same pointer-event
    // path, so it either works for both or the gate never asked.
    await openOccludedPlate(page);
    const rows = await discoverWallRow(page);
    await setBodyMode(page, rows.wall, "hidden");
    await waitForFrames(page, 6);
    await armShellPick(page);

    const faces = await offeredFaces(page);
    expect(
      faces.filter((f) => f.wall).map((f) => f.label),
      "the hidden wall offers no shell face mark (SEL-6b)",
    ).toEqual([]);
    const near = nearestPlateFace(faces);
    report(
      "faces on offer with the wall hidden",
      faces.map((f) => `${f.ordinal} ${f.label}`).join(" | "),
    );

    /*
      WHERE THE WALL STOOD, in MODEL terms rather than in stale pixels.

      Hiding a body re-runs the fit (`Viewport.tsx` — the hidden count is part
      of the fit key), so a screen coordinate measured while the wall was drawn
      addresses different geometry once it is not; an intersection of the two
      frames' lit grids is an accident, not a region. What does not move is the
      fixture: the wall spans x = 10…50 of a plate that spans x = 0…60, so the
      middle THIRD of the plate's lit extent is inside the wall's former span
      with room to spare for fit margin. Every point below is therefore a point
      the wall used to cover.
    */
    const lit = await litPoints(page, { step: 12 });
    expect(
      lit.length,
      "the plate is on screen with the wall hidden",
    ).toBeGreaterThan(40);
    const xs = lit.map((p) => p.x);
    const [left, right] = [Math.min(...xs), Math.max(...xs)];
    const span = right - left;
    const inSpan = lit.filter(
      (p) => p.x > left + span / 3 && p.x < right - span / 3,
    );

    // …and clear of every 24 px mark, so the tap lands on the SURFACE. This is
    // the whole point of SEL-4/SEL-6: the body is the target, not the dot.
    const boxes = (
      await Promise.all(
        (await page.locator('[data-testid^="shell-face-"]').all()).map((n) =>
          n.boundingBox(),
        ),
      )
    ).flatMap((b) => (b === null ? [] : [b]));
    expect(
      boxes.length,
      "the plate's own marks are measurable — with none, 'clear of every mark' is free",
    ).toBeGreaterThan(0);
    /** Signed gap to the NEAREST mark's box: positive means outside all of them. */
    const clearance = (p: Point): number =>
      Math.min(
        ...boxes.map((b) =>
          Math.max(
            b.x - p.x,
            p.x - (b.x + b.width),
            b.y - p.y,
            p.y - (b.y + b.height),
          ),
        ),
      );
    // THE CLAIM, restated on a touch-sized frame before any tap: the span the
    // wall used to cover answers, and answers with the plate's NEAR face.
    // Measured 82.1 % here against 94.8 % at 1600 × 1000 under the perspective
    // front view, and 78.6-82.1 % against 98.2 % since ORTHO-1 — the difference is
    // this framing, not the pick: the plate is a 240 × 40 px strip, so the rows
    // at its top and bottom graze the z = 0 / z = 10 faces.
    const scan = await stampCensus(page, inSpan);
    report("stamps over the wall's former span", describeCensus(scan));
    expect(
      scan.fraction,
      `the wall's former span answers on a touch frame too (${describeCensus(scan)})`,
    ).toBeGreaterThanOrEqual(0.5);
    expect(
      dominant(scan),
      `and with the plate's NEAR face ${near.ordinal} (${near.label}) — ${describeCensus(scan)}`,
    ).toBe(near.ordinal);

    // The tap point: the one with the most room around it that addresses that
    // near face. A positive gap already means the point is outside every mark's
    // box, so the hit can only be the SURFACE; 12 px — half a mark — is the
    // margin for the marks moving a hair between the measurement and the tap,
    // NOT a fingertip allowance, because Playwright taps the exact point. On a
    // 240 × 40 px strip carrying six 24 px marks a larger demand cannot be met
    // at all (measured best: ~26 px).
    const candidates = [...inSpan].sort((a, b) => clearance(b) - clearance(a));
    let target: Point | null = null;
    for (const point of candidates) {
      if (clearance(point) <= 12) break;
      const stamped = await stampAfterMove(
        page,
        point,
        "data-shell-face-hover",
      );
      if (stamped !== near.ordinal) continue;
      target = point;
      report(
        "touch target",
        `${Math.round(point.x)},${Math.round(point.y)} — ${Math.round(clearance(point))} px clear of ` +
          `all ${boxes.length} marks, addresses face ${stamped}, inside the wall's former ` +
          `span (x ${Math.round(left)}…${Math.round(right)})`,
      );
      break;
    }
    expect(
      target,
      `a point in the wall's former span, > 12 px clear of every mark, addressing the plate's near face ` +
        `${near.ordinal}: ${inSpan.length} of ${lit.length} lit points, x ${Math.round(left)}…${Math.round(right)}`,
    ).not.toBeNull();
    if (target === null) return;

    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "No faces open — a sealed hollow",
      { timeout: 15_000 },
    );
    await page.touchscreen.tap(target.x, target.y);
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
      { timeout: 10_000 },
    );
    const pressed = page.locator(
      '[data-testid^="shell-face-"][aria-pressed="true"]',
    );
    await expect(pressed).toHaveCount(1, { timeout: 15_000 });
    await expect(pressed).toHaveAttribute(
      "data-testid",
      `shell-face-${near.ordinal}`,
      { timeout: 15_000 },
    );

    // CROSS-SURFACE: switching the wall back on restores its six marks and
    // refits the camera, and the pick — keyed by full-precision signature, not
    // by the transient overlay index — must still be the SAME plate face.
    await setBodyMode(page, rows.wall, "solid");
    await waitForFrames(page, 6);
    const restored = await offeredFaces(page);
    expect(
      restored.filter((f) => f.wall).length,
      "showing the wall puts its faces back on offer",
    ).toBeGreaterThan(0);
    await expect(page.getByTestId("shell-open-count")).toHaveText(
      "1 face open",
      { timeout: 15_000 },
    );
    await expect(pressed).toHaveCount(1, { timeout: 15_000 });
    await expect(pressed).toHaveAttribute(
      "data-testid",
      `shell-face-${near.ordinal}`,
      { timeout: 15_000 },
    );
  });
});
