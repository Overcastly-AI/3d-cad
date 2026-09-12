import { cx, Kbd } from "@loft/design";
import { useCallback, useEffect, useRef } from "react";
import type { ReactNode, Ref } from "react";

import { useModalLayer } from "../lib/modalGate";

/**
 * THE EXIT TICKET — what the three ordinary exits say now (FLOW-A2).
 *
 * AUDIT-FLOW-2026-09 A2 found the browser Back button, the in-app breadcrumb
 * and a page reload each destroying a four-entity, nine-constraint sketch with
 * no prompt and no recovery. The mandate's rule is "no dead ends, no ambiguous
 * exits", and its worked example (FB-13) is a key that sometimes saves and
 * sometimes discards. An OK/Cancel box over "You have unsaved changes" is that
 * same defect in a new costume: two words, neither of which says what happens.
 *
 * ## The design, and what it deliberately is not
 *
 * NOT a button bar. A row of verbs at the bottom-right of a card is the shape
 * every web app uses, and it puts the consequence of each choice nowhere — you
 * learn what "Don't Save" did afterwards. Here the exits are a LADDER: one
 * full-width row each, in descending consequence, verb on the left and what it
 * does written beside it in the same breath. The reading order IS the decision
 * order, and no row can be chosen without its consequence having been on screen.
 *
 * THE SIGNATURE is the manifest — the work at stake, counted, in the numeral
 * face the inspector uses for real measurements. The dialog SHOWS your sketch
 * rather than describing it, and those two numbers are the only place boldness
 * is spent: everything else is the same quiet title-block grammar as the rest
 * of the chrome (stamped tracked caps, hairline rules, one brass action).
 * Both numbers are derived from the live buffer — nothing here decorates
 * (mandate 3a).
 *
 * ## Why the middle rung is not frightening
 *
 * Because it is not destructive any more. `sketchDraft.ts` keeps the buffer per
 * part, so leaving without saving really does hand the entities back on
 * re-entry, and the row says exactly that. The distinction the copy has to
 * carry is therefore not saved-vs-lost but IN THE PART (server, shared,
 * versioned) vs IN THIS BROWSER (a draft, private, only here) — which is true,
 * checkable, and the actual reason to prefer the top rung.
 */
export interface LeaveSketchPromptProps {
  /** The part's name — what "in the part" means, said by name. */
  partName: string;
  /** Where the blocked navigation was heading, in the user's words. */
  destination: string;
  entityCount: number;
  constraintCount: number;
  /**
   * Is the browser actually holding a draft of this buffer? False when the
   * write was refused (quota, private mode) — the middle rung then stops
   * promising a rescue it cannot deliver.
   */
  draftHeld: boolean;
  /** A save is in flight (the top rung was taken). */
  saving: boolean;
  /** The last save failure, if the top rung has already been tried. */
  error: string | null;
  onSaveAndLeave: () => void;
  onLeave: () => void;
  onStay: () => void;
}

