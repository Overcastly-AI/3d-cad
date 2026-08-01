/**
 * The hole point-pick overlay inside the WebGL viewport — the "Pick a point on
 * the face" step of the Hole command. Once a placement face is chosen, its
 * snappable points get a DOM-in-canvas `PickNode` (drei `Html`), the SAME
 * point affordance the measurement overlay places at every vertex — so picking
 * is keyboard-navigable, screen-reader named, and e2e-drivable.
 *
 * Two point kinds are offered, both guaranteed ON the face: the face CENTRE (its
 * area centroid — the everyday "hole in the middle" seed) and each of the face's
 * own corner VERTICES (the overlay vertices coplanar with the face). A click
 * echoes the world-space point up; the geometry service projects it onto the
 * face plane to fix the drill axis. This layer is presentational — the parent
 * owns the position state + the resulting param write.
 */
import { PickNode } from "@loft/design";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";

import type { PlanarFaceSignature, Vec3 } from "../api/parts";
import { coplanarVertexIndices, samePoint } from "../features/hole";
import { formatVec3Mm, occtToScene } from "../measure/geometry";

export interface HolePointOverlayProps {
  /** The picked placement face's signature, or null before a face is chosen. */
  signature: PlanarFaceSignature | null;
  /** The evaluated body's B-rep vertices (from the overlay), or null. */
  vertices: readonly Vec3[] | null;
  /** The current drill position (world mm), or null — drives the selected cue. */
  position: Vec3 | null;
  /** Echo a picked world-space point up as the drill position. */
  onPick: (point: Vec3) => void;
}

export function HolePointOverlay({
  signature,
  vertices,
  position,
  onPick,
}: HolePointOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the pickable set or selection changes.
  useEffect(() => {
    invalidate();
  }, [signature, vertices, position, invalidate]);

  // The face's own corners (overlay vertices coplanar with the face plane) —
  // the snap points besides the centre. Empty until the overlay loads.
  const cornerIndices = useMemo(
    () =>
      signature === null || vertices === null
        ? []
        : coplanarVertexIndices(signature, vertices),
    [signature, vertices],
  );

  if (signature === null) return null;

  const centroid = signature.centroid;

  return (
    <group>
      {/* The face centre — the seed placement (a hole in the middle). */}
      <Html position={occtToScene(centroid)} center zIndexRange={[36, 18]}>
        <PickNode
          shape="vertex"
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
              selected={samePoint(position, vertex)}
              data-testid={`hole-point-vertex-${index}`}
              aria-label={`Corner at ${formatVec3Mm(vertex)} millimetres`}
              onClick={() => onPick(vertex)}
            />
          </Html>
        );
      })}
    </group>
  );
}
