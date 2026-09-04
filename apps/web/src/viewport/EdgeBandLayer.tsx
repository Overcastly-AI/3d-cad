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
import { useThree, type ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { Raycaster, Vector2, Vector3 } from "three";
import type { BufferGeometry, Intersection, Mesh } from "three";
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
import { useEdgeMarkAnchors, type EdgeMarkAnchor } from "./useEdgeMarkAnchors";

/**
 * Scratch for the mark-seat oracle, held across frames so the recompute
 * allocates nothing. `Vector3.project` and `Raycaster.setFromCamera` both write
 * in place, and the hit array is truncated rather than replaced.
 */
const probeRaycaster = new Raycaster();
const probeNdc = new Vector2();
const probeWorld = new Vector3();
const probeProjected = new Vector3();
const probeHits: Intersection[] = [];

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
  /**
   * WHERE EACH EDGE'S PICK MARK BELONGS (PICKMARK-OCCLUDE-1), in the same order
   * as `edges`. Published from here rather than computed by the overlay because
   * the answer is the BAND's — one hit-test decides both where a mark sits and
   * what a click on the geometry resolves to, so the two cannot disagree.
   */
  onAnchors?: (anchors: readonly EdgeMarkAnchor[]) => void;
}

export function EdgeBandLayer({
  edges,
  geometry,
  onHover,
  onPick,
  onAnchors,
}: EdgeBandLayerProps) {
  const camera = useThree((s) => s.camera);
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

  /**
   * THE MARK-SEAT ORACLE. Fire the pointer's own question at a scene point:
   * cast a ray through it and ask `resolveBandIntersections` — the very
   * function the pointer handlers call — whether the answer is this edge.
   *
   * `intersectObject` sorts what it appends, so the combined list arrives
   * near → far exactly as r3f delivers `event.intersections`; taking the first
   * band hit is then the same choice r3f's per-object dedupe makes.
   */
  const addressable = useCallback(
    (point: readonly [number, number, number], edgeIndex: number): boolean => {
      const line = lineRef.current;
      if (line === null) return true;
      probeWorld.set(point[0] ?? 0, point[1] ?? 0, point[2] ?? 0);
      probeProjected.copy(probeWorld).project(camera);
      probeNdc.set(probeProjected.x, probeProjected.y);
      probeRaycaster.setFromCamera(probeNdc, camera);
      probeHits.length = 0;
      probeRaycaster.intersectObject(line, false, probeHits);
      const surface = surfaceRef.current;
      if (surface !== null) {
        probeRaycaster.intersectObject(surface, false, probeHits);
      }
      return (
        resolveBandIntersections(
          probeHits as unknown as BandIntersection[],
          { band: line, surface },
          band.edgeOfSegment,
          bias,
        ) === edgeIndex
      );
    },
    [camera, band, bias],
  );

  const anchors = useEdgeMarkAnchors(
    edges,
    onAnchors === undefined ? undefined : addressable,
  );

  useEffect(() => {
    onAnchors?.(anchors);
  }, [anchors, onAnchors]);

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
