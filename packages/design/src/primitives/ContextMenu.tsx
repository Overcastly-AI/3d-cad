/**
 * ContextMenu — the right-click menu, drawn in the same machine-shop idiom as
 * {@link Flyout}: a square-cornered anvil card with hairline rules, scribed
 * icons, and an engraved `Kbd` accelerator on every row. One reusable primitive
 * (fix the primitive, never the instance): the viewport and the feature tree
 * both open it, passing their own sections. Fully keyboard-navigable (roving
 * focus across sections, Home/End, Escape closes and restores focus) and quiet
 * under `prefers-reduced-motion` (the open fade is `motion-safe` only).
 *
 * Positioning: opens at the pointer (`x`/`y`, viewport-relative `position:
 * fixed`), then a layout pass nudges it back inside the window so a corner
 * click never clips the menu off-screen.
 */
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { cx } from "../cx";
import { Kbd } from "./ToolButton";
import type { ReactNode } from "react";

export interface ContextMenuItem {
  /** Stable key + default test-id suffix. */
  key: string;
  /** Row label. */
  label: string;
  /** Optional scribed glyph. */
  icon?: ReactNode;
  /** Optional keyboard accelerator chip. */
  shortcut?: string;
  onSelect: () => void;
  disabled?: boolean;
  /**
   * Why the row is gated ("Model a body first"). Reaches the pointer as a
   * `title` and a screen reader through `aria-describedby`; a gated row is
   * `aria-disabled` rather than natively disabled, so both are reachable.
   */
  disabledReason?: string;
  /** Destructive action (delete) — reads in the flag color. */
  danger?: boolean;
  "data-testid"?: string;
  "aria-label"?: string;
}

export interface ContextMenuSection {
  /** Stable key. */
  key: string;
  /** Optional tracked-caps group header. */
  label?: string;
  items: readonly ContextMenuItem[];
}

export interface ContextMenuProps {
  /** Whether the menu is mounted/open. */
  open: boolean;
  /** Pointer x in viewport pixels (clientX). */
  x: number;
  /** Pointer y in viewport pixels (clientY). */
  y: number;
  sections: readonly ContextMenuSection[];
  /** Close request (outside click, Escape, item pick, scroll/resize). */
  onClose: () => void;
  "data-testid"?: string;
  "aria-label": string;
}

/** Estimated menu size for the first paint's clamp (refined after measure). */
const MENU_MIN_WIDTH = 224;

/**
 * Can roving focus land here? Gated rows carry `aria-disabled` (they must stay
 * hoverable to explain themselves), so "enabled" is no longer the DOM `disabled`
 * property — read the attribute the row actually sets.
 */
function isSelectable(
  el: HTMLButtonElement | null | undefined,
): el is HTMLButtonElement {
  return (
    el !== null &&
    el !== undefined &&
    el.getAttribute("aria-disabled") !== "true"
  );
}

