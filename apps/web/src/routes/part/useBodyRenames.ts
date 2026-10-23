/**
 * Renaming a body in the Bodies panel (BODY-NAMES), as Fusion renames one in
 * its browser: the part's whole rename set is replaced under the tree-version
 * guard, retried once on a stale version as the material write is.
 */
import { useCallback, useState } from "react";

import { updatePartBodyNames } from "../../api/bodyNames";
import { fetchFeatureTree } from "../../api/parts";
import { type BodyInfo, withBodyRename } from "../../features/bodies";
import type { PartDocument } from "./usePartDocument";

type BodyRenamesParams = Pick<PartDocument, "partId" | "part" | "queryClient">;

export function useBodyRenames({
  partId,
  part,
  queryClient,
}: BodyRenamesParams) {
  const [error, setError] = useState<string | null>(null);
  const renameBody = useCallback(
    (body: BodyInfo, name: string) => {
      const current = part.data?.body_names ?? [];
      const next = withBodyRename(
        current,
        body.baseFeatureId,
        name,
        body.unrenamed,
      );
      const same =
        next.length === current.length &&
        next.every((entry) =>
          current.some(
            (old) =>
              old.base_feature_id === entry.base_feature_id &&
              old.name === entry.name,
          ),
        );
      if (same) return;
      setError(null);
      void (async () => {
        try {
          const version = (await fetchFeatureTree(partId)).tree_version;
          try {
            await updatePartBodyNames(partId, next, version);
          } catch {
            await updatePartBodyNames(
              partId,
              next,
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          await queryClient.invalidateQueries({ queryKey: ["part", partId] });
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
        } catch (failure) {
          setError(
            failure instanceof Error
              ? failure.message
              : "The body could not be renamed.",
          );
        }
      })();
    },
    [part.data?.body_names, partId, queryClient],
  );
  return { renameBody, renameError: error };
}

export type BodyRenames = ReturnType<typeof useBodyRenames>;
