/**
 * PROJECT A NAMED SUBTREE ONTO THE SCREEN — how big it is drawn, and how much
 * of it the modeler can actually see.
 *
 * Two questions in this wave need the same measurement and neither has a DOM
 * node to read:
 *
 *  · **the preview re-fit** — "is the open command drawing something outside
 *    the frame?" is a statement about the `command-layer` group's projected
 *    area against the canvas rect;
 *  · **the datum sheets** — "how big is the thing I have to click?" is the
 *    projected minor dimension of a `datum-sheet-<plane>` group, which is a
 *    raycast mesh with no DOM presence at all, so `elementFromPoint` and
 *    `boundingBox()` are both blind to it.
 *
 * Both are therefore read from the LIVE scene graph and the LIVE camera, the
 * same way `namedWorldBox` and the camera probe already do.
 *
 * ## Why the corner count AND the area fraction
 *
 * They are two independently-derived opinions about the same thing, and the
 * pair is the point. The area fraction is what a modeler experiences ("most of
 * the ghost is off-screen") but it is computed from an axis-aligned box in
 * SCREEN space, which overstates a subject seen at an angle. The corner count
 * is crude — nine discrete values — but it is exact about what it measures and
 * cannot be inflated by projection. When a re-fit works both go to their
 * maximum together; when they disagree, one of them is measuring something
 * nobody named, and a caller is better off refusing than averaging.
 *
 * `vertices` is reported for the same reason `namedWorldBox` reports it: a
 * name that matched NOTHING and a subject that is genuinely tiny produce very
 * similar numbers, and only this one distinguishes them.
 */
import { expect, type Page } from "./fixtures";

export interface ProjectedSubject {
  /** Vertices that contributed. 0 means the name matched nothing. */
  vertices: number;
  /** Screen-space axis-aligned box of the eight projected world corners. */
  width: number;
  height: number;
  /** `min(width, height)` — the dimension that decides whether it is clickable. */
  minor: number;
  /** How many of the eight projected corners lie inside the canvas rect (0-8). */
  cornersInFrame: number;
  /** Intersection of the screen AABB with the canvas rect, over the AABB. */
  coveredFraction: number;
  /** The canvas rect the fractions are against, for the log. */
  frame: { width: number; height: number };
}

/**
 * Project the named subtree's world bounding box and measure it on screen.
 *
 * Returns `null` when the name matches nothing, rather than a zero-sized
 * result — "absent" and "drawn very small" are different findings and the
 * datum-sheet case exists precisely because they were once confused.
 */
export async function projectNamed(
  page: Page,
  name: string,
): Promise<ProjectedSubject | null> {
  return page.evaluate((wanted: string): ProjectedSubject | null => {
    interface Attr {
      array: ArrayLike<number>;
      count: number;
      itemSize: number;
    }
    interface Obj3D {
      name: string;
      matrixWorld: { elements: number[] };
      geometry?: { attributes?: { position?: Attr } };
      traverse: (fn: (child: Obj3D) => void) => void;
      updateWorldMatrix?: (parents: boolean, children: boolean) => void;
    }
    interface Cam {
      matrixWorldInverse: { elements: number[] };
      projectionMatrix: { elements: number[] };
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

      // Accumulate the world box of every position attribute under the name.
      let vertices = 0;
      const lo = [Infinity, Infinity, Infinity];
      const hi = [-Infinity, -Infinity, -Infinity];
      scene.traverse((node) => {
        if (node.name !== wanted) return;
        node.traverse((child) => {
          const position = child.geometry?.attributes?.position;
          if (position === undefined) return;
          child.updateWorldMatrix?.(true, false);
          const m = child.matrixWorld.elements;
          for (let i = 0; i < position.count; i += 1) {
            const o = i * position.itemSize;
            const p = apply(
              m,
              position.array[o] as number,
              position.array[o + 1] as number,
              position.array[o + 2] as number,
              1,
            );
            for (let a = 0; a < 3; a += 1) {
              const v = p[a] as number;
              if (v < (lo[a] as number)) lo[a] = v;
              if (v > (hi[a] as number)) hi[a] = v;
            }
            vertices += 1;
          }
        });
      });
      if (vertices === 0) continue;

      const canvas = document.querySelector<HTMLCanvasElement>(
        '[data-testid="viewport"] canvas',
      );
      if (canvas === null) return null;
      const rect = canvas.getBoundingClientRect();

      const toScreen = (x: number, y: number, z: number): [number, number] => {
        const view = apply(camera.matrixWorldInverse.elements, x, y, z, 1);
        const clip = apply(
          camera.projectionMatrix.elements,
          view[0],
          view[1],
          view[2],
          view[3],
        );
        const wc = clip[3] === 0 ? 1e-9 : clip[3];
        return [
          rect.left + ((clip[0] / wc + 1) / 2) * rect.width,
          rect.top + ((1 - clip[1] / wc) / 2) * rect.height,
        ];
      };

      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      let cornersInFrame = 0;
      for (let c = 0; c < 8; c += 1) {
        const p = toScreen(
          (c & 1 ? hi[0] : lo[0]) as number,
          (c & 2 ? hi[1] : lo[1]) as number,
          (c & 4 ? hi[2] : lo[2]) as number,
        );
        const [sx, sy] = p;
        if (sx < minX) minX = sx;
        if (sx > maxX) maxX = sx;
        if (sy < minY) minY = sy;
        if (sy > maxY) maxY = sy;
        if (
          sx >= rect.left &&
          sx <= rect.right &&
          sy >= rect.top &&
          sy <= rect.bottom
        ) {
          cornersInFrame += 1;
        }
      }

      const width = maxX - minX;
      const height = maxY - minY;
      const overlapW = Math.max(
        0,
        Math.min(maxX, rect.right) - Math.max(minX, rect.left),
      );
      const overlapH = Math.max(
        0,
        Math.min(maxY, rect.bottom) - Math.max(minY, rect.top),
      );
      const area = width * height;
      return {
        vertices,
        width,
        height,
        minor: Math.min(width, height),
        cornersInFrame,
        coveredFraction: area <= 0 ? 0 : (overlapW * overlapH) / area,
        frame: { width: rect.width, height: rect.height },
      };
    }
    return null;
  }, name);
}

/** {@link projectNamed}, refusing rather than returning null. */
export async function expectProjected(
  page: Page,
  name: string,
): Promise<ProjectedSubject> {
  const seen = await projectNamed(page, name);
  expect(
    seen,
    `no subtree named "${name}" carried any geometry — the measurement below ` +
      `would be about nothing`,
  ).not.toBeNull();
  const found = seen as ProjectedSubject;
  expect(
    found.vertices,
    `"${name}" matched but contributed 0 vertices`,
  ).toBeGreaterThan(0);
  return found;
}

export function describeProjected(
  label: string,
  seen: ProjectedSubject,
): string {
  return (
    `${label}: ${seen.width.toFixed(1)}x${seen.height.toFixed(1)} px ` +
    `(minor ${seen.minor.toFixed(1)}), ${seen.cornersInFrame}/8 corners in ` +
    `frame, ${(seen.coveredFraction * 100).toFixed(1)}% of its projected box ` +
    `covered, from ${seen.vertices} vertices, frame ` +
    `${seen.frame.width}x${seen.frame.height}`
  );
}
