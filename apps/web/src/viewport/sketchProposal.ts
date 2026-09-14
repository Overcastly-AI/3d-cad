/**
 * WHERE THE SKETCH PROPOSAL'S LEADER NOTE GOES — pure geometry, no DOM.
 *
 * The chip hangs off the anchor dot on a short diagonal leader, up and to the
 * right by default: that is the reading direction, and it keeps the chip clear
 * of the cursor, which would otherwise occlude the very face the note is about.
 *
 * The whole reason this is a FUNCTION rather than two Tailwind classes is the
 * FRAME. A chip that hangs half outside the viewport is not a cosmetic problem,
 * it is an unhittable control — the same defect class as a zero-area pick
 * target, arrived at from a different direction — and faces near the right and
 * top edges of the frame are exactly where a modeller works when the camera is
 * framed on a feature. So the chip FLIPS to the other side of the anchor when
 * its default side would overflow, and is CLAMPED afterwards as a backstop for
 * frames too small for either side (a clamp alone would let the chip drift off
 * its own leader, and a flip alone cannot save a 200 px-wide frame).
 *
 * Every number comes from `proposal` in `@loft/design` — the same constants the
 * Tailwind preset renders `w-proposal` / `h-proposal` from, so the arithmetic
 * here and the box on screen cannot disagree about where the chip's far edge
 * lands.
 *
 * ## The frame is not the only thing in the way
 *
 * A chip inside the frame can still be ON TOP OF A CONTROL, and the chip is the
 * LATER sibling in the HUD layer, so it wins the hit test and the control below
 * it stops answering. Measured by cross-item QA (2026-09-13): a profile solved
 * in the bottom-right corner put the chip over the reference cube, taking 29 %
 * of its seat INCLUDING ITS CENTRE — a real click aimed at the cube opened the
 * Extrude editor instead of steering the camera.
 *
 * The frame keep-out could not have caught that: 12 px from the edge is a claim
 * about the VIEWPORT, and the cube sits 42 px inside it. So the placement takes
 * OBSTRUCTIONS — the live rects of everything carrying `data-viewport-chrome`,
 * the same declaration `fitFraming.measureChrome` reads so a fit never tucks
 * the model under a panel. One declaration, two consequences, and the next
 * widget somebody docks in a corner is avoided by both without being named
 * here. A hardcoded cube rect would have gone stale the first time it moved.
 */
import { proposal } from "@loft/design";

/** A point in FRAME coordinates (px from the viewport's top-left corner). */
export interface ProposalAnchor {
  x: number;
  y: number;
}

/** The viewport's own box, in its own coordinates. */
export interface ProposalFrame {
  width: number;
  height: number;
}

export interface ProposalPlacement {
  /** The chip's box, in frame coordinates. */
  chip: { left: number; top: number; width: number; height: number };
  /**
   * The leader stub, anchor -> the chip's near corner. Derived from the placed
   * chip rather than assumed, so a flip or a clamp drags the leader with it
   * instead of leaving a stub pointing at where the chip used to be.
   */
  leader: { x1: number; y1: number; x2: number; y2: number };
  /**
   * Which side of the anchor the chip ended up on. Exposed because it is the
   * only externally checkable evidence that the flip happened at all — a
   * placement test that only asserts "inside the frame" passes just as well
   * when the chip is clamped into a corner on top of the cursor.
   */
  side: { x: "right" | "left"; y: "above" | "below" };
}

/**
 * A rect the chip must not cover, in frame coordinates. Produced by
 * `fitFraming.measureChrome`, whose shape this deliberately matches so the two
 * readers of `data-viewport-chrome` take the same input.
 */
