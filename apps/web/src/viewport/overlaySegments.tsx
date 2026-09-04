/**
 * Shared viewport line-overlay primitives — un-tonemapped line layers drawn in
 * `measure` token colors, with GPU-resource disposal on unmount. Used by the
 * measurement overlay, the fillet/chamfer edge-pick overlay, the flange span
 * and bend overlays and the extrude gauge, so the draw lives in ONE place
 * (CLAUDE.md DRY rule).
 *
 * TWO primitives, and the difference between them is the whole of SEL-8.
 * {@link Segments} is a plain 1 px GL line, correct for anything drawn in FREE
 * SPACE — a dimension line between two witness points, a gauge graduation.
 * {@link HighlightLines} is for geometry drawn ON THE BODY, where a plain GL
 * line does not work and cannot be made to; see its own doc comment.
 */
import { Line } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import { BufferGeometry, Float32BufferAttribute } from "three";

/** Concatenate several position buffers into one draw. */
export function concatPositions(
  buffers: readonly Float32Array[],
): Float32Array {
  const total = buffers.reduce((n, b) => n + b.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const b of buffers) {
    out.set(b, offset);
    offset += b.length;
  }
  return out;
}

export interface SegmentsProps {
  positions: Float32Array;
  color: string;
  depthTest?: boolean;
  renderOrder?: number;
  /**
   * Line opacity. Defaults to solid, which is what every highlight wants; the
   * extrude gauge's graduations want half strength, and a token-held opacity
   * belongs on the shared primitive rather than as a second `lineSegments` in
   * the one component that needed it.
   */
  opacity?: number;
}

/** One un-tonemapped line layer with GPU-resource disposal. */
export function Segments({
  positions,
  color,
  depthTest = true,
  renderOrder = 0,
  opacity = 1,
}: SegmentsProps) {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return g;
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  if (positions.length === 0) return null;
  return (
    <lineSegments
      geometry={geometry}
      frustumCulled={false}
      renderOrder={renderOrder}
    >
      <lineBasicMaterial
        color={color}
        toneMapped={false}
        depthTest={depthTest}
        depthWrite={false}
        transparent
        opacity={opacity}
      />
    </lineSegments>
  );
}

/**
 * Segment endpoint pairs as drei's `Line` wants them. `LineSegments2` builds
 * instanced quads from a point list, so it cannot take the `Float32Array` the
 * rest of this module passes around.
 *
 * Runs inside a `useMemo` keyed on the buffer, i.e. when the hovered or picked
 * set CHANGES — never per frame, so the render loop stays allocation-free.
 */
function segmentPoints(
  positions: Float32Array,
): [number, number, number][] | null {
  if (positions.length < 6) return null;
  const points: [number, number, number][] = [];
  for (let i = 0; i + 2 < positions.length; i += 3) {
    points.push([
      positions[i] as number,
      positions[i + 1] as number,
      positions[i + 2] as number,
    ]);
  }
  return points;
}

export interface HighlightLinesProps {
  /** Segment endpoint pairs, flat xyz — the same buffer {@link Segments} takes. */
  positions: Float32Array;
  color: string;
  /** Screen-space width in px, from the token that owns this highlight. */
  widthPx: number;
  /** Strength of the pass drawn where the geometry is BEHIND the body. */
  xrayOpacity: number;
  /** Base draw order; the two passes sit at this and this + 1. */
  renderOrder?: number;
}

/**
 * GEOMETRY ON THE BODY, HIGHLIGHTED — drawn in the two passes it takes to be
 * visible at all.
 *
 * ## Why a plain GL line does not work here (SEL-8)
 *
 * A B-rep edge's polyline is numerically coincident with the drawn mesh: the
 * edge IS where the surface is. A 1 px `lineBasicMaterial` at that depth loses
 * the depth test against the body's own triangles and is discarded — not
 * dimmed, not stippled, DISCARDED. Measured on the product audit's own part
 * (`docs/AUDIT-PRODUCT.md` R-8): hovering the hub/flange junction set the hover
 * state correctly and changed 13 of 1,363,200 canvas pixels, i.e. nothing.
 * That is why the audit reported "no hover highlight anywhere along the real
 * edge" while every pick spec was green — the specs asserted on the hover
 * STAMP, which was firing the whole time.
 *
 * `polygonOffset` is the usual answer to a coincident-depth fight and WebGL
 * only exposes `POLYGON_OFFSET_FILL`, so it does nothing for a GL line. The
 * fix is therefore to stop drawing a GL line: `LineSegments2` renders instanced
 * QUADS, which are fills, so it has screen-space width AND a working depth
 * bias.
 *
 *  - the x-ray pass: the whole set, `depthTest: false`, at `xrayOpacity` —
 *    faint enough not to compete with the material in front of it, present
 *    enough to say a circular edge closes round the back.
 *  - the front pass: the ribbon, depth-tested and biased a hair toward the
 *    camera, at full strength wherever the geometry is genuinely visible.
 *
 * Neither pass writes depth, so a highlight can never occlude what is behind
 * it. `FaceTrace` reached this same shape first, for the face half of the same
 * problem; this is the edge half, and the two now say it the same way.
 */
export function HighlightLines({
  positions,
  color,
  widthPx,
  xrayOpacity,
  renderOrder = 0,
}: HighlightLinesProps) {
  const points = useMemo(() => segmentPoints(positions), [positions]);
  if (points === null) return null;
  return (
    <group>
      <Segments
        positions={positions}
        color={color}
        depthTest={false}
        opacity={xrayOpacity}
        renderOrder={renderOrder}
      />
      <Line
        points={points}
        segments
        color={color}
        lineWidth={widthPx}
        toneMapped={false}
        depthWrite={false}
        polygonOffset
        polygonOffsetFactor={-4}
        polygonOffsetUnits={-4}
        renderOrder={renderOrder + 1}
      />
    </group>
  );
}
