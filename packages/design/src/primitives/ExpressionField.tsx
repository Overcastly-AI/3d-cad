import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

import { cx } from "../cx";

export interface ExpressionFieldProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "id"
> {
  /** Visible cell label, e.g. "Distance". */
  label: string;
  /** Unit suffix rendered inside the cell, e.g. "mm". */
  unit?: string;
  /** Validation message; sets aria-invalid + flag styling when present. */
  error?: string | null;
  /**
   * Resolved-value echo shown under the cell — the drafting "computed value"
   * of an expression (e.g. "= 10 mm"). Rendered in brass, the parametric ink,
   * only when there's no error. Null hides the line.
   */
  resolved?: ReactNode;
}

/**
 * A dimension value cell that accepts a bare literal (`20`) OR a math
 * expression over other dimension names (`width/2`). Same ruled anatomy as
 * NumberField, but free-text `inputMode` (an expression carries letters and
 * operators) and an optional brass echo of the last resolved value beneath the
 * cell — the spreadsheet-cell idea in the title-block idiom. Lives in the
 * design system so app code never restyles a raw <input>.
 */
export function ExpressionField({
  label,
  unit,
  error,
  resolved,
  className,
  ...rest
}: ExpressionFieldProps) {
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
          inputMode="text"
          autoComplete="off"
          autoCapitalize="off"
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
      ) : !invalid && resolved != null ? (
        <p className="font-data text-xs text-brass tabular-nums">{resolved}</p>
      ) : null}
    </div>
  );
}
