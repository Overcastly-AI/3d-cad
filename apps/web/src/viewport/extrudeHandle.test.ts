/**
 * The depth gauge's math (T-23) — the part of a drag handle a browser is not
 * required to test, and therefore the part that must not live inside the r3f
 * component.
 *
 * The e2e drags the real thing in a real browser and asserts the distance
 * changed; that proves it is WIRED. These prove it is CORRECT: that the gauge
 * stands where the profile is, that a pointer ray means the millimetres it
 * appears to mean, that the value cannot leave the range the form can submit,
 * and that a key does what a slider's key is supposed to do. A browser test
 * that only checks "the number moved" passes just as happily on a handle that
 * moves the number by the wrong amount.
 */
import { describe, expect, it } from "vitest";
import { Vector3 } from "three";

import { sceneOriginBasis } from "../sketch/plane";
import {
  arrowLength,
  clampDepth,
  depthAlongAxis,
  handleAxis,
  LADDER_MAX,
  ladderTicks,
  MAX_DEPTH_MM,
  MIN_DEPTH_MM,
  nudgeDepth,
  perspectiveMmPerPixel,
  quantizeDepth,
  screenDragDepth,
  SNAP_MM,
  tipPoint,
} from "./extrudeHandle";
import type { ProfileRegion } from "./profileLoops";

/** A 40x25 rectangle in plane (u,v) mm, its centre at (30, 20). */
const RECT: ProfileRegion[] = [
  {
    outer: [
      { x: 10, y: 7.5 },
      { x: 50, y: 7.5 },
      { x: 50, y: 32.5 },
      { x: 10, y: 32.5 },
    ],
    holes: [],
  },
];

describe("handleAxis — the gauge stands on the profile, pointing the way it sweeps", () => {
  it("seats on the profile's centre, in the plane, for an XY sketch", () => {
    const axis = handleAxis(sceneOriginBasis("XY"), "normal", RECT);
    // XY is the ground in a Y-up scene: u -> scene +X, v -> scene -Z.
    expect(axis.base.x).toBeCloseTo(30, 6);
    expect(axis.base.y).toBeCloseTo(0, 6);
    expect(axis.base.z).toBeCloseTo(-20, 6);
    // …and it pulls UP the scene, which is the way the body will grow.
    expect(axis.dir.x).toBeCloseTo(0, 6);
    expect(axis.dir.y).toBeCloseTo(1, 6);
    expect(axis.dir.z).toBeCloseTo(0, 6);
  });

  it("pulls the other way for a reverse extrude", () => {
    const axis = handleAxis(sceneOriginBasis("XY"), "reverse", RECT);
    expect(axis.dir.y).toBeCloseTo(-1, 6);
    // The seat does not move — only the sense does.
    expect(axis.base.y).toBeCloseTo(0, 6);
  });

  it("rejects a KERNEL-frame basis by disagreeing with it (FB-9's shape)", () => {
    // The negative control the ghost's own pose test carries: an un-rotated
    // basis pulls along scene +Z, at right angles to the body it belongs to.
    const kernel = handleAxis(
      { u: [1, 0, 0], v: [0, 1, 0], normal: [0, 0, 1], origin: [0, 0, 0] },
      "normal",
      RECT,
    );
    expect(kernel.dir.z).toBeCloseTo(1, 6);
  });

  it("falls back to the plane origin for an empty profile", () => {
    const axis = handleAxis(sceneOriginBasis("XY"), "normal", []);
    expect([axis.base.x, axis.base.y, axis.base.z]).toEqual([0, 0, 0]);
    expect(axis.radius).toBe(0);
  });

  it("reports the profile's half-diagonal as the gauge's own scale", () => {
    const axis = handleAxis(sceneOriginBasis("XY"), "normal", RECT);
    expect(axis.radius).toBeCloseTo(Math.hypot(40, 25) / 2, 6);
  });

  it("puts the tip `depth` mm along the pull, not somewhere `depth` mm away", () => {
    const axis = handleAxis(sceneOriginBasis("XY"), "normal", RECT);
    const tip = tipPoint(axis, 10);
    expect(tip.y).toBeCloseTo(10, 6);
    expect(tip.x).toBeCloseTo(30, 6);
  });
});

