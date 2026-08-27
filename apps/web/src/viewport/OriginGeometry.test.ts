import { describe, expect, it } from "vitest";

import {
  occtToSceneTuple,
  sceneOriginBasis,
  type Vec3Tuple,
} from "../sketch/plane";
import { VIEW_DIRECTIONS } from "./viewCommands";
import { AXIS_DIRECTION } from "./OriginGeometry";

/**
 * FB-21 — the origin axis glyphs were LABELLED in kernel space and DRAWN in
 * scene space, which the GLB rotation has already turned.
 *
 * These are relationship tests, not constant transcriptions. The defect was
 * exactly a transcription: `Z: [0, 0, 1]`, written beside a comment asserting
 * the two frames coincide, next to sheets built from `sceneOriginBasis` — which
 * is rotated. Asserting the triple would have agreed with the bug. So each case
 * below derives the expected direction from something the PRODUCT already uses
 * for the same purpose, and fails if the two ever disagree again.
 */
describe("origin axis glyphs point where the part does", () => {
  it("draws the Z glyph along the extrude direction of an XY sketch", () => {
    // The acceptance criterion, stated as the product states it: a sketch on XY
    // extrudes along that plane's normal, and `sceneOriginBasis` is the basis
    // every renderer of that plane (sheet, ink, extrude ghost) is built from.
    const extrudeDirection: Vec3Tuple = sceneOriginBasis("XY").normal;
    expect(AXIS_DIRECTION.Z).toEqual(extrudeDirection);
  });

  it("agrees with the ViewCube's TOP, because they are the same vector", () => {
    // The founder's own test: "turn on the axis and compare them to the view
    // cube." TOP looks down scene −Y from scene +Y, so a correct Z glyph points
    // at the camera in that view. Under the defect this was scene +Z — the
    // cube's FRONT — so the glyph read Z while pointing at the front face.
    expect(AXIS_DIRECTION.Z).toEqual([...VIEW_DIRECTIONS.top]);
  });

  it("carries each kernel axis through the ONE rotation, not a second table", () => {
    expect(AXIS_DIRECTION.X).toEqual(occtToSceneTuple([1, 0, 0]));
    expect(AXIS_DIRECTION.Y).toEqual(occtToSceneTuple([0, 1, 0]));
    expect(AXIS_DIRECTION.Z).toEqual(occtToSceneTuple([0, 0, 1]));
  });

  it("keeps the triad orthonormal and right-handed", () => {
    // A rotation cannot change handedness, so this is what catches a "fix" that
    // repairs one glyph by negating another — the blind label-swap the ticket
    // explicitly warned against.
    const [x, y, z] = [AXIS_DIRECTION.X, AXIS_DIRECTION.Y, AXIS_DIRECTION.Z];
    const dot = (a: Vec3Tuple, b: Vec3Tuple) =>
      a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const cross = (a: Vec3Tuple, b: Vec3Tuple): Vec3Tuple => [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0],
    ];
    for (const axis of [x, y, z]) expect(dot(axis, axis)).toBeCloseTo(1, 12);
    expect(dot(x, y)).toBeCloseTo(0, 12);
    expect(dot(y, z)).toBeCloseTo(0, 12);
    expect(dot(z, x)).toBeCloseTo(0, 12);
    // x cross y = z: right-handed in the scene frame, as it is in the kernel's.
    const xy = cross(x, y);
    expect(xy[0]).toBeCloseTo(z[0], 12);
    expect(xy[1]).toBeCloseTo(z[1], 12);
    expect(xy[2]).toBeCloseTo(z[2], 12);
  });

  it("does not point Z where the kernel's -Y lives (the shipped defect)", () => {
    // The negative control, naming the exact wrong answer so a regression to it
    // fails by name rather than by an inscrutable tuple mismatch.
    expect(AXIS_DIRECTION.Z).not.toEqual([0, 0, 1]);
    expect(AXIS_DIRECTION.Y).not.toEqual([0, 1, 0]);
  });
});
