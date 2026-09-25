/**
 * `useGaugeFedForm` — an editor's form state, re-seeded when the editor is
 * retargeted and written by its viewport gauges, with BOTH kinds of write made
 * DURING RENDER rather than from an effect.
 *
 * WHY DURING RENDER (measured 2026-09-23, `3b7f9ad`). Written from an effect,
 * each gauge write cost the field one extra commit, at DEFAULT priority, after
 * the render that carried the new override. The gauge draws its ask in the
 * render of the pointer event itself, so on every drag step the drawn rod led
 * the field by a commit, and after a release the field could read the PREVIOUS
 * step against the rod's new one for 100-300 ms (`release · rod=26 field=25 ·
 * ... · field=26`) — two numbers on screen that disagree. Written here, the
 * field commits WITH the override that carries its value: 0 disagreeing frames
 * in 10 timed drags, where every step used to show one.
 *
 * This is React's "adjusting state when a prop changes" pattern. Every write is
 * guarded by the prop identity it has already applied, so it runs once per NEW
 * prop and never per render — which is what leaves the field typeable while an
 * override stands.
 *
 * ORDER IS PART OF THE CONTRACT. The re-seed is queued first and the gauge
 * writes after it, in the order they are passed, so a retarget and a drag that
 * land in the same render compose exactly as the effects this replaces did
 * (re-seed, then the drag on top).
 *
 * WHY ONE HOOK. Eight editors had the same two effects, each a copy of the
 * other seven; `3b7f9ad` fixed one of them. Fixing the other seven by copying
 * the fix would have left eight places to keep in step, and the next timing
 * defect would again be fixed in one.
 */
import { type Dispatch, type SetStateAction, useState } from "react";

/**
 * One gauge's write into the form. Build it with `gaugeWrite`, which keeps the
 * override's own type inside the closure.
 */
export interface GaugeWrite<F> {
  /**
   * The gauge's latest value, or `null` when it has written nothing. IDENTITY
   * is the signal: a new object is a new write even when its number repeats
   * (dragging back to the same value must still land after a typed edit).
   */
  readonly override: object | null;
  /**
   * Whatever else the written TEXT depends on — the document length unit for a
   * length. A change re-writes the standing override, as the effect's
   * dependency array did. `undefined` for a unitless value.
   */
  readonly formattedBy: unknown;
  /** The form with this override written into it. Never called when null. */
  readonly apply: (form: F) => F;
}

/**
 * Pair a gauge's override with the field write it drives. `formattedBy` is the
 * value the text is formatted with (the document unit), so changing it
 * re-writes the field.
 */
export function gaugeWrite<F, O extends object>(
  override: O | null,
  write: (form: F, override: O) => F,
  formattedBy?: unknown,
): GaugeWrite<F> {
  return {
    override,
    formattedBy,
    apply: (form) => (override === null ? form : write(form, override)),
  };
}

interface Applied {
  readonly override: object;
  readonly formattedBy: unknown;
}

/**
 * The editor's form, seeded from `initial` and re-seeded whenever `initial`
 * changes identity (a retarget at another feature), then written by `writes`
 * in order. Pass the SAME number of writes on every render — each keeps the
 * identity it last applied by position, exactly as hooks keep their state.
 */
export function useGaugeFedForm<F>(
  initial: F,
  ...writes: readonly GaugeWrite<F>[]
): readonly [F, Dispatch<SetStateAction<F>>] {
  // Lazy initialisers and updater-form writes throughout: `F` is generic, and a
  // bare `useState(initial)` / `setForm(initial)` would CALL a function-typed F.
  const [form, setForm] = useState<F>(() => initial);

  // Re-seed on retarget. Queued before the gauge writes below, so they land on
  // top of the new seed rather than being erased by it.
  const [seededFrom, setSeededFrom] = useState<F>(() => initial);
  if (seededFrom !== initial) {
    setSeededFrom(() => initial);
    setForm(() => initial);
  }

  // Each gauge write, once per new override (or new unit for a standing one).
  const [applied, setApplied] = useState<readonly (Applied | null)[]>([]);
  let next: (Applied | null)[] | null = null;
  for (const [i, w] of writes.entries()) {
    if (w.override === null) continue;
    const was = applied[i] ?? null;
    if (
      was !== null &&
      was.override === w.override &&
      Object.is(was.formattedBy, w.formattedBy)
    ) {
      continue;
    }
    next ??= [...applied];
    next[i] = { override: w.override, formattedBy: w.formattedBy };
    setForm(w.apply);
  }
  if (next !== null) setApplied(next);

  return [form, setForm];
}
