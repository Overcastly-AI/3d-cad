import { expect, type Page } from "@playwright/test";

import {
  silhouette,
  type ScreenBox,
  type SilhouetteOptions,
} from "./perception";
import { waitForFrames } from "./support";

/**
 * STRUCTURAL INVARIANTS — the one-line gates that would have caught two of the
 * founder's reports before he saw them (FB-17, final paragraph).
 *
 * Both are the same idea: most of what makes a modeller feel broken is not a
 * wrong RESULT, it is a right result delivered while something else silently
 * changed. Specs assert the result and never look at the something else.
 *
 *  · CAMERA (FB-1) — "after the extrude it flipped to xy", and worse, a sketch
 *    on a face "kept snapping back and I couldn't see it". The extrude was
 *    correct every time; the auto-fit slammed the viewpoint to iso on every
 *    rebuild. Record the direction, do the thing, assert it did not move.
 *  · OCCLUSION (FB-7, photographed) — the editor panel opened directly over the
 *    model. Every assertion about the panel passed. Nobody asked where the
 *    model was.
 */

/**
 * Install the scene probe. MUST be called before `page.goto`, because it hooks
 * three.js at construction time.
 *
 * How it works, since it looks like magic: three.js dispatches an `observe`
 * event to a global `__THREE_DEVTOOLS__` whenever a `Scene` is constructed —
 * the seam the official three.js devtools extension uses. We install an
 * `EventTarget` there before any app code runs, and wrap each scene's
 * `onBeforeRender`, which `WebGLRenderer.render` calls with the camera it is
 * rendering that scene from. That yields the REAL camera object with zero
 * changes to application code, which matters here: QA does not get to add test
 * hooks to the product, and `data-camera-pos` alone cannot answer this question
 * (it is a position, stamped only on settle, and the fix for FB-1 deliberately
 * MOVES the position while preserving the direction — so comparing positions
 * would fail on correct behaviour).
 *
 * Two scenes render into this canvas: the model scene and the reference cube's
 * (drei `Hud`, its own scene and orthographic camera). They are disambiguated
 * by preferring the camera whose position matches the viewport's own
 * `data-camera-pos` stamp, falling back to the first scene observed (r3f
 * constructs the root store's scene before any portal). `qa-harness.spec.ts`
 * asserts the agreement so a silent mis-pick cannot hide.
 */
export async function installSceneProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    const bus = new EventTarget();
    w["__THREE_DEVTOOLS__"] = bus;
    const order: string[] = [];
    const cameras: Record<string, unknown> = {};
    w["__loftSceneOrder"] = order;
    w["__loftCameras"] = cameras;
    bus.addEventListener("observe", (event) => {
      const scene = (event as CustomEvent).detail as {
        isScene?: boolean;
        uuid: string;
        onBeforeRender?: (...args: unknown[]) => void;
      };
      if (scene?.isScene !== true) return;
      order.push(scene.uuid);
      const prior = scene.onBeforeRender;
      scene.onBeforeRender = (...args: unknown[]) => {
        prior?.apply(scene, args);
        cameras[scene.uuid] = args[2];
      };
    });
  });
}

export interface CameraPose {
  /** Unit view direction in world space (where the camera is looking). */
  direction: [number, number, number];
  position: [number, number, number];
  up: [number, number, number];
  /** True when the picked camera agrees with the viewport's own stamp. */
  agreesWithStamp: boolean;
}

/** Read the live camera pose. Requires {@link installSceneProbe}. */
export async function cameraPose(page: Page): Promise<CameraPose> {
  const pose = await page.evaluate((): CameraPose | null => {
    interface Vec {
      x: number;
      y: number;
      z: number;
    }
    interface Cam {
      position: Vec;
      up: Vec;
      matrixWorld: { elements: number[] };
    }
    const w = window as unknown as Record<string, unknown>;
    const order = (w["__loftSceneOrder"] ?? []) as string[];
    const cameras = (w["__loftCameras"] ?? {}) as Record<string, Cam>;
    const stamp = document
      .querySelector('[data-testid="viewport"]')
      ?.getAttribute("data-camera-pos");
    const stamped = stamp
      ? stamp.split(",").map((value) => Number(value))
      : null;
    const near = (camera: Cam): boolean =>
      stamped !== null &&
      stamped.length === 3 &&
      Math.abs(camera.position.x - (stamped[0] as number)) < 0.2 &&
      Math.abs(camera.position.y - (stamped[1] as number)) < 0.2 &&
      Math.abs(camera.position.z - (stamped[2] as number)) < 0.2;
    let picked: Cam | null = null;
    let agrees = false;
    for (const uuid of order) {
      const camera = cameras[uuid];
      if (camera === undefined) continue;
      if (near(camera)) {
        picked = camera;
        agrees = true;
        break;
      }
      picked ??= camera;
    }
    if (picked === null) return null;
    // -Z column of the world matrix is the camera's forward axis.
    const e = picked.matrixWorld.elements;
    const forward: [number, number, number] = [
      -(e[8] as number),
      -(e[9] as number),
      -(e[10] as number),
    ];
    const length = Math.hypot(...forward) || 1;
    return {
      direction: [
        forward[0] / length,
        forward[1] / length,
        forward[2] / length,
      ],
      position: [picked.position.x, picked.position.y, picked.position.z],
      up: [picked.up.x, picked.up.y, picked.up.z],
      agreesWithStamp: agrees,
    };
  });
  if (pose === null) {
    throw new Error(
      "cameraPose: no camera captured — call installSceneProbe(page) BEFORE page.goto",
    );
  }
  return pose;
}

