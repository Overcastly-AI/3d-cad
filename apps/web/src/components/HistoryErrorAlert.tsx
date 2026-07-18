/**
 * The undo/redo failure HUD — one rendering shared by BOTH workspaces (part +
 * assembly) so a failed step reads identically wherever it happens (the DRY
 * rule applied to chrome; extracted from the two verbatim copies UR3 left in
 * the page bodies). A non-stale undo/redo failure is surfaced honestly here
 * (mandate 3a — chrome shows its real state) rather than swallowed; stale and
 * boundary-no-op steps never reach it (they resync quietly).
 */
import type { HistoryStep } from "../lib/undoRedoShortcut";

/** A failed history step: which direction, and the server's message. */
export interface HistoryStepError {
  step: HistoryStep;
  message: string;
}

export function HistoryErrorAlert({
  error,
  onDismiss,
}: {
  error: HistoryStepError | null;
  onDismiss: () => void;
}) {
  if (error === null) return null;
  return (
    <div
      role="alert"
      data-testid="history-error"
      className="absolute bottom-3 left-3 max-w-sm rounded-sm border border-flag bg-anvil px-3 py-2"
    >
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-flag">
        {error.step === "undo" ? "Undo failed" : "Redo failed"}
      </span>
      <span className="mt-1 block font-body text-xs text-mist">
        {error.message}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        data-testid="history-error-dismiss"
        className="mt-2 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
      >
        Dismiss
      </button>
    </div>
  );
}
