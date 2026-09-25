/**
 * W3-EXIT — A FINGER ON EVERY PARAMETRIC GAUGE (nine at W3 exit, eleven with CRAFT-9c).
 *
 * Every reach measurement this project has taken on these instruments was
 * MOUSE-driven, at 1280x800 and 1600x1000. A 24x24 grip is a fine mouse target
 * and a failing touch target, so the whole "the affordance is reachable"
 * evidence base is silent on the hand this spec uses.
 *
 * Four measurements per control, and nothing softer:
 *
 *  1. **hit-target area** in CSS px, both axes (a 0 in either axis is an
 *     un-styled control, not a mis-laid-out one — this repo has shipped four
 *     distinct zero-area controls);
 *  2. **reachability by the user's own mechanism** — `document.elementFromPoint`
 *     at the control's centre must resolve to the control. Never
 *     `toBeVisible()`, which is a box property and has passed for a control
 *     clipped out of the frame; never `click({ force: true })`, which disables
 *     the only check that asks whether a user COULD have pressed it;
 *  3. **real touch input** through `Input.dispatchTouchEvent`, not a synthetic
 *     mouse click at the same coordinates;
 *  4. **spacing to the nearest neighbouring target** — two 44 px targets 2 px
 *     apart are one ambiguous target.
 *
 * ## The settle, named out loud
 *
 * Burial/occlusion in this viewport is decided by a rotating per-frame budget
 * that converges in 16-21 s quiet and up to 31 s under load. Any reading taken
 * before it drains is a reading of a different state, and a BEFORE/AFTER pair
 * straddling it attributes to the gauge everything that moved on that clock.
 * Every census below calls {@link expectGaugeSettled} FIRST, and the
 * before/after pair in the occlusion case calls it on both sides.
 */
import { expect, test, type Page } from "./fixtures";
import { GAUGE_IDS, MOUNTS, SECTION_XZ, type Mount } from "./gaugeMounts";
import { projectedTrack, REACH_FLOOR } from "./gaugeProbe";
import { installSceneProbe, waitForCameraRest } from "./invariants";
import { createFeature } from "./partSeed";
import { createPartViaApi, seedSession } from "./support";
import {
  centreOf,
  expectGaugeSettled,
  Finger,
  gapBetween,
  hitTestAt,
  measureTarget,
  nearestGap,
  printCensus,
  TOUCH_FLOOR_PX,
  type Point,
  type TouchTarget,
  WCAG_AA_FLOOR_PX,
} from "./touchTargets";

/**
 * A tablet-class context. `hasTouch` is what makes `ontouchstart` present and
 * `navigator.maxTouchPoints` non-zero, which is what any feature-detecting code
 * in the app would branch on — measuring touch in a mouse context would let a
 * `matchMedia("(pointer: coarse)")` branch we do not have hide from the probe.
 */
test.use({ hasTouch: true, viewport: { width: 1280, height: 800 } });

/** Every DOM control a gauge publishes, resolved against the live page. */
async function censusOf(page: Page, gaugeId: string): Promise<TouchTarget[]> {
  const ids = [`${gaugeId}-handle`, `${gaugeId}-readout`, `${gaugeId}-steps`];
  // The sleeve is ONE band on a straight track and N on an arc, published as
  // `-sleeve` then `-sleeve-1..N`. Enumerated from the DOM rather than guessed:
  // an id assembled by template is invisible to a literal grep, and the count
  // is a function of the tessellation, which is a function of the value.
  const sleeves = await page
    .locator(`[data-testid^="${gaugeId}-sleeve"]`)
    .evaluateAll((nodes) =>
      nodes.map((n) => n.getAttribute("data-testid") ?? ""),
    );
  const out: TouchTarget[] = [];
  for (const id of [...ids, ...sleeves.filter((s) => s !== "")]) {
    out.push(await measureTarget(page, id));
  }
  return out;
}

