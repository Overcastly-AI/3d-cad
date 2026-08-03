import type { Locator, Page } from "@playwright/test";

/**
 * INPUT FIDELITY — a click the way a hand makes one.
 *
 * FB-17 (founder, 2026-08-01: *"How do you catch this stuff with playwright?"*).
 * The honest answer was that the suite could not, and this module is half of
 * why. `page.mouse.click(x, y)` presses and releases at the IDENTICAL pixel in
 * the SAME millisecond: 0 px of travel, 0 ms of dwell. No hand has ever done
 * that. A finger on a trackpad drifts 5–10 px between press and release and
 * holds the button 40–120 ms, and the viewport's own gesture classifier
 * (`src/sketch/clickIntent.ts`) reads BOTH numbers to decide whether you picked
 * something or panned the camera.
 *
 * That single gap is the entire reason FB-12 shipped: a 4 px slop threshold
 * discarded most real clicks — "the line wouldn't even select" — while every
 * spec in the suite drove exactly 0 px and stayed green. A gate that only
 * exercises the degenerate input cannot see a defect that lives outside it.
 *
 * USE `handClick` BY DEFAULT FOR ANY INTERACTION TEST. Reach for
 * `page.mouse.click` only when the point of the test is the degenerate case
 * itself (e.g. the 0 px rung of the drift sweep in `founder-picking.spec.ts`),
 * and say so in a comment when you do. The defaults here are a deliberately
 * ORDINARY hand, not a worst case — if a control only works for a perfectly
 * still one, that is a defect and this helper is how it surfaces.
 *
 * Determinism: the drift path is a fixed quadratic bow at a fixed angle, never
 * `Math.random()`. Two runs of the same spec dispatch byte-identical pointer
 * geometry, so a failure is reproducible and a flake is never "the jitter".
 */

/** Travel, in CSS px, that an ordinary trackpad press carries. */
export const DEFAULT_DRIFT_PX = 6;

/**
 * MINIMUM time the button is held, in ms. Real presses run 40–120 ms; 90 sits
 * mid-range. It is load-bearing rather than cosmetic: `isClick()` treats travel
 * above `CLICK_SLOP_PX` as a click only when it was SLOW, so a helper that
 * drifted without dwelling would misrepresent a wobble as a flick-pan.
 *
 * A FLOOR, not a target, and the difference is measured: one `page.mouse.move`
 * over the viewport costs ~400 ms of CDP round trip plus raycast here, so a
 * 4-step press already lasts ~1.6 s. Sleeping the full dwell on top of that
 * bought nothing but wall clock (5.4 s vs 2.4 s per click, measured). Topping
 * up only the shortfall keeps the guarantee — press duration is never below
 * what a hand does — without paying for it twice.
 */
export const DEFAULT_DWELL_MS = 90;

export interface HandClickOptions {
  /** Straight-line travel between press and release (CSS px). */
  drift?: number;
  /** Milliseconds the button stays down. */
  dwell?: number;
  /** `pointermove` events dispatched while the button is down. */
  steps?: number;
  /** Drift direction (radians, screen space). Fixed by default — deterministic. */
  angleRad?: number;
  /** Which button. */
  button?: "left" | "right" | "middle";
  /**
   * Move onto the target before pressing, so `pointerover`/`pointermove`
   * hover handlers run exactly as they would for a user arriving at a control.
   * A press dispatched onto a never-hovered element is another shape of
   * fiction — pre-selection (FB-8) lives entirely in that hover.
   */
  approach?: boolean;
}

type ResolvedOptions = Required<HandClickOptions>;

function resolve(options: HandClickOptions): ResolvedOptions {
  return {
    drift: options.drift ?? DEFAULT_DRIFT_PX,
    dwell: options.dwell ?? DEFAULT_DWELL_MS,
    // 4 is the smallest number that still makes the path read as a CURVE
    // rather than a straight segment; each step is a CDP round trip, so this
    // is the axis test time lives on.
    steps: options.steps ?? 4,
    // 0.6 rad ≈ 34°, so drift is never purely axial — an axis-aligned path can
    // hide a bug in one coordinate (the `e.delta` the rig reports is a scalar,
    // but overlay hit-boxes are rectangles and fail asymmetrically).
    angleRad: options.angleRad ?? 0.6,
    button: options.button ?? "left",
    approach: options.approach ?? true,
  };
}

/**
 * The pointer path of one press, in CSS px, as offsets from the press point.
 *
 * A hand does not travel in a straight line and does not travel in white noise
 * either: it bows. The bow is a quadratic perpendicular deviation capped at a
 * third of the drift, which keeps ACCUMULATED travel within a few percent of
 * the requested straight-line drift. That matters because `isClick()` sums
 * travel — a per-step random jitter would inflate the sum past the slop and
 * turn an "ordinary click" helper into a drag generator.
 */
export function driftPath(
  drift: number,
  steps: number,
  angleRad: number,
): { dx: number; dy: number }[] {
  const path: { dx: number; dy: number }[] = [];
  const ux = Math.cos(angleRad);
  const uy = Math.sin(angleRad);
  const bow = Math.min(2, drift / 3);
  for (let i = 1; i <= steps; i += 1) {
    const t = i / steps;
    const along = drift * t;
    // 4t(1-t) peaks at t=0.5 and is 0 at both ends: the path leaves and lands
    // on the straight line, so the release point is exactly `drift` away.
    const across = bow * 4 * t * (1 - t);
    path.push({
      dx: along * ux - across * uy,
      dy: along * uy + across * ux,
    });
  }
  return path;
}