describe("depthAlongAxis — a pointer ray, in millimetres", () => {
  const axis = handleAxis(sceneOriginBasis("XY"), "normal", []);

  it("reads the height the ray crosses the axis at", () => {
    // A ray flying in along -X at height 7 crosses the axis at 7 mm.
    const t = depthAlongAxis(
      axis,
      new Vector3(50, 7, 0),
      new Vector3(-1, 0, 0),
    );
    expect(t).toBeCloseTo(7, 6);
  });

  it("still resolves a skew ray — the closest approach, not an intersection", () => {
    // Offset 12 mm out of the plane the axis lies in: the lines never meet,
    // and the answer is still 7, because that is the point of closest approach.
    const t = depthAlongAxis(
      axis,
      new Vector3(50, 7, 12),
      new Vector3(-1, 0, 0),
    );
    expect(t).toBeCloseTo(7, 6);
  });

  it("refuses when the camera looks straight down the pull axis", () => {
    // Every depth projects to the same pixel here, so any number would be
    // invented. The handle switches to the screen-space drag instead.
    expect(
      depthAlongAxis(axis, new Vector3(0, 90, 0), new Vector3(0, -1, 0)),
    ).toBeNull();
  });

  it("refuses a merely SHALLOW axis too, not only an exactly parallel one", () => {
    // 10 degrees off the line of sight: the arithmetic is fine and the feel is
    // not — one pixel of pointer would move the depth by twenty. This is the
    // pose a modeller is in immediately after saving a sketch, so refusing it
    // (and falling back) is the difference between a live handle and a dead one.
    const shallow = new Vector3(
      Math.sin((10 * Math.PI) / 180),
      -Math.cos((10 * Math.PI) / 180),
      0,
    );
    expect(depthAlongAxis(axis, new Vector3(0, 90, 0), shallow)).toBeNull();
    // 45 degrees is a real view and must still resolve.
    const usable = new Vector3(1, -1, 0).normalize();
    expect(depthAlongAxis(axis, new Vector3(0, 90, 0), usable)).not.toBeNull();
  });

  it("does not require a normalised ray direction", () => {
    const t = depthAlongAxis(
      axis,
      new Vector3(50, 7, 0),
      new Vector3(-4, 0, 0),
    );
    expect(t).toBeCloseTo(7, 6);
  });
});

describe("the fallback drag — when the axis points at the eye", () => {
  it("grows with upward travel and shrinks with downward", () => {
    // dy is `grabY - clientY`, so positive means the pointer went UP.
    expect(screenDragDepth(10, 40, 0.25)).toBeCloseTo(20, 9);
    expect(screenDragDepth(10, -40, 0.25)).toBeCloseTo(0, 9);
  });

  it("moves the model at the pointer's own rate, at any zoom", () => {
    // 40 deg fov, 100 mm away, 1000 px tall: the frame spans 2*tan(20)*100 mm.
    const near = perspectiveMmPerPixel(40, 100, 1000);
    expect(near).toBeCloseTo(
      (2 * Math.tan((20 * Math.PI) / 180) * 100) / 1000,
      12,
    );
    // Twice as far away, twice the millimetres per pixel — which is what makes
    // the gesture feel identical whether you are zoomed in or out.
    expect(perspectiveMmPerPixel(40, 200, 1000)).toBeCloseTo(near * 2, 12);
  });

  it("refuses to divide by a zero-height viewport", () => {
    expect(perspectiveMmPerPixel(40, 100, 0)).toBe(0);
  });
});

describe("quantizeDepth — snapped by default, exact on demand", () => {
  it("snaps a millimetre document to the half-millimetre", () => {
    expect(quantizeDepth(12.34, "mm", false)).toBe(12.5);
    expect(quantizeDepth(12.2, "mm", false)).toBe(12);
  });

  it("hands the exact value back when Ctrl/Cmd suppresses the snap", () => {
    expect(quantizeDepth(12.34, "mm", true)).toBe(12.34);
  });

  it("snaps an INCH document to 1/32 in, not to a metric step", () => {
    // A snap the user cannot name is not a snap. 1 in = 25.4 mm exactly.
    const step = SNAP_MM["in"];
    expect(step).toBeCloseTo(25.4 / 32, 12);
    const snapped = quantizeDepth(25.4 + 0.4, "in", false);
    // An exact multiple of 1/32 in — which a blanket round to 4 decimal
    // millimetres would silently destroy (0.79375 is five decimals).
    expect(snapped / step).toBeCloseTo(Math.round(snapped / step), 9);
    // 25.8 mm is 32.504 thirty-seconds; the nearest grid line is 33 of them.
    expect(snapped).toBeCloseTo(33 * step, 9);
  });

  it("never leaves the range the form can submit", () => {
    // A drag past the plane parks at the floor rather than going invalid —
    // `parseDistanceMm` rejects 0, so a 0 here would be a dead end.
    expect(quantizeDepth(-40, "mm", true)).toBe(MIN_DEPTH_MM);
    expect(quantizeDepth(1e9, "mm", true)).toBe(MAX_DEPTH_MM);
    expect(clampDepth(0)).toBe(MIN_DEPTH_MM);
  });

  it("does not write float noise into a field a human is about to read", () => {
    expect(quantizeDepth(0.1 + 0.2, "mm", true)).toBe(0.3);
  });
});

