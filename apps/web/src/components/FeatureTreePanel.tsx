/**
 * The feature tree as a title block: ruled rows carrying the part's build
 * order (the row number IS the evaluation order — structure encoding truth),
 * per-feature evaluate status/error, a rollback "cut line" the build can be
 * wound back to, and the NEW SKETCH / EXTRUDE action cells. Selecting a row
 * hands it up to the workspace (an extrude opens its editor); rolling the bar
 * before a feature marks everything below it inert without deleting it.
 */
import { Panel, PanelActionCell, PanelSection } from "@loft/design";
import type { ReactNode } from "react";

import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureResult,
  FeatureTreeResponse,
} from "../api/parts";
import { barSlotIndex, rollbackIdForSlot } from "../features/rollback";

export interface FeatureTreePanelProps {
  tree: FeatureTreeResponse | undefined;
  treeError: Error | null;
  evaluation: EvaluateTreeResult | undefined;
  evaluating: boolean;
  /** Enter sketch mode (disabled while already sketching). */
  onNewSketch: () => void;
  sketchActive: boolean;
  /** True when a solved sketch exists to extrude. */
  canExtrude: boolean;
  /** Begin a new extrude against the last solved sketch. */
  onNewExtrude: () => void;
  /** True when a solved sketch exists to revolve (same gate as extrude). */
  canRevolve: boolean;
  /** Begin a new revolve against the last solved sketch. */
  onNewRevolve: () => void;
  /** Selected feature id (brass left-rule); extrude rows open their editor. */
  selectedFeatureId: string | null;
  onSelectFeature: (feature: FeatureResponse) => void;
  /** Move the rollback bar (null = tip); the workspace re-evaluates. */
  onMoveRollback: (rollbackFeatureId: string | null) => void;
  rollbackBusy: boolean;
}

const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  error: "ERR",
  skipped: "SKIP",
};

