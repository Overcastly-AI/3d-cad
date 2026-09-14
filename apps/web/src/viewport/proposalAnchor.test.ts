import { proposal } from "@loft/design";
import { beforeEach, describe, expect, it } from "vitest";

import {
  loopAnchor,
  useProposalAnchorStore,
  type ProposalAnchor,
} from "./proposalAnchor";

const FRAME = { width: 1280, height: 800 };

/** A rectangle, counter-clockwise, in screen px. */
function rect(x: number, y: number, w: number, h: number) {
  return [
    { x, y },
    { x: x + w, y },
    { x: x + w, y: y + h },
    { x, y: y + h },
  ];
}

describe("loopAnchor", () => {
  it("puts the anchor at the area centroid, not the bounding-box middle", () => {
    // An L-shape: a 100x100 square with its top-right 50x50 quadrant removed.
    // The vertex mean and the bbox centre both land at (50, 50); the AREA
    // centroid — the point a leader should run from — is pulled down-left.
    const l = [
      { x: 0, y: 0 },
      { x: 50, y: 0 },
      { x: 50, y: 50 },
      { x: 100, y: 50 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ].map((p) => ({ x: p.x + 200, y: p.y + 200 }));
    const anchor = loopAnchor(l, FRAME);
    expect(anchor).not.toBeNull();
    // Exact: three 50x50 cells at (25,25), (25,75), (75,75) → (41.67, 58.33).
    expect(anchor?.x).toBeCloseTo(200 + 125 / 3, 6);
    expect(anchor?.y).toBeCloseTo(200 + 175 / 3, 6);
  });

  it("is winding-independent — a clockwise loop anchors in the same place", () => {
    const ccw = rect(100, 100, 200, 120);
    const cw = [...ccw].reverse();
    expect(loopAnchor(cw, FRAME)).toEqual(loopAnchor(ccw, FRAME));
  });

  it("refuses a loop shorter than the chip it would carry", () => {
    // A profile seen almost edge-on. A note here would be a chip taller than
    // the thing it annotates, with a leader pointing at a hairline.
    const sliver = rect(600, 400, 300, proposal.chipHeight - 1);
    expect(loopAnchor(sliver, FRAME)).toBeNull();
    // One pixel taller and it is a thing worth annotating.
    const honest = rect(600, 400, 300, proposal.chipHeight);
    expect(loopAnchor(honest, FRAME)).not.toBeNull();
  });

  it("refuses an anchor outside the frame's keep-out", () => {
    // The profile is on screen; its CENTROID is not. `placeProposal` can flip
    // and clamp the chip, but nothing can bring the anchor dot back — the
    // leader would run off the edge and stop.
    const offLeft = [
      { x: -400, y: 300 },
      { x: 60, y: 300 },
      { x: 60, y: 500 },
      { x: -400, y: 500 },
    ];
    expect(loopAnchor(offLeft, FRAME)).toBeNull();
    const offBottom = [
      { x: 400, y: FRAME.height - 40 },
      { x: 700, y: FRAME.height - 40 },
      { x: 700, y: FRAME.height + 400 },
      { x: 400, y: FRAME.height + 400 },
    ];
    expect(loopAnchor(offBottom, FRAME)).toBeNull();
  });

  it("keeps the anchor clear of the frame edge by the chip's own keep-out", () => {
    const anchor = loopAnchor(rect(0, 0, 200, 200), FRAME);
    expect(anchor).not.toBeNull();
    expect(anchor?.x).toBeGreaterThanOrEqual(proposal.margin);
    expect(anchor?.y).toBeGreaterThanOrEqual(proposal.margin);
  });

  it("refuses anything that is not a loop", () => {
    expect(loopAnchor([], FRAME)).toBeNull();
    expect(loopAnchor([{ x: 10, y: 10 }], FRAME)).toBeNull();
    expect(
      loopAnchor(
        [
          { x: 10, y: 10 },
          { x: 200, y: 400 },
        ],
        FRAME,
      ),
    ).toBeNull();
  });

  it("refuses a non-finite point rather than publishing NaN", () => {
    // A vertex behind a perspective camera projects to infinity; one of them
    // poisons the centroid, and `left: NaN` is a chip nobody can see or hit.
    const poisoned = rect(400, 300, 200, 200);
    poisoned[2] = { x: Number.POSITIVE_INFINITY, y: 500 };
    expect(loopAnchor(poisoned, FRAME)).toBeNull();
    const nan = rect(400, 300, 200, 200);
    nan[1] = { x: 600, y: Number.NaN };
    expect(loopAnchor(nan, FRAME)).toBeNull();
  });

  it("falls back to the vertex mean when the loop encloses no area", () => {
    // A fold-back: out and straight back again. The shoelace centroid is 0/0,
    // and the height gate has already let it through because it is tall.
    const foldback = [
      { x: 400, y: 200 },
      { x: 400, y: 500 },
      { x: 400, y: 200 },
    ];
    expect(loopAnchor(foldback, FRAME)).toEqual({ x: 400, y: 300 });
  });
});

describe("the anchor channel", () => {
  const anchor: ProposalAnchor = { x: 10, y: 20, frame: FRAME };

  beforeEach(() => {
    useProposalAnchorStore.setState({ subject: null, anchor: null });
  });

  it("drops the old anchor when the subject changes", () => {
    const store = useProposalAnchorStore.getState();
    store.requestAnchor("sketch-1");
    store.publishAnchor(anchor);
    expect(useProposalAnchorStore.getState().anchor).toEqual(anchor);
    // The point belonged to Sketch1. Keeping it would place Sketch2's note, for
    // one frame, exactly where the last one was — a leader naming the wrong
    // sketch, which is worse than a note that arrives a frame late.
    useProposalAnchorStore.getState().requestAnchor("sketch-2");
    expect(useProposalAnchorStore.getState().anchor).toBeNull();
  });

  it("keeps the anchor while the subject is unchanged", () => {
    const store = useProposalAnchorStore.getState();
    store.requestAnchor("sketch-1");
    store.publishAnchor(anchor);
    store.requestAnchor("sketch-1");
    expect(useProposalAnchorStore.getState().anchor).toEqual(anchor);
  });

  it("clears the anchor when nothing is wanted", () => {
    const store = useProposalAnchorStore.getState();
    store.requestAnchor("sketch-1");
    store.publishAnchor(anchor);
    store.requestAnchor(null);
    expect(useProposalAnchorStore.getState().anchor).toBeNull();
    expect(useProposalAnchorStore.getState().subject).toBeNull();
  });
});