export interface ProposalObstruction {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Clamp `v` into `[lo, hi]`, tolerating an inverted range (frame < chip). */
function clamp(v: number, lo: number, hi: number): number {
  if (hi < lo) return lo;
  return Math.min(Math.max(v, lo), hi);
}

/** Area two rects share — 0 when they merely touch. */
function overlapArea(
  chip: ProposalPlacement["chip"],
  rect: ProposalObstruction,
): number {
  const w =
    Math.min(chip.left + chip.width, rect.x + rect.width) -
    Math.max(chip.left, rect.x);
  const h =
    Math.min(chip.top + chip.height, rect.y + rect.height) -
    Math.max(chip.top, rect.y);
  return w > 0 && h > 0 ? w * h : 0;
}

/** One quadrant's placement, clamped into the frame. */
function inQuadrant(
  anchor: ProposalAnchor,
  frame: ProposalFrame,
  side: ProposalPlacement["side"],
): ProposalPlacement {
  const { chipWidth: width, chipHeight: height, offset, margin } = proposal;
  const wantsLeft = side.x === "left";
  const wantsBelow = side.y === "below";

  const rawLeft = wantsLeft ? anchor.x - offset - width : anchor.x + offset;
  const rawTop = wantsBelow ? anchor.y + offset : anchor.y - offset - height;

  const left = clamp(rawLeft, margin, frame.width - margin - width);
  const top = clamp(rawTop, margin, frame.height - margin - height);

  // The leader lands on the chip corner NEAREST the anchor, which is the
  // corner on the anchor's side in both axes.
  const x2 = wantsLeft ? left + width : left;
  const y2 = wantsBelow ? top : top + height;

  return {
    chip: { left, top, width, height },
    leader: { x1: anchor.x, y1: anchor.y, x2, y2 },
    side,
  };
}

/**
 * Place the chip for an anchor inside a frame, clear of the chrome.
 *
 * The quadrants are tried in preference order — the default one the frame
 * allows first, then the three flips — and the FIRST that covers no chrome
 * wins. When every quadrant is compromised (a narrow frame, a big panel) the
 * least-covered one is used rather than refusing: the chip has to go
 * somewhere, and half a chip over a panel edge is still readable and still
 * clickable, whereas no chip at all loses the offer entirely.
 *
 * @param anchor       Where the pointer came to rest, in frame coordinates.
 * @param frame        The viewport box.
 * @param obstructions Live chrome rects in the same coordinates (may be empty).
 */
export function placeProposal(
  anchor: ProposalAnchor,
  frame: ProposalFrame,
  obstructions: readonly ProposalObstruction[] = [],
): ProposalPlacement {
  const { chipWidth: width, chipHeight: height, offset, margin } = proposal;

  // The quadrant the FRAME wants — unchanged, and still first in line, so a
  // placement with nothing in the way is exactly what it always was.
  const preferX: "left" | "right" =
    anchor.x + offset + width > frame.width - margin ? "left" : "right";
  const preferY: "above" | "below" =
    anchor.y - offset - height < margin ? "below" : "above";
  const otherX = preferX === "left" ? "right" : "left";
  const otherY = preferY === "above" ? "below" : "above";

  // Horizontal flip before vertical: the leader reads along the line of text,
  // so trading sides costs less than trading rows.
  const order: ProposalPlacement["side"][] = [
    { x: preferX, y: preferY },
    { x: otherX, y: preferY },
    { x: preferX, y: otherY },
    { x: otherX, y: otherY },
  ];

  let best: ProposalPlacement | null = null;
  let bestCover = Infinity;
  for (const side of order) {
    const candidate = inQuadrant(anchor, frame, side);
    let cover = 0;
    for (const rect of obstructions) cover += overlapArea(candidate.chip, rect);
    if (cover === 0) return candidate;
    if (cover < bestCover) {
      best = candidate;
      bestCover = cover;
    }
  }
  // `order` is never empty, so `best` is never null — the fallback keeps the
  // return type honest without a non-null assertion.
  return (
    best ?? inQuadrant(anchor, frame, order[0] as ProposalPlacement["side"])
  );
}
