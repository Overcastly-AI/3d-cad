/**
 * One action cell of a full-width band — the horizontal sibling of
 * `PanelActionCell`: a tracked-caps label over a quiet keyboard/reason caption,
 * seated in a hairline-divided run at the end of a band.
 *
 * Extracted from `CreateStrip`'s in-command OK/Cancel on its second real use
 * (the bottom timeline's TO TIP escape hatch), so the two bands cannot drift.
 * `accent` marks the one primary commit in a run; everything else stays quiet.
 *
 * Gating uses `aria-disabled`, not the native attribute, so a gated cell still
 * hovers and focuses and can therefore SAY why it is gated (the caption is the
 * place for the reason). It is inert on activation: clicks — and so Enter/Space,
 * which dispatch one — are swallowed. Playwright's `toBeDisabled()` honors
 * `aria-disabled`, so gate assertions still hold.
 */
import type { ButtonHTMLAttributes, MouseEvent, ReactNode } from "react";

import { cx } from "../cx";

export interface BandActionCellProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** The action, tracked caps — e.g. "OK", "To tip". */
  label: string;
  /** Quiet second line: the accelerator, or WHY the cell is gated. */
  caption?: ReactNode;
  /** The primary commit of the run — carries the brass accent. */
  accent?: boolean;
}

export function BandActionCell({
  label,
  caption,
  accent = false,
  className,
  type,
  disabled,
  onClick,
  ...rest
}: BandActionCellProps) {
  const isDisabled = disabled === true;
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (isDisabled) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };
  return (
    <button
      type={type ?? "button"}
      aria-disabled={isDisabled || undefined}
      onClick={handleClick}
      className={cx(
        "flex min-h-target flex-col items-center justify-center gap-0.5 px-4",
        "motion-safe:transition-colors motion-safe:duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
        isDisabled
          ? "cursor-not-allowed opacity-40"
          : accent
            ? "text-brass hover:bg-brass/10"
            : "text-gauge hover:bg-hairline/40 hover:text-mist",
        className,
      )}
      {...rest}
    >
      <span className="font-display text-2xs uppercase tracking-[0.18em]">
        {label}
      </span>
      {caption !== undefined ? (
        <span className="font-body text-[9px] uppercase tracking-[0.14em] text-gauge">
          {caption}
        </span>
      ) : null}
    </button>
  );
}
