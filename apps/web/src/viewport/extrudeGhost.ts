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

import type { Vec3 } from "@loft/design";

import type { ExtrudeDirection, ExtrudeOperation } from "../features/extrude";
import { planeToWorld, type PlaneBasis } from "../sketch/plane";
import type { ArcSeat } from "./axisAnchorGauge";
import type { ProfileRegion } from "./profileLoops";

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

// --- THE TWIST (helical-gear gap G1) -----------------------------------------

/**
 * Degrees of twist per ghost STEP. `ExtrudeGeometry` builds a straight prism in
 * one step; a twisted one needs its walls cut into rings so each ring can turn,
 * and 5 degrees a ring keeps a tooth flank reading as a helix rather than a
 * staircase. Floored so a small twist still bends visibly, capped so a
 * ten-turn twist does not build a quarter-million-vertex ghost.
 */
export const TWIST_DEG_PER_STEP = 5;
const MIN_TWIST_STEPS = 8;
const MAX_TWIST_STEPS = 360;

/** How many rings the ghost's walls are cut into for a `twistDeg` twist. */
export function twistGhostSteps(twistDeg: number): number {
  if (twistDeg === 0) return 1;
  return Math.min(
    MAX_TWIST_STEPS,
    Math.max(
      MIN_TWIST_STEPS,
      Math.ceil(Math.abs(twistDeg) / TWIST_DEG_PER_STEP),
    ),
  );
}

/**
 * Turn a straight ghost into a twisted one, IN PLACE, in the ghost's local
 * plane space (x, y on the sketch, z along the normal; see
 * {@link extrudeGhostPose}).
 *
 * The kernel's rule, restated for a mesh: every slice is the profile turned
 * rigidly about the twist axis (through `centre`, parallel to the travel), by
 * `twistDeg` times the fraction of the distance travelled. The sign is
 * RIGHT-HANDED ABOUT THE DIRECTION OF TRAVEL, so a reverse extrude (travelling
 * toward -z) turns the other way about +z for the same positive twist: the
 * handedness belongs to the part, not to the direction toggle
 * (`docs/design/twisted-extrude.md` §5).
 *
 * ## The normals are twisted EXACTLY, not recomputed
 *
 * `computeVertexNormals` on the twisted mesh shades every ring's two triangles
 * separately, and a thin ring across a wide wall folds far enough that the
 * ghost came out striped like a saw blade. Given `normals`, each wall normal is
 * instead replaced by the analytic normal of the twisted surface at that
 * vertex: for a wall point `p` (from the axis) with straight normal `n0`, the
 * surface `R(k z) p` has normal `(R n0_xy, k (n0_x p_y - n0_y p_x))`, with
 * `k = dθ/dz`. It is smooth along a wall, exact at the vertices, and leaves a
 * cap flat and a cylinder about its own axis radial, as a twist does.
 *
 * @param positions a flat xyz buffer (a `BufferGeometry` position array).
 * @param centre the axis's sketch point, or null for the sketch origin.
 * @param normals the matching normal buffer, twisted alongside when given.
 */
export function twistPositionsInPlace(
  positions: Float32Array,
  depthMm: number,
  twistDeg: number,
  centre: { x: number; y: number } | null,
  reverse: boolean,
  normals?: Float32Array,
): void {
  if (twistDeg === 0 || !(depthMm > 0)) return;
  const cx = centre?.x ?? 0;
  const cy = centre?.y ?? 0;
  const perMm = (((twistDeg * Math.PI) / 180) * (reverse ? -1 : 1)) / depthMm;
  for (let i = 0; i + 2 < positions.length; i += 3) {
    const x = (positions[i] as number) - cx;
    const y = (positions[i + 1] as number) - cy;
    const z = positions[i + 2] as number;
    const a = perMm * Math.abs(z);
    const c = Math.cos(a);
    const s = Math.sin(a);
    positions[i] = cx + x * c - y * s;
    positions[i + 1] = cy + x * s + y * c;
    if (normals !== undefined) {
      const nx = normals[i] as number;
      const ny = normals[i + 1] as number;
      // dθ/dz. A reverse prism occupies z <= 0, where |z| = -z.
      const k = reverse ? -perMm : perMm;
      const tx = nx * c - ny * s;
      const ty = nx * s + ny * c;
      const tz = (normals[i + 2] as number) + k * (nx * y - ny * x);
      const len = Math.hypot(tx, ty, tz) || 1;
      normals[i] = tx / len;
      normals[i + 1] = ty / len;
      normals[i + 2] = tz / len;
    }
  }
}

