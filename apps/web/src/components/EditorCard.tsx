/**
 * EditorCard — the ONE shell every HUD feature editor hangs in.
 *
 * Seventeen editors had copied the same positioning string
 * (`absolute left-editor top-3 w-editor max-w-full`) with no height clamp, so
 * the card was free to grow off the bottom of the frame as verbs kept landing.
 * Measured on 2026-07-30: an M10 countersunk blind TAPPED hole made the hole
 * editor 858px tall, which at 1366×768 put the derived tap-drill override chip
 * *and* the whole Cancel/Create footer below the fold — and made the app root
 * scrollable, so the page scrolled the top bar away instead (UI-REVIEW P1).
 *
 * The clamp is not a second invention: `max-h-hud-card` is the same
 * token-derived clearance `FloatingPanel` uses (`layout.hudLaneBottom`), so the
 * bottom HUD lane — view rail, measure readout, DRO — stays reachable under any
 * card. The body scrolls; an optional `footer` is pinned outside the scroll so
 * the commit action never scrolls away from a modeller mid-edit.
 *
 * Anatomy (title-block idiom preserved — the header and footer keep the card's
 * ruled frame, so a clamped card reads as one instrument with its anchor block
 * and action row ruled off, not as three floating boxes):
 *
 *   ┌───────────────────────────┐  ← top-3, w-editor
 *   │ NEW HOLE                  │
 *   │ FACE   Face at 5, 5, 10 ⟳ │  ← header, pinned (shrink-0)
 *   ├───────────────────────────┤
 *   │ …fields…            ▲     │  ← min-h-0 overflow-y-auto (scrolls)
 *   │                     ▼     │
 *   ├─────────────┬─────────────┤
 *   │   CANCEL    │   CREATE    │  ← footer, pinned (shrink-0)
 *   └─────────────┴─────────────┘
 *
 * WHY a header slot and not just "put it first in the body": a feature's
 * REFERENCES (what it is attached to) and its PARAMETERS (numbers) are
 * different kinds of thing, and only the references can be lost without the
 * card being able to say so. Scrolling them away is how "Placement face" ended
 * up below the fold while "C'sink angle" was on screen (UI-W4) — so the slot
 * that holds them does not scroll, by construction.
 */
import { cx } from "@loft/design";
import type { HTMLAttributes, ReactNode } from "react";

export interface EditorCardProps extends HTMLAttributes<HTMLDivElement> {
  /**
   * Which seat the card takes. `left` is the title-block seat clearing the
   * feature tree; `right` is used while a viewport pick is armed, so the card
   * never covers the face the user must click.
   */
  seat?: "left" | "right";
  /**
   * The feature's REFERENCE anchor block, pinned above the scrolling body —
   * what this feature is attached to, always in sight. See `HoleEditor` for
   * the reference header.
   */
  header?: ReactNode;
  /**
   * Action row (and any error stamp) pinned below the scrolling body. Give it
   * the card's own frame — see `HoleEditor` for the reference footer.
   */
  footer?: ReactNode;
  children: ReactNode;
}

export function EditorCard({
  seat = "left",
  header,
  footer,
  className,
  children,
  ...rest
}: EditorCardProps) {
  return (
    <div
      className={cx(
        // `shadow-float` is the floating-instrument language `FloatingPanel`
        // already speaks: a card that shares a rail with a panel has to read as
        // LIFTED OVER it, or the two run together into one impossible column.
        "absolute top-3 flex w-editor max-w-full flex-col shadow-float",
        // Seat-aware clearance, the same pair `FloatingPanel` uses: a card on
        // the RIGHT rail must also clear the in-canvas reference cube, because
        // covering the view gizmo is a mandate-3a defect (measured: a
        // right-seated hole editor drew its footer straight over the cube).
        seat === "right"
          ? "right-3 max-h-cube-card"
          : "left-editor max-h-hud-card",
        className,
      )}
      {...rest}
    >
      {header !== undefined ? <div className="shrink-0">{header}</div> : null}
      <div className="flex min-h-0 flex-col overflow-y-auto">{children}</div>
      {footer !== undefined ? <div className="shrink-0">{footer}</div> : null}
    </div>
  );
}
