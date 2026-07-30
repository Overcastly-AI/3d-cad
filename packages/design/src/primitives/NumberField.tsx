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
  /**
   * `primary` marks THE parametric handle of the feature being authored — the
   * hole's diameter, the extrude's distance: the one number the modeller came
   * to type. It reads at DRO scale in brass over a comfortable target, so a
   * card of a dozen inputs still has an obvious point of entry (UI-W4).
   *
   * Exactly one per editor. Boldness is spent in one place (design mandate);
   * a card with two primaries has none.
   */
  emphasis?: "default" | "primary";
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
  emphasis = "default",
  ...rest
}: NumberFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const invalid = Boolean(error);
  const primary = emphasis === "primary";
  return (
    <div className={cx("flex flex-col gap-0.5", className)}>
      <label
        htmlFor={id}
        className={cx(
          "text-gauge",
          primary
            ? "font-display text-2xs uppercase tracking-[0.18em]"
            : "font-body text-xs",
        )}
      >
        {label}
      </label>
      <div
        className={cx(
          "flex items-baseline gap-1 rounded-sm border bg-carbide px-2",
          "focus-within:outline focus-within:outline-2 focus-within:outline-offset-1",
          primary ? "min-h-target py-0.5" : "py-1",
          invalid
            ? "border-flag focus-within:outline-flag"
            : primary
              ? "border-brass/60 focus-within:outline-brass"
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
          className={cx(
            "w-full min-w-0 bg-transparent font-data outline-none placeholder:text-gauge",
            primary ? "text-lg text-brass" : "text-md text-mist",
          )}
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
