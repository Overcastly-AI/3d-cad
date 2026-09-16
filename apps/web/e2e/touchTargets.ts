/**
 * TOUCH-TARGET PROBES — what a FINGER can reach on a parametric gauge.
 *
 * Every reach measurement this project has taken on the gauges was
 * mouse-driven, at 1280x800 and 1600x1000 (`gaugeProbe.ts`, `gaugeReach.ts`,
 * `extrude-grip-reach.spec.ts`). A 24x24 grip is a perfectly good mouse target
 * and a failing touch target, so that whole evidence base is silent on the
 * question this module asks.
 *
 * ## The three things a mouse probe cannot say
 *
 *  1. **Area against a TOUCH floor.** `boundingBox()` is the same number for
 *     both hands; what changes is the floor it is graded against. WCAG 2.2
 *     SC 2.5.8 (AA) is 24x24 CSS px and SC 2.5.5 (AAA) is 44x44 — and the
 *     platform guidance every tablet user's muscle memory is calibrated on is
 *     44 (Apple HIG) to 48 (Material). {@link TOUCH_FLOOR_PX} is 44.
 *  2. **A REAL touch sequence.** `page.mouse.down/move/up` synthesises a MOUSE
 *     pointer; a control can listen for `pointerdown` and still be unusable
 *     with a finger, because `touch-action` steals the gesture, because the
 *     element needs a hover the finger never delivers, or because the only
 *     route into it is a physical keyboard. This module dispatches
 *     `Input.dispatchTouchEvent` over CDP, which is what the browser itself
 *     turns into `pointerType: "touch"` events.
 *  3. **Neighbour spacing.** Two 44 px targets 2 px apart are ONE ambiguous
 *     target. Area alone cannot see that; {@link nearestGap} can.
 *
 * ## No `force: true`, and no `toBeVisible()` as a reachability claim
 *
 * Both have passed in this repo for controls no user could touch — an SVG
 * stroke whose `getBoundingClientRect` is 0 px tall, an `sr-only` node clipped
 * to `1x1 @ (-1,43)` that `checkVisibility()` calls true, a Tailwind utility
 * that was never generated, and a GL-drawn handle with no DOM raycast target.
 * Reachability here is always `document.elementFromPoint` resolving to the
 * control, and operability is always a real input sequence.
 */
import type { CDPSession } from "@playwright/test";

import { expect, type Page } from "./fixtures";
import { SEAT_SETTLE_TIMEOUT_MS, waitForFrames } from "./support";

