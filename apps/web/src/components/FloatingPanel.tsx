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
import { cx } from "@loft/design";
import { useState, type ReactNode } from "react";

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
}

// The reference cube (drei GizmoHelper) always lives bottom-RIGHT, occupying
// roughly the 64–144px band above the frame's bottom edge. A tall right panel
// at the default 4.5rem clearance would draw its opaque body over that band and
// hide a table-stakes nav element (mandate 3a). Right panels therefore clear the
// cube band; left panels keep the tight default (nothing but the DRO sits
// bottom-left, and that lives below any panel).
const DEFAULT_CLEARANCE = {
  left: "max-h-[calc(100%-4.5rem)]",
  right: "max-h-[calc(100%-9.5rem)]",
} as const;

export function FloatingPanel({
  side,
  title,
  id,
  children,
  maxHeightClassName = DEFAULT_CLEARANCE[side],
}: FloatingPanelProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <button
        type="button"
        data-testid={`panel-expand-${id}`}
        aria-expanded={false}
        onClick={() => setCollapsed(false)}
        className={cx(
          "absolute top-3 z-panel border border-hairline bg-anvil px-2 py-1.5 shadow-float",
          "font-display text-2xs uppercase tracking-[0.16em] text-gauge",
          "transition-colors duration-fast hover:text-brass",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
          side === "left" ? "left-3" : "right-3",
        )}
      >
        {title} {side === "left" ? "▸" : "◂"}
      </button>
    );
  }

  return (
    <div
      className={cx(
        "absolute top-3 z-panel flex w-inspector max-w-[calc(100%-1.5rem)] flex-col",
        maxHeightClassName,
        side === "left" ? "left-3" : "right-3",
      )}
    >
      {/* Collapse tab — pinned to the heading row's empty right corner (the
          eyebrow text is left-aligned, so no content is ever covered). NB:
          the preset's closed spacing scale has no `px` step — only scale
          values (`top-0`/`right-0`) compile. */}
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
      <div className="min-h-0 overflow-y-auto shadow-float">{children}</div>
    </div>
  );
}
