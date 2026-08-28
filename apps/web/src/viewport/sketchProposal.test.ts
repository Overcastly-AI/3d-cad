import { proposal } from "@loft/design";
import { describe, expect, it } from "vitest";

import { placeProposal } from "./sketchProposal";

const FRAME = { width: 1280, height: 800 };

/** Fully inside the frame, keep-out included — the property that matters. */
function insideFrame(
  chip: { left: number; top: number; width: number; height: number },
  frame: { width: number; height: number },
): boolean {
  return (
    chip.left >= proposal.margin &&
    chip.top >= proposal.margin &&
    chip.left + chip.width <= frame.width - proposal.margin &&
    chip.top + chip.height <= frame.height - proposal.margin
  );
}

describe("placeProposal", () => {
  it("hangs up and to the right of the anchor with room to spare", () => {
    const { chip, side } = placeProposal({ x: 400, y: 400 }, FRAME);
    expect(side).toEqual({ x: "right", y: "above" });
    expect(chip.left).toBe(400 + proposal.offset);
    expect(chip.top).toBe(400 - proposal.offset - proposal.chipHeight);
  });

  it("never sits under the cursor", () => {
    // The gap the offset buys: the chip's near edge clears the anchor in BOTH
    // axes, so the pointer is never inside the chip's box at rest.
    const { chip } = placeProposal({ x: 400, y: 400 }, FRAME);
    expect(chip.left).toBeGreaterThan(400);
    expect(chip.top + chip.height).toBeLessThan(400);
  });

  it("flips to the LEFT rather than hanging off the right edge", () => {
    const anchor = { x: FRAME.width - 20, y: 400 };
    const { chip, side } = placeProposal(anchor, FRAME);
    expect(side.x).toBe("left");
    expect(chip.left).toBe(anchor.x - proposal.offset - proposal.chipWidth);
    expect(insideFrame(chip, FRAME)).toBe(true);
  });

  it("flips BELOW rather than hanging off the top edge", () => {
    const anchor = { x: 400, y: 8 };
    const { chip, side } = placeProposal(anchor, FRAME);
    expect(side.y).toBe("below");
    expect(chip.top).toBe(anchor.y + proposal.offset);
    expect(insideFrame(chip, FRAME)).toBe(true);
  });

  it("flips in BOTH axes in the top-right corner", () => {
    const { chip, side } = placeProposal({ x: FRAME.width - 6, y: 6 }, FRAME);
    expect(side).toEqual({ x: "left", y: "below" });
    expect(insideFrame(chip, FRAME)).toBe(true);
  });

  it("drags the leader onto whichever corner the chip flipped to", () => {
    const right = placeProposal({ x: 400, y: 400 }, FRAME);
    // Default quadrant: the leader lands on the chip's bottom-LEFT corner.
    expect(right.leader.x2).toBe(right.chip.left);
    expect(right.leader.y2).toBe(right.chip.top + right.chip.height);

    const left = placeProposal({ x: FRAME.width - 20, y: 400 }, FRAME);
    // Flipped: it lands on the bottom-RIGHT corner instead. A leader that
    // stayed on `chip.left` here would point into open space.
    expect(left.leader.x2).toBe(left.chip.left + left.chip.width);
    expect(left.leader.y2).toBe(left.chip.top + left.chip.height);
  });

  it("always starts the leader at the anchor itself", () => {
    for (const anchor of [
      { x: 0, y: 0 },
      { x: 640, y: 400 },
      { x: FRAME.width, y: FRAME.height },
    ]) {
      const { leader } = placeProposal(anchor, FRAME);
      expect(leader.x1).toBe(anchor.x);
      expect(leader.y1).toBe(anchor.y);
    }
  });

  it("stays inside the frame from every corner and edge", () => {
    const xs = [0, 1, 40, 640, FRAME.width - 40, FRAME.width - 1, FRAME.width];
    const ys = [
      0,
      1,
      40,
      400,
      FRAME.height - 40,
      FRAME.height - 1,
      FRAME.height,
    ];
    for (const x of xs) {
      for (const y of ys) {
        const { chip } = placeProposal({ x, y }, FRAME);
        expect(insideFrame(chip, FRAME), `anchor ${x},${y}`).toBe(true);
      }
    }
  });

  it("clamps rather than exploding when the frame cannot hold the chip", () => {
    // A flip cannot save a frame narrower than the chip; the clamp is the
    // backstop, and `left` must still be a real number a style can take.
    const tiny = { width: 60, height: 40 };
    const { chip } = placeProposal({ x: 30, y: 20 }, tiny);
    expect(Number.isFinite(chip.left)).toBe(true);
    expect(Number.isFinite(chip.top)).toBe(true);
    expect(chip.left).toBe(proposal.margin);
    expect(chip.top).toBe(proposal.margin);
  });
});
