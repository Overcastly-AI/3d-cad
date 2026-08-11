/**
 * WHAT A SWITCHED-OFF BODY MUST NOT OFFER — the mirror half of SEL-6.
 *
 * `pickRaycast.ts` fixed one direction: a hidden body in FRONT no longer EATS
 * the pick for the body behind it. It left the other direction open, and the
 * review measured it: a hidden body still OFFERED picks. `/overlay` describes
 * the WHOLE part with no notion of visibility, so every overlay mapped every
 * edge and every face — a switched-off body's edges stayed hoverable and
 * clickable through the full 24 px `EdgeBandLayer` corridor, and its faces
 * stayed selectable through their centroid `PickNode`s, painting a brass
 * `FacePatch` over empty space. SEL-4 widened that from a 24 px dot to a
 * corridor along every edge, so the edge half is partly new.
 *
 * ## Why the answer is not simply `pickHiddenFaces`
 *
 * For FACES it is: `OverlayFace.index` and the mesh's face ordinal are the same
 * number (`glbGeometry.ts` — "group ordinal === face ordinal ===
 * OverlayFace.index"), so the set `ModelMesh` already publishes says which face
 * marks to withhold.
 *
 * An EDGE has no ordinal in that space, and nothing on the wire says which body
 * owns it — so the edge → body question is answered the way `bodyPartition.ts`
 * answers face → body: BY POSITION. Bodies are disjoint solids that share no
 * coordinates (if they touched they would be one lump, and the partition would
 * refuse rather than guess), so a weld bucket belongs to exactly one body. An
 * edge's ENDPOINTS are exact B-rep vertices and therefore triangulation nodes
 * of the faces they bound; look them up and the owning body falls out.
 *
 * Interior polyline points are deliberately NOT consulted: a curve's polyline
 * is sampled to the tree's `linear_deflection` independently of the surface
 * mesh, so an interior point need not be a mesh node at all.
 *
 * ## Which way it fails
 *
 * Toward OFFERING. A point that matches no bucket, or one that matches both a
 * hidden and a drawn body (touching solids, an unpartitionable mesh), is
 * treated as DRAWN. Withholding a pick the modeller can see would be a worse
 * defect than the one this closes, so ambiguity resolves to the status quo.
 *
 * Pure and node-testable on purpose (the `unit` vitest project, same precedent
 * as `bodyPartition.ts` and `pickRaycast.ts`): "is this entity on offer" is a
 * decision a screenshot cannot check.
 */
import { useMemo } from "react";
import type { BufferGeometry } from "three";

import type { Vec3 } from "../api/measure";
import { occtToScene } from "../measure/geometry";
import { WELD_MM, weldKey } from "./bodyPartition";
import { faceStarts } from "./glbGeometry";
import { usePartViewStore } from "./partView";

/** Bucket flags: a mesh position is a corner of a hidden body, a drawn one, or both. */
const HIDDEN_BIT = 1;
const DRAWN_BIT = 2;

/** One weld step either way — see `flagsNear`. */
const NEIGHBOURHOOD = [-WELD_MM, 0, WELD_MM] as const;

export interface HiddenPickFilter {
  /** Is this B-rep face ordinal owned by a body that is switched off? */
  isHiddenFace: (ordinal: number) => boolean;
  /** Is this OCCT-space point a corner of switched-off bodies only? */
  isHiddenPoint: (point: Vec3) => boolean;
  /** Is this OCCT-space edge polyline owned by switched-off bodies only? */
  isHiddenEdge: (polyline: readonly Vec3[]) => boolean;
}

/** Nothing is switched off — a stable identity, so the common case costs nothing. */
export const OFFER_EVERYTHING: HiddenPickFilter = {
  isHiddenFace: () => false,
  isHiddenPoint: () => false,
  isHiddenEdge: () => false,
};

/**
 * The offer filter for one pick mesh and one set of hidden B-rep face ordinals.
 *
 * Costs one pass over the index buffer plus one weld key per unique vertex, and
 * only when something is actually hidden — with every body drawn this returns
 * {@link OFFER_EVERYTHING} without touching the geometry.
 */
