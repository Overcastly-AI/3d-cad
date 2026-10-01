/**
 * The inspector's material panel: the served library and the wholesale
 * assignment write.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import {
  fetchMaterials,
  type MaterialAssignment,
  type MaterialKey,
  updatePartMaterials,
} from "../../api/materials";
import { fetchFeatureTree } from "../../api/parts";
import {
  bodyMaterialRows,
  withBodyMaterial,
  withDefaultMaterial,
} from "../../features/materials";
import type { PartDocument } from "./usePartDocument";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { TreeWrites } from "./useTreeWrites";

type MaterialControlsParams = Pick<
  PartDocument,
  "partId" | "queryClient" | "part" | "evaluation"
> &
  Pick<FeatureCatalog, "bodies"> &
  Pick<TreeWrites, "freshTreeVersion">;

export function useMaterialControls({
  partId,
  queryClient,
  part,
  evaluation,
  bodies,
  freshTreeVersion,
}: MaterialControlsParams) {
  // MATERIAL (docs/design/materials.md). The library is SERVED, never typed
  // client-side — a density is a physical constant with one home, and a second
  // copy in TS would silently drift. It is a fixed table, so one fetch per
  // session; a failure disables the picker and says why rather than guessing.
  const materialLibrary = useQuery({
    queryKey: ["materials"],
    queryFn: () => fetchMaterials(),
    staleTime: Infinity,
    retry: false,
  });
  // A stored NULL reads back as the EMPTY assignment (§4), so the panel has ONE
  // shape to render and never has to tell null from empty.
  const assignment = useMemo<MaterialAssignment>(
    () => part.data?.materials ?? { default_material: null, bodies: [] },
    [part.data?.materials],
  );
  // One row per body: the tree's names/ordinals joined to the evaluation's
  // RESOLVED material + mass. Resolution is the server's single function
  // (`resolve_body_material`); nothing here re-derives it.
  const materialRows = useMemo(
    () => bodyMaterialRows(bodies, evaluation.data?.bodies ?? [], assignment),
    [bodies, evaluation.data?.bodies, assignment],
  );
  const [materialBusy, setMaterialBusy] = useState(false);
  const [materialError, setMaterialError] = useState<string | null>(null);
  // Assignment is a WHOLESALE replacement under the tree-version OCC guard
  // (§2): the request states the full intended state, so two concurrent edits
  // cannot interleave into an assignment neither of them sent. Unlike a rename
  // or a unit change this really does invalidate the recorded evaluate — mass
  // was derived from the material — so the tree refetch bumps `tree_version`,
  // which re-keys the evaluate query and rebuilds with the new density.
  const assignMaterials = useCallback(
    (next: MaterialAssignment) => {
      if (materialBusy) return;
      setMaterialBusy(true);
      setMaterialError(null);
      void (async () => {
        try {
          // Retry ONCE on a stale-version race, the way every other discrete
          // edit here does: a user who re-units the document and immediately
          // picks a material would otherwise hit a 422 for a conflict that
          // isn't one (nobody else edited anything — the cached version simply
          // hadn't caught up yet).
          try {
            await updatePartMaterials(partId, next, await freshTreeVersion());
          } catch {
            await updatePartMaterials(
              partId,
              next,
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({ queryKey: ["part", partId] });
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
          await queryClient.invalidateQueries({
            queryKey: ["evaluate", partId],
          });
        } catch (error) {
          setMaterialError(
            error instanceof Error
              ? error.message
              : "The material could not be assigned.",
          );
        } finally {
          setMaterialBusy(false);
        }
      })();
    },
    [materialBusy, partId, freshTreeVersion, queryClient],
  );
  const assignDefaultMaterial = useCallback(
    (material: MaterialKey | null) =>
      assignMaterials(withDefaultMaterial(assignment, material)),
    [assignMaterials, assignment],
  );
  const assignBodyMaterial = useCallback(
    (baseFeatureId: string, material: MaterialKey | null) =>
      assignMaterials(withBodyMaterial(assignment, baseFeatureId, material)),
    [assignMaterials, assignment],
  );
  const materialControls = useMemo(
    () => ({
      library: materialLibrary.data ?? [],
      libraryError:
        materialLibrary.error instanceof Error
          ? materialLibrary.error.message
          : null,
      assignment,
      rows: materialRows,
      busy: materialBusy,
      error: materialError,
      onAssignDefault: assignDefaultMaterial,
      onAssignBody: assignBodyMaterial,
    }),
    [
      materialLibrary.data,
      materialLibrary.error,
      assignment,
      materialRows,
      materialBusy,
      materialError,
      assignDefaultMaterial,
      assignBodyMaterial,
    ],
  );
  return { materialControls };
}

export type MaterialControls = ReturnType<typeof useMaterialControls>;
