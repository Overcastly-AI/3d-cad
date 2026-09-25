/**
 * MEASURING A GAUGE THE WAY A USER REACHES FOR ONE.
 *
 * Extracted from `extrude-grip-reach.spec.ts` on its SECOND real use (CRAFT-9a
 * mounts the same instrument for fillet radius and chamfer distance), which is
 * the DRY rule's own trigger — extract on the second use, not the first
 * imagined one. Nothing here is new; the extrude spec's helpers were already
 * parameterised by `gaugeId` because `ParametricGauge` stamps `data-gauge` and
 * `<id>-handle` / `-sleeve` on every instrument it draws.
 *
 * ## Why these read the SCENE and not the DOM
 *
 * A drawn manipulator photographs perfectly while being unusable. `toBeVisible`
 * is a box property and `boundingBox` is a box property; only asking the
 * browser WHAT IS UNDER THIS PIXEL, along the track the instrument actually
 * draws, can see the affordance and the hit target coming apart. So the track's
 * two ends are taken from the SPINE MESH ITSELF — the cylinder is unit-height
 * and scaled to the value, so its local `(0, ±0.5, 0)` are exactly the seat and
 * the arrowhead's base, and `matrixWorld` carries whatever pose the component
 * gave it. That is a measurement of the thing the user can see rather than of
 * an assumption about it.
 *
 * **There is no `force: true` in anything built on this and there must never
 * be.** This repo has measured that flag hiding a zero-area target four times.
 */
import type { Page } from "@playwright/test";

/** How many points to walk down a projected track. */
export const SAMPLES = 16;

/**
 * The acceptance floor, from the W3 direction doc (§9).
 *
 * 12 of 16 rather than all 16 because the two ends legitimately fall outside:
 * `t = 0` sits on the seat, where the sleeve must NOT be (it would swallow the
 * pick underneath it), and the last sample rides the arrow's point where the
 * grip's own round target is inset from the square sample.
 */
export const REACH_FLOOR = 12;

export interface Point {
  x: number;
  y: number;
}

/** The grip's centre in page coordinates. */
export async function gripCentre(page: Page, gaugeId: string): Promise<Point> {
  const box = await page.getByTestId(`${gaugeId}-handle`).boundingBox();
  if (box === null) throw new Error(`the ${gaugeId} grip has no box`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** The drawn shaft's two ends, in CSS pixels. */
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
  // The cylinder's +Y end is the arrowhead's base; which of the two that is on
  // screen depends only on the camera, so pick by distance to the grip.
  const grip = await gripCentre(page, gaugeId);
  const near = (p: Point): number => Math.hypot(p.x - grip.x, p.y - grip.y);
  return near(seen.a) < near(seen.b)
    ? { seat: seen.b, base: seen.a }
    : { seat: seen.a, base: seen.b };
}

export interface ReachReport {
  hits: number;
  resolved: string[];
  from: Point;
  to: Point;
}

/** Walk the projected track and ask the browser what is under each pixel. */
export async function reach(page: Page, gaugeId: string): Promise<ReachReport> {
  const { seat } = await projectedSpine(page, gaugeId);
  const apex = await gripCentre(page, gaugeId);
  const points: Point[] = [];
  for (let i = 0; i < SAMPLES; i += 1) {
    const t = i / (SAMPLES - 1);
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

/** The midpoint of the drawn shaft — where the arrow tells you to aim. */
export async function shaftMidpoint(
  page: Page,
  gaugeId: string,
): Promise<Point> {
  const { seat } = await projectedSpine(page, gaugeId);
  const apex = await gripCentre(page, gaugeId);
  return { x: (seat.x + apex.x) / 2, y: (seat.y + apex.y) / 2 };
}
