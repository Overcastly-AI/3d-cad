/**
 * THE ASK QUEUE, WIRED TO REACT — the state half of every gauge.
 *
 * The RULES are pure and live in `@loft/design`'s `gauge.ts` (`seedAsks`,
 * `recordAsk`, `acknowledgeAsk`, `holdAsks`, `releaseAsks`, with their own
 * unit cases). What is here is the part that cannot be pure: a ref the next
 * input can read before a render has happened, a state cell so the instrument
 * redraws, and the one effect that reacts to THE OWNER SPEAKING.
 *
 * ## Why the split is drawn here and not somewhere tidier
 *
 * This mechanism was written after a load-dependent lost update, so its
 * correctness is invisible to a normal run: everything it does matters only
 * when two inputs collide inside one round trip. For most of its life the only
 * thing standing behind it was one Playwright case, and that case catches a
 * queue-clearing mutant **2 runs in 12** — green is the mutant's modal outcome.
 * Splitting the rules out made them checkable every run; splitting the WIRING
 * out makes the React semantics checkable too, in jsdom, which matters because
 * the subtlest line in the whole thing is a dependency array (below).
 *
 * ## `value` IS THE ONLY DEPENDENCY OF THE ACKNOWLEDGEMENT EFFECT
 *
 * `same`, `authoring` and `onChange` are read through a latest-value ref rather
 * than listed as dependencies, and that is deliberate rather than lazy. A
 * `GaugeTrack` closes over its seat, so an owner that builds one inline hands
 * us a new identity on every render; listing it would re-run the reconciliation
 * between a key press and its acknowledgement, find no match for an ask the
 * owner has not echoed yet, read that as a stranger's edit and clear the
 * queue — which is the lost update this whole mechanism exists to prevent,
 * restored by a dependency array. What this effect reacts to is the owner
 * SPEAKING, and that is exactly one thing.
 *
 * The ref is written during render, which is safe because the write is
 * idempotent and derives from nothing but this render's own arguments — and
 * because the effect that reads it runs after the commit of the render that
 * changed `value`, i.e. it sees exactly what the closure would have seen.
 *
 * ## LETTING GO IS NOT AN ANSWER (CRAFT-13 follow-up, measured 2026-09-16)
 *
 * `shown` is `live ?? value`, and `release` used to drop `live` outright — so
 * the instant the pointer came up, the gauge asserted the owner's LAST ECHO.
 * That echo is structurally behind: the drag's final ask reaches the panel
 * field in one commit and the gauge's own `value` prop only after the owner has
 * re-derived it (override -> editor form -> parse -> page state -> prop). In
 * between, the gauge drew a number the user had already dragged past, while the
 * panel beside it drew the right one — two dialects of one value on screen at
 * once, which is worse than either being slow.
 *
 * Measured in a real browser at 1280x800, sampling the DRAWN rod (`scale.y` off
 * the scene graph) and the panel input on every animation frame, against the
 * r3f render clock:
 *
 * | gauge          | panel settles | rod shows the OLD value | rod settles |
 * | -------------- | ------------- | ----------------------- | ----------- |
 * | shell thickness| +8.7 ms       | +109.6 .. +350.7 ms      | +350.7 ms   |
 * | extrude depth  | +4.9 ms       | +15.2 .. +251.0 ms       | +251.0 ms   |
 *
 * i.e. the rod REVERTED a step after release and held the wrong number for
 * 236-241 ms. The wall figure is machine- and build-dependent (each of those
 * commits cost 50-115 ms here); the machine-independent statement is that the
 * rod was TWO RENDERS stale, and no amount of faster rendering makes zero out
 * of two.
 *
 * So a release no longer abandons the ask. The final value stays OUTSTANDING
 * and `acknowledgeAsk` retires it when the owner echoes — or overrides it when
 * the owner answers with something else, which is the case that keeps the owner
 * sovereign: a clamp, a snap or a refusal still wins, it simply has to WIN BY
 * SPEAKING rather than by the gauge reading silence as disagreement.
 *
 * ## ...AND A LATE ANSWER IS NOT AN OVERRIDE (measured 2026-09-23)
 *
 * Holding only the FINAL ask left one failure on the table, on 3 of 12 runs of
 * `gauge-release-sync.spec.ts`: the owner's pipeline is two renders deep and a
 * drag outruns it, so the answer to the drag's PREVIOUS ask routinely lands
 * after the release — `ask 25 · ask 26 · release · prop 25 · prop 26`. With 26
 * the only thing outstanding, `prop 25` matched nothing, rule 3 read it as the
 * owner overriding the release, and the rod stepped back to 25 beside a field
 * of 26 until `prop 26` landed. The drag's asks are now queued like any other
 * (`recordAsk`), the owner's answers retire them mid-drag without moving what
 * is drawn (`acknowledgeAsk(…, authoring)`), and a late answer is recognised as
 * the answer to a superseded ask by its place in the queue. See `gauge.ts`,
 * "A drag's asks are asks", for what a value-only echo still cannot tell apart.
 *
 * The cost of the change, stated because it is real: a mount whose echo is
 * never wired no longer springs back, so it no longer advertises its own
 * missing wiring. That contract is asserted where it belongs instead —
 * `useGaugeOverride`'s cases and the per-verb e2e contract-β cases, which check
 * the FIELD and the ROD, not the rod alone.
 *
 * ## The actions object is referentially STABLE
 *
 * Same shape and same reason as `useGaugeOverride`: `[shown, actions]`, the
 * `useState` split, so a handler that depends on the actions is not rebuilt on
 * every frame of a drag. A gauge's pointer handlers go onto a portalled DOM
 * grip, and its ladder callback sits in a `useCallback` chain — churn there
 * costs the same ordering instability the override hook was fixed for.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  acknowledgeAsk,
  holdAsks,
  recordAsk,
  releaseAsks,
  seedAsks,
  type AskQueue,
} from "@loft/design";

export interface UseAskQueueOptions {
  /** The owner's value — the prop the gauge never owns. */
  value: number;
  /** The track's own tolerance for "the same value came back". */
  same: (a: number, b: number) => boolean;
  /** Ask the owner. Called by {@link AskQueueActions.ask} AFTER recording. */
  onChange: (next: number) => void;
  /**
   * True while the POINTER is authoring. The caller owns this flag (it also
   * holds the grab record), so there is one source of truth for "is a drag in
   * progress" rather than two that can disagree.
   */
  authoring: () => boolean;
}

