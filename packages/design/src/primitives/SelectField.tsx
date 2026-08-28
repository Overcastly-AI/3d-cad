import type { ReactNode, SelectHTMLAttributes } from "react";
import { forwardRef, useId } from "react";

import { cx } from "../cx";
import { FieldRow } from "./FieldRow";

export interface SelectFieldOption {
  value: string;
  label: string;
  /**
   * Displayed but not choosable — a guard entry (e.g. an unresolvable stored
   * reference) the select can SHOW without letting the user re-pick it.
   */
  disabled?: boolean;
  /**
   * The heading this option files under. When ANY option carries one the cell
   * renders real `<optgroup>`s — the only way a select can say "these two
   * names are different KINDS of thing" to a screen reader or a keyboard user
   * as well as to an eye. Options with no group stay at the top level, above
   * the first heading, in build order.
   */
  group?: string;
}

export interface SelectFieldProps extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "id" | "children"
> {
  /** Visible cell label, e.g. "Profile". */
  label: string;
  /** Choices rendered in build order. */
  options: readonly SelectFieldOption[];
  /** Validation message; sets aria-invalid + flag styling when present. */
  error?: string | null;
  /**
   * Keep the label for assistive tech but take it off the screen. For a cell
   * whose meaning is already given by its surroundings (a folder picker inside
   * a row that names the document it is filing) — the label is still REQUIRED,
   * because a select with no accessible name is unusable by anyone not looking
   * at it.
   */
  hideLabel?: boolean;
  /**
   * `inline` sets the caption BESIDE the cell instead of above it (`FieldRow`)
   * — the dense title-block anatomy (FB-19). Ignored when `hideLabel` is set:
   * a hidden caption has no column to sit in.
   */
  layout?: "stacked" | "inline";
  /**
   * A quiet read-only reading pinned after the control on an `inline` row —
   * see `FieldRow.trailing`. Ignored by the stacked layout, which has no row to
   * pin it to.
   */
  trailing?: ReactNode;
}

/**
 * A ruled select cell — the same title-block anatomy as NumberField/TextField
 * (label over a carbide inset cell, brass focus, flag on error) for choosing
 * one of a small set. Lives in the design system so app code never restyles a
 * raw <select>.
 */
export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(
  function SelectField(
    {
      label,
      options,
      error,
      className,
      hideLabel = false,
      layout = "stacked",
      trailing,
      ...rest
    },
    ref,
  ) {
    const id = useId();
    const errorId = `${id}-error`;
    const invalid = Boolean(error);
    // Grouped rendering is opt-in per option, so an ungrouped caller emits the
    // exact markup it always did (no empty `<optgroup>` wrapper to change how
    // any assistive tech announces the cell). Headings keep first-seen order.
    const groupNames: string[] = [];
    for (const option of options) {
      if (option.group !== undefined && !groupNames.includes(option.group)) {
        groupNames.push(option.group);
      }
    }
    const ungrouped = options.filter((option) => option.group === undefined);
    const renderOption = (option: SelectFieldOption) => (
      <option
        key={option.value}
        value={option.value}
        disabled={option.disabled}
        className="bg-anvil"
      >
        {option.label}
      </option>
    );
    // One cell, two layouts — see `NumberField` for why the cell markup is
    // written once (the inset, the focus ring and the flag state cannot drift).
    const cell = (
      <div
        className={cx(
          "flex w-full items-center rounded-sm border bg-carbide px-2 py-0.5",
          "focus-within:outline focus-within:outline-2 focus-within:outline-offset-1",
          invalid
            ? "border-flag focus-within:outline-flag"
            : "border-etch focus-within:outline-brass",
        )}
      >
        <select
          ref={ref}
          id={id}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? errorId : undefined}
          // The SELECT is the target, not the cell around it — a click on the
          // wrapper's padding hits the div. It measured 276x19 on the material
          // picker (2026-08-28), i.e. under the 24px dense floor this product
          // wrote down for itself in `target` — the same defect `InlineSelect`
          // had fixed on its own copy and this one never inherited. The cell's
          // padding drops to `py-0.5` in exchange, so the floor is bought with
          // the control's own height rather than with a taller row.
          className={cx(
            "min-h-target-dense w-full min-w-0 cursor-pointer bg-transparent font-data text-mist outline-none",
            // A NATIVE `<select>` CANNOT ELLIPSIZE ITS VALUE — it hard-clips,
            // so "Steel (AISI 1018)" renders as "Steel (AISI 101" and two
            // different alloys become the same string on screen. That makes the
            // select the one control in the row that must never be the thing
            // giving up width, and on an `inline` row it is squeezed from both
            // sides (a 64px caption column and a trailing readout).
            //
            // Measured on the mixed-material part at 1440: 17 chars needs
            // ~177px at 14px and the row has 168px, so it clipped. At 12px it
            // needs ~156px and fits. 12px is also what every sibling readout in
            // these panels is set in, so the inline cell now agrees with its
            // neighbours instead of being the one 14px value among them.
            //
            // The STACKED layout keeps 14px: it is full-width in a feature
            // editor, has no trailing column stealing from it, and that is the
            // size twelve editors were designed and photographed at.
            layout === "inline" && !hideLabel ? "text-sm" : "text-md",
          )}
          {...rest}
        >
          {ungrouped.map(renderOption)}
          {groupNames.map((name) => (
            <optgroup key={name} label={name} className="bg-anvil">
              {options
                .filter((option) => option.group === name)
                .map(renderOption)}
            </optgroup>
          ))}
        </select>
      </div>
    );

    if (layout === "inline" && !hideLabel) {
      return (
        <FieldRow
          label={label}
          htmlFor={id}
          error={error}
          errorId={errorId}
          trailing={trailing}
          className={className}
        >
          {cell}
        </FieldRow>
      );
    }

    return (
      <div className={cx("flex flex-col gap-0.5", className)}>
        <label
          htmlFor={id}
          className={cx("font-body text-xs text-gauge", hideLabel && "sr-only")}
        >
          {label}
        </label>
        {cell}
        {invalid ? (
          <p id={errorId} className="font-body text-xs text-flag" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
