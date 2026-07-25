/**
 * The live extrude ghost (UI-REVIEW 2026-07-24 #8 — "respond while you work").
 * While the extrude editor is OPEN, this renders a translucent swept solid of
 * the selected profile at the CURRENT distance, before Save — so a typed change
 * moves the picture instantly instead of leaving the viewport edit-blind.
 *
 * It is a client-side approximation (no kernel round-trip per keystroke): the
 * solved profile edges are stitched into loops ({@link profileRegions}) and
 * extruded along the sketch-plane normal with three.js. The committed body
 * still comes from the geometry service on Save; this is the "about to be" cue,
 * drawn in the same studio matcap as the real body, tinted toward brass and
 * held translucent (the `viewport.preview` tokens — one palette, two renderers).
 *
 * Every color/opacity is a token; GPU resources are disposed on change/unmount;
 * the depth is lightly debounced so a fast typist doesn't rebuild the mesh on
 * every intermediate keystroke.
 */
import { viewport } from "@loft/design/tokens";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import {
  BufferGeometry,
  EdgesGeometry,
  ExtrudeGeometry,
  LineBasicMaterial,
  Matrix4,
  MeshMatcapMaterial,
  Path,
  Quaternion,
  Shape,
  Vector2,
  Vector3,
} from "three";

import type { ExtrudeDirection } from "../features/extrude";
import type { SolvedSketchLayer } from "./SketchScene";
import { profileRegions } from "./profileLoops";
import { studioMatcap } from "./studioMatcap";

export interface ExtrudePreviewProps {
  /** The profile sketch to sweep (solved entities on its resolved basis). */
  layer: SolvedSketchLayer;
  /** The editor's current distance in canonical mm (always positive). */
  distanceMm: number;
  /** Sweep sense along the plane normal. */
  direction: ExtrudeDirection;
}

/** Rebuild the ghost mesh at most this often while the distance field changes. */
const PREVIEW_DEBOUNCE_MS = 70;

/** Debounce a numeric value so keystrokes don't thrash the geometry rebuild. */
function useDebounced(value: number, ms: number): number {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function ExtrudePreview({
  layer,
  distanceMm,
  direction,
}: ExtrudePreviewProps) {
  const invalidate = useThree((state) => state.invalidate);
  const depth = useDebounced(distanceMm, PREVIEW_DEBOUNCE_MS);

  // The profile → solid regions depend only on the geometry, not the depth.
  const regions = useMemo(() => profileRegions(layer.entities), [layer]);

  // One extruded BufferGeometry per region, in local plane (u,v,+normal) space.
  const geometries = useMemo<BufferGeometry[]>(() => {
    if (depth <= 0) return [];
    const reverse = direction === "reverse";
    return regions.map((region) => {
      const shape = new Shape(region.outer.map((p) => new Vector2(p.x, p.y)));
      shape.holes = region.holes.map(
        (hole) => new Path(hole.map((p) => new Vector2(p.x, p.y))),
      );
      const geometry = new ExtrudeGeometry(shape, {
        depth,
        bevelEnabled: false,
        steps: 1,
      });
      // ExtrudeGeometry sweeps toward local +Z (the plane normal). A reverse
      // extrude sweeps toward −normal, so slide the solid back by its depth.
      if (reverse) geometry.translate(0, 0, -depth);
      return geometry;
    });
  }, [regions, depth, direction]);

  const edges = useMemo(
    () => geometries.map((geometry) => new EdgesGeometry(geometry, 25)),
    [geometries],
  );

  // Orient local plane space onto the sketch basis: local X→u, Y→v, Z→normal,
  // placed at the plane origin (shared with the sketch ink — one plane-math
  // source). Recomputed only when the basis changes.
  const { position, quaternion } = useMemo(() => {
    const { u, v, normal, origin } = layer.basis;
    const matrix = new Matrix4().makeBasis(
      new Vector3(...u),
      new Vector3(...v),
      new Vector3(...normal),
    );
    return {
      position: new Vector3(...origin),
      quaternion: new Quaternion().setFromRotationMatrix(matrix),
    };
  }, [layer.basis]);

  const surfaceMaterial = useMemo(() => {
    const material = new MeshMatcapMaterial({ matcap: studioMatcap() });
    material.color.set(viewport.preview.surfaceTint);
    material.transparent = true;
    material.opacity = viewport.preview.surfaceOpacity;
    material.depthWrite = false;
    return material;
  }, []);
  const edgeMaterial = useMemo(() => {
    const material = new LineBasicMaterial({ color: viewport.preview.edge });
    material.transparent = true;
    material.opacity = viewport.preview.edgeOpacity;
    material.depthWrite = false;
    return material;
  }, []);

  // Dispose GPU resources: geometries/edges when they change, materials on
  // unmount. Draw a frame on every change (frameloop="demand").
  useEffect(() => {
    invalidate();
    return () => {
      for (const geometry of geometries) geometry.dispose();
      for (const edge of edges) edge.dispose();
    };
  }, [geometries, edges, invalidate]);
  useEffect(
    () => () => {
      surfaceMaterial.dispose();
      edgeMaterial.dispose();
    },
    [surfaceMaterial, edgeMaterial],
  );

  if (geometries.length === 0) return null;
  return (
    <group position={position} quaternion={quaternion}>
      {geometries.map((geometry, i) => (
        <mesh key={i} geometry={geometry} material={surfaceMaterial} />
      ))}
      {edges.map((edge, i) => (
        <lineSegments key={i} geometry={edge} material={edgeMaterial} />
      ))}
    </group>
  );
}
