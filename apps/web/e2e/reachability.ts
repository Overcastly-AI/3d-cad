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

/**
 * How many pixels near each of `points` match `hex` — ONE readback for the lot.
 *
 * WHY BATCHED. Reading the canvas costs a `drawImage` of the ENTIRE frame
 * regardless of how few pixels you then look at, so a per-point helper called
 * in a loop pays for the whole canvas once per point. `qa-sketch-frame`'s ring
 * scan did exactly that: 89 radii x 4 diagonals x 3 zoom legs = **1068
 * full-frame copies to read nine pixels each**. Batching does not change a
 * single measured value; it changes 1068 readbacks into 3.
 *
 * AND IT IS NOT A SPEED FIX — measured, because it looked like one. That scan
 * was 190 ms of a 33.2 s test (0.6 %) while the test's zoom loop was 47 %, so
 * batching it moved the wall clock by nothing at all (CI-4 headroom pass,
 * 2026-08-29). Reach for this to stop wasting work and to keep one readback's
 * worth of the frame CONSISTENT across every point in a census; do not reach
 * for it to buy headroom.
 *
 * ONE CONSISTENT FRAME IS A BEHAVIOUR CHANGE, so callers must know it. The
 * per-point form re-read the canvas for every probe and therefore saw whatever
 * had been painted by then; this sees one instant. That is more correct for a
 * census — but any caller relying on the old form's incidental latency to let a
 * render land must now wait for the render EXPLICITLY. `measureRingRadiusPx`
 * had exactly that dependency and started reading pre-paint frames until it
 * gained a `waitForFrames`.
 *
 * The predicate is per-channel absolute difference <= 8, the same tolerance the
 * per-point version used, over a `2*halfPx+1` box in CANVAS pixels centred on
 * the point's canvas coordinate. A point whose box falls outside the canvas
 * scores -1, exactly as before, so callers testing `> 0` are unaffected.
 */
export async function inkAt(
  page: Page,
  points: readonly Point[],
  hex: string,
  halfPx = 1,
  selector = VIEWPORT_CANVAS,
): Promise<number[]> {
  return page.evaluate(
    ({
      points,
      hex,
      halfPx,
      selector,
    }: {
      points: readonly Point[];
      hex: string;
      halfPx: number;
      selector: string;
    }): number[] => {
      const canvas = document.querySelector<HTMLCanvasElement>(selector);
      if (!canvas) return points.map(() => -1);
      const rect = canvas.getBoundingClientRect();
      const sx = canvas.width / rect.width;
      const sy = canvas.height / rect.height;
      const probe = document.createElement("canvas");
      probe.width = canvas.width;
      probe.height = canvas.height;
      const ctx = probe.getContext("2d");
      if (!ctx) return points.map(() => -1);
      ctx.drawImage(canvas, 0, 0);
      const { data } = ctx.getImageData(0, 0, probe.width, probe.height);
      const target = [
        Number.parseInt(hex.slice(1, 3), 16),
        Number.parseInt(hex.slice(3, 5), 16),
        Number.parseInt(hex.slice(5, 7), 16),
      ];
      const size = halfPx * 2 + 1;
      return points.map(({ x, y }) => {
        const x0 = Math.round((x - rect.left) * sx) - halfPx;
        const y0 = Math.round((y - rect.top) * sy) - halfPx;
        if (
          x0 < 0 ||
          y0 < 0 ||
          x0 + size > probe.width ||
          y0 + size > probe.height
        ) {
          return -1;
        }
        let hits = 0;
        for (let dy = 0; dy < size; dy += 1) {
          for (let dx = 0; dx < size; dx += 1) {
            const i = ((y0 + dy) * probe.width + (x0 + dx)) * 4;
            if (
              Math.abs((data[i] as number) - (target[0] as number)) <= 8 &&
              Math.abs((data[i + 1] as number) - (target[1] as number)) <= 8 &&
              Math.abs((data[i + 2] as number) - (target[2] as number)) <= 8
            ) {
              hits += 1;
            }
          }
        }
        return hits;
      });
    },
    { points, hex, halfPx, selector },
  );
}

/**
 * Of `points`, the ones that are BACKGROUND with room to spare — no lit pixel
 * anywhere within `marginPx`.
 *
 * WHY A CENSUS NEEDS THIS. `litPoints` classifies a single pixel, and a body's
 * rendered edge is not a single pixel: it is a dark rim plus an outline stroke
 * several pixels wide, all of it BELOW the luminance floor and all of it
 * squarely on the body as far as a raycast is concerned. So a grid point that
 * lands in that band is "not lit" and "on the solid" at the same time, and any
 * assertion that treats not-lit as *nothing is there* is asking the oracle
 * about the body it just excluded.
 *
 * MEASURED, on the failure that produced this helper (`pick-affordance`
 * SEL-6's ghost sweep, 1 of 4 shard runs, 2026-08-29): five reported ghosts,
 * all five in ONE grid column at x = 1236, and the plate's last lit pixel on
 * every one of those rows was x = 1234. Luminance across the boundary read
 * 178 (lit) at 1234, 65 at 1236, 89 at 1238 — the outline stroke — and 18 at
 * 1240. So the "vacated" region included a 2-px-wide strip of the still-drawn
 * plate's own right edge, and the plate's face answered there, correctly.
 *
 * It is a lottery rather than a constant because the grid is fixed in CSS px
 * (`step/2 + n*step`) while the body's edge is placed by the camera fit, which
 * varies sub-pixel between runs — so whether any column lands inside the ~5 px
 * rim is decided per run.
 *
 * The default margin is 8 px: 1.6x the measured rim and one third of the
 * coarsest grid this suite uses, so it can only ever discard points that
 * straddle a silhouette boundary — never a point out in open background, which
 * is where a body that had genuinely stayed pickable would answer.
 */
export async function clearOfSilhouette(
  page: Page,
  points: readonly Point[],
  options: SamplingOptions & { marginPx?: number } = {},
): Promise<Point[]> {
  const {
    marginPx = 8,
    minLuminance = 110,
    selector = VIEWPORT_CANVAS,
  } = options;
  return page.evaluate(
    ({
      points,
      marginPx,
      minLuminance,
      selector,
    }: {
      points: readonly Point[];
      marginPx: number;
      minLuminance: number;
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
      const bx = probe.width / (canvas.clientWidth || probe.width);
      const by = probe.height / (canvas.clientHeight || probe.height);
      const lit = (px: number, py: number): boolean => {
        if (px < 0 || py < 0 || px >= probe.width || py >= probe.height) {
          return false;
        }
        const i = (py * probe.width + px) * 4;
        const r = data[i] ?? 0;
        const g = data[i + 1] ?? 0;
        const b = data[i + 2] ?? 0;
        return 0.2126 * r + 0.7152 * g + 0.0722 * b > minLuminance;
      };
      const rx = Math.max(1, Math.round(marginPx * bx));
      const ry = Math.max(1, Math.round(marginPx * by));
      return points.filter(({ x, y }) => {
        const cx = Math.floor((x - rect.left) * bx);
        const cy = Math.floor((y - rect.top) * by);
        for (let dy = -ry; dy <= ry; dy += 1) {
          for (let dx = -rx; dx <= rx; dx += 1) {
            if (lit(cx + dx, cy + dy)) return false;
          }
        }
        return true;
      });
    },
    { points, marginPx, minLuminance, selector },
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
