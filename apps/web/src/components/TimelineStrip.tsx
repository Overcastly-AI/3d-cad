/**
 * THE TIMELINE — a machine way with a travel stop, docked along the bottom of
 * the frame (founder-directed 2026-07-30: "should the timeline be at the bottom
 * with the ability to drag the slider to revert?"; design in
 * `docs/design/ui-wave-tool-grade.md` Surface 1).
 *
 * It replaces the 1px dashed rule that used to hide inside the feature-tree
 * panel. A 1px line is not a scrub control, and a vertical list buries the one
 * thing about a feature tree that genuinely IS sequential: feature N is
 * evaluated against N−1's body, so the order is causal and the honest axis is
 * horizontal.
 *
 * The metaphor is a description, not decoration: features are op stations along
 * a ruled way, and the rollback marker is the TRAVEL STOP that bounds how far
 * the tool runs — which is literally what `rollback_feature_id` does.
 *
 * Encoding (all of it load-bearing, mandate 3c — nothing here is ornament):
 *  · way line SOLID through travelled ops, DASHED past the stop, with the seam
 *    exactly under the stop (dashed = "not present" is drafting convention and
 *    already this product's language in the drawings' hidden-line render);
 *  · chips past the stop take a dashed outline AND dim. For the dash to be a
 *    real second cue it has to be VISIBLE: the chip border is `etch` (3.06:1 on
 *    its carbide seat), not `hairline` — measured at 1.54:1, which is below the
 *    non-text floor and made this file's redundancy claim false while it made
 *    it (UI-REVIEW 2026-07-30 P2-A). The way's own dash already used `etch`;
 *    the chip now matches it;
 *  · the travel stop is the ONLY brass in the strip — it is the one position
 *    indicator, so it gets the accent and nothing else does. A SELECTED chip is
 *    therefore marked by the strip's brightest EDGE (`mist`, 4.31:1 against the
 *    `etch` its neighbours wear). The seat also lifts to `hairline`, but that
 *    step is 1.41:1 and is a NUANCE, not a cue — the border carries the state
 *    on its own, and this comment used to claim a redundancy it did not have
 *    (P2-B);
 *  · an errored feature takes `flag`, a suppressed one the tree's own struck-
 *    through treatment — same vocabulary, new axis;
 *  · every slot on the way is clickable (it keeps the `rollback-slot-N` hooks),
 *    the stop is draggable AND keyboard-operable, and `TO TIP` is the escape
 *    hatch back to "everything included".
 *
 * The slot math is shared with nothing to translate: `features/rollback.ts` was
 * written for the vertical bar and ported to this axis unchanged.
 */
import { BandActionCell, cx, layout, Stamp, VerbGlyph } from "@loft/design";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";

import type {
  EvaluateTreeResult,
  FeatureResponse,
  FeatureResult,
  FeatureTreeResponse,
} from "../api/parts";
import { featureTypeLabel } from "../features/featureLabels";
import { usePrefetchIntent } from "../features/prefetch";
import {
  barSlotIndex,
  nearestSlotIndex,
  rollbackIdForSlot,
} from "../features/rollback";
import { useReducedMotion } from "../lib/useReducedMotion";

export interface TimelineStripProps {
  /** The feature tree; `undefined` while it loads (the strip keeps its frame). */
  tree: FeatureTreeResponse | undefined;
  /** Per-feature evaluate results — the source of the error/suppressed chips. */
  evaluation: EvaluateTreeResult | undefined;
  /** Selected feature id (the addressed chip); clicking a chip selects it. */
  selectedFeatureId: string | null;
  /**
   * The feature ids the OPEN command will act on (the pattern/mirror scope).
   * The strip carries this as well as the tree because the tree panel COLLAPSES
   * and the strip does not — a subject mark that disappears with the panel is a
   * mark the user cannot rely on (REACH-2-FLOW P1-2).
   */
  scopedFeatureIds?: readonly string[];
  onSelectFeature: (feature: FeatureResponse) => void;
  /** Move the travel stop (null = tip); the workspace re-evaluates. */
  onMoveRollback: (rollbackFeatureId: string | null) => void;
  /** A tree write is in flight — the stop holds until it settles. */
  busy: boolean;
  /** Right-click a chip: open the same row menu the tree offers. */
  onChipContextMenu?: (feature: FeatureResponse, x: number, y: number) => void;
}

