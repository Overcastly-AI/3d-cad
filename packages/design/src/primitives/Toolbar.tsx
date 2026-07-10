import type { HTMLAttributes } from "react";

import { cx } from "../cx";

/** Top chrome bar — quiet, hairline-separated, fixed instrument height. */
export function Toolbar({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <header
      className={cx(
        "flex h-toolbar shrink-0 items-center gap-3 border-b border-hairline bg-anvil px-3",
        className,
      )}
      {...rest}
    />
  );
}

/** Status chip — tracked caps, brass on dark, drawing-stamp rectangular. */
export function Chip({ className, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm border border-hairline bg-carbide px-2 py-0.5",
        "font-display text-2xs uppercase tracking-[0.18em] text-brass",
        className,
      )}
      {...rest}
    />
  );
}