export interface Point {
  x: number;
  y: number;
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * The touch floor, CSS px.
 *
 * NOT the 24 px WCAG 2.2 AA minimum: that is the floor below which a target is
 * a conformance FAILURE, not the size at which a finger can use it. 44 is
 * Apple's HIG figure, SC 2.5.5 (AAA), and the number every tablet user's aim is
 * calibrated against. A gauge is a precision instrument used one-handed on a
 * tablet while the other hand holds the device; grading it against the failure
 * floor rather than the usability floor is how "technically conformant and
 * unusable" ships.
 */
export const TOUCH_FLOOR_PX = 44;

/** The WCAG 2.2 SC 2.5.8 (AA) minimum, for the record. */
export const WCAG_AA_FLOOR_PX = 24;

/** One measured control. */
export interface TouchTarget {
  /** How the probe names it in a table — usually the test id. */
  name: string;
  box: Box | null;
  /** What `document.elementFromPoint` returns at the box's centre. */
  resolvesTo: string;
  /** True when that element is (or is inside) the control itself. */
  reaches: boolean;
}

/**
 * Measure one locator: its box, and what is actually under its own centre.
 *
 * `resolvesTo` is a DESCRIPTION, not an element — the point of the probe is to
 * name the occluder when the answer is "something else", because "unreachable"
 * with no culprit is a finding nobody can act on.
 */
export async function measureTarget(
  page: Page,
  testId: string,
): Promise<TouchTarget> {
  const locator = page.getByTestId(testId);
  if ((await locator.count()) === 0) {
    return { name: testId, box: null, resolvesTo: "absent", reaches: false };
  }
  const box = await locator.first().boundingBox();
  if (box === null) {
    return { name: testId, box: null, resolvesTo: "no-box", reaches: false };
  }
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const seen = await hitTestAt(page, centre, `[data-testid="${testId}"]`);
  return { name: testId, box, resolvesTo: seen.described, reaches: seen.owned };
}

/**
 * `document.elementFromPoint`, described — and told whether the hit belongs to
 * the wanted owner.
 *
 * Ownership is `closest(<selector>)` rather than identity, because a legitimate
 * target routinely resolves to its own child (the grip's collar `span`, the
 * tag's label `span`). Identity would score a correct control as unreachable,
 * which is the false positive that gets a gate muted.
 *
 * The owner is a SELECTOR rather than a test id, and that is a correction
 * earned in this pass rather than generality for its own sake. An arc gauge's
 * hit sleeve is N bands (`-sleeve`, `-sleeve-1` .. `-sleeve-95`), so asking
 * "does the shaft midpoint belong to `revolve-angle-sleeve`" reports FALSE for
 * a press that lands squarely on `revolve-angle-sleeve-10` — a perfectly
 * reachable point scored as unreachable, which is the false-negative half of
 * the same mistake. `[data-gauge="<id>"]`, which the component puts on every
 * band AND on the grip, is the question actually being asked: did this pixel
 * belong to THIS instrument.
 */
export async function hitTestAt(
  page: Page,
  point: Point,
  ownerSelector: string,
): Promise<{ described: string; owned: boolean }> {
  return page.evaluate(
    ({ p, id }: { p: Point; id: string }) => {
      const el = document.elementFromPoint(p.x, p.y);
      if (el === null) return { described: "null", owned: false };
      const owned = el.closest(id) !== null;
      const named = el.closest("[data-testid]");
      const described =
        named === null
          ? el.tagName.toLowerCase()
          : (named.getAttribute("data-testid") ?? el.tagName.toLowerCase());
      return { described, owned };
    },
    { p: point, id: ownerSelector },
  );
}

/** Centre of a box. */
export function centreOf(box: Box): Point {
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/**
 * Edge-to-edge gap, CSS px, between two boxes — 0 when they touch or overlap.
 *
 * Chebyshev rather than Euclidean: adjacency on a screen is per-axis, and two
 * boxes side by side with a 2 px channel between them are 2 px apart no matter
 * how tall they are.
 */
export function gapBetween(a: Box, b: Box): number {
  const dx = Math.max(
    0,
    Math.max(a.x - (b.x + b.width), b.x - (a.x + a.width)),
  );
  const dy = Math.max(
    0,
    Math.max(a.y - (b.y + b.height), b.y - (a.y + a.height)),
  );
  return Math.hypot(dx, dy);
}

/** The closest OTHER target to `target`, and how far away it is. */
export function nearestGap(
  target: TouchTarget,
  others: readonly TouchTarget[],
): { name: string; gap: number } | null {
  if (target.box === null) return null;
  let best: { name: string; gap: number } | null = null;
  for (const other of others) {
    if (other.name === target.name || other.box === null) continue;
    const gap = gapBetween(target.box, other.box);
    if (best === null || gap < best.gap) best = { name: other.name, gap };
  }
  return best;
}

// --- REAL TOUCH INPUT --------------------------------------------------------

/**
 * A touch sequence dispatched through CDP, which is where real finger input
 * enters Blink.
 *
 * `page.touchscreen.tap` covers the tap and nothing else: there is no
 * Playwright API for a touch DRAG, and a `page.mouse` drag at the same
 * coordinates proves nothing about a finger — it carries `pointerType:
 * "mouse"`, it is never subject to `touch-action`, and it cannot be stolen by
 * a scroll or a pinch. Those are exactly the three ways a drag handle fails on
 * a tablet while passing every mouse spec in the suite.
 */
export class Finger {
  constructor(private readonly cdp: CDPSession) {}

  static async open(page: Page): Promise<Finger> {
    const cdp = await page.context().newCDPSession(page);
    return new Finger(cdp);
  }

  async down(p: Point): Promise<void> {
    await this.cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: p.x, y: p.y, id: 1, radiusX: 11, radiusY: 11 }],
    });
  }

  async move(p: Point): Promise<void> {
    await this.cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: p.x, y: p.y, id: 1, radiusX: 11, radiusY: 11 }],
    });
  }

  async up(): Promise<void> {
    await this.cdp.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
  }

  /** Press, travel in `steps`, release. The gesture a value drag really is. */
  async drag(from: Point, to: Point, steps = 8): Promise<void> {
    await this.down(from);
    for (let i = 1; i <= steps; i += 1) {
      await this.move({
        x: from.x + ((to.x - from.x) * i) / steps,
        y: from.y + ((to.y - from.y) * i) / steps,
      });
    }
    await this.up();
  }

  async tap(p: Point): Promise<void> {
    await this.down(p);
    await this.up();
  }

  async detach(): Promise<void> {
    await this.cdp.detach().catch(() => undefined);
  }
}