export function ContextMenu({
  open,
  x,
  y,
  sections,
  onClose,
  "data-testid": testid,
  "aria-label": ariaLabel,
}: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();
  const [pos, setPos] = useState({ left: x, top: y });

  // Re-seat the roving-focus ref array each render; the map below assigns a
  // stable flat index per item so arrow navigation crosses section boundaries.
  itemRefs.current = [];
  let flatIndex = 0;

  // Clamp inside the window once measured, and re-seed from the click point
  // every time the menu re-opens at a new spot.
  useLayoutEffect(() => {
    if (!open) return;
    const rect = menuRef.current?.getBoundingClientRect();
    const w = rect?.width || MENU_MIN_WIDTH;
    const h = rect?.height || 0;
    const maxLeft = Math.max(4, window.innerWidth - w - 4);
    const maxTop = Math.max(4, window.innerHeight - h - 4);
    setPos({ left: Math.min(x, maxLeft), top: Math.min(y, maxTop) });
  }, [open, x, y, sections]);

  // Focus return (FINDINGS burn-down 2026-07-25 #9): remember what held focus
  // when the menu opened and hand it back when the menu closes, so a keyboard
  // user who presses Escape lands back on the feature row they came from
  // instead of on <body>. Declared BEFORE the open-focus effect so it captures
  // the trigger before the first row takes focus.
  //
  // It defers to a DELIBERATE focus move: an item whose action focuses
  // something (Rename → the inline field) has already placed the caret, and
  // the menu's own row is gone by cleanup time, so we only restore when focus
  // fell back to the document body.
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const trigger = document.activeElement;
    restoreFocusRef.current = trigger instanceof HTMLElement ? trigger : null;
    return () => {
      const target = restoreFocusRef.current;
      restoreFocusRef.current = null;
      if (target === null || !target.isConnected) return;
      const active = document.activeElement;
      if (active !== null && active !== document.body) return;
      target.focus();
    };
  }, [open]);

  // Focus the first enabled row on open.
  useEffect(() => {
    if (!open) return;
    const first = itemRefs.current.findIndex(isSelectable);
    if (first >= 0) itemRefs.current[first]?.focus();
  }, [open]);

  // Dismiss on outside pointer, or on scroll/resize (the anchor would drift).
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) onClose();
    };
    const onScrollOrResize = () => onClose();
    document.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("resize", onScrollOrResize);
    window.addEventListener("scroll", onScrollOrResize, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("resize", onScrollOrResize);
      window.removeEventListener("scroll", onScrollOrResize, true);
    };
  }, [open, onClose]);

  const focusAt = useCallback((index: number) => {
    const count = itemRefs.current.length;
    for (let step = 0; step < count; step++) {
      const el = itemRefs.current[(((index + step) % count) + count) % count];
      if (isSelectable(el)) {
        el.focus();
        return;
      }
    }
  }, []);

  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const current = itemRefs.current.findIndex(
      (el) => el === document.activeElement,
    );
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusAt(current + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusAt(current - 1);
        break;
      case "Home":
        event.preventDefault();
        focusAt(0);
        break;
      case "End":
        event.preventDefault();
        focusAt(itemRefs.current.length - 1);
        break;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        onClose();
        break;
      case "Tab":
        // A context menu is modal-ish: keep focus inside, wrap with arrows.
        event.preventDefault();
        focusAt(event.shiftKey ? current - 1 : current + 1);
        break;
    }
  };

  if (!open) return null;

  return (
    <div
      ref={menuRef}
      id={menuId}
      role="menu"
      aria-label={ariaLabel}
      data-testid={testid}
      onKeyDown={onMenuKeyDown}
      onContextMenu={(e) => e.preventDefault()}
      style={{ position: "fixed", left: pos.left, top: pos.top }}
      className="z-menu min-w-[14rem] border border-hairline bg-anvil py-1 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
    >
      {sections.map((section, si) => (
        <div
          key={section.key}
          className={cx(si > 0 && "mt-1 border-t border-hairline pt-1")}
        >
          {section.label ? (
            <div className="px-3 pb-1 pt-0.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
              {section.label}
            </div>
          ) : null}
          {section.items.map((item) => {
            const index = flatIndex++;
            const gated = item.disabled === true;
            const reasonId = `${menuId}-reason-${item.key}`;
            const hasReason = gated && item.disabledReason !== undefined;
            return (
              <button
                key={item.key}
                ref={(el) => {
                  itemRefs.current[index] = el;
                }}
                type="button"
                role="menuitem"
                tabIndex={-1}
                // `aria-disabled`, not the native attribute: a natively
                // disabled row leaves the a11y tree and refuses hover, so a
                // gated verb had nowhere to say why (UI-REVIEW 2026-07-30 P2 —
                // the same trap `ToolButton` fixed two audits ago). Arrow
                // navigation still SKIPS gated rows (menu convention — see
                // `isSelectable`), but the pointer can reach one and read it.
                aria-disabled={gated || undefined}
                aria-describedby={hasReason ? reasonId : undefined}
                title={hasReason ? item.disabledReason : undefined}
                data-testid={item["data-testid"]}
                aria-label={item["aria-label"] ?? item.label}
                onClick={() => {
                  if (gated) return;
                  item.onSelect();
                  onClose();
                }}
                className={cx(
                  "flex min-h-target-dense w-full select-none items-center gap-2.5 px-3 py-1.5 text-left",
                  "transition-colors duration-fast",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
                  gated
                    ? "cursor-not-allowed opacity-40"
                    : item.danger
                      ? "text-flag hover:bg-flag/10 focus-visible:bg-flag/10"
                      : "text-mist hover:bg-carbide focus-visible:bg-carbide",
                  gated && (item.danger ? "text-flag" : "text-mist"),
                )}
              >
                <span
                  aria-hidden
                  className={cx(
                    "flex w-4 shrink-0 items-center justify-center",
                    item.danger ? "text-flag" : "text-gauge",
                  )}
                >
                  {item.icon}
                </span>
                <span className="grow font-body text-xs">{item.label}</span>
                {hasReason ? (
                  <span id={reasonId} className="sr-only">
                    {item.disabledReason}
                  </span>
                ) : null}
                {item.shortcut ? <Kbd>{item.shortcut}</Kbd> : null}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
