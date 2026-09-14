/**
 * In-command action bus (Makeover Batch 3, item 10 — UI-REVIEW 2026-07-16).
 *
 * While a feature editor is open the command band recedes to an in-command
 * bar (the active command + OK / Cancel). Cancel is wired straight to the
 * workspace's `closeEditor`, but OK must run the OPEN editor's own validated
 * submit — and that submit lives inside the editor (it owns the form state).
 *
 * This tiny store bridges the two: the in-command OK bumps `submitNonce`, and
 * the open editor's `useCommandBridge` runs its submit on the bump (exactly the
 * editor's Enter path, driven from the band). One command is ever open, so one
 * nonce suffices; nonce-keyed so a repeated OK re-fires.
 */
import { useEffect, useRef } from "react";
import { create } from "zustand";

interface CommandActionState {
  /** Bumped by the in-command band's OK — the open editor commits on change. */
  submitNonce: number;
  requestSubmit: () => void;
  /**
   * The open editor's submit gate (`canSubmit`), published by its bridge so the
   * in-command band's OK cell can render its TRUE state — honestly disabled on
   * an invalid form, not silently inert (mandate 3a: chrome reads its real
   * state). `false` whenever no editor is open.
   */
  okReady: boolean;
  setOkReady: (ready: boolean) => void;
  /**
   * The feature ids the OPEN command will act on, published by the editor that
   * owns the choice, so the tree, the timeline and the viewport can mark them
   * (REACH-2-FLOW P1-2: the pattern editor named `HOLE1` and nothing in the
   * frame echoed it, on a part with two visually identical holes).
   *
   * It is DERIVED from the editor's live form state rather than from the tree
   * selection, and that difference is the point: the scope row is a two-state
   * toggle the user can flip mid-command, so a selection-driven mark would keep
   * pointing at `Hole1` after they chose `This body` — chrome stating something
   * the command will not do. It also covers a case selection cannot: an editor
   * seeded from the TIP feature has a subject while nothing at all is selected.
   *
   * THREE STATES, NOT TWO (REACH-2-FLOW-B). `null` means no command is
   * authoring a scope — most of the time, since most editors have no subject to
   * name. `[]` means one IS, and its answer names no feature (`This body`).
   * The tree and the timeline can conflate those two, because neither has a
   * fallback and both render the absence identically; the viewport cannot, and
   * conflating them is precisely how its tint went on saying `Hole1` after the
   * user chose the whole body. See `viewport/scopeHighlight.ts`.
   */
  scopedFeatureIds: readonly string[] | null;
  setScopedFeatures: (ids: readonly string[] | null) => void;
}

/** Same members, same order — so re-publishing an unchanged scope is a no-op. */
function sameIds(
  a: readonly string[] | null,
  b: readonly string[] | null,
): boolean {
  if (a === null || b === null) return a === b;
  return a.length === b.length && a.every((id, i) => id === b[i]);
}

export const useCommandActionStore = create<CommandActionState>((set, get) => ({
  submitNonce: 0,
  requestSubmit: () => set({ submitNonce: get().submitNonce + 1 }),
  okReady: false,
  setOkReady: (ready) =>
    set((state) => (state.okReady === ready ? state : { okReady: ready })),
  scopedFeatureIds: null,
  setScopedFeatures: (ids) =>
    set((state) =>
      sameIds(state.scopedFeatureIds, ids) ? state : { scopedFeatureIds: ids },
    ),
}));

/**
 * An open editor bridges the in-command band's OK to its own submit. `ready`
 * is the editor's existing submit gate (`canSubmit`) so a band OK on an invalid
 * form is inert, exactly like the editor's disabled Create cell. Never fires on
 * mount — only on a real nonce bump.
 */
export function useCommandBridge(submit: () => void, ready: boolean): void {
  const nonce = useCommandActionStore((s) => s.submitNonce);
  const setOkReady = useCommandActionStore((s) => s.setOkReady);
  const seen = useRef(nonce);
  // Keep the latest submit/ready without re-subscribing the effect to them.
  const submitRef = useRef(submit);
  submitRef.current = submit;
  const readyRef = useRef(ready);
  readyRef.current = ready;
  useEffect(() => {
    if (nonce === seen.current) return;
    seen.current = nonce;
    if (readyRef.current) submitRef.current();
  }, [nonce]);
  // Publish the submit gate so the band's OK cell renders its true state.
  useEffect(() => {
    setOkReady(ready);
  }, [ready, setOkReady]);
  // Clear it when the editor closes so a closed command never leaves the OK
  // cell falsely enabled on the next open (reset runs only on unmount —
  // `setOkReady` is a stable store setter).
  useEffect(() => () => setOkReady(false), [setOkReady]);
}

/**
 * Publish what the open command acts on, for as long as it is open.
 *
 * Lives beside `useCommandBridge` because it is the same seam pointed the other
 * way: the bridge carries the band's OK INTO the editor, this carries the
 * editor's subject OUT to the tree, the timeline and the viewport. Mounting
 * declares "a command is asking"; unmounting retracts the whole question (back
 * to `null`, not to `[]`), so a closed command can never leave a stale mark —
 * which would make the mark worse than no mark at all — and can never suppress
 * the tree selection's own tint on its way out.
 */
export function usePublishedScope(featureIds: readonly string[]): void {
  const setScopedFeatures = useCommandActionStore((s) => s.setScopedFeatures);
  // The array identity changes on nearly every render at the call site (it is
  // mapped from form state), so the effect keys on the CONTENT, not the
  // reference — otherwise it would re-publish forever.
  const key = featureIds.join(" ");
  useEffect(() => {
    setScopedFeatures(key === "" ? [] : key.split(" "));
  }, [key, setScopedFeatures]);
  useEffect(() => () => setScopedFeatures(null), [setScopedFeatures]);
}