const byName = (census: TouchTarget[], name: string): TouchTarget => {
  const found = census.find((t) => t.name === name);
  if (found === undefined) throw new Error(`no census row for ${name}`);
  return found;
};

/** The mount's panel field, as a string — the gauge never owns its value. */
async function fieldValue(page: Page, mount: Mount): Promise<string> {
  return page.getByTestId(mount.field).inputValue();
}

/**
 * Two points on the drawn track: where a finger would press, and where it would
 * end up. The midpoint is deliberately NOT the grip — it is where the arrow
 * tells you to aim.
 */
async function trackGesture(
  page: Page,
  gaugeId: string,
): Promise<{ from: Point; to: Point }> {
  const points = await projectedTrack(page, gaugeId);
  const mid = points[Math.floor(points.length / 2)] as Point;
  const apex = points[points.length - 1] as Point;
  const seat = points[0] as Point;
  const dx = apex.x - seat.x;
  const dy = apex.y - seat.y;
  const len = Math.hypot(dx, dy) || 1;
  // 60 px along the track's own direction: far enough to cross several
  // graduations at any camera this suite frames, short enough to stay in frame.
  return {
    from: mid,
    to: { x: mid.x + (dx / len) * 60, y: mid.y + (dy / len) * 60 },
  };
}

// --- THE CENSUS --------------------------------------------------------------

