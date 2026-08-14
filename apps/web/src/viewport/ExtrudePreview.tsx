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
 * The ghost obeys the OPERATION (FINDINGS burn-down 2026-07-25 #5). An ADD
 * sweeps warm, bright metal about to exist. A CUT sweeps the same volume but
 * inverts the read into a VOID: only the cavity's BACK walls are drawn (you
 * look into the pocket, not at a body's near face) and they are shaded cold and
 * DARK — a hole in aluminum is a shadow, not a highlight. A cut preview
 * therefore never paints a proud solid where Save will leave a pocket: the
 * picture cannot contradict the result.
 *
 * Every color/opacity is a token; GPU resources are disposed on change/unmount;
 * the depth is lightly debounced so a fast typist doesn't rebuild the mesh on
 * every intermediate keystroke.
 */
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import {
  BufferGeometry,
  EdgesGeometry,
  ExtrudeGeometry,
  LineBasicMaterial,
  MeshMatcapMaterial,
  Path,
  Shape,
  Vector2,
} from "three";

import type { ExtrudeDirection, ExtrudeOperation } from "../features/extrude";
import type { SolvedSketchLayer } from "./SketchScene";
import { extrudeGhostAppearance, extrudeGhostPose } from "./extrudeGhost";
import { profileRegions } from "./profileLoops";
import { studioMatcap } from "./studioMatcap";

export interface ExtrudePreviewProps {
  /** The profile sketch to sweep (solved entities on its resolved basis). */
  layer: SolvedSketchLayer;
  /** The editor's current distance in canonical mm (always positive). */
  distanceMm: number;
  /** Sweep sense along the plane normal. */
  direction: ExtrudeDirection;
  /**
   * What Save will do with the swept volume. `"add"` draws metal about to
   * exist; `"cut"` draws the void it will remove — never a solid.
   */
  operation: ExtrudeOperation;
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
  operation,
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

  // How this operation is shaded — the pure seam below the renderer, so "a cut
  // never reads as added metal" is unit-testable without a GPU.
  const appearance = useMemo(
    () => extrudeGhostAppearance(operation),
    [operation],
  );

  const edges = useMemo(
    () => geometries.map((geometry) => new EdgesGeometry(geometry, 25)),
    [geometries],
  );

  // Orient local plane space onto the sketch basis — the pure seam beside the
  // appearance one, so "the ghost sits ON the plane it was drawn on" is a node
  // assertion rather than something only a browser can see (FB-7c).
  const { position, quaternion } = useMemo(
    () => extrudeGhostPose(layer.basis),
    [layer.basis],
  );

  // ADD paints warm, bright metal about to exist; CUT paints the void it
  // removes — the cavity's far walls only (BackSide), shaded cold and dark, so
  // the ghost reads as a hole rather than a body. Every value is a token.
  //
  // `depthTest: false` — the ghost is an X-RAY, and it has to be. The swept
  // volume of the interesting operations lies INSIDE the body: a pocket cut
  // into a plate is entirely under its top face, and so is a boss added into
  // existing material. With depth testing on, the one preview a modeler most
  // needs — "which way does this cut go, and where does it land?" (FB-4) — is
  // occluded by the very solid it is about to change, and the viewport is
  // edit-blind exactly when it matters.
  //
  // This was hidden until FB-7c. The ghost used to be drawn from a basis in the
  // kernel's Z-up frame while the scene renders Y-up, so it stood 90° off the
  // body and was visible for the wrong reason — floating in mid-air beside the
  // part rather than showing through it. Fixing the frame put it where it
  // belongs and revealed that the depth read had never been decided.
  const surfaceMaterial = useMemo(() => {
    const material = new MeshMatcapMaterial({ matcap: studioMatcap() });
    material.color.set(appearance.surfaceTint);
    material.transparent = true;
    material.opacity = appearance.surfaceOpacity;
    material.depthWrite = false;
    material.depthTest = false;
    material.side = appearance.surfaceSide;
    return material;
  }, [appearance]);
  const edgeMaterial = useMemo(() => {
    const material = new LineBasicMaterial({ color: appearance.edgeColor });
    material.transparent = true;
    material.opacity = appearance.edgeOpacity;
    material.depthWrite = false;
    material.depthTest = false;
    return material;
  }, [appearance]);

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
