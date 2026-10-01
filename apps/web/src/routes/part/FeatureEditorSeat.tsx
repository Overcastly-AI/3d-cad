/**
 * The authoring seat: the ONE open feature editor, wired to its submit,
 * its pick sessions and its gauge channels.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { ChamferEditor } from "../../components/ChamferEditor";
import { CombineEditor } from "../../components/CombineEditor";
import { DatumEditor } from "../../components/DatumEditor";
import { DraftEditor } from "../../components/DraftEditor";
import { ExtrudeEditor } from "../../components/ExtrudeEditor";
import { HoleEditor } from "../../components/HoleEditor";
import { BaseFlangeEditor } from "../../components/BaseFlangeEditor";
import { EdgeFlangeEditor } from "../../components/EdgeFlangeEditor";
import { HemEditor } from "../../components/HemEditor";
import { CornerReliefEditor } from "../../components/CornerReliefEditor";
import { FilletEditor } from "../../components/FilletEditor";
import { LoftEditor } from "../../components/LoftEditor";
import { MirrorEditor } from "../../components/MirrorEditor";
import { PatternEditor } from "../../components/PatternEditor";
import { RevolveEditor } from "../../components/RevolveEditor";
import { ShellEditor } from "../../components/ShellEditor";
import { SweepEditor } from "../../components/SweepEditor";
import type { PartDocument } from "./usePartDocument";
import type { PartBody } from "./usePartBody";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { FeatureSubmit } from "./useFeatureSubmit";
import type { EditorRepick } from "./useEditorRepick";
import type { EditorSeat } from "./useEditorSeat";
import type { RebuildNotices } from "./useRebuildNotices";
import type { SolvedSketches } from "./useSolvedSketches";
import type { PickOverlays } from "./usePickOverlays";
import type { PickState } from "./usePickState";
import type { HolePicking } from "./useHolePicking";
import type { PickSessions } from "./usePickSessions";
import type { ActionFlags } from "./useActionFlags";
import type { DatumFacePicking } from "./useDatumFacePicking";

export function FeatureEditorSeat({
  partDocument,
  partBody,
  featureCatalog,
  featureSubmit,
  editorRepick,
  editorSeat,
  rebuildNotices,
  solvedSketches,
  pickOverlays,
  pickState,
  holePicking,
  pickSessions,
  actionFlags,
  datumFacePicking,
}: {
  partDocument: Pick<PartDocument, "mode">;
  partBody: Pick<PartBody, "editor" | "hasBody">;
  featureCatalog: Pick<
    FeatureCatalog,
    | "sketchProfiles"
    | "axesByProfile"
    | "pathsByProfile"
    | "smDefaults"
    | "edgeFlangeOpts"
    | "datumPlaneOptions"
    | "bodies"
  >;
  featureSubmit: Pick<
    FeatureSubmit,
    | "submitExtrude"
    | "submitRevolve"
    | "submitSweep"
    | "submitLoft"
    | "submitPattern"
    | "submitFillet"
    | "submitChamfer"
    | "submitShell"
    | "submitDraft"
    | "submitHole"
    | "submitBaseFlange"
    | "submitEdgeFlange"
    | "submitHem"
    | "submitCornerRelief"
    | "submitMirror"
    | "submitDatum"
    | "submitCombine"
  >;
  editorRepick: Pick<EditorRepick, "closeEditor" | "editorMovedEdge">;
  editorSeat: Pick<
    EditorSeat,
    | "editorSaving"
    | "editorError"
    | "setExtrudePreview"
    | "extrudeDepthOverride"
    | "setRevolveGauge"
    | "revolveAngleOverride"
    | "setPatternPreview"
    | "patternCountOverride"
    | "patternSpacingOverride"
    | "filletRadiusOverride"
    | "setFilletRadiusMm"
    | "chamferDistanceOverride"
    | "setChamferDistanceMm"
    | "setShellThicknessMm"
    | "shellThicknessOverride"
    | "setDraftGauge"
    | "draftAngleOverride"
    | "setHoleGauge"
    | "holeDiameterOverride"
    | "holeDepthOverride"
    | "setDatumGaugeSeed"
    | "datumOffsetOverride"
  >;
  rebuildNotices: Pick<RebuildNotices, "sweepRebuildError">;
  solvedSketches: Pick<SolvedSketches, "profileEntities">;
  pickOverlays: Pick<
    PickOverlays,
    | "pickAnchorFeatureId"
    | "holePickRefusal"
    | "holePlacementHidden"
    | "holeOverlayEdges"
    | "datumPickRefusal"
  >;
  pickState: Pick<
    PickState,
    | "holePick"
    | "holeFacePicked"
    | "holePointPicked"
    | "holePickError"
    | "datumFacePick"
    | "datumFacePicked"
    | "datumFacePickError"
  >;
  holePicking: Pick<HolePicking, "toggleHolePick" | "onHolePreviewChange">;
  pickSessions: Pick<
    PickSessions,
    "onEdgeFlangeSpanChange" | "onReliefBendsChange"
  >;
  actionFlags: Pick<ActionFlags, "datumEditorRefs">;
  datumFacePicking: Pick<DatumFacePicking, "toggleDatumFacePick">;
}) {
  const { mode } = partDocument;
  const { editor, hasBody } = partBody;
  const {
    sketchProfiles,
    axesByProfile,
    pathsByProfile,
    smDefaults,
    edgeFlangeOpts,
    datumPlaneOptions,
    bodies,
  } = featureCatalog;
  const {
    submitExtrude,
    submitRevolve,
    submitSweep,
    submitLoft,
    submitPattern,
    submitFillet,
    submitChamfer,
    submitShell,
    submitDraft,
    submitHole,
    submitBaseFlange,
    submitEdgeFlange,
    submitHem,
    submitCornerRelief,
    submitMirror,
    submitDatum,
    submitCombine,
  } = featureSubmit;
  const { closeEditor, editorMovedEdge } = editorRepick;
  const {
    editorSaving,
    editorError,
    setExtrudePreview,
    extrudeDepthOverride,
    setRevolveGauge,
    revolveAngleOverride,
    setPatternPreview,
    patternCountOverride,
    patternSpacingOverride,
    filletRadiusOverride,
    setFilletRadiusMm,
    chamferDistanceOverride,
    setChamferDistanceMm,
    setShellThicknessMm,
    shellThicknessOverride,
    setDraftGauge,
    draftAngleOverride,
    setHoleGauge,
    holeDiameterOverride,
    holeDepthOverride,
    setDatumGaugeSeed,
    datumOffsetOverride,
  } = editorSeat;
  const { sweepRebuildError } = rebuildNotices;
  const { profileEntities } = solvedSketches;
  const {
    pickAnchorFeatureId,
    holePickRefusal,
    holePlacementHidden,
    holeOverlayEdges,
    datumPickRefusal,
  } = pickOverlays;
  const {
    holePick,
    holeFacePicked,
    holePointPicked,
    holePickError,
    datumFacePick,
    datumFacePicked,
    datumFacePickError,
  } = pickState;
  const { toggleHolePick, onHolePreviewChange } = holePicking;
  const { onEdgeFlangeSpanChange, onReliefBendsChange } = pickSessions;
  const { datumEditorRefs } = actionFlags;
  const { toggleDatumFacePick } = datumFacePicking;
  return (
    <>
      {mode === "off" && editor !== null ? (
        editor.kind === "extrude" ? (
          <ExtrudeEditor
            mode={editor.mode}
            profiles={sketchProfiles}
            initial={editor.initial}
            onSubmit={submitExtrude}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            onPreviewChange={setExtrudePreview}
            depthOverride={extrudeDepthOverride}
          />
        ) : editor.kind === "revolve" ? (
          <RevolveEditor
            mode={editor.mode}
            profiles={sketchProfiles}
            axesByProfile={axesByProfile}
            initial={editor.initial}
            onSubmit={submitRevolve}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            onGaugeChange={setRevolveGauge}
            angleOverride={revolveAngleOverride}
          />
        ) : editor.kind === "sweep" ? (
          <SweepEditor
            mode={editor.mode}
            profiles={sketchProfiles}
            pathsByProfile={pathsByProfile}
            initial={editor.initial}
            onSubmit={submitSweep}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            rebuildError={sweepRebuildError}
            profileEntities={profileEntities}
          />
        ) : editor.kind === "loft" ? (
          <LoftEditor
            mode={editor.mode}
            sections={sketchProfiles}
            initial={editor.initial}
            onSubmit={submitLoft}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
          />
        ) : editor.kind === "pattern" ? (
          <PatternEditor
            mode={editor.mode}
            initial={editor.initial}
            onSubmit={submitPattern}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            // ANCHOR C — contract β's echo, both halves. The
            // gauges ask, the form takes it, the form projects the
            // row back out through `onPreviewChange`, and the
            // gauges redraw from THAT. One value each, two ways in.
            onPreviewChange={setPatternPreview}
            countOverride={patternCountOverride}
            spacingOverride={patternSpacingOverride}
          />
        ) : editor.kind === "fillet" ? (
          <FilletEditor
            mode={editor.mode}
            movedEdge={editorMovedEdge}
            initial={editor.initial}
            bodyFeatureId={pickAnchorFeatureId}
            onSubmit={submitFillet}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            radiusOverride={filletRadiusOverride}
            onPreviewChange={setFilletRadiusMm}
          />
        ) : editor.kind === "chamfer" ? (
          <ChamferEditor
            mode={editor.mode}
            movedEdge={editorMovedEdge}
            initial={editor.initial}
            bodyFeatureId={pickAnchorFeatureId}
            onSubmit={submitChamfer}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            distanceOverride={chamferDistanceOverride}
            onPreviewChange={setChamferDistanceMm}
          />
        ) : editor.kind === "shell" ? (
          <ShellEditor
            mode={editor.mode}
            initial={editor.initial}
            bodyFeatureId={pickAnchorFeatureId}
            onSubmit={submitShell}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            onThicknessChange={setShellThicknessMm}
            thicknessOverride={shellThicknessOverride}
          />
        ) : editor.kind === "draft" ? (
          <DraftEditor
            mode={editor.mode}
            initial={editor.initial}
            bodyFeatureId={pickAnchorFeatureId}
            onSubmit={submitDraft}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            onGaugeChange={setDraftGauge}
            angleOverride={draftAngleOverride}
          />
        ) : editor.kind === "hole" ? (
          <HoleEditor
            mode={editor.mode}
            initial={editor.initial}
            onSubmit={submitHole}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            canPickFace={hasBody}
            // PICK-2: an armed pick whose overlay cannot populate is
            // not an armed pick. Reading `null` here is what stops
            // the row badging `Picking` over an empty scene.
            activePick={holePickRefusal === null ? holePick : null}
            onTogglePick={toggleHolePick}
            facePick={holeFacePicked}
            pointPick={holePointPicked}
            pickError={holePickError}
            pickBlockedReason={holePickRefusal}
            placementHidden={holePlacementHidden}
            edges={holeOverlayEdges}
            onPreviewChange={onHolePreviewChange}
            onGaugeChange={setHoleGauge}
            diameterOverride={holeDiameterOverride}
            depthOverride={holeDepthOverride}
          />
        ) : editor.kind === "baseFlange" ? (
          <BaseFlangeEditor
            mode={editor.mode}
            profiles={sketchProfiles}
            initial={editor.initial}
            onSubmit={submitBaseFlange}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
          />
        ) : editor.kind === "edgeFlange" ? (
          <EdgeFlangeEditor
            mode={editor.mode}
            movedEdge={editorMovedEdge}
            initial={editor.initial}
            bodyFeatureId={pickAnchorFeatureId}
            defaults={smDefaults}
            onSubmit={submitEdgeFlange}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            onSpanChange={onEdgeFlangeSpanChange}
          />
        ) : editor.kind === "hem" ? (
          <HemEditor
            mode={editor.mode}
            movedEdge={editorMovedEdge}
            initial={editor.initial}
            bodyFeatureId={pickAnchorFeatureId}
            defaults={smDefaults}
            onSubmit={submitHem}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
          />
        ) : editor.kind === "cornerRelief" ? (
          <CornerReliefEditor
            mode={editor.mode}
            initial={editor.initial}
            edgeFlanges={edgeFlangeOpts}
            defaults={smDefaults}
            onSubmit={submitCornerRelief}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            onBendsChange={onReliefBendsChange}
          />
        ) : editor.kind === "mirror" ? (
          <MirrorEditor
            mode={editor.mode}
            initial={editor.initial}
            datumPlanes={datumPlaneOptions}
            onSubmit={submitMirror}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
          />
        ) : editor.kind === "datum" ? (
          <DatumEditor
            mode={editor.mode}
            initial={editor.initial}
            datumRefs={datumEditorRefs}
            onSubmit={submitDatum}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
            canPickFace={hasBody}
            // PICK-2, as for the hole editor: an armed slot whose
            // overlay cannot populate reads as not armed…
            activeFacePickSlot={
              datumPickRefusal === null ? datumFacePick : null
            }
            onToggleFacePick={toggleDatumFacePick}
            facePick={datumFacePicked}
            onPlaneChange={setDatumGaugeSeed}
            offsetOverride={datumOffsetOverride}
            // …and the standing refusal is stated on the editor's
            // own (ungated) pick-error line rather than nowhere.
            facePickError={datumFacePickError ?? datumPickRefusal}
          />
        ) : (
          <CombineEditor
            bodies={bodies}
            initial={editor.initial}
            onSubmit={submitCombine}
            onCancel={closeEditor}
            saving={editorSaving}
            error={editorError}
          />
        )
      ) : null}
    </>
  );
}
