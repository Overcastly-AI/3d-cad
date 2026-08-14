/**
 * THE FACE HIGHLIGHT — a translucent disc laid ON a planar face's plane, built
 * from the face signature's centroid + normal + area.
 *
 * It exists so a face pick reads as TOPOLOGY rather than as a blanket of
 * floating squares (UI audit #19a): the face under the cursor, or the one
 * already armed, is drawn as the real surface. Every colour and opacity comes
 * from the `viewport.facePick` tokens, so the DOM and the WebGL viewport share
 * one selection palette (CLAUDE.md DRY rule).
 *
 * Extracted from `FacePickOverlay` when SEL-4 converted the other face picks to
 * a surface raycast: `ShellFaceOverlay` and `InstanceMateOverlay` had NO
 * topology highlight at all, and a raycast with no hover feedback is worse than
 * a dot — the dot at least told you where the target was. So the patch ships
 * with each conversion, from one implementation rather than three.
 */
import { viewport } from "@loft/design/tokens";
import { useMemo } from "react";
import { DoubleSide, Quaternion, Vector3 } from "three";

import type { PlanarFaceSignature } from "../api/parts";
import { occtToScene } from "../measure/geometry";

/** +Z (a circle's rest normal) → the face's scene-space normal. */
const REST_NORMAL = new Vector3(0, 0, 1);

export interface FacePatchProps {
  signature: PlanarFaceSignature;
  /** Armed/picked (brass fill) rather than merely hovered. */
  selected: boolean;
}

/** A translucent disc laid on a planar face's plane — the topology highlight. */
export function FacePatch({ signature, selected }: FacePatchProps) {
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
