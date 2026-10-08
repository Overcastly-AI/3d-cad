import { ContextMenu } from "@loft/design";
import { useCallback, useEffect } from "react";

import { useMeasureStore } from "../measure/store";
import { MeasureReadout } from "../components/MeasureReadout";
import { AuthoringViewCube } from "../components/AuthoringViewCube";
import { type FeatureResponse } from "../api/parts";
import { Breadcrumb } from "../components/Breadcrumb";
import { DocumentUnitSelect } from "../components/DocumentUnitSelect";
import { DocumentUnitProvider } from "../units/documentUnit";
import { ChromeRailProvider } from "../components/ChromeRail";
import { FeatureDeleteConfirm } from "../components/FeatureDeleteConfirm";
import { defaultCombineForm } from "../features/boolean";
import { SketchDro } from "../components/SketchDro";
import { SolveDiagnostic } from "../components/SolveDiagnostic";
import { TimelineStrip } from "../components/TimelineStrip";
import { TopBar } from "../components/TopBar";
import { TopToolbar } from "../components/TopToolbar";
import { resolveSketchKey } from "../sketch/constraints";
import { isTypingTarget } from "../lib/isTypingTarget";
import { undoRedoStep } from "../lib/undoRedoShortcut";
import { ProposalNote } from "../viewport/ProposalNote";
import { useSketchStore } from "../sketch/store";
import { TOOL_SHORTCUTS } from "../sketch/tools";
import {
  KEY_MEASURE,
  KEY_SNAP,
  PART_CREATE_SHORTCUTS,
} from "../shortcuts/registry";
import { LeaveSketchPrompt } from "./LeaveSketchPrompt";
import { SketchScene } from "../viewport/SketchScene";
import { Viewport } from "../viewport/Viewport";
import { editorForFeature } from "./part/featureEditors";
import {
  TreeActionErrorNote,
  DraftRestoredNote,
  BodyNotices,
  ActionNotices,
  LoftImportNotice,
} from "./part/WorkspaceNotices";
import { InspectorRail, FeatureTreeRail } from "./part/PartSidePanels";
import { PartViewportLayers } from "./part/PartViewportLayers";
import { FeatureEditorSeat } from "./part/FeatureEditorSeat";
import { PartCommandBand } from "./part/PartCommandBand";
import { treeMenuSections, viewportMenuSections } from "./part/contextMenus";
import { usePartDocument } from "./part/usePartDocument";
import { usePartBody } from "./part/usePartBody";
import { usePickState } from "./part/usePickState";
import { useMeasureSession } from "./part/useMeasureSession";
import { useSketchPersistence } from "./part/useSketchPersistence";
import { useSolvedSketches } from "./part/useSolvedSketches";
import { useSketchEditRequests } from "./part/useSketchEditRequests";
import { useFeatureCatalog } from "./part/useFeatureCatalog";
import { useEditorSeat } from "./part/useEditorSeat";
import { useActionFlags } from "./part/useActionFlags";
import { usePickOverlays } from "./part/usePickOverlays";
import { useTreeWrites } from "./part/useTreeWrites";
import { useMaterialControls } from "./part/useMaterialControls";
import { useWorkspaceActions } from "./part/useWorkspaceActions";
import { useFeatureOpeners } from "./part/useFeatureOpeners";
import { useFlatPatternExport } from "./part/useFlatPatternExport";
import { useEditorRepick } from "./part/useEditorRepick";
import { usePickSessions } from "./part/usePickSessions";
import { useFeatureSubmit } from "./part/useFeatureSubmit";
import { useTreeActions } from "./part/useTreeActions";
import { useSketchEntry } from "./part/useSketchEntry";
import { useDatumFacePicking } from "./part/useDatumFacePicking";
import { useHolePicking } from "./part/useHolePicking";
import { useTimelineHistory } from "./part/useTimelineHistory";
import { useRebuildNotices } from "./part/useRebuildNotices";
import { useViewportState } from "./part/useViewportState";

/**
 * The part workspace: feature tree left, viewport hero, sketch mode inside
 * the viewport. Solved geometry ALWAYS comes from the evaluate payload —
 * the sketcher renders what the solver says, never its own input echo. The
 * live parametric loop: the first constraint action persists the sketch as
 * a feature; every edit after that debounce-saves, re-evaluates, and the
 * solved positions are adopted back into the buffer.
 */
