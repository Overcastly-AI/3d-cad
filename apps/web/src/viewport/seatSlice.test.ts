import { describe, expect, it } from "vitest";

import {
  SURFACE_SEAT_FRAME_MS,
  SURFACE_SEAT_MAX_SLICE_MS,
  seatSliceMs,
} from "./useSurfaceMarkBurial";

describe("seatSliceMs — the face-mark seat pass's share of a frame", () => {
  it("is the floor at 60 fps: a third of 16.7 ms is under it", () => {
    expect(seatSliceMs(1 / 60)).toBe(SURFACE_SEAT_FRAME_MS);
  });

  it("is a third of a slow frame, so the pass keeps its share of the frame", () => {
    expect(seatSliceMs(0.3)).toBeCloseTo(100, 6);
  });

  it("is capped: the first frame after idle reports the idle time as delta", () => {
    expect(seatSliceMs(30)).toBe(SURFACE_SEAT_MAX_SLICE_MS);
  });

  it("falls back to the floor on a non-finite delta", () => {
    expect(seatSliceMs(Number.NaN)).toBe(SURFACE_SEAT_FRAME_MS);
    expect(seatSliceMs(Number.POSITIVE_INFINITY)).toBe(SURFACE_SEAT_FRAME_MS);
  });
});
