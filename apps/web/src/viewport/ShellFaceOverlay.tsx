/**
 * The shell face-pick overlay inside the WebGL viewport — the face-pick step of
 * the ShellEditor. Every PLANAR face of the current body gets a DOM-in-canvas
 * `PickNode` (drei `Html`) at its area centroid, so picking is keyboard-
 * navigable, screen-reader named, and e2e-drivable — the same posture as the
 * sketch-on-face overlay. Clicking TOGGLES that face into the "open" set; the
 * shell then leaves ONLY those faces open (empty set = a sealed hollow).
 *
 * Unlike the single-select sketch-on-face picker (`FacePickOverlay`), this is a
 * store-driven MULTI-select set (the edge picker's posture), keyed by full-
 * precision `PlanarFaceSignature` — never the transient overlay index — so a
 * refetch never mismarks a pick. Selected faces take the brass fill (the app's
 * selection language); the parent store owns the picked set + hover.
 */
import { PickNode } from "@loft/design";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";

import { faceLabel, faceSignatureKey, isPickableFace } from "../features/face";
import { useFacePickStore } from "../features/facePickStore";
import { occtToScene } from "../measure/geometry";

export interface ShellFaceOverlayProps {
  /**
   * Prefix for each pick node's `data-testid` (e.g. `shell-face` → `shell-face-3`).
   * The shell and draft editors share this ONE store-driven overlay (only one is
   * ever open), so QA drives each by its own prefix. Defaults to `shell-face`.
   */
  testIdPrefix?: string;
}

export function ShellFaceOverlay({
  testIdPrefix = "shell-face",
}: ShellFaceOverlayProps = {}) {
  const overlay = useFacePickStore((s) => s.overlay);
  const picked = useFacePickStore((s) => s.picked);
  const hoverFace = useFacePickStore((s) => s.hoverFace);
  const toggle = useFacePickStore((s) => s.toggle);
  const setHoverFace = useFacePickStore((s) => s.setHoverFace);
  const invalidate = useThree((s) => s.invalidate);

  // frameloop="demand": redraw when the pick/hover set changes.
  useEffect(() => {
    invalidate();
  }, [overlay, picked, hoverFace, invalidate]);

  const pickedKeys = useMemo(
    () => new Set(picked.map(faceSignatureKey)),
    [picked],
  );

  if (overlay === null) return null;

  return (
    <group>
      {overlay.faces.map((face) =>
        isPickableFace(face) ? (
          <Html
            key={`f${face.index}`}
            position={occtToScene(face.signature.centroid)}
            center
            zIndexRange={[30, 10]}
          >
            <PickNode
              shape="face"
              selected={pickedKeys.has(faceSignatureKey(face.signature))}
              data-testid={`${testIdPrefix}-${face.index}`}
              aria-label={faceLabel(face.index, face.signature)}
              onClick={() => toggle(face.signature)}
              onPointerOver={() => setHoverFace(face.index)}
              onPointerOut={() => setHoverFace(null)}
              onFocus={() => setHoverFace(face.index)}
              onBlur={() => setHoverFace(null)}
            />
          </Html>
        ) : null,
      )}
    </group>
  );
}
