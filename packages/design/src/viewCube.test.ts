/**
 * The reference cube's geometry, and the ONE invariant that binds the two
 * renderers to it (VIEWCUBE-1).
 *
 * These are not "assert the constants" tests — those are worthless. Each case
 * pins a relationship that, when it broke, made a control the design mandate
 * calls table stakes unusable: the chrome's clearance was a hand-copied 140
 * beside a cube that reached 156 px, so a rail was licensed to paint into the
 * block. Numbers transcribed between files drift; a derivation cannot.
 */
import { describe, expect, it } from "vitest";

import { layout, spacing, viewCube } from "./tokens";

describe("reference cube geometry", () => {
  it("sizes its host to the ISO silhouette, not the face", () => {
    // At an isometric attitude the block presents its SPACE DIAGONAL, not its
    // face — the mistake that produced both a too-generous 120 px fit footprint
    // and a too-mean 140 px chrome clearance.
    const silhouette = viewCube.face * Math.sqrt(3);
    expect(viewCube.size).toBeGreaterThanOrEqual(silhouette);
    // …and not wastefully bigger: the surplus is stroke clearance, nothing more.
    expect(viewCube.size - silhouette).toBeLessThan(6);
  });

  it("seats the block's CENTRE on its margin from the frame corner", () => {
    // The founder's 2026-07-31 capture settled this inset; the host's seat has
    // to be derived from it rather than chosen alongside it.
    expect(viewCube.inset + viewCube.size / 2).toBe(viewCube.margin);
  });

  it("keeps chrome out of the block, with a gutter", () => {
    // THE regression guard. `referenceCubeBand` is what a right-hand rail
    // clamps to (`bottom-cube-band`) and what a floating card clamps under
    // (`max-h-cube-card`). It must clear the block's full reach — inset plus
    // size — or the chrome may paint over view navigation.
    const reach = viewCube.inset + viewCube.size;
    expect(layout.referenceCubeBand).toBeGreaterThanOrEqual(reach);
    // The same gutter every other floating card breathes on, so the cube reads
    // as part of the chrome's rhythm rather than as an exclusion zone.
    expect(layout.referenceCubeBand - reach).toBe(spacing["3"]);
  });
});