/** Build-order ordinal, zero-padded — the tabular `01 / 02` of the title block. */
function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** One half-segment of the way: solid where travelled, dashed where it is not. */
function halfWay(travelled: boolean): string {
  return travelled
    ? "h-px grow bg-etch"
    : "h-0 grow border-t border-dashed border-etch";
}

export function TimelineStrip({
  tree,
  evaluation,
  selectedFeatureId,
  scopedFeatureIds,
  onSelectFeature,
  onMoveRollback,
  busy,
  onChipContextMenu,
}: TimelineStripProps) {
  const features = tree?.features ?? [];
  const count = features.length;
  const committedSlot = barSlotIndex(
    features,
    tree?.rollback_feature_id ?? null,
  );

  // The stop the USER is holding — a drag in progress, or a committed move whose
  // write hasn't landed yet. Mirrored in a ref so the pointer-up handler can read
  // it without a side effect inside a state updater (which StrictMode would run
  // twice, i.e. two rollback writes).
  const [pendingSlot, setPendingSlot] = useState<number | null>(null);
  const pendingRef = useRef<number | null>(null);
  const setPending = useCallback((value: number | null) => {
    pendingRef.current = value;
    setPendingSlot(value);
  }, []);

  const [dragging, setDragging] = useState(false);
  const dragAnchors = useRef<readonly number[] | null>(null);
  const stopRef = useRef<HTMLButtonElement | null>(null);
  const slotRefs = useRef<(HTMLDivElement | null)[]>([]);
  const refocusStop = useRef(false);
  const wasBusy = useRef(busy);
  const reducedMotion = useReducedMotion();

  const slot = pendingSlot ?? committedSlot;
  const atTip = slot >= count - 1;

  // TRIGGER 2 (docs/PERF.md PERF-1b): warm the stop the user is heading for.
  //
  // Only BACKWARD travel is worth speculating on, and the asymmetry is the
  // rebuild cache's own shape rather than a guess: rolling FORWARD appends
  // features to a tree the worker already holds a checkpoint for, so it costs
  // one feature; rolling BACK asks for a shorter tree, which is a different
  // content hash and pays the whole rebuild. Hence `< committedSlot`.
  //
  // Mid-drag the target is the stop being held (the likely drop point); at rest
  // it is the stop one step back — the neighbour, which is where a scrub goes
  // next. Both are held off while a move is in flight, so speculation never
  // races the real rebuild that move just triggered.
  const travelTarget = dragging ? slot : committedSlot - 1;
  usePrefetchIntent(
    !busy && travelTarget >= 0 && travelTarget < committedSlot
      ? {
          partId: tree?.part_id ?? "",
          featureId: features[travelTarget]?.id ?? "",
          kind: "travel_stop",
        }
      : null,
    { enabled: tree !== undefined && features[travelTarget] !== undefined },
  );

  // Release the optimistic stop when the write SETTLES — not when the server
  // agrees. A rejected move must snap the stop back to the truth rather than
  // leave the strip claiming a rollback that never happened.
  useEffect(() => {
    if (wasBusy.current && !busy) {
      pendingRef.current = null;
      setPendingSlot(null);
    }
    wasBusy.current = busy;
  }, [busy]);

  // Keyboard travel moves the stop into a different slot, which remounts the
  // button — hand focus back so the next arrow press still lands on it.
  useEffect(() => {
    if (!refocusStop.current) return;
    refocusStop.current = false;
    stopRef.current?.focus();
  }, [slot]);

  // A long build scrolls the way; keep the stop reachable after a committed move
  // (and after mount, which lands the view on the tip where work happens).
  useEffect(() => {
    const element = stopRef.current;
    if (element === null || typeof element.scrollIntoView !== "function")
      return;
    element.scrollIntoView({
      block: "nearest",
      inline: "center",
      behavior: reducedMotion ? "auto" : "smooth",
    });
  }, [committedSlot, reducedMotion]);

  /** Move the stop to `next` (clamped) and write it through. */
  const travel = useCallback(
    (next: number) => {
      if (busy || count === 0) return;
      const target = Math.min(Math.max(next, 0), count - 1);
      if (target === committedSlot) {
        setPending(null);
        return;
      }
      setPending(target);
      onMoveRollback(rollbackIdForSlot(features, target));
    },
    [busy, count, committedSlot, features, onMoveRollback, setPending],
  );

  // Drag: listeners go on the WINDOW rather than the stop, because moving the
  // stop remounts it (it lives in the slot it occupies) and pointer capture on a
  // node that unmounts mid-gesture drops the rest of the drag.
  useEffect(() => {
    if (!dragging) return;
    const move = (event: PointerEvent) => {
      const anchors = dragAnchors.current;
      if (anchors === null) return;
      const next = nearestSlotIndex(anchors, event.clientX);
      if (next >= 0) setPending(next);
    };
    const end = () => {
      setDragging(false);
      dragAnchors.current = null;
      const landed = pendingRef.current;
      if (landed !== null && landed !== committedSlot) {
        onMoveRollback(rollbackIdForSlot(features, landed));
      } else {
        setPending(null);
      }
    };
    // Escape ABORTS the drag — the stop snaps back to where the build actually
    // is and nothing is written. A scrub gesture that can only be committed is
    // a gesture you cannot explore with (UI-REVIEW P3).
    const abort = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setDragging(false);
      dragAnchors.current = null;
      setPending(null);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    window.addEventListener("keydown", abort);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      window.removeEventListener("keydown", abort);
    };
  }, [dragging, committedSlot, features, onMoveRollback, setPending]);

  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (busy || event.button !== 0) return;
    // Anchor every slot ONCE, at grab time: the stop is absolutely positioned,
    // so nothing on the way reflows while it travels and the rects stay true.
    dragAnchors.current = Array.from({ length: count }, (_, index) => {
      const rect = slotRefs.current[index]?.getBoundingClientRect();
      // No rect (never laid out) → NaN, which `nearestSlotIndex` can never pick.
      return rect === undefined ? Number.NaN : rect.left + rect.width / 2;
    });
    setDragging(true);
  };

  const onStopKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step =
      event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
    if (step !== 0) {
      event.preventDefault();
      refocusStop.current = true;
      travel(slot + step);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      refocusStop.current = true;
      travel(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      refocusStop.current = true;
      travel(count - 1);
      return;
    }
    // A slider does not activate — swallow Space so it can't scroll the page.
    if (event.key === " ") event.preventDefault();
  };

  const resultById = new Map<string, FeatureResult>(
    (evaluation?.features ?? []).map((f) => [f.feature_id, f]),
  );

  // The caption is the cell's REASON while it is gated, so it has to name the
  // gate that is actually holding — an in-flight move said "Include all", which
  // describes what the cell would do if you could press it (UI-REVIEW P2-D).
  const toTipCaption = busy
    ? "Moving the stop…"
    : tree === undefined
      ? "Loading the tree"
      : count === 0
        ? "Nothing built yet"
        : atTip
          ? "Already at the tip"
          : "Include all";

  return (
    <section
      aria-label="Timeline"
      data-testid="timeline-strip"
      data-busy={busy || undefined}
      aria-busy={busy || undefined}
      className="flex h-timeline shrink-0 items-stretch border-t border-hairline bg-anvil"
    >
      {/* Head cell — the title block laid on its side: what this instrument is,
          and the one number that MOVES (how much of the build is included). */}
      <div className="flex shrink-0 flex-col justify-center gap-0.5 border-r border-hairline px-3">
        <span className="font-display text-2xs uppercase leading-none tracking-[0.18em] text-gauge">
          Timeline
        </span>
        <span
          className="font-data text-xs leading-none tabular-nums text-mist"
          data-testid="timeline-position"
        >
          {count === 0 ? "—" : `${pad(slot + 1)}/${pad(count)}`}
        </span>
      </div>

      <div
        role="group"
        aria-label="Build order"
        data-testid="timeline-way"
        className="flex grow items-center overflow-x-auto px-2"
      >
        {tree === undefined ? (
          <span className="px-1 font-body text-xs text-gauge">Loading…</span>
        ) : count === 0 ? (
          <span
            data-testid="timeline-empty"
            className="px-1 font-body text-xs text-gauge"
          >
            No features yet — start with a sketch.
          </span>
        ) : (
          features.map((feature, index) => {
            const status = resultById.get(feature.id)?.status;
            const rolledBack = index > slot;
            const suppressed =
              (feature.feature.suppressed ?? false) || status === "suppressed";
            const errored = status === "error" && !rolledBack;
            const selected = feature.id === selectedFeatureId;
            const scoped = scopedFeatureIds?.includes(feature.id) ?? false;
            const active = index === slot;
            const name = feature.name;
            const state = rolledBack
              ? ", not built — past the travel stop"
              : errored
                ? ", failed to build"
                : suppressed
                  ? ", suppressed"
                  : "";
            return (
              <Fragment key={feature.id}>
                <button
                  type="button"
                  data-testid={`timeline-chip-${index}`}
                  data-scoped={scoped || undefined}
                  data-rolled-back={rolledBack || undefined}
                  data-suppressed={suppressed || undefined}
                  data-status={status ?? undefined}
                  aria-pressed={selected}
                  aria-label={`${name} — ${featureTypeLabel(
                    feature.feature.type,
                  )}, step ${index + 1} of ${count}${state}${
                    scoped ? ", in scope for the open command" : ""
                  }`}
                  // Chip names truncate at 7.5rem; the pointer gets the full
                  // one back (the screen reader already had it, above).
                  title={name}
                  onClick={() => onSelectFeature(feature)}
                  onContextMenu={
                    onChipContextMenu
                      ? (event) => {
                          event.preventDefault();
                          onChipContextMenu(
                            feature,
                            event.clientX,
                            event.clientY,
                          );
                        }
                      : undefined
                  }
                  className={cx(
                    "flex min-h-target shrink-0 items-center gap-1.5 rounded-sm border px-2",
                    "motion-safe:transition-colors motion-safe:duration-fast",
                    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass",
                    rolledBack ? "border-dashed" : "border-solid",
                    selected ? "bg-hairline" : "bg-carbide",
                    errored
                      ? "border-flag"
                      : selected
                        ? "border-mist"
                        : // Three distinct steps so hover can never be mistaken
                          // for selection: etch (rest) < gauge (hover) < mist
                          // (selected).
                          "border-etch hover:border-gauge",
                  )}
                >
                  <VerbGlyph
                    verb={feature.feature.type}
                    size={14}
                    className={cx(
                      "shrink-0",
                      errored
                        ? "text-flag"
                        : rolledBack || suppressed
                          ? "text-gauge"
                          : "text-mist",
                    )}
                  />
                  <span className="font-data text-2xs leading-none tabular-nums text-gauge">
                    {pad(index + 1)}
                  </span>
                  <span
                    className={cx(
                      "max-w-[7.5rem] truncate font-body text-xs leading-none",
                      suppressed && "line-through decoration-etch",
                      rolledBack || suppressed ? "text-gauge" : "text-mist",
                    )}
                  >
                    {name}
                  </span>
                  {/* The SCOPE stamp — the same `Stamp tone="brass"` the tree
                      row wears for the same fact, so one mark means one thing
                      across both surfaces. It does NOT break the strip's
                      "brass is the travel stop alone" rule the way a brass
                      CHIP would: the stop owns the accent among POSITION
                      indicators, and this is not one — it is transient, it
                      exists only while a command is open, and it is a word
                      rather than a mark on the way. */}
                  {scoped ? (
                    <Stamp
                      tone="brass"
                      data-testid={`timeline-scoped-${index}`}
                    >
                      Scope
                    </Stamp>
                  ) : null}
                </button>

                {/* The way between this op and the next — and the slot the stop
                    lands in. The two half-segments put the solid/dashed seam
                    exactly under the stop. */}
                <div
                  ref={(element) => {
                    slotRefs.current[index] = element;
                  }}
                  className="relative flex w-6 shrink-0 self-stretch items-center"
                >
                  <span aria-hidden className={halfWay(index <= slot)} />
                  <span aria-hidden className={halfWay(index < slot)} />
                  {/* A drop slot is gated by `aria-disabled`, never the native
                      attribute: a natively-disabled control leaves the a11y
                      tree and stops hovering, so "why can't I move the stop?"
                      has nowhere to appear — the exact trap removed from
                      `PanelActionCell` on 2026-07-30 and re-introduced here
                      (UI-REVIEW P2-D). It is inert on activation instead. */}
                  <button
                    type="button"
                    aria-disabled={busy || active || undefined}
                    data-testid={`rollback-slot-${index}`}
                    data-active={active || undefined}
                    aria-label={
                      busy
                        ? "Moving the travel stop — one move at a time"
                        : index >= count - 1
                          ? "Roll forward to the tip (include all features)"
                          : `Roll back to after ${name}`
                    }
                    onClick={() => {
                      if (busy || active) return;
                      travel(index);
                    }}
                    className={cx(
                      "absolute inset-0 rounded-none",
                      "motion-safe:transition-colors motion-safe:duration-fast",
                      "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
                      busy
                        ? "cursor-progress"
                        : active
                          ? "cursor-default"
                          : "hover:bg-brass/10",
                    )}
                  />
                  {active ? (
                    <button
                      ref={stopRef}
                      type="button"
                      role="slider"
                      aria-label="Travel stop"
                      aria-orientation="horizontal"
                      aria-valuemin={1}
                      aria-valuemax={count}
                      aria-valuenow={slot + 1}
                      aria-valuetext={
                        atTip
                          ? `Tip — all ${count} features built`
                          : `After ${name} — ${slot + 1} of ${count} built`
                      }
                      aria-disabled={busy || undefined}
                      data-testid="timeline-stop"
                      data-dragging={dragging || undefined}
                      onPointerDown={startDrag}
                      onKeyDown={onStopKeyDown}
                      title={busy ? "Moving the travel stop…" : undefined}
                      className={cx(
                        "absolute inset-y-0 left-1/2 z-10 w-6 -translate-x-1/2",
                        "touch-none text-brass",
                        "motion-safe:transition-colors motion-safe:duration-fast",
                        // A gated stop must LOOK gated: while the move is in
                        // flight it keeps `aria-disabled` AND drops the grab
                        // cursor and the hover response, instead of inviting a
                        // drag it will silently swallow (UI-REVIEW P2-D).
                        busy
                          ? "cursor-progress opacity-60"
                          : "cursor-ew-resize hover:text-brass-hover",
                        // The focus ring is MIST, not the house brass: the
                        // focused control is itself brass, and a brass ring on
                        // a brass blade is not a visible indicator (WCAG 2.4.7).
                        // Drawn INSIDE the blade (`-outline-offset-2`): an
                        // outset ring is clipped by the way's own scroll box
                        // and by the frame edge, which rendered it as two loose
                        // vertical bars (UI-REVIEW P3).
                        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-mist",
                      )}
                    >
                      {/* The stop itself: a blade spanning both rails, wedged
                          against each — the one element in the strip that
                          touches top and bottom, because that is what a travel
                          stop does. Sized from the strip's own token so the
                          wedges always seat on the rails. */}
                      <svg
                        aria-hidden
                        focusable="false"
                        width={24}
                        height={layout.timelineHeight}
                        viewBox={`0 0 24 ${layout.timelineHeight}`}
                        className="pointer-events-none absolute inset-0"
                      >
                        <rect
                          x={11}
                          y={0}
                          width={2}
                          height={layout.timelineHeight}
                          fill="currentColor"
                        />
                        <polygon points="5,0 19,0 12,7" fill="currentColor" />
                        <polygon
                          points={`5,${layout.timelineHeight} 19,${layout.timelineHeight} 12,${layout.timelineHeight - 7}`}
                          fill="currentColor"
                        />
                        {/* The grip: a knurled thumb on the blade. It is the
                            "you may grab this" cue — without it the stop reads
                            as a mark rather than a control. */}
                        <rect
                          x={7}
                          y={layout.timelineHeight / 2 - 7}
                          width={10}
                          height={14}
                          rx={1}
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={1.5}
                        />
                      </svg>
                    </button>
                  ) : null}
                </div>
              </Fragment>
            );
          })
        )}
      </div>

      <div className="flex shrink-0 items-stretch border-l border-hairline">
        <BandActionCell
          label="To tip"
          caption={toTipCaption}
          data-testid="timeline-to-tip"
          aria-label="Roll forward to the tip (include all features)"
          disabled={busy || count === 0 || atTip}
          onClick={() => travel(count - 1)}
        />
      </div>
    </section>
  );
}
