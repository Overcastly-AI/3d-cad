/**
 * The part workspace's side rails. Split out of `PartPage.tsx`
 * (SPLIT-PARTPAGE); behaviour unchanged.
 */
import { Panel } from "@loft/design";

import { type FeatureResponse } from "../../api/parts";
import { BodyInspector } from "../../components/BodyInspector";
import { BodiesPanel } from "../../components/BodiesPanel";
import { ChromeRail } from "../../components/ChromeRail";
import { FloatingPanel } from "../../components/FloatingPanel";
import { FeatureTreePanel } from "../../components/FeatureTreePanel";
import { ParametersPanel } from "../../components/ParametersPanel";
import { PartExportControls } from "../../components/PartExportControls";
import type { PartDocument } from "./usePartDocument";
import type { ViewportState } from "./useViewportState";
import type { EditorSeat } from "./useEditorSeat";
import type { TreeActions } from "./useTreeActions";
import type { EditorRepick } from "./useEditorRepick";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { PartBody } from "./usePartBody";
import type { MaterialControls } from "./useMaterialControls";
import type { PartVersions } from "./usePartVersions";
import type { PartParameters } from "./usePartParameters";

/** The left rail: the feature tree and the bodies panel. */
export function FeatureTreeRail({
  partDocument,
  viewportState,
  editorSeat,
  treeActions,
  editorRepick,
  featureCatalog,
  selectFeature,
}: {
  partDocument: Pick<PartDocument, "tree" | "evaluation">;
  viewportState: Pick<ViewportState, "build">;
  editorSeat: Pick<EditorSeat, "selectedFeatureId" | "scopedFeatureIds">;
  treeActions: Pick<
    TreeActions,
    | "keepAsOneBody"
    | "disjointRecovering"
    | "toggleSuppress"
    | "suppressingId"
    | "openTreeMenu"
    | "renamingId"
    | "commitRename"
    | "setRenamingId"
    | "reorderTree"
    | "selectBody"
  >;
  editorRepick: Pick<
    EditorRepick,
    "repickFace" | "repickEdges" | "dismissedMovedEdges" | "dismissMovedEdge"
  >;
  featureCatalog: Pick<FeatureCatalog, "bodies" | "lumpsByFeature">;
  selectFeature: (feature: FeatureResponse) => void;
}) {
  const { tree, evaluation } = partDocument;
  const { build } = viewportState;
  const { selectedFeatureId, scopedFeatureIds } = editorSeat;
  const {
    keepAsOneBody,
    disjointRecovering,
    toggleSuppress,
    suppressingId,
    openTreeMenu,
    renamingId,
    commitRename,
    setRenamingId,
    reorderTree,
    selectBody,
  } = treeActions;
  const { repickFace, repickEdges, dismissedMovedEdges, dismissMovedEdge } =
    editorRepick;
  const { bodies, lumpsByFeature } = featureCatalog;
  return (
    <>
      <ChromeRail side="left">
        <FloatingPanel side="left" title="Feature tree" id="tree">
          <div className="flex flex-col gap-3">
            <FeatureTreePanel
              tree={tree.data}
              treeError={tree.error}
              evaluation={evaluation.data}
              build={build}
              selectedFeatureId={selectedFeatureId}
              scopedFeatureIds={scopedFeatureIds ?? undefined}
              onSelectFeature={selectFeature}
              onKeepAsOneBody={keepAsOneBody}
              recoveringDisjoint={disjointRecovering}
              onRepickFace={repickFace}
              onRepickEdges={repickEdges}
              dismissedWarnings={dismissedMovedEdges}
              onDismissWarning={dismissMovedEdge}
              onToggleSuppress={toggleSuppress}
              suppressingId={suppressingId}
              onRowContextMenu={openTreeMenu}
              renamingId={renamingId}
              onCommitRename={commitRename}
              onCancelRename={() => setRenamingId(null)}
              onReorder={reorderTree}
            />
            {bodies.length > 0 ? (
              <BodiesPanel
                bodies={bodies}
                lumpsByFeature={lumpsByFeature}
                selectedFeatureId={selectedFeatureId}
                onSelectBody={selectBody}
              />
            ) : null}
          </div>
        </FloatingPanel>
      </ChromeRail>
    </>
  );
}