for (const mount of MOUNTS) {
  test.describe(`touch census — ${mount.id}`, () => {
    test(`hit targets are sized and reachable`, async ({ page }) => {
      // P1-T2 CLOSED 2026-09-18 — the annotation that used to sit here is gone
      // because it did its job. The pattern COUNT grip's own centre resolved to
      // `timeline-way` at both widths when this pass was written; it now
      // resolves to ITSELF, at (831,646) on 1280x800 and (1062,832) on
      // 1600x1000 — the far rail moved up out of the bottom chrome. The
      // `test.fail()` reddened for PASSING, which is the whole reason to
      // annotate a known gap rather than delete the case: a closed gap has to
      // announce itself.
      await installSceneProbe(page);
      await mount.open(page);
      await expect(page.getByTestId(`${mount.id}-handle`)).toHaveCount(1);
      // NAMED SETTLE. Every number below is taken in the drained state, so two
      // mounts' censuses are comparable and the drag's before/after pair cannot
      // straddle a burial pass.
      await expectGaugeSettled(page, `${mount.id} census`);

      const census = await censusOf(page, mount.id);
      printCensus(mount.id, census);

      const grip = byName(census, `${mount.id}-handle`);
      const readout = byName(census, `${mount.id}-readout`);
      const sleeve = byName(census, `${mount.id}-sleeve`);

      // A `tag: "none"` instrument publishes no readout BY DESIGN — the pattern
      // mounts two gauges on one feature and only one may speak for the pair —
      // so grading it like the rest would file a design decision as a zero-area
      // defect. Asserted rather than tolerated, with the sibling that DOES
      // carry a tag as the companion proving the locator shape resolves at all.
      if (mount.tag === "none") {
        await expect(page.getByTestId(`${mount.id}-readout`)).toHaveCount(0);
        // The SPEAKER is named by the mount rather than hard-coded here: two
        // verbs now mount a silent instrument (pattern count, hole depth), and
        // a companion that always looked for the pattern's tag would pass the
        // hole's silence for the wrong reason — or fail it for none.
        expect(
          mount.speaker,
          `${mount.id} is silent but names no gauge that speaks for it`,
        ).toBeDefined();
        await expect(
          page.getByTestId(`${mount.speaker ?? "none"}-readout`),
        ).toHaveCount(1);
      }

      // ZERO-AREA GUARD, and the companion that proves the locator resolves.
      // `toHaveCount(1)` above is that companion for the grip: an assertion
      // that can only pass when the node exists cannot be vacuous.
      const sized =
        mount.tag === "none" ? [grip, sleeve] : [grip, readout, sleeve];
      for (const target of sized) {
        expect(
          target.box,
          `${target.name} has no box at all — the control is absent or ` +
            `display:none, not merely small`,
        ).not.toBeNull();
        const box = target.box as NonNullable<typeof target.box>;
        expect(
          Math.min(box.width, box.height),
          `${target.name} measures ${box.width}x${box.height} — a 0 in either ` +
            `axis means the STYLE was never applied, not that the layout is ` +
            `tight (four such controls have shipped in this repo)`,
        ).toBeGreaterThan(0);
      }

      // REACHABILITY BY THE USER'S OWN MECHANISM.
      expect(
        grip.reaches,
        `the ${mount.id} grip's own centre resolves to ${grip.resolvesTo}, ` +
          `so a finger aimed at the middle of the target hits something else`,
      ).toBe(true);
    });

    /**
     * THE TOUCH FLOOR, as its own case rather than a fourth assertion above.
     *
     * It is `test.fail()` on all nine, and an annotation that broad has to name
     * exactly ONE gap or it becomes a blanket excuse: a case marked
     * expected-fail is satisfied by failing ANYWHERE, so bundling the 44 px
     * floor with the zero-area and reach guards would have let a future
     * zero-area regression hide inside an annotation written about target size.
     * Split, each annotation covers the one assertion underneath it.
     */
    test(`the grip meets the touch target floor`, async ({ page }) => {
      test.fail(
        true,
        `every gauge grip is 24x24 — WCAG 2.2 AA exactly, and 20 px under the ` +
          `44 px touch floor (P1 in docs/UI-REVIEW.md)`,
      );
      await installSceneProbe(page);
      await mount.open(page);
      await expectGaugeSettled(page, `${mount.id} touch floor`);

      const grip = await measureTarget(page, `${mount.id}-handle`);
      const gripBox = grip.box as NonNullable<typeof grip.box>;
      expect(
        Math.min(gripBox.width, gripBox.height),
        `the ${mount.id} grip is ${gripBox.width}x${gripBox.height} CSS px. ` +
          `WCAG 2.2 SC 2.5.8 (AA) floor is ${WCAG_AA_FLOOR_PX}; the TOUCH ` +
          `floor (SC 2.5.5 / Apple HIG) is ${TOUCH_FLOOR_PX}`,
      ).toBeGreaterThanOrEqual(TOUCH_FLOOR_PX);
    });

    test(`a real finger drag on the grip moves the value`, async ({ page }) => {
      // All nine pass as of 2026-09-18. The count gauge used to fail here at
      // `data-grabbed` — the diagnostic half of this case earning its keep,
      // because it proved the finger never reached the control and so pointed
      // at the burial rather than at a dead handler.
      await installSceneProbe(page);
      await mount.open(page);
      await expectGaugeSettled(page, `${mount.id} grip drag`);

      const grip = await measureTarget(page, `${mount.id}-handle`);
      const box = grip.box as NonNullable<typeof grip.box>;
      const from = centreOf(box);
      const gesture = await trackGesture(page, mount.id);
      const before = await fieldValue(page, mount);

      const dx = gesture.to.x - gesture.from.x;
      const dy = gesture.to.y - gesture.from.y;

      const finger = await Finger.open(page);
      await finger.down(from);
      // Prove the gesture was RECEIVED before asking whether it did anything:
      // "the value did not move" and "the touch never reached the control" are
      // different defects with different fixes, and they look identical from
      // the field alone.
      const grabbed = await page
        .getByTestId(`${mount.id}-handle`)
        .getAttribute("data-grabbed");
      const steps = 8;
      for (let i = 1; i <= steps; i += 1) {
        await finger.move({
          x: from.x + (dx * i) / steps,
          y: from.y + (dy * i) / steps,
        });
      }
      await finger.up();

      // BOTH DIRECTIONS, and this is a correction to the first draft rather
      // than belt-and-braces. Several of these instruments open AT a bound —
      // revolve seeds at 360, which IS `MAX_REVOLVE_DEG` — so a one-way drag
      // reports `grabbed=true, 360 -> 360`, which reads exactly like a dead
      // handle and is in fact a correctly-clamped one. A control that refuses
      // to move in EITHER direction is the defect; one that refuses in one is
      // a bound.
      let after = await fieldValue(page, mount);
      let direction = "outward";
      if (after === before) {
        await finger.drag(from, { x: from.x - dx, y: from.y - dy });
        after = await fieldValue(page, mount);
        direction = "inward (outward was clamped or inert)";
      }
      await finger.detach();

      console.log(
        `[touch drag] ${mount.id}: grabbed=${grabbed} ` +
          `${before} -> ${after} ${direction} ` +
          `(from ${from.x.toFixed(0)},${from.y.toFixed(0)})`,
      );
      expect(
        grabbed,
        `a touchStart on the ${mount.id} grip did not put it in the grabbed ` +
          `state, so the finger never reached the control at all`,
      ).toBe("true");
      expect(
        after,
        `a real finger drag across the ${mount.id} grip, in BOTH directions, ` +
          `left the value at ${before}`,
      ).not.toBe(before);
    });

    test(`a real finger drag on the drawn shaft moves the value`, async ({
      page,
    }) => {
      await installSceneProbe(page);
      await mount.open(page);
      await expectGaugeSettled(page, `${mount.id} sleeve drag`);

      const gesture = await trackGesture(page, mount.id);
      // The press point must BE the gauge before it is pressed — otherwise a
      // null result measures whatever else is under the shaft's midpoint.
      const under = await hitTestAt(
        page,
        gesture.from,
        `[data-gauge="${mount.id}"]`,
      );
      const before = await fieldValue(page, mount);

      const finger = await Finger.open(page);
      await finger.drag(gesture.from, gesture.to);
      let after = await fieldValue(page, mount);
      // Same both-directions rule as the grip case: a bound is not a dead
      // control, and telling them apart needs the second gesture.
      let direction = "outward";
      if (after === before) {
        await finger.drag(gesture.from, {
          x: 2 * gesture.from.x - gesture.to.x,
          y: 2 * gesture.from.y - gesture.to.y,
        });
        after = await fieldValue(page, mount);
        direction = "inward (outward was clamped or inert)";
      }
      await finger.detach();

      console.log(
        `[touch shaft] ${mount.id}: midpoint resolves to ${under.described} ` +
          `(this gauge: ${under.owned}) — ${before} -> ${after} ${direction}`,
      );
      expect(
        after,
        `a real finger drag from the ${mount.id} shaft midpoint ` +
          `(${gesture.from.x.toFixed(0)},${gesture.from.y.toFixed(0)}, which ` +
          `resolves to ${under.described}), in BOTH directions, left the ` +
          `value at ${before}`,
      ).not.toBe(before);
    });

    test(`a finger can reach the numeric cell`, async ({ page }) => {
      // EVERY TAGGED GAUGE FAILS THIS, and the companion inside proves the
      // zero is a statement about the product: a keyboard digit opens exactly
      // one cell on the same locator, in the same state, immediately before.
      // `pattern-count-gauge` is deliberately NOT annotated — it carries
      // `tag="none"`, takes the other branch, and passes.
      test.fail(
        mount.tag !== "none",
        "tapping a gauge readout opens nothing; typing is keyboard-only " +
          "(P1 in docs/UI-REVIEW.md)",
      );
      await installSceneProbe(page);
      await mount.open(page);
      await expectGaugeSettled(page, `${mount.id} numeric entry`);

      if (mount.tag === "none") {
        // NO TAG BY DESIGN, so there is no on-canvas number to tap and none to
        // type into. Stated as an assertion rather than a skip: a skipped case
        // is a case nobody reads, and the consequence for a touch user is real
        // — the pattern COUNT can only be typed in the panel field, 800 px from
        // the instrument that draws it.
        await expect(page.getByTestId(`${mount.id}-readout`)).toHaveCount(0);
        await expect(page.getByTestId(mount.field)).toHaveCount(1);
        console.log(
          `[touch cell] ${mount.id}: tag="none" by design; the number lives ` +
            `only in the ${mount.field} panel field`,
        );
        return;
      }

      const readout = await measureTarget(page, `${mount.id}-readout`);
      const box = readout.box as NonNullable<typeof readout.box>;

      const cell = page.getByTestId(`${mount.id}-readout`).locator("input");

      // THE COMPANION FOR THE NEGATIVE ASSERTION, and it is not optional: a
      // `toHaveCount(0)` whose locator can never resolve is the cheapest member
      // of this repo's "cannot observe its failure mode" family. A keyboard
      // digit is the route that IS known to work, so proving it opens a cell
      // here is what makes the zero below a statement about the product.
      //
      // The poll is a NAMED settle, not padding: drei `Html` commits its
      // children in a SEPARATE React root, so between the digit that opens the
      // cell and the input existing there is a window of a frame or two.
      // Measured without it — 0 cells, on a route that works.
      await page.getByTestId(`${mount.id}-handle`).focus();
      await page.keyboard.press("7");
      const cellsViaKeyboard = await cell
        .count()
        .then(async (n) =>
          n > 0
            ? n
            : await expect
                .poll(() => cell.count(), { timeout: 5_000 })
                .toBeGreaterThan(0)
                .then(() => cell.count()),
        )
        .catch(() => 0);
      await page.keyboard.press("Escape");
      expect(
        cellsViaKeyboard,
        `the keyboard route into the ${mount.id} cell is itself broken, so ` +
          `the touch measurement below would be meaningless`,
      ).toBeGreaterThan(0);
      await expect(cell).toHaveCount(0);

      // NOW THE FINGER. A tap on the number the gauge is asserting, given the
      // same window the keyboard route needed.
      const finger = await Finger.open(page);
      await finger.tap(centreOf(box));
      await page.waitForTimeout(1_000);
      const cellsViaTouch = await cell.count();
      await finger.detach();

      console.log(
        `[touch cell] ${mount.id}: readout ${box.width.toFixed(1)}x` +
          `${box.height.toFixed(1)}, keyboard opens ${cellsViaKeyboard} cell(s), ` +
          `tap opens ${cellsViaTouch}`,
      );
      expect(
        cellsViaTouch,
        `tapping the ${mount.id} readout opened no input. Typing is the ` +
          `PRECISION half of direct manipulation and a tablet has no physical ` +
          `keyboard, so on touch this gauge has a drag and no way to enter a ` +
          `number at all`,
      ).toBeGreaterThan(0);
    });
  });
}

