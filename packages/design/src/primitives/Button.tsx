import type { ButtonHTMLAttributes } from "react";

import { cx } from "../cx";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * `solid` = the one brass action; `ghost` = quiet chrome action;
   * `danger` = a confirmed destructive action (flag, used sparingly).
   */
  variant?: "solid" | "ghost" | "danger";
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-sm font-body text-sm font-medium " +
  "px-3 py-1 select-none transition-colors duration-fast " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-brass disabled:opacity-50 disabled:pointer-events-none";

const variants = {
  solid: "bg-brass text-carbide hover:bg-brass-hover",
  ghost:
    "bg-transparent text-gauge border border-etch hover:text-mist hover:border-gauge",
  danger: "bg-flag text-carbide hover:brightness-95 focus-visible:outline-flag",
} as const;

/** The button. Spend brass on at most one solid button per surface. */
export function Button({
  variant = "ghost",
  className,
  type,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type ?? "button"}
      className={cx(base, variants[variant], className)}
      {...rest}
    />
  );
}