/** Angle between two unit vectors, in degrees. */
export function angleBetween(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): number {
  const dot = Math.min(
    1,
    Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]),
  );
  return (Math.acos(dot) * 180) / Math.PI;
}

/**
 * Wait until the camera stops moving, then return its pose.
 *
 * NOT optional politeness — without it this whole gate is a flake generator,
 * and the measurement that proves it is worth writing down. A mouse orbit ends
 * with OrbitControls damping still coasting, so sampling the "baseline"
 * immediately after the drag captures a moving camera. Measured on a real
 * orbit: 11.02° of further travel over the next 30 frames, another 2.78° over
 * the following 1.5 s, and 1.16° more while an editor panel was opened — while
 * the REBUILD under test moved the camera 0.071°. A gate that read the baseline
 * early would report ~10° of "the extrude stole my viewpoint" that no user
 * experienced, and the honest 0.071° would be buried in it.
 *
 * The condition is the camera's own: two consecutive samples, a few painted
 * frames apart, that agree to within `epsilonDeg`. Not a `waitForTimeout`
 * guess at how long damping takes.
 */
export async function waitForCameraRest(
  page: Page,
  options: { epsilonDeg?: number; timeoutMs?: number } = {},
): Promise<CameraPose> {
  const { epsilonDeg = 0.05, timeoutMs = 15_000 } = options;
  const deadline = Date.now() + timeoutMs;
  let previous = await cameraPose(page);
  for (;;) {
    await waitForFrames(page, 6);
    const current = await cameraPose(page);
    if (angleBetween(previous.direction, current.direction) <= epsilonDeg) {
      return current;
    }
    previous = current;
    if (Date.now() > deadline) {
      throw new Error(
        `waitForCameraRest: camera still moving after ${timeoutMs}ms ` +
          `(last direction ${current.direction.map((v) => v.toFixed(3)).join(",")})`,
      );
    }
  }
}

/**
 * Run `action` and assert the camera is still pointing where it was.
 *
 * DIRECTION, deliberately, not position: re-framing distance and target when a
 * body changes is the behaviour users want and the reason the auto-fit exists.
 * Taking the VIEWPOINT away is the defect. That distinction is the whole of the
 * FB-1 fix, so a gate that compared positions would fail on the fix.
 *
 * Both samples wait for rest by default (see {@link waitForCameraRest}); pass
 * `settle: false` only when you have already established the camera is static
 * and want the raw comparison.
 *
 * Returns the measured drift in degrees.
 */
export async function expectCameraStable(
  page: Page,
  action: () => Promise<void>,
  options: { maxDegrees?: number; settle?: boolean } = {},
): Promise<number> {
  const { maxDegrees = 1, settle = true } = options;
  const before = settle
    ? await waitForCameraRest(page)
    : await cameraPose(page);
  await action();
  const after = settle ? await waitForCameraRest(page) : await cameraPose(page);
  const drift = angleBetween(before.direction, after.direction);
  expect(
    drift,
    `camera direction moved ${drift.toFixed(2)}° across the action ` +
      `(${before.direction.map((v) => v.toFixed(3)).join(",")} → ` +
      `${after.direction.map((v) => v.toFixed(3)).join(",")})`,
  ).toBeLessThanOrEqual(maxDegrees);
  return drift;
}

export interface ChromeRect extends ScreenBox {
  /** The `data-viewport-chrome` name, e.g. `panel-tree`. */
  name: string;
}