// --- SPACING, WHICH ONLY THE TWO-INSTRUMENT MOUNT CAN FAIL --------------------

test.describe("touch census — adjacent targets", () => {
  test("the pattern mount's two grips are not one ambiguous target", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const pattern = MOUNTS.find((m) => m.id === "pattern-count-gauge") as Mount;
    await pattern.open(page);
    await expectGaugeSettled(page, "pattern spacing census");

    const targets: TouchTarget[] = [];
    for (const id of [
      "pattern-count-gauge-handle",
      "pattern-spacing-gauge-handle",
      "pattern-count-gauge-readout",
      "pattern-spacing-gauge-readout",
    ]) {
      targets.push(await measureTarget(page, id));
    }
    printCensus("pattern (both instruments)", targets);

    const count = targets[0] as TouchTarget;
    const near = nearestGap(count, targets);
    expect(near, "the pattern census found no neighbour to measure").not.toBe(
      null,
    );
    const gap = (near as { name: string; gap: number }).gap;
    console.log(
      `[touch spacing] pattern-count grip's nearest target is ` +
        `${(near as { name: string }).name} at ${gap.toFixed(1)} px`,
    );
    // Two 44 px targets need a channel between them or a finger cannot choose.
    // 8 px is the floor a dense instrument can defend; below it the two grips
    // are one target wearing two names.
    expect(
      gap,
      `the two pattern grips are ${gap.toFixed(1)} px apart — at that spacing ` +
        `a finger cannot choose which instrument it is pulling`,
    ).toBeGreaterThanOrEqual(8);
  });

  test("every gauge id in the app is covered by this pass", async () => {
    // A census that walks what it happens to find can only grade work somebody
    // remembered to do. The ids are derived ONCE, in `gaugeMounts.ts`, and
    // this asserts the mount table covers every one of them — so a tenth gauge
    // added without a touch mount fails here rather than being silently
    // unmeasured.
    const mounted = new Set(MOUNTS.map((m) => m.id));
    const missing = GAUGE_IDS.filter((id) => !mounted.has(id));
    expect(
      missing,
      `gauge ids with no touch mount: ${missing.join(", ")}`,
    ).toEqual([]);
    expect(MOUNTS.length).toBe(GAUGE_IDS.length);
  });
});

