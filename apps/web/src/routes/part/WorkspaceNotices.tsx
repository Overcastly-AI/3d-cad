/**
 * The part workspace's status notices and alerts. Split out of
 * `PartPage.tsx` (SPLIT-PARTPAGE); behaviour unchanged.
 */

import { type FeatureResponse } from "../../api/parts";
import { RailDock } from "../../components/ChromeRail";
import { partialBodySentence } from "../../features/partBuild";
import { HistoryErrorAlert } from "../../components/HistoryErrorAlert";
import { useLoftImportNotice } from "../../features/loftImport";
import { draftAge } from "../sketchDraft";
import type { ActionFlags } from "./useActionFlags";
import type { TimelineHistory } from "./useTimelineHistory";
import type { PartBody } from "./usePartBody";
import type { RebuildNotices } from "./useRebuildNotices";
import type { EditorSeat } from "./useEditorSeat";
import type { ViewportState } from "./useViewportState";
import type { FeatureCatalog } from "./useFeatureCatalog";
import type { SketchPersistence } from "./useSketchPersistence";
import type { TreeActions } from "./useTreeActions";

/**
 * The discrete actions' HUD notices: STEP import, flat pattern, and the
 * undo/redo failure alert.
 */
export function ActionNotices({
  actionFlags,
  timelineHistory,
}: {
  actionFlags: Pick<
    ActionFlags,
    | "importing"
    | "importError"
    | "setImportError"
    | "flatPatternBusy"
    | "flatPatternError"
    | "setFlatPatternError"
  >;
  timelineHistory: Pick<TimelineHistory, "historyError" | "setHistoryError">;
}) {
  const {
    importing,
    importError,
    setImportError,
    flatPatternBusy,
    flatPatternError,
    setFlatPatternError,
  } = actionFlags;
  const { historyError, setHistoryError } = timelineHistory;
  return (
    <>
      {importing ? (
        <div
          role="status"
          data-testid="import-step-status"
          className="absolute bottom-3 left-3 rounded-sm border border-hairline bg-anvil px-3 py-2"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Importing STEP
          </span>
          <span className="mt-1 block font-body text-xs text-mist">
            Reading the solid and building the base body.
          </span>
        </div>
      ) : importError !== null ? (
        <div
          role="alert"
          data-testid="import-step-error"
          className="absolute bottom-3 left-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
            Import failed
          </span>
          <span className="mt-1 block font-body text-xs text-mist">
            {importError}
          </span>
          <button
            type="button"
            onClick={() => setImportError(null)}
            data-testid="import-step-dismiss"
            className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Dismiss
          </button>
        </div>
      ) : null}
      {flatPatternBusy ? (
        <div
          role="status"
          data-testid="flat-pattern-status"
          className="absolute bottom-3 left-3 rounded-sm border border-hairline bg-anvil px-3 py-2"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Unfolding flat pattern
          </span>
          <span className="mt-1 block font-body text-xs text-mist">
            Laying the blank onto a drawing sheet.
          </span>
        </div>
      ) : flatPatternError !== null ? (
        <div
          role="alert"
          data-testid="flat-pattern-error"
          className="absolute bottom-3 left-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
            Flat pattern failed
          </span>
          <span className="mt-1 block font-body text-xs text-mist">
            {flatPatternError}
          </span>
          <button
            type="button"
            onClick={() => setFlatPatternError(null)}
            data-testid="flat-pattern-dismiss"
            className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Dismiss
          </button>
        </div>
      ) : null}
      <HistoryErrorAlert
        error={historyError}
        onDismiss={() => setHistoryError(null)}
      />
    </>
  );
}

/**
 * The body's notices at the editor seat: regenerating, unavailable, the
 * last save's rebuild error, and the partial-body notice.
 */
