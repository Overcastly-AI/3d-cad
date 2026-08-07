/**
 * The extrude ghost must never contradict what Save will do.
 *
 * This asserts the seam BELOW the r3f renderer: `ExtrudePreview` itself is a
 * WebGL component that jsdom cannot render (there is no GL context, and mocking
 * the GPU stack would test the mock), so the decision the defect actually got
 * wrong — how an operation is shaded — was lifted into the pure
 * {@link extrudeGhostAppearance}. What is left in the component is
 * `new MeshMatcapMaterial(...)` assignment from these values.
 *
 * The regression being locked out (FINDINGS burn-down 2026-07-25 #5): the
 * preview ignored `operation: "cut"` entirely and painted a solid standing
 * proud of the plate — the visual opposite of the pocket Save produced.
 */
import { BackSide, FrontSide, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import {
  faceBasis,
  originBasis,
  sceneOriginBasis,
  type PlanarFaceSignature,
} from "../sketch/plane";
import {
  extrudeGhostAppearance,
  extrudeGhostPose,
  type ExtrudeGhostPose,
} from "./extrudeGhost";

/** Relative luminance of a `#rrggbb` token — "is this ink dark or bright?". */
function luminance(hex: string): number {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

describe("extrudeGhostAppearance", () => {
  it("is operation-sensitive at all — a cut is never shaded like an add", () => {
    // The dead-field bug in one assertion: if `operation` stops reaching the
    // shading, these two collapse into the same object and this fails.
    expect(extrudeGhostAppearance("cut")).not.toEqual(
      extrudeGhostAppearance("add"),
    );
  });

  it("draws a cut as a cavity — back walls only, never a proud solid", () => {
    const cut = extrudeGhostAppearance("cut");
    expect(cut.surfaceSide).toBe(BackSide);
    // An added solid shows its NEAR faces; a void must not.
    expect(cut.surfaceSide).not.toBe(extrudeGhostAppearance("add").surfaceSide);
  });

  it("draws an add as a solid — front faces of metal about to exist", () => {
    expect(extrudeGhostAppearance("add").surfaceSide).toBe(FrontSide);
  });

  it("shades a cut cold and dark and an add warm and bright", () => {
    // A hole in aluminium is a shadow, not a highlight: the cut wall tint must
    // read materially darker than the add tint, or the two states look alike.
    const cut = luminance(extrudeGhostAppearance("cut").surfaceTint);
    const add = luminance(extrudeGhostAppearance("add").surfaceTint);
    expect(cut).toBeLessThan(add - 0.25);
  });

  it("keeps both ghosts translucent — a preview is never committed metal", () => {
    for (const operation of ["add", "cut"] as const) {
      const a = extrudeGhostAppearance(operation);
      expect(a.surfaceOpacity).toBeGreaterThan(0);
      expect(a.surfaceOpacity).toBeLessThan(1);
      expect(a.edgeOpacity).toBeGreaterThan(0);
      expect(a.edgeOpacity).toBeLessThanOrEqual(1);
    }
  });

  it("inks the void silhouette differently from the add silhouette", () => {
    expect(extrudeGhostAppearance("cut").edgeColor).not.toBe(
      extrudeGhostAppearance("add").edgeColor,
    );
  });

  it("sources every colour from a design token, never a literal", () => {
    for (const operation of ["add", "cut"] as const) {
      const a = extrudeGhostAppearance(operation);
      expect(a.surfaceTint).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(a.edgeColor).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });
});

/** Where a point of the ghost's own space (profile x/y, sweep z) lands. */
function place(
  pose: ExtrudeGhostPose,
  local: [number, number, number],
): [number, number, number] {
  const p = new Vector3(...local)
    .applyQuaternion(pose.quaternion)
    .add(pose.position);
  const round = (v: number): number => Math.round(v * 1e6) / 1e6 + 0;
  return [round(p.x), round(p.y), round(p.z)];
}

describe("extrudeGhostPose — the ghost sits ON the plane it was drawn on", () => {
  /**
   * FB-7c / FB-9. `ExtrudeGeometry` builds the profile in local XY and sweeps
   * toward local +Z, so the pose has one job: put local +Z on the plane NORMAL,
   * in the frame the body renders in. It was fed a basis stated in the kernel's
   * Z-up frame while the scene is Y-up, so re-opening an unmodified 10 mm
   * extrude on XY drew the ghost lying through the ground grid — 152 px below
   * the body it was meant to coincide with, and into the bottom view rail.
   */
  it("sweeps an XY extrude UP the scene, the way the body grows", () => {
    const pose = extrudeGhostPose(sceneOriginBasis("XY"));
    // 10 mm of sweep = 10 mm of scene height. This is the assertion that fails
    // on the old behaviour: the kernel-frame basis sent it to [0, 0, 10].
    expect(place(pose, [0, 0, 10])).toEqual([0, 10, 0]);
    // …and the profile still lies IN the ground plane (scene y = 0).
    expect(place(pose, [7, -3, 0])).toEqual([7, 0, 3]);
  });

  it("rejects a kernel-frame basis by disagreeing with it", () => {
    // The negative control: same plane, un-rotated basis, 90° of error.
    expect(place(extrudeGhostPose(originBasis("XY")), [0, 0, 10])).toEqual([
      0, 0, 10,
    ]);
  });

  it("agrees with a sketch on the same face, resolved the other way", () => {
    // A sketch on a box's top face at z=10 and a sketch on XY+10 are the same
    // plane. `faceBasis` was already scene-frame, so this pair is what the
    // origin-datum path now has to match.
    const face: PlanarFaceSignature = {
      normal: { x: 0, y: 0, z: 1 },
      centroid: { x: 0, y: 0, z: 10 },
      area_mm2: 100,
      subshape_type: "face",
      surface: "plane",
    };
    const onFace = extrudeGhostPose(faceBasis(face, 0));
    expect(place(onFace, [0, 0, 5])).toEqual([0, 15, 0]);
  });

  it("places the ghost at the plane's own origin", () => {
    const pose = extrudeGhostPose(sceneOriginBasis("YZ"));
    expect(place(pose, [0, 0, 0])).toEqual([0, 0, 0]);
  });
});
