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
 *
 * …and the reason has to be READABLE, which is the whole point of keeping the
 * cell in the tree. A blanket `opacity-40` on the cell rendered it at 2.13:1
 * (UI-REVIEW 2026-07-30 P2-C) — the cell was reachable and the sentence was
 * not. The gated state is now carried by the LABEL dropping to `etch` (an
 * inactive control, exempt from 1.4.3) while the caption keeps `gauge` at
 * 7.2:1. The caption also sits on the 10px type floor: `text-[9px]` was the
 * only arbitrary font size left in the design system.
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
          ? "cursor-not-allowed"
          : accent
            ? "text-brass hover:bg-brass/10"
            : "text-gauge hover:bg-hairline/40 hover:text-mist",
        className,
      )}
      {...rest}
    >
      <span
        className={cx(
          "font-display text-2xs uppercase tracking-[0.18em]",
          isDisabled && "text-etch",
        )}
      >
        {label}
      </span>
      {caption !== undefined ? (
        <span className="font-body text-2xs uppercase tracking-[0.14em] text-gauge">
          {caption}
        </span>
      ) : null}
    </button>
  );
}
