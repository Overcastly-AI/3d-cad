/**
 * Per-instance mate-pick overlay — the "pick the mating geometry" step of mate
 * authoring, reusing the SAME hit-test machinery as the part workspace's face
 * and edge picks (CLAUDE.md DRY rule). The overlay rides the instance's SOLVED
 * scene transform, so both the raycast targets and the pick nodes sit on the
 * rendered instance; the geometry comes from the PART's own `/overlay` (local
 * frame), and each picked signature passes through UNCHANGED into the mate ref
 * (the backend resolves it against that instance's local part body).
 *
 * Coincident wants PLANAR faces (each carries a `PlanarFaceSignature`) and is
 * hit-tested by raycasting the instance's own surface; concentric wants
 * CIRCULAR edges (each a circle `EdgeSignature` → an axis) and is hit-tested by
 * a screen-space band along those circles. `PickNode` stays as the keyboard,
 * screen-reader and touch target (SEL-4).
 *
 * THE RAYCAST TARGET IS THE INSTANCE'S OWN MESH, not the part scene's — this
 * overlay is not in the part workspace, so `usePartViewStore.pickGeometry` is
 * unavailable and irrelevant. `AssemblyScene` already holds
 * `inst.geometry.surface`, a `BufferGeometry` from the SAME `loadGlbGeometry`
 * parser, so it carries the same B-rep face partition and
 * `faceOrdinalOfTriangle` applies unchanged. It is mounted INSIDE the
 * transform group so it rides the solved pose, and it needs no hidden-face set:
 * an instance that is not drawn mounts no overlay at all.
 */
import { PickNode } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { BufferGeometry } from "three";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import type { OverlayResult } from "../api/measure";
import { occtPointToScene, type SceneTransform } from "../assembly/placement";
import { isPickableFace, faceLabel } from "../features/face";
import { polylineMidpoint, polylineSegments } from "../measure/geometry";
import { EdgeBandLayer } from "./EdgeBandLayer";
import type { EdgeBandInput } from "./edgeBand";
import { FacePatch } from "./facePatch";
import { Segments } from "./overlaySegments";
import { PickSurface } from "./pickSurface";
import { useViewportPickStamp } from "./pickStamp";

