/**
 * THE GAUGE OVERRIDE — the channel a viewport manipulator uses to move a value
 * an editor in the rail owns (CRAFT-8, direction §7.2).
 *
 * ## The contract, in one sentence each, because both halves look finished
 * ## alone and the product is broken unless both are there
 *
 * A gauge renders `shown = live ?? value`, where `live` is its own last ask, and
 * it clears `live` when the drag ends. So:
 *
 *  · **If the editor takes the gauge's `onChange` but the gauge's `value` prop
 *    is not fed from the editor's ECHOED state, the arrow springs back to its
 *    starting length the instant you let go — while the rail field shows the
 *    number you dragged to.** The drag is smooth and correct for its entire
 *    duration; the defect fires on `pointerup`, which is after every screenshot
 *    anyone would take.
 *
 *  · **If closing the editor does not clear the override, the next open of that
 *    command seeds from the last drag instead of its default.** Equally quiet,
 *    and it corrupts a value the user never touched this time round.
 *
 * This hook exists so the second one cannot be forgotten: `reset` is returned
 * beside the setter and `PartPage`'s `closeEditor` calls it, so a later verb
 * adds ONE call here and ONE line in `closeEditor` rather than remembering an
 * invariant that has no test until somebody notices the wrong default.
 *
 * ## Why the value is boxed
 *
 * `{ mm: number } | null`, not `number | null`. Dragging back to a value you
 * already had must still reach the editor, and a bare number would compare
 * equal and be dropped by React's bail-out: the identity changes even when the
 * number does not. That is not a micro-optimisation dodge — it is the
 * difference between "drag out to 20 and back to 10" leaving the editor at 10
 * and leaving it at whatever it was before the gesture.
 *
 * The field is `mm` because every override in the product so far is a canonical
 * length. An angular gauge boxes its degrees the same way; see
 * {@link GaugeOverride}.
 */
import { useCallback, useMemo, useState } from "react";

/**
 * One override, boxed so a repeat of the same number is still a new ask.
 *
 * `mm` for a length in canonical millimetres, `deg` for an angle, `n` for a
 * count — ONE of them, named for what it is, because an editor that reads
 * `value` off an untyped box cannot be caught misreading degrees as
 * millimetres by anything but a founder.
 */
export type GaugeOverride = { mm: number } | { deg: number } | { n: number };

export interface GaugeOverrideHandle<T extends GaugeOverride> {
  /** Pass to your editor as its `*Override` prop — anchor C. */
  override: T | null;
  /** Pass to the gauge as its `onChange` — anchor D. */
  set: (value: number) => void;
  /** Call from `closeEditor` — anchor B, THE LINE EVERYONE FORGETS. */
  reset: () => void;
}

/**
 * State + setter + reset for one gauge-driven value.
 *
 * @param key Which quantity this box carries — `"mm"`, `"deg"` or `"n"`. It is
 *   the discriminant the editor reads, so it is named at the call site rather
 *   than inferred: a silent unit swap is the one mistake this shape can still
 *   make, and it should be visible in the one line that creates the channel.
 */
export function useGaugeOverride<K extends "mm" | "deg" | "n">(
  key: K,
): GaugeOverrideHandle<Extract<GaugeOverride, Record<K, number>>> {
  type Box = Extract<GaugeOverride, Record<K, number>>;
  const [override, setOverride] = useState<Box | null>(null);
  const set = useCallback(
    (value: number) => setOverride({ [key]: value } as Box),
    [key],
  );
  const reset = useCallback(() => setOverride(null), []);
  return useMemo(() => ({ override, set, reset }), [override, set, reset]);
}
