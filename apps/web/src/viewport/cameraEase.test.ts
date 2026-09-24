import { describe, expect, it } from "vitest";

import {
  CAMERA_EASE_FIRST_STEP_S,
  CAMERA_EASE_RATE,
  cameraEaseStep,
} from "./cameraEase";

/** Frames an ease needs to close `distance` mm to the rigs' 0.05 mm landing. */
function framesToLand(distance: number, frameSeconds: number): number {
  let left = distance;
  let frames = 0;
  let continuing = false;
  while (left >= 0.05 && frames < 10_000) {
    left *= 1 - cameraEaseStep(frameSeconds, continuing);
    continuing = true;
    frames += 1;
  }
  return frames;
}

describe("cameraEaseStep", () => {
  it("is unchanged at an interactive frame rate — no clamp is reached", () => {
    const dt = 1 / 60;
    const legacy = 1 - Math.exp(-Math.min(dt, 0.1) * 10);
    expect(cameraEaseStep(dt, false)).toBe(legacy);
    expect(cameraEaseStep(dt, true)).toBe(legacy);
  });

  it("keeps the FIRST frame clamped — its delta is idle time, not a frame", () => {
    // Ten idle seconds must not snap the camera to its goal in one frame.
    expect(cameraEaseStep(10, false)).toBe(
      1 - Math.exp(-CAMERA_EASE_FIRST_STEP_S * CAMERA_EASE_RATE),
    );
    expect(cameraEaseStep(10, false)).toBeLessThan(0.7);
  });

  it("stays time-based on a slow machine: a 2.4 s frame lands in a handful", () => {
    // The gauntlet's gearbox under software GL: ~2.4 s a frame, and the
    // plane-pick vantage ~2 000 mm away. The legacy clamp needed ~11 frames
    // (~26 s) for this; the rule is that the ease takes the same WALL time at
    // any frame rate down to 2 fps, so it lands in very few frames.
    expect(framesToLand(2000, 2.4)).toBeLessThanOrEqual(4);
  });

  it("NEGATIVE CONTROL: the legacy every-frame clamp needs ~11 frames there", () => {
    let left = 2000;
    let frames = 0;
    while (left >= 0.05) {
      left *= Math.exp(-Math.min(2.4, 0.1) * 10);
      frames += 1;
    }
    expect(frames).toBeGreaterThanOrEqual(10);
  });

  it("never steps backward or past the goal", () => {
    for (const dt of [0, 1e-6, 1 / 120, 0.1, 0.5, 3, 1e6]) {
      for (const continuing of [false, true]) {
        const k = cameraEaseStep(dt, continuing);
        expect(k).toBeGreaterThanOrEqual(0);
        expect(k).toBeLessThan(1);
      }
    }
    expect(cameraEaseStep(-1, true)).toBe(0);
  });
});
