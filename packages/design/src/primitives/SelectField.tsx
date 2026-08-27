import type { SelectHTMLAttributes } from "react";
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
          "flex w-full items-center rounded-sm border bg-carbide px-2 py-1",
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
          className="w-full min-w-0 cursor-pointer bg-transparent font-data text-md text-mist outline-none"
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
