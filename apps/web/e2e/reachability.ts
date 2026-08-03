import { expect, type Page } from "@playwright/test";

import { VIEWPORT_CANVAS } from "./perception";

/**
 * REACHABILITY — can a pointer land on it, not merely "does the app respond
 * when we address it by name".
 *
 * FB-17(b)/(c). Every pick spec in this suite drives
 * `page.getByTestId("plane-pick-face-3").click()`, which Playwright resolves to
 * the element's centre and clicks it dead on. That is a perfect assertion about
 * STATE — the overlay exists, it is enabled, clicking it seats the sketch — and
 * it says NOTHING about whether a human can hit it. The founder's report was
 * "picking a face is very difficult" (FB-3/FB-5); the suite was green because
 * every spec hit a 24 px dot with machine precision, and 2.2 % of the face's
 * on-screen area is a live target (32 of 1457 sampled points).
 *
 * WHICH TO USE:
 *
 *   getByTestId(...)      asserting STATE. Does the control exist, is it
 *                         enabled, does acting on it produce the right result?
 *                         Cheap, stable, immune to camera drift. Keep using it
 *                         for chrome, forms, trees, toolbars.
 *
 *   coordinate + hand.ts  asserting REACHABILITY. Would a user's pointer, aimed
 *                         at the ENTITY they can see, actually hit a target?
 *                         Required for anything drawn in the viewport: faces,
 *                         edges, vertices, overlay markers, direct-manipulation
 *                         handles. Pair with `measureReachability` so the answer
 *                         is a FRACTION of the entity's area, not a boolean —
 *                         a boolean passes on a single dot, which is precisely
 *                         the defect that shipped.
 *
 * The census below hit-tests the real DOM (`document.elementFromPoint`), which
 * is the correct model for our in-canvas pick targets: they are drei `Html`
 * nodes (`PickNode`), deliberately DOM so they are keyboard-navigable and
 * screen-reader named. A point over the bare canvas is therefore NOT a pick
 * target — which is the true statement about `ModelMesh`, whose faces carry no
 * raycast handler at all.
 *
 * For a target that IS a raycast handler rather than DOM, pass your own
 * `probe` to {@link measureReachabilityWith}: it can hover-and-read, click-and-
 * undo, or anything else — the fraction arithmetic is the same.
 */

/** A point in page/client CSS pixels — `page.mouse` space. */
export interface Point {
  x: number;
  y: number;
}

export interface SamplingOptions {
  /** Grid pitch in CSS px. 8 px ≈ a fingertip's aiming precision. */
  step?: number;
  /** Lit-pixel threshold (see `perception.silhouette`). */
  minLuminance?: number;
  /** Bottom-right square to skip (the in-canvas reference cube). */
  maskCornerPx?: number;
  selector?: string;
}

/**
 * Sample points on the ENTITY the user can see: grid points whose canvas pixel
 * is lit body rather than bench.
 *
 * Sampling the rendered silhouette (not the bounding box) matters for the
 * fraction to mean anything: an iso view of a box fills ~75 % of its bbox, so a
 * bbox-based denominator would flatter every result by a third.
 */
export async function litPoints(
  page: Page,
  options: SamplingOptions = {},
): Promise<Point[]> {
  const {
    step = 8,
    minLuminance = 110,
    maskCornerPx = 170,
    selector = VIEWPORT_CANVAS,
  } = options;
  return page.evaluate(
    ({
      step,
      minLuminance,
      maskCornerPx,
      selector,
    }: {
      step: number;
      minLuminance: number;
      maskCornerPx: number;
      selector: string;
    }): Point[] => {
      const canvas = document.querySelector<HTMLCanvasElement>(selector);
      if (!canvas) return [];
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return [];
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
      const rect = canvas.getBoundingClientRect();
      const cssWidth = canvas.clientWidth || probe.width;
      const cssHeight = canvas.clientHeight || probe.height;
      const bx = probe.width / cssWidth;
      const by = probe.height / cssHeight;
      const points: Point[] = [];
      for (let cy = step / 2; cy < cssHeight; cy += step) {
        for (let cx = step / 2; cx < cssWidth; cx += step) {
          if (cx > cssWidth - maskCornerPx && cy > cssHeight - maskCornerPx) {
            continue;
          }
          const px = Math.min(probe.width - 1, Math.floor(cx * bx));
          const py = Math.min(probe.height - 1, Math.floor(cy * by));
          const i = (py * probe.width + px) * 4;
          const r = data[i] ?? 0;
          const g = data[i + 1] ?? 0;
          const b = data[i + 2] ?? 0;
          if (0.2126 * r + 0.7152 * g + 0.0722 * b <= minLuminance) continue;
          points.push({ x: rect.left + cx, y: rect.top + cy });
        }
      }
      return points;
    },
    { step, minLuminance, maskCornerPx, selector },
  );
}

