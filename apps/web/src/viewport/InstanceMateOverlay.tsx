/**
 * Per-instance mate-pick overlay — the "pick the mating geometry" step of mate
 * authoring, reusing the SAME `PickNode` + `Html` machinery as the sketch-on-
 * face / edge-pick overlays (CLAUDE.md DRY rule). The overlay rides the
 * instance's SOLVED scene transform, so its pick nodes sit on the rendered
 * instance; the geometry comes from the PART's own `/overlay` (local frame),
 * and each picked signature passes through UNCHANGED into the mate ref (the
 * backend resolves it against that instance's local part body).
 *
 * Coincident wants PLANAR faces (each carries a `PlanarFaceSignature`);
 * concentric wants CIRCULAR edges (each a circle `EdgeSignature` → an axis).
 */
import { PickNode } from "@loft/design";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect } from "react";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import type { OverlayResult } from "../api/measure";
import { occtPointToScene, type SceneTransform } from "../assembly/placement";
import { isPickableFace, faceLabel } from "../features/face";
import { polylineMidpoint } from "../measure/geometry";

export interface InstanceMateOverlayProps {
  instanceId: string;
  /** The instance's solved scene transform (the pick nodes ride it). */
  transform: SceneTransform;
  /** Which geometry to offer: planar faces (coincident) or axes (concentric). */
  tool: "coincident" | "concentric";
  /** The part's pickable overlay (faces + edges), or null while it loads. */
  overlay: OverlayResult | null;
  /** The face/edge index already picked on THIS instance (selected cue), or null. */
  selectedIndex: number | null;
  onPickFace: (index: number, signature: PlanarFaceSignature) => void;
  onPickAxis: (index: number, signature: EdgeSignature) => void;
}

export function InstanceMateOverlay({
  instanceId,
  transform,
  tool,
  overlay,
  selectedIndex,
  onPickFace,
  onPickAxis,
}: InstanceMateOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    invalidate();
  }, [overlay, selectedIndex, tool, invalidate]);

  if (overlay === null) return null;

  return (
    <group position={transform.position} quaternion={transform.quaternion}>
      {tool === "coincident"
        ? overlay.faces.map((face) =>
            isPickableFace(face) ? (
              <Html
                key={`f${face.index}`}
                position={occtPointToScene(face.signature.centroid)}
                center
                zIndexRange={[30, 10]}
              >
                <PickNode
                  shape="face"
                  selected={selectedIndex === face.index}
                  data-testid={`mate-face-${instanceId}-${face.index}`}
                  aria-label={faceLabel(face.index, face.signature)}
                  onClick={() => onPickFace(face.index, face.signature)}
                />
              </Html>
            ) : null,
          )
        : overlay.edges.map((edge, index) =>
            edge.signature.curve === "circle" ? (
              <Html
                key={`e${index}`}
                position={occtPointToScene(polylineMidpoint(edge.polyline))}
                center
                zIndexRange={[30, 10]}
              >
                <PickNode
                  shape="edge"
                  selected={selectedIndex === index}
                  data-testid={`mate-axis-${instanceId}-${index}`}
                  aria-label={`Circular edge ${index + 1} — hole axis`}
                  onClick={() => onPickAxis(index, edge.signature)}
                />
              </Html>
            ) : null,
          )}
    </group>
  );
}
