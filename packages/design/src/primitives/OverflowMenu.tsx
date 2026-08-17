/**
 * OVERFLOW MENU — one quiet mark that holds a row's verbs.
 *
 * Why it exists (REGISTER-1, UI-REVIEW 2026-08-17 P1-2): a table that prints
 * RENAME / DUPLICATE / MOVE / DELETE on every row spends its widest column —
 * measured 256 px of 957 at 1280, 1.5x the NAME column — on repeating four words
 * the user reads once, and it puts the destructive one at the same weight as the
 * rest. Collapsing them costs one click on a verb nobody uses per session and
 * buys the identifying column back, which is the whole trade.
 *
 * It is a TRIGGER, not a new menu: the card is `ContextMenu`, unchanged, so a
 * row's verbs and the viewport's right-click read identically (one menu in the
 * product, one set of keyboard rules — roving focus, Home/End, Escape returns
 * focus to the trigger, gated rows explain themselves). The only thing added
 * here is the anchor: the card is right-aligned to the trigger, because the
 * trigger sits at the right edge of its row and a menu hanging further right
 * would leave the frame it belongs to.
 *
 * The mark is `MoreIcon` — three of the scribe's punch marks. Not a vertical
 * "kebab": the register's own rules and gutters are horizontal, and three marks
 * on a line read as "the row continues" rather than as an app-bar affordance.
 */
import { useCallback, useRef, useState } from "react";

import { cx } from "../cx";
import { ContextMenu, MENU_MIN_WIDTH } from "./ContextMenu";
import { MoreIcon } from "./icons";
import type { ContextMenuSection } from "./ContextMenu";

export interface OverflowMenuProps {
  /**
   * The accessible name of the trigger AND of the menu it opens — say what the
   * verbs act on ("Actions for Bracket plate"), never a bare "More": a row of
   * identical "More" buttons is a screen-reader list of nothing.
   */
  label: string;
  sections: readonly ContextMenuSection[];
  /** Test hook for the trigger; the card gets `${testid}-menu`. */
  "data-testid"?: string;
  /** Extra ink for the trigger (the row supplies its resting colour). */
  className?: string;
}

export function OverflowMenu({
  label,
  sections,
  "data-testid": testid,
  className,
}: OverflowMenuProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const close = useCallback(() => setAnchor(null), []);

  const open = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect === undefined) return;
    // RIGHT-ALIGNED to the trigger. The card's width is its `min-w` unless a
    // label overruns it, and `ContextMenu` clamps anything that would fall off
    // the window, so this is a starting point the layout pass can correct — not
    // a size assumption that can be wrong on screen.
    setAnchor({ x: rect.right - MENU_MIN_WIDTH, y: rect.bottom + 2 });
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={anchor !== null}
        aria-label={label}
        data-testid={testid}
        onClick={() => (anchor === null ? open() : close())}
        className={cx(
          "inline-flex min-h-target-dense min-w-target-dense items-center justify-center rounded-sm",
          "outline-none transition-colors duration-fast",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass",
          anchor === null ? "text-gauge" : "text-brass",
          "hover:text-brass",
          className,
        )}
      >
        <MoreIcon size={16} />
      </button>
      <ContextMenu
        open={anchor !== null}
        x={anchor?.x ?? 0}
        y={anchor?.y ?? 0}
        sections={sections}
        onClose={close}
        aria-label={label}
        {...(testid === undefined ? {} : { "data-testid": `${testid}-menu` })}
      />
    </>
  );
}