/** What sits under a point, from the browser's own hit test. */
export interface HitTarget {
  /** Nearest `data-testid` at or above the topmost element, if any. */
  testId: string | null;
  /** Tag name of the topmost element, lowercase. */
  tag: string;
}

/**
 * Hit-test many points in ONE round trip.
 *
 * The whole census is a single `page.evaluate`, so 1457 points cost about as
 * much as one `click()`. That is what makes a FRACTION affordable as a routine
 * gate rather than a one-off investigation.
 */
export async function hitTest(
  page: Page,
  points: readonly Point[],
): Promise<HitTarget[]> {
  return page.evaluate((points: readonly Point[]): HitTarget[] => {
    return points.map(({ x, y }) => {
      const element = document.elementFromPoint(x, y);
      if (element === null) return { testId: null, tag: "" };
      const owner = element.closest("[data-testid]");
      return {
        testId: owner?.getAttribute("data-testid") ?? null,
        tag: element.tagName.toLowerCase(),
      };
    });
  }, points);
}

export interface ReachabilityCensus {
  /** Points sampled over the entity. */
  sampled: number;
  /** Points that landed on a live target. */
  reachable: number;
  /** `reachable / sampled` — the affordance, as a fraction of what you see. */
  fraction: number;
  /** How many points each accepted target absorbed — where the dots are. */
  byTarget: Record<string, number>;
}

function census(
  hits: readonly HitTarget[],
  accept: (hit: HitTarget) => boolean,
): ReachabilityCensus {
  const byTarget: Record<string, number> = {};
  let reachable = 0;
  for (const hit of hits) {
    if (!accept(hit)) continue;
    reachable += 1;
    const key = hit.testId ?? hit.tag;
    byTarget[key] = (byTarget[key] ?? 0) + 1;
  }
  return {
    sampled: hits.length,
    reachable,
    fraction: hits.length === 0 ? 0 : reachable / hits.length,
    byTarget,
  };
}

export interface ReachabilityOptions extends SamplingOptions {
  /** Points to sample; defaults to the lit silhouette. */
  points?: readonly Point[];
  /** Which hit counts as a live pick target. */
  accept: (hit: HitTarget) => boolean;
}

/** Measure what fraction of the visible entity is a live DOM pick target. */
export async function measureReachability(
  page: Page,
  options: ReachabilityOptions,
): Promise<ReachabilityCensus> {
  const points = options.points ?? (await litPoints(page, options));
  const hits = await hitTest(page, points);
  return census(hits, options.accept);
}

/**
 * Measure with a CUSTOM probe — for targets that are raycast handlers rather
 * than DOM, or where "reachable" means something richer than "an element is
 * under the pointer" (hover highlight appears, cursor changes, a pick lands).
 *
 * One round trip per point, so keep the grid coarse (`step: 24`+).
 */
export async function measureReachabilityWith(
  points: readonly Point[],
  probe: (point: Point) => Promise<boolean>,
): Promise<ReachabilityCensus> {
  const hits: HitTarget[] = [];
  for (const point of points) {
    hits.push({ testId: (await probe(point)) ? "probe" : null, tag: "" });
  }
  return census(hits, (hit) => hit.testId === "probe");
}

/** Accept any hit whose nearest test id starts with `prefix`. */
export function testIdPrefix(prefix: string): (hit: HitTarget) => boolean {
  return (hit) => hit.testId !== null && hit.testId.startsWith(prefix);
}

export interface FractionGate extends ReachabilityOptions {
  /**
   * The floor, as a fraction of the entity's visible area.
   *
   * There is no universal right number, so state the reasoning where you set
   * it. A useful anchor: WCAG 2.5.8 asks for a 24×24 px target, and a face
   * filling 40 000 px of screen that offers one such dot is at 1.4 % — the
   * regime the founder called "very difficult". Direct manipulation in Fusion
   * or Plasticity is ~100 %: the face itself is the target.
   */
  min: number;
}

/** Assert the affordance, and return the census so the number gets printed. */
export async function expectReachableFraction(
  page: Page,
  gate: FractionGate,
): Promise<ReachabilityCensus> {
  const measured = await measureReachability(page, gate);
  expect(
    measured.sampled,
    "no lit pixels sampled — is the body rendered?",
  ).toBeGreaterThan(50);
  expect(
    measured.fraction,
    `clickable ${measured.reachable}/${measured.sampled} = ${(measured.fraction * 100).toFixed(1)}% (${JSON.stringify(measured.byTarget)})`,
  ).toBeGreaterThanOrEqual(gate.min);
  return measured;
}
