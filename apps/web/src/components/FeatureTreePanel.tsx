/**
 * The feature tree as a title block: ruled rows carrying the part's build
 * order (the row number IS the evaluation order — structure encoding truth),
 * per-feature evaluate status, and the NEW SKETCH action cell.
 */
import { Panel, PanelActionCell, PanelSection } from "@loft/design";

import type { EvaluateTreeResult, FeatureTreeResponse } from "../api/parts";

export interface FeatureTreePanelProps {
  tree: FeatureTreeResponse | undefined;
  treeError: Error | null;
  evaluation: EvaluateTreeResult | undefined;
  evaluating: boolean;
  /** Enter sketch mode (disabled while already sketching). */
  onNewSketch: () => void;
  sketchActive: boolean;
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
}: FeatureTreePanelProps) {
  const statusById = new Map(
    (evaluation?.features ?? []).map((f) => [f.feature_id, f.status]),
  );
  const evalSummary = evaluating
    ? "Solving…"
    : evaluation === undefined
      ? "—"
      : evaluation.features.some((f) => f.status === "error")
        ? "Failed"
        : "Solved";

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
          ) : tree.features.length === 0 ? (
            <p className="px-3 py-1 font-body text-xs text-gauge">
              No features yet. Start with a sketch.
            </p>
          ) : (
            <ol className="pb-1">
              {tree.features.map((feature, index) => {
                const status = statusById.get(feature.id);
                return (
                  <li
                    key={feature.id}
                    className="flex items-baseline gap-2 px-3 py-1"
                    data-testid="feature-row"
                  >
                    <span className="w-5 shrink-0 font-data text-xs tabular-nums text-gauge">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="grow truncate font-data text-base text-mist">
                      {feature.name}
                    </span>
                    <span className="shrink-0 font-body text-xs text-gauge">
                      {feature.feature.type}
                    </span>
                    <span
                      className={`w-8 shrink-0 text-right font-data text-xs ${
                        status === "error" ? "text-flag" : "text-gauge"
                      }`}
                      aria-label={status ? `evaluation ${status}` : undefined}
                    >
                      {status ? STATUS_LABEL[status] : "—"}
                    </span>
                  </li>
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
