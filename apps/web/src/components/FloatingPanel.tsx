/**
 * A floating instrument panel (Batch 1 makeover; UI-REVIEW 2026-07-16 P0-4).
 * The tree/inspector used to be flex COLUMNS subtracted from the canvas —
 * the scene literally ended where they began. Now the canvas is full-bleed
 * and these panels float over it (the Fusion/Plasticity pattern),
 * collapsible to a corner tab so the scene can take 100% of the frame.
 *
 * Pure positioning + collapse chrome: the content keeps its own testids and
 * scroll. Default is expanded — collapse is a real, user-driven state.
 */
import { cx, ScrollRegion } from "@loft/design";
import { useEffect, useState, type ReactNode } from "react";

import { announceChromeChange } from "../viewport/fitFraming";
import { useRailSlot } from "./ChromeRail";

export interface FloatingPanelProps {
  side: "left" | "right";
  /** Tracked-caps tab label + accessible name of the collapse control. */
  title: string;
  /** Test-hook suffix: `panel-collapse-${id}` / `panel-expand-${id}`. */
  id: string;
  children: ReactNode;
  /**
   * Bottom clearance (Tailwind max-height class) so bottom-anchored HUD
   * (DRO, import status, view rail) stays reachable under a tall panel.
   * Defaults are side-aware (see below); pass to override.
   */
  maxHeightClassName?: string;
  /**
   * An action row pinned below the scrolling body — the panel's answer to the
   * same problem `EditorCard.footer` solves: the panel's height is clamped, so
   * whatever sits LAST in a scrolling column is whatever falls under the fold,
   * and that is never what should be sacrificed. The inspector's EXPORT strip
   * lives here for exactly that reason (UI-REVIEW 2026-07-30 P1: the 48px
   * timeline shrank the frame and the strip — including the sentence warning
   * that a file will be marked *partial* — went off the bottom at 1366x768).
   *
   * Trimming the copy above it is not a fix; that had already failed twice.
   */
  footer?: ReactNode;
}

// The reference cube (drei GizmoHelper) always lives bottom-RIGHT, occupying
// roughly the 64–144px band above the frame's bottom edge. A tall right panel
// at the default clearance would draw its opaque body over that band and hide a
// table-stakes nav element (mandate 3a). Right panels therefore clear the cube
// band; left panels keep the tight default (nothing but the DRO sits
// bottom-left, and that lives below any panel). Both clamps are token-derived
// (`maxHeight.hud-card` / `.cube-card`) so the feature-editor cards can use the
// same one instead of inventing a second clamp.
const DEFAULT_CLEARANCE = {
  left: "max-h-hud-card",
  right: "max-h-cube-card",
} as const;

export function FloatingPanel({
  side,
  title,
  id,
  children,
  maxHeightClassName = DEFAULT_CLEARANCE[side],
  footer,
}: FloatingPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  // Inside a `ChromeRail` the panel is a FLOW child of the column it shares
  // with the feature editor, not an absolutely-placed card: the rail owns the
  // seat, the inset and the clamp, and the panel takes whatever the editor
  // leaves — down to `min-h-rail-panel`, never to nothing.
  const railed = useRailSlot(side) !== null;
  // A panel that opens or closes changes how much of the scene the modeler can
  // see, so "Fit model" has to be re-solvable against the new free rect —
  // announced rather than polled (see `fitFraming.VIEWPORT_CHROME_EVENT`).
  // In a rail the rail itself observes the column's edge, so the announcement
  // is made once, by whichever of the two actually changed the charged inset.
  useEffect(() => {
    if (railed) return;
    announceChromeChange();
  }, [collapsed, railed]);

  if (collapsed) {
    return (
      <button
        type="button"
        data-testid={`panel-expand-${id}`}
        aria-expanded={false}
        data-viewport-chrome={`panel-${id}`}
        onClick={() => setCollapsed(false)}
        className={cx(
          "pointer-events-auto border border-hairline bg-anvil px-2 py-1.5 shadow-float",
          "font-display text-2xs uppercase tracking-[0.16em] text-gauge",
          "transition-colors duration-fast hover:text-brass",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
          railed
            ? "shrink-0 self-start"
            : cx(
                "absolute top-3 z-panel",
                side === "left" ? "left-3" : "right-3",
              ),
        )}
      >
        {title} {side === "left" ? "▸" : "◂"}
      </button>
    );
  }

  return (
    <div
      data-viewport-chrome={`panel-${id}`}
      className={cx(
        "pointer-events-auto flex w-inspector flex-col",
        railed
          ? // A flow child of the rail: shrinkable so a tall editor can take the
            // room it needs, floored at `min-h-rail-panel` so the tree it was
            // opened from stays usable. Its own body scroll (below) does the
            // rest. `relative` keeps the collapse tab anchored to the panel's
            // own corner — in the floating case `absolute` already provides
            // that. NO `max-w` here: percentages would resolve against the rail
            // (320px) instead of the frame and shave 24px off every panel; the
            // rail carries the frame clamp for the whole column. No `flex-1`
            // either: the panel HUGS its content the way it always has, and
            // only shrinks (scrolling its own body) when the card above it
            // needs the room — a tree stretched to fill the column would just
            // be a taller box of empty anvil.
            "relative min-h-rail-panel"
          : cx(
              "absolute top-3 z-panel max-w-[calc(100%-1.5rem)]",
              maxHeightClassName,
              side === "left" ? "left-3" : "right-3",
            ),
      )}
    >
      {/* Collapse tab — pinned to the heading row's empty right corner (the
          eyebrow text is left-aligned, so no content is ever covered). */}
      <button
        type="button"
        data-testid={`panel-collapse-${id}`}
        aria-expanded={true}
        aria-label={`Collapse ${title}`}
        onClick={() => setCollapsed(true)}
        className={cx(
          "absolute right-0 top-0 z-10 h-6 w-6 border-b border-l border-hairline bg-anvil",
          "font-data text-xs leading-none text-gauge",
          "transition-colors duration-fast hover:text-brass",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
        )}
      >
        {side === "left" ? "◂" : "▸"}
      </button>
      {/* The body scrolls, and SAYS SO — see `ScrollRegion`. It was a bare
          `overflow-y-auto` div until T-18: correct, invisible, and therefore
          read (three audit passes running) as a panel that truncates. The
          primitive owns the scrollbar, the break rule and the keyboard seat;
          nothing here restyles them. */}
      <ScrollRegion label={`${title} readouts`} className="shadow-float">
        {children}
      </ScrollRegion>
      {footer !== undefined ? (
        <div
          className="shrink-0 shadow-float"
          data-testid={`panel-footer-${id}`}
        >
          {footer}
        </div>
      ) : null}
    </div>
  );
}
