/**
 * Feature-tree actions: disjoint recovery, suppress, delete (asked first),
 * rename, reorder, and the context menus' open state.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import {
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useState,
} from "react";

import { useMeasureStore } from "../../measure/store";
import { useSketchStore } from "../../sketch/store";
import {
  type BooleanParams,
  deleteFeature,
  renameFeature,
  type FeatureResponse,
  type FeatureDependent,
  fetchFeatureDependents,
  fetchFeatureTree,
  FeatureHasDependentsError,
  StaleTreeVersionError,
  suppressFeature,
  updateFeature,
  FeatureOrderRefusedError,
  reorderFeatures,
} from "../../api/parts";
import { type FeatureOrderRefusal } from "../../components/FeatureTreePanel";
import type { PartDocument } from "./usePartDocument";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { EditorSeat } from "./useEditorSeat";
import type { TreeWrites } from "./useTreeWrites";
import type { EditorRepick } from "./useEditorRepick";

type TreeActionsParams = Pick<PartDocument, "partId" | "queryClient" | "mode"> &
  Pick<FeatureCatalog, "features"> &
  Pick<EditorSeat, "selectedFeatureId" | "setSelectedFeatureId"> &
  Pick<
    TreeWrites,
    | "freshTreeVersion"
    | "refreshTreeAndBody"
    | "beginTreeWrite"
    | "endTreeWrite"
    | "noteWrittenTreeVersion"
  > &
  Pick<EditorRepick, "closeEditor"> & {
    selectFeature: (feature: FeatureResponse) => void;
  };

export function useTreeActions({
  partId,
  queryClient,
  mode,
  features,
  selectedFeatureId,
  setSelectedFeatureId,
  freshTreeVersion,
  refreshTreeAndBody,
  beginTreeWrite,
  endTreeWrite,
  noteWrittenTreeVersion,
  selectFeature,
  closeEditor,
}: TreeActionsParams) {
  // Guided recovery for a `boolean_disjoint` rebuild error (MB-4c): re-run the
  // failing boolean with `allow_disjoint` on, so its disconnected pieces become
  // ONE multi-lump body instead of a dead-end error. An in-place PATCH of the
  // existing boolean feature (never a second boolean) — freshest tree version,
  // retry once on a stale-version race, then refresh the tree + body.
  const [disjointRecovering, setDisjointRecovering] = useState(false);
  const keepAsOneBody = useCallback(
    (feature: FeatureResponse) => {
      if (feature.feature.type !== "boolean") return;
      const params: BooleanParams = {
        ...feature.feature.params,
        allow_disjoint: true,
      };
      setDisjointRecovering(true);
      beginTreeWrite();
      void (async () => {
        try {
          const attempt = (version: number) =>
            updateFeature(partId, feature.id, {
              expected_tree_version: version,
              feature: { type: "boolean", version: 1, params },
            });
          let response;
          try {
            response = await attempt(await freshTreeVersion());
          } catch {
            response = await attempt(
              (await fetchFeatureTree(partId)).tree_version,
            );
          }
          noteWrittenTreeVersion(response.tree_version);
          setSelectedFeatureId(feature.id);
          await refreshTreeAndBody();
        } catch {
          // A hard failure leaves the boolean_disjoint error row in place — the
          // recovery button reappears so the user can retry. Nothing changed.
        } finally {
          setDisjointRecovering(false);
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

  // Suppress toggle (feature-tree.md §4.3a): flip a feature's suppress flag so a
  // rebuild SKIPS it (the body builds off the non-suppressed prefix) — the row
  // stays in the tree, just dimmed. A minimal, param-untouching mutation; like
  // every tree write it takes the freshest tree version and refreshes the tree +
  // body. On a stale-version race (422) it refetches the fresh version and
  // retries once (OCC soft-resync, matching moveRollback / keepAsOneBody) so the
  // toggle can never leave the UI out of sync.
  const [suppressingId, setSuppressingId] = useState<string | null>(null);
  const toggleSuppress = useCallback(
    (feature: FeatureResponse) => {
      if (suppressingId !== null) return;
      const next = !(feature.feature.suppressed ?? false);
      // Rebuilding the body invalidates a mid-measure pick index — disarm the
      // tool, as every other tree-mutating path does.
      useMeasureStore.getState().deactivate();
      setSuppressingId(feature.id);
      beginTreeWrite();
      void (async () => {
        try {
          const attempt = (version: number) =>
            suppressFeature(partId, feature.id, next, version);
          let response;
          try {
            response = await attempt(await freshTreeVersion());
          } catch (error) {
            if (error instanceof StaleTreeVersionError) {
              response = await attempt(
                (await fetchFeatureTree(partId)).tree_version,
              );
            } else {
              throw error;
            }
          }
          noteWrittenTreeVersion(response.tree_version);
          setSelectedFeatureId(feature.id);
          await refreshTreeAndBody();
        } catch {
          // A hard failure leaves the feature as it was; the toggle stays put so
          // the user can retry. Nothing changed.
        } finally {
          setSuppressingId(null);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      suppressingId,
      freshTreeVersion,
      refreshTreeAndBody,
      beginTreeWrite,
      endTreeWrite,
      noteWrittenTreeVersion,
    ],
  );

  // Select a body from the Bodies panel: select its base feature — lights the
  // brass rule in both panels and opens that feature's editor (the same select
  // a tree row does). Per-body viewport highlight is MB-4.
  const selectBody = useCallback(
    (baseFeatureId: string) => {
      const feature = features.find((f) => f.id === baseFeatureId);
      if (feature !== undefined) selectFeature(feature);
    },
    [features, selectFeature],
  );

  // ---------------------------------------------------------------------
  // Right-click context menus (UI-REVIEW 2026-07-24 #10). Two surfaces, one
  // reusable primitive: the viewport menu (view snaps, tools, selection) and
  // the feature-tree row menu (edit / suppress / rename / delete). Both hold
  // only WIRED actions — a decorative menu row is a defect (mandate 3a).
  // ---------------------------------------------------------------------
  const [viewportMenu, setViewportMenu] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [treeMenu, setTreeMenu] = useState<{
    x: number;
    y: number;
    feature: FeatureResponse;
  } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [treeActionError, setTreeActionError] = useState<string | null>(null);

  /**
   * ASK BEFORE DESTROYING (UI-REVIEW F3). Delete used to fire straight off the
   * context menu with no confirmation and no dependency check; a user found out
   * what it broke when the extrude turned red on the next evaluate.
   *
   * The ask is a real question to the SERVER — `GET …/dependents`, answered by
   * the same query the delete's 409 is built from — so the confirmation names
   * the features and drawings that break, and when there are any the delete is
   * not offered at all (the server would refuse it, and a button that cannot
   * work is worse than no button). While the ask is in flight nothing is shown
   * and nothing is destroyed.
   */
  const [deleteIntent, setDeleteIntent] = useState<{
    feature: FeatureResponse;
    dependents: FeatureDependent[];
  } | null>(null);

  const requestDeleteFeature = useCallback(
    (feature: FeatureResponse) => {
      if (deletingId !== null) return;
      useMeasureStore.getState().deactivate();
      setTreeActionError(null);
      void (async () => {
        try {
          const dependents = await fetchFeatureDependents(partId, feature.id);
          setDeleteIntent({ feature, dependents });
        } catch (error) {
          setTreeActionError(
            error instanceof Error
              ? error.message
              : "What depends on this feature could not be read.",
          );
        }
      })();
    },
    [partId, deletingId],
  );

  // Delete a feature (OCC, stale-version retry once) — the same write grammar
  // suppress uses; a hard failure surfaces the server's message, never silent.
  const deleteFeatureAction = useCallback(
    (feature: FeatureResponse) => {
      if (deletingId !== null) return;
      useMeasureStore.getState().deactivate();
      setDeletingId(feature.id);
      setTreeActionError(null);
      beginTreeWrite();
      void (async () => {
        try {
          const attempt = (version: number) =>
            deleteFeature(partId, feature.id, version);
          let restored;
          try {
            restored = await attempt(await freshTreeVersion());
          } catch (error) {
            if (error instanceof StaleTreeVersionError) {
              restored = await attempt(
                (await fetchFeatureTree(partId)).tree_version,
              );
            } else {
              throw error;
            }
          }
          noteWrittenTreeVersion(restored.tree_version);
          if (selectedFeatureId === feature.id) {
            setSelectedFeatureId(null);
            closeEditor();
          }
          if (renamingId === feature.id) setRenamingId(null);
          setDeleteIntent(null);
          await refreshTreeAndBody();
        } catch (error) {
          // A clean pre-check is not a promise: another client could have added
          // a reference in between, and the delete re-checks under the row lock.
          // Re-open the confirmation with the names the REFUSAL carried, rather
          // than reducing them to an error string.
          if (error instanceof FeatureHasDependentsError) {
            setDeleteIntent({ feature, dependents: error.dependents });
          } else {
            setDeleteIntent(null);
            setTreeActionError(
              error instanceof Error
                ? error.message
                : "The feature could not be deleted.",
            );
          }
        } finally {
          setDeletingId(null);
          endTreeWrite();
        }
      })();
    },
    [
      partId,
      deletingId,
      selectedFeatureId,
      renamingId,
      freshTreeVersion,
      refreshTreeAndBody,
      closeEditor,
      beginTreeWrite,
      endTreeWrite,
      noteWrittenTreeVersion,
    ],
  );

  // Commit an inline rename: a no-op when unchanged/blank (the field just
  // closes); otherwise a minimal name-only PATCH (never touches params).
  const commitRename = useCallback(
    (feature: FeatureResponse, nextName: string) => {
      const name = nextName.trim();
      setRenamingId(null);
      if (name === "" || name === feature.name) return;
      setTreeActionError(null);
      void (async () => {
        try {
          const attempt = (version: number) =>
            renameFeature(partId, feature.id, name, version);
          try {
            await attempt(await freshTreeVersion());
          } catch (error) {
            if (error instanceof StaleTreeVersionError) {
              await attempt((await fetchFeatureTree(partId)).tree_version);
            } else {
              throw error;
            }
          }
          await queryClient.invalidateQueries({
            queryKey: ["features", partId],
          });
        } catch (error) {
          setTreeActionError(
            error instanceof Error
              ? error.message
              : "The feature could not be renamed.",
          );
        }
      })();
    },
    [partId, freshTreeVersion, queryClient],
  );

  // REORDER (REACH-ORDER). Apply a new BUILD ORDER — the full permutation the
  // documents route takes — under the same write grammar every other tree edit
  // uses: freshest version, one soft-resync retry on a stale-version race, then
  // refresh tree + body. The order is what a feature MEANS (a fillet before a
  // hole and after it are different solids), so this is a full rebuild, and
  // `beginTreeWrite` holds SOLVE at "Solving…" from the click until the rebuilt
  // body is on screen.
  //
  // A `reference_not_earlier` refusal is HANDED BACK rather than raised as a
  // banner: the tree states it at the seat the drop was aimed at, where the
  // user is looking, and offers the legal seat. Everything else is a real
  // failure and surfaces the server's own message.
  const reorderTree = useCallback(
    async (order: string[]): Promise<FeatureOrderRefusal | null> => {
      useMeasureStore.getState().deactivate();
      setTreeActionError(null);
      beginTreeWrite();
      try {
        const attempt = (version: number) =>
          reorderFeatures(partId, order, version);
        let restored;
        try {
          restored = await attempt(await freshTreeVersion());
        } catch (error) {
          if (error instanceof StaleTreeVersionError) {
            restored = await attempt(
              (await fetchFeatureTree(partId)).tree_version,
            );
          } else {
            throw error;
          }
        }
        noteWrittenTreeVersion(restored.tree_version);
        await refreshTreeAndBody();
        return null;
      } catch (error) {
        if (error instanceof FeatureOrderRefusedError) {
          return {
            featureId: error.featureId,
            referencesFeatureId: error.referencesFeatureId,
          };
        }
        setTreeActionError(
          error instanceof Error
            ? error.message
            : "The feature order could not be changed.",
        );
        return null;
      } finally {
        endTreeWrite();
      }
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

  // Viewport right-click: open the menu at the pointer when the view rig owns
  // the camera (mode off), or while sketching, where it is the SKETCH's menu
  // (Break link, construction, delete), acting on the selection or, with
  // nothing selected, on the entity under the pointer — Fusion's right-click.
  // The plane-pick step owns its own gestures.
  const openViewportMenu = useCallback(
    (event: ReactMouseEvent) => {
      if (mode !== "off" && mode !== "draw") return;
      if (mode === "draw") {
        const sketch = useSketchStore.getState();
        if (sketch.selection.length === 0 && sketch.hoverPick !== null) {
          sketch.togglePick(sketch.hoverPick);
        }
      }
      event.preventDefault();
      setTreeMenu(null);
      setViewportMenu({ x: event.clientX, y: event.clientY });
    },
    [mode],
  );

  // Feature-row right-click: open the row menu at the pointer.
  const openTreeMenu = useCallback(
    (feature: FeatureResponse, x: number, y: number) => {
      setViewportMenu(null);
      setTreeMenu({ x, y, feature });
    },
    [],
  );
  return {
    disjointRecovering,
    keepAsOneBody,
    suppressingId,
    toggleSuppress,
    selectBody,
    viewportMenu,
    setViewportMenu,
    treeMenu,
    setTreeMenu,
    renamingId,
    setRenamingId,
    deletingId,
    treeActionError,
    setTreeActionError,
    deleteIntent,
    setDeleteIntent,
    requestDeleteFeature,
    deleteFeatureAction,
    commitRename,
    reorderTree,
    openViewportMenu,
    openTreeMenu,
  };
}

export type TreeActions = ReturnType<typeof useTreeActions>;