export function BodyNotices({
  partBody,
  rebuildNotices,
  editorSeat,
  viewportState,
  featureCatalog,
  selectFeature,
}: {
  partBody: Pick<
    PartBody,
    "regenerating" | "regenFailed" | "retryBody" | "editor"
  >;
  rebuildNotices: Pick<RebuildNotices, "rebuildNotice">;
  editorSeat: Pick<EditorSeat, "setRebuildNoticeDismissed">;
  viewportState: Pick<ViewportState, "build">;
  featureCatalog: Pick<FeatureCatalog, "features">;
  selectFeature: (feature: FeatureResponse) => void;
}) {
  const { regenerating, regenFailed, retryBody, editor } = partBody;
  const { rebuildNotice } = rebuildNotices;
  const { setRebuildNoticeDismissed } = editorSeat;
  const { build } = viewportState;
  const { features } = featureCatalog;
  return (
    <>
      <RailDock side="left">
        {regenerating ? (
          <div
            role="status"
            data-testid="body-regenerating"
            className="rounded-sm border border-hairline bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-gauge">
              Regenerating body
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              The mesh expired from the cache — re-evaluating the tree.
            </span>
          </div>
        ) : regenFailed ? (
          <div
            role="alert"
            data-testid="body-regen-failed"
            className="rounded-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              Body unavailable
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              The body mesh could not be regenerated.
            </span>
            <button
              type="button"
              onClick={retryBody}
              className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
            >
              Re-evaluate
            </button>
          </div>
        ) : editor === null && rebuildNotice !== null ? (
          <div
            role="alert"
            data-testid="rebuild-notice"
            className="rounded-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              This feature couldn't build
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              {rebuildNotice}
            </span>
            <button
              type="button"
              onClick={() => setRebuildNoticeDismissed(true)}
              data-testid="rebuild-notice-dismiss"
              className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
            >
              Dismiss
            </button>
          </div>
        ) : editor === null && build.failed && build.hasBody ? (
          // WHAT YOU ARE LOOKING AT (AUDIT-PRODUCT N3). The strict-prefix
          // rule renders the last-good PREFIX, so one bad pick can turn a
          // modelled bracket into a bare brick — and until now nothing on
          // screen said the solid was not the part. `last_good_feature_id`
          // was on the wire and unused; it names the state being shown.
          // NOT dismissible: it describes a live condition, and it leaves
          // when the condition does.
          <div
            role="status"
            data-testid="partial-body-notice"
            className="rounded-sm border border-flag bg-anvil px-3 py-2"
          >
            <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
              Partial body
            </span>
            <span className="mt-1 block font-body text-xs text-mist">
              {partialBodySentence(build)}
            </span>
            {build.failure !== null ? (
              <button
                type="button"
                onClick={() => {
                  const failed = features.find(
                    (f) => f.id === build.failure?.id,
                  );
                  if (failed !== undefined) selectFeature(failed);
                }}
                data-testid="partial-body-show-failure"
                className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
              >
                Show {build.failure.name}
              </button>
            ) : null}
          </div>
        ) : null}
      </RailDock>
    </>
  );
}

/**
 * FLOW-A2's restored-draft note.
 */
export function DraftRestoredNote({
  sketchPersistence,
}: {
  sketchPersistence: Pick<
    SketchPersistence,
    "restoredDraft" | "setRestoredDraft"
  >;
}) {
  const { restoredDraft, setRestoredDraft } = sketchPersistence;
  return (
    <>
      {restoredDraft !== null ? (
        <div
          role="status"
          data-testid="sketch-draft-restored"
          className="absolute bottom-hud-lane left-1/2 z-hud flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-3 border border-hairline bg-anvil/90 px-3 py-1.5 shadow-float backdrop-blur-sm"
        >
          <span className="shrink-0 font-display text-2xs uppercase tracking-[0.16em] text-brass">
            Draft restored
          </span>
          <span aria-hidden className="h-3 w-px shrink-0 bg-hairline" />
          <span className="min-w-0 font-body text-2xs text-gauge">
            <span className="font-data text-mist">
              {restoredDraft.entities}
            </span>{" "}
            {restoredDraft.entities === 1 ? "entity" : "entities"} from{" "}
            {draftAge(restoredDraft.savedAt)}, kept in this browser — Save
            sketch puts them in the part.
          </span>
          <button
            type="button"
            onClick={() => setRestoredDraft(null)}
            data-testid="sketch-draft-restored-dismiss"
            className="shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Dismiss
          </button>
        </div>
      ) : null}
    </>
  );
}

/**
 * A failed tree action (rename/delete), honest and dismissible.
 */
export function TreeActionErrorNote({
  treeActions,
}: {
  treeActions: Pick<TreeActions, "treeActionError" | "setTreeActionError">;
}) {
  const { treeActionError, setTreeActionError } = treeActions;
  return (
    <>
      {treeActionError !== null ? (
        <div
          role="alert"
          data-testid="tree-action-error"
          className="absolute bottom-3 left-3 z-hud max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
        >
          <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
            Action failed
          </span>
          <span className="mt-1 block font-body text-xs text-mist">
            {treeActionError}
          </span>
          <button
            type="button"
            onClick={() => setTreeActionError(null)}
            data-testid="tree-action-error-dismiss"
            className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Dismiss
          </button>
        </div>
      ) : null}
    </>
  );
}

/**
 * What a `.loft` import noticed without refusing (docs/FILE-FORMAT.md): a
 * hand-edited tree, a rebuilt volume that differs from the file's, features
 * that failed to rebuild. Shown on the part the import CREATED — the store
 * carries the warnings across the navigation — until dismissed.
 */
export function LoftImportNotice({ partId }: { partId: string }) {
  const notice = useLoftImportNotice();
  if (notice.partId !== partId || notice.warnings.length === 0) return null;
  return (
    <div
      role="alert"
      data-testid="loft-import-warnings"
      className="absolute bottom-3 left-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
    >
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
        Imported with warnings
      </span>
      {notice.warnings.map((warning) => (
        <span
          key={warning.code}
          data-warning-code={warning.code}
          className="mt-1 block font-body text-xs text-mist"
        >
          {warning.message}
        </span>
      ))}
      <button
        type="button"
        onClick={notice.dismiss}
        data-testid="loft-import-dismiss"
        className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
      >
        Dismiss
      </button>
    </div>
  );
}
