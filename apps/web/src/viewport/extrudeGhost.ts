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
import {
  BackSide,
  FrontSide,
  Matrix4,
  Quaternion,
  Vector3,
  type Side,
} from "three";

import type { ExtrudeOperation } from "../features/extrude";
import type { PlaneBasis } from "../sketch/plane";

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

/** Where the ghost group sits and how it is turned, for a sketch `basis`. */
export interface ExtrudeGhostPose {
  position: Vector3;
  quaternion: Quaternion;
}

/**
 * Orient the ghost's own space onto the sketch plane: `ExtrudeGeometry` builds
 * the profile in local XY and sweeps toward local +Z, so local X→u, Y→v, Z→the
 * plane NORMAL, placed at the plane origin.
 *
 * The APPEARANCE seam above exists because a decision buried in a `useMemo`
 * inside a WebGL-only component is invisible below a full browser run. This is
 * the same lesson applied to PLACEMENT, and it was needed for the same reason:
 * the ghost was drawn from a basis stated in the KERNEL's Z-up frame while the
 * body renders in the scene's Y-up frame, so re-opening an unmodified 10 mm
 * extrude on XY drew its ghost lying through the ground grid and 152 px below
 * the body it was supposed to coincide with (FB-7c / FB-9). Measured, not
 * inferred: body at scene y∈[0,10] z∈[−15.4,16.6], ghost at y∈[−16.6,15.4]
 * z∈[0,10] — the same solid, minus the frame rotation.
 *
 * Hand it a SCENE-frame basis (`sceneOriginBasis` / `resolveSpecBasis` /
 * `faceBasis`); pass a kernel-frame one and the ghost is wrong by 90°, which is
 * exactly what `extrudeGhost.test.ts` now pins.
 */
export function extrudeGhostPose(basis: PlaneBasis): ExtrudeGhostPose {
  const { u, v, normal, origin } = basis;
  const matrix = new Matrix4().makeBasis(
    new Vector3(...u),
    new Vector3(...v),
    new Vector3(...normal),
  );
  return {
    position: new Vector3(...origin),
    quaternion: new Quaternion().setFromRotationMatrix(matrix),
  };
}
