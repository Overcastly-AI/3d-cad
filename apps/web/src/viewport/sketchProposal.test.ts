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

/**
 * THE CHROME KEEP-OUT (cross-item QA, 2026-09-13).
 *
 * The defect was not a chip outside the frame — it was a chip INSIDE the frame
 * and on top of a control, which the frame keep-out cannot express. The cube's
 * measured seat at 1600x1000 is the fixture, so these cases fail for the same
 * reason the browser did.
 */
describe("placeProposal, clear of the chrome", () => {
  const WIDE = { width: 1600, height: 1000 };
  /** The reference cube's measured seat at 1600x1000 (QA's own numbers). */
  const CUBE = { x: 1450, y: 802, width: 108, height: 108 };

  /** Do these two rects share any area at all? */
  function covers(
    chip: { left: number; top: number; width: number; height: number },
    rect: { x: number; y: number; width: number; height: number },
  ): boolean {
    return (
      chip.left < rect.x + rect.width &&
      chip.left + chip.width > rect.x &&
      chip.top < rect.y + rect.height &&
      chip.top + chip.height > rect.y
    );
  }

  it("takes the cube's seat when nothing tells it not to", () => {
    // The NEGATIVE CONTROL, and it is the whole point of the case below: with
    // no obstruction the placement is exactly what shipped, so the next case
    // is measuring the keep-out and not some unrelated change of default.
    const anchor = { x: 1420, y: 880 };
    const { chip } = placeProposal(anchor, WIDE);
    expect(covers(chip, CUBE)).toBe(true);
  });

  it("moves off the cube's seat once the cube is declared", () => {
    const anchor = { x: 1420, y: 880 };
    const { chip } = placeProposal(anchor, WIDE, [CUBE]);
    expect(covers(chip, CUBE)).toBe(false);
    expect(insideFrame(chip, WIDE)).toBe(true);
  });

  it("keeps the default quadrant when the chrome is nowhere near", () => {
    // A keep-out that moved the chip on every placement would be a worse
    // affordance than the one it replaced: the leader's default direction is
    // the reading direction, and it is only spent when it has to be.
    const clear = placeProposal({ x: 400, y: 400 }, WIDE, [CUBE]);
    expect(clear.side).toEqual({ x: "right", y: "above" });
    expect(clear.chip).toEqual(placeProposal({ x: 400, y: 400 }, WIDE).chip);
  });

  it("prefers a horizontal flip to a vertical one", () => {
    // Trading sides keeps the chip on the anchor's own line; trading rows
    // moves it a whole chip-height away from the thing it names.
    const anchor = { x: 1420, y: 880 };
    const { side } = placeProposal(anchor, WIDE, [CUBE]);
    expect(side.x).toBe("left");
  });

  it("settles on the LEAST covered quadrant when every one is compromised", () => {
    // A wall down the right half leaves no clean quadrant. The chip still has
    // to go somewhere — an offer withheld because of a panel is the offer lost
    // — so the rule is least-covered, not refuse. Anchored 40 px inside the
    // wall: the default quadrant is buried (120 px of chip x 24), the flip
    // hangs 32 px of chip over the wall's edge and is the better of the two.
    const wall = { x: 600, y: 0, width: 1000, height: 1000 };
    const { chip, side } = placeProposal({ x: 640, y: 400 }, WIDE, [wall]);
    expect(insideFrame(chip, WIDE)).toBe(true);
    expect(side.x).toBe("left");
    expect(chip.left).toBe(640 - proposal.offset - proposal.chipWidth);
  });

  it("does not thrash when every quadrant is covered EQUALLY", () => {
    // Deep inside the wall, no flip buys anything. The chip stays where the
    // frame put it rather than picking a side by accident of iteration order —
    // a placement that moved for no gain would read as a glitch.
    const wall = { x: 600, y: 0, width: 1000, height: 1000 };
    const anchor = { x: 900, y: 400 };
    expect(placeProposal(anchor, WIDE, [wall]).side).toEqual(
      placeProposal(anchor, WIDE).side,
    );
    expect(placeProposal(anchor, WIDE, [wall]).chip).toEqual(
      placeProposal(anchor, WIDE).chip,
    );
  });

  it("is unmoved by a zero-area obstruction", () => {
    // `measureChrome` already drops these, so this is a guard against the
    // placement acquiring its own opinion about degenerate rects.
    const empty = { x: 1420, y: 860, width: 0, height: 0 };
    expect(placeProposal({ x: 1420, y: 880 }, WIDE, [empty]).chip).toEqual(
      placeProposal({ x: 1420, y: 880 }, WIDE).chip,
    );
  });
});
