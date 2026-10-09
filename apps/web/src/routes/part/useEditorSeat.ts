/**
 * The authoring seat's state: selection, scope, save state, the editors'
 * live projections and the gauge override channels, and `setEditor`, the
 * one way the open editor changes.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useCallback, useMemo, useState } from "react";

import { type DraftGaugeState } from "../../components/DraftEditor";
import { type HoleGaugeState } from "../../components/HoleEditor";
import { type RevolveGaugeState } from "../../components/RevolveEditor";
import { type ExtrudePreviewState } from "../../features/extrude";
import { scopeSeed } from "../../features/patternScope";
import { usePreselectStore } from "../../features/preselect";
import { useCommandActionStore } from "../../features/commandActions";
import { useEdgeGaugeAnchors } from "../../viewport/edgeAnchorSource";
import { type DatumGaugeSeed } from "../../viewport/faceAnchor";
import type { PatternPreviewState } from "../../viewport/patternGhost";
import { useGaugeOverride } from "../../viewport/useGaugeOverride";
import { type OpenEditor } from "./openEditor";
import type { PartBody } from "./usePartBody";
import type { FeatureCatalog } from "./useFeatureCatalog";

type EditorSeatParams = Pick<PartBody, "setEditorState"> &
  Pick<FeatureCatalog, "features">;

export function useEditorSeat({ setEditorState, features }: EditorSeatParams) {
  // The authoring seat holds one editor at a time — an extrude OR a revolve —
  // so they share the saving/error state and the viewport top-left anchor.
  // (The union lives in `OpenEditor` above, which also keys COMMAND_LABEL.)
  // `setEditorState` is deliberately NOT used directly anywhere below — every
  // call site goes through the `setEditor` wrapper defined beside the gauge
  // channels, which ends the outgoing command's gauge session first. See the
  // note there; the split exists so a gauge override cannot outlive the command
  // that produced it.
  // (`editor` itself is declared above the body query: see the note there.)
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(
    null,
  );
  // WHAT a pattern/mirror opened right now would act on (docs/design/
  // pattern-scope.md). The tree selection IS the scope: with `Hole1` selected
  // the Create strip's verb reads "Repeat Hole1" and the editor opens already
  // scoped to it. With nothing selected we still offer the tip in the editor's
  // scope row, but the toolbar keeps its plain words.
  const patternScopeSeed = useMemo(
    () => scopeSeed(features, selectedFeatureId),
    [features, selectedFeatureId],
  );
  const scopeSubject =
    patternScopeSeed !== null && patternScopeSeed.fromSelection
      ? patternScopeSeed.name
      : null;
  // What the OPEN command actually acts on, published by its scope row (see
  // `usePublishedScope`). Distinct from the selection above and worth the
  // second channel for two reasons: the scope row is flippable, so a selection-
  // driven mark would keep pointing at `Hole1` after the user chose `This
  // body`; and an editor seeded from the TIP feature has a subject while
  // nothing at all is selected. `null` whenever no command is asking; `[]` when
  // one is and its answer is the whole body (REACH-2-FLOW-B).
  const scopedFeatureIds = useCommandActionStore((s) => s.scopedFeatureIds);
  const [editorSaving, setEditorSaving] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
  // UX audit #20e — a feature can SAVE cleanly yet fail to REBUILD (the create
  // 200s, then the tree re-evaluation flags the feature). That error lands in
  // the tree while the eye is still on the editor seat, so we mirror it right
  // there. Keyed to the last-saved feature so merely selecting an old broken
  // feature never nags; dismissible, and re-armed by the next save.
  const [lastSavedFeatureId, setLastSavedFeatureId] = useState<string | null>(
    null,
  );
  const [rebuildNoticeDismissed, setRebuildNoticeDismissed] = useState(false);
  const [rollbackBusy, setRollbackBusy] = useState(false);
  // Live extrude ghost (UI-REVIEW #8): the open extrude editor projects its
  // form here on every keystroke; the viewport sweeps the profile at this
  // distance before Save. Cleared the moment the editor closes.
  const [extrudePreview, setExtrudePreview] =
    useState<ExtrudePreviewState | null>(null);
  /**
   * The depth the viewport's drag handle is asserting (T-23). It flows the
   * OTHER way from the ghost: the gauge reports a distance, the editor's form
   * takes it, and the ghost redraws from that form — one value, two ways in
   * (drag and type), never two states to keep in step.
   *
   * `useGaugeOverride` carries both halves of that contract in one call — the
   * echoed state AND the reset — because the reset is the line everyone
   * forgets, and forgetting it seeds the NEXT open of the command from the last
   * drag. Every verb that grows a gauge adds one of these, one prop on its own
   * editor, and one mount; see that hook's note for the two silent broken
   * states this shape exists to prevent.
   */
  const [extrudeDepthOverride, extrudeDepthGauge] = useGaugeOverride("mm");
  const handleExtrudeDrag = extrudeDepthGauge.set;

  // The fillet/chamfer gauges (CRAFT-9a), carrying the same contract: the live
  // value the editor holds (so the viewport can draw the round or the bevel at
  // it) and the override channel a drag writes back through. The ANCHORS are
  // seated here and passed DOWN as a prop rather than read inside the gauges —
  // CRAFT-12 moves where a selection lives, and a component that reached into
  // this pick session would be rewritten then instead of re-wired (§11).
  const [filletRadiusMm, setFilletRadiusMm] = useState<number | null>(null);
  const [chamferDistanceMm, setChamferDistanceMm] = useState<number | null>(
    null,
  );
  const [filletRadiusOverride, filletRadiusGauge] = useGaugeOverride("mm");
  const [chamferDistanceOverride, chamferDistanceGauge] =
    useGaugeOverride("mm");
  const edgeGaugeAnchors = useEdgeGaugeAnchors();

  // The same two halves, once per verb that grew a gauge in CRAFT-9b. The
  // `…Mm` / `…Seed` state beside each override is the editor's LIVE form
  // projected up here (the ghost's direction), so the viewport can seat the
  // instrument and draw its preview before Save; the override is the value
  // coming back the other way. One value, two ways in.
  const [shellThicknessOverride, shellThicknessGauge] = useGaugeOverride("mm");
  const [shellThicknessMm, setShellThicknessMm] = useState<number | null>(null);
  const [datumOffsetOverride, datumOffsetGauge] = useGaugeOverride("mm");
  const [datumGaugeSeed, setDatumGaugeSeed] = useState<DatumGaugeSeed | null>(
    null,
  );

  // ANCHOR A (CRAFT-10) — the two ANGULAR gauges. Same contract as the depth
  // gauge above and the same three insertions: this hook, one prop on the
  // editor, one mount in the viewport. `"deg"` rather than `"mm"` is the whole
  // point of the box being named for its quantity — an editor that read a bare
  // `value` off an untyped box could be handed millimetres for degrees and
  // nothing but a founder would catch it.
  const [revolveAngleOverride, revolveAngleGauge] = useGaugeOverride("deg");
  const handleRevolveDrag = revolveAngleGauge.set;
  const [draftAngleOverride, draftAngleGauge] = useGaugeOverride("deg");
  const handleDraftDrag = draftAngleGauge.set;
  // The open form, projected by the editor for the viewport to place its arc on
  // (the revolve/draft twin of `extrudePreview`). Cleared when the editor closes.
  const [revolveGauge, setRevolveGauge] = useState<RevolveGaugeState | null>(
    null,
  );
  const [draftGauge, setDraftGauge] = useState<DraftGaugeState | null>(null);
  // ANCHOR A, pattern (CRAFT-11). TWO of them, because a pattern mounts the
  // gauge TWICE — a stepped count along the row and a linear spacing across the
  // first gap — and two instruments driving one box could not hold one number
  // steady while the other moves, which is the whole reason §5.3 split them.
  const [patternCountOverride, patternCountGauge] = useGaugeOverride("n");
  const [patternSpacingOverride, patternSpacingGauge] = useGaugeOverride("mm");
  // The open pattern editor's live row, projected for the viewport (the pattern
  // twin of `extrudePreview`). Cleared the moment the editor closes.
  const [patternPreview, setPatternPreview] =
    useState<PatternPreviewState | null>(null);
  // ANCHOR A, hole (CRAFT-9c). Two channels, one per instrument — Ø and blind
  // depth — for the pattern's reason: two gauges driving one box could not hold
  // one number steady while the other moves. `holeGauge` is the editor's live
  // pair projected up (the hole twin of `draftGauge`); cleared on close.
  const [holeDiameterOverride, holeDiameterGauge] = useGaugeOverride("mm");
  const [holeDepthOverride, holeDepthGauge] = useGaugeOverride("mm");
  const [holeGauge, setHoleGauge] = useState<HoleGaugeState | null>(null);

  /**
   * End the gauge session — every override box back to null (ANCHOR B).
   *
   * A gauge override is SESSION state: it is the value a viewport instrument is
   * asking the open editor for, and it means nothing once that editor is gone.
   * Leaving one behind is not a stale readout, it is a WRONG NUMBER IN A FIELD
   * THAT LOOKS AUTHORITATIVE — the next editor to mount applies the box over
   * its own seed on its first effect pass, so a feature stored at 8 mm re-opens
   * pre-filled at whatever the last drag reached, one Enter from a silent
   * change the user never asked for (product audit 2026-09-16, F-9).
   */
  const endGaugeSession = useCallback(() => {
    extrudeDepthGauge.reset();
    filletRadiusGauge.reset();
    chamferDistanceGauge.reset();
    shellThicknessGauge.reset();
    datumOffsetGauge.reset();
    revolveAngleGauge.reset();
    draftAngleGauge.reset();
    // Both of the pattern's, because it mounts the gauge TWICE.
    patternCountGauge.reset();
    patternSpacingGauge.reset();
    // Both of the hole's, for the same reason.
    holeDiameterGauge.reset();
    holeDepthGauge.reset();
  }, [
    extrudeDepthGauge,
    filletRadiusGauge,
    chamferDistanceGauge,
    shellThicknessGauge,
    datumOffsetGauge,
    revolveAngleGauge,
    draftAngleGauge,
    patternCountGauge,
    patternSpacingGauge,
    holeDiameterGauge,
    holeDepthGauge,
  ]);

  /**
   * OPEN / REPLACE / CLOSE THE AUTHORING SEAT — the ONLY way `editor` moves.
   *
   * The reset used to live in `closeEditor` alone, described in
   * `useGaugeOverride` as "the line everyone forgets". It was worse than
   * forgettable: `closeEditor` is one of SEVEN ways an editor stops being the
   * open one. A successful save calls `setEditor(null)` straight from the write
   * handler, `selectFeature` REPLACES the open editor with another feature's,
   * and entering the sketcher / arming Measure / importing a STEP each drop it
   * on the floor. None of those ran the reset, so the box survived — and the
   * audit's fillet re-opened at the drag value rather than at `radius_mm: 8`.
   *
   * Binding the reset to the TRANSITION rather than to one of its callers is
   * what makes it structural: a later verb adds its channel to
   * `endGaugeSession` and cannot get this wrong at any of the seven sites,
   * because there are no longer seven sites. The reset is synchronous and runs
   * BEFORE the state update on purpose — an effect would land after the newly
   * mounted editor's own effects, i.e. after the clobber it exists to prevent.
   */
  const setEditor = useCallback(
    (next: OpenEditor | null) => {
      endGaugeSession();
      // SKETCH-PLANE-PICK: whatever the closing command picked and did not
      // save is not a selection. The save path settles its picks first.
      usePreselectStore.getState().dropProvisional();
      setEditorState(next);
    },
    [endGaugeSession],
  );
  return {
    selectedFeatureId,
    setSelectedFeatureId,
    patternScopeSeed,
    scopeSubject,
    scopedFeatureIds,
    editorSaving,
    setEditorSaving,
    editorError,
    setEditorError,
    lastSavedFeatureId,
    setLastSavedFeatureId,
    rebuildNoticeDismissed,
    setRebuildNoticeDismissed,
    rollbackBusy,
    setRollbackBusy,
    extrudePreview,
    setExtrudePreview,
    extrudeDepthOverride,
    handleExtrudeDrag,
    filletRadiusMm,
    setFilletRadiusMm,
    chamferDistanceMm,
    setChamferDistanceMm,
    filletRadiusOverride,
    filletRadiusGauge,
    chamferDistanceOverride,
    chamferDistanceGauge,
    edgeGaugeAnchors,
    shellThicknessOverride,
    shellThicknessGauge,
    shellThicknessMm,
    setShellThicknessMm,
    datumOffsetOverride,
    datumOffsetGauge,
    datumGaugeSeed,
    setDatumGaugeSeed,
    revolveAngleOverride,
    handleRevolveDrag,
    draftAngleOverride,
    handleDraftDrag,
    revolveGauge,
    setRevolveGauge,
    draftGauge,
    setDraftGauge,
    patternCountOverride,
    patternCountGauge,
    patternSpacingOverride,
    patternSpacingGauge,
    patternPreview,
    setPatternPreview,
    holeDiameterOverride,
    holeDiameterGauge,
    holeDepthOverride,
    holeDepthGauge,
    holeGauge,
    setHoleGauge,
    setEditor,
  };
}

export type EditorSeat = ReturnType<typeof useEditorSeat>;