export interface AskQueueActions {
  /**
   * The value the next input reasons from: the last ASK, not the last prop.
   * Synchronous and ref-backed, because a key press must be able to step off a
   * press that has not been acknowledged yet.
   */
  readBase: () => number;
  /** Ask the owner for a value — the ONE place a new value leaves a gauge. */
  ask: (next: number) => void;
  /** The grip has been taken: show `base` rather than the prop. */
  hold: () => void;
  /**
   * The pointer is done authoring. What the drag asked and the owner has not
   * answered stays outstanding, and the newest of it is drawn — see
   * {@link useAskQueue}'s note on why letting go is not an answer.
   */
  release: () => void;
}

/**
 * @returns `[shown, actions]` — `shown` is `live ?? value`, what the instrument
 *   draws, tags and announces; `actions` never changes identity.
 */
export function useAskQueue({
  value,
  same,
  onChange,
  authoring,
}: UseAskQueueOptions): readonly [number, AskQueueActions] {
  const queueRef = useRef<AskQueue>(seedAsks(value));
  const [live, setLive] = useState<number | null>(null);

  // See the module note: read by the effect and the actions, NOT depended on.
  const latest = useRef({ same, onChange, authoring });
  latest.current = { same, onChange, authoring };

  /** Commit a transition: the ref for the next input, the state for the draw. */
  const apply = useCallback((next: AskQueue) => {
    queueRef.current = next;
    setLive(next.live);
  }, []);

  const actions = useMemo<AskQueueActions>(
    () => ({
      readBase: () => queueRef.current.base,
      ask: (next: number) => {
        // The ask is RECORDED BEFORE IT IS SENT, so the next input reasons from
        // it even if no render has happened in between.
        apply(recordAsk(queueRef.current, next));
        latest.current.onChange(next);
      },
      hold: () => apply(holdAsks(queueRef.current)),
      // LETTING GO IS NOT AN ANSWER — see the module note. The drag's asks were
      // queued like any other, so whatever the owner has not answered yet stays
      // outstanding and the newest of it is what the instrument keeps drawing.
      release: () => {
        apply(releaseAsks(queueRef.current));
      },
    }),
    [apply],
  );

  useEffect(() => {
    // Mid-drag the pointer is still the author: the owner's answers retire the
    // asks they answer (so the queue holds only what is in flight) without
    // moving what is drawn — see `acknowledgeAsk`.
    apply(
      acknowledgeAsk(
        queueRef.current,
        value,
        latest.current.same,
        latest.current.authoring(),
      ),
    );
    // `apply` is stable, so this is a `[value]`-only effect. That is the point;
    // read the module note before adding to this array.
  }, [value, apply]);

  return [live ?? value, actions];
}