describe("nudgeDepth — the slider's keyboard, and only its keys", () => {
  it("grows on Up/Right and shrinks on Down/Left, one snap step", () => {
    expect(nudgeDepth(10, "ArrowUp", "mm", false)).toBe(10.5);
    expect(nudgeDepth(10, "ArrowRight", "mm", false)).toBe(10.5);
    expect(nudgeDepth(10, "ArrowDown", "mm", false)).toBe(9.5);
    expect(nudgeDepth(10, "ArrowLeft", "mm", false)).toBe(9.5);
  });

  it("takes ten steps with Shift and with the Page keys", () => {
    expect(nudgeDepth(10, "ArrowUp", "mm", true)).toBe(15);
    expect(nudgeDepth(10, "PageUp", "mm", false)).toBe(15);
    expect(nudgeDepth(10, "PageDown", "mm", false)).toBe(5);
  });

  it("steps in the DOCUMENT's unit", () => {
    expect(nudgeDepth(25.4, "ArrowUp", "in", false)).toBeCloseTo(
      25.4 + 25.4 / 32,
      9,
    );
  });

  it("clamps at the floor instead of walking into an invalid form", () => {
    expect(nudgeDepth(0.2, "ArrowDown", "mm", false)).toBe(MIN_DEPTH_MM);
  });

  it("returns null for a key that is not ours, so the app still sees it", () => {
    // Enter must reach the editor's submit, Escape its cancel: a slider that
    // swallowed them would make the handle a dead end.
    for (const key of ["Enter", "Escape", "Tab", "a"]) {
      expect(nudgeDepth(10, key, "mm", false)).toBeNull();
    }
  });
});

describe("ladderTicks — the signature graduation", () => {
  it("never draws more than the ceiling, at any scale", () => {
    for (const depth of [0.4, 3, 10, 12, 12.1, 60.5, 300, 4000]) {
      expect(ladderTicks(depth).length).toBeLessThanOrEqual(LADDER_MAX);
    }
  });

  it("keeps a readable ladder at every scale — five or more, five decades", () => {
    // The floor is a PROPERTY of the 1/2/5 rule, so it is measured here rather
    // than asserted by a constant that would agree with itself. Five is the
    // worst case and it is real: a 12.1 mm sweep steps by 2 (a 1 mm step would
    // overrun the ceiling), which leaves rungs at 2/4/6/8/10.
    for (const depth of [0.4, 3, 10, 12.1, 60.5, 300, 4000, 9000]) {
      expect(ladderTicks(depth).length).toBeGreaterThanOrEqual(5);
    }
  });

  it("steps by a number a person would say out loud", () => {
    const step = (depth: number): number => {
      const ticks = ladderTicks(depth);
      return ticks[0] as number;
    };
    expect(step(10)).toBeCloseTo(1, 9);
    expect(step(3)).toBeCloseTo(0.5, 9);
    expect(step(300)).toBeCloseTo(50, 9);
    expect(step(4000)).toBeCloseTo(500, 9);
  });

  it("draws neither the base nor a rung under the grip", () => {
    const ticks = ladderTicks(10);
    expect(ticks[0]).toBeGreaterThan(0);
    expect(ticks[ticks.length - 1]).toBeLessThan(10);
  });

  it("has nothing to draw for a zero or negative depth", () => {
    expect(ladderTicks(0)).toEqual([]);
    expect(ladderTicks(-5)).toEqual([]);
  });
});

describe("arrowLength — sized from the profile, never from the depth", () => {
  it("scales with the profile so the arrow suits the part", () => {
    expect(arrowLength(50)).toBeGreaterThan(arrowLength(10));
  });

  it("stays grabbable on a tiny profile and sane on a huge one", () => {
    expect(arrowLength(0)).toBeGreaterThanOrEqual(2);
    expect(arrowLength(5000)).toBeLessThanOrEqual(18);
  });
});
