/**
 * The feature tree as a title block: ruled rows carrying the part's build
 * order (the row number IS the evaluation order — structure encoding truth),
 * per-feature evaluate status/error, a rollback "cut line" the build can be
 * wound back to, and the FEATURES / TREE / SOLVE vitals. The CREATE tools now
 * live in the full-width top band (CreateStrip), not here — the panel is a
 * quiet read-out of the build. Selecting a row hands it up to the workspace
 * (an extrude opens its editor); rolling the bar before a feature marks
 * everything below it inert without deleting it.
 */
import {
  Button,
  Panel,
  PanelSection,
  SuppressIcon,
  TextField,
} from "@loft/design";
import type { ReactNode } from "react";

import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureResult,
  FeatureTreeResponse,
} from "../api/parts";
import {
  friendlyFeatureError,
  KEEP_AS_ONE_BODY_ACTION,
  offersBooleanDisjointRecovery,
  offersRepickFace,
  REPICK_FACE_ACTION,
} from "../features/featureErrors";
import { holeThreadDesignation } from "../features/hole";
import { barSlotIndex, rollbackIdForSlot } from "../features/rollback";

export interface FeatureTreePanelProps {
  tree: FeatureTreeResponse | undefined;
  treeError: Error | null;
  evaluation: EvaluateTreeResult | undefined;
  evaluating: boolean;
  /** Selected feature id (brass left-rule); extrude rows open their editor. */
  selectedFeatureId: string | null;
  onSelectFeature: (feature: FeatureResponse) => void;
  /** Move the rollback bar (null = tip); the workspace re-evaluates. */
  onMoveRollback: (rollbackFeatureId: string | null) => void;
  rollbackBusy: boolean;
  /** Guided recovery for a `boolean_disjoint` error (MB-4c): re-run this boolean
   * with `allow_disjoint` on, keeping the disconnected pieces as one multi-lump
   * body. Only offered when the feature is a boolean whose opt-in is still off. */
  onKeepAsOneBody?: (feature: FeatureResponse) => void;
  /** True while a `boolean_disjoint` recovery write is in flight — disables the
   * recovery button so a double-click can't enqueue two updates. */
  recoveringDisjoint?: boolean;
  /** Re-pick repair for a `subshape_unresolved` error (FINDINGS #3): re-arm face
   * selection for this feature so the user can re-attach the lost reference.
   * Absent = no repair offered (e.g. the assembly reuse). */
  onRepickFace?: (feature: FeatureResponse) => void;
  /** Toggle a feature's suppress flag (feature-tree.md §4.3a): a suppressed
   * feature is skipped at rebuild but stays in the tree (reversible). */
  onToggleSuppress: (feature: FeatureResponse) => void;
  /** The feature id whose suppress toggle is mid-write — disables its control
   * so a double-click can't enqueue two flips. */
  suppressingId?: string | null;
  /** Right-click on a row (UI-REVIEW #10): open the row context menu at the
   * pointer. Absent = no menu (e.g. the assembly reuse, which has none). */
  onRowContextMenu?: (feature: FeatureResponse, x: number, y: number) => void;
  /** The feature id whose name is being edited inline (from the row menu's
   * Rename); its label cell becomes a text field. */
  renamingId?: string | null;
  /** Commit an inline rename (Enter / blur) — a no-op upstream when unchanged. */
  onCommitRename?: (feature: FeatureResponse, name: string) => void;
  /** Abandon an inline rename (Escape) without writing. */
  onCancelRename?: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  error: "ERR",
  skipped: "SKIP",
  suppressed: "SUPP",
};

/**
 * Friendlier type badges for the few feature types whose wire name is
 * snake_case. Everything else (extrude / fillet / …) is already a plain word,
 * so it falls through to the raw type.
 */
const FEATURE_TYPE_LABEL: Record<string, string> = {
  sheet_metal_base_flange: "base flange",
  sheet_metal_edge_flange: "edge flange",
  sheet_metal_hem: "hem",
  sheet_metal_corner_relief: "corner relief",
};

