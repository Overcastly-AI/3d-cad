/**
 * The edge- and face-pick session lifecycles, the sheet-metal previews,
 * the gauge anchors and the pre-selection mirror (create sessions only).
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */
import { formatLength } from "@loft/design";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  cornerReliefBendHighlights,
  type EdgeFlangeSpanPreview,
} from "../../features/sheetMetal";
import { useEdgePickStore } from "../../features/edgePickStore";
import { useFacePickStore } from "../../features/facePickStore";
import { usePreselectStore } from "../../features/preselect";
import { datumAnchor, shellAnchor } from "../../viewport/faceAnchor";
import { holeAnchor } from "../../viewport/holeAnchor";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { PickState } from "./usePickState";
import type { SolvedSketches } from "./useSolvedSketches";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { EditorSeat } from "./useEditorSeat";
import type { PickOverlays } from "./usePickOverlays";
import type { EditorRepick } from "./useEditorRepick";

type PickSessionsParams = Pick<PartDocument, "lengthUnit"> &
  Pick<PartBody, "editor"> &
  Pick<PickState, "holePreview"> &
  Pick<SolvedSketches, "datumBasisById"> &
  Pick<FeatureCatalog, "features"> &
  Pick<EditorSeat, "datumGaugeSeed"> &
  Pick<PickOverlays, "bodyFeatureId"> &
  Pick<EditorRepick, "pendingRepick">;

