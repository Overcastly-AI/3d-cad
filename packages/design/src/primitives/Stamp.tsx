import type { HTMLAttributes } from "react";

import { cx } from "../cx";

export type StampTone = "flag" | "gauge" | "brass";

export interface StampProps extends HTMLAttributes<HTMLSpanElement> {
  /** Ink of an ESTABLISHED fact. Ignored when `indeterminate` is set. */
  tone?: StampTone;
  /**
   * The fact is NOT ESTABLISHED — drawn with a dashed rule in quiet ink, never
   * in an alarm or an approval colour. See the doc comment: this is the one
   * vocabulary the product uses for "unknown", so a consumer cannot invent a
   * third look for the same idea.
   */
  indeterminate?: boolean;
}

/**
 * A STAMPED EXCEPTION — the small tracked-caps badge a drawing gets rubber-
 * stamped with when something about it needs saying: CLASH, UNVERIFIED, BROKEN.
 *
 * Two states, and the distinction is the whole point:
 *
 *  - **established** (`tone`) — the fact is measured and current, so it is
 *    inked: `flag` for an exception that needs action, `brass` for a
 *    standard/selected fact, `gauge` for a quiet one. Solid rule.
 *  - **indeterminate** (`indeterminate`) — the fact is NOT established. Drawn
 *    with a DASHED rule in gauge, because a broken line is drafting's phantom
 *    idiom for "not established", and it reads as attention without alarm.
 *
 * Extracted on the third use (DRY): the assembly clash schedule's UNVERIFIED
 * badge, the assembly tree's CLASH/UNVERIFIED badges, and the register's
 * rebuild-health column all say "here is an exception, and here is how sure we
 * are". They had each hand-rolled the same six classes, which is how a surface
 * ends up claiming more certainty than its neighbour for the same data
 * (UI-REVIEW 2026-07-30: the clash panel was honest while the viewport was not).
 *
 * `data-stamp` is the QA hook: the difference between "unknown" and "broken" is
 * a BORDER STYLE and an INK, so it is asserted by computed style rather than by
 * screenshot (`e2e/p2-register-health.spec.ts`).
 */
export function Stamp({
  tone = "gauge",
  indeterminate,
  className,
  ...rest
}: StampProps) {
  return (
    <span
      data-stamp={indeterminate ? "indeterminate" : tone}
      className={cx(
        "inline-block shrink-0 rounded-sm border px-1 font-display text-2xs uppercase tracking-[0.14em]",
        indeterminate
          ? "border-dashed border-etch text-gauge"
          : tone === "flag"
            ? "border-flag text-flag"
            : tone === "brass"
              ? "border-brass text-brass"
              : "border-etch text-gauge",
        className,
      )}
      {...rest}
    />
  );
}
