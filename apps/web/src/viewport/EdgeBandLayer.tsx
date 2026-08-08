/**
 * THE EDGE HIT-TEST — an invisible screen-space corridor around every pickable
 * edge, so a fillet, a chamfer, a measurement or a mate axis addresses the edge
 * the modeller can see instead of a 24 px diamond parked at its mid-span
 * (SEL-4, spec A2).
 *
 * The maths and the two decisions worth testing live in `edgeBand.ts`; this is
 * the scene plumbing around them, shared by every edge pick so there is one
 * implementation rather than four.
 *
 * ## Why `LineSegments2` and not a hand-rolled projection
 *
 * Its raycast is ALREADY screen-space when `material.worldUnits === false`: a
 * hit needs the pointer within `material.linewidth / 2` pixels of the segment,
 * and each intersection carries `faceIndex` = the segment index, which is the
 * segment→edge lookup for free. Rolling our own would mean projecting every
 * polyline every frame in JS, on the main thread, to answer one pick.
 *
 * Two consequences of using it are load-bearing and easy to get wrong:
 *
 *  * The band must actually RENDER. `LineSegments2.raycast` reads
 *    `material.resolution` (drei sets it from the viewport size) and three's
 *    raycaster skips invisible objects, so `visible={false}` would silently
 *    kill every hit. `colorWrite={false}` + `depthWrite={false}` is how it
 *    draws nothing while staying live — the same trick `PickSurface` uses, and
 *    drei's `Line` already forwards material props here (`ModelMesh` passes
 *    `toneMapped`/`depthWrite`/`polygonOffset*` through it).
 *
 *  * r3f dedupes to ONE hit per OBJECT, so the band resolves nearest-in-DEPTH
 *    rather than nearest-in-screen. See `resolveBandEdge` for why that is the
 *    right answer and why not to build a screen-distance tie-break on it.
 *
 * ## Why a `PickSurface` rides along
 *
 * An edge on the FAR side of the solid must not win over the material in front
 * of it. The surface is mounted as a second raycast target purely so the
 * handler can compare depths; the decision itself is
 * `resolveBandIntersections`', and both handlers run it over the SAME
 * `event.intersections` array, so whichever fires first they compute the same
 * answer and the result cannot depend on hit order.
 *
 * A hit on that surface is DRAWN material by construction: `PickSurface` mounts
 * it with the `pickRaycast.ts` filter, which drops a hidden body's triangles
 * inside `Mesh.raycast` before r3f ever dedupes the list. So this layer needs no
 * opinion about visibility at all — it used to carry a `surfaceOccludes`
 * predicate, and that predicate could only ever REFUSE the nearest hit, never
 * see past it (SEL-6). One filter, one place, and both handlers inherit it.
 */
import { Line } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import { useCallback, useMemo, useRef } from "react";
import type { BufferGeometry, Mesh } from "three";
import type { LineSegments2 } from "three-stdlib";

import {
  bandRadius,
  buildEdgeBand,
  edgeOcclusionBias,
  resolveBandIntersections,
  type BandIntersection,
  type EdgeBandInput,
  EDGE_BAND_WIDTH_PX,
} from "./edgeBand";
import { PickSurface } from "./pickSurface";

export interface EdgeBandLayerProps {
  /** The pickable edges, each with the index a hit should report. */
  edges: readonly EdgeBandInput[];
  /**
   * Explicit raycast surface for the occlusion test. Omit in the part
   * workspace and the mesh `ModelMesh` publishes is used.
   */
  geometry?: BufferGeometry | null;
  /** The edge the pointer is addressing, or null. Fires on every move. */
  onHover: (index: number | null) => void;
  /** A click that resolved to an edge. */
  onPick?: (index: number) => void;
}

export function EdgeBandLayer({
  edges,
  geometry,
  onHover,
  onPick,
}: EdgeBandLayerProps) {
  const band = useMemo(() => buildEdgeBand(edges), [edges]);
  const bias = useMemo(
    () => edgeOcclusionBias(bandRadius(band.points)),
    [band],
  );
  const lineRef = useRef<LineSegments2 | null>(null);
  const surfaceRef = useRef<Mesh | null>(null);

  /**
   * The addressed edge for one pointer event. Reads the whole intersection
   * list rather than the event's own hit, so the band handler and the surface
   * handler are the same function of the same input.
   */
  const resolve = useCallback(
    (intersections: readonly BandIntersection[]): number | null =>
      resolveBandIntersections(
        intersections,
        { band: lineRef.current, surface: surfaceRef.current },
        band.edgeOfSegment,
        bias,
      ),
    [band, bias],
  );

  const handleMove = useCallback(
    (event: { intersections: readonly BandIntersection[] }) => {
      onHover(resolve(event.intersections));
    },
    [resolve, onHover],
  );

  /**
   * The click lands on the BAND only. The surface deliberately carries no click
   * handler: running the same resolve in both would fire `onPick` twice for one
   * click (a toggle picked and un-picked in the same gesture), and a click with
   * no band hit has no edge to report anyway.
   */
  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      const index = resolve(event.intersections);
      if (index === null) return;
      event.stopPropagation();
      onPick?.(index);
    },
    [resolve, onPick],
  );

  return (
    <group>
      <PickSurface
        geometry={geometry}
        meshRef={surfaceRef}
        onMove={(_ordinal, event) => handleMove(event)}
        onOut={() => onHover(null)}
      />
      {band.points.length > 0 ? (
        <Line
          ref={lineRef}
          points={band.points}
          segments
          lineWidth={EDGE_BAND_WIDTH_PX}
          colorWrite={false}
          depthWrite={false}
          toneMapped={false}
          renderOrder={-1}
          onPointerMove={handleMove}
          onPointerOut={() => onHover(null)}
          onClick={handleClick}
        />
      ) : null}
    </group>
  );
}
