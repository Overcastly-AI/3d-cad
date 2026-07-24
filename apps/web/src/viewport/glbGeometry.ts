/**
 * GLB → BufferGeometry pipeline for the viewport, kept free of React so the
 * failure paths are unit-testable. A corrupt payload that leaves a stale
 * model on screen while the inspector shows fresh numbers is the worst CAD
 * failure mode — every parse here must end in exactly one visible outcome.
 */
import { BufferGeometry, EdgesGeometry, Mesh } from "three";
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
 * The merge keeps one draw GROUP per source primitive (`useGroups`): group
 * ordinal `i` is B-rep face `i` (== `OverlayFace.index`, one glTF primitive
 * per face in `body.faces()` order). That lets the viewport tint ONLY a
 * selected feature's faces (feature-localized selection, FINDINGS #9) while
 * the rest keep the studio matcap; a single-material render ignores the groups,
 * so the ungrouped path is unaffected.
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
  const geometry = mergeGeometries(parts, true);
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

/**
 * B-rep edges of a FACE SUBSET of a merged body geometry — the brass-edge
 * emphasis on a feature-localized selection (FINDINGS #9). The merged geometry
 * carries one draw group per B-rep face (group ordinal === `body.faces()` index
 * === `OverlayFace.index`); this gathers the index ranges of the requested face
 * ordinals into a throwaway geometry (sharing the source position buffer — no
 * vertex copy) and returns its `EdgesGeometry`, ready to overlay in the
 * selection brass. The caller owns disposing the result.
 *
 * Returns `null` when the geometry is not grouped/indexed or the subset selects
 * no triangles — the caller then draws no emphasis (never throws mid-render).
 */
export function subsetEdges(
  geometry: BufferGeometry,
  faceOrdinals: ReadonlySet<number>,
): EdgesGeometry | null {
  const index = geometry.getIndex();
  const position = geometry.getAttribute("position");
  if (
    index === null ||
    position === undefined ||
    geometry.groups.length === 0
  ) {
    return null;
  }
  const source = index.array;
  const kept: number[] = [];
  geometry.groups.forEach((group, ordinal) => {
    if (!faceOrdinals.has(ordinal)) return;
    const end = group.start + group.count;
    for (let i = group.start; i < end; i += 1) {
      kept.push(source[i] as number);
    }
  });
  if (kept.length === 0) return null;
  // Shares the source position attribute; only the index is new. Never
  // uploaded to the GPU on its own, so there is nothing to dispose here — the
  // returned EdgesGeometry copies the positions it needs.
  const subset = new BufferGeometry();
  subset.setAttribute("position", position);
  subset.setIndex(kept);
  return new EdgesGeometry(subset, 25);
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