// --- THE PATTERN COUNT RAIL, AT BOTH WIDTHS ----------------------------------

/**
 * WHAT IS UNDER THE PATTERN COUNT GRIP, AT 1280x800 AND AT 1600x1000.
 *
 * This case was written to test a hypothesis, REFUTED it, and has since watched
 * the defect it found get fixed — all three of which are why both readings stay.
 *
 * The first census found the count grip's own centre resolving to
 * `timeline-way` at 1280x800 — the small-laptop floor CLAUDE.md mandates — and
 * the obvious read was a RESPONSIVE defect: an instrument that fits at the size
 * every existing gauge spec happens to run at (1600x1000, the config default)
 * and falls under the bottom chrome at the size we promise. Measured, it was
 * `timeline-way` at BOTH — 24x24 at (927,756) and at (1194,986) — so it was
 * never a layout-width artefact, and a lone "unreachable at 1280" would have
 * sent the fix to a breakpoint instead of to the rail's seat.
 *
 * FIXED 2026-09-18, and the pair is what shows it cleanly: the grip now
 * resolves to ITSELF at (831,646) and (1062,832) — the far rail moved up out of
 * the chrome at both widths, not merely at one. The assertion below is now a
 * plain gate rather than an annotated gap.
 */
test.describe("touch census — the pattern count rail at two widths", () => {
  for (const size of [
    { width: 1280, height: 800 },
    { width: 1600, height: 1000 },
  ]) {
    test(`${size.width}x${size.height}: what is under the count grip`, async ({
      page,
    }) => {
      await page.setViewportSize(size);
      await installSceneProbe(page);
      const pattern = MOUNTS.find(
        (m) => m.id === "pattern-count-gauge",
      ) as Mount;
      await pattern.open(page);
      await expectGaugeSettled(page, `pattern count @ ${size.width}`);

      const grip = await measureTarget(page, "pattern-count-gauge-handle");
      const box = grip.box as NonNullable<typeof grip.box>;
      console.log(
        `[touch width] ${size.width}x${size.height}: count grip ` +
          `${box.width.toFixed(1)}x${box.height.toFixed(1)} at ` +
          `(${box.x.toFixed(0)},${box.y.toFixed(0)}) — its own centre resolves ` +
          `to ${grip.resolvesTo}`,
      );
      expect(
        grip.reaches,
        `at ${size.width}x${size.height} the pattern COUNT grip sits at ` +
          `(${box.x.toFixed(0)},${box.y.toFixed(0)}) and its own centre ` +
          `resolves to ${grip.resolvesTo} — the instrument is drawn where the ` +
          `chrome already is, so neither a finger nor a mouse can take it`,
      ).toBe(true);
    });
  }
});

