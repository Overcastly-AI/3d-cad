import type { InputHTMLAttributes } from "react";
import { useId } from "react";

import { cx } from "../cx";

export interface NumberFieldProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "id"
> {
  /** Visible cell label, e.g. "X". */
  label: string;
  /** Unit suffix rendered inside the cell, e.g. "mm". */
  unit?: string;
  /** Validation message; sets aria-invalid + flag styling when present. */
  error?: string | null;
}

/**
 * Unit-aware numeric input cell (keyboard-first: decimal inputMode, all
 * styling token-driven). Lives in the design system so app code never
 * restyles a raw <input>.
 */
export function NumberField({
  label,
  unit,
  error,
  className,
  ...rest
}: NumberFieldProps) {
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
          "flex items-baseline gap-1 rounded-sm border bg-carbide px-2 py-1",
          "focus-within:outline focus-within:outline-2 focus-within:outline-offset-1",
          invalid
            ? "border-flag focus-within:outline-flag"
            : "border-etch focus-within:outline-brass",
        )}
      >
        <input
          id={id}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? errorId : undefined}
          className="w-full min-w-0 bg-transparent font-data text-md text-mist outline-none placeholder:text-gauge"
          {...rest}
        />
        {unit ? (
          <span className="font-body text-xs text-gauge select-none">
            {unit}
          </span>
        ) : null}
      </div>
      {invalid ? (
        <p id={errorId} className="font-body text-xs text-flag" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
