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
  BufferGeometry,
  EdgesGeometry,
  ExtrudeGeometry,
  Float32BufferAttribute,
  FrontSide,
  Matrix4,
  Path,
  Quaternion,
  Shape,
  Vector2,
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
 * staircase. Floored so a small twist still bends visibly.
 */
export const TWIST_DEG_PER_STEP = 5;
const MIN_TWIST_STEPS = 8;
const MAX_TWIST_STEPS = 360;

/**
 * The most WALL vertices a twisted ghost may carry. Rings multiply the walls,
 * and the ghost rebuilds every 70 ms while the arc is dragged: review S1
 * measured a 664-point gear outline at 360 rings as 1.44M vertices and 3.4 s
 * of edge-finding per rebuild. The budget bounds the rings by the outline
 * instead of the angle alone (a 664-point outline gets 37 rings; a rectangle
 * still gets the full 5 degrees a ring). A coarser helix on a ten-turn,
 * many-toothed preview is the right trade; a frozen viewport is not.
 */
export const GHOST_WALL_VERTEX_BUDGET = 150_000;

/** Vertices one ring of wall costs: two triangles per outline edge. */
const WALL_VERTICES_PER_EDGE = 6;

/**
 * How many rings the ghost's walls are cut into for a `twistDeg` twist of an
 * outline with `outlineVertexCount` points (outer loop plus holes).
 */
export function twistGhostSteps(
  twistDeg: number,
  outlineVertexCount: number,
): number {
  if (twistDeg === 0) return 1;
  const wanted = Math.min(
    MAX_TWIST_STEPS,
    Math.max(
      MIN_TWIST_STEPS,
      Math.ceil(Math.abs(twistDeg) / TWIST_DEG_PER_STEP),
    ),
  );
  const affordable = Math.floor(
    GHOST_WALL_VERTEX_BUDGET /
      Math.max(1, outlineVertexCount * WALL_VERTICES_PER_EDGE),
  );
  return Math.max(1, Math.min(wanted, affordable));
}

/**
 * Cut every segment that SPANS the travel (a straight prism's side edges run
 * from z = 0 to z = +/-depth) into `steps` pieces, so the twist can bend it
 * into a helix; segments within one z (the cap outlines) pass through. Exact
 * on a straight prism, where a side edge is a straight line in z.
 */
export function ringEdgePositions(
  segments: Float32Array,
  steps: number,
): Float32Array {
  if (steps <= 1) return segments;
  const out: number[] = [];
  for (let i = 0; i + 5 < segments.length; i += 6) {
    const a = [segments[i], segments[i + 1], segments[i + 2]] as number[];
    const b = [segments[i + 3], segments[i + 4], segments[i + 5]] as number[];
    if (Math.abs((a[2] as number) - (b[2] as number)) < 1e-9) {
      out.push(...a, ...b);
      continue;
    }
    for (let k = 0; k < steps; k += 1) {
      for (const t of [k / steps, (k + 1) / steps]) {
        out.push(
          (a[0] as number) + ((b[0] as number) - (a[0] as number)) * t,
          (a[1] as number) + ((b[1] as number) - (a[1] as number)) * t,
          (a[2] as number) + ((b[2] as number) - (a[2] as number)) * t,
        );
      }
    }
  }
  return new Float32Array(out);
}

/** One region's ghost: the swept mesh and the ink over it. */
export interface GhostRegionGeometry {
  mesh: BufferGeometry;
  edges: BufferGeometry;
}

/**
 * Build one region's ghost, in local plane space (see {@link extrudeGhostPose}):
 * the prism swept `depthMm` along +z (or -z for a reverse extrude), cut into
 * rings and twisted when `twistDeg` is not 0.
 *
 * THE INK IS FOUND ON A ONE-STEP PRISM. Found on the ringed mesh, every ring's
 * triangle diagonal is a crease past the threshold (a lattice), and edge-finding
 * over a ringed mesh is the cost review S1 measured; on the one-step prism it
 * is the outline's size, and the side edges are then split into the same rings
 * ({@link ringEdgePositions}) so they bend with the walls.
 */
export function buildGhostRegion(
  region: ProfileRegion,
  depthMm: number,
  direction: ExtrudeDirection,
  twistDeg: number,
  centre: { x: number; y: number } | null,
): GhostRegionGeometry {
  const reverse = direction === "reverse";
  const shape = new Shape(region.outer.map((p) => new Vector2(p.x, p.y)));
  shape.holes = region.holes.map(
    (hole) => new Path(hole.map((p) => new Vector2(p.x, p.y))),
  );
  const outlineVertexCount =
    region.outer.length +
    region.holes.reduce((sum, hole) => sum + hole.length, 0);
  const steps = twistGhostSteps(twistDeg, outlineVertexCount);
  const build = (s: number): ExtrudeGeometry => {
    const geometry = new ExtrudeGeometry(shape, {
      depth: depthMm,
      bevelEnabled: false,
      steps: s,
    });
    // ExtrudeGeometry sweeps toward local +Z (the plane normal). A reverse
    // extrude sweeps toward -normal, so slide the solid back by its depth.
    if (reverse) geometry.translate(0, 0, -depthMm);
    return geometry;
  };
  const mesh = build(steps);
  const prism = steps === 1 ? mesh : build(1);
  const found = new EdgesGeometry(prism, 25);
  if (prism !== mesh) prism.dispose();
  const edgePositions = ringEdgePositions(
    found.getAttribute("position").array as Float32Array,
    steps,
  );
  const edges =
    steps === 1
      ? found
      : new BufferGeometry().setAttribute(
          "position",
          new Float32BufferAttribute(edgePositions, 3),
        );
  if (edges !== found) found.dispose();
  if (twistDeg !== 0) {
    // THE GHOST TWISTS (helical-gear gap G1): the picture must not contradict
    // the twisted body Save produces. Normals turn WITH the mesh, exactly.
    twistPositionsInPlace(
      mesh.getAttribute("position").array as Float32Array,
      depthMm,
      twistDeg,
      centre,
      reverse,
      mesh.getAttribute("normal").array as Float32Array,
    );
    twistPositionsInPlace(
      edges.getAttribute("position").array as Float32Array,
      depthMm,
      twistDeg,
      centre,
      reverse,
    );
  }
  return { mesh, edges };
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
