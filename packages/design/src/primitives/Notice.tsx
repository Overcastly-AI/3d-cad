import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "../cx";
import { Stamp, type StampTone } from "./Stamp";

export interface NoticeProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "role"
> {
  /**
   * `alert` when something the user just did has not fully happened (it
   * interrupts); `status` for a standing condition they should know before
   * they act (polite). Required: an announcement's urgency is a decision, not
   * a default.
   */
  role: "alert" | "status";
  /** The stamped lead — two or three words, tracked caps. */
  label: string;
  /** `flag` for an exception that needs action; `gauge` for a quiet one. */
  tone?: Extract<StampTone, "flag" | "gauge">;
  /** The sentence: what happened, then what to do about it. */
  children: ReactNode;
  /**
   * The ONE thing that answers the notice, when there is one ("Re-pick
   * edges"), in Dismiss's ink: a notice that names a fix and leaves the reader
   * to hunt for it is half a notice. In a row it sits beside Dismiss; stacked,
   * it takes its own line under the sentence, which is where the eye is when
   * the sentence says what to do.
   */
  action?: { label: string; onClick: () => void; testId?: string };
  /** Renders the dismiss control; omit for a notice that cannot be dismissed. */
  onDismiss?: () => void;
  /** Test hook for the dismiss control. */
  dismissTestId?: string;
  /**
   * `row` (default): stamp, sentence, action, dismiss on one line — a
   * full-width strip. `stacked`: stamp and dismiss share the first line, the
   * sentence takes the full width below, and the action (if any) the line
   * under that — for a narrow panel, where one row would squeeze the sentence
   * into a column one word wide. The DOM order (and so the announcement and
   * the tab order) is the same in both: stamp, sentence, action, dismiss.
   */
  layout?: "row" | "stacked";
}

/** A notice's own controls: brass tracked caps, the dense target floor. */
const NOTICE_CONTROL =
  "min-h-target-dense shrink-0 whitespace-nowrap rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass";

/**
 * A STANDING NOTICE — a condition that stays true until it is fixed or the
 * user says they have read it, so it is a strip IN FLOW rather than a toast:
 * it takes its own row and pushes the content below it down, so it can never
 * sit over the model, and it does not vanish on a timer before it is read.
 *
 * Built from the product's own exception vocabulary: the lead is a `Stamp`
 * (the same flag-inked badge that marks CLASH and BROKEN), and the ground is
 * the chrome's own anvil with a hairline — the only colour it spends is the
 * stamp's ink and a two-pixel rule on the leading edge, so a notice reads as
 * an annotation on the sheet, not as a banner across it.
 */
export function Notice({
  role,
  label,
  tone = "flag",
  children,
  action,
  onDismiss,
  dismissTestId,
  layout = "row",
  className,
  ...rest
}: NoticeProps) {
  const stacked = layout === "stacked";
  return (
    <div
      role={role}
      data-notice={tone}
      data-layout={layout}
      className={cx(
        "shrink-0 border-b border-l-2 border-b-hairline bg-anvil px-3 py-1.5",
        stacked
          ? "grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5"
          : "flex items-center gap-3",
        tone === "flag" ? "border-l-flag" : "border-l-etch",
        className,
      )}
      {...rest}
    >
      <Stamp
        tone={tone}
        className={
          stacked ? "col-start-1 row-start-1 justify-self-start" : undefined
        }
      >
        {label}
      </Stamp>
      <p
        className={cx(
          "min-w-0 font-body text-xs text-mist",
          stacked ? "col-span-2 row-start-2" : "grow",
        )}
      >
        {children}
      </p>
      {stacked ? (
        <>
          {action ? (
            <span className="col-span-2 row-start-3 justify-self-start">
              <button
                type="button"
                onClick={action.onClick}
                data-testid={action.testId}
                // -ml-1 sets the label's first letter on the sentence's edge.
                className={cx(NOTICE_CONTROL, "-ml-1")}
              >
                {action.label}
              </button>
            </span>
          ) : null}
          {onDismiss ? (
            <span className="col-start-2 row-start-1 justify-self-end">
              <button
                type="button"
                onClick={onDismiss}
                data-testid={dismissTestId}
                className={NOTICE_CONTROL}
              >
                Dismiss
              </button>
            </span>
          ) : null}
        </>
      ) : action || onDismiss ? (
        <span className="flex shrink-0 items-center gap-1">
          {action ? (
            <button
              type="button"
              onClick={action.onClick}
              data-testid={action.testId}
              className={NOTICE_CONTROL}
            >
              {action.label}
            </button>
          ) : null}
          {onDismiss ? (
            <button
              type="button"
              onClick={onDismiss}
              data-testid={dismissTestId}
              className={NOTICE_CONTROL}
            >
              Dismiss
            </button>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}