/**
 * Every element docked over the scene, in page coordinates.
 *
 * Reads the SAME `data-viewport-chrome` contract the app's own fit uses
 * (`viewport/fitFraming.measureChrome`), so a new panel is covered by this gate
 * the day it is added — one convention, not a list to maintain here.
 *
 * `extraSelectors` exists because "it forgot the attribute" is not a hole in
 * this gate, it is a FINDING. Measured 2026-08-01: the feature editors
 * (`[data-testid="extrude-editor"]` et al.) float over the viewport at
 * x 344–664 and carry NO `data-viewport-chrome`, so the app's own free-rect fit
 * cannot see them either — which is a large part of why FB-7 happens at all.
 * Naming such a panel here gates it anyway; the attribute is still the fix.
 */
export async function chromeRects(
  page: Page,
  extraSelectors: readonly string[] = [],
): Promise<ChromeRect[]> {
  return page.evaluate((extra: readonly string[]): ChromeRect[] => {
    const rects: ChromeRect[] = [];
    const visible = (node: Element): boolean => {
      const style = window.getComputedStyle(node);
      return style.visibility !== "hidden" && style.display !== "none";
    };
    for (const node of document.querySelectorAll("[data-viewport-chrome]")) {
      const rect = node.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0 || !visible(node)) continue;
      rects.push({
        name: node.getAttribute("data-viewport-chrome") ?? "chrome",
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
      });
    }
    for (const selector of extra) {
      for (const node of document.querySelectorAll(selector)) {
        if (node.hasAttribute("data-viewport-chrome")) continue; // already in
        const rect = node.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0 || !visible(node)) continue;
        rects.push({
          name: `${selector} (undeclared)`,
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
        });
      }
    }
    return rects;
  }, extraSelectors);
}

/** Overlap area of two boxes, in CSS px². */
export function overlapArea(a: ScreenBox, b: ScreenBox): number {
  const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const height = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return width <= 0 || height <= 0 ? 0 : width * height;
}

export interface OcclusionReport {
  model: ScreenBox;
  modelArea: number;
  /** Lit pixels the model box was derived from. */
  modelPixels: number;
  /** Chrome elements found at all — 0 means this gate measured NOTHING. */
  chromeCount: number;
  /** Overlapping chrome, worst first. */
  offenders: { name: string; area: number; fraction: number }[];
  /** Largest single overlap as a fraction of the model's screen box. */
  worstFraction: number;
}

export interface OcclusionOptions extends SilhouetteOptions {
  /** Chrome names to exclude from the comparison. */
  ignore?: readonly string[];
  /** Panels to include that never declared `data-viewport-chrome`. */
  extraSelectors?: readonly string[];
}

/** Which chrome covers the model right now, and by how much. */
export async function measureOcclusion(
  page: Page,
  options: OcclusionOptions = {},
): Promise<OcclusionReport> {
  const { ignore = [], extraSelectors = [], ...sampling } = options;
  const model = await silhouette(page, sampling);
  const area = Math.max(
    (model.box.right - model.box.left) * (model.box.bottom - model.box.top),
    1,
  );
  const rects = await chromeRects(page, extraSelectors);
  const offenders = rects
    .filter((rect) => !ignore.includes(rect.name))
    .map((rect) => {
      const overlap = overlapArea(model.box, rect);
      return { name: rect.name, area: overlap, fraction: overlap / area };
    })
    .filter((entry) => entry.area > 0)
    .sort((a, b) => b.area - a.area);
  return {
    model: model.box,
    modelArea: area,
    modelPixels: model.pixels,
    chromeCount: rects.length,
    offenders,
    worstFraction: offenders[0]?.fraction ?? 0,
  };
}

/**
 * Assert no floating chrome sits on top of the model.
 *
 * `maxFraction` defaults to 0 — panels and parts do not share pixels. It is a
 * parameter because a transient overlay (a drag ghost, a tooltip) can be
 * legitimate; a persistent editor is not, which is the FB-7 case.
 *
 * The two guards before the real assertion are not ceremony, they are the
 * lesson this repo keeps relearning: a gate is only as honest as its INPUT. If
 * the body has not rendered, or if `data-viewport-chrome` were ever dropped,
 * every overlap would be zero and this would report health forever.
 */
export async function expectModelUnoccluded(
  page: Page,
  options: OcclusionOptions & { maxFraction?: number } = {},
): Promise<OcclusionReport> {
  const { maxFraction = 0, ...rest } = options;
  const report = await measureOcclusion(page, rest);
  expect(
    report.modelPixels,
    "no lit body on canvas to occlude",
  ).toBeGreaterThan(500);
  expect(
    report.chromeCount,
    "no [data-viewport-chrome] found — this gate would pass vacuously",
  ).toBeGreaterThan(0);
  expect(
    report.worstFraction,
    `chrome over the model: ${JSON.stringify(report.offenders)} ` +
      `(model box ${JSON.stringify(report.model)})`,
  ).toBeLessThanOrEqual(maxFraction);
  return report;
}
