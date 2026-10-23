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
import { cx, layout, ScrollRegion } from "@loft/design";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";

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
  /**
   * The panel's width token: `inspector` (320: the tree, the inspector),
   * `parameters` (the Parameters table's five columns) or `cut-list` (the
   * Cut list's takeoff table). In a rail that holds two widths, a panel hugs
   * its own side's edge, so a narrower one never floats in the middle of the
   * column.
   */
  width?: "inspector" | "parameters" | "cut-list";
  /**
   * In a rail beside a full-height VIEW (the Cut list, as Chief Architect's
   * Materials List opens), this panel gives way first, down to its
   * `min-h-rail-panel` floor, so the view takes the column. Set by the rail's
   * owner, which knows the view is open.
   */
  yields?: boolean;
  /**
   * The panel's inner edge drags wider (a palette's sash, as in Fusion): the
   * width token is the floor, the frame less a tree's column the ceiling
   * (see `resizeBounds`: a frame too narrow for both shrinks the floor).
   * Keyboard: the sash is a focusable separator; the arrow keys move it,
   * Home resets it.
   */
  resizable?: boolean;
  /**
   * In a rail shared with another panel, this one is where the user is
   * WORKING: it keeps its content height (up to 60 % of the column) and its
   * neighbour scrolls instead. Without it two railed panels shrink in
   * proportion to their content, so a three-row table opened over a long
   * inspector was squeezed to a scrolling sliver of itself.
   */
  holds?: boolean;
}

const WIDTH = {
  inspector: "w-inspector",
  parameters: "w-parameters",
  "cut-list": "w-cut-list",
} as const;

/** The width tokens in px: a resizable panel's floor. */
const WIDTH_PX = {
  inspector: layout.inspectorWidth,
  parameters: layout.parametersPanelWidth,
  "cut-list": layout.cutListPanelWidth,
} as const;

/** One arrow-key step of the sash (px); with Shift, four. */
const SASH_STEP = 32;

/** The two frame insets (`left-3`, `right-3`) a resized panel keeps clear. */
const FRAME_INSETS = 24;

/**
 * A resizable panel's width bounds (px) in a frame `frameWidth` px wide. The
 * room is the frame less its insets and the other side's tree (320): it is
 * the ceiling and, in a frame narrower than the token plus the tree (about
 * 984 px for the Cut list's 640), the floor too, so the panel never runs over
 * the tree or out of the frame. Never below the inspector's 320, nor wider
 * than the frame less its insets.
 */
export function resizeBounds(
  token: number,
  frameWidth: number,
): { floor: number; ceiling: number } {
  const room = frameWidth - FRAME_INSETS - layout.inspectorWidth;
  const least = Math.min(layout.inspectorWidth, frameWidth - FRAME_INSETS);
  const floor = Math.max(0, Math.min(token, Math.max(least, room)));
  return { floor, ceiling: Math.max(floor, room) };
}

/** A railed panel's edge: the frame edge its rail is anchored to. */
const RAIL_EDGE = { left: "self-start", right: "self-end" } as const;

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
  width = "inspector",
  holds = false,
  yields = false,
  resizable = false,
}: FloatingPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  /** A resized panel's width (px); null keeps the token's. */
  const [dragged, setDragged] = useState<number | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ x: number; width: number } | null>(null);
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

  /** A resizable panel's frame width (px), observed: its bounds follow it. */
  const [frameWidth, setFrameWidth] = useState<number>(() =>
    typeof window === "undefined" ? Infinity : window.innerWidth,
  );
  useEffect(() => {
    if (!resizable || collapsed) return;
    const node = panelRef.current;
    // Railed, the rail is the absolutely placed box; floating, the panel is.
    const frame = railed
      ? node?.parentElement?.offsetParent
      : node?.offsetParent;
    const measure = () =>
      setFrameWidth(
        frame instanceof HTMLElement ? frame.clientWidth : window.innerWidth,
      );
    measure();
    if (frame instanceof HTMLElement && typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(measure);
      observer.observe(frame);
      return () => observer.disconnect();
    }
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [resizable, collapsed, railed]);
  const { floor, ceiling } = resizeBounds(WIDTH_PX[width], frameWidth);
  function resizeTo(next: number) {
    const clamped = Math.min(ceiling, Math.max(floor, next));
    setDragged(clamped === floor ? null : Math.round(clamped));
  }
  // A drag outlives a frame that shrank under it: clamp it again.
  const current = resizable
    ? Math.round(Math.min(ceiling, Math.max(floor, dragged ?? floor)))
    : WIDTH_PX[width];
  const sized = resizable && current !== WIDTH_PX[width];
  // A right panel widens leftwards: its sash is its left edge.
  const outward = side === "right" ? -1 : 1;
  function onSashDown(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      x: event.clientX,
      width: panelRef.current?.getBoundingClientRect().width ?? current,
    };
  }
  function onSashMove(event: PointerEvent<HTMLDivElement>) {
    if (drag.current === null) return;
    resizeTo(drag.current.width + outward * (event.clientX - drag.current.x));
  }
  function onSashUp(event: PointerEvent<HTMLDivElement>) {
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }
  function onSashKey(event: KeyboardEvent<HTMLDivElement>) {
    const step = SASH_STEP * (event.shiftKey ? 4 : 1);
    let next: number | null = null;
    if (event.key === "ArrowLeft") next = current - outward * step;
    else if (event.key === "ArrowRight") next = current + outward * step;
    else if (event.key === "Home") next = floor;
    else if (event.key === "End") next = ceiling;
    if (next === null) return;
    event.preventDefault();
    resizeTo(next);
  }

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
            ? cx("shrink-0", RAIL_EDGE[side])
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
      ref={panelRef}
      data-viewport-chrome={`panel-${id}`}
      style={sized ? { width: current } : undefined}
      className={cx(
        "pointer-events-auto flex flex-col",
        WIDTH[width],
        railed && RAIL_EDGE[side],
        railed && holds && "max-h-[60%] shrink-0",
        // A yielding panel shrinks by a weight 1000x its neighbour's (flex
        // shrinks by weight x basis), so it gives way to its floor before the
        // view beside it gives up a pixel: a long view takes the column, a
        // short one keeps its content height and the rest stays this panel's.
        // The weight is put on the yielder, not a fraction on the view: a
        // shrink sum under 1 distributes only that fraction of the overflow
        // (CSS Flexbox 9.7.4), and a 0.001 view overflowed the rail.
        railed && yields && "shrink-[1000]",
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
      {resizable ? (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={`Resize ${title}`}
          aria-valuemin={Math.round(floor)}
          aria-valuemax={Math.round(ceiling)}
          aria-valuenow={current}
          tabIndex={0}
          data-testid={`panel-resize-${id}`}
          onPointerDown={onSashDown}
          onPointerMove={onSashMove}
          onPointerUp={onSashUp}
          onPointerCancel={onSashUp}
          onKeyDown={onSashKey}
          onDoubleClick={() => resizeTo(floor)}
          title="Drag to widen; double-click to reset"
          className={cx(
            "absolute inset-y-0 z-10 w-1.5 cursor-col-resize touch-none",
            side === "right" ? "-left-0.5" : "-right-0.5",
            "transition-colors duration-fast hover:bg-brass/40",
            "focus-visible:bg-brass/60 focus-visible:outline-none",
          )}
        />
      ) : null}
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
