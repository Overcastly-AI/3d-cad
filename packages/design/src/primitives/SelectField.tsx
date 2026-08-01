import type { SelectHTMLAttributes } from "react";
import { forwardRef, useId } from "react";

import { cx } from "../cx";

export interface SelectFieldOption {
  value: string;
  label: string;
  /**
   * Displayed but not choosable — a guard entry (e.g. an unresolvable stored
   * reference) the select can SHOW without letting the user re-pick it.
   */
  disabled?: boolean;
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
}

/**
 * A ruled select cell — the same title-block anatomy as NumberField/TextField
 * (label over a carbide inset cell, brass focus, flag on error) for choosing
 * one of a small set. Lives in the design system so app code never restyles a
 * raw <select>.
 */
export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(
  function SelectField(
    { label, options, error, className, hideLabel = false, ...rest },
    ref,
  ) {
    const id = useId();
    const errorId = `${id}-error`;
    const invalid = Boolean(error);
    return (
      <div className={cx("flex flex-col gap-0.5", className)}>
        <label
          htmlFor={id}
          className={cx("font-body text-xs text-gauge", hideLabel && "sr-only")}
        >
          {label}
        </label>
        <div
          className={cx(
            "flex items-center rounded-sm border bg-carbide px-2 py-1",
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
            {options.map((option) => (
              <option
                key={option.value}
                value={option.value}
                disabled={option.disabled}
                className="bg-anvil"
              >
                {option.label}
              </option>
            ))}
          </select>
        </div>
        {invalid ? (
          <p id={errorId} className="font-body text-xs text-flag" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
