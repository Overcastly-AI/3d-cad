import { viewport } from "@loft/design/tokens";
import { useEffect, useMemo, useState } from "react";
import {
  BufferGeometry,
  EdgesGeometry,
  LineBasicMaterial,
  MeshStandardMaterial,
} from "three";
import { useThree } from "@react-three/fiber";

import { loadGlbGeometry } from "./glbGeometry";

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
}

/** The tessellated model: token-driven surface + B-rep edge overlay. */
export function ModelMesh({ glb, onGeometry, onError }: ModelMeshProps) {
  const invalidate = useThree((state) => state.invalidate);
  const [geometry, setGeometry] = useState<BufferGeometry | null>(null);

  // Materials are created once and shared across re-tessellations.
  const surfaceMaterial = useMemo(
    () =>
      new MeshStandardMaterial({
        color: viewport.modelSurface,
        metalness: 0.35,
        roughness: 0.55,
      }),
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
      <mesh geometry={geometry} material={surfaceMaterial} />
      <lineSegments geometry={edges} material={edgeMaterial} />
    </group>
  );
}
