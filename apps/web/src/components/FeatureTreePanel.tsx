/**
 * The feature tree as a title block: ruled rows carrying the part's build
 * order (the row number IS the evaluation order — structure encoding truth),
 * per-feature evaluate status/error, and the SOLVE vital. The CREATE tools live
 * in the full-width top band (CreateStrip) and ROLLBACK now lives in the bottom
 * TimelineStrip (UI-W1) — the panel is a quiet read-out of the build. Selecting
 * a row hands it up to the workspace (an extrude opens its editor).
 *
 * The panel still SHOWS the travel stop's effect (`data-rolled-back` rows, dashed
 * "—" status) — it just no longer offers the control: a 1px dashed rule squeezed
 * between 24px rows was never a scrub control, and the build order is honestly
 * horizontal (see `TimelineStrip`).
 */
import {
  Button,
  EyeIcon,
  EyeOffIcon,
  Panel,
  PanelSection,
  Stamp,
  SuppressIcon,
  TextField,
} from "@loft/design";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

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
import { featureTypeLabel } from "../features/featureLabels";
import {
  conflictMessage,
  firstOrderConflict,
  movedOrder,
  nearestLegalIndex,
  repairLabel,
  type OrderConflict,
} from "./featureOrder";
import { scopeBadgeSuffix } from "../features/patternScope";
import { holeThreadDesignation } from "../features/hole";
import { KEY_REORDER_EARLIER, KEY_REORDER_LATER } from "../shortcuts/registry";
import { usePrefetchIntent } from "../features/prefetch";
import {
  excludedNote,
  type PartBuild,
  skippedReason,
  solveSummary,
} from "../features/partBuild";
import { barSlotIndex } from "../features/rollback";
import {
  entityIsDrawn,
  ORIGIN_AXES,
  ORIGIN_PLANES,
  originAxisKey,
  originPlaneKey,
  sketchIsDrawn,
  sketchKey,
  usePartViewStore,
} from "../viewport/partView";

export interface FeatureTreePanelProps {
  tree: FeatureTreeResponse | undefined;
  treeError: Error | null;
  evaluation: EvaluateTreeResult | undefined;
  /**
   * What the workspace knows about this build (`features/partBuild.ts`) — the
   * SOLVE cell and every SKIP row's reason are derived from it, and so are the
   * inspector's STATUS cell and the EXPORT gate, so the three cannot drift
   * apart again (AUDIT-ENGINEERING J2).
   */
  build: PartBuild;
  /** Selected feature id (brass left-rule); extrude rows open their editor. */
  selectedFeatureId: string | null;
  /**
   * The feature ids the OPEN command will act on — the pattern/mirror scope,
   * published by its editor's scope row (REACH-2-FLOW P1-2). Marked distinctly
   * from selection because it answers a different question: selection is what
   * the user pointed at, scope is what the command in progress will change, and
   * on a plate with two identical holes the editor naming `HOLE1` in a side
   * panel settles neither. Empty whenever no command names a subject, which is
   * nearly always — so the mark stays rare, and therefore legible.
   */
  scopedFeatureIds?: readonly string[];
  onSelectFeature: (feature: FeatureResponse) => void;
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
  /**
   * Commit a new build order — the COMPLETE permutation of feature ids, which
   * is what `PUT …/features/order` takes. Resolves with `null` when the tree
   * accepted it, or with the pair the server refused so the panel can state the
   * reason at the seat that was attempted. Absent = the tree is read-only for
   * order (e.g. a reuse with no write path).
   */
  onReorder?: (order: string[]) => Promise<FeatureOrderRefusal | null>;
}

/** The pair a `reference_not_earlier` refusal named, as ids. */
export interface FeatureOrderRefusal {
  readonly featureId: string;
  readonly referencesFeatureId: string;
}

/**
 * A refused seat, held until the user does something else — the reason has to
 * outlive the gesture that produced it, or a keyboard user never reads it.
 */
interface RefusedSeat {
  /** Row index the refusal is drawn ABOVE — the seat that was attempted. */
  readonly seat: number;
  readonly conflict: OrderConflict;
  /** Index of the moved row when it was refused (for the repair). */
  readonly fromIndex: number;
  /** Nearest seat the tree WOULD take, or null when there is no repair. */
  readonly legalIndex: number | null;
}

