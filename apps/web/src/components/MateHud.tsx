/**
 * The mate-authoring HUD — the in-viewport prompt while a mate tool is armed
 * (the DRO/solve-diagnostic drawing-stamp language). It reads the mate store
 * for the active tool + how many picks are collected and tells the user the
 * next click; the store's rejection (same instance twice) and the submit error
 * surface here too. Nothing renders when no tool is armed.
 */
import { useMateAuthoringStore } from "../assembly/mateStore";

const FIRST: Record<string, string> = {
  coincident: "Pick a flat face on the first part.",
  concentric: "Pick a hole edge on the first part.",
  lock: "Pick the first part to anchor to.",
};
const SECOND: Record<string, string> = {
  coincident: "Now pick the mating face on the OTHER part — they snap flush.",
  concentric: "Now pick the mating hole edge on the OTHER part — axes align.",
  lock: "Now pick the OTHER part to lock it rigidly.",
};

export interface MateHudProps {
  /** A POST/re-solve failure, surfaced verbatim. */
  submitError: string | null;
  /** The mate is being added + re-solved (the snap). */
  submitting: boolean;
}

export function MateHud({ submitError, submitting }: MateHudProps) {
  const tool = useMateAuthoringStore((s) => s.tool);
  const picks = useMateAuthoringStore((s) => s.picks);
  const error = useMateAuthoringStore((s) => s.error);
  if (tool === null) return null;

  const prompt = picks.length === 0 ? FIRST[tool] : SECOND[tool];

  return (
    <div
      role="status"
      data-testid="mate-hud"
      data-mate-tool={tool}
      className="absolute left-editor top-3 max-w-sm border border-brass bg-anvil px-3 py-2"
    >
      <span className="block font-display text-2xs uppercase tracking-[0.18em] text-brass">
        {tool === "coincident"
          ? "Coincident mate"
          : tool === "concentric"
            ? "Concentric mate"
            : "Lock mate"}
      </span>
      <span className="mt-1 block font-body text-xs text-mist">
        {submitting ? "Solving the assembly…" : prompt}
      </span>
      {error ? (
        <span
          role="alert"
          className="mt-1 block font-body text-xs text-flag"
          data-testid="mate-hud-error"
        >
          {error}
        </span>
      ) : null}
      {submitError ? (
        <span
          role="alert"
          className="mt-1 block font-body text-xs text-flag"
          data-testid="mate-submit-error"
        >
          {submitError}
        </span>
      ) : null}
    </div>
  );
}