/**
 * The right rail: the Parameters panel when it is open, over the inspector
 * (mass properties, material, EXPORT) or, with no body yet, the EXPORT strip
 * alone. Parameters sits ABOVE the inspector so a change to a value and the
 * mass it moves are read in one column.
 */
export function InspectorRail({
  viewportState,
  partDocument,
  partBody,
  materialPanel,
  partVersions,
  partParameters,
}: {
  viewportState: Pick<
    ViewportState,
    "showInspector" | "build" | "showExportOnly"
  >;
  partDocument: Pick<PartDocument, "partId" | "lengthUnit">;
  partBody: Pick<PartBody, "bodyProperties">;
  materialPanel: Pick<MaterialControls, "materialControls">;
  partVersions: Pick<PartVersions, "openPanel">;
  partParameters: PartParameters;
}) {
  const { showInspector, build, showExportOnly } = viewportState;
  const { partId, lengthUnit } = partDocument;
  const { bodyProperties } = partBody;
  const { materialControls } = materialPanel;
  const versionActions = { onShowVersions: partVersions.openPanel };
  return (
    <>
      <ChromeRail side="right">
        {partParameters.panelOpen ? (
          <FloatingPanel
            side="right"
            title="Parameters"
            id="parameters"
            width="parameters"
            holds
          >
            <ParametersPanel
              rows={partParameters.rows}
              stored={partParameters.stored}
              documentUnit={lengthUnit}
              loadError={partParameters.loadError}
              error={partParameters.error}
              stale={partParameters.stale}
              saving={partParameters.saving}
              blockedReason={partParameters.blockedReason}
              refreshFailed={partParameters.refreshFailed}
              onReload={partParameters.reload}
              focusRowId={partParameters.focusRowId}
              onCommitCell={partParameters.commitCell}
              onUnitChange={partParameters.setUnit}
              onAdd={partParameters.addRow}
              onDelete={partParameters.deleteRow}
              onRetry={partParameters.retry}
              onClose={partParameters.closePanel}
            />
          </FloatingPanel>
        ) : null}
        {showInspector ? (
          // The EXPORT strip is PINNED under the panel, not trailing the
          // scrolling readouts: the panel's height is clamped (it clears the
          // reference cube), so whatever sits last in the column is whatever
          // goes under the fold — and on a 1366x768 frame that was the strip
          // plus the sentence warning that the file will be marked *partial*
          // (UI-REVIEW 2026-07-30 P1, a regression of the 48px timeline).
          // Mass properties scroll; the actions never move.
          <FloatingPanel
            side="right"
            title="Inspector"
            id="inspector"
            footer={
              <Panel className="border-t-0">
                <PartExportControls
                  partId={partId}
                  build={build}
                  versionActions={versionActions}
                />
              </Panel>
            }
          >
            <BodyInspector
              properties={bodyProperties}
              build={build}
              material={materialControls}
            />
          </FloatingPanel>
        ) : showExportOnly ? (
          // No body yet (a sketch-only or rolled-back tree), but the part is
          // modeled enough to have a tree — offer the EXPORT strip in its
          // honest disabled state so the affordance is discoverable.
          <FloatingPanel side="right" title="Export" id="inspector">
            <aside
              className="w-full"
              aria-label="Part export"
              data-testid="part-export-idle"
            >
              <Panel>
                <PartExportControls
                  partId={partId}
                  build={build}
                  versionActions={versionActions}
                />
              </Panel>
            </aside>
          </FloatingPanel>
        ) : null}
      </ChromeRail>
    </>
  );
}