export function usePickSessions({
  lengthUnit,
  editor,
  holePreview,
  datumBasisById,
  features,
  datumGaugeSeed,
  bodyFeatureId,
  pendingRepick,
}: PickSessionsParams) {
  // Edge-pick session lifecycle: a fillet/chamfer editor opens a session
  // (seeded with its persisted picks + mode); anything else closes it. Keyed on
  // `editor` identity, which only changes on an open/select/close, so the store
  // never churns mid-edit. The overlay fetch + render gate on the store.
  useEffect(() => {
    const store = useEdgePickStore.getState();
    // A re-pick asked for from the tree ("Edge moved") opened THIS editor: it
    // drops the moved picks once the session has been seeded (below).
    const repick =
      editor !== null &&
      editor.mode === "edit" &&
      editor.featureId !== undefined &&
      editor.featureId === pendingRepick.current;
    pendingRepick.current = null;
    if (
      editor !== null &&
      (editor.kind === "fillet" || editor.kind === "chamfer")
    ) {
      store.open(editor.initialPicked, editor.initial.mode === "pick");
    } else if (
      editor !== null &&
      (editor.kind === "edgeFlange" || editor.kind === "hem")
    ) {
      // An edge flange / hem always picks (a lone straight edge to fold) —
      // single-select: a click replaces the pick rather than accumulating a set.
      store.open(editor.initialPicked, true, true);
    } else {
      store.close();
      return;
    }
    if (repick) store.repickMoved();
  }, [editor]);
  // Leaving the workspace tears the edge-pick session down.
  useEffect(() => () => useEdgePickStore.getState().close(), []);

  // Corner-relief bend highlight (SM-relief-ui-1): the editor mirrors its live
  // Bend A / Bend B selection up, PartPage resolves each id to its flange's
  // stored fold-edge signature, and the viewport draws the bend line + tag
  // (`BendHighlightOverlay`) — the in-scene answer to which select option is
  // which physical corner. Cleared whenever the corner-relief editor closes.
  const [reliefBends, setReliefBends] = useState<{
    a: string;
    b: string;
  } | null>(null);
  const onReliefBendsChange = useCallback(
    (a: string, b: string) => setReliefBends({ a, b }),
    [],
  );
  useEffect(() => {
    if (editor === null || editor.kind !== "cornerRelief") {
      setReliefBends(null);
    }
  }, [editor]);
  const reliefBendHighlights = useMemo(() => {
    if (editor?.kind !== "cornerRelief" || reliefBends === null) return [];
    return cornerReliefBendHighlights(features, reliefBends.a, reliefBends.b);
  }, [editor, reliefBends, features]);

  // Edge-flange width-extent preview (§4.5.1): the editor mirrors its live
  // Full / Centered / Offset span up, and the viewport draws it ON the picked
  // edge (`FlangeSpanOverlay`) — the in-scene answer to the chosen extent.
  // Cleared whenever the edge-flange editor closes.
  const [edgeFlangeSpan, setEdgeFlangeSpan] =
    useState<EdgeFlangeSpanPreview | null>(null);
  const onEdgeFlangeSpanChange = useCallback(
    (span: EdgeFlangeSpanPreview | null) => setEdgeFlangeSpan(span),
    [],
  );
  useEffect(() => {
    if (editor?.kind !== "edgeFlange") setEdgeFlangeSpan(null);
  }, [editor]);
  const edgeFlangeSpanLabel = useMemo(
    () =>
      edgeFlangeSpan === null
        ? ""
        : formatLength(edgeFlangeSpan.spanMm, lengthUnit, { unitSuffix: true }),
    [edgeFlangeSpan, lengthUnit],
  );

  // Face-pick session lifecycle: a shell OR draft editor opens a session
  // (seeded with its persisted picked faces), anything else closes it. Keyed on
  // `editor` identity (only changes on open/select/close), so the store never
  // churns mid-edit. The overlay fetch + render gate on the store.
  useEffect(() => {
    const store = useFacePickStore.getState();
    if (
      editor !== null &&
      (editor.kind === "shell" || editor.kind === "draft")
    ) {
      store.open(editor.initialPickedFaces);
    } else {
      store.close();
    }
  }, [editor]);
  // Leaving the workspace tears the face-pick session down.
  useEffect(() => () => useFacePickStore.getState().close(), []);

  // ---------------------------------------------------------------------
  // Pre-selection mirror (UI-W3). The in-canvas overlays write their picks to
  // the edge/face pick stores, which are SESSION state — closing the editor
  // wipes them. These two effects copy the live picks out to the pre-selection
  // while a session is open, so the selection survives the command that made
  // it and the next command opens seeded. Guarded on `active`, so the store's
  // own teardown (`close()` → picked: []) never erases what it just published.
  // ---------------------------------------------------------------------
  const shellPickedFaces = useFacePickStore((s) => s.picked);
  const shellSessionOpen = useFacePickStore((s) => s.active);
  const shellPickOverlay = useFacePickStore((s) => s.overlay);

  /**
   * Where each CRAFT-9b gauge stands. Resolved HERE and handed down as a value:
   * the gauges never read a pick store, so W4's persistent selection store
   * (CRAFT-12) re-wires these two lines rather than rewriting two components.
   * The datum seat also needs the datum-resolution table, which this page
   * already owns — one walk, not a second copy of it inside the viewport.
   */
  const shellGaugeAnchor = useMemo(
    () => shellAnchor(shellPickOverlay, shellPickedFaces),
    [shellPickOverlay, shellPickedFaces],
  );
  const datumGaugeAnchor = useMemo(
    () =>
      datumAnchor(
        datumGaugeSeed,
        (featureId) => datumBasisById.get(featureId) ?? null,
      ),
    [datumGaugeSeed, datumBasisById],
  );
  // The hole instruments stand on the editor's live face + drill point — the
  // SAME mirror the placement overlay draws from, so the bore is drawn exactly
  // where the crosshair says the drill goes.
  const holeGaugeAnchor = useMemo(
    () =>
      holePreview?.signature == null || holePreview.position === null
        ? null
        : holeAnchor(holePreview.signature, holePreview.position),
    [holePreview],
  );
  // CREATE sessions only. An edit's picks are the feature's own, made on the
  // body it is built on, and Cancel must leave nothing of them behind: mirrored,
  // they outlived the Cancel and seeded the next command with picks on a body
  // that is not the tip, stamped with the tip's id. Read from a ref the LAST
  // editor sets, not from `editingFeatureId`: the render that closes an edit
  // still sees its session open, with `editingFeatureId` already null.
  const pickSessionIsEdit = useRef(false);
  useEffect(() => {
    if (editor !== null) pickSessionIsEdit.current = editor.mode === "edit";
  }, [editor]);
  useEffect(() => {
    if (!shellSessionOpen || bodyFeatureId === null) return;
    if (pickSessionIsEdit.current) return;
    usePreselectStore.getState().rememberFaces(
      shellPickedFaces.map((signature) => ({
        signature,
        anchorId: bodyFeatureId,
      })),
    );
  }, [shellSessionOpen, shellPickedFaces, bodyFeatureId]);

  const edgePickedEdges = useEdgePickStore((s) => s.picked);
  const edgeSessionOpen = useEdgePickStore((s) => s.active);
  const edgeSessionPurpose = useEdgePickStore((s) => s.purpose);
  useEffect(() => {
    if (!edgeSessionOpen || pickSessionIsEdit.current) return;
    // Projected edges are the sketch's, not a selection to carry forward.
    if (edgeSessionPurpose === "project") return;
    usePreselectStore.getState().rememberEdges(edgePickedEdges, bodyFeatureId);
  }, [edgeSessionOpen, edgeSessionPurpose, edgePickedEdges, bodyFeatureId]);
  return {
    onReliefBendsChange,
    reliefBendHighlights,
    edgeFlangeSpan,
    onEdgeFlangeSpanChange,
    edgeFlangeSpanLabel,
    shellPickedFaces,
    shellGaugeAnchor,
    datumGaugeAnchor,
    holeGaugeAnchor,
  };
}

export type PickSessions = ReturnType<typeof usePickSessions>;
