import { describe, expect, it } from "vitest";

import { cameraEaseStep, CAMERA_EASE_FIRST_STEP_S } from "./cameraEase";
import { measuredFrameSeconds } from "./frameDelta";
import {
  SURFACE_SEAT_FRAME_MS,
  SURFACE_SEAT_MAX_SLICE_MS,
  seatSliceMs,
} from "./useSurfaceMarkBurial";

describe("measuredFrameSeconds — when r3f's delta is a frame time", () => {
  it("is null on the first frame of a run: its delta is the idle span", () => {
    expect(measuredFrameSeconds(1.2, false)).toBeNull();
  });

  it("is the delta on a continuing frame", () => {
    expect(measuredFrameSeconds(0.25, true)).toBe(0.25);
  });

  it("is null for a delta that is not a duration", () => {
    expect(measuredFrameSeconds(Number.NaN, true)).toBeNull();
    expect(measuredFrameSeconds(Number.POSITIVE_INFINITY, true)).toBeNull();
    expect(measuredFrameSeconds(-1, true)).toBeNull();
  });
});

describe("seatSliceMs — the face-mark seat pass's share of a frame", () => {
  it("THE FIRST FRAME AFTER IDLE gets the floor, not a slice of the idle span", () => {
    // The review finding: at 60 fps an orbit that starts after ~1 s of idle
    // arrives with delta = 1 s, and the pass took the 250 ms ceiling — a
    // visible hitch, spent on seats the next orbit frame throws away.
    expect(seatSliceMs(1.0, false)).toBe(SURFACE_SEAT_FRAME_MS);
    expect(seatSliceMs(30, false)).toBe(SURFACE_SEAT_FRAME_MS);
  });

  it("is the floor on a continuing 60 fps frame: a third of 16.7 ms is under it", () => {
    expect(seatSliceMs(1 / 60, true)).toBe(SURFACE_SEAT_FRAME_MS);
  });

  it("is a third of a slow continuing frame, so the pass keeps its share", () => {
    expect(seatSliceMs(0.3, true)).toBeCloseTo(100, 6);
  });

  it("is capped on a continuing frame that is merely very slow", () => {
    expect(seatSliceMs(30, true)).toBe(SURFACE_SEAT_MAX_SLICE_MS);
  });

  it("falls back to the floor on a non-finite delta", () => {
    expect(seatSliceMs(Number.NaN, true)).toBe(SURFACE_SEAT_FRAME_MS);
    expect(seatSliceMs(Number.POSITIVE_INFINITY, true)).toBe(
      SURFACE_SEAT_FRAME_MS,
    );
  });
});

describe("one first-frame rule for both budgets", () => {
  it("the camera ease and the seat slice agree on which frame is 'first'", () => {
    // An idle-length delta: the ease clamps it, the slice ignores it. A
    // continuing one: both treat it as a real frame time.
    const idle = 1.0;
    expect(cameraEaseStep(idle, false)).toBe(
      1 - Math.exp(-CAMERA_EASE_FIRST_STEP_S * 10),
    );
    expect(seatSliceMs(idle, false)).toBe(SURFACE_SEAT_FRAME_MS);
    expect(cameraEaseStep(0.3, true)).toBe(1 - Math.exp(-0.3 * 10));
    expect(seatSliceMs(0.3, true)).toBeCloseTo(100, 6);
  });
});