const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  error: "ERR",
  skipped: "SKIP",
  suppressed: "SUPP",
};

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
function featureBadge(
  feature: FeatureResponse["feature"],
  features: readonly FeatureResponse[],
): string {
  const label = featureTypeLabel(feature.type);
  if (feature.type === "hole") {
    const designation = holeThreadDesignation(feature.params);
    if (designation !== null) return `${label} · ${designation}`;
  }
  // A pattern/mirror scoped to a FEATURE earns the same extension for the same
  // reason: `Pattern1` beside `Pattern1` cannot say which repeats the hole and
  // which repeats the plate, and that ambiguity is the defect the scope union
  // exists to end (docs/design/pattern-scope.md §1).
  const subject = scopeBadgeSuffix(feature, features);
  if (subject !== null) return `${label} · ${subject}`;
  return label;
}

export function FeatureTreePanel({
  tree,
  treeError,
  evaluation,
  build,
  selectedFeatureId,
  scopedFeatureIds,
  onSelectFeature,
  onKeepAsOneBody,
  recoveringDisjoint = false,
  onRepickFace,
  onToggleSuppress,
  suppressingId = null,
  onRowContextMenu,
  renamingId = null,
  onCommitRename,
  onCancelRename,
  onReorder,
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
  // TRIGGER 1 (docs/PERF.md PERF-1b). Selecting a row is what opens that
  // feature's editor, and it is the moment the user declares every feature
  // BEFORE it settled — so the worker starts rebuilding that prefix while the
  // dialog is being read, and the commit resumes from it instead of from
  // feature 0. It is also the only cure for the first face pick after an edit
  // (the provenance lineage is warmed alongside). Deselecting, or leaving the
  // part, cancels it: speculation outlives its reason for nobody.
  usePrefetchIntent(
    tree !== undefined && selectedFeatureId !== null
      ? {
          partId: tree.part_id,
          featureId: selectedFeatureId,
          kind: "feature_edit",
        }
      : null,
  );
  // One derivation, read here and by the inspector's STATUS cell + EXPORT gate.
  const evalSummary = solveSummary(build);
  // WHY the rows below the failure say SKIP. The strict-prefix rule stops the
  // build at the first error, so an INDEPENDENT corner fillet is dropped too —
  // and a bare "SKIP" badge made that look like a fillet bug (AUDIT-PRODUCT N3).
  const skipCause = skippedReason(build);

  // ---------------------------------------------------------------------
  // REORDER (`PUT …/features/order`). Three ways in, all anchored on the row
  // the user is already pointing at: the selected row's ORDINAL becomes its
  // grip, Alt+Up / Alt+Down move it, and a refused seat states its reason where
  // the drop was aimed instead of vanishing with the gesture.
  //
  // Nothing in the list moves until the server accepts, which is what makes
  // "Escape restores the original order" true by construction rather than by an
  // undo: a drag paints a SEAT, it does not rehearse the permutation.
  // ---------------------------------------------------------------------
  const [drag, setDrag] = useState<{
    id: string;
    from: number;
    seat: number;
  } | null>(null);
  const [refused, setRefused] = useState<RefusedSeat | null>(null);
  const [reordering, setReordering] = useState(false);
  /** Feature id whose grip should take focus once the tree has re-rendered. */
  const [focusGripId, setFocusGripId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLLIElement>());
  const gripRefs = useRef(new Map<string, HTMLButtonElement>());
  const canReorder = onReorder !== undefined && features.length > 1;

  // A reorder renumbers every row, so the grip the user was holding is a
  // different DOM node afterwards. Hand focus back to the SAME FEATURE — losing
  // it after each Alt+Up would make the keyboard path a one-shot.
  useEffect(() => {
    if (focusGripId === null) return;
    const grip = gripRefs.current.get(focusGripId);
    if (grip === undefined) return;
    grip.focus();
    setFocusGripId(null);
  }, [focusGripId, features]);

  // A refusal describes ONE seat in ONE tree. Point somewhere else, or let the
  // tree change under it, and it stops being true — so it goes, rather than
  // sitting there as a stale red block the user has to reason about.
  const treeVersion = tree?.tree_version ?? null;
  useEffect(() => {
    setRefused(null);
  }, [selectedFeatureId, treeVersion]);

  const attemptMove = useCallback(
    (fromIndex: number, toIndex: number, restoreFocus: boolean) => {
      if (onReorder === undefined || reordering) return;
      const moved = features[fromIndex];
      if (moved === undefined) return;
      if (toIndex < 0 || toIndex >= features.length || toIndex === fromIndex) {
        return;
      }
      const next = movedOrder(features, fromIndex, toIndex);
      const conflict = firstOrderConflict(next);
      if (conflict !== null) {
        const legal = nearestLegalIndex(features, fromIndex, toIndex);
        setRefused({
          seat: toIndex,
          conflict,
          fromIndex,
          legalIndex: legal === fromIndex ? null : legal,
        });
        return;
      }
      setRefused(null);
      setReordering(true);
      void onReorder(next.map((feature) => feature.id))
        .then((refusal) => {
          // The client rule and the server rule are the same edge set, so this
          // branch is a race (another client changed the tree), not a routine
          // path — it still has to say the same sentence rather than nothing.
          if (refusal === null) {
            if (restoreFocus) setFocusGripId(moved.id);
            return;
          }
          const dependent = features.find((f) => f.id === refusal.featureId);
          const reference = features.find(
            (f) => f.id === refusal.referencesFeatureId,
          );
          setRefused({
            seat: toIndex,
            fromIndex,
            legalIndex: null,
            conflict: {
              dependentId: refusal.featureId,
              dependentName: dependent?.name ?? "This feature",
              referenceId: refusal.referencesFeatureId,
              referenceName: reference?.name ?? "the feature it is built on",
            },
          });
        })
        .finally(() => setReordering(false));
    },
    [features, onReorder, reordering],
  );

  // Alt+Up / Alt+Down on the SELECTED row — the keyboard path, and the reason
  // this affordance is not drag-only (WCAG 2.2 SC 2.5.7). Every other handler
  // in the workspace bails on `altKey`, so the chord is unclaimed.
  useEffect(() => {
    if (!canReorder || selectedFeatureId === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey) return;
      if (
        event.key !== KEY_REORDER_EARLIER &&
        event.key !== KEY_REORDER_LATER
      ) {
        return;
      }
      // A ROW BEING RENAMED IS MID-EDIT — moving it out from under the field
      // the user is typing in is the one case where the chord has to stand
      // down. Anything else is fair game, and that is deliberate: selecting a
      // row OPENS ITS EDITOR AND FOCUSES A FIELD (measured — clicking a fillet
      // row leaves focus on `fillet-radius`), so a handler that bailed on any
      // `<input>` would be unreachable in precisely the state that arms it.
      // Alt+Arrow edits no text on any platform we target, and the chord is
      // claimed by nothing else in the workspace.
      if (renamingId !== null) return;
      const target = event.target;
      // `<select>` is the exception: Alt+Down OPENS the native picker, and
      // stealing that would break a real control to serve a shortcut.
      if (
        target instanceof HTMLElement &&
        (target.tagName === "SELECT" || target.isContentEditable)
      ) {
        return;
      }
      const from = features.findIndex((f) => f.id === selectedFeatureId);
      if (from === -1) return;
      event.preventDefault();
      attemptMove(
        from,
        from + (event.key === KEY_REORDER_EARLIER ? -1 : 1),
        true,
      );
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [canReorder, selectedFeatureId, features, renamingId, attemptMove]);

  // ESCAPE ABANDONS THE DRAG — and because the list never moved, abandoning it
  // IS restoring the original order. A drag that committed on release with no
  // way out is the "ambiguous exit" the flow rule calls a defect.
  useEffect(() => {
    if (drag === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setDrag(null);
      setRefused(null);
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [drag]);

  /**
   * Which row's band the pointer is over — the seat it would take. Nearest
   * band rather than "the gap between rows": a 26px row has no gap worth
   * aiming at, and a seat model that demands one is a seat model that misses.
   */
  const seatAt = useCallback(
    (clientY: number, fallback: number): number => {
      let best = fallback;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (const [index, feature] of features.entries()) {
        const row = rowRefs.current.get(feature.id);
        if (row === undefined) continue;
        const rect = row.getBoundingClientRect();
        if (clientY >= rect.top && clientY <= rect.bottom) return index;
        const distance =
          clientY < rect.top ? rect.top - clientY : clientY - rect.bottom;
        if (distance < bestDistance) {
          bestDistance = distance;
          best = index;
        }
      }
      return best;
    },
    [features],
  );

  const startDrag = useCallback(
    (
      event: ReactPointerEvent<HTMLButtonElement>,
      index: number,
      id: string,
    ) => {
      if (!canReorder || event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      setRefused(null);
      setDrag({ id, from: index, seat: index });
    },
    [canReorder],
  );

  const moveDrag = useCallback(
    (event: ReactPointerEvent<HTMLButtonElement>) => {
      if (drag === null) return;
      const seat = seatAt(event.clientY, drag.from);
      if (seat !== drag.seat) setDrag({ ...drag, seat });
    },
    [drag, seatAt],
  );

  const endDrag = useCallback(() => {
    if (drag === null) return;
    const { from, seat } = drag;
    setDrag(null);
    if (seat !== from) attemptMove(from, seat, false);
  }, [drag, attemptMove]);

  /** The live drop rule: what is wrong with the seat under the pointer, now. */
  const dragConflict = useMemo(
    () =>
      drag === null || drag.seat === drag.from
        ? null
        : firstOrderConflict(movedOrder(features, drag.from, drag.seat)),
    [drag, features],
  );

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
                // The open command will change THIS row (see the prop doc).
                const scoped = scopedFeatureIds?.includes(feature.id) ?? false;
                // Suppressed reads from the persisted envelope flag (authoritative
                // the instant the tree refetches, before the re-evaluate lands)
                // OR the evaluate's dedicated `suppressed` status — either marks
                // the row quiet-and-struck, distinct from a red error.
                const suppressed =
                  (feature.feature.suppressed ?? false) ||
                  status === "suppressed";
                const suppressBusy = feature.id === suppressingId;
                const renaming = feature.id === renamingId;
                // This row was never attempted — and the cause is a DIFFERENT
                // feature, so the row has to name it.
                const blockedBy =
                  status === "skipped" && !suppressed && !rolledBack
                    ? (build.failure?.id ?? null)
                    : null;
                return (
                  <FeatureRowGroup key={feature.id}>
                    {/* THE SEAT. A 2px scribe line where the dragged row would
                        land — brass when the tree will take it, flag with the
                        reason written underneath when it will not. In the flow
                        of the list, not a tooltip, so the pointer and the
                        keyboard reach the same words. */}
                    {drag !== null &&
                    drag.seat === index &&
                    drag.seat !== drag.from ? (
                      <li
                        className="pr-3 pl-[10px]"
                        data-testid="reorder-seat"
                        data-legal={dragConflict === null || undefined}
                      >
                        <span
                          className={`block h-0.5 ${
                            dragConflict === null ? "bg-brass" : "bg-flag"
                          }`}
                        />
                        {dragConflict !== null ? (
                          <span className="mt-1 block font-body text-xs text-flag">
                            {conflictMessage(dragConflict)}
                          </span>
                        ) : null}
                      </li>
                    ) : null}
                    {/* A REFUSED SEAT, held after the gesture ends. */}
                    {refused !== null && refused.seat === index ? (
                      <RefusedSeatRow
                        refused={refused}
                        features={features}
                        onRepair={() => {
                          const legal = refused.legalIndex;
                          setRefused(null);
                          if (legal !== null) {
                            attemptMove(refused.fromIndex, legal, true);
                          }
                        }}
                        onDismiss={() => setRefused(null)}
                      />
                    ) : null}
                    <li
                      ref={(node) => {
                        if (node === null) rowRefs.current.delete(feature.id);
                        else rowRefs.current.set(feature.id, node);
                      }}
                      // ONE 24px BAND, the header's own tool-row height. It was
                      // `py-1` around a `min-h-target-dense` button, i.e. a
                      // 24px control in a 35px row — 11px of slack per feature,
                      // on the panel a modeller scans most (founder,
                      // 2026-08-28). `items-center` so the ordinal chip, the
                      // name and the status badge share one centre line instead
                      // of hanging from a baseline at the top of the band.
                      className={`group/row flex min-h-target-dense items-center gap-2 border-l-2 py-0 pr-2 pl-[10px] ${
                        selected || scoped
                          ? "border-brass"
                          : "border-transparent"
                      } ${drag?.id === feature.id ? "bg-carbide" : ""}`}
                      data-testid="feature-row"
                      data-scoped={scoped || undefined}
                      data-rolled-back={rolledBack || undefined}
                      data-suppressed={suppressed || undefined}
                      data-blocked-by={blockedBy ?? undefined}
                      data-dragging={drag?.id === feature.id || undefined}
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
                      <OrdinalCell
                        index={index}
                        count={features.length}
                        name={feature.name}
                        armed={canReorder && selected && !renaming}
                        dragging={drag?.id === feature.id}
                        busy={reordering}
                        onRef={(node) => {
                          if (node === null)
                            gripRefs.current.delete(feature.id);
                          else gripRefs.current.set(feature.id, node);
                        }}
                        onPointerDown={(event) =>
                          startDrag(event, index, feature.id)
                        }
                        onPointerMove={moveDrag}
                        onPointerUp={endDrag}
                        onPointerCancel={() => setDrag(null)}
                        onNudge={(delta) =>
                          attemptMove(index, index + delta, true)
                        }
                      />
                      {renaming ? (
                        <div className="flex grow items-baseline gap-2">
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
                            {featureBadge(feature.feature, features)}
                          </span>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onSelectFeature(feature)}
                          aria-pressed={selected}
                          aria-label={`Select ${feature.name}`}
                          data-testid={`feature-select-${index}`}
                          className="flex min-h-target-dense grow items-center gap-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                        >
                          <span
                            className={`grow truncate font-data text-sm ${
                              suppressed
                                ? "text-gauge line-through decoration-etch"
                                : rolledBack
                                  ? "text-gauge"
                                  : "text-mist"
                            }`}
                          >
                            {feature.name}
                          </span>
                          {/* The SCOPE stamp — the same word the command band
                              uses for the same fact, so the two surfaces teach
                              one vocabulary rather than two. It takes the badge
                              slot rather than sitting beside it: while a
                              command holds this row, what it is ABOUT TO
                              CHANGE outranks what type it is, and a 24px row
                              has no width for both. */}
                          {scoped ? (
                            <Stamp
                              tone="brass"
                              data-testid={`feature-scoped-${index}`}
                            >
                              Scope
                            </Stamp>
                          ) : (
                            <span className="shrink-0 font-body text-xs text-gauge">
                              {featureBadge(feature.feature, features)}
                            </span>
                          )}
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
                        // Measured 18x18 before this pass — under the 24px floor
                        // this product wrote down for itself (`target.dense`,
                        // WCAG 2.2 SC 2.5.8). A density pass is the moment that
                        // gets fixed, not the moment it gets worse: the row is
                        // 24px now, so the toggle fills it rather than sitting
                        // inside a 35px row at 18px.
                        className={`flex min-h-target-dense min-w-target-dense shrink-0 items-center justify-center rounded-sm transition-colors duration-fast focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:cursor-default ${
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
                        // The badge is three glyphs; the CAUSE reaches the
                        // pointer and the screen reader (N3: a SKIP with no
                        // reason reads as "this feature is broken").
                        title={
                          blockedBy !== null && skipCause !== null
                            ? `${feature.name}: ${skipCause}`
                            : undefined
                        }
                        aria-label={
                          rolledBack
                            ? "rolled back"
                            : suppressed
                              ? "evaluation suppressed"
                              : blockedBy !== null && skipCause !== null
                                ? `evaluation skipped: ${skipCause}`
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
                    {/* The casualty list, stated ONCE where the build stopped:
                        the rows under here were never attempted, and several of
                        them may have nothing to do with the failure (N3 — the
                        datum plane and the far-corner dowel hole that vanished
                        with a bad hole pick). Each of those rows also names this
                        feature in its own status cell. */}
                    {feature.id === build.failure?.id &&
                    build.excluded.length > 0 ? (
                      <li
                        className="py-1 pr-3 pl-[26px]"
                        data-testid="feature-excluded-note"
                      >
                        <span className="block font-body text-xs text-gauge">
                          {excludedNote(build)}
                        </span>
                      </li>
                    ) : null}
                  </FeatureRowGroup>
                );
              })}
            </ol>
          )}
        </PanelSection>

        <ViewCategories tree={tree} />

        {/* Title-block footer: the one vital that MOVES — the solve state.
            FEATURES folded into the eyebrow; TREE (the internal optimistic-
            concurrency version) was decorative and is gone (Track B). */}
        {/* One ruled cell, not a stacked pair: caption and vital share a line
            exactly as every readout above them does. Stacking cost two lines
            plus `py-2` to say one short word. */}
        <div className="flex min-h-target-dense items-center gap-2 border-t border-hairline px-3 py-0.5">
          <span className="shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-gauge">
            Solve
          </span>
          <span
            className="grow text-right font-data text-sm text-mist"
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

/**
 * THE ITEM NUMBER IS THE CONTROL (the signature of this panel).
 *
 * The row number already states the one fact a reorder changes — where this
 * feature sits in the build — so it is the number that becomes draggable, not a
 * six-dot handle bolted beside it. At rest it is the quiet gauge slug the tree
 * has always drawn. On the SELECTED row it lifts into a brass index tab: a
 * ruled 24x24 cell with the number still in it, grab cursor, and a scribe tick
 * on its left edge. Nothing is added to the row; an existing readout is given
 * the job it was already describing.
 *
 * The tab is a real filled BUTTON, not a stroked glyph — a stroke has no hit
 * box (`getBoundingClientRect` ignores stroke width), and a control a pointer
 * cannot land on is not a control. 24x24 is the dense target floor
 * (WCAG 2.2 SC 2.5.8), and Up/Down on the focused tab does what the drag does,
 * so the affordance is never drag-only (SC 2.5.7).
 */
function OrdinalCell({
  index,
  count,
  name,
  armed,
  dragging = false,
  busy,
  onRef,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onNudge,
}: {
  index: number;
  count: number;
  name: string;
  /** The row is selected and the tree can be reordered — show the grip. */
  armed: boolean;
  dragging?: boolean;
  busy: boolean;
  onRef: (node: HTMLButtonElement | null) => void;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onPointerUp: () => void;
  onPointerCancel: () => void;
  onNudge: (delta: -1 | 1) => void;
}) {
  const label = String(index + 1).padStart(2, "0");
  if (!armed) {
    return (
      <span
        className="w-6 shrink-0 text-center font-data text-xs tabular-nums text-gauge"
        data-testid={`feature-ordinal-${index}`}
      >
        {label}
      </span>
    );
  }
  const onKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    if (event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    onNudge(event.key === "ArrowUp" ? -1 : 1);
  };
  return (
    <button
      ref={onRef}
      type="button"
      disabled={busy}
      data-testid={`feature-grip-${index}`}
      data-ordinal={label}
      // The name says what it moves and where it is — a bare "Reorder" leaves a
      // screen-reader user with no way to tell the move landed.
      aria-label={`Reorder ${name} — build step ${index + 1} of ${count}. Up or down arrow to move it.`}
      title={`Drag to reorder, or Alt+Up / Alt+Down (${index + 1} of ${count})`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onKeyDown={onKeyDown}
      className={`relative flex min-h-target-dense min-w-target-dense w-6 shrink-0 touch-none items-center justify-center rounded-sm border font-data text-xs tabular-nums transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:cursor-default ${
        dragging
          ? "cursor-grabbing border-brass bg-brass/20 text-brass"
          : "cursor-grab border-etch text-brass hover:border-brass hover:bg-brass/10"
      }`}
    >
      {/* The scribe tick: the drafting mark that says this cell is a rail, not
          a label. Two hairlines, no new glyph, no decoration that does nothing
          — it appears only where the grip is live. */}
      <span
        aria-hidden="true"
        className="absolute top-1 bottom-1 left-0 w-px bg-brass/60"
      />
      {label}
    </button>
  );
}

/**
 * THE REFUSAL, at the seat it was aimed at.
 *
 * It outlives the gesture on purpose: a reason that disappears with the pointer
 * cannot be read by anyone who was not watching, and a reason that lives in a
 * `title` cannot be read by the keyboard at all. So this is a focusable
 * `role="alert"` — Tab lands on it and the words are its accessible name — with
 * the one-click repair beside it when there is a seat the tree would take.
 */
function RefusedSeatRow({
  refused,
  features,
  onRepair,
  onDismiss,
}: {
  refused: RefusedSeat;
  features: readonly FeatureResponse[];
  onRepair: () => void;
  onDismiss: () => void;
}) {
  const message = conflictMessage(refused.conflict);
  return (
    <li className="border-l-2 border-flag py-1 pr-3 pl-[26px]">
      <div
        role="alert"
        tabIndex={0}
        data-testid="reorder-refusal"
        aria-label={`Order refused. ${message}`}
        className="rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
      >
        <span className="block font-display text-2xs uppercase tracking-[0.14em] text-flag">
          Order refused
        </span>
        <span className="mt-0.5 block font-body text-xs text-mist">
          {message}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {refused.legalIndex !== null ? (
          <Button
            variant="ghost"
            className="mt-1.5 py-0.5 text-xs"
            data-testid="reorder-repair"
            onClick={onRepair}
          >
            {repairLabel(features, refused.fromIndex, refused.legalIndex)}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          className="mt-1.5 py-0.5 text-xs"
          data-testid="reorder-refusal-dismiss"
          onClick={onDismiss}
        >
          Leave it here
        </Button>
      </div>
    </li>
  );
}

/**
 * One VIEW row (UI-W2, part half): the learned eye, then the thing's name.
 *
 * Two stops, not three, and that is a decision rather than an omission. GHOST
 * is "see THROUGH the solid to what is behind it" — it only means something for
 * a body. A datum plane is already translucent and a sketch is a line; a third
 * stop on those rows would be a control that changes nothing, which is exactly
 * the decorative chrome the mandate calls a defect. Bodies keep the full
 * SOLID · GHOST · HIDE control (see `BodiesPanel`).
 *
 * The glyph set, ink and hover behaviour are the assembly half's, unchanged:
 * `gauge` at rest (7.3:1 on anvil), `mist` once the row's view has been TOUCHED
 * so it is findable when scanning, `brass` on hover. The shape carries the
 * state; the ink is the second cue.
 */
function ViewRow({
  drawn,
  label,
  detail,
  testId,
  rowTestId,
  onToggle,
  onAddress,
}: {
  drawn: boolean;
  label: string;
  /** Right-hand kind badge, in the feature row's voice ("plane", "sketch"). */
  detail: string;
  /** Test hook on the EYE. Deliberately distinct from `rowTestId`: a shared
   *  prefix would make `getByTestId(/^sketch-visibility-/)` ambiguous. */
  testId: string;
  rowTestId: string;
  onToggle: () => void;
  onAddress: () => void;
}) {
  const Glyph = drawn ? EyeIcon : EyeOffIcon;
  const action = `${drawn ? "Hide" : "Show"} ${label}`;
  return (
    <li
      className="flex min-h-target-dense items-center gap-2 border-l-2 border-transparent py-0 pr-2 pl-2"
      data-testid={rowTestId}
      data-drawn={drawn || undefined}
    >
      <button
        type="button"
        onClick={() => {
          onAddress();
          onToggle();
        }}
        aria-pressed={drawn}
        aria-label={action}
        title={action}
        data-testid={testId}
        className={`flex min-h-target-dense min-w-target-dense shrink-0 items-center justify-center rounded-sm outline-none transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass ${
          drawn ? "text-mist" : "text-gauge"
        }`}
      >
        <Glyph size={16} />
      </button>
      <span
        className={`grow truncate font-data text-sm ${
          drawn ? "text-mist" : "text-gauge"
        }`}
      >
        {label}
      </span>
      <span className="shrink-0 font-body text-xs text-gauge">{detail}</span>
    </li>
  );
}

/**
 * One cell of the ORIGIN datum table — the eye and the entity's short name, in
 * a ruled square. It is `ViewRow`'s control in a grid cell rather than a row:
 * the origin set is FIXED and its names are two characters, so a full-width row
 * per entity was spending a panel's height on a label that fits in a corner.
 *
 * Ink, glyphs and hover behaviour are `ViewRow`'s, unchanged (`gauge` at rest,
 * `mist` once drawn, `brass` on hover) — the shape carries the state, the ink is
 * the second cue. The accessible name states the KIND ("Show XY plane"), which
 * is the one thing the compaction drops from the screen.
 */
function OriginCell({
  drawn,
  label,
  kind,
  testId,
  onToggle,
  onAddress,
}: {
  drawn: boolean;
  /** The stamped short name — "XY" for a plane, "X" for an axis. */
  label: string;
  kind: "plane" | "axis";
  testId: string;
  onToggle: () => void;
  onAddress: () => void;
}) {
  const Glyph = drawn ? EyeIcon : EyeOffIcon;
  const action = `${drawn ? "Hide" : "Show"} ${label} ${kind}`;
  return (
    <li className="bg-anvil">
      <button
        type="button"
        onClick={() => {
          onAddress();
          onToggle();
        }}
        aria-pressed={drawn}
        aria-label={action}
        title={action}
        data-testid={testId}
        data-drawn={drawn || undefined}
        className={`flex min-h-target-dense w-full items-center justify-center gap-1.5 outline-none transition-colors duration-fast hover:bg-carbide hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass ${
          drawn ? "text-mist" : "text-gauge"
        }`}
      >
        <Glyph size={14} />
        <span className="font-data text-xs">{label}</span>
      </button>
    </li>
  );
}

/**
 * ORIGIN and SKETCHES — the two categories a Fusion user reaches for that this
 * browser had no row for (founder: *"what about the ability to enable planes,
 * sketches and bodies?"*). Bodies is the third, and lives in `BodiesPanel`
 * beside its solids.
 *
 * Origin sits LAST because it is the least-touched and defaults off; the build
 * order stays at the top of the panel where a modeler's eye already goes.
 */
function ViewCategories({ tree }: { tree: FeatureTreeResponse | undefined }) {
  const view = usePartViewStore((state) => state.view);
  const bodyPresent = usePartViewStore((state) => state.bodyPresent);
  const toggle = usePartViewStore((state) => state.toggle);
  const setAddressed = usePartViewStore((state) => state.setAddressed);
  const setSubject = usePartViewStore((state) => state.setSubject);
  const partId = tree?.part_id ?? null;
  // Registering the subject both scopes the view state to THIS part (opening
  // another one resets it, so a hidden body can never follow you across
  // documents) and arms the `V` / `⇧V` accelerators, which stay disarmed in the
  // assembly workspace because it never mounts this browser.
  useEffect(() => {
    if (partId !== null) setSubject(partId);
  }, [partId, setSubject]);

  const sketches = (tree?.features ?? []).filter(
    (feature) => feature.feature.type === "sketch" && !feature.rolled_back,
  );

  return (
    <>
      {sketches.length > 0 ? (
        <PanelSection
          eyebrow={`Sketches · ${sketches.length}`}
          data-testid="sketches-section"
        >
          <ul className="pb-1" data-testid="sketch-view-list">
            {sketches.map((feature) => (
              <ViewRow
                key={feature.id}
                drawn={sketchIsDrawn(view, feature.id, bodyPresent)}
                label={feature.name}
                detail="sketch"
                testId={`sketch-visibility-${feature.id}`}
                rowTestId={`sketch-row-${feature.id}`}
                onToggle={() => toggle(sketchKey(feature.id))}
                // Addresses, and does NOT select. Selecting a sketch feature
                // warms the whole body brass (the tree→geometry link), so an
                // eye that also selected would make "show me this profile"
                // light up the solid instead — one element, one job. The tree
                // rows above are where a feature gets selected.
                onAddress={() => setAddressed(sketchKey(feature.id))}
              />
            ))}
          </ul>
        </PanelSection>
      ) : null}

      <PanelSection eyebrow="Origin" data-testid="origin-section">
        {/*
          THE DATUM TABLE (FB-19). Six fixed entities spent six full-width rows
          — a 212px block of a panel that floats over the model, to say "XY, XZ,
          YZ, X, Y, Z", which every one of our users already knows. Measured
          after: 95px, and at 1280x800 with an editor open the six toggles went
          from OFF the bottom of the frame (`elementFromPoint` found none of
          them) to reachable. A drawing stamps a fixed set like this as a small
          ruled schedule, so this is a 3x2 one:
          planes on the top course, axes under them, hairline-ruled cells inside
          one frame. The structure carries the kind — two letters is a plane,
          one is an axis — and each cell's accessible name says it in words
          ("Show XY plane"), so nothing is lost by dropping the detail badge the
          rows carried.

          Same cells, same test hooks, same targets: every cell is a 24px
          `target.dense` toggle (WCAG 2.2 SC 2.5.8), which is what the 6 rows
          were, laid out in two courses instead of six.
        */}
        <ul
          className="mx-3 mb-1 grid grid-cols-3 gap-px border border-hairline bg-hairline"
          data-testid="origin-list"
        >
          {ORIGIN_PLANES.map((plane) => (
            <OriginCell
              key={plane}
              drawn={entityIsDrawn(view, originPlaneKey(plane))}
              label={plane}
              kind="plane"
              testId={`origin-plane-${plane}`}
              onToggle={() => toggle(originPlaneKey(plane))}
              onAddress={() => setAddressed(originPlaneKey(plane))}
            />
          ))}
          {ORIGIN_AXES.map((axis) => (
            <OriginCell
              key={axis}
              drawn={entityIsDrawn(view, originAxisKey(axis))}
              label={axis}
              kind="axis"
              testId={`origin-axis-${axis}`}
              onToggle={() => toggle(originAxisKey(axis))}
              onAddress={() => setAddressed(originAxisKey(axis))}
            />
          ))}
        </ul>
      </PanelSection>
    </>
  );
}
