import { formatChord, Kbd } from "@loft/design";
import { useCallback, useEffect, useRef, useState } from "react";

import { BUILD_SHA, buildLabel } from "../lib/build";
import { isTypingTarget } from "../lib/isTypingTarget";
import {
  KEY_SHORTCUT_SHEET,
  type ShortcutGroup,
  shortcutGroups,
} from "../shortcuts/registry";

/**
 * THE KEY CARD — the keyboard reference `?` opens (UI-REVIEW 2026-07-30 F4).
 *
 * FORM. Not a modal with a drop shadow and a rounded card, which is what a web
 * app reaches for. A machinist's KEY CARD: the folded reference that gets taped
 * inside a machine's door — ruled columns, a stamped header band, everything in
 * the tracked display face the title blocks already use, on the same anvil
 * ground as every panel in the product. It is the register's own language at a
 * different scale, so it reads as part of the instrument rather than as a
 * dialog that arrived from a component library. The one accent is the `Kbd`
 * chip's brass, which is where it already is everywhere else.
 *
 * CONTENT. Every row comes from `shortcuts/registry`, which is the source the
 * HANDLERS read — see that module for why a hand-typed sheet was not an option
 * (it is this repo's "gate that cannot fail" defect wearing a help panel). This
 * component decides nothing about what the keys are; it only draws them.
 *
 * BEHAVIOUR. `?` opens from anywhere (not while typing), Esc closes, focus moves
 * to the sheet on open and returns to whatever had it on close. The backdrop is
 * a plain scrim, not a blur — a blur over a 3-D viewport costs a full-screen
 * filter every frame for decoration.
 */

/** Global `?` handler + the sheet. Mounted once, inside the authed layout. */
export function ShortcutSheetHost() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      // `?` arrives WITH shift held on every layout that has it, so the shift
      // is part of the glyph rather than a modifier to test for.
      if (event.key !== KEY_SHORTCUT_SHEET) return;
      event.preventDefault();
      setOpen((current) => !current);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  if (!open) return null;
  return <ShortcutSheet onClose={() => setOpen(false)} />;
}

export function ShortcutSheet({ onClose }: { onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusTo = useRef<Element | null>(null);

  useEffect(() => {
    returnFocusTo.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement) target.focus();
    };
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    },
    [onClose],
  );

  const groups = shortcutGroups();

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-carbide/85 p-4 sm:p-8"
      data-testid="shortcut-sheet-backdrop"
      // A click on the ground closes, the way tapping outside a card does; the
      // sheet itself stops the event so a click on a row never dismisses.
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-sheet-title"
        tabIndex={-1}
        data-testid="shortcut-sheet"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
        className="my-auto w-full max-w-4xl border border-hairline bg-anvil text-mist outline-none"
      >
        {/* The stamped header band — the title block's own grammar. */}
        <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-hairline bg-carbide px-4 py-3">
          <h2
            id="shortcut-sheet-title"
            className="font-display text-2xs uppercase tracking-[0.2em] text-gauge"
          >
            Key card
          </h2>
          <p className="font-body text-sm text-mist">
            Every shortcut the app is listening for, right now.
          </p>
          <span className="grow" />
          <button
            type="button"
            onClick={onClose}
            data-testid="shortcut-sheet-close"
            className="inline-flex min-h-target-dense items-center gap-2 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none transition-colors duration-fast hover:text-brass focus-visible:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
          >
            Close
            <Kbd aria-hidden="true">Esc</Kbd>
          </button>
        </header>

        {/* CSS multi-column, not a grid: the six blocks are wildly different
            heights (four view snaps against twelve constraint verbs), and a
            grid leaves the short column's remaining space empty while the tall
            one runs off the bottom of the frame. Columns FLOW, so the card
            packs and fits — `break-inside-avoid` on each section keeps a block
            whole. */}
        <div className="columns-1 gap-x-8 px-4 py-4 sm:columns-2 lg:columns-3">
          {groups.map((group) => (
            <Group key={group.title} group={group} />
          ))}
        </div>

        {/* WHICH BUILD IS THIS (FB-11). Here rather than in the app chrome
            because the viewport is the hero and a permanent version stamp is
            chrome that earns nothing 99% of the time — but the key card is
            already mounted on every authed surface and is one keystroke (`?`)
            away, so the answer is always reachable without taking a pixel from
            the model. Selectable, monospace: it exists to be read out or pasted
            into a bug report. */}
        <footer className="border-t border-hairline px-4 py-2">
          <p
            data-testid="build-stamp"
            data-build-sha={BUILD_SHA}
            className="select-text font-data text-2xs text-gauge"
          >
            Build {buildLabel()}
          </p>
        </footer>
      </div>
    </div>
  );
}

/** One ruled block: a stamped heading, an optional condition, then the rows. */
function Group({ group }: { group: ShortcutGroup }) {
  return (
    <section
      className="mb-5 break-inside-avoid"
      data-testid="shortcut-group"
      data-group={group.title}
    >
      <h3 className="flex items-center gap-2 font-display text-2xs uppercase tracking-[0.2em] text-brass">
        {group.title}
        {/* The rule runs out to the column edge — a title-block field, not an
            underlined heading. */}
        <span className="h-px grow bg-etch" aria-hidden="true" />
      </h3>
      {group.note === null ? null : (
        <p className="mt-1 font-body text-xs text-gauge">{group.note}</p>
      )}
      <dl className="mt-2">
        {group.shortcuts.map((shortcut) => (
          <div
            key={`${shortcut.keys}-${shortcut.action}`}
            className="flex items-baseline gap-2 border-b border-hairline/40 py-1 last:border-b-0"
            data-testid="shortcut-row"
          >
            <dt className="w-[5.5rem] shrink-0">
              <Kbd>{formatChord(shortcut.keys)}</Kbd>
            </dt>
            <dd className="min-w-0 font-body text-xs text-mist">
              {shortcut.action}
              {shortcut.when === undefined ? null : (
                <span className="text-gauge"> — {shortcut.when}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
