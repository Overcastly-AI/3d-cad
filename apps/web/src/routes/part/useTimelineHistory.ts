/**
 * Undo/redo and the rollback bar: the timeline's writes, mutually
 * exclusive with each other.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useRef, useState } from "react";

import { useMeasureStore } from "../../measure/store";
import {
  fetchFeatureTree,
  moveRollbackBar,
  redoPart,
  StaleTreeVersionError,
  undoPart,
} from "../../api/parts";
import { executeHistoryStep, signedInUserId } from "../../lib/historyStep";
import {
  historyResyncNotice,
  type HistoryStepError,
} from "../../components/HistoryErrorAlert";
import { type HistoryStep } from "../../lib/undoRedoShortcut";
import type { PartDocument } from "./usePartDocument";
import type { EditorSeat } from "./useEditorSeat";
import type { TreeWrites } from "./useTreeWrites";

type TimelineHistoryParams = Pick<
  PartDocument,
  "partId" | "queryClient" | "tree"
> &
  Pick<
    EditorSeat,
    "setSelectedFeatureId" | "rollbackBusy" | "setRollbackBusy"
  > &
  Pick<
    TreeWrites,
    | "freshTreeVersion"
    | "refreshTreeAndBody"
    | "beginTreeWrite"
    | "endTreeWrite"
    | "noteWrittenTreeVersion"
  >;

export function useTimelineHistory({
  partId,
  queryClient,
  tree,
  setSelectedFeatureId,
  rollbackBusy,
  setRollbackBusy,
  freshTreeVersion,
  refreshTreeAndBody,
  beginTreeWrite,
  endTreeWrite,
  noteWrittenTreeVersion,
}: TimelineHistoryParams) {
  // ---------------------------------------------------------------------
  // Undo/redo (docs/design/undo-redo.md §UR2). History is SERVER-side snapshot
  // state: the tree GET's can_undo/can_redo gate the controls, and a step is a
  // document edit under the same tree-version OCC as every other write. The
  // restored tree re-renders through the SAME post-mutation refresh path all
  // feature saves use — never a second pipeline.
  // ---------------------------------------------------------------------
  const canUndo = tree.data?.can_undo ?? false;
  const canRedo = tree.data?.can_redo ?? false;
  /** Which step is in flight (drives the honest hold caption), or null. */
  const [historyStep, setHistoryStep] = useState<HistoryStep | null>(null);
  const historyInFlight = useRef(false);
  /** A non-stale undo/redo failure, surfaced in the viewport HUD. */
  const [historyError, setHistoryError] = useState<HistoryStepError | null>(
    null,
  );

  const runHistoryStep = useCallback(
    (step: HistoryStep) => {
      // One tree rewrite at a time: repeats (held key / double click) AND an
      // in-flight rollback-bar move are ignored until the write settles —
      // history and the bar mutually exclude (both rewrite the tree; the OCC
      // would 422 the loser, but the bar's blind retry must never run against
      // a freshly restored tree).
      if (historyInFlight.current || rollbackBusy) return;
      historyInFlight.current = true;
      setHistoryStep(step);
      setHistoryError(null);
      beginTreeWrite();
      void (async () => {
        try {
          // The shared engine (lib/historyStep, also driving the assembly
          // workspace) runs the sequence; only the part-tree seams live here.
          const outcome = await executeHistoryStep(step, {
            version: freshTreeVersion,
            run: (s, expected) =>
              s === "undo"
                ? undoPart(partId, expected)
                : redoPart(partId, expected),
            versionOf: (tree) => tree.tree_version,
            // Boundary no-op (clean 200): nothing changed — adopt the echoed
            // tree (fresh can_undo/can_redo) without a re-evaluate cycle.
            adoptNoOp: (restored) =>
              queryClient.setQueryData(["features", partId], restored),
            onRestored: async (restored) => {
              // A REAL restore happened: only now disarm measure and drop the
              // selection (the tree is known to have changed under them),
              // then resync through the shared invalidation path. Undo/redo
              // bumps `tree_version` like any other write, and the restored
              // tree carries it — so the readouts learn the body is superseded
              // here rather than after the refetch (QA-R4).
              noteWrittenTreeVersion(restored.tree_version);
              useMeasureStore.getState().deactivate();
              setSelectedFeatureId(null);
              await refreshTreeAndBody();
            },
            isStale: (error) => error instanceof StaleTreeVersionError,
            // Someone else moved the tree: the design doc's soft reload —
            // resync quietly; the user re-issues against what they now see.
            resync: () => refreshTreeAndBody(),
            // A step that resolves after a sign-in as someone else is dropped,
            // never adopted into the cache that was cleared for them
            // (UNDO-REDO-USER-SWITCH-RACE-1).
            owner: signedInUserId,
          });
          if (outcome.kind === "failed") {
            // The tree is unchanged server-side — say so through the HUD (the
            // import-error affordance), never a silent busy flash.
            setHistoryError({ step, message: outcome.message });
          } else if (outcome.kind === "stale") {
            // The step never ran: the tree moved in another window and the
            // resync above put the CURRENT one on screen. Saying nothing here
            // is the worse of the two silences — the user pressed a key, the
            // model changed by an amount they did not ask for (the other
            // window's edit arriving), and nothing distinguishes that from
            // their own undo landing. Measured with two windows on one part:
            // feature rows 3 -> 2 on a click that undid nothing.
            setHistoryError(historyResyncNotice(step, "part"));
          }
        } finally {
          historyInFlight.current = false;
          setHistoryStep(null);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      rollbackBusy,
      freshTreeVersion,
      refreshTreeAndBody,
      queryClient,
      beginTreeWrite,
      endTreeWrite,
      noteWrittenTreeVersion,
    ],
  );

  const triggerUndo = useCallback(() => {
    if (canUndo) runHistoryStep("undo");
  }, [canUndo, runHistoryStep]);
  const triggerRedo = useCallback(() => {
    if (canRedo) runHistoryStep("redo");
  }, [canRedo, runHistoryStep]);

  const moveRollback = useCallback(
    (rollbackFeatureId: string | null) => {
      // Mutual exclusion with undo/redo (and drag re-entry): both rewrite the
      // tree, and the bar's blind stale-retry must never land on a tree a
      // history step just restored.
      if (rollbackBusy || historyInFlight.current) return;
      // Moving the bar rebuilds the body → the measure overlay refetches
      // against a different tree version; disarm the tool so a mid-measure
      // rollback can never resolve a stale pick index (matches every other
      // tree-mutating path: openCreate*, selectFeature, handleNewSketch).
      useMeasureStore.getState().deactivate();
      setRollbackBusy(true);
      beginTreeWrite();
      void (async () => {
        try {
          const run = async (version: number) =>
            moveRollbackBar(partId, rollbackFeatureId, version);
          let restored;
          try {
            restored = await run(await freshTreeVersion());
          } catch {
            restored = await run((await fetchFeatureTree(partId)).tree_version);
          }
          noteWrittenTreeVersion(restored.tree_version);
          await refreshTreeAndBody();
        } finally {
          setRollbackBusy(false);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      rollbackBusy,
      freshTreeVersion,
      refreshTreeAndBody,
      beginTreeWrite,
      endTreeWrite,
      noteWrittenTreeVersion,
    ],
  );
  return {
    canUndo,
    canRedo,
    historyStep,
    historyError,
    setHistoryError,
    triggerUndo,
    triggerRedo,
    moveRollback,
  };
}

export type TimelineHistory = ReturnType<typeof useTimelineHistory>;
