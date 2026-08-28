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

/** Clamp `v` into `[lo, hi]`, tolerating an inverted range (frame < chip). */
function clamp(v: number, lo: number, hi: number): number {
  if (hi < lo) return lo;
  return Math.min(Math.max(v, lo), hi);
}

/**
 * Place the chip for an anchor inside a frame.
 *
 * @param anchor Where the pointer came to rest, in frame coordinates.
 * @param frame  The viewport box.
 */
export function placeProposal(
  anchor: ProposalAnchor,
  frame: ProposalFrame,
): ProposalPlacement {
  const { chipWidth: width, chipHeight: height, offset, margin } = proposal;

  // Default quadrant: up and to the right of the anchor.
  const wantsLeft = anchor.x + offset + width > frame.width - margin;
  const wantsBelow = anchor.y - offset - height < margin;

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
    side: {
      x: wantsLeft ? "left" : "right",
      y: wantsBelow ? "below" : "above",
    },
  };
}
