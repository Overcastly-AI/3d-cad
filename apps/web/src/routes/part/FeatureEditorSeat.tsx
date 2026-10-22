/**
 * The authoring seat: the ONE open feature editor, wired to its submit,
 * its pick sessions and its gauge channels.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { useMemo } from "react";

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
import { PipeEditor } from "../../components/PipeEditor";
import { Sketch3DEditor } from "../../components/Sketch3DEditor";
import { solvedSketch3DMap } from "../../features/sketch3d";
import { pipeCurveOptions } from "../../features/pipe";
import { PluginFeatureEditor } from "../../components/PluginFeatureEditor";
import type { CustomFeatureWrite, PluginManifest } from "../../api/plugins";
import { FormulaSessionContext } from "../../components/ValueField";
import type { EditorFormulas } from "./useEditorFormulas";
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
  editorFormulas,
  rebuildNotices,
  solvedSketches,
  pickOverlays,
  pickState,
  holePicking,
  pickSessions,
  actionFlags,
  datumFacePicking,
  pluginCatalog,
  submitCustom,
}: {
  editorFormulas: Pick<EditorFormulas, "formulaSession" | "editorInputError">;
  partDocument: Pick<PartDocument, "mode" | "evaluation">;
  partBody: Pick<PartBody, "editor" | "hasBody">;
  featureCatalog: Pick<
    FeatureCatalog,
    | "sketchProfiles"
    | "closedProfiles"
    | "axesByProfile"
    | "pathsByProfile"
    | "smDefaults"
    | "edgeFlangeOpts"
    | "datumPlaneOptions"
    | "bodies"
    | "features"
    | "cutBodiesByFeature"
  >;
  featureSubmit: Pick<
    FeatureSubmit,
    | "submitExtrude"
    | "submitRevolve"
    | "submitSweep"
    | "submitPipe"
    | "submitSketch3D"
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
    | "setDatumAnglePreview"
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
  actionFlags: Pick<ActionFlags, "datumEditorRefs" | "datumSketchLines">;
  datumFacePicking: Pick<
    DatumFacePicking,
    | "toggleDatumFacePick"
    | "toggleDatumEdgePick"
    | "datumEdgePickArmed"
    | "datumEdgePicked"
    | "datumEdgePickError"
  >;
  /** The installed plugins (a custom feature's form), undefined while loading. */
  pluginCatalog?: readonly PluginManifest[] | undefined;
  submitCustom?: (write: CustomFeatureWrite) => void;
}) {
  const { mode, evaluation } = partDocument;
  const solved3d = useMemo(
    () => solvedSketch3DMap(evaluation.data?.features),
    [evaluation.data],
  );
  const { editor, hasBody } = partBody;
  const {
    sketchProfiles,
    closedProfiles,
    axesByProfile,
    pathsByProfile,
    smDefaults,
    edgeFlangeOpts,
    datumPlaneOptions,
    bodies,
    features,
    cutBodiesByFeature,
  } = featureCatalog;
  const {
    submitExtrude,
    submitRevolve,
    submitSweep,
    submitPipe,
    submitSketch3D,
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
    setDatumAnglePreview,
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
  const { datumEditorRefs, datumSketchLines } = actionFlags;
  const {
    toggleDatumFacePick,
    toggleDatumEdgePick,
    datumEdgePickArmed,
    datumEdgePicked,
    datumEdgePickError,
  } = datumFacePicking;
  const { formulaSession, editorInputError } = editorFormulas;
  // A save's refusal, else the feature's own `input_error` when no field on
  // screen carries it (PART-PARAMETERS step 8).
  const seatError = editorError ?? editorInputError;
  // A cut editor's Objects To Cut: the part's bodies, and those the cut met on
  // its last rebuild (none yet for a new cut).
  const objectsToCut =
    editor === null
      ? undefined
      : {
          bodies,
          met:
            editor.featureId === undefined
              ? null
              : (cutBodiesByFeature.get(editor.featureId) ?? null),
        };
  return (
    <FormulaSessionContext.Provider value={formulaSession}>
      {mode === "off" && editor !== null ? (
        editor.kind === "extrude" ? (
          <ExtrudeEditor
            mode={editor.mode}
            profiles={closedProfiles}
            initial={editor.initial}
            onSubmit={submitExtrude}
            objectsToCut={objectsToCut}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
            onPreviewChange={setExtrudePreview}
            depthOverride={extrudeDepthOverride}
          />
        ) : editor.kind === "revolve" ? (
          <RevolveEditor
            mode={editor.mode}
            profiles={closedProfiles}
            axesByProfile={axesByProfile}
            initial={editor.initial}
            onSubmit={submitRevolve}
            objectsToCut={objectsToCut}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
            onGaugeChange={setRevolveGauge}
            angleOverride={revolveAngleOverride}
          />
        ) : editor.kind === "sweep" ? (
          <SweepEditor
            mode={editor.mode}
            profiles={closedProfiles}
            pathsByProfile={pathsByProfile}
            initial={editor.initial}
            onSubmit={submitSweep}
            objectsToCut={objectsToCut}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
            rebuildError={sweepRebuildError}
            profileEntities={profileEntities}
          />
        ) : editor.kind === "pipe" ? (
          <PipeEditor
            mode={editor.mode}
            // Curves of sketches BEFORE the pipe only: a later sketch is a
            // forward reference the write would refuse.
            curves={pipeCurveOptions(
              editor.featureId === undefined
                ? features
                : features.slice(
                    0,
                    Math.max(
                      0,
                      features.findIndex((f) => f.id === editor.featureId),
                    ),
                  ),
              solved3d,
            )}
            initial={editor.initial}
            onSubmit={submitPipe}
            objectsToCut={objectsToCut}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
          />
        ) : editor.kind === "sketch3d" ? (
          <Sketch3DEditor
            mode={editor.mode}
            featureId={editor.featureId}
            initial={editor.initial}
            solved={
              editor.featureId === undefined
                ? null
                : (solved3d.get(editor.featureId) ?? null)
            }
            onSubmit={submitSketch3D}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
          />
        ) : editor.kind === "loft" ? (
          <LoftEditor
            mode={editor.mode}
            sections={sketchProfiles}
            initial={editor.initial}
            onSubmit={submitLoft}
            objectsToCut={objectsToCut}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
          />
        ) : editor.kind === "pattern" ? (
          <PatternEditor
            mode={editor.mode}
            initial={editor.initial}
            onSubmit={submitPattern}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
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
            error={seatError}
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
            error={seatError}
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
            error={seatError}
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
            error={seatError}
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
            error={seatError}
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
            scopeBodies={bodies}
          />
        ) : editor.kind === "baseFlange" ? (
          <BaseFlangeEditor
            mode={editor.mode}
            profiles={sketchProfiles}
            initial={editor.initial}
            onSubmit={submitBaseFlange}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
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
            error={seatError}
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
            error={seatError}
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
            error={seatError}
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
            error={seatError}
          />
        ) : editor.kind === "custom" ? (
          <PluginFeatureEditor
            key={`${editor.pluginId}@${editor.pluginVersion}:${editor.featureId ?? "new"}`}
            mode={editor.mode}
            pluginId={editor.pluginId}
            pluginVersion={editor.pluginVersion}
            featureId={editor.featureId}
            stored={editor.stored}
            catalog={pluginCatalog}
            features={features}
            onSubmit={submitCustom ?? (() => undefined)}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
          />
        ) : editor.kind === "datum" ? (
          <DatumEditor
            mode={editor.mode}
            initial={editor.initial}
            datumRefs={datumEditorRefs}
            sketchLines={datumSketchLines}
            pathCurves={pipeCurveOptions(
              editor.featureId === undefined
                ? features
                : features.slice(
                    0,
                    Math.max(
                      0,
                      features.findIndex((f) => f.id === editor.featureId),
                    ),
                  ),
            )}
            onSubmit={submitDatum}
            onCancel={closeEditor}
            saving={editorSaving}
            error={seatError}
            canPickFace={hasBody}
            // PICK-2, as for the hole editor: an armed slot whose
            // overlay cannot populate reads as not armed…
            activeFacePickSlot={
              datumPickRefusal === null ? datumFacePick : null
            }
            onToggleFacePick={toggleDatumFacePick}
            facePick={datumFacePicked}
            onPlaneChange={setDatumGaugeSeed}
            onAnglePlaneChange={setDatumAnglePreview}
            edgePickArmed={datumEdgePickArmed}
            onToggleEdgePick={toggleDatumEdgePick}
            edgePick={datumEdgePicked}
            edgePickError={datumEdgePickError ?? null}
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
            error={seatError}
          />
        )
      ) : null}
    </FormulaSessionContext.Provider>
  );
}
