/**
 * Flyout — a grouped dropdown menu (Fusion's "gallery under a group"), drawn
 * in the machine-shop idiom: a square-cornered anvil card with hairline rules,
 * scribed icons, and an engraved `Kbd` accelerator on every row. Fully
 * keyboard-navigable (roving focus, Home/End, Escape returns focus to the
 * trigger) so the discoverable surface never costs a power user their hands.
 *
 * Items are a prop (not children) so the menu owns focus management: it can
 * reach every row's button ref for arrow navigation without a context dance.
 *
 * A row may also declare AVAILABILITY (`available` + `requires`), which turns
 * the menu from a list of what exists into a list of what is possible right
 * now: a live row's glyph lights, and a row that cannot act says what it needs
 * instead. That is the half a selection-driven offer surface structurally
 * cannot cover — an offer only appears once you already hold the right
 * selection, so it can propose a verb but can never teach you to reach one.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { cx } from "../cx";
import { CaretDownIcon } from "./icons";
import { Kbd, ToolStamp } from "./ToolButton";
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
  /**
   * Whether the CURRENT context (a selection, a mode) makes this row's verb do
   * something. `undefined` opts the row out of availability entirely — every
   * caller that predates this reads as an ordinary row, unchanged.
   *
   * NOT the same as {@link disabled}: an unavailable row is still clickable, on
   * purpose. Disabling it would answer a user who reached for the verb with
   * nothing at all, which is the dead end the row is here to remove; clicking
   * runs the verb and lets IT say what it needs, in its own words.
   */
  available?: boolean;
  /**
   * What the row needs before it can act ("2 lines", "point + line"), shown
   * ONLY while `available === false`. A noun phrase, not a sentence: this is
   * the pick SHAPE, which is the one thing a user cannot deduce from a verb's
   * name, and the vocabulary a CAD user already reads at a glance.
   */
  requires?: string;
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
 *
 * **The trigger label is part of the band's MEASURED label tier** — the same
 * `data-labels` mechanism `ToolButton` honours, so one `CommandBand` probe
 * governs every control on the row. It did not used to be, and that gap was
 * QA-R1: `Flyout` is the only labelled control on the sketch strip (every
 * `ToolButton` there is icon-only), so shedding "labels" saved the band 0 px
 * and the strip ran 139.4 px past a 1280 px window with the sketch's own
 * FINISH/CANCEL outside the frame and unclickable. A primitive that opts out
 * of the layout contract its peers keep does not fail loudly; it fails as a
 * surface that cannot shrink.
 *
 * Shed, the trigger keeps its icon and caret and gains the `ToolStamp` its
 * peers have always had, so a label-less trigger still names itself to the
 * pointer; `aria-label` carries the name for assistive tech either way.
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
          "group/tt relative inline-flex select-none items-center gap-1.5 rounded-sm py-1.5",
          // Same ≥32px target and the same padding step as `ToolButton` takes
          // when its enclosing group sheds — one band row, one hover geometry.
          "min-h-8 px-2.5 [[data-labels=off]_&]:px-1.5",
          "transition-colors duration-fast hover:bg-carbide",
          "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
          open ? "bg-carbide text-mist" : "text-mist",
        )}
      >
        <span className="flex shrink-0 items-center">{icon}</span>
        <span className="font-display text-2xs uppercase tracking-[0.12em] [[data-labels=off]_&]:hidden">
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
        {/* Not while the menu is down: the stamp and the menu occupy the same
            strip of viewport, and a tooltip over an open menu is noise. */}
        {open ? null : <ToolStamp label={label} />}
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
          // 15rem, not 13: a row that declares what it `requires` carries a
          // second line, and at 13rem the commonest shapes ("a circle/arc",
          // "2 non-parallel lines") wrapped — a menu of ragged two-line rows
          // reads as prose, which is the opposite of the instrument this is.
          className="absolute left-0 top-full z-40 mt-1 min-w-[15rem] border border-hairline bg-anvil py-1 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
        >
          {eyebrow ? (
            <div className="border-b border-hairline px-3 pb-1.5 pt-1 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
              {eyebrow}
            </div>
          ) : null}
          {items.map((item, index) => {
            // An unavailable row shows what it needs; a live one shows nothing
            // extra, because the answer to "can I use this?" is then just yes.
            const unmet = item.available === false ? item.requires : undefined;
            const name = item["aria-label"] ?? item.label;
            return (
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
                // The requirement rides the ACCESSIBLE NAME, not just the ink.
                // Availability is signalled visually by the glyph going brass,
                // and colour alone is never a channel (WCAG 1.4.1) — a screen
                // reader gets the same fact in words, and `aria-label` would
                // otherwise hide the visible line entirely.
                aria-label={
                  unmet === undefined ? name : `${name} — needs ${unmet}`
                }
                data-available={
                  item.available === undefined
                    ? undefined
                    : String(item.available)
                }
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
                <span
                  className={cx(
                    "flex w-4 shrink-0 items-center justify-center",
                    // The glyph IS the verb, so a live verb's glyph lights —
                    // the icon set's own rule that the active state flows from
                    // the row's colour, spent here rather than on a new badge.
                    item.available === true ? "text-brass" : "text-gauge",
                  )}
                >
                  {item.icon}
                </span>
                <span className="grow font-body text-xs">
                  {item.label}
                  {unmet === undefined ? null : (
                    <span
                      aria-hidden
                      className="mt-0.5 block font-data text-2xs leading-none text-gauge"
                    >
                      needs {unmet}
                    </span>
                  )}
                </span>
                {item.shortcut ? <Kbd>{item.shortcut}</Kbd> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
