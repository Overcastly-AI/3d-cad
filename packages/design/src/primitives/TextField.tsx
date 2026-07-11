import type { InputHTMLAttributes } from "react";
import { forwardRef, useId } from "react";

import { cx } from "../cx";

export interface TextFieldProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "id"
> {
  /** Visible cell label, e.g. "Email". */
  label: string;
  /** Input type — text-like only; numbers belong to NumberField. */
  type?: "text" | "email" | "password";
  /** Validation message; sets aria-invalid + flag styling when present. */
  error?: string | null;
}

/**
 * Text input cell — same ruled anatomy as NumberField (label over a carbide
 * inset cell, brass focus, flag on error) for email/password/text values.
 * Lives in the design system so app code never restyles a raw <input>.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(
  function TextField({ label, type = "text", error, className, ...rest }, ref) {
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
            "flex items-baseline rounded-sm border bg-carbide px-2 py-1",
            "focus-within:outline focus-within:outline-2 focus-within:outline-offset-1",
            invalid
              ? "border-flag focus-within:outline-flag"
              : "border-etch focus-within:outline-brass",
          )}
        >
          <input
            ref={ref}
            id={id}
            type={type}
            spellCheck={false}
            aria-invalid={invalid || undefined}
            aria-describedby={invalid ? errorId : undefined}
            className="w-full min-w-0 bg-transparent font-data text-md text-mist outline-none placeholder:text-gauge"
            {...rest}
          />
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
