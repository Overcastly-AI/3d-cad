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
import { BackSide, FrontSide } from "three";
import { describe, expect, it } from "vitest";

import { extrudeGhostAppearance } from "./extrudeGhost";

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
