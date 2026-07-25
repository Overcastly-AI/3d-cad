/**
 * The face-pick overlay inside the WebGL viewport — the "Pick a face" step of
 * the sketch plane picker. Every PLANAR face of the current body gets a
 * DOM-in-canvas `PickNode` (drei `Html`) at its area centroid, so picking is
 * keyboard-navigable, screen-reader named, and e2e-drivable (the same posture
 * as the measurement overlay). Non-planar faces carry no signature and are NOT
 * pickable in v1 — they are omitted, never a dead target.
 *
 * The pick reads as TOPOLOGY, not a blanket of floating squares (UI audit
 * #19a): the face under the cursor (hovered) — or the one currently armed —
 * also gets a translucent brass patch laid ON its plane (built from the
 * signature's centroid + normal + area), so the highlight is the real surface,
 * cursor-driven. Every color/opacity comes from `@loft/design` tokens.
 *
 * A clicked face echoes its stage-1 `signature` into an `on_face` datum (the
 * parent owns that write + the sketch seating); this layer is presentational.
 */
import { PickNode } from "@loft/design";
import { viewport } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import { DoubleSide, Quaternion, Vector3 } from "three";

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

/** +Z (a circle's rest normal) → the face's scene-space normal. */
const REST_NORMAL = new Vector3(0, 0, 1);

/** A translucent disc laid on a planar face's plane — the topology highlight. */
function FacePatch({
  signature,
  selected,
}: {
  signature: PlanarFaceSignature;
  selected: boolean;
}) {
  const { position, quaternion, radius } = useMemo(() => {
    const pos = occtToScene(signature.centroid);
    // The normal is a DIRECTION — the OCCT→scene map is a pure rotation, so the
    // same point transform carries it (no translation term).
    const n = occtToScene(signature.normal);
    const sceneNormal = new Vector3(n[0], n[1], n[2]).normalize();
    const quat = new Quaternion().setFromUnitVectors(REST_NORMAL, sceneNormal);
    // Area-equivalent disc — a plane-lying patch that reads as "this face".
    const r = Math.max(
      Math.sqrt(Math.max(signature.area_mm2, 0) / Math.PI),
      0.5,
    );
    return {
      position: new Vector3(pos[0], pos[1], pos[2]),
      quaternion: quat,
      radius: r,
    };
  }, [signature]);

  return (
    <mesh position={position} quaternion={quaternion}>
      <circleGeometry args={[radius, 48]} />
      <meshBasicMaterial
        color={selected ? viewport.facePick.selected : viewport.facePick.hover}
        transparent
        opacity={
          selected
            ? viewport.facePick.selectedOpacity
            : viewport.facePick.hoverOpacity
        }
        side={DoubleSide}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}

export function FacePickOverlay({
  faces,
  onPick,
  pendingIndex,
}: FacePickOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);
  const [hovered, setHovered] = useState<number | null>(null);

  // frameloop="demand": redraw when the pickable set / pending / hover changes.
  useEffect(() => {
    invalidate();
  }, [faces, pendingIndex, hovered, invalidate]);

  // Drop a stale hover when the pickable set changes out from under it.
  useEffect(() => {
    setHovered(null);
  }, [faces]);

  if (faces === null) return null;

  return (
    <group>
      {faces.map((face) =>
        isPickableFace(face) ? (
          <group key={`f${face.index}`}>
            {pendingIndex === face.index || hovered === face.index ? (
              <FacePatch
                signature={face.signature}
                selected={pendingIndex === face.index}
              />
            ) : null}
            <Html
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
                onPointerOver={() => setHovered(face.index)}
                onPointerOut={() =>
                  setHovered((h) => (h === face.index ? null : h))
                }
                onFocus={() => setHovered(face.index)}
                onBlur={() => setHovered((h) => (h === face.index ? null : h))}
              />
            </Html>
          </group>
        ) : null,
      )}
    </group>
  );
}
