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
}

export const useCommandActionStore = create<CommandActionState>((set, get) => ({
  submitNonce: 0,
  requestSubmit: () => set({ submitNonce: get().submitNonce + 1 }),
}));

/**
 * An open editor bridges the in-command band's OK to its own submit. `ready`
 * is the editor's existing submit gate (`canSubmit`) so a band OK on an invalid
 * form is inert, exactly like the editor's disabled Create cell. Never fires on
 * mount — only on a real nonce bump.
 */
export function useCommandBridge(submit: () => void, ready: boolean): void {
  const nonce = useCommandActionStore((s) => s.submitNonce);
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
}
