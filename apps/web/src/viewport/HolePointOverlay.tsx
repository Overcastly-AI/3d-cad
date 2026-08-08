/**
 * The hole PLACEMENT overlay inside the WebGL viewport — where the drill point
 * is, what frame its coordinates are in, and every point on the face worth
 * snapping to.
 *
 * Two layers, and they answer different questions:
 *
 *   THE FRAME (always, once a face is chosen). A datum crosshair drawn ON the
 *   face at the origin of the X/Y cells in the editor, with its axes labelled.
 *   It is drawn in the resting datum-plane ink the sketcher already uses for a
 *   reference it is not addressing, and it is the answer to "what does 0, 0 mean on this
 *   face" — asked on screen instead of in a tooltip, because an X/Y entry whose
 *   origin is invisible is exactly how a ring came out 0.065 mm eccentric to a
 *   motor register (QA-REVIEW 2026-08-01, QA3-2). The live drill point takes the
 *   brass, so typing a coordinate MOVES a mark you can watch.
 *
 *   THE PLACEMENT (while the point pick is armed). The FACE ITSELF is the
 *   target: a raycast against the drawn surface accepts hits on the placement
 *   face, projects the hit back onto the face plane and drills there (SEL-4,
 *   spec A2). This is the one part of SEL-4 that changes what a click DOES, and
 *   it is the honest fix rather than a wider dot: a `PickNode` is already a
 *   ~12 px proximity test around a projected point, so converting the hit-test
 *   alone would buy nothing. Free placement is what makes a dense bolt pattern
 *   placeable at all, and it is what Fusion does.
 *
 *   THE SNAPS. Every point guaranteed on the face keeps a DOM-in-canvas
 *   `PickNode` (drei `Html`) — the same affordance the measurement overlay
 *   places at every vertex, so picking is keyboard-navigable, screen-reader
 *   named and e2e-drivable. Three kinds: the face CENTRE (its area centroid),
 *   the face's own corner VERTICES, and the CENTRE of every circular edge lying
 *   in the face's plane, which is what makes concentric and bolt-circle
 *   placement possible: snap a bore centre, read its coordinates in the cells,
 *   dial the pitch circle from there.
 *
 *   SNAP BEATS FREE PLACEMENT BY MECHANISM, not by a second radius test. A
 *   `PickNode` lives in a drei `Html` layer ABOVE the canvas, so a pointer
 *   within its 24 px target is consumed by the DOM and the raycast never runs —
 *   the snap wins exactly where a snap should win, and the bore centre is
 *   echoed at full precision instead of at whatever pixel was under the cursor.
 *   That is also why the snap nodes now `recede`: they are secondary to the
 *   surface, the way `FacePickOverlay`'s marks became secondary in A2.
 *
 * Presentational: the parent owns the position state and the resulting param
 * write. Geometry comes from `../features/facePlacement` (one frame, shared with
 * the editor's cells — never a second private basis here).
 */
