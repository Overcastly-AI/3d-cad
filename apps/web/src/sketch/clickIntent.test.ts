import { describe, expect, it } from "vitest";

import { CLICK_SLOP_PX, DRIFT_SLOP_PX, isClick } from "./clickIntent";

describe("isClick", () => {
  it("accepts a still click", () => {
    expect(isClick({ travelPx: 0, durationMs: 90 })).toBe(true);
  });

  it("accepts the trackpad drift the old 4 px rule discarded", () => {
    // The exact travels the QA pass measured DEAD before FB-12.
    for (const travelPx of [5, 6, 8, 10]) {
      expect(isClick({ travelPx, durationMs: 120 })).toBe(true);
    }
  });

  it("accepts travel up to the plain slop at any speed", () => {
    expect(isClick({ travelPx: CLICK_SLOP_PX, durationMs: 1 })).toBe(true);
  });

  it("accepts a SLOW wobble past the plain slop", () => {
    // 20 px over a 200 ms press — 0.1 px/ms, a shaky hand.
    expect(isClick({ travelPx: 20, durationMs: 200 })).toBe(true);
  });

  it("rejects a FAST flick of the same distance", () => {
    // The same 20 px in 30 ms — 0.67 px/ms, a deliberate nudge-pan.
    expect(isClick({ travelPx: 20, durationMs: 30 })).toBe(false);
  });

  it("rejects a real pan however slow it was", () => {
    expect(isClick({ travelPx: 200, durationMs: 4000 })).toBe(false);
    expect(isClick({ travelPx: DRIFT_SLOP_PX + 1, durationMs: 5000 })).toBe(
      false,
    );
  });

  it("falls back to distance when no timing was recorded", () => {
    expect(isClick({ travelPx: 8, durationMs: null })).toBe(true);
    expect(isClick({ travelPx: 20, durationMs: null })).toBe(false);
  });
});
