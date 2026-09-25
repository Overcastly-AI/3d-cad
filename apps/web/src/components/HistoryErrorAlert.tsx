/**
 * The undo/redo HUD — one rendering shared by BOTH workspaces (part +
 * assembly) so a step that does not land reads identically wherever it happens
 * (the DRY rule applied to chrome; extracted from the two verbatim copies UR3
 * left in the page bodies).
 *
 * TWO REGISTERS, because two different things can stop a step and only one of
 * them is a failure.
 *
 *  · `failed` — the server refused and the document is unchanged. Red, an
 *    alert, dismissible: the original UR3 behaviour, unchanged.
 *
 *  · `resynced` — the document moved in another window, so the step was never
 *    applied and the app quietly refetched. This used to render NOTHING, and
 *    the silence was the defect: measured 2026-09-18 with two windows on one
 *    part, the first window's Undo click took its feature count from 3 to 2
 *    while never running an undo at all — the rows that vanished were the
 *    OTHER window's undo arriving. The user presses a control, the model
 *    changes by an amount they did not ask for, and nothing on screen says
 *    their step did not run. A second press then undoes twice.
 *    So this register is not an error and must not wear error red; it is a
 *    status, and its whole job is to answer "did my key do anything?".
 *
 * A boundary no-op still renders nothing, correctly: the echoed document
 * carries fresh `can_undo`/`can_redo`, so the button disables itself and the
 * chrome has already answered the question.
 */
import type { HistoryStep } from "../lib/undoRedoShortcut";

/** Which register the HUD is in — see the note above. */
export type HistoryNoticeTone = "failed" | "resynced";

/**
 * A history step that did not land: which direction, why, and in which
 * register. `tone` is optional and defaults to `failed` so the failure call
 * sites read exactly as they did before this existed.
 */
export interface HistoryStepError {
  step: HistoryStep;
  message: string;
  tone?: HistoryNoticeTone;
}

/**
 * The stale-write copy, per workspace, in the interface's voice: what happened,
 * then what the key does now. `subject` is the document word the user sees in
 * that workspace ("part" / "assembly"), because a shared component that says
 * "part" inside the assembly workspace is a small lie told a hundred times.
 */
export function historyResyncNotice(
  step: HistoryStep,
  subject: "part" | "assembly",
): HistoryStepError {
  return {
    step,
    tone: "resynced",
    message: `This ${subject} changed in another window, so nothing was ${
      step === "undo" ? "undone" : "redone"
    } here. You are now on the current version — press again to step from it.`,
  };
}

export function HistoryErrorAlert({
  error,
  onDismiss,
}: {
  error: HistoryStepError | null;
  onDismiss: () => void;
}) {
  if (error === null) return null;
  const resynced = error.tone === "resynced";
  const verb = error.step === "undo" ? "Undo" : "Redo";
  return (
    <div
      // `alert` for a failure (it interrupts — the write did not happen);
      // `status` for a resync, which is polite because nothing was lost and
      // the user is mid-gesture.
      role={resynced ? "status" : "alert"}
      // The failure keeps its original hook, so every spec that watches for a
      // failed step keeps watching exactly the same node.
      data-testid={resynced ? "history-resynced" : "history-error"}
      className={`absolute bottom-3 left-3 max-w-sm rounded-sm border bg-anvil px-3 py-2 ${
        resynced ? "border-hairline" : "border-flag"
      }`}
    >
      <span
        className={`block font-display text-2xs uppercase tracking-[0.18em] ${
          resynced ? "text-gauge" : "text-flag"
        }`}
      >
        {resynced ? `${verb} did not run` : `${verb} failed`}
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
