/**
 * What an armed assembly picker is waiting on, and what it cannot offer
 * (BIKE2-FAILED-PART-KILLS-PICKS). The on-holes picker sat at "PICKING…" for
 * 40 s with no word of why; now, while a mate, joint or pattern pick is armed:
 *
 *  - "Loading edges and faces to pick…" while overlays are on their way;
 *  - one line per part that has none: "Crank arm has nothing to pick: <why>.
 *    The other parts can be picked." — a part that failed to build, or whose
 *    pick geometry did not arrive within the timeout (`pickOverlays.ts`).
 *
 * Renders nothing when no picker is armed or all is well.
 */
import type { PickOverlays } from "../assembly/pickOverlays";

/** A kernel message, closed as a sentence. */
function sentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

export function PickGeometryStatus({
  active,
  overlays,
}: {
  active: boolean;
  overlays: PickOverlays;
}) {
  if (!active) return null;
  const { loading, failures } = overlays;
  if (!loading && failures.length === 0) return null;
  return (
    <div
      data-testid="pick-geometry-status"
      data-loading={loading ? "true" : "false"}
      aria-live="polite"
      className="absolute bottom-3 left-1/2 max-w-md -translate-x-1/2 border border-hairline bg-anvil px-3 py-2"
    >
      {loading ? (
        <p className="font-body text-xs text-gauge">
          Loading edges and faces to pick…
        </p>
      ) : null}
      {failures.map((failure) => (
        <p
          key={failure.partDocumentId}
          role="alert"
          data-testid="pick-geometry-failed"
          data-part-document-id={failure.partDocumentId}
          className="font-body text-xs text-flag"
        >
          {failure.name} has nothing to pick: {sentence(failure.message)} The
          other parts can be picked.
        </p>
      ))}
    </div>
  );
}
