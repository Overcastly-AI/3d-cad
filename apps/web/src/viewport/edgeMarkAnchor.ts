/**
 * WHERE AN EDGE'S PICK DIAMOND GOES — the point of the edge that the BAND will
 * actually answer with, rather than the edge's mid-span wherever that falls.
 *
 * PICKMARK-OCCLUDE-1, split out of SEL-8. R-8's other sentence — "several
 * sitting mid-FACE rather than on any visible edge" — is a different defect
 * from the missing hover highlight and has a different cause. Measured on the
 * same coupling, with the marks' own `pointer-events` disabled so the BAND
 * answers at each mark's centre: of 21 diamonds, **8 agreed**, 8 read `none`
 * (the mark floats over material that hides its edge, so `resolveBandEdge`
 * refuses) and 5 resolved to a DIFFERENT edge. Click the mark and you pick edge
 * 1; click one pixel outside it and you pick edge 6. Two hit-tests for one
 * entity, disagreeing about reachability — which is worse than either answer,
 * because the mark is the thing that LOOKS authoritative.
 *
 * The mid-span is not sacred: it is a placement convention, and the convention
 * is wrong exactly where the mid-span is buried. So the mark moves ALONG ITS
 * OWN EDGE to the middle of the longest stretch the band accepts, and only when
 * no part of the edge is reachable at all does it stop being drawn there
 * (`buried`) — which is a statement about the edge, not a way of hiding a
 * control: the diamond stays a focusable, named button, and focusing it x-rays
 * the edge.
 *
 * PURE on purpose, like `edgeBand.ts` and `bodyPartition.ts` next door: "which
 * point of a curve is the one you can address" is precisely the decision a
 * screenshot cannot check, and keeping it out of the scene means it is asserted
 * against arithmetic rather than eyeballed. The three.js plumbing — the
 * raycast, the camera, the frame budget — lives in `useEdgeMarkAnchors`.
 */

/**
 * How many points of one edge may be tested per recompute.
 *
 * A budget rather than "every point", because a tessellated circle arrives with
 * ~64 vertices and a fully buried edge would otherwise pay for all of them on
 * every camera change — 21 edges x 64 hit-tests is the per-frame cost that got
 * this split out of SEL-8 in the first place. Nine samples put a candidate
 * every ~10 % of the edge, far finer than the 24 px corridor the band offers,
 * so a visible stretch of any practical size is found.
 */
export const ANCHOR_SAMPLE_BUDGET = 9;

/**
 * How many hit-tests one recompute may spend, across ALL edges.
 *
 * MEASURED, not chosen: on the reference coupling one band+surface hit-test
 * costs **0.259-0.270 ms** (420 timed calls through the real raycast at
 * 1600x1000), and an unbudgeted pass over its 21 edges costs 10 x 1 + 11 x 9 =
 * 109 tests = **28.2 ms** — comfortably over the 16.67 ms a 60 fps frame has,
 * and the exact risk this ticket was split out of SEL-8 to answer. A cap of 24
 * keeps the worst recompute at ~6.5 ms, about a third of the frame, on ANY
 * part: the work that does not fit is carried to the next frame by a rotating
 * cursor, so the cost per frame is bounded by this number and not by the edge
 * count.
 *
 * What it costs in exchange is latency, not correctness: a full pass over the
 * coupling takes ~5 frames, so during a fast orbit a mark can be that far
 * behind the camera. At rest the loop always drains — the caller keeps asking
 * for frames until every edge has been refreshed — so the settled placement,
 * which is the one anybody picks from, is exact.
 */
export const ANCHOR_FRAME_BUDGET = 24;

/**
 * How far from an edge's ENDS a mark may be seated, as a fraction of arc
 * length.
 *
 * An endpoint is a CORNER: it is the point this edge shares with its
 * neighbours, so their 24 px corridors are exactly as close as this edge's own
 * and the band's nearest-in-depth rule can legitimately answer either. Seating
 * a mark there manufactures the disagreement this ticket exists to remove, and
 * it also shortens the corridor a user can sweep from the mark. The inset keeps
 * every candidate on the edge's own interior.
 */
export const ANCHOR_END_INSET = 0.08;

