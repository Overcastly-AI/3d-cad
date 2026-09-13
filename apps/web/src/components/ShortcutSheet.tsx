import { formatChord, Kbd } from "@loft/design";
import { useCallback, useEffect, useRef, useState } from "react";

import { BUILD_SHA, buildLabel } from "../lib/build";
import { useGlobalKeys, useModalLayer } from "../lib/modalGate";
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
 *
 * AND IT HOLDS THE KEYBOARD (W2 review, blocking finding). It always SAID it
 * did — `aria-modal="true"` promises a screen-reader user that everything
 * outside is inert — while every workspace shortcut stayed live behind it. The
 * path is the card's own: read the row that says `E — Extrude`, press `E`, and
 * the Extrude editor opened BEHIND the sheet; `Enter` on this sheet's own Close
 * button did the same, because a `<button>` is not a typing target and the
 * ambient proposal note's window listener guarded on nothing else. So the sheet
 * registers a layer in `lib/modalGate.ts` and its keys arrive from there rather
 * than from a React `onKeyDown` — which could only ever see a key that had
 * already passed every window listener in the app.
 */

/** Global `?` handler + the sheet. Mounted once, inside the authed layout. */
export function ShortcutSheetHost() {
  const [open, setOpen] = useState(false);

  // The typing-target bail comes from the seam, not from a copy of it here.
  // While the sheet is OPEN this listener is shielded by the gate and never
  // runs — closing on a second `?` is the layer's job, below.
  useGlobalKeys(
    "the key card",
    useCallback((event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      // `?` arrives WITH shift held on every layout that has it, so the shift
      // is part of the glyph rather than a modifier to test for.
      if (event.key !== KEY_SHORTCUT_SHEET) return;
      event.preventDefault();
      setOpen((current) => !current);
    }, []),
  );

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

  /**
   * THE KEYS, FROM THE GATE. While this layer is open nothing else in the app
   * can act on a keystroke, so this handler is the whole keyboard:
   *
   *  · `Esc` closes, as it always did;
   *  · `?` closes too — it is the key that opened the card, and the host's
   *    toggle is shielded while the card is up, so without this row the card's
   *    own key would stop working the moment it was showing;
   *  · a key arriving from OUTSIDE the panel spends itself putting focus back,
   *    rather than leaking into a workspace the user cannot see. Tab is exempt,
   *    because Tab is how a reader walks the card.
   */
  const onKeyDown = useCallback(
    (event: KeyboardEvent, insidePanel: boolean) => {
      if (event.key === "Escape" || event.key === KEY_SHORTCUT_SHEET) {
        event.preventDefault();
        onClose();
        return;
      }
      if (!insidePanel && event.key !== "Tab") {
        event.preventDefault();
        panelRef.current?.focus();
      }
    },
    [onClose],
  );

  useModalLayer("the key card", panelRef, onKeyDown);

  const groups = shortcutGroups();

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-carbide/85 p-4 sm:p-6"
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
        className="my-auto w-full max-w-6xl border border-hairline bg-anvil text-mist outline-none"
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

        {/* CSS multi-column, not a grid: the seven blocks are wildly different
            heights (two reorder keys against sixteen modelling verbs), and a
            grid leaves the short column's remaining space empty while the tall
            one runs off the bottom of the frame. Columns FLOW, so the card
            packs and fits — `break-inside-avoid` on each section keeps a block
            whole.

            A FOURTH COLUMN AT `xl`, with the card widened to match, is what
            keeps the card on ONE SCREEN now that MODELLING carries 16 rows
            (FLOW-B2 bound five more verbs and the card went to 1127px of
            content in a 900px frame). The column WIDTH is deliberately
            unchanged — 1152px across four columns is 262px each, against the
            266px that three columns of 896px were giving — so the extra column
            costs no extra line wrapping. The alternative, dropping rows until
            it fits, would be removing the reference from the reference. */}
        <div className="columns-1 gap-x-6 px-4 py-3 sm:columns-2 lg:columns-3 xl:columns-4">
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
      className="mb-4 break-inside-avoid"
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
      <dl className="mt-1.5">
        {group.shortcuts.map((shortcut) => (
          <div
            key={`${shortcut.keys}-${shortcut.action}`}
            className="flex items-baseline gap-2 border-b border-hairline/40 py-0.5 last:border-b-0"
            data-testid="shortcut-row"
          >
            {/* FLEX, AND THIS ONE CLASS IS THE WHOLE DENSITY PASS — 97px of the
                card, measured by reverting it on its own (804px vs 707px).
                Worth stating because it is not guessable from the markup: as a
                plain block, the `dt` laid the stamped `Kbd` chip out as an
                INLINE box, which sits on the text baseline and drags the line
                box down by the font's descent underneath it. The chip is 14px
                and the row it produced was 29px — to carry 17px of text. As a
                flex container the `dt` is exactly its chip, and the row is 22px.

                The lesson generalises past this file: a row that is 33px tall
                to hold 17px of text looks completely normal in a screenshot, so
                this was only ever findable by MEASURING the rows. The first fix
                drafted here — `items-start` on the row — addressed the visible
                half of the same effect, and a mutation test then showed it
                moved the card height by exactly zero once this class was
                present (707px either way). It was dropped rather than shipped
                as a change that would read, forever after, as load-bearing. */}
            <dt className="flex w-[5.5rem] shrink-0">
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
