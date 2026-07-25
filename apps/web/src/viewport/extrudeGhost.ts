/**
 * The extrude ghost's APPEARANCE, as a pure function of the operation — the
 * seam below {@link ExtrudePreview}'s r3f renderer.
 *
 * FINDINGS burn-down 2026-07-25 #5: `ExtrudePreviewState.operation` was a dead
 * field. The live ghost painted a solid standing proud of the plate for a CUT —
 * the visual OPPOSITE of what Save produced — and nothing below a full browser
 * e2e could see it, because the decision lived inside a `useMemo` in a
 * WebGL-only component. Lifting it here makes "a cut never reads as added
 * metal" an assertion a node unit test can make.
 *
 * The read: an ADD is warm, bright metal about to exist. A CUT is a VOID — only
 * the cavity's BACK walls are drawn (`BackSide`, so you look INTO the pocket
 * rather than at a body's near face) and they are shaded cold and dark, because
 * a hole in aluminium is a shadow, not a highlight. Every value is a
 * `@loft/design` token; no hex literal lives in the viewport.
 */
import { viewport } from "@loft/design/tokens";
import { BackSide, FrontSide, type Side } from "three";

import type { ExtrudeOperation } from "../features/extrude";

export interface ExtrudeGhostAppearance {
  /** Swept-surface tint. */
  surfaceTint: string;
  surfaceOpacity: number;
  /**
   * Which faces of the swept volume are drawn. `FrontSide` for an ADD (a
   * solid); `BackSide` for a CUT (the far walls of the cavity only).
   */
  surfaceSide: Side;
  /** Wireframe ink over the sweep. */
  edgeColor: string;
  edgeOpacity: number;
}

/** How the ghost of `operation` is shaded. */
export function extrudeGhostAppearance(
  operation: ExtrudeOperation,
): ExtrudeGhostAppearance {
  if (operation === "cut") {
    return {
      surfaceTint: viewport.preview.cut.wallTint,
      surfaceOpacity: viewport.preview.cut.wallOpacity,
      surfaceSide: BackSide,
      edgeColor: viewport.preview.cut.edge,
      edgeOpacity: viewport.preview.cut.edgeOpacity,
    };
  }
  return {
    surfaceTint: viewport.preview.surfaceTint,
    surfaceOpacity: viewport.preview.surfaceOpacity,
    surfaceSide: FrontSide,
    edgeColor: viewport.preview.edge,
    edgeOpacity: viewport.preview.edgeOpacity,
  };
}