/**
 * Candidate positions along one edge, as fractions of ARC LENGTH, ORDERED FROM
 * THE MID-SPAN OUTWARD.
 *
 * Arc length rather than vertex index, and that is load-bearing rather than
 * tidy: a straight edge's polyline is `[start, end]`, so an index-based middle
 * is the END VERTEX. An earlier draft did exactly that and cost a straight edge
 * its corridor — `pick-affordance`'s reach sweep dropped it from 40 px to 28 px
 * — because the mark had moved onto the corner.
 *
 * The order means a mark that can stay at its mid-span does, so this change is
 * invisible wherever it was not needed; the spread means the search reaches
 * both ends of the edge (inset) inside the budget, which is what lets a diamond
 * escape onto the visible quarter of a mostly-hidden bore.
 */
export function anchorCandidates(
  budget: number = ANCHOR_SAMPLE_BUDGET,
  inset: number = ANCHOR_END_INSET,
): number[] {
  const wanted = Math.max(1, Math.floor(budget));
  if (wanted === 1) return [0.5];
  const lo = Math.min(0.5, Math.max(0, inset));
  const hi = 1 - lo;
  const seen = new Set<number>([0.5]);
  for (let i = 0; i < wanted; i += 1) {
    seen.add(lo + ((hi - lo) * i) / (wanted - 1));
  }
  return [...seen].sort(
    (a, b) => Math.abs(a - 0.5) - Math.abs(b - 0.5) || a - b,
  );
}

/** Where one edge's mark sits, and whether the edge is reachable at all. */
export interface EdgeAnchor {
  /** Fraction of the edge's arc length, in [0, 1]. */
  at: number;
  /** No sampled point of this edge is addressable from the current camera. */
  buried: boolean;
}

/**
 * The anchor for one edge: the mid-span when the band answers there, otherwise
 * the MIDDLE OF THE LONGEST ADDRESSABLE RUN, otherwise buried.
 *
 * ## Why the mid-span is tried first
 *
 * It is the convention, so an edge that can keep it does — which makes this
 * change invisible wherever it was not needed. Getting that ordering wrong cost
 * a measured round trip: an earlier draft consulted a remembered seat first, so
 * a placement chosen during the opening camera FLIGHT (when half the part is
 * edge-on) survived into the settled view and marks that were already correct
 * ended up parked off their mid-span — the census moved 8 -> 9 while the
 * wrong-edge count went 5 -> 10. The seat is now a pure function of the CURRENT
 * camera, with no memory to go stale.
 *
 * ## Why the MIDDLE of the run and not the first point that answers
 *
 * Walking outward and taking the first hit puts the diamond exactly at the
 * boundary of the visible stretch — on the silhouette, where half its corridor
 * runs off the geometry. The middle of the run is the seat with the most edge
 * on either side of it, which is what both a mouse and a thumb want.
 */
export function chooseAnchor(
  addressable: (fraction: number) => boolean,
  budget: number = ANCHOR_SAMPLE_BUDGET,
  inset: number = ANCHOR_END_INSET,
): EdgeAnchor {
  if (addressable(0.5)) return { at: 0.5, buried: false };

  // Candidates in POSITION order, so "consecutive" means "adjacent along the
  // edge" — the outward-from-mid order cannot express a run at all.
  const ordered = anchorCandidates(budget, inset).sort((a, b) => a - b);
  const answers = ordered.map(addressable);
  const middleOf = (start: number, length: number): number =>
    ordered[start + (length >> 1)] as number;

  let bestStart = -1;
  let bestLength = 0;
  let runStart = -1;
  for (let i = 0; i <= answers.length; i += 1) {
    if (answers[i] === true) {
      if (runStart === -1) runStart = i;
      continue;
    }
    if (runStart === -1) continue;
    const length = i - runStart;
    const better =
      length > bestLength ||
      (length === bestLength &&
        Math.abs(middleOf(runStart, length) - 0.5) <
          Math.abs(middleOf(bestStart, bestLength) - 0.5));
    if (better) {
      bestStart = runStart;
      bestLength = length;
    }
    runStart = -1;
  }

  // Nothing on this edge answers. The mark keeps its conventional place so its
  // accessible name still describes where the edge IS; `buried` is what stops
  // it being drawn there at full strength.
  if (bestLength === 0) return { at: 0.5, buried: true };
  return { at: middleOf(bestStart, bestLength), buried: false };
}
