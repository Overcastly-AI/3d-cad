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
 *  * The band stays DRAWN, writing nothing (`colorWrite={false}` +
 *    `depthWrite={false}`; drei's `Line` forwards material props here, as
 *    `ModelMesh` relies on for `toneMapped`/`depthWrite`/`polygonOffset*`).
 *    Not because the raycaster would skip it otherwise: read in
 *    `three@0.185.1`, `Raycaster` tests `layers` only and never `visible`,
 *    which is why `PickSurface` skips its draw with `material.visible = false`
 *    (PERF-REAL-1). The band's own raycast is screen-space and reads
 *    `material.resolution`, returning nothing while that is zero. drei sets it
 *    from the canvas size, and the line's `onBeforeRender` refreshes it from
 *    the renderer viewport, and only a DRAWN line gets `onBeforeRender`.
 *    Whether drei's value alone would be enough has not been measured, so the
 *    band keeps the draw.
 *
 *  * r3f dedupes to ONE hit per OBJECT, the nearest in DEPTH, so its
 *    `event.intersections` cannot say which edge is nearest the CURSOR. On a
 *    thin wall that handed the pick to the wrong rim (EDGE-MARK-OVERLAP), so
 *    the layer does not read r3f's list at all: r3f's hit only says "the
 *    pointer is near the band", and {@link EdgeBandLayer}'s `resolveAt` casts
 *    its own ray through the pointer, keeps EVERY segment hit with its screen
 *    gap, and asks `resolveBandIntersections` for the nearest to the cursor
 *    that is PROVABLY visible (a second ray through that edge's own pixel;
 *    see `edgeBandProbe.ts`). Otherwise the edge in front keeps the pick, so
 *    an edge hidden behind a thin wall can never beat the visible one.
 *
 * ## Why a `PickSurface` rides along
 *
 * An edge on the FAR side of the solid must not win over the material in front
 * of it. The surface is mounted as a second raycast target purely so the
 * resolver can compare depths; the decision itself is
 * `resolveBandIntersections`', and the hover, the click and the mark-seat
 * oracle all reach it through the one `resolveAt`, so whichever handler fires
 * first they compute the same answer and the result cannot depend on hit
 * order.
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
import { Vector3 } from "three";
import type { BufferGeometry, Mesh, Vector2 } from "three";
import type { LineSegments2 } from "three-stdlib";

import {
  bandRadius,
  buildEdgeBand,
  edgeOcclusionBias,
  type EdgeBandInput,
  EDGE_BAND_WIDTH_PX,
} from "./edgeBand";
import { resolveBandAt } from "./edgeBandProbe";
import { PickSurface } from "./pickSurface";
import { useEdgeMarkAnchors, type EdgeMarkAnchor } from "./useEdgeMarkAnchors";

/**
 * Scratch for the mark-seat oracle, held across frames so the recompute
 * allocates nothing. `Vector3.project` writes in place.
 */
const probeWorld = new Vector3();
const probeProjected = new Vector3();

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
  const size = useThree((s) => s.size);
  const band = useMemo(() => buildEdgeBand(edges), [edges]);
  const bias = useMemo(
    () => edgeOcclusionBias(bandRadius(band.points)),
    [band],
  );
  const lineRef = useRef<LineSegments2 | null>(null);
  const surfaceRef = useRef<Mesh | null>(null);

  /**
   * THE ONE HIT-TEST: which edge a pointer at this NDC point addresses.
   *
   * Casts its own ray rather than reading r3f's `event.intersections`, because
   * r3f keeps one hit per object and the band is one object, so its list holds
   * only the edge nearest in DEPTH (see `resolveBandIntersections`). Here every
   * segment within the corridor is kept, each measured by how far it passes
   * from the cursor on screen, and the resolver takes the nearest visible one.
   * The hover, the click and the mark-seat oracle all come through here, so
   * the edge that highlights is the edge a click commits and the edge a mark
   * is seated on. The raycasts themselves live in `edgeBandProbe.ts`, where
   * they are unit-tested against real three.js objects.
   */
  const resolveAt = useCallback(
    (ndcX: number, ndcY: number): number | null => {
      const line = lineRef.current;
      if (line === null) return null;
      return resolveBandAt(ndcX, ndcY, {
        camera,
        width: size.width,
        height: size.height,
        band: line,
        surface: surfaceRef.current,
        edgeOfSegment: band.edgeOfSegment,
        bias,
      });
    },
    [camera, size, band, bias],
  );

  /**
   * THE MARK-SEAT ORACLE. Fire the pointer's own question at a scene point
   * through `resolveAt` — the very function the pointer handlers call — and ask
   * whether the answer is this edge.
   */
  const addressable = useCallback(
    (point: readonly [number, number, number], edgeIndex: number): boolean => {
      if (lineRef.current === null) return true;
      probeWorld.set(point[0] ?? 0, point[1] ?? 0, point[2] ?? 0);
      probeProjected.copy(probeWorld).project(camera);
      return resolveAt(probeProjected.x, probeProjected.y) === edgeIndex;
    },
    [camera, resolveAt],
  );

  const anchors = useEdgeMarkAnchors(
    edges,
    onAnchors === undefined ? undefined : addressable,
  );

  useEffect(() => {
    onAnchors?.(anchors);
  }, [anchors, onAnchors]);

  const handleMove = useCallback(
    (event: { pointer: Vector2 }) => {
      onHover(resolveAt(event.pointer.x, event.pointer.y));
    },
    [resolveAt, onHover],
  );

  /**
   * The click lands on the BAND only. The surface deliberately carries no click
   * handler: running the same resolve in both would fire `onPick` twice for one
   * click (a toggle picked and un-picked in the same gesture), and a click with
   * no band hit has no edge to report anyway.
   */
  const handleClick = useCallback(
    (event: ThreeEvent<MouseEvent>) => {
      const index = resolveAt(event.pointer.x, event.pointer.y);
      if (index === null) return;
      event.stopPropagation();
      onPick?.(index);
    },
    [resolveAt, onPick],
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
