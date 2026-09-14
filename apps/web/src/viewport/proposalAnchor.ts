/**
 * WHERE THE SOLVE'S OFFER POINTS — the screen anchor of a solved profile, and
 * the one channel the scene uses to hand it to the DOM (FLOW-B1).
 *
 * THE LAW OF THE IDIOM, copied here because this module exists to serve it
 * (W2 direction §1):
 *
 *   · brass + leader + `Kbd` = an offer you can take right now.
 *   · mist + no leader + no `Kbd` = a name for what is under the pointer.
 *   · band cell + eyebrow + `×` = a held state that renames verbs.
 *
 * A leader note is an ANNOTATION ON A THING, so the whole affordance rests on
 * the anchor being the thing: the pointer supplies it for the hover offer, and
 * a sketch that has just solved has no pointer at all. Its anchor is therefore
 * DERIVED — the area centroid of its biggest profile loop, projected to the
 * frame — which is the point a draughtsman would run a leader from, and is
 * inside the profile for every shape whose regions this app can already build.
 *
 * ## Why there is a refusal in here
 *
 * A leader that points at a speck, or off the edge of the frame, is a lie about
 * the thing it names — the same defect class as a zero-area pick target, told
 * from the other end. So {@link loopAnchor} RETURNS NULL rather than clamping
 * something onto the screen: with no anchor there is no chip, and `E` still
 * opens Extrude on that very sketch. A silent honest fallback beats a note
 * nobody can act on.
 *
 * ## Why a store and not props
 *
 * The projection needs the live camera, which exists only inside the r3f
 * canvas; the note is DOM in the HUD layer above it. The two sit on opposite
 * branches of the workspace tree, exactly as `viewCommands.ts` (view rail ↔
 * camera rig) and `partView.ts` (panels ↔ scene) already do — so this is the
 * established seam, not a new one. The scene publishes; the note consumes.
 */
import { proposal } from "@loft/design";
import { create } from "zustand";

import type { Point2D } from "../sketch/plane";

/** The viewport box the anchor is expressed in (frame px). */
export interface AnchorFrame {
  width: number;
  height: number;
}

/** A published anchor: a frame-space point, and the frame it was measured in. */
export interface ProposalAnchor {
  x: number;
  y: number;
  frame: AnchorFrame;
}

/**
 * The area centroid of a closed screen-space loop, or NULL where a leader note
 * would be dishonest.
 *
 * Three refusals, each a thing a user would have to squint at:
 *
 *  1. **Fewer than three points, or a non-finite one.** Not a loop.
 *  2. **A bounding box shorter than the chip.** The profile is edge-on or a
 *     speck; a chip taller than the thing it annotates reads as a card sitting
 *     on the model rather than a note about it. `chipHeight` is the measure
 *     because it is the smallest object the note itself draws.
 *  3. **A centroid outside the frame's keep-out.** `placeProposal` can flip and
 *     clamp the CHIP inside the frame, but nothing can bring the ANCHOR back:
 *     the dot would sit off-screen and the leader would run to the edge and
 *     stop, pointing at nothing.
 *
 * The shoelace centroid degenerates on a zero-area loop (a fold-back, or a
 * profile seen exactly edge-on), so the vertex mean is the fallback — but only
 * after refusal 2, which has already rejected the cases where that matters.
 */
export function loopAnchor(
  points: readonly Point2D[],
  frame: AnchorFrame,
): { x: number; y: number } | null {
  if (points.length < 3) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const point of points) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
    if (point.x < minX) minX = point.x;
    if (point.x > maxX) maxX = point.x;
    if (point.y < minY) minY = point.y;
    if (point.y > maxY) maxY = point.y;
  }
  if (maxY - minY < proposal.chipHeight) return null;

  let twiceArea = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i] as Point2D;
    const b = points[(i + 1) % points.length] as Point2D;
    const cross = a.x * b.y - b.x * a.y;
    twiceArea += cross;
    cx += (a.x + b.x) * cross;
    cy += (a.y + b.y) * cross;
  }
  let anchor: { x: number; y: number };
  if (Math.abs(twiceArea) < 1e-6) {
    let sx = 0;
    let sy = 0;
    for (const point of points) {
      sx += point.x;
      sy += point.y;
    }
    anchor = { x: sx / points.length, y: sy / points.length };
  } else {
    anchor = { x: cx / (3 * twiceArea), y: cy / (3 * twiceArea) };
  }

  const keepOut = proposal.margin;
  if (
    anchor.x < keepOut ||
    anchor.y < keepOut ||
    anchor.x > frame.width - keepOut ||
    anchor.y > frame.height - keepOut
  ) {
    return null;
  }
  return anchor;
}

interface ProposalAnchorState {
  /**
   * The sketch feature the NOTE wants an anchor for, or null when it wants
   * none. The DOM side owns this: only it knows whether an offer is due, and
   * making the scene decide would put the offer policy in two places.
   */
  subject: string | null;
  /** The scene's answer for {@link subject}, or null while it has none. */
  anchor: ProposalAnchor | null;
  requestAnchor: (subject: string | null) => void;
  publishAnchor: (anchor: ProposalAnchor | null) => void;
}

/**
 * Scene → DOM, one value. `requestAnchor(null)` also clears the anchor, so a
 * withdrawn note can never leave a stale point behind for the next subject to
 * be placed at.
 */
export const useProposalAnchorStore = create<ProposalAnchorState>((set) => ({
  subject: null,
  anchor: null,
  requestAnchor: (subject) =>
    set((state) =>
      // A CHANGE of subject drops the old anchor with it. Keeping it would let
      // the next note be placed, for one frame, at the point that belonged to
      // the last one — a leader pointing at the wrong sketch, which is the
      // exact silent-wrong-result this idiom cannot afford.
      state.subject === subject ? state : { subject, anchor: null },
    ),
  publishAnchor: (anchor) => set({ anchor }),
}));