export function hiddenPickFilter(
  geometry: BufferGeometry | null,
  hiddenFaces: ReadonlySet<number>,
): HiddenPickFilter {
  if (geometry === null || hiddenFaces.size === 0) return OFFER_EVERYTHING;
  const index = geometry.getIndex();
  const position = geometry.getAttribute("position");
  const starts = faceStarts(geometry);
  if (index === null || position === undefined || starts.length < 2) {
    return OFFER_EVERYTHING;
  }

  // Flag each VERTEX first (by buffer index, no allocation), then key the
  // unique vertices once — a vertex is referenced by 3–6 triangles, so keying
  // inside the index walk would build the same string that many times.
  const flags = new Uint8Array(position.count);
  const idx = index.array;
  for (let ordinal = 0; ordinal + 1 < starts.length; ordinal += 1) {
    const bit = hiddenFaces.has(ordinal) ? HIDDEN_BIT : DRAWN_BIT;
    const end = starts[ordinal + 1] as number;
    for (let i = starts[ordinal] as number; i < end; i += 1) {
      const vertex = idx[i] as number;
      flags[vertex] = (flags[vertex] as number) | bit;
    }
  }
  const buckets = new Map<string, number>();
  for (let vertex = 0; vertex < position.count; vertex += 1) {
    const bit = flags[vertex] as number;
    if (bit === 0) continue;
    const key = weldKey(
      position.getX(vertex),
      position.getY(vertex),
      position.getZ(vertex),
    );
    buckets.set(key, (buckets.get(key) ?? 0) | bit);
  }

  /**
   * The flags of every bucket within one weld step of a SCENE-space point.
   *
   * The neighbourhood is not slop for its own sake: the overlay's coordinates
   * are the kernel's float64 and the mesh's are float32 metres scaled to mm, so
   * the same corner can quantize either side of a bucket boundary. Widening by
   * one bucket (1e-4 mm) cannot reach a different body — a part with two
   * distinct solids a tenth of a micron apart would already be one lump — and
   * if it somehow did, both bits would set and the point would read as DRAWN.
   */
  const flagsNear = (x: number, y: number, z: number): number => {
    let mask = 0;
    for (const dx of NEIGHBOURHOOD) {
      for (const dy of NEIGHBOURHOOD) {
        for (const dz of NEIGHBOURHOOD) {
          mask |= buckets.get(weldKey(x + dx, y + dy, z + dz)) ?? 0;
        }
      }
    }
    return mask;
  };

  const isHiddenPoint = (point: Vec3): boolean => {
    const [x, y, z] = occtToScene(point);
    const mask = flagsNear(x, y, z);
    return mask === HIDDEN_BIT;
  };

  return {
    isHiddenFace: (ordinal) => hiddenFaces.has(ordinal),
    isHiddenPoint,
    isHiddenEdge: (polyline) => {
      const first = polyline[0];
      const last = polyline[polyline.length - 1];
      if (first === undefined || last === undefined) return false;
      return isHiddenPoint(first) && isHiddenPoint(last);
    },
  };
}

/**
 * The offer filter for the PART workspace, from the two facts `ModelMesh`
 * publishes. Inert in the assembly workspace (no part mesh is published there,
 * and an undrawn instance mounts no overlay at all).
 */
export function useHiddenPicks(): HiddenPickFilter {
  const geometry = usePartViewStore((state) => state.pickGeometry);
  const hiddenFaces = usePartViewStore((state) => state.pickHiddenFaces);
  return useMemo(
    () => hiddenPickFilter(geometry, hiddenFaces),
    [geometry, hiddenFaces],
  );
}

/**
 * Is this B-rep face ordinal owned by a switched-off body? Subscribes to the
 * ordinal set ONLY — no weld pass, so a caller that needs nothing else costs
 * nothing.
 *
 * The full filter above builds a weld bucket over the whole index buffer to
 * answer the POINT and EDGE questions; a caller that only ever holds an ordinal
 * (hole placement, SEL-7) would pay for a geometry pass it never reads, and a
 * second mounting consumer would duplicate it. Same rule, one place, both call
 * sites — the overlay that withholds its marks and the editor that says why.
 *
 * FAILURE DIRECTION, deliberate and the same as this module's: a null ordinal
 * (the signature matched no pickable face in the overlay) reads as DRAWN —
 * ambiguity resolves toward OFFERING. Do NOT add
 * `isHiddenPoint(signature.centroid)` as a fallback: a face's AREA centroid is
 * not a mesh vertex, so `flagsNear` returns mask 0 and the answer is `false`
 * whatever the body's state. A safety net that is a no-op is worse than none,
 * because it stops anyone looking for the real one.
 *
 * Ghosting is not hiding: `pickHiddenFaces` carries `bodyFaceState.hidden`
 * only, so a GHOSTED body stays pickable — correct, because you can see it.
 */
export function useIsHiddenFaceOrdinal(ordinal: number | null): boolean {
  const hidden = usePartViewStore((state) => state.pickHiddenFaces);
  return ordinal !== null && hidden.has(ordinal);
}
