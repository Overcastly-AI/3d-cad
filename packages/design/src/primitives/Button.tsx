import type { ButtonHTMLAttributes } from "react";

import { cx } from "../cx";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * `solid` = the one brass action; `ghost` = quiet chrome action;
   * `danger` = a confirmed destructive action (flag, used sparingly).
   */
  variant?: "solid" | "ghost" | "danger";
  /**
   * `regular` = a dialog or panel action; `dense` = a control in a 24 px
   * caption bar (a panel's Expand), sized to the dense row it sits in.
   */
  size?: "regular" | "dense";
}

const sizes = {
  regular: "gap-2 px-3 py-1 text-sm",
  dense: "min-h-target-dense gap-1.5 px-1.5 py-0 text-2xs",
} as const;

const base =
  "inline-flex items-center justify-center rounded-sm font-body font-medium " +
  "select-none transition-colors duration-fast " +
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
  size = "regular",
  className,
  type,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type ?? "button"}
      className={cx(base, sizes[size], variants[variant], className)}
      {...rest}
    />
  );
}
