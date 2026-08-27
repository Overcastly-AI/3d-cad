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
 *
 * MATE-1 MOVED THE FACE HIT-TEST OUT OF HERE, and the reason is the whole
 * ticket. Each instance used to mount its own `PickSurface`, so N overlays each
 * answered "what did MY body do" — and a buried face belongs to no single body:
 * it is an entry in the COLUMN the ray crosses. Worse, each instance's
 * `onPointerMove` wrote the shared hover without stopping propagation while its
 * `onClick` did stop, so hover was decided by the FARTHEST surface and the
 * commit by the NEAREST (measured: the viewport lit the bracket's bottom face
 * while the click took the plate's — a different face on a different part).
 * `AssemblyScene` now mounts one `PickSurface` per instance ITSELF and resolves
 * the column once, so there is exactly one answer and both halves read it. What
 * stays here is what is genuinely per-instance: the highlight, and the
 * `PickNode` keyboard / screen-reader / touch targets.
 */
import { PickNode } from "@loft/design";
import { measure } from "@loft/design/tokens";
import { Html } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useCallback, useEffect, useMemo } from "react";
import type { BufferGeometry } from "three";

import type { EdgeSignature, PlanarFaceSignature } from "../api/parts";
import type { OverlayResult } from "../api/measure";
import { occtPointToScene, type SceneTransform } from "../assembly/placement";
import { isPickableFace, faceLabel } from "../features/face";
import { polylineMidpoint, polylineSegments } from "../measure/geometry";
import { EdgeBandLayer } from "./EdgeBandLayer";
import type { EdgeBandInput } from "./edgeBand";
import { FaceTrace } from "./faceTrace";
import { Segments } from "./overlaySegments";

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
  /**
   * The entity of THIS instance the pointer is addressing, or null.
   *
   * Hover is the SCENE's state, not the overlay's, even though it looks local:
   * one pointer addresses one entity across every instance, and the QA stamp
   * that publishes it is one attribute on one viewport node. Per-overlay
   * `useState` made N writers for that one attribute, and crossing from
   * instance A to instance B in a single commit could run A's cleanup after B's
   * setup and wipe the live stamp (SEL-4 review, 2026-08-08). One owner, one
   * writer.
   */
  hovered: number | null;
  /** The pointer addressed this entity of this instance (null = left it). */
  onHover: (index: number | null) => void;
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
  hovered,
  onHover,
  onPickFace,
  onPickAxis,
}: InstanceMateOverlayProps) {
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => {
    invalidate();
  }, [overlay, selectedIndex, tool, hovered, invalidate]);

  /** Leave an entity only if the pointer is still ON it (out/blur races). */
  const clearHover = useCallback(
    (index: number) => {
      if (hovered === index) onHover(null);
    },
    [hovered, onHover],
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

  const onBandPick = useCallback(
    (index: number) => {
      const circle = circles.find((candidate) => candidate.index === index);
      if (circle !== undefined) onPickAxis(index, circle.signature);
    },
    [circles, onPickAxis],
  );

  /**
   * The two face highlights, as ordinal sets for `FaceTrace`.
   *
   * Kept apart rather than merged so the two STATEMENTS stay apart: brass fill
   * for the face already committed to this mate, hover brass for the one the
   * pick is aimed at. A face that is both is drawn once, as committed — the
   * stronger claim wins, the same precedence `ModelMesh` applies.
   */
  const selectedOrdinals = useMemo<ReadonlySet<number> | null>(
    () => (selectedIndex === null ? null : new Set([selectedIndex])),
    [selectedIndex],
  );
  const hoveredOrdinals = useMemo<ReadonlySet<number> | null>(
    () =>
      hovered === null || hovered === selectedIndex ? null : new Set([hovered]),
    [hovered, selectedIndex],
  );

  if (overlay === null) return null;

  return (
    <group position={transform.position} quaternion={transform.quaternion}>
      {tool === "coincident" ? (
        <>
          {/*
            THE HIGHLIGHT IS THE FACE ITSELF (MATE-1 / T-13). It used to be
            `FacePatch` — an area-equivalent DISC on the face's plane, which the
            product audit read as "a translucent ellipse floating mostly below
            the plate, bearing no relation to the face's actual outline". A disc
            of the right area is not the right shape: on a rectangular face it
            hangs over two edges and leaves two corners bare. `FaceTrace` washes
            the face's OWN triangles and traces its OWN boundary, from the same
            partitioned geometry the pick raycasts — so what is lit and what
            would be picked cannot disagree.
          */}
          <FaceTrace
            geometry={geometry}
            faceOrdinals={selectedOrdinals}
            fill
            selected
          />
          <FaceTrace geometry={geometry} faceOrdinals={hoveredOrdinals} fill />
          {overlay.faces.map((face) =>
            isPickableFace(face) ? (
              <group key={`f${face.index}`}>
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
                    onPointerOver={() => onHover(face.index)}
                    onPointerOut={() => clearHover(face.index)}
                    onFocus={() => onHover(face.index)}
                    onBlur={() => clearHover(face.index)}
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
            onHover={onHover}
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
                onPointerOver={() => onHover(index)}
                onPointerOut={() => clearHover(index)}
                onFocus={() => onHover(index)}
                onBlur={() => clearHover(index)}
              />
            </Html>
          ))}
        </>
      )}
    </group>
  );
}
