/**
 * The shared tree-write plumbing (fresh version, refresh, the in-flight
 * write facts of QA-R4) and the document-unit change.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useEffect, useState } from "react";

import {
  fetchFeatureTree,
  updatePartUnit,
  type LengthUnit,
} from "../../api/parts";
import type { PartDocument } from "./usePartDocument";

type TreeWritesParams = Pick<
  PartDocument,
  "partId" | "queryClient" | "lengthUnit" | "tree"
>;

export function useTreeWrites({
  partId,
  queryClient,
  lengthUnit,
  tree,
}: TreeWritesParams) {
  /** Latest tree version, refetched if the query has none yet. */
  const freshTreeVersion = useCallback(async (): Promise<number> => {
    if (tree.data !== undefined) return tree.data.tree_version;
    return (await fetchFeatureTree(partId)).tree_version;
  }, [partId, tree.data]);

  const refreshTreeAndBody = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["features", partId] });
    await queryClient.invalidateQueries({ queryKey: ["evaluate", partId] });
    await queryClient.invalidateQueries({ queryKey: ["mesh", partId] });
  }, [partId, queryClient]);

  // ---------------------------------------------------------------------
  // WHAT THE WORKSPACE KNOWS BEFORE ITS CACHES DO (QA-R4).
  //
  // Every tree write ends in `refreshTreeAndBody`, and until those refetches
  // land, the part row and the feature tree still hold the PRE-write version —
  // which is the denominator `derivePartBuild` compares the evaluation against.
  // So for the whole length of a write the provenance test came out "current"
  // and every readout in the app confidently reported a superseded body:
  // measured at ~600-840 ms, the panel showing the PREVIOUS part's mass with
  // both status cells claiming to be up to date (QA-REVIEW 2026-08-27).
  //
  // Two facts close it, and they are independent on purpose:
  //  - `pending` — a write is in flight. True from the click, before any reply
  //    exists, because from the moment the app issues the write it KNOWS the
  //    body on screen is superseded; it is holding the mutation.
  //  - `version` — the `tree_version` a write RESPONSE reported. A provenance
  //    fact rather than a request state, so it keeps the derivation honest even
  //    where a caller forgets the flag, and it is the earliest the new
  //    denominator exists anywhere in the client.
  // Reset per part: a version from one part is not a fact about another.
  // ---------------------------------------------------------------------
  const [treeWrite, setTreeWrite] = useState<{
    pending: number;
    version: number | null;
  }>({ pending: 0, version: null });
  useEffect(() => {
    setTreeWrite({ pending: 0, version: null });
  }, [partId]);
  const beginTreeWrite = useCallback(() => {
    setTreeWrite((state) => ({ ...state, pending: state.pending + 1 }));
  }, []);
  /** Pair with `beginTreeWrite` in a `finally` — never on the success path. */
  const endTreeWrite = useCallback(() => {
    setTreeWrite((state) => ({
      ...state,
      pending: Math.max(0, state.pending - 1),
    }));
  }, []);
  /** Monotonic, like the counter itself: a later write can only move it up. */
  const noteWrittenTreeVersion = useCallback((version: number) => {
    setTreeWrite((state) => ({
      ...state,
      version: Math.max(state.version ?? version, version),
    }));
  }, []);

  // Document-unit change (docs/design/units.md §U2): a pure re-label. It PATCHes
  // the part's `length_unit` under the tree-version OCC and refreshes the part +
  // tree — NO stored mm value is touched, so the body never re-solves; every
  // dimension cell + readout simply re-formats into the new unit on the next
  // render (the DocumentUnitProvider feeds them the new value).
  const [unitBusy, setUnitBusy] = useState(false);
  const changeUnit = useCallback(
    (next: LengthUnit) => {
      if (next === lengthUnit || unitBusy) return;
      setUnitBusy(true);
      void (async () => {
        try {
          const version = await freshTreeVersion();
          await updatePartUnit(partId, next, version);
          await queryClient.invalidateQueries({ queryKey: ["part", partId] });
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
        } catch {
          // A stale-version race (422) or transient failure leaves the unit as
          // it was; the selector reverts to the loaded value and the user can
          // retry. Nothing stored changed.
        } finally {
          setUnitBusy(false);
        }
      })();
    },
    [lengthUnit, unitBusy, partId, freshTreeVersion, queryClient],
  );
  return {
    freshTreeVersion,
    refreshTreeAndBody,
    treeWrite,
    beginTreeWrite,
    endTreeWrite,
    noteWrittenTreeVersion,
    unitBusy,
    changeUnit,
  };
}

export type TreeWrites = ReturnType<typeof useTreeWrites>;
