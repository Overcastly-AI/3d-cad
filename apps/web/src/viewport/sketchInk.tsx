/**
 * The sketch's ink primitives — one LineSegments / Points draw per layer —
 * shared by the live sketch (`SketchScene`) and the projected-geometry layer
 * (`ProjectedInk`). Split out of `SketchScene.tsx`; behaviour unchanged. The
 * render-order policy these constants implement is documented there.
 */
import { sketch } from "@loft/design/tokens";
import { useEffect, useMemo, useRef } from "react";
import {
  BufferGeometry,
  Float32BufferAttribute,
  type LineSegments,
} from "three";

import type { PlaneBasis } from "../sketch/plane";
import { pointEntityStations, stationPositions } from "../sketch/pointEntity";
import type { SketchEntity } from "../sketch/tools";

/** The active sketch's ink draws over the solid (SketchScene policy note). */
export const ACTIVE_INK_RENDER_ORDER = 900;
/** Defining-point dots ride one step above their own lines. */
export const ACTIVE_POINT_RENDER_ORDER = 901;

/** Shared geometry plumbing: a positions buffer with disposal. */
export function usePositionsGeometry(positions: Float32Array): BufferGeometry {
  const geometry = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(positions, 3));
    return g;
  }, [positions]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return geometry;
}

interface InkSegmentsProps {
  positions: Float32Array;
  color: string;
  dashed?: boolean;
  /** Dash geometry (world mm); defaults to the rubber-band preview pattern. */
  dashSize?: number;
  gapSize?: number;
  /**
   * This is the ACTIVE sketch — draw it over the solid (policy note above).
   * Off by default so committed/solved ink keeps ordinary occlusion.
   */
  onTop?: boolean;
  /** Order WITHIN the on-top layer; defaults to the ink's own step. */
  order?: number;
}

/** One layer of sketch ink — a single LineSegments draw call. */
export function InkSegments({
  positions,
  color,
  dashed = false,
  dashSize = sketch.previewDashMm,
  gapSize = sketch.previewGapMm,
  onTop = false,
  order = ACTIVE_INK_RENDER_ORDER,
}: InkSegmentsProps) {
  const ref = useRef<LineSegments>(null);
  const geometry = usePositionsGeometry(positions);
  // LineDashedMaterial needs per-vertex line distances.
  useEffect(() => {
    if (dashed) ref.current?.computeLineDistances();
  }, [geometry, dashed]);
  if (positions.length === 0) return null;
  // Alpha stays 1: `transparent` is here to put the ink in the queue that
  // renders LAST, not to fade it, so the token hex still lands exactly (the
  // e2e pixel probe reads it).
  const depth = onTop
    ? { depthTest: false, depthWrite: false, transparent: true }
    : {};
  return (
    <lineSegments
      ref={ref}
      geometry={geometry}
      frustumCulled={false}
      renderOrder={onTop ? order : 0}
    >
      {dashed ? (
        <lineDashedMaterial
          color={color}
          dashSize={dashSize}
          gapSize={gapSize}
          toneMapped={false}
          {...depth}
        />
      ) : (
        <lineBasicMaterial color={color} toneMapped={false} {...depth} />
      )}
    </lineSegments>
  );
}

/** Split entities into profile (solid scribe) and construction (dashed) sets. */
export function partitionConstruction(entities: readonly SketchEntity[]): {
  profile: SketchEntity[];
  construction: SketchEntity[];
} {
  const profile: SketchEntity[] = [];
  const construction: SketchEntity[] = [];
  for (const entity of entities) {
    (entity.construction ? construction : profile).push(entity);
  }
  return { profile, construction };
}

/** Defining points (endpoints, centers) — screen-space brass dots. */
export function InkPoints({
  positions,
  color,
  sizePx = sketch.pointSizePx,
  onTop = false,
  renderOrder,
}: {
  positions: Float32Array;
  color: string;
  sizePx?: number;
  /** Active-sketch handles draw over the solid (policy note above). */
  onTop?: boolean;
  /** Overrides the layer's order (a mark that must sit UNDER the dots). */
  renderOrder?: number;
}) {
  const geometry = usePositionsGeometry(positions);
  if (positions.length === 0) return null;
  return (
    <points
      geometry={geometry}
      frustumCulled={false}
      renderOrder={renderOrder ?? (onTop ? ACTIVE_POINT_RENDER_ORDER : 0)}
    >
      <pointsMaterial
        color={color}
        size={sizePx}
        sizeAttenuation={false}
        toneMapped={false}
        {...(onTop
          ? { depthTest: false, depthWrite: false, transparent: true }
          : {})}
      />
    </points>
  );
}

/**
 * Station marks for sketch POINT entities, live and solved. Every other layer
 * draws curves, so a point entity would otherwise be a bare defining dot (no
 * different from an endpoint) while authoring, and invisible once the sketch
 * is finished, which is exactly when a loft apex has to be found and checked.
 *
 * Live: a scribe-ink square one render step UNDER the point's own brass dot,
 * so it reads as a ringed punch mark; picks and hovers still land on top.
 * Solved: the settled scribe, depth tested like the rest of a solved sketch.
 */
export function PointEntityInk({
  entities,
  basis,
  solved = false,
}: {
  entities: readonly SketchEntity[];
  basis: PlaneBasis;
  /** A finished sketch out in the model, not the one being authored. */
  solved?: boolean;
}) {
  const stations = useMemo(() => pointEntityStations(entities), [entities]);
  const profile = useMemo(
    () => stationPositions(stations.profile, basis),
    [stations, basis],
  );
  const construction = useMemo(
    () => stationPositions(stations.construction, basis),
    [stations, basis],
  );
  const live = solved
    ? {}
    : { onTop: true, renderOrder: ACTIVE_INK_RENDER_ORDER };
  return (
    <>
      <InkPoints
        positions={profile}
        color={solved ? sketch.scribeSolved : sketch.scribe}
        sizePx={sketch.stationPointSizePx}
        {...live}
      />
      <InkPoints
        positions={construction}
        color={sketch.constructionInk}
        sizePx={sketch.stationPointSizePx}
        {...live}
      />
    </>
  );
}
