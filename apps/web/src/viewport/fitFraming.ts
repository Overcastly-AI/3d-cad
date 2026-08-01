/**
 * "Fit model" has to frame the part in the part of the frame you can SEE.
 *
 * The defect (founder capture 2026-07-31, measured on a 120×80×40 shelled
 * enclosure): `view-fit` solved against the whole canvas, and the canvas is
 * full-bleed with the feature tree, the Bodies list and the inspector FLOATING
 * over it. So a fit that was arithmetically perfect put the left third of the
 * part under the tree and the right third under the inspector. A control that
 * hides the thing it just claimed to fit is a chrome element that does not do
 * what it says — design mandate 3c.
 *
 * The fix is two numbers, both derived from the DOM the user is actually
 * looking at rather than from hardcoded panel widths (panels collapse, and a
 * fit must follow):
 *
 *  · a DISTANCE, solved from the subject's own projected corners so it exactly
 *    fills the free rect — replacing a fixed multiple of the bounding diagonal,
 *    which was blind both to the frame it was filling and to the subject's
 *    aspect ratio; and
 *  · a TARGET SHIFT — how far to slide the orbit target so the subject lands in
 *    the MIDDLE of the free rect rather than the middle of the canvas.
 *
 * Both are pure functions of rectangles here, so the framing invariant is unit
 * testable without a GPU, and the camera rig stays a thin applicator.
 */

/** A rectangle in CSS pixels, relative to the canvas's top-left corner. */
export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** How much of each canvas edge is covered by chrome, in CSS pixels. */
export interface Insets {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** Breathing room between the framed subject and the chrome (CSS pixels). */
export const FIT_MARGIN_PX = 24;

/**
 * Fired on `window` when a docked panel opens, closes or resizes. The chrome
 * announces its own change rather than the viewport polling for it: a collapse
 * is a discrete user action, and a `ResizeObserver` sweep over the whole
 * document to notice it would cost every frame for an event that happens twice
 * an hour.
 */
export const VIEWPORT_CHROME_EVENT = "loft:viewport-chrome";

/** Tell the viewport the chrome moved (see {@link VIEWPORT_CHROME_EVENT}). */
export function announceChromeChange(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(VIEWPORT_CHROME_EVENT));
}

/**
 * The insets an obstruction imposes. An obstruction is charged to exactly ONE
 * edge — a left panel eats from the left, the view rail from the bottom —
 * because charging it to two edges would let a bottom-right gizmo shrink the
 * frame twice and a fit would crawl away from a part it can see perfectly well.
 *
 * An obstruction that covers the canvas centre in both axes is ignored: it is
 * an overlay (a modal, an editor card the user can move), not a dock, and
 * treating it as a dock would make the fit lurch every time a card opened.
 */
export function insetsFor(canvas: Rect, obstruction: Rect): Insets {
  const none = { left: 0, right: 0, top: 0, bottom: 0 };
  const left = obstruction.x - canvas.x;
  const right = canvas.x + canvas.width - (obstruction.x + obstruction.width);
  const top = obstruction.y - canvas.y;
  const bottom =
    canvas.y + canvas.height - (obstruction.y + obstruction.height);
  // Fully outside the canvas in either axis — no obstruction at all.
  if (
    obstruction.width <= 0 ||
    obstruction.height <= 0 ||
    left >= canvas.width ||
    right >= canvas.width ||
    top >= canvas.height ||
    bottom >= canvas.height
  ) {
    return none;
  }
  // Straddles the canvas centre in BOTH axes — an overlay (a modal, a card the
  // user can dismiss), not a dock. Charging it to an edge would eat most of the
  // frame and make the fit lurch every time a card opened.
  const centreX = canvas.x + canvas.width / 2;
  const centreY = canvas.y + canvas.height / 2;
  if (
    obstruction.x < centreX &&
    obstruction.x + obstruction.width > centreX &&
    obstruction.y < centreY &&
    obstruction.y + obstruction.height > centreY
  ) {
    return none;
  }
  // Charge it to the edge that leaves the LARGEST free area — i.e. the edge
  // whose inset is the smallest FRACTION of its own axis. Comparing raw pixels
  // instead is the trap: a 320×340 panel in a 1600×900 frame costs 332px from
  // the left but only 240px from the top, so "fewest pixels" charges a corner
  // panel across the whole top of the frame. Measured on the assembly
  // workspace, that wasted the entire top band and pushed the model 24px out of
  // the bottom of the rect the fit had just solved for — while charging it to
  // the left (0.21 of the width, against 0.27 of the height) leaves 8% more
  // room and is what a modeler would call correct.
  //
  // The fraction also reads full-width bands right for free: a toolbar spanning
  // the frame scores 1.0 horizontally, so it can only ever be charged to top or
  // bottom.
  const candidates = [
    {
      edge: "left" as const,
      eats: left + obstruction.width,
      axis: canvas.width,
    },
    {
      edge: "right" as const,
      eats: right + obstruction.width,
      axis: canvas.width,
    },
    {
      edge: "top" as const,
      eats: top + obstruction.height,
      axis: canvas.height,
    },
    {
      edge: "bottom" as const,
      eats: bottom + obstruction.height,
      axis: canvas.height,
    },
  ].sort((a, b) => a.eats / a.axis - b.eats / b.axis);
  const cheapest = candidates[0];
  if (cheapest === undefined) return none;
  return { ...none, [cheapest.edge]: Math.max(cheapest.eats, 0) };
}