export interface InstanceMateOverlayProps {
  instanceId: string;
  /** The instance's solved scene transform (the pick targets ride it). */
  transform: SceneTransform;
  /** The instance's drawn surface — the raycast target for coincident picks. */
  geometry: BufferGeometry | null;
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
  geometry,
  tool,
  overlay,
  selectedIndex,
  onPickFace,
  onPickAxis,
}: InstanceMateOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);
  /**
   * Hover is LOCAL state here, not store state: it is presentational (a patch
   * or a highlight under the cursor) and it belongs to one instance. Before
   * SEL-4 this overlay had no hover at all, which was survivable while the only
   * target was a dot you aimed at — with a raycast, a pick with no feedback
   * lands invisibly, so the hover ships with the conversion.
   */
  const [hovered, setHovered] = useState<number | null>(null);

  useEffect(() => {
    invalidate();
  }, [overlay, selectedIndex, tool, hovered, invalidate]);

  // Drop a stale hover when the offered set changes out from under it.
  useEffect(() => {
    setHovered(null);
  }, [overlay, tool]);

  /** QA hook: which instance + entity the armed mate pick is addressing. */
  useViewportPickStamp(
    "matePickHover",
    hovered === null ? null : `${instanceId}:${hovered}`,
  );

  /** The circular edges on offer for a concentric mate, with their signatures. */
  const circles = useMemo(
    () =>
      overlay === null
        ? []
        : overlay.edges.flatMap((edge, index) =>
            edge.signature.curve === "circle"
              ? [{ index, polyline: edge.polyline, signature: edge.signature }]
              : [],
          ),
    [overlay],
  );
  const circleBand = useMemo<EdgeBandInput[]>(
    () => circles.map(({ index, polyline }) => ({ index, polyline })),
    [circles],
  );

  /** Hover / selected highlights for the offered axes — one brass palette. */
  const hoveredCirclePositions = useMemo(() => {
    const circle = circles.find(({ index }) => index === hovered);
    return circle === undefined || circle.index === selectedIndex
      ? new Float32Array(0)
      : polylineSegments(circle.polyline);
  }, [circles, hovered, selectedIndex]);
  const selectedCirclePositions = useMemo(() => {
    const circle = circles.find(({ index }) => index === selectedIndex);
    return circle === undefined
      ? new Float32Array(0)
      : polylineSegments(circle.polyline);
  }, [circles, selectedIndex]);

  const faceAt = useCallback(
    (ordinal: number | null) => {
      if (overlay === null || ordinal === null) return null;
      const face = overlay.faces.find(
        (candidate) => candidate.index === ordinal,
      );
      return face !== undefined && isPickableFace(face) ? face : null;
    },
    [overlay],
  );

  const onSurfaceMove = useCallback(
    (ordinal: number | null) => setHovered(faceAt(ordinal)?.index ?? null),
    [faceAt],
  );

  const onSurfaceClick = useCallback(
    (ordinal: number | null, event: { stopPropagation: () => void }) => {
      const face = faceAt(ordinal);
      if (face === null || !isPickableFace(face)) return;
      event.stopPropagation();
      onPickFace(face.index, face.signature);
    },
    [faceAt, onPickFace],
  );

  const onBandPick = useCallback(
    (index: number) => {
      const circle = circles.find((candidate) => candidate.index === index);
      if (circle !== undefined) onPickAxis(index, circle.signature);
    },
    [circles, onPickAxis],
  );

  if (overlay === null) return null;

  return (
    <group position={transform.position} quaternion={transform.quaternion}>
      {tool === "coincident" ? (
        <>
          <PickSurface
            geometry={geometry}
            onMove={onSurfaceMove}
            onOut={() => setHovered(null)}
            onClick={onSurfaceClick}
          />
          {overlay.faces.map((face) =>
            isPickableFace(face) ? (
              <group key={`f${face.index}`}>
                {selectedIndex === face.index || hovered === face.index ? (
                  <FacePatch
                    signature={face.signature}
                    selected={selectedIndex === face.index}
                  />
                ) : null}
                <Html
                  position={occtPointToScene(face.signature.centroid)}
                  center
                  zIndexRange={[30, 10]}
                >
                  <PickNode
                    shape="face"
                    // A7's recession: the instance's drawn surface is this
                    // pick's primary hit-test now.
                    recede
                    selected={selectedIndex === face.index}
                    data-testid={`mate-face-${instanceId}-${face.index}`}
                    aria-label={faceLabel(face.index, face.signature)}
                    onClick={() => onPickFace(face.index, face.signature)}
                    onPointerOver={() => setHovered(face.index)}
                    onPointerOut={() =>
                      setHovered((h) => (h === face.index ? null : h))
                    }
                    onFocus={() => setHovered(face.index)}
                    onBlur={() =>
                      setHovered((h) => (h === face.index ? null : h))
                    }
                  />
                </Html>
              </group>
            ) : null,
          )}
        </>
      ) : (
        <>
          <EdgeBandLayer
            edges={circleBand}
            geometry={geometry}
            onHover={setHovered}
            onPick={onBandPick}
          />
          <Segments
            positions={hoveredCirclePositions}
            color={measure.edgeHover}
          />
          <Segments
            positions={selectedCirclePositions}
            color={measure.edgeSelected}
          />
          {circles.map(({ index, polyline, signature }) => (
            <Html
              key={`e${index}`}
              position={occtPointToScene(polylineMidpoint(polyline))}
              center
              zIndexRange={[30, 10]}
            >
              <PickNode
                shape="edge"
                // A7's recession: the circular edge itself is the hit-test now.
                recede
                selected={selectedIndex === index}
                data-testid={`mate-axis-${instanceId}-${index}`}
                aria-label={`Circular edge ${index + 1} — hole axis`}
                onClick={() => onPickAxis(index, signature)}
                onPointerOver={() => setHovered(index)}
                onPointerOut={() => setHovered((h) => (h === index ? null : h))}
                onFocus={() => setHovered(index)}
                onBlur={() => setHovered((h) => (h === index ? null : h))}
              />
            </Html>
          ))}
        </>
      )}
    </group>
  );
}