/**
 * How far outside the profile the twist arc is drawn, as a fraction of the
 * profile's reach from the axis: the revolve arc's clearance, for the revolve
 * arc's reason (a protractor ON the silhouette is buried in the part).
 */
const TWIST_ARC_CLEARANCE_FRAC = 0.2;

/** Shortest arc radius the twist gauge seats at, scene mm (see revolve's). */
const MIN_TWIST_ARC_MM = 0.5;

/**
 * WHERE THE TWIST ARC STANDS: on the FAR cap, about the twist axis, measuring
 * from the profile's own furthest-out point.
 *
 * The far cap because that is where the twist is: the near end never turns, so
 * an arc at the sketch would dimension nothing. From the furthest point because
 * that is the corner whose travel you can see: at zero the grip sits just
 * outside it, and dragging carries the grip round with where that corner will
 * land. The axis is the TRAVEL direction, so the arc's positive sense (right-
 * handed about its axis) is the twist's positive sense with no sign to carry.
 *
 * Null when the profile encloses nothing (no ghost, so no cap to stand on).
 */
export function twistArcSeat(
  basis: PlaneBasis,
  regions: readonly ProfileRegion[],
  centre: { x: number; y: number } | null,
  depthMm: number,
  direction: ExtrudeDirection,
): ArcSeat | null {
  const cx = centre?.x ?? 0;
  const cy = centre?.y ?? 0;
  let reach = -1;
  let far = { x: cx, y: cy };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const region of regions) {
    for (const p of region.outer) {
      const r = Math.hypot(p.x - cx, p.y - cy);
      if (r > reach) {
        reach = r;
        far = p;
      }
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
  }
  if (reach < 0 || !(depthMm > 0)) return null;
  const sign = direction === "reverse" ? -1 : 1;
  const axis: Vec3 = [
    basis.normal[0] * sign,
    basis.normal[1] * sign,
    basis.normal[2] * sign,
  ];
  const onPlane = planeToWorld(basis, { x: cx, y: cy });
  const dx = far.x - cx;
  const dy = far.y - cy;
  const len = Math.hypot(dx, dy);
  // A profile whose furthest point IS the axis has no radial to measure from;
  // the plane's own u is as good a zero as any, and never a NaN.
  const reference: Vec3 =
    len > 1e-9
      ? [
          (basis.u[0] * dx + basis.v[0] * dy) / len,
          (basis.u[1] * dx + basis.v[1] * dy) / len,
          (basis.u[2] * dx + basis.v[2] * dy) / len,
        ]
      : [basis.u[0], basis.u[1], basis.u[2]];
  return {
    centre: [
      onPlane[0] + axis[0] * depthMm,
      onPlane[1] + axis[1] * depthMm,
      onPlane[2] + axis[2] * depthMm,
    ],
    axis,
    reference,
    arcRadiusMm: Math.max(
      MIN_TWIST_ARC_MM,
      reach * (1 + TWIST_ARC_CLEARANCE_FRAC),
    ),
    // The instrument's own scale is the PROFILE's (its half-diagonal), as for
    // the depth and revolve gauges: never the number it is showing.
    seatRadiusMm: Math.max(
      MIN_TWIST_ARC_MM,
      Math.hypot(maxX - minX, maxY - minY) / 2,
    ),
  };
}