/**
 * The unobstructed rect: the canvas minus the deepest bite taken out of each
 * edge, minus a uniform margin. Never returns a degenerate rect — a frame so
 * crowded that nothing is left falls back to the canvas, because a fit that
 * zooms to infinity is worse than one that ignores a panel.
 */
export function unobstructedRect(
  canvas: Rect,
  obstructions: readonly Rect[],
  marginPx: number = FIT_MARGIN_PX,
): Rect {
  const total = obstructions.reduce<Insets>(
    (acc, obstruction) => {
      const inset = insetsFor(canvas, obstruction);
      return {
        left: Math.max(acc.left, inset.left),
        right: Math.max(acc.right, inset.right),
        top: Math.max(acc.top, inset.top),
        bottom: Math.max(acc.bottom, inset.bottom),
      };
    },
    { left: 0, right: 0, top: 0, bottom: 0 },
  );
  const x = total.left + marginPx;
  const y = total.top + marginPx;
  const width = canvas.width - x - total.right - marginPx;
  const height = canvas.height - y - total.bottom - marginPx;
  if (width < canvas.width * 0.2 || height < canvas.height * 0.2) {
    return { x: 0, y: 0, width: canvas.width, height: canvas.height };
  }
  return { x, y, width, height };
}

/**
 * One corner of the subject in CAMERA axes, relative to the subject's centre:
 * `a` along the camera's right, `b` along its up, `c` TOWARD the camera.
 */
export interface CameraSpacePoint {
  a: number;
  b: number;
  c: number;
}

/** A hair of slack for the B-rep edge overlay's own line width. */
const FIT_PADDING = 1.01;

/**
 * The camera distance at which the subject exactly fills `free` — solved from
 * the subject's corners under the real PERSPECTIVE projection.
 *
 * The old fit was a fixed multiple of the bounding DIAGONAL. That is blind
 * three times over: to the frame it is filling, to the subject's aspect ratio
 * (a long rail broadside needs far more room than a compact block of the same
 * diagonal), and to the fact that the NEAR end of a long part projects wider
 * than the far end. The first cut of this fix used orthographic half-extents
 * and measured 51px of overhang on a 260 mm rail for exactly that third reason,
 * which is why the depth term `c` is carried here rather than approximated away.
 *
 * Derivation, per corner: at distance `d` the corner sits `d − c` from the
 * camera, so its normalised screen offsets are `b / ((d−c)·tan(fov/2))` and
 * `a / ((d−c)·tan(fov/2)·aspect)`. Requiring each to stay inside the free
 * rect's share of the frame and solving for `d` gives the expression below —
 * the aspect ratio cancels into one shared `canvas.height / tan` factor.
 *
 * Returns 0 for a degenerate rect so the caller can fall back.
 */
export function fitDistance(
  corners: readonly CameraSpacePoint[],
  canvas: Rect,
  free: Rect,
  fovDeg: number,
): number {
  if (free.width <= 0 || free.height <= 0 || canvas.height <= 0) return 0;
  const tan = Math.tan((fovDeg * Math.PI) / 360);
  if (tan <= 0 || corners.length === 0) return 0;
  let distance = 0;
  for (const { a, b, c } of corners) {
    const spread =
      Math.max(Math.abs(a) / free.width, Math.abs(b) / free.height) *
      canvas.height *
      FIT_PADDING;
    distance = Math.max(distance, c + spread / tan);
  }
  return distance;
}

/**
 * Where the orbit target must move, in the camera's own RIGHT / UP directions
 * and in world units, so that a subject centred on the target appears at the
 * centre of `free` instead of the centre of the canvas.
 *
 * `visible` is the world-space size of the canvas at the target's depth (for a
 * perspective camera: `2 · distance · tan(fov/2)`, times aspect for the width).
 * The sign flip on `up` is the screen-y-down → world-y-up conversion.
 */
export function targetShift(
  canvas: Rect,
  free: Rect,
  visible: { width: number; height: number },
): { right: number; up: number } {
  if (canvas.width <= 0 || canvas.height <= 0) return { right: 0, up: 0 };
  const dx = free.x + free.width / 2 - canvas.width / 2;
  const dy = free.y + free.height / 2 - canvas.height / 2;
  // `+ 0` normalises −0 (e.g. −(0/1440)·w) to +0 so a centred rect compares
  // cleanly — the same guard `sketch/plane.ts` applies to datum origins.
  return {
    right: -(dx / canvas.width) * visible.width + 0,
    up: (dy / canvas.height) * visible.height + 0,
  };
}

/**
 * Read the live chrome out of the DOM. Every element that docks over the scene
 * carries `data-viewport-chrome`; this returns their rects in canvas
 * coordinates, so a collapsed panel simply stops being an obstruction and the
 * next fit uses the space it gave back.
 *
 * The search runs over the whole DOCUMENT, not the container's subtree: the
 * floating panels are siblings of the viewport, not children of it, and a fit
 * has to answer to what covers the pixels — not to where the markup happens to
 * sit.
 */
export function measureChrome(container: Element): {
  canvas: Rect;
  obstructions: Rect[];
} {
  const box = container.getBoundingClientRect();
  const canvas: Rect = { x: 0, y: 0, width: box.width, height: box.height };
  const obstructions: Rect[] = [];
  const scope = container.ownerDocument;
  for (const node of scope.querySelectorAll("[data-viewport-chrome]")) {
    const rect = node.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    obstructions.push({
      x: rect.x - box.x,
      y: rect.y - box.y,
      width: rect.width,
      height: rect.height,
    });
  }
  return { canvas, obstructions };
}
