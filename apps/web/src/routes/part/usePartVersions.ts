/**
 * Named versions in the part workspace (LOFT-VERSIONS): the Versions panel,
 * the Save version dialog, and the restore write.
 *
 * A restore is a tree write like undo: it takes the tree version on screen,
 * holds the write counter, and re-renders through the same
 * `refreshTreeAndBody` path every feature save uses, so the tree, the
 * timeline and the viewport all move together and Ctrl+Z undoes it.
 */
import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { StaleTreeVersionError } from "../../api/parts";
import {
  listPartVersions,
  PartVersionLimitError,
  restorePartVersion,
  savePartVersion,
} from "../../api/versions";
import { isSaveChord } from "../../components/dialogKeys";
import { useGlobalKeys } from "../../lib/modalGate";
import { useMeasureStore } from "../../measure/store";
import type { EditorSeat } from "./useEditorSeat";
import type { PartBody } from "./usePartBody";
import type { PartDocument } from "./usePartDocument";
import type { TreeWrites } from "./useTreeWrites";

type PartVersionsParams = Pick<PartDocument, "partId" | "tree" | "mode"> &
  Pick<PartBody, "editor"> &
  Pick<EditorSeat, "setSelectedFeatureId" | "rollbackBusy"> &
  Pick<
    TreeWrites,
    | "freshTreeVersion"
    | "refreshTreeAndBody"
    | "beginTreeWrite"
    | "endTreeWrite"
    | "noteWrittenTreeVersion"
  > & {
    /** An undo/redo is in flight (they and a restore exclude each other). */
    historyBusy: boolean;
  };

export const STALE_SAVE_MESSAGE =
  "The part changed in another window. Check the model, then save again.";
export const STALE_RESTORE_MESSAGE =
  "The part changed in another window; the current tree is now on screen. Restore again if you still want this version.";

export function usePartVersions({
  partId,
  tree,
  mode,
  editor,
  setSelectedFeatureId,
  rollbackBusy,
  freshTreeVersion,
  refreshTreeAndBody,
  beginTreeWrite,
  endTreeWrite,
  noteWrittenTreeVersion,
  historyBusy,
}: PartVersionsParams) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [restoringSeq, setRestoringSeq] = useState<number | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const versions = useQuery({
    queryKey: ["part-versions", partId],
    queryFn: () => listPartVersions(partId),
    // Loaded when it is needed: for the panel, and for the next default name.
    enabled: panelOpen || saveOpen,
  });

  const openPanel = useCallback(() => {
    setRestoreError(null);
    setPanelOpen(true);
  }, []);
  const closePanel = useCallback(() => setPanelOpen(false), []);
  const openSave = useCallback(() => {
    setSaveError(null);
    setSaveOpen(true);
  }, []);
  const closeSave = useCallback(() => {
    if (!saving) setSaveOpen(false);
  }, [saving]);

  // Ctrl/Cmd+S opens Save version (Fusion's chord). Always swallowed in the
  // workspace, so the browser's "Save page" never opens over the model; it
  // opens the dialog only with no command open, the Modelling group's rule.
  // While typing too: a modifier chord never inserts text.
  const canSaveFromKeys = mode === "off" && editor === null;
  useGlobalKeys(
    "save version",
    useCallback(
      (event: KeyboardEvent) => {
        if (!isSaveChord(event)) return;
        event.preventDefault();
        if (canSaveFromKeys) openSave();
      },
      [canSaveFromKeys, openSave],
    ),
    { whileTyping: true },
  );

  const highestSeq = versions.data?.reduce((top, v) => Math.max(top, v.seq), 0);
  const defaultName = `V${(highestSeq ?? 0) + 1}`;

  const save = useCallback(
    (input: { name: string; message: string }) => {
      if (saving) return;
      setSaving(true);
      setSaveError(null);
      void (async () => {
        try {
          await savePartVersion(partId, {
            name: input.name,
            message: input.message,
            expectedTreeVersion: tree.data?.tree_version,
          });
          await versions.refetch();
          setSaveOpen(false);
        } catch (error) {
          if (error instanceof StaleTreeVersionError) {
            await refreshTreeAndBody();
            setSaveError(STALE_SAVE_MESSAGE);
          } else if (error instanceof PartVersionLimitError) {
            setSaveError(error.message);
          } else {
            setSaveError(
              error instanceof Error
                ? error.message
                : "The version could not be saved.",
            );
          }
        } finally {
          setSaving(false);
        }
      })();
    },
    [partId, saving, tree.data?.tree_version, versions, refreshTreeAndBody],
  );

  const restoreBlockedReason =
    mode !== "off"
      ? "Finish the sketch to restore a version."
      : editor !== null
        ? "Close the open command to restore a version."
        : historyBusy || rollbackBusy
          ? "Wait for the current change to finish."
          : undefined;

  const restore = useCallback(
    (seq: number) => {
      if (restoringSeq !== null || restoreBlockedReason !== undefined) return;
      setRestoringSeq(seq);
      setRestoreError(null);
      beginTreeWrite();
      void (async () => {
        try {
          const restored = await restorePartVersion(
            partId,
            seq,
            await freshTreeVersion(),
          );
          noteWrittenTreeVersion(restored.tree_version);
          useMeasureStore.getState().deactivate();
          setSelectedFeatureId(null);
          // Close first: the model is what the user wants to see change.
          setPanelOpen(false);
          await refreshTreeAndBody();
        } catch (error) {
          if (error instanceof StaleTreeVersionError) {
            await refreshTreeAndBody();
            setRestoreError(STALE_RESTORE_MESSAGE);
          } else {
            setRestoreError(
              error instanceof Error
                ? error.message
                : "The version could not be restored.",
            );
          }
        } finally {
          setRestoringSeq(null);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      restoringSeq,
      restoreBlockedReason,
      beginTreeWrite,
      endTreeWrite,
      freshTreeVersion,
      noteWrittenTreeVersion,
      refreshTreeAndBody,
      setSelectedFeatureId,
    ],
  );

  return {
    panelOpen,
    openPanel,
    closePanel,
    saveOpen,
    openSave,
    closeSave,
    saving,
    saveError,
    save,
    defaultName,
    versions: versions.data,
    versionsError:
      versions.error instanceof Error ? versions.error.message : null,
    restoringSeq,
    restoreError,
    restoreBlockedReason,
    restore,
  };
}

export type PartVersions = ReturnType<typeof usePartVersions>;
