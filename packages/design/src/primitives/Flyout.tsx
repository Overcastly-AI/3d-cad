/**
 * Flyout — a grouped dropdown menu (Fusion's "gallery under a group"), drawn
 * in the machine-shop idiom: a square-cornered anvil card with hairline rules,
 * scribed icons, and an engraved `Kbd` accelerator on every row. Fully
 * keyboard-navigable (roving focus, Home/End, Escape returns focus to the
 * trigger) so the discoverable surface never costs a power user their hands.
 *
 * Items are a prop (not children) so the menu owns focus management: it can
 * reach every row's button ref for arrow navigation without a context dance.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { cx } from "../cx";
import { CaretDownIcon } from "./icons";
import { Kbd } from "./ToolButton";
import type { ReactNode } from "react";

export interface FlyoutItem {
  /** Stable key + return value; also the default test id suffix. */
  key: string;
  /** Scribed glyph element. */
  icon: ReactNode;
  /** Row label. */
  label: string;
  /** Keyboard accelerator chip. */
  shortcut?: string;
  onSelect: () => void;
  disabled?: boolean;
  "data-testid"?: string;
  "aria-label"?: string;
}

export interface FlyoutProps {
  /** Group name on the trigger (e.g. "Geometric"). */
  label: string;
  /** Group glyph on the trigger. */
  icon: ReactNode;
  items: readonly FlyoutItem[];
  /** Tracked-caps header inside the menu. */
  eyebrow?: string;
  "data-testid"?: string;
}

/**
 * A group trigger + its menu. The trigger mirrors `ToolButton` styling but
 * carries a caret and `aria-haspopup`; opening focuses the first enabled row.
 */
export function Flyout({
  label,
  icon,
  items,
  eyebrow,
  "data-testid": testid,
}: FlyoutProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();

  const close = useCallback((focusTrigger: boolean) => {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  }, []);

  // Focus the first enabled row when the menu opens.
  useEffect(() => {
    if (!open) return;
    const first = itemRefs.current.findIndex((el) => el && !el.disabled);
    if (first >= 0) itemRefs.current[first]?.focus();
  }, [open]);

  // Dismiss on outside pointer or focus leaving the group.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () =>
      document.removeEventListener("pointerdown", onPointerDown, true);
  }, [open]);

  const focusAt = (index: number) => {
    const count = itemRefs.current.length;
    for (let step = 0; step < count; step++) {
      const el = itemRefs.current[(index + step + count) % count];
      if (el && !el.disabled) {
        el.focus();
        return;
      }
    }
  };

  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const current = itemRefs.current.findIndex(
      (el) => el === document.activeElement,
    );
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        event.stopPropagation();
        focusAt(current + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        event.stopPropagation();
        focusAt(current - 1);
        break;
      case "Home":
        event.preventDefault();
        event.stopPropagation();
        focusAt(0);
        break;
      case "End":
        event.preventDefault();
        event.stopPropagation();
        focusAt(itemRefs.current.length - 1);
        break;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        close(true);
        break;
      case "Tab":
        close(false);
        break;
    }
  };

  const onTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (
      event.key === "ArrowDown" ||
      event.key === "Enter" ||
      event.key === " "
    ) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(true);
    }
  };

  return (
    <div ref={rootRef} className="relative flex items-stretch">
      <button
        ref={triggerRef}
        type="button"
        data-testid={testid}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        onClick={() => (open ? close(true) : setOpen(true))}
        onKeyDown={onTriggerKeyDown}
        className={cx(
          "group/tt relative inline-flex select-none items-center gap-1.5 rounded-sm px-2.5 py-1.5",
          "transition-colors duration-fast hover:bg-carbide",
          "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
          open ? "bg-carbide text-mist" : "text-mist",
        )}
      >
        <span className="flex shrink-0 items-center">{icon}</span>
        <span className="font-display text-2xs uppercase tracking-[0.12em]">
          {label}
        </span>
        <span
          aria-hidden
          className={cx(
            "flex shrink-0 items-center text-gauge motion-safe:transition-transform motion-safe:duration-fast",
            open && "rotate-180",
          )}
        >
          <CaretDownIcon size={12} />
        </span>
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
          className="absolute left-0 top-full z-40 mt-1 min-w-[13rem] border border-hairline bg-anvil py-1 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
        >
          {eyebrow ? (
            <div className="border-b border-hairline px-3 pb-1.5 pt-1 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
              {eyebrow}
            </div>
          ) : null}
          {items.map((item, index) => (
            <button
              key={item.key}
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              type="button"
              role="menuitem"
              tabIndex={-1}
              disabled={item.disabled}
              data-testid={item["data-testid"]}
              aria-label={item["aria-label"] ?? item.label}
              onClick={() => {
                item.onSelect();
                close(true);
              }}
              className={cx(
                "flex w-full select-none items-center gap-2.5 px-3 py-1.5 text-left",
                "text-mist transition-colors duration-fast hover:bg-carbide",
                "focus-visible:bg-carbide focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
                "disabled:opacity-40 disabled:pointer-events-none",
              )}
            >
              <span className="flex w-4 shrink-0 items-center justify-center text-gauge">
                {item.icon}
              </span>
              <span className="grow font-body text-xs">{item.label}</span>
              {item.shortcut ? <Kbd>{item.shortcut}</Kbd> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
