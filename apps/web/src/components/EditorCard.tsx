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
import { cx, ScrollRegion } from "@loft/design";
import type { HTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";

import { useRailSlot } from "./ChromeRail";

export interface EditorCardProps extends HTMLAttributes<HTMLDivElement> {
  /**
   * WHICH RAIL the card takes. `left` is the title-block seat, sharing the
   * feature tree's column; `right` is used while a viewport pick is armed, so
   * the card never covers the face the user must click.
   *
   * Where a `ChromeRail` is mounted for that side the card DOCKS into it — the
   * fix for FB-7, the founder's photograph of an editor sitting on the model it
   * was editing. Measured at HEAD on a 1600x1000 frame: the extrude card covered
   * 50 069 px2, 9.0 % of the body's screen box. Docking makes that overlap
   * structurally impossible rather than merely smaller, which is why compaction
   * was rejected as the fix: a smaller panel still covers the part.
   *
   * With no rail in context (the assembly and drawing workspaces, and component
   * unit tests) the card floats exactly as it always has.
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
  const rail = useRailSlot(seat);
  const card = (
    <div
      className={cx(
        // `shadow-float` is the floating-instrument language `FloatingPanel`
        // already speaks: a card that shares a rail with a panel has to read as
        // LIFTED OVER it, or the two run together into one impossible column.
        "flex w-editor max-w-full flex-col shadow-float",
        rail !== null
          ? // Docked: a flow child of the rail, and the one that gets its way.
            // `shrink-0` because the card is the instrument being OPERATED — a
            // 591px feature tree must not scroll the Operation row out of an
            // open extrude (measured: it took 71px). `max-h-rail-card` is what
            // keeps that safe: the tallest card still leaves the panel its
            // floor, so the column can never overflow into the HUD lane. Both
            // resolve because the rail's height is definite.
            "pointer-events-auto max-h-rail-card min-h-0 shrink-0"
          : // Floating: seat-aware clearance, the same pair `FloatingPanel`
            // uses. A card on the RIGHT must also clear the in-canvas reference
            // cube, because covering the view gizmo is a mandate-3a defect
            // (measured: a right-seated hole editor drew its footer over it).
            cx(
              "absolute top-3",
              seat === "right"
                ? "right-3 max-h-cube-card"
                : "left-editor max-h-hud-card",
            ),
        className,
      )}
      {...rest}
    >
      {header !== undefined ? <div className="shrink-0">{header}</div> : null}
      {/* Same primitive, same reason as `FloatingPanel` (T-18): a clamped body
          that clips mid-field with no scrollbar and no rule reads as a card
          that ends there. The tallest editors (an M10 countersunk blind tapped
          hole) are exactly where that costs a field. */}
      <ScrollRegion label="Editor fields" contentClassName="flex flex-col">
        {children}
      </ScrollRegion>
      {footer !== undefined ? <div className="shrink-0">{footer}</div> : null}
    </div>
  );
  return rail === null ? card : createPortal(card, rail);
}
