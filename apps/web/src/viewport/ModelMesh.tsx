import { viewport } from "@loft/design/tokens";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BufferGeometry,
  EdgesGeometry,
  LineBasicMaterial,
  MeshMatcapMaterial,
} from "three";
import { useThree, type ThreeEvent } from "@react-three/fiber";

import { loadGlbGeometry } from "./glbGeometry";
import { studioMatcap } from "./studioMatcap";

/** How the body reads: neutral, pointer-hovered, or feature-selected. */
export type BodyHighlight = "none" | "hover" | "selected";

export interface ModelMeshProps {
  glb: ArrayBuffer;
  /** Called with the mm-scaled geometry whenever a new mesh is ready. */
  onGeometry?: (geometry: BufferGeometry) => void;
  /**
   * Called when the GLB cannot be parsed. The stale mesh is cleared first —
   * a wrong model on screen next to fresh inspector numbers is worse than an
   * empty viewport.
   */
  onError?: (error: Error) => void;
  /**
   * The body responds to the pointer (hover glow) when true — off while a pick
   * tool owns the viewport (measure / edge / face pick), so the two highlight
   * languages never fight (Makeover Batch 3, item 11).
   */
  interactive?: boolean;
  /**
   * The body's feature is selected in the tree — the body warms even when not
   * interactive (the tree→geometry link). Wins over hover.
   */
  selected?: boolean;
  /** Report the current highlight so the viewport can stamp a QA hook. */
  onHighlightChange?: (highlight: BodyHighlight) => void;
}

/** The tessellated model: token-driven surface + B-rep edge overlay. */
export function ModelMesh({
  glb,
  onGeometry,
  onError,
  interactive = false,
  selected = false,
  onHighlightChange,
}: ModelMeshProps) {
  const invalidate = useThree((state) => state.invalidate);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);
  const [hovered, setHovered] = useState(false);
  // Selection wins over hover; hover only reads while the body is interactive.
  const highlight: BodyHighlight = selected
    ? "selected"
    : interactive && hovered
      ? "hover"
      : "none";

  // Materials are created once and shared across re-tessellations. The
  // studio matcap ("machined aluminum under shop lights") carries the whole
  // lighting rig — the scene needs no lights, and the body reads its
  // curvature at every camera angle (Batch 1 makeover, P0-3).
  const surfaceMaterial = useMemo(
    () => new MeshMatcapMaterial({ matcap: studioMatcap() }),
    [],
  );
  const edgeMaterial = useMemo(
    () => new LineBasicMaterial({ color: viewport.modelEdge }),
    [],
  );
  useEffect(
    () => () => {
      surfaceMaterial.dispose();
      edgeMaterial.dispose();
    },
    [surfaceMaterial, edgeMaterial],
  );

  // Highlight cue (Batch 3, item 11): selection warms the surface + brasses the
  // edges (the assembly selection language); hover only brightens the edges.
  // Matcap tint multiplies the studio sphere — the machined read is preserved.
  useEffect(() => {
    surfaceMaterial.color.set(
      highlight === "selected"
        ? viewport.selectedSurfaceTint
        : viewport.restSurfaceTint,
    );
    edgeMaterial.color.set(
      highlight === "selected"
        ? viewport.selection
        : highlight === "hover"
          ? viewport.hover
          : viewport.modelEdge,
    );
    invalidate();
  }, [highlight, surfaceMaterial, edgeMaterial, invalidate]);

  // Report the highlight up so the viewport can stamp a QA hook on its DOM.
  useEffect(() => {
    onHighlightChange?.(highlight);
  }, [highlight, onHighlightChange]);

  // Leaving interactive mode drops a stale hover (e.g. arming Measure while the
  // pointer rests on the body) so the body never sticks lit.
  useEffect(() => {
    if (!interactive && hovered) setHovered(false);
  }, [interactive, hovered]);

  const onPointerOver = useCallback(
    (event: ThreeEvent<PointerEvent>) => {
      if (!interactive) return;
      event.stopPropagation();
      setHovered(true);
    },
    [interactive],
  );
  const onPointerOut = useCallback(() => setHovered(false), []);

  useEffect(() => {
    let cancelled = false;
    // loadGlbGeometry never rejects — every failure lands in onError.
    void loadGlbGeometry(glb, {
      isCancelled: () => cancelled,
      onGeometry: (next) => {
        setGeometry(next);
        onGeometry?.(next);
      },
      onError: (error) => {
        setGeometry(null);
        onError?.(error);
      },
    });
    return () => {
      cancelled = true;
    };
  }, [glb, onGeometry, onError]);

  // Post-commit frame. With frameloop="demand" + preserveDrawingBuffer, an
  // invalidate() issued inside the load callback draws BEFORE React commits
  // the mesh change — clearing a stale mesh would leave its last frame in
  // the framebuffer. This effect runs after the commit, so the drawn frame
  // always matches the React scene graph.
  useEffect(() => {
    invalidate();
  }, [geometry, invalidate]);

  // Dispose GPU resources when a geometry is replaced or unmounts.
  const edges = useMemo(
    () => (geometry ? new EdgesGeometry(geometry, 25) : null),
    [geometry],
  );
  useEffect(
    () => () => {
      geometry?.dispose();
      edges?.dispose();
    },
    [geometry, edges],
  );

  if (geometry === null || edges === null) {
    return null;
  }
  return (
    <group>
      <mesh
        geometry={geometry}
        material={surfaceMaterial}
        onPointerOver={interactive ? onPointerOver : undefined}
        onPointerOut={interactive ? onPointerOut : undefined}
      />
      <lineSegments geometry={edges} material={edgeMaterial} />
    </group>
  );
}
