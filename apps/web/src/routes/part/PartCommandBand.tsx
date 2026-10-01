/**
 * The command band's two faces: the Create strip at rest, the Sketch strip
 * while sketching.
 * Split out of `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { CreateStrip } from "../../components/CreateStrip";
import { useCommandActionStore } from "../../features/commandActions";
import { SketchStrip } from "../../components/SketchStrip";
import { useSketchStore } from "../../sketch/store";
import type { PartDocument } from "./usePartDocument";
import type { TimelineHistory } from "./useTimelineHistory";
import type { EditorSeat } from "./useEditorSeat";
import type { SketchEntry } from "./useSketchEntry";
import type { PickOverlays } from "./usePickOverlays";
import type { ActionFlags } from "./useActionFlags";
import type { WorkspaceActions } from "./useWorkspaceActions";
import type { FeatureOpeners } from "./useFeatureOpeners";
import type { RebuildNotices } from "./useRebuildNotices";
import type { PartBody } from "./usePartBody";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { FlatPatternExport } from "./useFlatPatternExport";
import type { MeasureSession } from "./useMeasureSession";
import type { ViewportState } from "./useViewportState";
import type { EditorRepick } from "./useEditorRepick";
import type { SketchPersistence } from "./useSketchPersistence";
import type { PickState } from "./usePickState";

export function PartCommandBand({
  partDocument,
  timelineHistory,
  editorSeat,
  sketchEntry,
  pickOverlays,
  actionFlags,
  workspaceActions,
  featureOpeners,
  rebuildNotices,
  partBody,
  featureCatalog,
  flatPatternExport,
  measureSession,
  viewportState,
  editorRepick,
  sketchPersistence,
  pickState,
  openCreateCombine,
}: {
  partDocument: Pick<PartDocument, "mode" | "tree">;
  timelineHistory: Pick<
    TimelineHistory,
    "canUndo" | "canRedo" | "historyStep" | "triggerUndo" | "triggerRedo"
  >;
  editorSeat: Pick<
    EditorSeat,
    "rollbackBusy" | "scopeSubject" | "setSelectedFeatureId"
  >;
  sketchEntry: Pick<
    SketchEntry,
    "startSketch" | "authorOffsetPlane" | "togglePickFace"
  >;
  pickOverlays: Pick<PickOverlays, "bodyFeatureId" | "facePickRefusal">;
  actionFlags: Pick<
    ActionFlags,
    | "importing"
    | "flatPatternBusy"
    | "flatDxfBusy"
    | "offsetPlaneBusy"
    | "offsetPlaneError"
  >;
  workspaceActions: Pick<
    WorkspaceActions,
    "handleImportStep" | "toggleMeasure"
  >;
  featureOpeners: Pick<
    FeatureOpeners,
    | "openCreateDatum"
    | "openCreateExtrude"
    | "openCreateRevolve"
    | "openCreateSweep"
    | "openCreateLoft"
    | "openCreateFillet"
    | "openCreateChamfer"
    | "openCreatePattern"
    | "openCreateShell"
    | "openCreateDraft"
    | "openCreateHole"
    | "openCreateMirror"
    | "openCreateBaseFlange"
    | "openCreateEdgeFlange"
    | "openCreateHem"
    | "openCreateCornerRelief"
  >;
  rebuildNotices: Pick<
    RebuildNotices,
    "hasSolvedSketch" | "canSweep" | "canLoft"
  >;
  partBody: Pick<PartBody, "hasBody">;
  featureCatalog: Pick<
    FeatureCatalog,
    | "isSheetMetal"
    | "canCornerRelief"
    | "bodies"
    | "nextStep"
    | "datumPlaneOptions"
  >;
  flatPatternExport: Pick<
    FlatPatternExport,
    "openFlatPattern" | "exportFlatDxf"
  >;
  measureSession: Pick<MeasureSession, "measureActive">;
  viewportState: Pick<ViewportState, "activeCommand" | "partExport">;
  editorRepick: Pick<EditorRepick, "closeEditor">;
  sketchPersistence: Pick<
    SketchPersistence,
    "finishSketch" | "syncPending" | "syncError"
  >;
  pickState: Pick<
    PickState,
    "facePicking" | "facePlaneBusy" | "facePlaneError"
  >;
  openCreateCombine: () => void;
}) {
  const { mode, tree } = partDocument;
  const { canUndo, canRedo, historyStep, triggerUndo, triggerRedo } =
    timelineHistory;
  const { rollbackBusy, scopeSubject, setSelectedFeatureId } = editorSeat;
  const { startSketch, authorOffsetPlane, togglePickFace } = sketchEntry;
  const { bodyFeatureId, facePickRefusal } = pickOverlays;
  const {
    importing,
    flatPatternBusy,
    flatDxfBusy,
    offsetPlaneBusy,
    offsetPlaneError,
  } = actionFlags;
  const { handleImportStep, toggleMeasure } = workspaceActions;
  const {
    openCreateDatum,
    openCreateExtrude,
    openCreateRevolve,
    openCreateSweep,
    openCreateLoft,
    openCreateFillet,
    openCreateChamfer,
    openCreatePattern,
    openCreateShell,
    openCreateDraft,
    openCreateHole,
    openCreateMirror,
    openCreateBaseFlange,
    openCreateEdgeFlange,
    openCreateHem,
    openCreateCornerRelief,
  } = featureOpeners;
  const { hasSolvedSketch, canSweep, canLoft } = rebuildNotices;
  const { hasBody } = partBody;
  const { isSheetMetal, canCornerRelief, bodies, nextStep, datumPlaneOptions } =
    featureCatalog;
  const { openFlatPattern, exportFlatDxf } = flatPatternExport;
  const { measureActive } = measureSession;
  const { activeCommand, partExport } = viewportState;
  const { closeEditor } = editorRepick;
  const { finishSketch, syncPending, syncError } = sketchPersistence;
  const { facePicking, facePlaneBusy, facePlaneError } = pickState;
  return (
    <>
      {mode === "off" ? (
        <CreateStrip
          treeReady={tree.data !== undefined}
          canUndo={canUndo}
          canRedo={canRedo}
          historyHold={
            historyStep ?? (rollbackBusy ? ("rollback" as const) : null)
          }
          onUndo={triggerUndo}
          onRedo={triggerRedo}
          onNewSketch={startSketch}
          canImportStep={bodyFeatureId === null}
          importingStep={importing}
          onImportStep={handleImportStep}
          onNewDatum={openCreateDatum}
          canExtrude={hasSolvedSketch}
          onNewExtrude={openCreateExtrude}
          canRevolve={hasSolvedSketch}
          onNewRevolve={openCreateRevolve}
          canSweep={canSweep}
          onNewSweep={openCreateSweep}
          canLoft={canLoft}
          onNewLoft={openCreateLoft}
          canModify={hasBody}
          onFillet={openCreateFillet}
          onChamfer={openCreateChamfer}
          onPattern={openCreatePattern}
          scopeSubject={scopeSubject}
          onClearScope={() => setSelectedFeatureId(null)}
          onShell={openCreateShell}
          onDraft={openCreateDraft}
          onHole={openCreateHole}
          onMirror={openCreateMirror}
          canBaseFlange={hasSolvedSketch}
          onNewBaseFlange={openCreateBaseFlange}
          canEdgeFlange={isSheetMetal}
          onNewEdgeFlange={openCreateEdgeFlange}
          canHem={isSheetMetal}
          onNewHem={openCreateHem}
          canCornerRelief={canCornerRelief}
          onNewCornerRelief={openCreateCornerRelief}
          canFlatPattern={isSheetMetal}
          flatteningPattern={flatPatternBusy}
          onFlatPattern={openFlatPattern}
          exportingFlatDxf={flatDxfBusy}
          onExportFlatDxf={exportFlatDxf}
          canCombine={bodies.length >= 2}
          onCombine={openCreateCombine}
          canMeasure={hasBody}
          measuring={measureActive}
          onToggleMeasure={toggleMeasure}
          activeCommand={activeCommand}
          onCommandOk={() => useCommandActionStore.getState().requestSubmit()}
          onCommandCancel={closeEditor}
          onExport={partExport.exporter}
          exportDisabledReason={partExport.gate.blockedReason}
          exportPartial={partExport.gate.partial}
          exportPartialQualifier={partExport.gate.qualifier ?? undefined}
          exportState={partExport.gate.state}
          nextStep={nextStep}
        />
      ) : (
        <SketchStrip
          onSave={finishSketch}
          saving={syncPending}
          saveError={syncError}
          datumPlanes={datumPlaneOptions}
          onChoosePlaneSpec={(spec) =>
            useSketchStore.getState().choosePlaneSpec(spec)
          }
          onAuthorOffsetPlane={authorOffsetPlane}
          authoringOffset={offsetPlaneBusy}
          offsetPlaneError={offsetPlaneError}
          onTogglePickFace={togglePickFace}
          canPickFace={hasBody}
          facePicking={facePicking}
          authoringFace={facePlaneBusy}
          facePickError={facePlaneError}
          // PICK-2: the prompt is mounted BY `facePicking`, so if the tip
          // stops building while the pick is armed it goes on saying "click
          // a highlighted planar face" at a scene that has none. This is the
          // reason it says instead.
          facePickBlocked={facePicking ? facePickRefusal : null}
        />
      )}
    </>
  );
}
