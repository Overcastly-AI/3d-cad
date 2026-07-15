/**
 * Parse each UNIQUE part GLB once into a shared `BufferGeometry` (+ its B-rep
 * edge overlay), keyed by content-addressed mesh id. This is the render half
 * of the dedup contract (design §4): two instances of the same part share ONE
 * mesh id, so they parse once and the geometry is drawn N times at N solved
 * poses — never re-parsed, never re-uploaded. GLTF parsing is headless
 * (`parseAsync`), so it runs outside the Canvas.
 *
 * Geometries + edges are disposed when the mesh set changes or the hook
 * unmounts (GPU hygiene, CLAUDE.md viewport discipline).
 */
import { useEffect, useState } from "react";
import { BufferGeometry, EdgesGeometry } from "three";

import { loadGlbGeometry } from "./glbGeometry";

export interface InstanceGeometry {
  surface: BufferGeometry;
  edges: EdgesGeometry;
}

export interface InstanceGeometries {
  /** Parsed geometry by content-addressed mesh id (shared across instances). */
  byMeshId: ReadonlyMap<string, InstanceGeometry>;
  /** A parse failure message (first offending mesh), or null. */
  error: string | null;
}

/**
 * Parse `meshes` (mesh id → GLB bytes) into shared geometries. Pass a stable
 * Map identity (memoize on the fetch result) so parsing only re-runs when the
 * fetched byte set actually changes.
 */
export function useInstanceGeometries(
  meshes: ReadonlyMap<string, ArrayBuffer>,
): InstanceGeometries {
  const [state, setState] = useState<InstanceGeometries>({
    byMeshId: new Map(),
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    const built = new Map<string, InstanceGeometry>();
    let error: string | null = null;

    void (async () => {
      for (const [meshId, bytes] of meshes) {
        await loadGlbGeometry(bytes, {
          isCancelled: () => cancelled,
          onGeometry: (geometry) => {
            built.set(meshId, {
              surface: geometry,
              edges: new EdgesGeometry(geometry, 25),
            });
          },
          onError: (cause) => {
            error = error ?? cause.message;
          },
        });
      }
      if (cancelled) {
        for (const g of built.values()) {
          g.surface.dispose();
          g.edges.dispose();
        }
        return;
      }
      setState({ byMeshId: built, error });
    })();

    return () => {
      cancelled = true;
      for (const g of built.values()) {
        g.surface.dispose();
        g.edges.dispose();
      }
    };
  }, [meshes]);

  return state;
}
