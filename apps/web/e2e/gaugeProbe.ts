/**
 * PROBES FOR A PARAMETRIC GAUGE — where it is drawn, how long it is, and what
 * is under the pixels the drawing invites you to press.
 *
 * Every gauge in the wave is one `<ParametricGauge>` with a different track, so
 * these ask their questions by `gaugeId` and work on all of them.
 *
 * ## Why these measurements and not `toBeVisible()`
 *
 * A drawn manipulator photographs perfectly while being unusable — that is
 * CRAFT-7's whole finding, and it survived a founder capture, a design review
 * and six passing specs because every one of them asserted a BOX property.
 * `toBeVisible()`, `boundingBox()` and a `data-*` readout are all true of a
 * control no pointer can reach. Only asking the browser *what is under this
 * pixel*, and then actually pressing it, can see the defect.
 *
 * **There is no `force: true` in this file and there must never be.** This repo
 * has measured that flag hiding a zero-area target four separate times.
 *
 * DRY NOTE: `extrude-grip-reach.spec.ts` (CRAFT-7) carries the original,
 * gauge-specific copy of `projectedSpine`/`gripCentre`/`reach`. This module is
 * the extraction on the second real use; that spec is another item's test file
 * and was left untouched deliberately while four builders are live, so it
 * should adopt this module the next time it is opened.
 */
import { expect, type Page } from "./fixtures";

export interface Point {
  x: number;
  y: number;
}

/** How many points a reach census walks down the projected track. */
export const REACH_SAMPLES = 16;

/**
 * The acceptance floor (direction §9, amended). 12 of 16 rather than all 16
 * because the two ends legitimately fall outside: `t = 0` sits on the seat,
 * where the sleeve must NOT be (it would swallow a pick on the geometry the
 * gauge stands on), and the last sample rides the arrow's point where the
 * grip's round target is inset from the square sample.
 */
export const REACH_FLOOR = 12;

/**
 * The drawn shaft's two ends, in CSS pixels, taken from the SPINE MESH ITSELF.
 *
 * The cylinder is unit-height and scaled to the value, so its local
 * `(0, ±0.5, 0)` are exactly the seat and the arrowhead's base, and
 * `matrixWorld` carries whatever pose the component gave it. That is what makes
 * this a measurement of the thing the user can see rather than of an assumption
 * about it.
 */
export async function projectedSpine(
  page: Page,
  gaugeId: string,
): Promise<{ seat: Point; base: Point }> {
  const seen = await page.evaluate((wanted: string) => {
    interface Mat {
      elements: number[];
    }
    interface Obj3D {
      name: string;
      matrixWorld: Mat;
      traverse: (fn: (child: Obj3D) => void) => void;
      updateWorldMatrix?: (parents: boolean, children: boolean) => void;
    }
    interface Cam {
      matrixWorldInverse: Mat;
      projectionMatrix: Mat;
    }
    const w = window as unknown as Record<string, unknown>;
    const scenes = (w["__loftScenes"] ?? {}) as Record<string, Obj3D>;
    const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
    const apply = (
      m: number[],
      x: number,
      y: number,
      z: number,
      h: number,
    ): [number, number, number, number] => [
      (m[0] as number) * x +
        (m[4] as number) * y +
        (m[8] as number) * z +
        (m[12] as number) * h,
      (m[1] as number) * x +
        (m[5] as number) * y +
        (m[9] as number) * z +
        (m[13] as number) * h,
      (m[2] as number) * x +
        (m[6] as number) * y +
        (m[10] as number) * z +
        (m[14] as number) * h,
      (m[3] as number) * x +
        (m[7] as number) * y +
        (m[11] as number) * z +
        (m[15] as number) * h,
    ];
    for (const uuid of order) {
      const scene = scenes[uuid];
      const camera = cameras[uuid];
      if (scene === undefined || camera === undefined) continue;
      let mesh: Obj3D | null = null;
      scene.traverse((node) => {
        if (node.name === wanted) mesh = node;
      });
      if (mesh === null) continue;
      const found: Obj3D = mesh;
      found.updateWorldMatrix?.(true, false);
      const canvas = document.querySelector("canvas");
      if (canvas === null) return null;
      const rect = canvas.getBoundingClientRect();
      const toScreen = (ly: number): Point => {
        const world = apply(found.matrixWorld.elements, 0, ly, 0, 1);
        const view = apply(
          camera.matrixWorldInverse.elements,
          world[0],
          world[1],
          world[2],
          1,
        );
        const clip = apply(
          camera.projectionMatrix.elements,
          view[0],
          view[1],
          view[2],
          view[3],
        );
        return {
          x: rect.left + ((clip[0] / clip[3] + 1) / 2) * rect.width,
          y: rect.top + ((1 - clip[1] / clip[3]) / 2) * rect.height,
        };
      };
      return { a: toScreen(-0.5), b: toScreen(0.5) };
    }
    return null;
  }, `gauge-${gaugeId}-spine`);
  if (seen === null) throw new Error(`no spine mesh for gauge ${gaugeId}`);
  // Which end is the arrowhead's base depends only on the camera, so pick by
  // distance to the grip — which sits on the arrow's point.
  const grip = await gripCentre(page, gaugeId);
  const near = (p: Point): number => Math.hypot(p.x - grip.x, p.y - grip.y);
  return near(seen.a) < near(seen.b)
    ? { seat: seen.b, base: seen.a }
    : { seat: seen.a, base: seen.b };
}

