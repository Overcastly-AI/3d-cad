/**
 * FieldRow — the DENSE field cell: caption BESIDE its control, not above it,
 * and helper prose behind an affordance instead of permanently resident.
 *
 * The founder's report (FB-19, 2026-08-01) was that EDIT EXTRUDE spends six
 * full-width rows on five short values, every label stacked over its control,
 * plus a helper sentence that is always on screen. The fix is not a tighter
 * gap; it is the wrong anatomy. A drawing's title block prints a small caption
 * in the corner of a ruled cell with the value beside it, and `PanelRow` has
 * drawn READ-ONLY cells that way since day one — only the EDITABLE cells were
 * still stacking, which is a whole line of leading per parameter on a form that
 * is almost entirely two-digit numbers.
 *
 * So this is `PanelRow`'s anatomy made writable, and it lives here rather than
 * in an editor so the idiom is ONE decision: the field primitives
 * (`NumberField`, `SelectField`) take `layout="inline"` and route their label
 * through this. App code never lays out a label by hand.
 *
 *   ┌──────────────────────────────────────┐
 *   │ Distance   │ 10                mm    │   ← one row, min 24px (SC 2.5.8)
 *   ├──────────────────────────────────────┤
 *   │ Profile    │ Sketch 1                │
 *   ├──────────────────────────────────────┤
 *   │ [⊕ ADD│⊖ CUT] [→ NORM│← REV]      ⓘ │   ← label-less, full-bleed
 *   └──────────────────────────────────────┘
 *
 * `stacked` stays the default on the field primitives: twelve editors compose
 * them and a silent global reflow is not a density pass, it is a regression
 * waiting to be photographed. The idiom is opt-in per editor.
 *
 * THE NOTE RULE, which is the part worth reading. A row may hide an
 * EXPLANATION; it may never hide a WARNING. `noteTone="flag"` therefore drops
 * the toggle and pins the note open in flag ink — the same principle
 * `Disclosure` states for collapsed sections ("a section is allowed to hide
 * controls; it is not allowed to hide an error"). Encoded here rather than
 * left to each caller, because "remember to keep the bad case visible" is
 * exactly the rule that erodes.
 */
import { useId, useState, type ReactNode } from "react";

import { cx } from "../cx";
import { NoteIcon } from "./icons";

// NB every optional below spells `| undefined`: this package runs
// `exactOptionalPropertyTypes`, and the field primitives forward their own
// optionals straight through, so an implicit-undefined optional here would not
// accept them.
export interface FieldRowProps {
  /**
   * The caption, e.g. "Distance". OMIT it for a full-bleed row whose controls
   * name themselves (two `hideLabel` segmented toggles sharing one row): the
   * caption column is then not rendered at all rather than left empty, which is
   * what buys those controls the width to hold their labels.
   */
  label?: string | undefined;
  /**
   * The control's id when the control is a labelable element (`input`,
   * `select`): renders a real `<label for>`. Omit for a control that is a
   * `role="group"` of buttons and pass `labelId` instead, pointing the group's
   * `aria-labelledby` at it.
   */
  htmlFor?: string | undefined;
  /** Id stamped on the caption when it labels a group rather than an input. */
  labelId?: string | undefined;
  /**
   * Validation message for the control, rendered under it. The caller wires it
   * to the control through `aria-describedby` using `errorId`.
   */
  error?: string | null | undefined;
  errorId?: string | undefined;
  /**
   * Helper prose about this row. Collapsed behind a note affordance by default
   * (FB-19: it was permanently resident and cost a row on every form) — see the
   * note rule above for why `noteTone="flag"` overrides that.
   */
  note?: ReactNode | undefined;
  /** Accessible name of the note toggle, e.g. "About the sweep direction". */
  noteLabel?: string | undefined;
  /** `flag` pins the note OPEN in flag ink — a warning is never behind a click. */
  noteTone?: "quiet" | "flag" | undefined;
  /** Test hook on the NOTE text (the toggle gets `${noteTestId}-toggle`). */
  noteTestId?: string | undefined;
  children: ReactNode;
  className?: string | undefined;
  "data-testid"?: string | undefined;
}

/** The caption column: a token width, never a guessed one (`layout.fieldLabelWidth`). */
const CAPTION = "w-field-label shrink-0 font-body text-xs text-gauge";

export function FieldRow({
  label,
  htmlFor,
  labelId,
  error,
  errorId,
  note,
  noteLabel,
  noteTone = "quiet",
  noteTestId,
  children,
  className,
  ...rest
}: FieldRowProps) {
  const generatedId = useId();
  const noteId = `${generatedId}-note`;
  const [open, setOpen] = useState(false);
  const warns = noteTone === "flag";
  const showNote = note !== undefined && (warns || open);
  return (
    <div className={cx("px-3 py-1", className)} {...rest}>
      <div className="flex min-h-target-dense items-center gap-2">
        {label !== undefined ? (
          htmlFor !== undefined ? (
            <label htmlFor={htmlFor} id={labelId} className={CAPTION}>
              {label}
            </label>
          ) : (
            <span id={labelId} className={CAPTION}>
              {label}
            </span>
          )
        ) : null}
        <div className="flex min-w-0 grow items-center gap-2">{children}</div>
        {note !== undefined && !warns ? (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={noteId}
            aria-label={noteLabel ?? "Show note"}
            title={noteLabel ?? "Show note"}
            data-testid={
              noteTestId === undefined ? undefined : `${noteTestId}-toggle`
            }
            onClick={() => setOpen((current) => !current)}
            className={cx(
              "flex min-h-target-dense min-w-target-dense shrink-0 items-center justify-center rounded-sm",
              "transition-colors duration-fast hover:text-brass",
              "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
              open ? "text-brass" : "text-gauge",
            )}
          >
            <NoteIcon size={14} />
          </button>
        ) : null}
      </div>
      {error ? (
        <p id={errorId} role="alert" className="font-body text-xs text-flag">
          {error}
        </p>
      ) : null}
      {/*
        Kept MOUNTED and `hidden` rather than unmounted: the note is the row's
        explanation of the state it is in, so it belongs to the accessible
        description whether or not it is on screen, and a test that reads it is
        asking about the state, not about the disclosure.
      */}
      {note !== undefined ? (
        <p
          id={noteId}
          hidden={!showNote}
          data-testid={noteTestId}
          className={cx(
            "font-body text-xs",
            warns ? "text-flag" : "text-gauge",
          )}
        >
          {note}
        </p>
      ) : null}
    </div>
  );
}