// --- THE PROBES' OWN NEGATIVE CONTROLS ---------------------------------------

/**
 * AN ASSERTION NOBODY HAS SEEN FAIL IS NOT YET A GATE.
 *
 * Most of the assertions above were born red against the real app — the 44 px
 * floor on all nine grips, the reach check on the pattern count grip, the tap
 * on every readout — so they have demonstrated they can observe their subject.
 * Three could not: the zero-area guard, the spacing floor and the coverage
 * check all PASSED on the live app from the first run, which is exactly the
 * shape of an assertion that can never fire. They are exercised here against a
 * deliberately broken input, once, so each has been seen to fail.
 */
test.describe("touch census — the probes' own negative controls", () => {
  test("the zero-area guard fires, and the reach check cannot replace it", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const pattern = MOUNTS.find((m) => m.id === "pattern-count-gauge") as Mount;
    await pattern.open(page);
    await expectGaugeSettled(page, "zero-area control");

    const healthy = await measureTarget(page, "pattern-spacing-gauge-handle");
    const healthyBox = healthy.box as NonNullable<typeof healthy.box>;
    expect(Math.min(healthyBox.width, healthyBox.height)).toBeGreaterThan(0);

    await page.addStyleTag({
      content: `[data-testid="pattern-spacing-gauge-handle"]{width:0 !important}`,
    });
    const starved = await measureTarget(page, "pattern-spacing-gauge-handle");
    const starvedBox = starved.box as NonNullable<typeof starved.box>;
    console.log(
      `[control] starved grip ${starvedBox.width}x${starvedBox.height}, ` +
        `elementFromPoint=${starved.resolvesTo}, reaches=${starved.reaches}`,
    );
    expect(
      Math.min(starvedBox.width, starvedBox.height),
      "the zero-area guard would not have fired on a starved control",
    ).toBe(0);

    // AND THE REACH CHECK DOES NOT COLLAPSE WITH IT — measured, not assumed.
    // A 0x24 box's "centre" is a point on its own left edge, and the 12 px
    // collar child overflows past it, so `elementFromPoint` still answers with
    // the control. The two guards are independently necessary, which is the
    // whole reason both are in the census: this repo has four shipped
    // zero-area controls and a reach probe alone would have caught none of the
    // ones whose style was simply never applied.
    expect(starved.reaches).toBe(true);
  });

  test("the spacing floor and the coverage check fire", () => {
    // `gapBetween` must report an edge-to-edge channel, not a centre distance:
    // two 24 px grips with a 2 px gutter are 2 apart, and two that overlap are 0.
    expect(
      gapBetween(
        { x: 0, y: 0, width: 24, height: 24 },
        { x: 26, y: 0, width: 24, height: 24 },
      ),
    ).toBeCloseTo(2, 6);
    expect(
      gapBetween(
        { x: 0, y: 0, width: 24, height: 24 },
        { x: 10, y: 10, width: 24, height: 24 },
      ),
    ).toBe(0);

    // The spacing assertion reads `nearestGap`, so drive THAT. Deliberately not
    // by nudging a DOM node in the live scene: measured, drei `Html` gives every
    // mount a TRANSFORMED container, so a `position: fixed` child is positioned
    // against that container and lands 1332 px away instead of 2 — a negative
    // control that silently tests nothing.
    const pair: TouchTarget[] = [
      {
        name: "a",
        box: { x: 100, y: 100, width: 24, height: 24 },
        resolvesTo: "self",
        reaches: true,
      },
      {
        name: "b",
        box: { x: 126, y: 100, width: 24, height: 24 },
        resolvesTo: "self",
        reaches: true,
      },
    ];
    const gap = (nearestGap(pair[0] as TouchTarget, pair) as { gap: number })
      .gap;
    expect(gap, "the spacing floor would not have fired").toBeLessThan(8);

    // Coverage: drop a mount and the check must NAME the hole rather than
    // reporting an empty difference.
    const holed = new Set(MOUNTS.map((m) => m.id).slice(1));
    const missing = GAUGE_IDS.filter((id) => !holed.has(id));
    expect(missing).not.toEqual([]);
    expect(missing).toContain("extrude-depth");
  });
});