/**
 * Print a census as a fixed-width table into the job log.
 *
 * The log tail is the only channel into a red CI shard, so a touch census that
 * only asserted would leave the next reader with a number and no context. This
 * prints the whole table on green runs too.
 */
export function printCensus(mount: string, targets: TouchTarget[]): void {
  const rows = targets.map((t) => {
    const size =
      t.box === null
        ? "—"
        : `${t.box.width.toFixed(1)}x${t.box.height.toFixed(1)}`;
    const near = nearestGap(t, targets);
    const gap = near === null ? "—" : `${near.gap.toFixed(1)} (${near.name})`;
    return `  ${t.name.padEnd(30)} ${size.padEnd(14)} ${(t.reaches ? "self" : t.resolvesTo).padEnd(22)} ${gap}`;
  });
  console.log(
    `[touch census] ${mount}\n` +
      `  ${"control".padEnd(30)} ${"w x h".padEnd(14)} ${"elementFromPoint".padEnd(22)} nearest gap\n` +
      rows.join("\n"),
  );
}

/**
 * THE SETTLE, NAMED — and it has two branches, which is why it is not simply a
 * call to `expectSeatsSettled`.
 *
 * Burial/occlusion is decided by a rotating per-frame budget that converges in
 * 16-21 s quiet and up to 31 s under load, and `expectSeatsSettled` waits on
 * the `data-edge-mark-seats` stamp for exactly that. But the stamp is written
 * only while edge marks are ADDRESSABLE (`useEdgeMarkAnchors` returns early
 * when they are not), so on a mount with no edge offer on screen — extrude on
 * a fresh sketch, revolve, datum, pattern — the attribute is never set at all
 * and a bare `expectSeatsSettled` hangs for its full 90 s ceiling and then
 * fails, on nine mounts, for a reason that has nothing to do with the gauge.
 *
 * MEASURED before this existed: all four extrude cases died at 1.6 min in
 * `toHaveAttribute`, and the natural read of that log is "the viewport never
 * settles", which is false.
 *
 * So this asks which world it is in FIRST and says so in the log. Where the
 * stamp exists it is the real wait; where it does not, the honest statement is
 * that there is no burial pass to drain and the only synchronisation owed is a
 * few rendered frames — which is stated here rather than left to the incidental
 * timing of whatever ran before. An unstated settle is not a wait.
 */
export async function expectGaugeSettled(
  page: Page,
  label: string,
): Promise<"seats" | "no-seats"> {
  const viewport = page.getByTestId("viewport");
  const stamp = await viewport.getAttribute("data-edge-mark-seats");
  if (stamp === null) {
    // No edge-mark offer on screen, so no rotating budget is running. Three
    // frames is the flush between a DOM wait and a canvas-derived measurement
    // that this suite already uses by name elsewhere.
    await waitForFrames(page, 3);
    console.log(`    [settle] ${label}: no edge-mark pass on screen; 3 frames`);
    return "no-seats";
  }
  const started = Date.now();
  await expect(viewport).toHaveAttribute("data-edge-mark-seats", "settled", {
    timeout: SEAT_SETTLE_TIMEOUT_MS,
  });
  console.log(
    `    [settle] ${label}: seats settled in ${Date.now() - started} ms ` +
      `(ceiling ${SEAT_SETTLE_TIMEOUT_MS} ms)`,
  );
  return "seats";
}
