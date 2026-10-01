/**
 * Repairs offered on a feature (re-pick a lost face, re-pick moved edges)
 * and closing the open editor.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { type FeatureResponse } from "../../api/parts";
import { movedEdgeWarning } from "../../features/subshapeResolution";
import { useEdgePickStore } from "../../features/edgePickStore";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { PickState } from "./usePickState";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { EditorSeat } from "./useEditorSeat";
import type { PickOverlays } from "./usePickOverlays";

type EditorRepickParams = Pick<PartDocument, "evaluation"> &
  Pick<PartBody, "editor"> &
  Pick<PickState, "setHolePick" | "setHolePickError"> &
  Pick<FeatureCatalog, "features"> &
  Pick<
    EditorSeat,
    | "setEditorError"
    | "setExtrudePreview"
    | "setFilletRadiusMm"
    | "setChamferDistanceMm"
    | "setRevolveGauge"
    | "setDraftGauge"
    | "setPatternPreview"
    | "setHoleGauge"
    | "setEditor"
  > &
  Pick<PickOverlays, "holePickRefusal"> & {
    selectFeature: (feature: FeatureResponse) => void;
  };

export function useEditorRepick({
  evaluation,
  editor,
  setHolePick,
  setHolePickError,
  features,
  setEditorError,
  setExtrudePreview,
  setFilletRadiusMm,
  setChamferDistanceMm,
  setRevolveGauge,
  setDraftGauge,
  setPatternPreview,
  setHoleGauge,
  setEditor,
  holePickRefusal,
  selectFeature,
}: EditorRepickParams) {
  // Re-pick repair for a `subshape_unresolved` feature error (FINDINGS #3). The
  // kernel re-matches a same-face reference resiliently, so this fires only for a
  // GENUINELY lost face; the one-click fix opens the feature's editor and re-arms
  // its FACE pick, so the user re-attaches the reference through the same overlay
  // that authored it. Batched with selectFeature: the hole pick-session effect
  // only clears `holePick` when the open editor is NOT a hole, and after this
  // render the editor IS the hole, so the armed pick survives.
  const repickFace = useCallback(
    (feature: FeatureResponse) => {
      selectFeature(feature);
      if (feature.feature.type !== "hole") return;
      setHolePickError(null);
      // PICK-2: the repair is offered ON a failed build, which is exactly the
      // state that can leave the evaluation with no body — and with no body
      // every pick overlay is disabled, so arming here would badge `Picking`
      // over a scene that contains no pickable target at all. The editor opens
      // either way (the feature is what the user asked to see) and states the
      // refusal on its face row; only the ARMING is withheld.
      if (holePickRefusal !== null) return;
      setHolePick("face");
    },
    [selectFeature, holePickRefusal],
  );

  // "EDGE MOVED" (EDGE-RESOLVE-WARN-1). A feature whose picked edge the kernel
  // re-found only by adjacency carries a notice in the tree and in its editor
  // (`features/subshapeResolution`). Re-picking opens the feature's editor
  // with the moved picks dropped and picking armed, on the body the feature is
  // built on (see the edge overlay query). The session effect above does the
  // dropping once it has seeded the picks, so the pending id is handed to it.
  const pendingRepick = useRef<string | null>(null);
  const repickEdges = useCallback(
    (feature: FeatureResponse) => {
      if (
        editor !== null &&
        editor.mode === "edit" &&
        editor.featureId === feature.id
      ) {
        useEdgePickStore.getState().repickMoved();
        return;
      }
      pendingRepick.current = feature.id;
      selectFeature(feature);
    },
    [editor, selectFeature],
  );
  // The OPEN editor's notice: the same derivation the tree row uses, for the
  // feature under edit. Not dismissable there: the editor is the answer.
  const editorMovedEdge = useMemo(() => {
    if (editor === null || editor.mode !== "edit" || !editor.featureId) {
      return null;
    }
    const feature = features.find((f) => f.id === editor.featureId);
    if (feature === undefined) return null;
    const result = evaluation.data?.features.find(
      (r) => r.feature_id === feature.id,
    );
    return movedEdgeWarning(feature, features, result);
  }, [editor, features, evaluation.data]);
  // Dismissed notices, by `MovedEdgeWarning.key`: session state, remembered
  // until an EARLIER feature changes (a new re-match brings it back).
  const [dismissedMovedEdges, setDismissedMovedEdges] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const dismissMovedEdge = useCallback((key: string) => {
    setDismissedMovedEdges((previous) => new Set(previous).add(key));
  }, []);

  const closeEditor = useCallback(() => {
    setEditor(null);
    setEditorError(null);
    setExtrudePreview(null);
    // The gauge OVERRIDES are reset by `setEditor` itself, for every transition
    // and not just this one — see its note. What is left here is the other
    // half: the editors' PROJECTIONS (the live value the viewport draws its
    // preview from). Those are nulled by each editor's own unmount, and a close
    // that does not unmount one — a retarget — would otherwise leave an arc or
    // a row drawn on the feature you just left.
    setFilletRadiusMm(null);
    setChamferDistanceMm(null);
    setRevolveGauge(null);
    setDraftGauge(null);
    setPatternPreview(null);
    setHoleGauge(null);
  }, [setEditor]);
  return {
    repickFace,
    pendingRepick,
    repickEdges,
    editorMovedEdge,
    dismissedMovedEdges,
    dismissMovedEdge,
    closeEditor,
  };
}

export type EditorRepick = ReturnType<typeof useEditorRepick>;
