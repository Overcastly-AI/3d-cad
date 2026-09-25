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
 * the depth is lightly throttled so a fast typist (or a dragged handle) does not
 * rebuild the mesh on every intermediate value.
 */
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  type BufferGeometry,
  LineBasicMaterial,
  MeshMatcapMaterial,
} from "three";

import {
  MAX_TWIST_DEG,
  type ExtrudeDirection,
  type ExtrudeOperation,
} from "../features/extrude";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { SolvedSketchLayer } from "./SketchScene";
import { twistGaugeTrack } from "./axisAnchorGauge";
import { ExtrudeDragHandle } from "./ExtrudeDragHandle";
import {
  buildGhostRegion,
  extrudeGhostAppearance,
  extrudeGhostPose,
  twistArcSeat,
} from "./extrudeGhost";
import { ANNOTATION_LAYER } from "./instruments";
import { ParametricGauge } from "./ParametricGauge";
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
  /**
   * Set the distance by DIRECT MANIPULATION (T-23). When present, the ghost
   * grows a depth gauge you can drag; the editor's numeric field stays the
   * exact path and both drive this one value. Absent = a ghost with no handle,
   * which is what every caller had before and what a read-only preview wants.
   */
  onDepthChange?: (mm: number) => void;
  /**
   * Signed twist over the whole distance, degrees (helical-gear gap G1); 0 or
   * absent is a straight prism. The ghost turns the way Save will: right-handed
   * about the direction of travel, about `twistCentre`.
   */
  twistDeg?: number;
  /** The twist axis's sketch point; null or absent is the sketch origin. */
  twistCentre?: { x: number; y: number } | null;
  /**
   * Set the twist by DIRECT MANIPULATION: an arc on the far cap, the Twist
   * field's drag handle (contract β, like `onDepthChange`). Absent = no arc.
   */
  onTwistChange?: (deg: number) => void;
}

/** Rebuild the ghost mesh at most this often while the distance changes. */
const PREVIEW_REBUILD_MS = 70;

/**
 * Rate-limit a numeric value so a fast input does not thrash the geometry
 * rebuild — a THROTTLE, not a debounce, and the difference is the whole point.
 *
 * A trailing debounce resets its timer on every change, so under CONTINUOUS
 * input it never fires at all: the ghost simply stopped following while the
 * depth handle was being dragged, and only caught up when the pointer paused.
 * Nobody noticed while the only input was a keyboard, where every keystroke is
 * followed by a gap longer than the window. Direct manipulation has no gaps —
 * it is the input this preview was always for, and it is the one the debounce
 * could not serve. Found in a founder capture: a 28 mm readout over a 10 mm
 * ghost.
 *
 * A throttle bounds the rebuild RATE (one per window) while guaranteeing the
 * picture is never more than one window behind the pointer.
 */
function useThrottled(value: number, ms: number): number {
  const [settled, setSettled] = useState(value);
  const lastAt = useRef(0);
  useEffect(() => {
    const wait = Math.max(0, ms - (performance.now() - lastAt.current));
    const timer = window.setTimeout(() => {
      lastAt.current = performance.now();
      setSettled(value);
    }, wait);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function ExtrudePreview({
  layer,
  distanceMm,
  direction,
  operation,
  onDepthChange,
  twistDeg = 0,
  twistCentre = null,
  onTwistChange,
}: ExtrudePreviewProps) {
  const invalidate = useThree((state) => state.invalidate);
  const unit = useDocumentLengthUnit();
  const depth = useThrottled(distanceMm, PREVIEW_REBUILD_MS);
  // Throttled like the depth, for the depth's reason: the twist arc is dragged.
  const twist = useThrottled(twistDeg, PREVIEW_REBUILD_MS);
  const centreX = twistCentre?.x ?? 0;
  const centreY = twistCentre?.y ?? 0;

  // The profile → solid regions depend only on the geometry, not the depth.
  const regions = useMemo(() => profileRegions(layer.entities), [layer]);

  // One extruded BufferGeometry per region, in local plane (u,v,+normal) space,
  // and the ink over each.
  const { geometries, edges } = useMemo<{
    geometries: BufferGeometry[];
    edges: BufferGeometry[];
  }>(() => {
    if (depth <= 0) return { geometries: [], edges: [] };
    // The build (rings, a vertex budget, ink found on a one-step prism, the
    // twist) is the pure seam in `extrudeGhost`, so its cost is a node test.
    const built = regions.map((region) =>
      buildGhostRegion(region, depth, direction, twist, {
        x: centreX,
        y: centreY,
      }),
    );
    return {
      geometries: built.map((b) => b.mesh),
      edges: built.map((b) => b.edges),
    };
  }, [regions, depth, direction, twist, centreX, centreY]);

  // The twist arc's seat and track, from the LIVE depth (the depth gauge's
  // reason: the arc stays on the cap under the pointer, not a frame behind).
  const twistSeat = useMemo(
    () =>
      onTwistChange === undefined
        ? null
        : twistArcSeat(
            layer.basis,
            regions,
            { x: centreX, y: centreY },
            distanceMm,
            direction,
          ),
    [
      onTwistChange,
      layer.basis,
      regions,
      centreX,
      centreY,
      distanceMm,
      direction,
    ],
  );
  const twistTrack = useMemo(
    () => (twistSeat === null ? null : twistGaugeTrack(twistSeat)),
    [twistSeat],
  );

  // How this operation is shaded — the pure seam below the renderer, so "a cut
  // never reads as added metal" is unit-testable without a GPU.
  const appearance = useMemo(
    () => extrudeGhostAppearance(operation),
    [operation],
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

  // The GAUGE is deliberately outside the ghost's own transform: it works in
  // scene coordinates (that is the frame a pointer ray arrives in), and it is
  // driven by the LIVE distance rather than the debounced one, so the arrow
  // stays under the cursor while the swept mesh catches up a frame later.
  return (
    <>
      {geometries.length > 0 ? (
        <group name="extrude-ghost" position={position} quaternion={quaternion}>
          {geometries.map((geometry, i) => (
            <mesh key={i} geometry={geometry} material={surfaceMaterial} />
          ))}
          {edges.map((edge, i) => (
            <lineSegments key={i} geometry={edge} material={edgeMaterial} />
          ))}
        </group>
      ) : null}
      {onDepthChange !== undefined ? (
        <ExtrudeDragHandle
          basis={layer.basis}
          regions={regions}
          depthMm={distanceMm}
          direction={direction}
          unit={unit}
          onDepthChange={onDepthChange}
        />
      ) : null}
      {onTwistChange !== undefined && twistTrack !== null ? (
        // An ANNOTATION to the proposal, not part of it. The arc stands a fifth
        // outside the profile's reach from the twist axis, so counted in the
        // proposal box it grew the box past the body on every open extrude,
        // even at twist 0, and CRAFT-12's keep-in-frame watch re-fitted the
        // camera ("fit-proposal") when nothing had been proposed
        // (viewport-makeover:129). The ghost it turns IS the proposal, and it
        // is already in the box.
        <group userData={ANNOTATION_LAYER}>
          <ParametricGauge
            label="Extrude twist"
            tagLabel="T"
            gaugeId="extrude-twist"
            value={twistDeg}
            onChange={onTwistChange}
            track={twistTrack}
            min={-MAX_TWIST_DEG}
            max={MAX_TWIST_DEG}
            // No `tagUnit`: the angle wears its degree sign (`formatAngle`).
          />
        </group>
      ) : null}
    </>
  );
}