export function PartPage() {
  const partDocument = usePartDocument();
  const {
    partId,
    queryClient,
    mode,
    edit,
    offset,
    mirrorRequest,
    cornerRequest,
    revision,
    featureId,
    userConstrained,
    entityCount,
    constraintCount,
    begin,
    setTool,
    toggleSnap,
    navigate,
    part,
    lengthUnit,
    tree,
    treeVersion,
    evaluation,
  } = partDocument;
  const partBody = usePartBody({ partId, queryClient, tree, evaluation });
  const {
    meshGlbId,
    bodyProperties,
    editor,
    setEditorState,
    displayTree,
    viewMeshGlbId,
    body,
    regenerating,
    regenFailed,
    hasBody,
    hasPickTargets,
  } = partBody;
  const pickState = usePickState();
  const {
    facePicking,
    setFacePicking,
    setFacePlaneBusy,
    setFacePlaneError,
    setPendingFaceIndex,
    datumFacePick,
    setDatumFacePick,
    setDatumFacePicked,
    setDatumFacePickError,
    datumFacePickNonce,
    holePick,
    setHolePick,
    setHoleFacePicked,
    setHolePointPicked,
    setHolePickError,
    holePreview,
    setHolePreview,
    holePickNonce,
  } = pickState;
  const measureSession = useMeasureSession({
    partId,
    tree,
    treeVersion,
    meshGlbId,
  });
  const { measureActive } = measureSession;
  const sketchPersistence = useSketchPersistence({
    partId,
    queryClient,
    mode,
    revision,
    featureId,
    userConstrained,
    entityCount,
    constraintCount,
    treeVersion,
    evaluation,
  });
  const {
    syncPending,
    syncError,
    setSyncError,
    lastSynced,
    failedRevision,
    draftHeld,
    leaveSaving,
    leaveGuard,
    leaveDestination,
    saveAndLeave,
  } = sketchPersistence;
  const solvedSketches = useSolvedSketches({
    mode,
    featureId,
    tree,
    evaluation,
  });
  const { datumById, datumBasisById, solved } = solvedSketches;

  // Keyboard-first: Escape cascade always; tools, snap, constraint verbs and
  // Delete while drawing. One keyboard, two vocabularies — selection
  // presence decides whether letters draw or constrain.
  useEffect(() => {
    if (mode === "off") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const store = useSketchStore.getState();
      if (event.key === "Escape") {
        event.preventDefault();
        // Face-pick has its own most-local cancel: disarm the mode, staying in
        // the plane-pick step (a second Escape then exits the sketch).
        if (facePicking) {
          setFacePicking(false);
          setFacePlaneError(null);
          return;
        }
        // ONE cascade, and the store owns it (ESC-2). Every rung — the mirror
        // and corner sub-cascades, the armed-dimension disarm, and the final
        // `unstarted` exit — is performed by `store.escape()`.
        //
        // This handler used to re-derive the rung with its own call to the
        // cascade's pure function and map `"exit"` to `finishSketch()`, which
        // SAVES, while the store maps that same verb to a fresh session, which
        // DISCARDS. The two could not disagree only because this call omitted
        // that function's fifth argument, so `unstarted` defaulted false,
        // `"exit"` was unreachable and the `finishSketch()` was dead — every press
        // fell through to `store.escape()` anyway. That is FB-13 ("a key that
        // sometimes saves and sometimes discards") lying dormant: passing that
        // argument, for any reason, would have armed it silently. A second
        // derivation of the same decision is the defect, so there is none.
        store.escape();
        return;
      }
      if (mode !== "draw") return;
      // Enter advances the mirror draft from collecting targets to the axis
      // pick — the keyboard-first path the "Choose axis" button mirrors.
      if (event.key === "Enter") {
        // Typed X / Y cells own Enter while they are open, and the Enter that
        // placed a typed point is theirs even though the cells have closed:
        // it must never also finish the spline (TYPED-POINT-RACE).
        if (event.defaultPrevented || store.pointEntry !== null) return;
        if (store.mirror?.phase === "targets") {
          event.preventDefault();
          store.advanceMirror();
          return;
        }
        // Enter commits an open spline (≥ 2 fit points) — the keyboard-first
        // finish the double-click mirrors.
        if (store.tool === "spline" && store.pending.length >= 2) {
          event.preventDefault();
          store.finishPlacement();
        }
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        if (store.selectedConstraint !== null) {
          event.preventDefault();
          store.removeConstraint(store.selectedConstraint);
        }
        return;
      }
      const key = event.key.toLowerCase();
      if (key === KEY_SNAP) {
        event.preventDefault();
        toggleSnap();
        return;
      }
      const resolved = resolveSketchKey(key, store.selection.length > 0);
      if (resolved === null) return;
      event.preventDefault();
      if (resolved.type === "constraint") {
        store.applyConstraint(resolved.action);
        return;
      }
      if (resolved.type === "construction") {
        store.toggleConstruction();
        return;
      }
      const tool = TOOL_SHORTCUTS[key];
      if (tool !== undefined) setTool(tool);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, setTool, toggleSnap, facePicking]);
  useSketchEditRequests({ mode, edit, offset, mirrorRequest, cornerRequest });
  const featureCatalog = useFeatureCatalog({
    partId,
    tree,
    evaluation,
    datumById,
  });
  const { features, sketchProfiles, bodies, specFromPlaneRef } = featureCatalog;
  const editorSeat = useEditorSeat({ setEditorState, features });
  const {
    selectedFeatureId,
    setSelectedFeatureId,
    patternScopeSeed,
    scopedFeatureIds,
    setEditorSaving,
    setEditorError,
    lastSavedFeatureId,
    setLastSavedFeatureId,
    rebuildNoticeDismissed,
    setRebuildNoticeDismissed,
    rollbackBusy,
    setRollbackBusy,
    extrudePreview,
    setExtrudePreview,
    setFilletRadiusMm,
    setChamferDistanceMm,
    datumGaugeSeed,
    revolveGauge,
    setRevolveGauge,
    setDraftGauge,
    patternPreview,
    setPatternPreview,
    setHoleGauge,
    setEditor,
  } = editorSeat;
  const actionFlags = useActionFlags({ editor, features });
  const {
    setImporting,
    setImportError,
    flatPatternBusy,
    setFlatPatternBusy,
    setFlatPatternError,
    flatDxfBusy,
    setFlatDxfBusy,
    setOffsetPlaneBusy,
    setOffsetPlaneError,
  } = actionFlags;
  const pickOverlays = usePickOverlays({
    partId,
    mode,
    tree,
    treeVersion,
    meshGlbId,
    editor,
    displayTree,
    hasBody,
    hasPickTargets,
    facePicking,
    datumFacePick,
    holePick,
    holePreview,
    measureActive,
    selectedFeatureId,
    scopedFeatureIds,
  });
  const {
    bodyFeatureId,
    holePickRefusal,
    datumPickRefusal,
    facePickRefusal,
    noteFaceHover,
    proposalContext,
    proposedFace,
    pickAnchorFeatureId,
    highlightFeatureIds,
    selectedFaceIndices,
    preselectedFaceIndices,
  } = pickOverlays;
  const treeWrites = useTreeWrites({ partId, queryClient, lengthUnit, tree });
  const {
    freshTreeVersion,
    refreshTreeAndBody,
    treeWrite,
    beginTreeWrite,
    endTreeWrite,
    noteWrittenTreeVersion,
    unitBusy,
    changeUnit,
  } = treeWrites;
  const materialPanel = useMaterialControls({
    partId,
    queryClient,
    part,
    evaluation,
    bodies,
    freshTreeVersion,
  });

  const workspaceActions = useWorkspaceActions({
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
  });
  const { handleNewSketch, toggleMeasure } = workspaceActions;

  // Measure keyboard path (mode off): M toggles the tool; Escape clears the
  // picks, then exits — the same cascade grammar the sketcher uses. Locked while
  // a feature editor is open (M would `setEditor(null)` and discard its picks).
  useEffect(() => {
    if (mode !== "off" || editor !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      const store = useMeasureStore.getState();
      if (event.key === "Escape") {
        if (!store.active) return;
        event.preventDefault();
        if (
          store.picks.length > 0 ||
          store.result !== null ||
          store.measureError !== null
        ) {
          store.reset();
        } else {
          store.deactivate();
        }
        return;
      }
      if (event.key.toLowerCase() === KEY_MEASURE) {
        event.preventDefault();
        if (store.active) {
          store.deactivate();
        } else if (hasBody) {
          setEditor(null);
          setSelectedFeatureId(null);
          store.activate();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, editor, hasBody]);
  const featureOpeners = useFeatureOpeners({
    lengthUnit,
    tree,
    setHolePick,
    setHolePickError,
    setSelectedFeatureId,
    patternScopeSeed,
    setEditorError,
    setEditor,
    bodyFeatureId,
  });
  const {
    openCreateExtrude,
    openCreateRevolve,
    openCreateSweep,
    openCreateLoft,
    openCreatePattern,
    openCreateFillet,
    openCreateChamfer,
    openCreateShell,
    openCreateDraft,
    openCreateHole,
    openCreateMirror,
    openScopedVerb,
  } = featureOpeners;
  const flatPatternExport = useFlatPatternExport({
    partId,
    navigate,
    part,
    flatPatternBusy,
    setFlatPatternBusy,
    setFlatPatternError,
    flatDxfBusy,
    setFlatDxfBusy,
  });

  // Combine needs ≥2 bodies to fuse (a boolean union names two of them). It
  // seeds the first two bodies in tree order; the user retargets either.
  const openCreateCombine = useCallback(() => {
    if (bodies.length < 2) return;
    useMeasureStore.getState().deactivate();
    setEditorError(null);
    setSelectedFeatureId(null);
    setEditor({
      kind: "combine",
      mode: "create",
      initial: defaultCombineForm(bodies),
    });
  }, [bodies]);

  const selectFeature = useCallback(
    (feature: FeatureResponse) => {
      useMeasureStore.getState().deactivate();
      setSelectedFeatureId(feature.id);
      setEditorError(null);
      if (feature.feature.type === "sketch") {
        // A SAVED SKETCH RE-OPENS IN THE SKETCHER (SKETCH-1). Every other type
        // opens a form (`part/featureEditors`); a sketch's editor IS the
        // sketcher, so this branch hydrates the session from the persisted
        // params instead — same plane, same entities, same constraints, and the
        // SAME feature id, so the next save PATCHes this sketch rather than
        // minting a second one. Without it the chain fell through to
        // `setEditor(null)` and the row click was a silent no-op: a dimension
        // could be authored once and never revised.
        const params = feature.feature.params;
        const store = useSketchStore.getState();
        // Already the open sketch — the row click is a selection, not a reload.
        // Rehydrating here would throw away the live buffer.
        if (store.mode === "draw" && store.featureId === feature.id) return;
        // Another sketch is open with edits the server has not heard yet.
        // Swapping would discard them with no way back, so refuse and name the
        // action that ends the session (FB-13: no ambiguous exits).
        if (store.mode === "draw" && store.revision > lastSynced.current) {
          setTreeActionError(
            `Finish the open sketch before editing ${feature.name}.`,
          );
          return;
        }
        const plane = specFromPlaneRef(params.plane);
        if (plane === null) {
          setTreeActionError(
            `${feature.name} sits on a plane that cannot be resolved here, so it cannot be re-opened.`,
          );
          return;
        }
        // Sync bookkeeping, exactly as entering a NEW sketch resets it
        // (`handleNewSketch`): the loaded buffer is revision 0, so the first
        // live edit after re-opening is correctly seen as unsynced.
        setTreeActionError(null);
        lastSynced.current = 0;
        failedRevision.current = null;
        setSyncError(null);
        setEditor(null);
        setImportError(null);
        store.beginEdit(feature.id, plane, params.entities, params.constraints);
      } else {
        setEditor(editorForFeature(feature, lengthUnit, features));
      }
    },
    // `features` joins the deps because a pattern/mirror's persisted scope is
    // shown by feature NAME, which only the tree can supply.
    [features, lengthUnit, specFromPlaneRef],
  );
  const editorRepick = useEditorRepick({
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
  });
  const { pendingRepick, closeEditor } = editorRepick;

  // Global cancel for an open feature editor (FINDINGS #11). The command band
  // advertises "CANCEL ESC", so Escape MUST disarm the editor from any focus —
  // the per-editor onKeyDown only fires when focus is inside the panel, so with
  // focus in the viewport the band's own promise was dead and the toolbar stayed
  // locked. This window-level handler is the ONE cancel path every editor's
  // Cancel cell also routes through (`closeEditor`); the editors no longer carry
  // their own Escape branch (DRY). It stands down while a hole/datum face pick is
  // armed — those pick handlers own Escape then (first Escape disarms the pick,
  // staying in the editor), exactly the cascade the Hole/Datum editors deferred
  // to before. Not registered in sketch mode (the sketch cascade owns Escape).
  useEffect(() => {
    if (mode !== "off" || editor === null) return;
    if (datumFacePick !== null || holePick !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      event.preventDefault();
      closeEditor();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, editor, datumFacePick, holePick, closeEditor]);
  const pickSessions = usePickSessions({
    lengthUnit,
    editor,
    holePreview,
    datumBasisById,
    features,
    datumGaugeSeed,
    bodyFeatureId,
    pendingRepick,
  });
  const { shellPickedFaces } = pickSessions;
  const featureSubmit = useFeatureSubmit({
    partId,
    editor,
    features,
    setSelectedFeatureId,
    setEditorSaving,
    setEditorError,
    setLastSavedFeatureId,
    setRebuildNoticeDismissed,
    setEditor,
    freshTreeVersion,
    refreshTreeAndBody,
    beginTreeWrite,
    endTreeWrite,
    noteWrittenTreeVersion,
  });
  const treeActions = useTreeActions({
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
  });
  const {
    toggleSuppress,
    viewportMenu,
    setViewportMenu,
    treeMenu,
    setTreeMenu,
    setRenamingId,
    deletingId,
    setTreeActionError,
    deleteIntent,
    setDeleteIntent,
    requestDeleteFeature,
    deleteFeatureAction,
    openViewportMenu,
    openTreeMenu,
  } = treeActions;
  const sketchEntry = useSketchEntry({
    partId,
    queryClient,
    tree,
    facePicking,
    setFacePicking,
    setFacePlaneBusy,
    setFacePlaneError,
    setPendingFaceIndex,
    features,
    setOffsetPlaneBusy,
    setOffsetPlaneError,
    bodyFeatureId,
    facePickRefusal,
    freshTreeVersion,
    handleNewSketch,
    openCreateExtrude,
  });
  const {
    startSketchOnFace,
    startSketch,
    acceptSketchProposal,
    acceptExtrudeProposal,
  } = sketchEntry;
  const datumFacePicking = useDatumFacePicking({
    editor,
    datumFacePick,
    setDatumFacePick,
    setDatumFacePicked,
    setDatumFacePickError,
    datumFacePickNonce,
    bodyFeatureId,
    datumPickRefusal,
    pickAnchorFeatureId,
  });

  // Escape disarms an armed datum face pick (staying in the editor) — the most
  // local cancel, mirroring the sketch-on-face Escape. Registered only while a
  // pick is armed; the editor's own Escape (cancel) stands down in that window.
  useEffect(() => {
    if (datumFacePick === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setDatumFacePick(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [datumFacePick]);
  const holePicking = useHolePicking({
    editor,
    holePick,
    setHolePick,
    setHoleFacePicked,
    setHolePointPicked,
    setHolePickError,
    setHolePreview,
    holePickNonce,
    bodyFeatureId,
    holePickRefusal,
    pickAnchorFeatureId,
  });

  // Escape disarms an armed hole pick (staying in the editor) — the most local
  // cancel, mirroring the datum face pick. Registered only while a pick is armed.
  useEffect(() => {
    if (holePick === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setHolePick(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [holePick]);
  const timelineHistory = useTimelineHistory({
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
  });
  const { historyStep, triggerUndo, triggerRedo, moveRollback } =
    timelineHistory;
  const rebuildNotices = useRebuildNotices({
    evaluation,
    editor,
    sketchProfiles,
    lastSavedFeatureId,
    rebuildNoticeDismissed,
  });
  const { hasSolvedSketch, canSweep, canLoft } = rebuildNotices;

  // Sketch mode owns the viewport; leaving/entering it dismisses the editor.
  useEffect(() => {
    if (mode !== "off") setEditor(null);
  }, [mode]);

  // Face-pick belongs to the plane-pick step only: a chosen plane (→ draw) or a
  // sketch exit (→ off) disarms it, so the face overlay never lingers.
  useEffect(() => {
    if (mode !== "plane") {
      setFacePicking(false);
      setFacePlaneError(null);
    }
  }, [mode]);

  // Create/Modify accelerators (mode off). Every verb the band names with a
  // `new-<id>` button and a letter is here, each gated on the same condition
  // that button uses — the same guard grammar as the Measure M accelerator.
  //
  // The letters are read from `PART_CREATE_SHORTCUTS`, never written here: this
  // table maps a key to its OPENER, the registry decides what the key IS. A
  // letter typed into this file would be a second source for the binding and
  // would drift from the reference that teaches it.
  //
  // These are LOCKED behind an open editor exactly like the pointer band is: an
  // open command owns the picks, and firing another opener would `setEditor(...)`
  // over the top, silently discarding the in-progress selection (the keyboard
  // twin of the fillet→extrude pick-loss the pointer lock closes).
  useEffect(() => {
    if (mode !== "off" || editor !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      // A proposal note on screen has FIRST claim on the letter it prints
      // (FLOW-B2, W2 direction §3.5). The note binds the same letters on
      // `window` in the CAPTURE phase and calls `preventDefault()`; this
      // listener is a bubble-phase one on the same target, so capture has
      // already run by the time we are here and `defaultPrevented` is the
      // signal that the note consumed the key.
      //
      // Without this line pressing `E` while the extrude offer is showing runs
      // BOTH handlers: the note's accept (extrude seeded with the offered
      // profile) and then this opener's generic `openCreateExtrude`, which
      // `setEditor(...)`s over the top with the DEFAULT profile. The editor is
      // open either way and looks right — the profile is merely the wrong one,
      // which is the silent-wrong-result class rather than a visible break.
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      // The keys come from `shortcuts/registry` — the SAME table the key card
      // prints (UI-REVIEW F4), so a re-keyed verb cannot leave the reference
      // teaching a letter nothing listens for.
      const key = event.key.toLowerCase();
      // Each row's `enabled` is the condition the band's own button uses for
      // the same verb, so the keyboard and the pointer can never disagree about
      // whether a verb is available.
      const openers: Record<string, { open: () => void; enabled: boolean }> = {
        k: { open: startSketch, enabled: true },
        e: { open: openCreateExtrude, enabled: hasSolvedSketch },
        r: { open: openCreateRevolve, enabled: hasSolvedSketch },
        f: { open: openCreateFillet, enabled: hasBody },
        c: { open: openCreateChamfer, enabled: hasBody },
        p: { open: openCreatePattern, enabled: hasBody },
        s: { open: openCreateSweep, enabled: canSweep },
        l: { open: openCreateLoft, enabled: canLoft },
        h: { open: openCreateShell, enabled: hasBody },
        d: { open: openCreateDraft, enabled: hasBody },
        o: { open: openCreateHole, enabled: hasBody },
        i: { open: openCreateMirror, enabled: hasBody },
      };
      const opener = PART_CREATE_SHORTCUTS.some((entry) => entry.key === key)
        ? openers[key]
        : undefined;
      if (opener !== undefined && opener.enabled) {
        event.preventDefault();
        opener.open();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    mode,
    editor,
    hasBody,
    hasSolvedSketch,
    canSweep,
    canLoft,
    startSketch,
    openCreateExtrude,
    openCreateRevolve,
    openCreateFillet,
    openCreateChamfer,
    openCreatePattern,
    openCreateSweep,
    openCreateLoft,
    openCreateShell,
    openCreateDraft,
    openCreateHole,
    openCreateMirror,
  ]);

  // Undo/redo keyboard grammar: Ctrl/⌘+Z, Ctrl/⌘+Shift+Z, Ctrl+Y — model idle
  // only. Sketch mode owns its own buffer (sketch-internal undo is a later,
  // finer-grained layer — docs/design/undo-redo.md "out of v1"), and an open
  // editor locks the band's History tools, so the keys hold to the same gate.
  // A focused text field keeps its NATIVE undo (the typing-target guard is
  // resolved inside the pure grammar helper).
  useEffect(() => {
    if (mode !== "off" || editor !== null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const step = undoRedoStep(event, isTypingTarget(event.target));
      if (step === null) return;
      // The chord is ours in the workspace even at a history bound — swallow
      // it so the browser never runs its own undo behind the tool.
      event.preventDefault();
      if (step === "undo") triggerUndo();
      else triggerRedo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, editor, triggerUndo, triggerRedo]);
  const viewportState = useViewportState({
    partId,
    mode,
    part,
    tree,
    evaluation,
    bodyProperties,
    editor,
    viewMeshGlbId,
    body,
    regenerating,
    regenFailed,
    measureActive,
    solved,
    features,
    extrudePreview,
    revolveGauge,
    patternPreview,
    treeWrite,
    shellPickedFaces,
  });
  const { showExtrudeGhost, isEmptyPart, activeCommand } = viewportState;

  // Context-menu section builders (UI-REVIEW #10): `part/contextMenus`.
  const buildViewportSections = () =>
    viewportMenuSections({
      selectedFeatureId,
      features,
      hasBody,
      measureActive,
      deletingId,
      startSketch,
      startSketchOnFace,
      toggleMeasure,
      toggleSuppress,
      requestDeleteFeature,
    });

  const buildTreeSections = (feature: FeatureResponse) =>
    treeMenuSections(feature, {
      hasBody,
      deletingId,
      selectFeature,
      setSelectedFeatureId,
      setRenamingId,
      toggleSuppress,
      requestDeleteFeature,
      openScopedVerb,
    });

  // The breadcrumb's mode leaf: sketch step / measure / open command / model.
  const workspaceMode =
    mode === "draw"
      ? "Sketch"
      : mode === "plane"
        ? "Pick a plane"
        : measureActive
          ? "Measure"
          : activeCommand;

  return (
    <DocumentUnitProvider unit={lengthUnit}>
      <div className="flex h-full flex-col">
        <TopBar>
          <Breadcrumb
            register="parts"
            documentName={part.data?.name ?? "Part"}
            documentTestId="part-name"
            mode={workspaceMode}
          />
          <DocumentUnitSelect
            value={lengthUnit}
            onChange={changeUnit}
            busy={unitBusy}
          />
        </TopBar>
        {/* The full-width command band, directly under the brand bar: the
          mode-aware CAD top-toolbar. Sketch tools while sketching, the
          feature-create tools otherwise — one edge-to-edge surface, the
          viewport below it. */}
        <TopToolbar>
          <PartCommandBand
            partDocument={partDocument}
            timelineHistory={timelineHistory}
            editorSeat={editorSeat}
            sketchEntry={sketchEntry}
            pickOverlays={pickOverlays}
            actionFlags={actionFlags}
            workspaceActions={workspaceActions}
            featureOpeners={featureOpeners}
            rebuildNotices={rebuildNotices}
            partBody={partBody}
            featureCatalog={featureCatalog}
            flatPatternExport={flatPatternExport}
            measureSession={measureSession}
            viewportState={viewportState}
            editorRepick={editorRepick}
            sketchPersistence={sketchPersistence}
            pickState={pickState}
            openCreateCombine={openCreateCombine}
          />
        </TopToolbar>
        {/* Full-bleed scene: the canvas owns the frame; the tree + inspector
          FLOAT over it as collapsible instruments (Batch 1 makeover, P0-4) —
          no more columns subtracted from the viewport. */}
        <main className="relative min-h-0 grow">
          {/* One column per side, shared by the feature editors and the panels
              they were opened from — so an editor can never be opened on top of
              the model it is editing (FB-7). The editors' JSX stays where it is
              inside the HUD; they relocate themselves into the rail by portal,
              which keeps the ~400-line editor switch out of this diff and keeps
              them working unchanged on the surfaces that have no rail. */}
          <ChromeRailProvider>
            <Viewport
              glb={body.data}
              onContextMenu={openViewportMenu}
              rotateEnabled={mode !== "draw"}
              groundGrid={mode !== "draw"}
              viewNav={mode === "off"}
              sketchNav={mode === "draw"}
              bodyInteractive={
                mode === "off" && editor === null && !measureActive
              }
              onFaceHover={noteFaceHover}
              bodySelected={
                mode === "off" &&
                !measureActive &&
                (highlightFeatureIds.length > 0 ||
                  preselectedFaceIndices !== null)
              }
              bodySelectedFaces={selectedFaceIndices ?? preselectedFaceIndices}
              hud={
                <>
                  {/* CRAFT-6 — the reference cube PERSISTS through plane pick
                    and sketch, where orientation matters most. `viewNav` above
                    still unmounts the view RAIL (and with it `view-projection`,
                    a mode the sketch rig cannot honour — see `ProjectionRig`);
                    only the cube comes back, and it comes back HERE rather
                    than as a second prop on `Viewport` because the hud slot
                    already seats chrome in that frame. It is interactive:
                    facet clicks steer without fighting the sketch rig, which
                    is measured in `AuthoringViewCube`'s own comment. */}
                  {mode !== "off" ? <AuthoringViewCube /> : null}
                  <SketchDro solving={syncPending || evaluation.isFetching} />
                  <SolveDiagnostic />
                  <MeasureReadout />
                  {/* THE ONE PROPOSAL NOTE. Rest on a face with nothing armed
                    and it offers the sketch that face affords (FLOW-1); solve a
                    sketch and it offers the extrude that profile affords
                    (FLOW-B1). It proposes; the click, the letter or Enter
                    disposes — and at most one note is ever on screen, with the
                    pointer-addressed one winning. */}
                  <ProposalNote
                    enabled={proposalContext}
                    face={proposedFace}
                    onAccept={acceptSketchProposal}
                    // NOT `proposalContext`: that one also demands a body, and
                    // the first sketch on an empty part is exactly the moment
                    // this offer exists for.
                    extrudeEnabled={
                      mode === "off" && editor === null && !measureActive
                    }
                    profiles={sketchProfiles}
                    onAcceptExtrude={acceptExtrudeProposal}
                  />
                  {/* Inert DOM signal that the live extrude ghost is on screen
                    (the ghost itself is WebGL) — a raster-independent hook QA
                    drives the "preview responds before Save" assertion from. */}
                  {showExtrudeGhost && extrudePreview !== null ? (
                    <span
                      hidden
                      data-testid="extrude-preview-active"
                      data-distance-mm={extrudePreview.distanceMm}
                      data-direction={extrudePreview.direction}
                      data-operation={extrudePreview.operation}
                      data-twist-deg={extrudePreview.twistDeg}
                    />
                  ) : null}
                  {isEmptyPart ? (
                    <div
                      data-testid="empty-viewport-hint"
                      className="pointer-events-none absolute left-1/2 top-[42%] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 text-center"
                    >
                      <span className="font-display text-2xs uppercase tracking-[0.24em] text-gauge">
                        Empty part
                      </span>
                      <span className="font-body text-sm text-mist">
                        Start with a <span className="text-brass">Sketch</span>{" "}
                        — pick a plane, then draw.
                      </span>
                      <span className="font-body text-xs text-gauge">
                        Or Import a STEP solid as the base body.
                      </span>
                    </div>
                  ) : null}
                  <FeatureEditorSeat
                    partDocument={partDocument}
                    partBody={partBody}
                    featureCatalog={featureCatalog}
                    featureSubmit={featureSubmit}
                    editorRepick={editorRepick}
                    editorSeat={editorSeat}
                    rebuildNotices={rebuildNotices}
                    solvedSketches={solvedSketches}
                    pickOverlays={pickOverlays}
                    pickState={pickState}
                    holePicking={holePicking}
                    pickSessions={pickSessions}
                    actionFlags={actionFlags}
                    datumFacePicking={datumFacePicking}
                  />
                  <ActionNotices
                    actionFlags={actionFlags}
                    timelineHistory={timelineHistory}
                  />
                  <LoftImportNotice partId={partId} />
                  {/* The regeneration / rebuild / partial-body notices take the
                    SAME seat the feature editors do, so they dock the same way
                    — otherwise FB-7 would have been fixed for one surface and
                    left standing on four. */}
                  <BodyNotices
                    partBody={partBody}
                    rebuildNotices={rebuildNotices}
                    editorSeat={editorSeat}
                    viewportState={viewportState}
                    featureCatalog={featureCatalog}
                    selectFeature={selectFeature}
                  />
                </>
              }
            >
              <SketchScene solved={solved} facePicking={facePicking} />
              <PartViewportLayers
                partDocument={partDocument}
                partBody={partBody}
                editorSeat={editorSeat}
                viewportState={viewportState}
                pickOverlays={pickOverlays}
                pickSessions={pickSessions}
                pickState={pickState}
                sketchEntry={sketchEntry}
                datumFacePicking={datumFacePicking}
                holePicking={holePicking}
              />
            </Viewport>
            <FeatureTreeRail
              partDocument={partDocument}
              viewportState={viewportState}
              editorSeat={editorSeat}
              treeActions={treeActions}
              editorRepick={editorRepick}
              featureCatalog={featureCatalog}
              selectFeature={selectFeature}
            />
            <InspectorRail
              viewportState={viewportState}
              partDocument={partDocument}
              partBody={partBody}
              materialPanel={materialPanel}
            />
            {/* What breaks if this feature goes — asked before it does (F3). */}
            {deleteIntent !== null ? (
              <FeatureDeleteConfirm
                featureName={deleteIntent.feature.name}
                dependents={deleteIntent.dependents}
                pending={deletingId === deleteIntent.feature.id}
                onCancel={() => setDeleteIntent(null)}
                onConfirm={() => deleteFeatureAction(deleteIntent.feature)}
              />
            ) : null}
            {/* FLOW-A2 — the sketch came back. Silently re-opening the
                sketcher on a buffer the user last saw before a reload would be
                an app state that cannot be explained from the screen, so it
                says what happened, how much came back, and from when. Quiet by
                design: the exit ticket is where the boldness is spent.

                SEAT: the bottom-centre HUD lane (`bottom-hud-lane`), the same
                one `NavCue` and the measure readout use. It is FREE here —
                `viewNav={mode === "off"}` keeps the view rail and the cue out
                of sketch mode, and this note only ever appears in sketch mode.
                Its first draft sat at `bottom-3 left-3` and covered the
                sketcher's own DRO, which is chrome occluding chrome. */}
            <DraftRestoredNote sketchPersistence={sketchPersistence} />
            {/* Tree-action failure (rename/delete) — honest, dismissible chrome. */}
            <TreeActionErrorNote treeActions={treeActions} />
          </ChromeRailProvider>
        </main>
        {/* THE TIMELINE — docked along the bottom of the frame, the way the
            build travels (UI-W1, founder-directed). In flow, not floating: the
            bottom of the viewport already carries the HUD lane, the reference
            cube and the status banners, and a fourth floating occupant would
            fight all three. */}
        <TimelineStrip
          // While an edit shows its input body, the strip shows the stop just
          // before the feature: a display of the preview, never a stored move.
          tree={displayTree}
          previewing={displayTree !== tree.data}
          evaluation={evaluation.data}
          selectedFeatureId={selectedFeatureId}
          scopedFeatureIds={scopedFeatureIds ?? undefined}
          onSelectFeature={selectFeature}
          onMoveRollback={moveRollback}
          // The stop also holds while a history step is restoring (the mutual
          // exclusion's visible half — runHistoryStep guards it).
          busy={rollbackBusy || historyStep !== null}
          onChipContextMenu={openTreeMenu}
        />
      </div>
      {/* Right-click menus (UI-REVIEW #10) — one primitive, two surfaces. */}
      {viewportMenu !== null ? (
        <ContextMenu
          open
          x={viewportMenu.x}
          y={viewportMenu.y}
          aria-label="Viewport actions"
          data-testid="viewport-context-menu"
          sections={buildViewportSections()}
          onClose={() => setViewportMenu(null)}
        />
      ) : null}
      {treeMenu !== null ? (
        <ContextMenu
          open
          x={treeMenu.x}
          y={treeMenu.y}
          aria-label={`Actions for ${treeMenu.feature.name}`}
          data-testid="tree-context-menu"
          sections={buildTreeSections(treeMenu.feature)}
          onClose={() => setTreeMenu(null)}
        />
      ) : null}
      {/* FLOW-A2 — the exit ticket. Rendered only while the router is actually
          holding a navigation, so it cannot appear for any other reason.
          No belt-and-braces draft write here: the SAME effect that raised
          `unsavedSketchRef` wrote the draft, so a blocked navigation already
          implies the bytes on disk are current. */}
      {leaveGuard.status === "blocked" ? (
        <LeaveSketchPrompt
          partName={part.data?.name ?? "this part"}
          destination={leaveDestination}
          entityCount={entityCount}
          constraintCount={constraintCount}
          draftHeld={draftHeld}
          saving={leaveSaving}
          error={syncError}
          onSaveAndLeave={saveAndLeave}
          onLeave={leaveGuard.proceed}
          onStay={leaveGuard.reset}
        />
      ) : null}
    </DocumentUnitProvider>
  );
}
