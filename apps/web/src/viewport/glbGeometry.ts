/**
 * GLB → BufferGeometry pipeline for the viewport, kept free of React so the
 * failure paths are unit-testable. A corrupt payload that leaves a stale
 * model on screen while the inspector shows fresh numbers is the worst CAD
 * failure mode — every parse here must end in exactly one visible outcome.
 */
import { BufferGeometry, Mesh } from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

/** GLB scenes are metres (glTF spec); the app works in millimetres. */
const METRES_TO_MM = 1000;

/**
 * Parse GLB bytes off the wire into one render-ready BufferGeometry, scaled
 * to mm. OCCT writes one glTF primitive per B-rep face (plus a Z-up→Y-up
 * node rotation), so every mesh is baked through its world matrix and
 * merged. Embedded materials are disposed — the surface material comes from
 * the design tokens, same palette as the DOM.
 *
 * Rejects on corrupt/truncated payloads; resolves `null` when the scene has
 * no renderable mesh. Callers must route both to a visible error state —
 * prefer `loadGlbGeometry`, which does this and never rejects.
 */
export async function parseGlbGeometry(
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

export interface LoadGlbCallbacks {
  /** Effect-cleanup guard — when true, results are disposed, not delivered. */
  isCancelled: () => boolean;
  /** Receives the mm-scaled geometry on success. */
  onGeometry: (geometry: BufferGeometry) => void;
  /** Receives every failure: parse rejection or a mesh-less scene. */
  onError: (error: Error) => void;
}

/**
 * Drive one GLB parse to a definite outcome: exactly one of `onGeometry` /
 * `onError` fires (neither if cancelled first). Never rejects — a corrupt or
 * truncated GLB must surface in the UI, not as an unhandled rejection.
 *
 * `parse` is injectable for unit tests only; production callers use the
 * default.
 */
export async function loadGlbGeometry(
  glb: ArrayBuffer,
  callbacks: LoadGlbCallbacks,
  parse: (
    glb: ArrayBuffer,
  ) => Promise<BufferGeometry | null> = parseGlbGeometry,
): Promise<void> {
  let geometry: BufferGeometry | null;
  try {
    geometry = await parse(glb);
  } catch (cause) {
    if (!callbacks.isCancelled()) {
      callbacks.onError(
        cause instanceof Error ? cause : new Error(String(cause)),
      );
    }
    return;
  }
  if (callbacks.isCancelled()) {
    geometry?.dispose();
    return;
  }
  if (geometry === null) {
    callbacks.onError(new Error("GLB payload contains no renderable mesh"));
    return;
  }
  callbacks.onGeometry(geometry);
}
