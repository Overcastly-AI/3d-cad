/**
 * The face-pick overlay inside the WebGL viewport — the "Pick a face" step of
 * the sketch plane picker. Every PLANAR face of the current body gets a
 * DOM-in-canvas `PickNode` (drei `Html`) at its area centroid, so picking is
 * keyboard-navigable, screen-reader named, and e2e-drivable (the same posture
 * as the measurement overlay). Non-planar faces carry no signature and are NOT
 * pickable in v1 — they are omitted, never a dead target.
 *
 * A clicked face echoes its stage-1 `signature` into an `on_face` datum (the
 * parent owns that write + the sketch seating); this layer is presentational.
 */
import { PickNode } from "@loft/design";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect } from "react";

import type { OverlayFace, PlanarFaceSignature } from "../api/parts";
import { faceLabel, isPickableFace } from "../features/face";
import { occtToScene } from "../measure/geometry";

export interface FacePickOverlayProps {
  /** The evaluated body's faces (from `OverlayResult.faces`), or null. */
  faces: readonly OverlayFace[] | null;
  /** Author an `on_face` datum from the picked face and seat the sketch. */
  onPick: (face: OverlayFace & { signature: PlanarFaceSignature }) => void;
  /** The `body.faces()` index currently being authored (brass-fill busy cue). */
  pendingIndex: number | null;
}

export function FacePickOverlay({
  faces,
  onPick,
  pendingIndex,
}: FacePickOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the pickable set or pending state changes.
  useEffect(() => {
    invalidate();
  }, [faces, pendingIndex, invalidate]);

  if (faces === null) return null;

  return (
    <group>
      {faces.map((face) =>
        isPickableFace(face) ? (
          <Html
            key={`f${face.index}`}
            position={occtToScene(face.signature.centroid)}
            center
            zIndexRange={[30, 10]}
          >
            <PickNode
              shape="face"
              selected={pendingIndex === face.index}
              data-testid={`plane-pick-face-${face.index}`}
              aria-label={faceLabel(face.index, face.signature)}
              onClick={() => onPick(face)}
            />
          </Html>
        ) : null,
      )}
    </group>
  );
}
