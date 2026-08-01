import type { ReactNode } from "react";
import { useId } from "react";

import { cx } from "../cx";

export interface DisclosureProps {
  /** Tracked-caps section name, e.g. "Thread". */
  label: string;
  /**
   * What the collapsed section currently SAYS — "None", "M10x1.5". A
   * disclosure that hides state without reporting it is a place for a setting
   * to go missing, which is the defect this primitive exists to avoid.
   */
  summary: string;
  /**
   * `flag` when the collapsed content has a problem the user must fix. A
   * section is allowed to hide controls; it is not allowed to hide an error,
   * so the summary carries it out to where the eye is.
   */
  summaryTone?: "quiet" | "flag";
  /** Open state (controlled — the owner decides, e.g. "open while tapped"). */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Test hook on the trigger; the panel gets `${id}-panel`. */
  "data-testid"?: string;
  children: ReactNode;
}

/**
 * A collapsible sub-section of a title-block card — progressive disclosure for
 * the parameters a feature only sometimes carries (the hole's thread block was
 * ~5 of its 12 rows and pushed the placement face off the top of the card:
 * UI-W4).
 *
 * Drawn in the established hand: a ruled row, a scribed caret that rotates on
 * open (motion respected), the label in the display face and the current value
 * in the data face. Not a `<details>`: the open state is controlled by the
 * owner so a section can be forced open when its content becomes load-bearing.
 */
export function Disclosure({
  label,
  summary,
  summaryTone = "quiet",
  open,
  onOpenChange,
  "data-testid": testId,
  children,
}: DisclosureProps) {
  const id = useId();
  const panelId = `${id}-panel`;
  return (
    <div className="border-t border-hairline">
      <button
        type="button"
        data-testid={testId}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => onOpenChange(!open)}
        className={cx(
          "flex min-h-target-dense w-full items-center gap-2 py-1 text-left",
          "transition-colors duration-fast",
          "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
          "group",
        )}
      >
        <span
          aria-hidden
          className={cx(
            "inline-block shrink-0 font-data text-2xs leading-none text-gauge",
            "transition-transform duration-fast motion-reduce:transition-none",
            open ? "rotate-90" : "rotate-0",
          )}
        >
          ▸
        </span>
        <span className="grow font-display text-2xs uppercase tracking-[0.14em] text-mist">
          {label}
        </span>
        <span
          className={cx(
            "shrink-0 font-data text-xs",
            summaryTone === "flag" ? "text-flag" : "text-gauge",
          )}
        >
          {summary}
        </span>
      </button>
      <div id={panelId} hidden={!open} className={open ? "pb-1" : undefined}>
        {open ? children : null}
      </div>
    </div>
  );
}