export function LeaveSketchPrompt({
  partName,
  destination,
  entityCount,
  constraintCount,
  draftHeld,
  saving,
  error,
  onSaveAndLeave,
  onLeave,
  onStay,
}: LeaveSketchPromptProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const returnFocusTo = useRef<Element | null>(null);

  useEffect(() => {
    returnFocusTo.current = document.activeElement;
    // The recommended rung takes focus, so Enter does the safe, complete thing
    // and Escape still stays. Focusing the panel instead would make the
    // keyboard user tab before they can act on a dialog they did not open.
    primaryRef.current?.focus();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement) target.focus();
    };
  }, []);

  /**
   * A modal that blocks a navigation has to hold focus, or Tab walks into the
   * page behind it and the user is operating a workspace they have just been
   * told they are leaving. Three buttons, so the trap is the two boundaries.
   *
   * THE KEYS ARRIVE FROM THE MODAL GATE, NOT FROM REACT'S onKeyDown, and that
   * is the fix for W0 review finding 1 rather than a refactor. A React handler
   * on the panel sees a key only after it has already passed every window
   * listener in the workspace — `SketchScene`'s draw-dimension Enter and
   * `SketchStrip`'s Ctrl+Z among them — so with the dimension strip armed
   * behind the dialog, Enter on the focused save rung applied the dimension and
   * `preventDefault()`ed the button's own activation. `lib/modalGate.ts` stops
   * every keystroke at the window capture phase and hands it here, so this
   * handler is the only code in the app that can act on a key while the prompt
   * is open.
   *
   * `insidePanel` is false when focus has escaped the dialog. That is not
   * hypothetical (finding 2), so a stray key is spent putting focus back rather
   * than reaching a workspace the user is halfway out of.
   */
  const onKeyDown = useCallback(
    (event: KeyboardEvent, insidePanel: boolean) => {
      const focusable = Array.from(
        panelRef.current?.querySelectorAll<HTMLButtonElement>(
          "button:not([disabled])",
        ) ?? [],
      );
      if (event.key === "Escape") {
        event.preventDefault();
        onStay();
        return;
      }
      if (!insidePanel) {
        event.preventDefault();
        focusable[0]?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first?.focus();
      }
    },
    [onStay],
  );

  useModalLayer("the exit ticket", panelRef, onKeyDown);

  return (
    <div
      data-testid="leave-sketch-backdrop"
      onClick={onStay}
      className="fixed inset-0 z-menu flex items-center justify-center bg-carbide/85 p-4"
    >
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="leave-sketch-title"
        aria-describedby="leave-sketch-body"
        tabIndex={-1}
        data-testid="leave-sketch-prompt"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-xl border border-etch bg-anvil text-mist shadow-float outline-none"
      >
        {/* The stamped header band — the title block's own grammar, and the
            one place the DESTINATION is named. "Back" is the exit people press
            without knowing where it goes; this says. */}
        <header className="flex items-baseline gap-x-4 border-b border-hairline bg-carbide px-4 py-2.5">
          <h2
            id="leave-sketch-title"
            className="font-display text-2xs uppercase tracking-[0.2em] text-gauge"
          >
            Leaving the sketch
          </h2>
          <span className="grow" />
          <span
            data-testid="leave-sketch-destination"
            className="min-w-0 truncate font-display text-2xs uppercase tracking-[0.16em] text-gauge"
          >
            <span aria-hidden className="pr-1.5 text-etch">
              ›
            </span>
            {destination}
          </span>
        </header>

        {/* THE MANIFEST — the work at stake, counted. */}
        <div className="flex items-end gap-8 px-4 pt-4">
          <Tally
            value={entityCount}
            label={entityCount === 1 ? "entity" : "entities"}
            testId="leave-sketch-entities"
          />
          <Tally
            value={constraintCount}
            label={constraintCount === 1 ? "constraint" : "constraints"}
            testId="leave-sketch-constraints"
          />
        </div>

        <p
          id="leave-sketch-body"
          className="px-4 pt-3 font-body text-sm text-mist"
        >
          None of it is in{" "}
          <span className="font-data text-brass">{partName}</span> yet.
        </p>

        {error !== null ? (
          <p
            role="alert"
            data-testid="leave-sketch-error"
            className="mx-4 mt-3 border border-flag px-3 py-2 font-body text-xs text-flag"
          >
            {error} Your work is still here — leave without saving to keep it as
            a draft.
          </p>
        ) : null}

        {/* THE LADDER — one rung per exit, consequence beside the verb. */}
        <div className="mt-4 border-t border-hairline">
          <Rung
            ref={primaryRef}
            primary
            verb={saving ? "Saving…" : "Save sketch, then leave"}
            consequence={`adds ${entityCount === 1 ? "it" : "them"} to ${partName}, then goes to ${destination}`}
            testId="leave-sketch-save"
            disabled={saving}
            onClick={onSaveAndLeave}
          />
          <Rung
            verb={draftHeld ? "Leave without saving" : "Leave and lose them"}
            consequence={
              draftHeld
                ? "kept as a draft in this browser — restored when you reopen this part"
                : "this browser refused to keep a draft, so these entities are gone for good"
            }
            testId="leave-sketch-leave"
            tone={draftHeld ? "normal" : "warn"}
            disabled={saving}
            onClick={onLeave}
          />
          <Rung
            verb="Stay in the sketch"
            consequence="nothing changes"
            testId="leave-sketch-stay"
            trailing={<Kbd aria-hidden="true">Esc</Kbd>}
            onClick={onStay}
          />
        </div>
      </div>
    </div>
  );
}

/** One counted thing — the numeral carries the weight, the label whispers. */
function Tally({
  value,
  label,
  testId,
}: {
  value: number;
  label: string;
  testId: string;
}) {
  return (
    <span className="flex items-baseline gap-2">
      <span
        data-testid={testId}
        className="font-data text-xl leading-none text-brass"
      >
        {value}
      </span>
      <span className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
        {label}
      </span>
    </span>
  );
}

/**
 * One exit, and what it does. Full width because the consequence has to fit on
 * the same line as the verb — the moment it wraps to a tooltip it stops being
 * read, which is how an ambiguous exit is built.
 */
function Rung({
  ref,
  verb,
  consequence,
  testId,
  primary = false,
  tone = "normal",
  disabled = false,
  trailing,
  onClick,
}: {
  ref?: Ref<HTMLButtonElement>;
  verb: string;
  consequence: string;
  testId: string;
  primary?: boolean;
  tone?: "normal" | "warn";
  disabled?: boolean;
  trailing?: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      ref={ref}
      type="button"
      data-testid={testId}
      // `aria-disabled`, NOT `disabled` — W0 review finding 2. Disabling the
      // element that HAS focus blurs it to `document.body`, and the save rung is
      // the focused one the instant a save starts, so the dialog lost focus at
      // exactly the moment it had nothing else to offer. The wait is not short:
      // a save that is still creating the feature blocks on a whole round trip.
      // An `aria-disabled` control keeps its place in the focus order and stays
      // announced — the refusal is in the handler, not in the DOM.
      aria-disabled={disabled || undefined}
      onClick={() => {
        if (disabled) return;
        onClick();
      }}
      className={cx(
        // A GRID, not a flex row: the consequences line up in one column, so
        // the three exits read as a table of outcomes rather than three
        // sentences of different lengths. Structure carrying information is the
        // point — the column IS the comparison the user is making.
        "group grid min-h-target w-full grid-cols-[minmax(0,10rem)_1fr_auto] items-baseline gap-x-4",
        "border-b border-hairline px-4 py-3 text-left",
        "outline-none motion-safe:transition-colors motion-safe:duration-fast",
        "last:border-b-0 hover:bg-carbide focus-visible:bg-carbide",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        "aria-disabled:opacity-50",
      )}
    >
      <span
        className={cx(
          "min-w-0 font-body text-sm font-medium",
          tone === "warn" ? "text-flag" : primary ? "text-brass" : "text-mist",
        )}
      >
        {verb}
      </span>
      <span
        className={cx(
          "min-w-0 font-body text-xs",
          tone === "warn" ? "text-flag" : "text-gauge",
        )}
      >
        {consequence}
      </span>
      {trailing}
    </button>
  );
}
