/**
 * THE FACE TRACE — a B-rep face drawn as ITS OWN BOUNDARY, on the real
 * geometry.
 *
 * Extracted from `ModelMesh` by MATE-1, which needed the same thing on an
 * assembly instance. The part workspace has traced the addressed face since
 * SEL-1; the mate pick had only `FacePatch`, an area-equivalent DISC laid on
 * the face's plane — which the fourth product pass (T-13) reported as "a
 * translucent ellipse floating mostly below the plate, bearing no relation to
 * the face's actual outline". It is a fair description: a disc of the right
 * AREA is not the right SHAPE, and on a rectangular face it hangs over two
 * edges while leaving two corners bare. Nobody should have to write that
 * component twice, and after this nobody has (CLAUDE.md: fix the primitive).
 *
 * ## Why the boundary is drawn twice
 *
 * Inherited verbatim from `ModelMesh`, where it was learned the hard way (code
 * review, 2026-08-06). `subsetEdges` feeds `EdgesGeometry` only the traced
 * face's triangles, and `EdgesGeometry` emits every UNMATCHED edge — so the
 * whole topological boundary comes out, including the half that faces away. On
 * a bore that is the top circle AND the bottom one, and drawn without a depth
 * test the bottom circle paints over the front of the part. But drawn WITH one
 * and nothing else, the trace is numerically coincident with the body's own
 * edge overlay and two 1 px GL lines at equal depth stipple.
 *
 *  - the x-ray pass: the whole loop, `depthTest: false`, at
 *    `hoverEdgeXrayOpacity` — faint enough not to compete with the surface in
 *    front of it, present enough to say the face wraps out of sight.
 *  - the front pass: a drei `Line` (`LineSegments2`) — instanced QUADS, so it
 *    has screen-space width and `polygonOffset` genuinely applies. Biased a
 *    hair toward the camera it wins the coincident-depth fight outright.
 *
 * `depthWrite` is off on both, so neither leaves anything for the next frame.
 */
import { viewport } from "@loft/design/tokens";
import { Line } from "@react-three/drei";
import { useEffect, useMemo } from "react";
import { DoubleSide, LineBasicMaterial } from "three";
import type { BufferGeometry, EdgesGeometry } from "three";

import { subsetEdges, subsetSurface } from "./glbGeometry";

export interface FaceTraceProps {
  /** The body's mesh — the SAME partitioned geometry the pick raycasts. */
  geometry: BufferGeometry | null;
  /** B-rep face ordinals to trace (usually one), or null for none. */
  faceOrdinals: ReadonlySet<number> | null;
  /** Committed rather than merely addressed — full brass instead of hover. */
  selected?: boolean;
  /**
   * Also wash the face's OWN TRIANGLES, inside the traced loop.
   *
   * The part workspace does not need this: `ModelMesh` tints the addressed
   * face through a draw group on the body itself, which is better still —
   * it multiplies the studio matcap and keeps the machined read. An assembly
   * instance draws one shared geometry with one material and has no such
   * group, so the wash is how a mate candidate gets a surface at all. Off by
   * default, so nobody gets both.
   */
  fill?: boolean;
}

/** The traced loop as a flat point list — `Line2` takes points, not geometry. */
function tracePoints(
  edges: EdgesGeometry | null,
): [number, number, number][] | null {
  if (edges === null) return null;
  const position = edges.getAttribute("position");
  if (position === undefined) return null;
  const points: [number, number, number][] = [];
  for (let i = 0; i < position.count; i += 1) {
    points.push([position.getX(i), position.getY(i), position.getZ(i)]);
  }
  return points.length > 0 ? points : null;
}

export function FaceTrace({
  geometry,
  faceOrdinals,
  selected = false,
  fill = false,
}: FaceTraceProps) {
  const color = selected ? viewport.facePick.selected : viewport.hover;
  const empty =
    geometry === null || faceOrdinals === null || faceOrdinals.size === 0;

  const edges = useMemo<EdgesGeometry | null>(
    () => (empty ? null : subsetEdges(geometry, faceOrdinals)),
    [empty, geometry, faceOrdinals],
  );
  useEffect(() => () => edges?.dispose(), [edges]);

  const surface = useMemo<BufferGeometry | null>(
    () => (empty || !fill ? null : subsetSurface(geometry, faceOrdinals)),
    [empty, fill, geometry, faceOrdinals],
  );
  // Disposes the INDEX only — the position attribute is the body's own and is
  // shared, not copied, so three's `dispose()` releasing it would take the
  // drawn mesh's buffer with it. `deleteAttribute` first is what keeps this
  // highlight from being able to blank the body it highlights.
  useEffect(
    () => () => {
      surface?.deleteAttribute("position");
      surface?.dispose();
    },
    [surface],
  );

  const xrayMaterial = useMemo(
    () =>
      new LineBasicMaterial({
        depthTest: false,
        depthWrite: false,
        transparent: true,
        opacity: viewport.facePick.hoverEdgeXrayOpacity,
      }),
    [],
  );
  useEffect(() => () => xrayMaterial.dispose(), [xrayMaterial]);
  useEffect(() => {
    xrayMaterial.color.set(color);
  }, [xrayMaterial, color]);

  const points = useMemo(() => tracePoints(edges), [edges]);

  if (edges === null || points === null) return null;

  return (
    <group>
      {/*
        The face's own triangles, washed — and washed in the SAME two passes
        the boundary takes, for the same reason. A mate candidate is routinely
        BURIED (a bracket seated on a plate has its bottom face behind its own
        body from above and behind the plate from below), so a wash that is
        only depth-tested lights nothing at exactly the moment it matters; and
        a wash that is only depth-test-off paints over whatever stands in front
        of it and stops being a statement about a surface.

        So: the x-ray pass at the faint `hoverEdgeXrayOpacity`, saying "the face
        continues behind this", under the depth-tested pass at full strength
        wherever the face is genuinely visible. `DoubleSide` on both, because
        a contact face is normally addressed from its back. Neither writes
        depth, so a highlight can never occlude the candidate BEHIND it in the
        same column.
      */}
      {surface !== null ? (
        <>
          <mesh geometry={surface} renderOrder={0}>
            <meshBasicMaterial
              color={color}
              transparent
              opacity={viewport.facePick.hoverEdgeXrayOpacity}
              side={DoubleSide}
              depthTest={false}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
          <mesh geometry={surface} renderOrder={1}>
            <meshBasicMaterial
              color={color}
              transparent
              opacity={
                selected
                  ? viewport.facePick.selectedOpacity
                  : viewport.facePick.hoverOpacity
              }
              side={DoubleSide}
              depthWrite={false}
              toneMapped={false}
              polygonOffset
              polygonOffsetFactor={-2}
              polygonOffsetUnits={-2}
            />
          </mesh>
        </>
      ) : null}
      <lineSegments geometry={edges} material={xrayMaterial} renderOrder={1} />
      <Line
        points={points}
        segments
        color={color}
        lineWidth={viewport.facePick.hoverEdgeWidthPx}
        toneMapped={false}
        depthWrite={false}
        polygonOffset
        polygonOffsetFactor={-4}
        polygonOffsetUnits={-4}
        renderOrder={2}
      />
    </group>
  );
}
