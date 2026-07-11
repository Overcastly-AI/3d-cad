import type { SelectHTMLAttributes } from "react";
import { useId } from "react";

import { cx } from "../cx";

export interface SelectFieldOption {
  value: string;
  label: string;
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
}

/**
 * A ruled select cell — the same title-block anatomy as NumberField/TextField
 * (label over a carbide inset cell, brass focus, flag on error) for choosing
 * one of a small set. Lives in the design system so app code never restyles a
 * raw <select>.
 */
export function SelectField({
  label,
  options,
  error,
  className,
  ...rest
}: SelectFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const invalid = Boolean(error);
  return (
    <div className={cx("flex flex-col gap-0.5", className)}>
      <label htmlFor={id} className="font-body text-xs text-gauge">
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
}