export function FeatureTreePanel({
  tree,
  treeError,
  evaluation,
  evaluating,
  onNewSketch,
  sketchActive,
  canExtrude,
  onNewExtrude,
  canRevolve,
  onNewRevolve,
  selectedFeatureId,
  onSelectFeature,
  onMoveRollback,
  rollbackBusy,
}: FeatureTreePanelProps) {
  const resultById = new Map<string, FeatureResult>(
    (evaluation?.features ?? []).map((f) => [f.feature_id, f]),
  );
  const features = tree?.features ?? [];
  const rollbackId = tree?.rollback_feature_id ?? null;
  const barSlot = barSlotIndex(features, rollbackId);
  const evalSummary = evaluating
    ? "Solving…"
    : evaluation === undefined
      ? "—"
      : evaluation.features.some((f) => f.status === "error")
        ? "Failed"
        : "Solved";

  const renderBar = (slotIndex: number) => {
    const active = slotIndex === barSlot;
    const target = rollbackIdForSlot(features, slotIndex);
    const atTip = slotIndex >= features.length - 1;
    return (
      <li key={`slot-${slotIndex}`} className="px-3">
        <button
          type="button"
          disabled={rollbackBusy || active}
          data-testid={`rollback-slot-${slotIndex}`}
          data-active={active || undefined}
          aria-label={
            atTip
              ? "Roll forward to the tip (include all features)"
              : `Roll back to after ${features[slotIndex]?.name ?? "feature"}`
          }
          onClick={() => onMoveRollback(target)}
          className="group flex w-full items-center gap-2 py-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:cursor-default"
        >
          {active ? (
            <>
              <span
                aria-hidden
                className="h-px grow bg-brass"
                data-testid="rollback-bar"
              />
              <span className="shrink-0 font-display text-2xs uppercase tracking-[0.18em] text-brass">
                Rollback
              </span>
              <span aria-hidden className="h-px w-3 bg-brass" />
            </>
          ) : (
            <span
              aria-hidden
              className="h-px grow bg-transparent transition-colors duration-fast group-hover:bg-etch"
            />
          )}
        </button>
      </li>
    );
  };

  return (
    <aside
      className="flex w-full shrink-0 flex-col gap-3 overflow-y-auto p-3 md:w-inspector"
      aria-label="Feature tree"
      data-testid="feature-tree"
    >
      <Panel>
        <PanelSection eyebrow="Feature tree">
          {tree === undefined ? (
            <p className="px-3 py-1 font-body text-xs text-gauge">
              {treeError ? "The feature tree could not be loaded." : "Loading…"}
            </p>
          ) : features.length === 0 ? (
            <p className="px-3 py-1 font-body text-xs text-gauge">
              No features yet. Start with a sketch.
            </p>
          ) : (
            <ol className="pb-1">
              {features.map((feature, index) => {
                const result = resultById.get(feature.id);
                const status = result?.status;
                const rolledBack = index > barSlot;
                const selected = feature.id === selectedFeatureId;
                return (
                  <FeatureRowGroup key={feature.id}>
                    <li
                      className={`flex items-baseline gap-2 border-l-2 py-1 pr-3 pl-[10px] ${
                        selected ? "border-brass" : "border-transparent"
                      }`}
                      data-testid="feature-row"
                      data-rolled-back={rolledBack || undefined}
                    >
                      <button
                        type="button"
                        onClick={() => onSelectFeature(feature)}
                        aria-pressed={selected}
                        aria-label={`Select ${feature.name}`}
                        data-testid={`feature-select-${index}`}
                        className="flex grow items-baseline gap-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                      >
                        <span className="w-5 shrink-0 font-data text-xs tabular-nums text-gauge">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span
                          className={`grow truncate font-data text-base ${
                            rolledBack ? "text-gauge" : "text-mist"
                          }`}
                        >
                          {feature.name}
                        </span>
                        <span className="shrink-0 font-body text-xs text-gauge">
                          {feature.feature.type}
                        </span>
                      </button>
                      <span
                        className={`w-8 shrink-0 text-right font-data text-xs ${
                          status === "error" ? "text-flag" : "text-gauge"
                        }`}
                        aria-label={
                          rolledBack
                            ? "rolled back"
                            : status
                              ? `evaluation ${status}`
                              : undefined
                        }
                      >
                        {rolledBack ? "—" : status ? STATUS_LABEL[status] : "—"}
                      </span>
                    </li>
                    {status === "error" && result?.error && !rolledBack ? (
                      <li
                        className="border-l-2 border-flag py-1 pr-3 pl-[26px]"
                        role="alert"
                        data-testid={`feature-error-${index}`}
                      >
                        <span className="block font-display text-2xs uppercase tracking-[0.14em] text-flag">
                          {result.error.code}
                        </span>
                        <span className="mt-0.5 block font-body text-xs text-mist">
                          {result.error.message}
                        </span>
                      </li>
                    ) : null}
                    {renderBar(index)}
                  </FeatureRowGroup>
                );
              })}
            </ol>
          )}
        </PanelSection>

        <PanelActionCell
          label="New sketch"
          caption="Pick a plane, then L / R / C / A"
          data-testid="new-sketch"
          disabled={sketchActive || tree === undefined}
          onClick={onNewSketch}
        />
        <PanelActionCell
          label="Extrude"
          caption={
            canExtrude ? "Add or cut a sketch profile" : "Solve a sketch first"
          }
          data-testid="new-extrude"
          disabled={!canExtrude || sketchActive || tree === undefined}
          onClick={onNewExtrude}
        />
        <PanelActionCell
          label="Revolve"
          caption={
            canRevolve
              ? "Sweep a sketch profile about an axis"
              : "Solve a sketch first"
          }
          data-testid="new-revolve"
          disabled={!canRevolve || sketchActive || tree === undefined}
          onClick={onNewRevolve}
        />

        {/* Title-block footer: the tree's vitals. */}
        <div className="grid grid-cols-3 divide-x divide-hairline border-t border-hairline">
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              Features
            </span>
            <span
              className="block font-data text-xs text-mist"
              data-testid="feature-count"
            >
              {tree?.features.length ?? "—"}
            </span>
          </div>
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              Tree
            </span>
            <span className="block font-data text-xs text-mist">
              {tree ? `v${tree.tree_version}` : "—"}
            </span>
          </div>
          <div className="px-3 py-2">
            <span className="block font-display text-2xs uppercase tracking-[0.14em] text-gauge">
              Solve
            </span>
            <span
              className="block font-data text-xs text-mist"
              data-testid="eval-status"
              aria-live="polite"
            >
              {evalSummary}
            </span>
          </div>
        </div>
      </Panel>

      {treeError ? (
        <p role="alert" className="font-body text-xs text-flag">
          {treeError.message}
        </p>
      ) : null}
    </aside>
  );
}

/** A fragment wrapper so each feature contributes several <li> siblings. */
function FeatureRowGroup({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
