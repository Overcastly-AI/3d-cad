/**
 * Entering a sketch, importing a STEP body or a `.loft` part, and toggling
 * Measure. Split out of `PartPage.tsx` (SPLIT-PARTPAGE).
 */

import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useCallback, useState } from "react";

import { useMeasureStore } from "../../measure/store";
import { importLoftFile } from "../../api/importLoft";
import { importStep } from "../../api/parts";
import { precheckStepFile, stepFeatureName } from "../../features/import";
import {
  precheckLoftFile,
  useLoftImportNotice,
} from "../../features/loftImport";
import type { PartDocument } from "./usePartDocument";
import type { SketchPersistence } from "./useSketchPersistence";
import type { EditorSeat } from "./useEditorSeat";
import type { ActionFlags } from "./useActionFlags";
import type { TreeWrites } from "./useTreeWrites";

type WorkspaceActionsParams = Pick<PartDocument, "partId" | "begin"> &
  Pick<SketchPersistence, "setSyncError" | "lastSynced" | "failedRevision"> &
  Pick<EditorSeat, "setSelectedFeatureId" | "setEditor"> &
  Pick<ActionFlags, "setImporting" | "setImportError"> &
  Pick<
    TreeWrites,
    | "freshTreeVersion"
    | "refreshTreeAndBody"
    | "beginTreeWrite"
    | "endTreeWrite"
    | "noteWrittenTreeVersion"
  >;

export function useWorkspaceActions({
  partId,
  begin,
  setSyncError,
  lastSynced,
  failedRevision,
  setSelectedFeatureId,
  setEditor,
  setImporting,
  setImportError,
  freshTreeVersion,
  refreshTreeAndBody,
  beginTreeWrite,
  endTreeWrite,
  noteWrittenTreeVersion,
}: WorkspaceActionsParams) {
  /** Enter sketch mode: reset the sync bookkeeping, drop any open editor. */
  const handleNewSketch = useCallback(() => {
    lastSynced.current = 0;
    failedRevision.current = null;
    setSyncError(null);
    setEditor(null);
    setSelectedFeatureId(null);
    setImportError(null);
    useMeasureStore.getState().deactivate();
    begin();
  }, [begin]);

  // STEP import: read the chosen file's bytes and POST them to the import route
  // as the base body (§2b). Client-side size/extension pre-checks give instant
  // feedback, but the server is the source of truth — its envelope message
  // (import_too_large / import_empty / import_not_step / import_with_prior_body)
  // is surfaced verbatim. On success the tree + evaluate + mesh refetch so the
  // imported body appears in BOTH the feature tree and the viewport (the #2
  // render path every other feature creation uses).
  const handleImportStep = useCallback(
    (file: File) => {
      useMeasureStore.getState().deactivate();
      setEditor(null);
      setSelectedFeatureId(null);
      setImportError(null);
      const preError = precheckStepFile(file);
      if (preError !== null) {
        setImportError(preError);
        return;
      }
      setImporting(true);
      beginTreeWrite();
      void (async () => {
        try {
          const bytes = await file.arrayBuffer();
          const response = await importStep(
            partId,
            bytes,
            stepFeatureName(file.name),
            await freshTreeVersion(),
          );
          noteWrittenTreeVersion(response.tree_version);
          setSelectedFeatureId(response.feature.id);
          await refreshTreeAndBody();
        } catch (error) {
          setImportError(
            error instanceof Error
              ? error.message
              : "The STEP file could not be imported.",
          );
        } finally {
          setImporting(false);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      freshTreeVersion,
      refreshTreeAndBody,
      beginTreeWrite,
      endTreeWrite,
      noteWrittenTreeVersion,
    ],
  );

  // .loft import: the file becomes a NEW part (docs/FILE-FORMAT.md), so on
  // success the workspace moves to it; the server's warnings ride across in
  // `useLoftImportNotice` and show on the page it lands on. A refusal is the
  // server's own envelope message, in the same Import-failed card STEP uses.
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [importingLoft, setImportingLoft] = useState(false);
  const handleImportLoft = useCallback(
    (file: File) => {
      setImportError(null);
      const preError = precheckLoftFile(file);
      if (preError !== null) {
        setImportError(preError);
        return;
      }
      setImportingLoft(true);
      void (async () => {
        try {
          const response = await importLoftFile(await file.arrayBuffer());
          useLoftImportNotice
            .getState()
            .show(response.part.id, response.warnings ?? []);
          await queryClient.invalidateQueries({ queryKey: ["parts"] });
          await navigate({
            to: "/parts/$partId",
            params: { partId: response.part.id },
          });
        } catch (error) {
          setImportError(
            error instanceof Error
              ? error.message
              : "The .loft file could not be imported.",
          );
        } finally {
          setImportingLoft(false);
        }
      })();
    },
    [queryClient, navigate],
  );

  /** Toggle the Measure tool; arming it drops any open feature editor. */
  const toggleMeasure = useCallback(() => {
    const store = useMeasureStore.getState();
    if (store.active) {
      store.deactivate();
      return;
    }
    setEditor(null);
    setSelectedFeatureId(null);
    store.activate();
  }, []);
  return {
    handleNewSketch,
    handleImportStep,
    handleImportLoft,
    importingLoft,
    toggleMeasure,
  };
}

export type WorkspaceActions = ReturnType<typeof useWorkspaceActions>;