import { formatLength, PickNode } from "@loft/design";
import { sketch, viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { OverlayEdge } from "../api/measure";
import type { OverlayFace, PlanarFaceSignature, Vec3 } from "../api/parts";
import { faceSignatureKey, isPickableFace } from "../features/face";
import { coplanarVertexIndices, samePoint } from "../features/hole";
import {
  facePlacement,
  toFacePoint,
  toWorldPoint,
  type FaceFrame,
} from "../features/facePlacement";
import { formatVec3Mm, occtToScene } from "../measure/geometry";
import { sceneToOcctTuple } from "../sketch/plane";
import { Segments } from "./overlaySegments";
import { PickSurface } from "./pickSurface";
import { useViewportPickStamp } from "./pickStamp";

export interface HolePointOverlayProps {
  /** The picked placement face's signature, or null before a face is chosen. */
  signature: PlanarFaceSignature | null;
  /**
   * The evaluated body's B-rep faces, or null. Only used to resolve the
   * placement face's ORDINAL, which is what a raycast reports — matching on the
   * signature rather than carrying a second copy of the index keeps this
   * overlay's input the same one the editor already holds.
   */
  faces: readonly OverlayFace[] | null;
  /** The evaluated body's B-rep vertices (from the overlay), or null. */
  vertices: readonly Vec3[] | null;
  /** The evaluated body's B-rep edges (from the overlay), or null. */
  edges: readonly OverlayEdge[] | null;
  /** The current drill position (world mm), or null — drives the selected cue. */
  position: Vec3 | null;
  /** True while the POINT pick is armed — the snap nodes are live. */
  armed: boolean;
  /** Echo a picked world-space point up as the drill position. */
  onPick: (point: Vec3) => void;
}

/** Add a world-space segment `a → b` to a scene-space position buffer. */
function pushSegment(out: number[], a: Vec3, b: Vec3): void {
  out.push(...occtToScene(a), ...occtToScene(b));
}

/** `origin + u·x + v·y` for a frame, in world mm. */
function at(frame: FaceFrame, from: Vec3, x: number, y: number): Vec3 {
  return {
    x: from.x + frame.u.x * x + frame.v.x * y,
    y: from.y + frame.u.y * x + frame.v.y * y,
    z: from.z + frame.u.z * x + frame.v.z * y,
  };
}

export function HolePointOverlay({
  signature,
  faces,
  vertices,
  edges,
  position,
  armed,
  onPick,
}: HolePointOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);
  /** The free-placement point under the cursor (world mm), or null. */
  const [hoverPoint, setHoverPoint] = useState<Vec3 | null>(null);

  // frameloop="demand": redraw when the pickable set or the placement changes.
  useEffect(() => {
    invalidate();
  }, [signature, vertices, edges, position, armed, hoverPoint, invalidate]);

  // A disarmed pick offers no free placement, so it shows no candidate.
  useEffect(() => {
    if (!armed) setHoverPoint(null);
  }, [armed]);

  // The face's own corners (overlay vertices coplanar with the face plane) —
  // the snap points besides the centre. Empty until the overlay loads.
  const cornerIndices = useMemo(
    () =>
      signature === null || vertices === null
        ? []
        : coplanarVertexIndices(signature, vertices),
    [signature, vertices],
  );

  // The frame + the circular edges in the face's plane. THE same computation
  // the editor's coordinate cells run — one basis, two renderers.
  const placement = useMemo(
    () => (signature === null ? null : facePlacement(signature, edges)),
    [signature, edges],
  );

  // Arm length scaled off the face, so the datum reads at any part size.
  const armMm =
    signature === null ? 0 : Math.max(Math.sqrt(signature.area_mm2) * 0.3, 1);

  const framePositions = useMemo(() => {
    if (placement === null) return new Float32Array(0);
    const { frame } = placement;
    const o = frame.origin;
    const stub = armMm * 0.12;
    const out: number[] = [];
    pushSegment(out, at(frame, o, -stub, 0), at(frame, o, armMm, 0));
    pushSegment(out, at(frame, o, 0, -stub), at(frame, o, 0, armMm));
    return Float32Array.from(out);
  }, [placement, armMm]);

  const pointPositions = useMemo(() => {
    if (placement === null || position === null) return new Float32Array(0);
    const { frame } = placement;
    const r = armMm * 0.24;
    const out: number[] = [];
    pushSegment(out, at(frame, position, -r, 0), at(frame, position, r, 0));
    pushSegment(out, at(frame, position, 0, -r), at(frame, position, 0, r));
    return Float32Array.from(out);
  }, [placement, position, armMm]);

  /** The candidate crosshair under the cursor — smaller than the live one. */
  const hoverPositions = useMemo(() => {
    if (placement === null || hoverPoint === null) return new Float32Array(0);
    const { frame } = placement;
    const r = armMm * 0.16;
    const out: number[] = [];
    pushSegment(out, at(frame, hoverPoint, -r, 0), at(frame, hoverPoint, r, 0));
    pushSegment(out, at(frame, hoverPoint, 0, -r), at(frame, hoverPoint, 0, r));
    return Float32Array.from(out);
  }, [placement, hoverPoint, armMm]);

  /**
   * The placement face's B-rep ordinal — what a raycast reports. Resolved by
   * matching the signature the editor already holds, so there is no second copy
   * of the index to drift.
   */
  const placementOrdinal = useMemo(() => {
    if (signature === null || faces === null) return null;
    const key = faceSignatureKey(signature);
    const match = faces.find(
      (face) =>
        isPickableFace(face) && faceSignatureKey(face.signature) === key,
    );
    return match?.index ?? null;
  }, [signature, faces]);

  /**
   * A raycast hit → the drill point, or null.
   *
   * Only the PLACEMENT face answers. A hit on any other face — including a
   * coplanar one — is refused rather than projected onto the plane anyway: the
   * hole is resolved against this face, so drilling at a point the modeller
   * addressed on a different one would be a pick acting on geometry nobody
   * chose. The hit is projected onto the face plane regardless, which costs
   * nothing and kills the float error the scene round trip introduces.
   */
  const pointAt = useCallback(
    (
      ordinal: number | null,
      hit: { point: { x: number; y: number; z: number } },
    ): Vec3 | null => {
      if (placement === null || placementOrdinal === null) return null;
      if (ordinal !== placementOrdinal) return null;
      const [x, y, z] = sceneToOcctTuple([
        hit.point.x,
        hit.point.y,
        hit.point.z,
      ]);
      const world: Vec3 = { x, y, z };
      return toWorldPoint(placement.frame, toFacePoint(placement.frame, world));
    },
    [placement, placementOrdinal],
  );

  const onSurfaceMove = useCallback(
    (
      ordinal: number | null,
      event: { point: { x: number; y: number; z: number } },
    ) => {
      setHoverPoint(pointAt(ordinal, event));
    },
    [pointAt],
  );

  const onSurfaceClick = useCallback(
    (
      ordinal: number | null,
      event: {
        point: { x: number; y: number; z: number };
        stopPropagation: () => void;
      },
    ) => {
      const point = pointAt(ordinal, event);
      if (point === null) return;
      event.stopPropagation();
      onPick(point);
    },
    [pointAt, onPick],
  );

  /** QA hook: is the armed point pick addressing the placement face? */
  useViewportPickStamp(
    "holePointHover",
    armed && hoverPoint !== null ? 1 : null,
  );

  if (signature === null || placement === null) return null;

  const { frame, circles } = placement;
  const centroid = signature.centroid;
  // A datum label has to stay legible over BOTH the light machined body and the
  // dark ground — the same problem `PickNode` solves with its two-tone reticle,
  // and a line layer cannot carry a halo. So the letters ride a small ground
  // chip, which is also the drafting/triad idiom.
  const labelClass =
    "pointer-events-none select-none rounded-sm bg-carbide/80 px-0.5 font-display text-2xs uppercase tracking-[0.14em] text-mist";

  return (
    <group>
      {/* The datum + the live point. `depthTest={false}`: the placement face is
          as often as not the one turned AWAY from the camera (a back plate is
          drilled from behind), and an annotation of the ACTIVE command that
          hides inside the part would be worse than none — the same posture the
          DOM pick nodes already take. */}
      <Segments
        positions={framePositions}
        color={sketch.planeEdge}
        depthTest={false}
        renderOrder={3}
      />
      <Segments
        positions={pointPositions}
        color={viewport.selection}
        depthTest={false}
        renderOrder={4}
      />
      {/* The free-placement candidate under the cursor. Without it the raycast
          would land invisibly — the modeller would learn where the drill went
          only after clicking, which is the failure mode the snap dots at least
          did not have. */}
      <Segments
        positions={hoverPositions}
        color={viewport.hover}
        depthTest={false}
        renderOrder={4}
      />

      {/* The frame's zero and its axis letters — what the X/Y cells count from. */}
      <Html
        position={occtToScene(frame.origin)}
        center
        zIndexRange={[34, 16]}
        pointerEvents="none"
      >
        <span
          aria-hidden
          data-testid="hole-frame-origin"
          className={`${labelClass} block translate-x-4 translate-y-4`}
        >
          0,0
        </span>
      </Html>
      <Html
        position={occtToScene(at(frame, frame.origin, armMm, 0))}
        center
        zIndexRange={[34, 16]}
        pointerEvents="none"
      >
        <span aria-hidden className={`${labelClass} block`}>
          X
        </span>
      </Html>
      <Html
        position={occtToScene(at(frame, frame.origin, 0, armMm))}
        center
        zIndexRange={[34, 16]}
        pointerEvents="none"
      >
        <span aria-hidden className={`${labelClass} block`}>
          Y
        </span>
      </Html>

      {armed ? (
        <>
          {/* FREE PLACEMENT: the placement face itself is the target. */}
          <PickSurface
            onMove={onSurfaceMove}
            onOut={() => setHoverPoint(null)}
            onClick={onSurfaceClick}
          />

          {/* The face centre — the seed placement (a hole in the middle). */}
          <Html position={occtToScene(centroid)} center zIndexRange={[36, 18]}>
            <PickNode
              shape="vertex"
              // A7's recession: the face itself is the placement target now, so
              // the snap marks are secondary — they are exact, not primary.
              recede
              selected={samePoint(position, centroid)}
              data-testid="hole-point-center"
              aria-label={`Centre of the face at ${formatVec3Mm(centroid)} millimetres`}
              onClick={() => onPick(centroid)}
            />
          </Html>

          {/* The face's corners — snap the drill onto a vertex of the face. */}
          {cornerIndices.map((index) => {
            const vertex = vertices?.[index];
            if (vertex === undefined) return null;
            return (
              <Html
                key={`hp${index}`}
                position={occtToScene(vertex)}
                center
                zIndexRange={[35, 17]}
              >
                <PickNode
                  shape="vertex"
                  recede
                  selected={samePoint(position, vertex)}
                  data-testid={`hole-point-vertex-${index}`}
                  aria-label={`Corner at ${formatVec3Mm(vertex)} millimetres`}
                  onClick={() => onPick(vertex)}
                />
              </Html>
            );
          })}

          {/* Circular-edge centres — concentric and bolt-circle placement. */}
          {circles.map((circle, index) => (
            <Html
              key={`hc${index}`}
              position={occtToScene(circle.center)}
              center
              zIndexRange={[36, 18]}
            >
              <PickNode
                shape="center"
                recede
                selected={samePoint(position, circle.center)}
                data-testid={`hole-point-circle-${index}`}
                data-diameter-mm={circle.radiusMm * 2}
                aria-label={`Centre of the Ø${formatLength(circle.radiusMm * 2, "mm")} circle at ${formatVec3Mm(circle.center)} millimetres`}
                onClick={() => onPick(circle.center)}
              />
            </Html>
          ))}
        </>
      ) : null}
    </group>
  );
}