// --- THE STATE THE USER ACTUALLY LANDS IN ------------------------------------

/**
 * THE REVOLVE ARC AT ITS OWN SEEDED ANGLE — 360 — WHICH NO GAUGE SPEC HAS EVER
 * MEASURED, AND WHICH IS WHERE EVERY USER STARTS.
 *
 * `MOUNTS` opens revolve at 120 degrees, deliberately and with its reason
 * written down: the seed is 360, which IS `MAX_REVOLVE_DEG`, so a one-way drag
 * there is clamped and reports `grabbed=true, 360 -> 360` — a bound reading
 * exactly like a dead handle. That framing is right for measuring the
 * INSTRUMENT and wrong for measuring the PRODUCT.
 *
 * ## Why this censuses 16 points and not the midpoint
 *
 * The first version of this case pressed the arc's MIDPOINT, because that is
 * what the shaft case does for a straight track. It reported the midpoint
 * resolving to `revolve-submit` on one run — the editor's own Submit button
 * under the pixel the drawing invites you to grab — and then PASSED on the
 * next, with the midpoint at (555,487) on the instrument instead of (273,505)
 * on the panel.
 *
 * A full turn is a CLOSED loop, so "the midpoint" is the point diametrically
 * opposite the seat, and where that lands on screen is a function of the fitted
 * camera. One sample of a ring is a coin toss dressed as a measurement, and it
 * would have filed an intermittent as a defect — or, worse, gone green in CI
 * and hidden a real overlap. So this walks the whole ring with the census idiom
 * the rest of the suite already uses, and reports how much of the drawn circle
 * is actually the instrument. Nothing is asserted about any single pixel.
 */
