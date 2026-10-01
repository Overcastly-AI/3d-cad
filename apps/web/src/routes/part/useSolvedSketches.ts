/**
 * Datum resolution and the solved sketch layers the scene draws.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useMemo } from "react";

import {
  type AnyDatumParams,
  faceBasis,
  sceneOriginBasis,
  type PlaneBasis,
  resolveDatumSceneBasis,
} from "../../sketch/plane";
import { type SolvedSketchLayer } from "../../viewport/SketchScene";
import type { PartDocument } from "./usePartDocument";

type SolvedSketchesParams = Pick<
  PartDocument,
  "mode" | "featureId" | "tree" | "evaluation"
>;

export function useSolvedSketches({
  mode,
  featureId,
  tree,
  evaluation,
}: SolvedSketchesParams) {
  /** All datum feature params by id — the datum-plane resolution table. */
  const datumById = useMemo(() => {
    const map = new Map<string, AnyDatumParams>();
    for (const feature of tree.data?.features ?? []) {
      if (feature.feature.type === "datum") {
        map.set(feature.id, feature.feature.params);
      }
    }
    return map;
  }, [tree.data]);

  /**
   * Every datum feature's placed sketch basis, resolved client-side by the SAME
   * math the kernel evaluates (offset / offset-from-a-datum / midplane over
   * origin + datum sides — one plane-math source, two renderers). An `on_face`
   * datum (or a face-picked midplane side) resolves server-side only, so it is
   * absent here and simply not offered as a reusable preview plane.
   */
  const datumBasisById = useMemo(() => {
    const map = new Map<string, PlaneBasis>();
    for (const id of datumById.keys()) {
      const basis = resolveDatumSceneBasis(id, datumById);
      if (basis !== null) map.set(id, basis);
    }
    return map;
  }, [datumById]);

  /** Solved sketch layers: tree feature (plane) × evaluate result (geometry). */
  const solved = useMemo<SolvedSketchLayer[]>(() => {
    if (tree.data === undefined || evaluation.data === undefined) return [];
    const results = new Map(
      evaluation.data.features.map((f) => [f.feature_id, f]),
    );
    const layers: SolvedSketchLayer[] = [];
    for (const feature of tree.data.features) {
      if (feature.feature.type !== "sketch") continue;
      // The bound feature renders through the live draw layer while
      // sketching — never twice.
      if (mode === "draw" && feature.id === featureId) continue;
      // Resolve the plane ref to a placed basis: an origin datum draws at the
      // world frame; a datum FeatureRef draws at that datum's offset (so a
      // sketch on XY+30 renders its solved ink at z=30). Mirrors the kernel's
      // resolve_sketch_plane so overlay + body agree.
      const plane = feature.feature.params.plane;
      let basis: PlaneBasis | null = null;
      if (plane.kind === "datum_plane") {
        basis = sceneOriginBasis(plane.plane);
      } else {
        basis = datumBasisById.get(plane.feature_id) ?? null;
        if (basis === null) {
          // An `on_face` datum has no world-frame walk (its plane belongs to a
          // body face), but its face signature is right there in the params —
          // the SAME reconstruction the sketch-on-face flow draws with. Without
          // it a face-seated sketch had no layer at all, so the live extrude
          // ghost simply never appeared on the one seat where the direction is
          // ambiguous to the eye (FB-4: the user must SEE which way the cut
          // goes before committing).
          const datum = datumById.get(plane.feature_id);
          if (datum?.kind === "on_face") {
            basis = faceBasis(datum.face.selector.signature, datum.offset_mm);
          }
        }
      }
      if (basis === null) continue; // unresolved plane (rolled back / deleted)
      const result = results.get(feature.id);
      if (result?.status !== "ok" || result.data?.kind !== "solved_sketch") {
        continue;
      }
      layers.push({
        featureId: feature.id,
        basis,
        entities: result.data.entities,
      });
    }
    return layers;
  }, [tree.data, evaluation.data, mode, featureId, datumById, datumBasisById]);

  /**
   * Each solved profile's entities, for the Sweep twist-cost note (review S9;
   * the cost is in turns and profile edges, so it is the extrude's formula).
   */
  const profileEntities = useCallback(
    (id: string) =>
      solved.find((layer) => layer.featureId === id)?.entities ?? null,
    [solved],
  );
  return { datumById, datumBasisById, solved, profileEntities };
}

export type SolvedSketches = ReturnType<typeof useSolvedSketches>;
