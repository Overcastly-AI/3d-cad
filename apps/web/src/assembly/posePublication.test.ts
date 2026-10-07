import { describe, expect, it } from "vitest";

import type { SceneTransform } from "./placement";
import {
  NO_DRAWN_POSES,
  poseKey,
  posesPending,
  recordDrawnPose,
} from "./posePublication";

const seat = (y: number): SceneTransform => ({
  position: [12.5, y, -5],
  quaternion: [0, 0, 0, 1],
});

describe("posesPending — the viewport has not drawn the pose this page renders", () => {
  it("is pending while a balloon still shows the PRE-mate seat", () => {
    // The measured frame: the page holds the mated pose (y=10), the balloon's
    // root has not committed yet and still carries y=0.
    const drawn = recordDrawnPose(NO_DRAWN_POSES, "b", poseKey(seat(0)));
    expect(posesPending([{ id: "b", transform: seat(10) }], drawn)).toBe(true);
  });

  it("clears once the balloon acknowledges the pose", () => {
    let drawn = recordDrawnPose(NO_DRAWN_POSES, "b", poseKey(seat(0)));
    drawn = recordDrawnPose(drawn, "b", poseKey(seat(10)));
    expect(posesPending([{ id: "b", transform: seat(10) }], drawn)).toBe(false);
  });

  it("tells a rotation apart from the same position", () => {
    const turned: SceneTransform = {
      position: [12.5, 0, -5],
      quaternion: [0, Math.SQRT1_2, 0, Math.SQRT1_2],
    };
    const drawn = recordDrawnPose(NO_DRAWN_POSES, "b", poseKey(seat(0)));
    expect(posesPending([{ id: "b", transform: turned }], drawn)).toBe(true);
  });

  it("is never pending for an instance with no balloon on screen", () => {
    // Hidden, not yet mounted, or no WebGL: no pose is shown, so none can be
    // contradicted — and the verdict must not wait forever on a receipt that
    // will never come.
    expect(
      posesPending([{ id: "b", transform: seat(10) }], NO_DRAWN_POSES),
    ).toBe(false);
    let drawn = recordDrawnPose(NO_DRAWN_POSES, "b", poseKey(seat(0)));
    drawn = recordDrawnPose(drawn, "b", null);
    expect(posesPending([{ id: "b", transform: seat(10) }], drawn)).toBe(false);
  });
});

describe("recordDrawnPose", () => {
  it("returns the same map when nothing changed, so React can bail out", () => {
    const drawn = recordDrawnPose(NO_DRAWN_POSES, "b", poseKey(seat(0)));
    expect(recordDrawnPose(drawn, "b", poseKey(seat(0)))).toBe(drawn);
    expect(recordDrawnPose(drawn, "absent", null)).toBe(drawn);
  });

  it("never mutates the map it was given", () => {
    const drawn = recordDrawnPose(NO_DRAWN_POSES, "b", poseKey(seat(0)));
    recordDrawnPose(drawn, "b", poseKey(seat(10)));
    recordDrawnPose(drawn, "b", null);
    expect(drawn.get("b")).toBe(poseKey(seat(0)));
    expect(NO_DRAWN_POSES.size).toBe(0);
  });
});