test.describe("touch census — revolve at its seeded 360 degrees", () => {
  test("how much of the drawn ring belongs to the instrument", async ({
    page,
  }) => {
    await installSceneProbe(page);
    const account = await seedSession(page);
    const part = await createPartViaApi(page, account.token, "Revolve default");
    await createFeature(page, account.token, part.id, {
      name: "Section",
      feature: { type: "sketch", version: 1, params: SECTION_XZ },
      expected_tree_version: 0,
    });
    await page.goto(`/parts/${part.id}`);
    const cue = page.getByTestId("nav-cue-dismiss");
    if (await cue.isVisible().catch(() => false)) {
      await cue.click();
      await expect(page.getByTestId("nav-cue")).toHaveCount(0);
    }
    await expect(page.getByTestId("eval-status")).toHaveText("Solved", {
      timeout: 60_000,
    });
    await page.getByTestId("new-revolve").click();
    await expect(page.getByTestId("revolve-editor")).toBeVisible();
    await page.getByTestId("view-iso").click();
    await waitForCameraRest(page);
    await expectGaugeSettled(page, "revolve @ seed");

    // The seed is asserted, not assumed: if it ever stops being 360 this case
    // is measuring a different product and should say so rather than pass.
    await expect(page.getByTestId("revolve-angle")).toHaveValue("360");

    const points = await projectedTrack(page, "revolve-angle");
    const seen: string[] = [];
    let mine = 0;
    for (const point of points) {
      const under = await hitTestAt(
        page,
        point,
        `[data-gauge="revolve-angle"]`,
      );
      seen.push(under.owned ? "gauge" : under.described);
      if (under.owned) mine += 1;
    }
    console.log(
      `[touch ring] revolve at 360: ${mine}/${points.length} sample points ` +
        `belong to the instrument — ${seen.join(", ")}`,
    );
    // The same floor every other reach census in this suite uses (`REACH_FLOOR`
    // in gaugeProbe.ts): 12 of 16, because the two ends legitimately fall on the
    // seat and on the grip's inset round target.
    expect(
      mine,
      `at the angle "Revolve" opens with, only ${mine} of ${points.length} ` +
        `points on the drawn ring belong to the instrument — the rest are ` +
        `${seen.filter((s) => s !== "gauge").join(", ")}`,
    ).toBeGreaterThanOrEqual(REACH_FLOOR);
  });
});
