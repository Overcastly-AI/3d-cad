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
 * Anatomy (title-block idiom preserved — the footer keeps the card's ruled
 * frame, so a clamped card reads as one instrument with its action row ruled
 * off, not as two floating boxes):
 *
 *   ┌───────────────────────────┐  ← top-3, w-editor
 *   │ NEW HOLE                  │
 *   │ …fields…            ▲     │  ← min-h-0 overflow-y-auto (scrolls)
 *   │                     ▼     │
 *   ├─────────────┬─────────────┤
 *   │   CANCEL    │   CREATE    │  ← footer, pinned (shrink-0)
 *   └─────────────┴─────────────┘
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
   * Action row (and any error stamp) pinned below the scrolling body. Give it
   * the card's own frame — see `HoleEditor` for the reference footer.
   */
  footer?: ReactNode;
  children: ReactNode;
}

export function EditorCard({
  seat = "left",
  footer,
  className,
  children,
  ...rest
}: EditorCardProps) {
  return (
    <div
      className={cx(
        "absolute top-3 flex max-h-hud-card w-editor max-w-full flex-col",
        seat === "right" ? "right-3" : "left-editor",
        className,
      )}
      {...rest}
    >
      <div className="flex min-h-0 flex-col overflow-y-auto">{children}</div>
      {footer !== undefined ? <div className="shrink-0">{footer}</div> : null}
    </div>
  );
}
