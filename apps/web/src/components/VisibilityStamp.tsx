/**
 * The way back (UI-W2). Isolate is destructive to view state, and so is hiding
 * a handful of components one at a time: either way the modeler ends up looking
 * at a scene that is missing parts, with nothing on screen saying why. That is
 * the classic "where did my parts go" moment, and a tool answers it in the
 * viewport, not in a panel the user may have collapsed.
 *
 * So: a rubber `Stamp` over the scene, in the drawing-stamp language the clash
 * schedule and the register already use, with ONE action beside it — Show all.
 * It appears only while something is hidden, which is the mandate's rule for
 * chrome (a tile that only decorates is a defect): when the whole assembly is
 * drawn there is nothing to say and nothing on screen.
 *
 * The claim is DERIVED from the scene, never from a stored "am I isolated" flag
 * (`isolatedInstanceId`), so it cannot outlive the state it describes.
 *
 * Pointer discipline: the HUD wrapper re-enables pointer events on each direct
 * child, which would turn this banner into a click shield over the model — the
 * exact defect an audit found elsewhere today. The card is therefore explicitly
 * inert (inline style, which beats the wrapper's class rule) and only the
 * button takes clicks back, so geometry stays pickable everywhere but under the
 * one control.
 */
import { Stamp } from "@loft/design";

export interface VisibilityStampProps {
  /** The one instance still drawn, when exactly one is — else null. */
  isolatedName: string | null;
  /** How many instances are hidden right now. Zero renders nothing. */
  hiddenCount: number;
  onShowAll: () => void;
}

export function VisibilityStamp({
  isolatedName,
  hiddenCount,
  onShowAll,
}: VisibilityStampProps) {
  if (hiddenCount === 0) return null;
  const label =
    isolatedName !== null
      ? `Isolated · ${isolatedName}`
      : `${hiddenCount} hidden`;
  return (
    <div
      data-testid="visibility-stamp"
      data-hidden-count={hiddenCount}
      // Inert card, live button — see the module doc.
      style={{ pointerEvents: "none" }}
      className="absolute left-1/2 top-3 flex -translate-x-1/2 items-center gap-3 border border-hairline bg-anvil/90 px-3 py-1.5 shadow-float backdrop-blur-sm"
    >
      <Stamp tone="brass" data-testid="visibility-stamp-label">
        {label}
      </Stamp>
      <button
        type="button"
        onClick={onShowAll}
        data-testid="visibility-show-all"
        className="pointer-events-auto min-h-target-dense rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-mist outline-none transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
      >
        Show all
      </button>
    </div>
  );
}
