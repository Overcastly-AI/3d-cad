/**
 * WHICH EDGE A POINTER ON AN EDGE MARK MEANS (EDGE-MARK-OVERLAP).
 *
 * `useEdgeMarkAnchors` walks crowded marks apart, but it cannot always: on a
 * 2 mm wall seen from far enough away, the outer and inner rim edges run a few
 * pixels apart along their WHOLE length, so no seat on either is clear of the
 * other, and the 24 px discs overlap. The browser then hands the click to
 * whichever disc is stacked on top, and on the enclosure that was the inner
 * rim, so a click aimed at the outer rim filleted the inner one.
 *
 * So the click does not trust the DOM's stacking. It asks the question Fusion
 * 360 and SolidWorks answer for a pre-highlight: of the edges whose marks are
 * under the pointer, which edge is NEAREST THE POINTER on screen? A mark's
 * centre lies on its own edge, so clicking a mark's centre always picks that
 * mark's edge, whichever disc happens to be drawn on top there. A mark with no
 * neighbour under the pointer answers its own edge, exactly as before.
 *
 * Pure, and in CSS pixels relative to the canvas, so it is unit-tested without
 * a GPU; `EdgePickOverlay` projects the scene into these terms.
 */

/** Half of `PickNode`'s 24 px target: a pointer within it is on the mark. */
export const MARK_RADIUS_PX = 12;

/**
 * Edges whose distances from the pointer differ by no more than this are a
 * tie, settled by the nearer MARK centre. A click's `clientX`/`clientY` are
 * whole pixels, and two rims of a 2 mm wall seen from afar are only a pixel
 * or two apart, so below this the edge distance is rounding, not aim; the
 * mark the pointer is on is what the user aimed at.
 */
export const EDGE_TIE_PX = 3;

/** One live edge mark, already projected to canvas CSS pixels. */
export interface ScreenEdgeMark {
  /** The overlay index the pick reports. */
  index: number;
  /** The mark's centre. */
  x: number;
  y: number;
}

/** Shortest distance from a point to a screen polyline (x0, y0, x1, y1, ...). */
export function distanceToPolylinePx(
  px: number,
  py: number,
  path: ArrayLike<number>,
): number {
  const n = path.length >> 1;
  if (n === 0) return Infinity;
  let best = Infinity;
  if (n === 1) return Math.hypot(px - path[0]!, py - path[1]!);
  for (let i = 0; i + 1 < n; i += 1) {
    const ax = path[2 * i]!;
    const ay = path[2 * i + 1]!;
    const bx = path[2 * i + 2]!;
    const by = path[2 * i + 3]!;
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy;
    const t =
      len2 === 0
        ? 0
        : Math.min(1, Math.max(0, ((px - ax) * dx + (py - ay) * dy) / len2));
    const d = Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
    if (d < best) best = d;
  }
  return best;
}

/**
 * The edge a pointer at (px, py) on mark `own` addresses.
 *
 * Candidates are `own` plus every mark whose disc also contains the pointer.
 * The nearest edge to the pointer wins; on a tie (`EDGE_TIE_PX`) the nearer
 * mark centre wins, and then `own`. `pathOf` projects an edge's
 * polyline on demand, so only the handful of candidates are ever projected.
 */
export function resolveMarkPick(
  px: number,
  py: number,
  own: number,
  marks: readonly ScreenEdgeMark[],
  pathOf: (index: number) => ArrayLike<number> | null,
  radius: number = MARK_RADIUS_PX,
): number {
  const scored: { index: number; edge: number; centre: number }[] = [];
  for (const mark of marks) {
    const centre = Math.hypot(px - mark.x, py - mark.y);
    if (mark.index !== own && centre > radius) continue;
    const path = pathOf(mark.index);
    const along = path === null ? Infinity : distanceToPolylinePx(px, py, path);
    scored.push({
      index: mark.index,
      edge: Number.isFinite(along) ? along : centre,
      centre,
    });
  }
  if (scored.length === 0) return own;
  // Every edge within the tie window of the nearest is a contender; of
  // those, the nearest mark centre wins, and `own` breaks an exact tie.
  const nearest = Math.min(...scored.map((s) => s.edge));
  let best = own;
  let bestCentre = Infinity;
  for (const s of scored) {
    if (s.edge > nearest + EDGE_TIE_PX) continue;
    if (
      s.centre < bestCentre - 0.5 ||
      (Math.abs(s.centre - bestCentre) <= 0.5 && s.index === own)
    ) {
      best = s.index;
      bestCentre = s.centre;
    }
  }
  return best;
}