/** The badge text for a feature type — a friendly label, else the raw type. */
function featureTypeLabel(type: string): string {
  return FEATURE_TYPE_LABEL[type] ?? type;
}

/**
 * The row's right-hand badge: what this feature IS. Normally just its type —
 * with one exception the geometry forces. A TAPPED hole's solid is byte-
 * identical to a plain bore (the thread is a cosmetic callout, not modelled
 * helical geometry), so the viewport cannot show it and the tree is the only
 * place a modeler can tell an M10x1.5 from the Ø8.5 clearance hole beside it.
 * The badge therefore carries the designation: `hole · M10x1.5`.
 *
 * A counterbore/countersink deliberately does NOT extend the badge: its recess
 * is real geometry you can see in the viewport, so naming it here would be
 * duplication. Only the invisible parameter earns the pixels.
 */
function featureBadge(feature: FeatureResponse["feature"]): string {
  const label = featureTypeLabel(feature.type);
  if (feature.type === "hole") {
    const designation = holeThreadDesignation(feature.params);
    if (designation !== null) return `${label} · ${designation}`;
  }
  return label;
}

export function FeatureTreePanel({
  tree,
  treeError,
  evaluation,
  evaluating,
  selectedFeatureId,
  onSelectFeature,
  onMoveRollback,
  rollbackBusy,
  onKeepAsOneBody,
  recoveringDisjoint = false,
  onRepickFace,
  onToggleSuppress,
  suppressingId = null,
  onRowContextMenu,
  renamingId = null,
  onCommitRename,
  onCancelRename,
}: FeatureTreePanelProps) {
  const resultById = new Map<string, FeatureResult>(
    (evaluation?.features ?? []).map((f) => [f.feature_id, f]),
  );
  const features = tree?.features ?? [];
  // The feature count folds into the eyebrow (it was a redundant footer cell —
  // the rows are numbered right above it; UI-REVIEW 2026-07-16, Track B).
  const treeEyebrow =
    features.length > 0 ? `Feature tree · ${features.length}` : "Feature tree";
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
      className="flex w-full flex-col gap-3"
      aria-label="Feature tree"
      data-testid="feature-tree"
    >
      <Panel>
        <PanelSection eyebrow={treeEyebrow} data-testid="feature-tree-section">
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
                // Suppressed reads from the persisted envelope flag (authoritative
                // the instant the tree refetches, before the re-evaluate lands)
                // OR the evaluate's dedicated `suppressed` status — either marks
                // the row quiet-and-struck, distinct from a red error.
                const suppressed =
                  (feature.feature.suppressed ?? false) ||
                  status === "suppressed";
                const suppressBusy = feature.id === suppressingId;
                const renaming = feature.id === renamingId;
                return (
                  <FeatureRowGroup key={feature.id}>
                    <li
                      className={`group/row flex items-baseline gap-2 border-l-2 py-1 pr-2 pl-[10px] ${
                        selected ? "border-brass" : "border-transparent"
                      }`}
                      data-testid="feature-row"
                      data-rolled-back={rolledBack || undefined}
                      data-suppressed={suppressed || undefined}
                      onContextMenu={
                        onRowContextMenu
                          ? (event) => {
                              event.preventDefault();
                              onRowContextMenu(
                                feature,
                                event.clientX,
                                event.clientY,
                              );
                            }
                          : undefined
                      }
                    >
                      {renaming ? (
                        <div className="flex grow items-baseline gap-2">
                          <span className="w-5 shrink-0 font-data text-xs tabular-nums text-gauge">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <TextField
                            label={`Rename ${feature.name}`}
                            hideLabel
                            autoFocus
                            defaultValue={feature.name}
                            className="grow"
                            data-testid={`feature-rename-${index}`}
                            onFocus={(e) => e.currentTarget.select()}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                onCommitRename?.(
                                  feature,
                                  e.currentTarget.value,
                                );
                              } else if (e.key === "Escape") {
                                e.preventDefault();
                                e.stopPropagation();
                                onCancelRename?.();
                              }
                            }}
                            onBlur={(e) =>
                              onCommitRename?.(feature, e.currentTarget.value)
                            }
                          />
                          <span className="shrink-0 font-body text-xs text-gauge">
                            {featureBadge(feature.feature)}
                          </span>
                        </div>
                      ) : (
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
                              suppressed
                                ? "text-gauge line-through decoration-etch"
                                : rolledBack
                                  ? "text-gauge"
                                  : "text-mist"
                            }`}
                          >
                            {feature.name}
                          </span>
                          <span className="shrink-0 font-body text-xs text-gauge">
                            {featureBadge(feature.feature)}
                          </span>
                        </button>
                      )}
                      {/* Suppress toggle — quiet by default, brass when the
                          feature is suppressed. Struck-out row + this pressed
                          control read "held out of the build", reversibly. */}
                      <button
                        type="button"
                        onClick={() => onToggleSuppress(feature)}
                        disabled={suppressBusy}
                        aria-pressed={suppressed}
                        aria-busy={suppressBusy}
                        aria-label={`Suppress ${feature.name}`}
                        data-testid={`feature-suppress-${index}`}
                        className={`shrink-0 rounded-sm p-0.5 transition-colors duration-fast focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:cursor-default ${
                          suppressed
                            ? "text-brass"
                            : "text-gauge opacity-60 hover:text-mist hover:opacity-100 group-focus-within/row:opacity-100 group-hover/row:opacity-100"
                        }`}
                      >
                        <SuppressIcon size={14} />
                      </button>
                      <span
                        className={`w-8 shrink-0 text-right font-data text-xs ${
                          status === "error" ? "text-flag" : "text-gauge"
                        }`}
                        aria-label={
                          rolledBack
                            ? "rolled back"
                            : suppressed
                              ? "evaluation suppressed"
                              : status
                                ? `evaluation ${status}`
                                : undefined
                        }
                      >
                        {rolledBack
                          ? "—"
                          : suppressed
                            ? STATUS_LABEL.suppressed
                            : status
                              ? STATUS_LABEL[status]
                              : "—"}
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
                          {friendlyFeatureError(
                            result.error.code,
                            result.error.message,
                            feature.feature.type,
                          )}
                        </span>
                        {onKeepAsOneBody &&
                        offersBooleanDisjointRecovery(
                          feature,
                          result.error.code,
                        ) ? (
                          <Button
                            variant="ghost"
                            className="mt-1.5 py-0.5 text-xs"
                            disabled={recoveringDisjoint}
                            aria-busy={recoveringDisjoint}
                            data-testid={`feature-recover-disjoint-${index}`}
                            onClick={() => onKeepAsOneBody(feature)}
                          >
                            {recoveringDisjoint
                              ? "Combining…"
                              : KEEP_AS_ONE_BODY_ACTION}
                          </Button>
                        ) : null}
                        {onRepickFace &&
                        offersRepickFace(feature, result.error.code) ? (
                          <Button
                            variant="ghost"
                            className="mt-1.5 py-0.5 text-xs"
                            data-testid={`feature-repick-face-${index}`}
                            onClick={() => onRepickFace(feature)}
                          >
                            {REPICK_FACE_ACTION}
                          </Button>
                        ) : null}
                      </li>
                    ) : null}
                    {renderBar(index)}
                  </FeatureRowGroup>
                );
              })}
            </ol>
          )}
        </PanelSection>

        {/* Title-block footer: the one vital that MOVES — the solve state.
            FEATURES folded into the eyebrow; TREE (the internal optimistic-
            concurrency version) was decorative and is gone (Track B). */}
        <div className="border-t border-hairline px-3 py-2">
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