/**
 * Click at a viewport COORDINATE the way a hand does: approach, press, drift
 * along a bowed path while holding, dwell, release.
 *
 * Coordinates are page/client pixels — the same space `page.mouse` and
 * `document.elementFromPoint` use, and the space `reachability.ts` returns
 * sample points in.
 *
 * The `waitForTimeout` calls here are NOT waiting for the app to do something
 * (which would be the sleep-instead-of-condition antipattern this suite bans);
 * they are the STIMULUS. Press duration is an input the product reads, so it
 * has to be real elapsed time, exactly as the drift has to be real pixels.
 */
export async function handClick(
  page: Page,
  x: number,
  y: number,
  options: HandClickOptions = {},
): Promise<void> {
  const { drift, dwell, steps, angleRad, button, approach } = resolve(options);
  if (approach) {
    await page.mouse.move(x - 12, y - 8);
    await page.mouse.move(x, y, { steps: 3 });
  } else {
    await page.mouse.move(x, y);
  }
  const pressedAt = Date.now();
  await page.mouse.down({ button });
  for (const { dx, dy } of driftPath(drift, steps, angleRad)) {
    await page.mouse.move(x + dx, y + dy);
  }
  const remaining = dwell - (Date.now() - pressedAt);
  if (remaining > 0) await page.waitForTimeout(remaining);
  await page.mouse.up({ button });
}

/**
 * `handClick` at a locator's centre — the drop-in replacement for
 * `locator.click()` in interaction tests.
 *
 * Note what this does NOT replace: `locator.click()` auto-waits for the element
 * to be visible, stable, enabled and hit-target-tested, and those checks are
 * worth having for ordinary chrome. Use this where the point is that a REAL
 * pointer reaches the control — a 24 px pick marker, a viewport overlay, a
 * dense toolbar — and keep `locator.click()` for buttons whose reachability is
 * not in question.
 */
export async function handClickElement(
  locator: Locator,
  options: HandClickOptions = {},
): Promise<void> {
  const box = await locator.boundingBox();
  if (box === null) {
    throw new Error("handClickElement: locator has no bounding box");
  }
  await handClick(
    locator.page(),
    box.x + box.width / 2,
    box.y + box.height / 2,
    options,
  );
}

/**
 * What the BROWSER actually received during the last recorded stretch — the
 * self-guard for everything above.
 *
 * A helper that claims to drift and dwell but quietly emits `mouse.click` would
 * leave every spec that depends on it green and meaningless, which is precisely
 * the failure FB-17 exists to end. `qa-harness.spec.ts` records a trace around
 * `handClick` and asserts the numbers, so the harness has a harness.
 */
export interface PointerTrace {
  /** `pointermove` events dispatched while a button was down. */
  movesWhileDown: number;
  /** Summed pointer travel between press and release (CSS px). */
  travelPx: number;
  /** Straight-line distance from press point to release point (CSS px). */
  displacementPx: number;
  /** Elapsed time between `pointerdown` and `pointerup` (ms). */
  pressMs: number;
  downs: number;
  ups: number;
  /** True if the element under the press also received a `click`. */
  clicked: boolean;
}

/** Start recording pointer events on the page (capture phase, whole document). */
export async function recordPointerTrace(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as Record<string, unknown>;
    const state = {
      movesWhileDown: 0,
      travelPx: 0,
      displacementPx: 0,
      pressMs: 0,
      downs: 0,
      ups: 0,
      clicked: false,
      down: false,
      lastX: 0,
      lastY: 0,
      startX: 0,
      startY: 0,
      startedAt: 0,
    };
    w["__loftPointerTrace"] = state;
    const prior = w["__loftPointerTraceOff"] as (() => void) | undefined;
    prior?.();
    const onDown = (event: PointerEvent) => {
      state.down = true;
      state.downs += 1;
      state.startedAt = performance.now();
      state.startX = event.clientX;
      state.startY = event.clientY;
      state.lastX = event.clientX;
      state.lastY = event.clientY;
    };
    const onMove = (event: PointerEvent) => {
      if (!state.down) return;
      state.movesWhileDown += 1;
      state.travelPx += Math.hypot(
        event.clientX - state.lastX,
        event.clientY - state.lastY,
      );
      state.lastX = event.clientX;
      state.lastY = event.clientY;
    };
    const onUp = (event: PointerEvent) => {
      if (!state.down) return;
      state.down = false;
      state.ups += 1;
      state.pressMs = performance.now() - state.startedAt;
      state.displacementPx = Math.hypot(
        event.clientX - state.startX,
        event.clientY - state.startY,
      );
    };
    const onClick = () => {
      state.clicked = true;
    };
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("pointermove", onMove, true);
    window.addEventListener("pointerup", onUp, true);
    window.addEventListener("click", onClick, true);
    w["__loftPointerTraceOff"] = () => {
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("pointermove", onMove, true);
      window.removeEventListener("pointerup", onUp, true);
      window.removeEventListener("click", onClick, true);
    };
  });
}

/** Read the trace recorded since the last {@link recordPointerTrace}. */
export async function readPointerTrace(page: Page): Promise<PointerTrace> {
  return page.evaluate(() => {
    const w = window as unknown as Record<string, unknown>;
    const state = w["__loftPointerTrace"] as PointerTrace | undefined;
    if (state === undefined) {
      throw new Error("readPointerTrace: call recordPointerTrace first");
    }
    return {
      movesWhileDown: state.movesWhileDown,
      travelPx: state.travelPx,
      displacementPx: state.displacementPx,
      pressMs: state.pressMs,
      downs: state.downs,
      ups: state.ups,
      clicked: state.clicked,
    };
  });
}
