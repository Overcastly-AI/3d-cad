import { viewport } from "@loft/design/tokens";
import { useEffect, useMemo, useState } from "react";
import {
  BufferGeometry,
  EdgesGeometry,
  LineBasicMaterial,
  Mesh,
  MeshStandardMaterial,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { useThree } from "@react-three/fiber";

/** GLB scenes are metres (glTF spec); the app works in millimetres. */
const METRES_TO_MM = 1000;

/**
 * Parse GLB bytes off the wire into one render-ready BufferGeometry, scaled
 * to mm. OCCT writes one glTF primitive per B-rep face (plus a Z-up→Y-up
 * node rotation), so every mesh is baked through its world matrix and
 * merged. Embedded materials are disposed — the surface material comes from
 * the design tokens, same palette as the DOM.
 */
async function parseGlbGeometry(
  glb: ArrayBuffer,
): Promise<BufferGeometry | null> {
  const gltf = await new GLTFLoader().parseAsync(glb, "");
  gltf.scene.updateMatrixWorld(true);
  const parts: BufferGeometry[] = [];
  gltf.scene.traverse((object) => {
    if (object instanceof Mesh) {
      const mesh = object as Mesh;
      parts.push(mesh.geometry.clone().applyMatrix4(mesh.matrixWorld));
      mesh.geometry.dispose();
      const material = mesh.material;
      for (const m of Array.isArray(material) ? material : [material]) {
        m.dispose();
      }
    }
  });
  if (parts.length === 0) {
    return null;
  }
  const geometry = mergeGeometries(parts, false);
  for (const part of parts) {
    part.dispose();
  }
  if (geometry === null) {
    return null;
  }
  geometry.scale(METRES_TO_MM, METRES_TO_MM, METRES_TO_MM);
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

export interface ModelMeshProps {
  glb: ArrayBuffer;
  /** Called with the mm-scaled geometry whenever a new mesh is ready. */
  onGeometry?: (geometry: BufferGeometry) => void;
}

/** The tessellated model: token-driven surface + B-rep edge overlay. */
export function ModelMesh({ glb, onGeometry }: ModelMeshProps) {
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
    void parseGlbGeometry(glb).then((next) => {
      if (cancelled || next === null) {
        next?.dispose();
        return;
      }
      setGeometry(next);
      onGeometry?.(next);
      invalidate();
    });
    return () => {
      cancelled = true;
    };
  }, [glb, onGeometry, invalidate]);

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
