/**
 * Shared viewport line-overlay primitive — one un-tonemapped `lineSegments`
 * layer drawn in a `measure` token color, with GPU-resource disposal on
 * unmount. Used by both the measurement overlay (edge highlights + dimension
 * line) and the fillet/chamfer edge-pick overlay (selected + hover highlights),
 * so the highlight draw lives in ONE place (CLAUDE.md DRY rule).
 */
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
