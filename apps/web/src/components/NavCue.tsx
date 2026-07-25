/**
 * The navigation cue (UI audit #19c — "orbit/pan/zoom is undiscoverable").
 * A quiet, one-time legend that teaches the three mouse gestures the scene
 * responds to, sitting just under the command band so it reads as guidance,
 * not chrome. It states REAL bindings (drei OrbitControls defaults: left-drag
 * orbits, wheel dollies, right-drag pans) — the mandate's "wire it or delete
 * it" applies to hints too, so every line maps to an actual control.
 *
 * It recedes the moment the user no longer needs it: "Got it" dismisses it for
 * good (persisted), and it is gone on the next load. Quiet by mandate — the
 * viewport keeps the pixels.
 */
import { CloseIcon } from "@loft/design";
import { useCallback, useState } from "react";

const STORAGE_KEY = "loft.nav-cue-dismissed";

function readDismissed(): boolean {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** One gesture → action pair, stamped in the title-block idiom. */
function Gesture({ gesture, action }: { gesture: string; action: string }) {
  return (
    <span className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="font-display text-2xs uppercase tracking-[0.12em] text-mist">
        {gesture}
      </span>
      <span className="font-body text-2xs text-gauge">{action}</span>
    </span>
  );
}

export function NavCue() {
  const [dismissed, setDismissed] = useState(readDismissed);
  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, "1");
    } catch {
      /* private-mode / no storage — the cue simply reappears next load. */
    }
  }, []);

  if (dismissed) return null;

  return (
    <div
      data-testid="nav-cue"
      role="note"
      aria-label="How to move the view"
      className="absolute bottom-[84px] left-1/2 flex -translate-x-1/2 items-center gap-3 border border-hairline bg-anvil/90 px-3 py-1.5 shadow-float backdrop-blur-sm"
    >
      <span className="font-display text-2xs uppercase tracking-[0.16em] text-brass">
        Move the view
      </span>
      <span aria-hidden className="h-3 w-px bg-hairline" />
      <Gesture gesture="Drag" action="orbit" />
      <Gesture gesture="Scroll" action="zoom" />
      <Gesture gesture="Right-drag" action="pan" />
      <button
        type="button"
        onClick={dismiss}
        data-testid="nav-cue-dismiss"
        aria-label="Got it, hide this hint"
        className="ml-1 inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-display text-2xs uppercase tracking-[0.12em] text-gauge transition-colors duration-fast hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
      >
        Got it
        <CloseIcon size={12} />
      </button>
    </div>
  );
}