/**
 * The DRAWN length of the shaft in world millimetres — the gauge's own answer
 * to "what value am I showing".
 *
 * A `linearTrack` spine runs seat → `base + dir × value`, and the mesh is a
 * unit cylinder scaled by that length, so `scale.y` IS the value. It is read
 * from the scene graph rather than from the form, which is the whole point: a
 * gauge that springs back on pointer-up (a missing contract-β echo) still has
 * the right number in the panel and the wrong rod on the screen.
 */
export async function spineLengthMm(
  page: Page,
  gaugeId: string,
): Promise<number> {
  const seen = await page.evaluate((wanted: string) => {
    interface Obj3D {
      name: string;
      scale: { y: number };
      traverse: (fn: (child: Obj3D) => void) => void;
    }
    const w = window as unknown as Record<string, unknown>;
    const scenes = (w["__loftScenes"] ?? {}) as Record<string, Obj3D>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
    for (const uuid of order) {
      const scene = scenes[uuid];
      if (scene === undefined) continue;
      let found: number | null = null;
      scene.traverse((node) => {
        if (node.name === wanted) found = node.scale.y;
      });
      if (found !== null) return found;
    }
    return null;
  }, `gauge-${gaugeId}-spine`);
  if (seen === null) throw new Error(`no spine mesh for gauge ${gaugeId}`);
  return seen;
}

/** The grip's centre in page coordinates. */
export async function gripCentre(page: Page, gaugeId: string): Promise<Point> {
  const box = await page.getByTestId(`${gaugeId}-handle`).boundingBox();
  if (box === null) throw new Error(`the ${gaugeId} grip has no box`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Walk the projected track and ask the browser what is under each pixel. */
export async function reach(
  page: Page,
  gaugeId: string,
): Promise<{ hits: number; resolved: string[]; from: Point; to: Point }> {
  const { seat } = await projectedSpine(page, gaugeId);
  const apex = await gripCentre(page, gaugeId);
  const points: Point[] = [];
  for (let i = 0; i < REACH_SAMPLES; i += 1) {
    const t = i / (REACH_SAMPLES - 1);
    points.push({
      x: seat.x + (apex.x - seat.x) * t,
      y: seat.y + (apex.y - seat.y) * t,
    });
  }
  const resolved = await page.evaluate(
    ({ pts, id }: { pts: Point[]; id: string }) =>
      pts.map((p) => {
        const el = document.elementFromPoint(p.x, p.y);
        if (el === null) return "null";
        return el.closest(`[data-gauge="${id}"]`) !== null
          ? "gauge"
          : (el.getAttribute("data-testid") ??
              el.tagName.toLowerCase() +
                (el.className && typeof el.className === "string"
                  ? `.${el.className.split(/\s+/)[0]}`
                  : ""));
      }),
    { pts: points, id: gaugeId },
  );
  return {
    hits: resolved.filter((r) => r === "gauge").length,
    resolved,
    from: seat,
    to: apex,
  };
}

/**
 * Drag the gauge with the REAL mouse, from a pixel chosen on the drawn shaft.
 *
 * `from` defaults to the shaft's midpoint — deliberately not the grip. The
 * midpoint is where the arrow tells you to aim and is exactly where CRAFT-7's
 * measurement found nothing listening; a drag that only works at the apex is
 * the defect this wave exists to close, wearing a green test.
 */
export async function dragGauge(
  page: Page,
  gaugeId: string,
  travel: { dx?: number; dy: number },
  options: { steps?: number; release?: boolean } = {},
): Promise<Point> {
  const { seat } = await projectedSpine(page, gaugeId);
  const apex = await gripCentre(page, gaugeId);
  const mid = { x: (seat.x + apex.x) / 2, y: (seat.y + apex.y) / 2 };
  const steps = options.steps ?? 6;
  await page.mouse.move(mid.x, mid.y);
  await page.mouse.down();
  for (let step = 1; step <= steps; step += 1) {
    await page.mouse.move(
      mid.x + ((travel.dx ?? 0) * step) / steps,
      mid.y + (travel.dy * step) / steps,
    );
  }
  if (options.release !== false) await page.mouse.up();
  return mid;
}

/** A `data-*` stamp published on the viewport container, as a number. */
export async function viewportStamp(
  page: Page,
  attribute: string,
): Promise<number | null> {
  const raw = await page
    .getByTestId("viewport")
    .getAttribute(`data-${attribute}`);
  return raw === null ? null : Number.parseFloat(raw);
}

/** Assert a reach census clears the floor, printing the census either way. */
export function expectReach(
  walked: { hits: number; resolved: string[] },
  gaugeId: string,
): void {
  console.log(
    `CRAFT-9b reach ${gaugeId}: ${walked.hits}/${REACH_SAMPLES} — ${walked.resolved.join(", ")}`,
  );
  expect(
    walked.hits,
    `the drawn track must BE the target: ${walked.hits}/${REACH_SAMPLES} ` +
      `sample points resolved to ${gaugeId} (${walked.resolved.join(", ")})`,
  ).toBeGreaterThanOrEqual(REACH_FLOOR);
}
