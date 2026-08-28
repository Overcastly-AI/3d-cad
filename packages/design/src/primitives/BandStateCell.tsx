/**
 * One STATE cell of a full-width band — a tracked-caps eyebrow over the name of
 * the thing the band's actions are currently working with or within, in brass.
 * `BandActionCell`'s twin: that one is what you can DO, this one is where you
 * ARE (or what you are pointed at).
 *
 * Extracted from `CreateStrip`'s in-command block on its second real use — the
 * scope cell that names the feature a pattern/mirror will repeat (REACH-2-FLOW
 * P1-1). The two must not drift: a band that says "In command ▸ Pattern" in one
 * typographic voice and "Scope · Hole1" in another is two designs sharing a
 * strip.
 *
 * Why this exists at all, rather than a label on the tool: inside a
 * `CommandBand` a tool's LABEL is a measured tier and gets shed at narrow
 * widths, so anything that rides the label is invisible at exactly the 1280x800
 * floor the quality bar names. A band cell is not part of any `ToolGroup`, so
 * the shed pass never reaches it — which is the whole point. Pay for it in
 * width only when there is something to say: render nothing when there is not.
 *
 * `onClear` is not decoration and is not optional-by-taste: a cell that
 * announces a state the user cannot leave is a dead end (design mandate, flow
 * rule 4). Where the state is retractable, give the cell the retraction.
 */
import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "../cx";
import { CloseIcon } from "./icons";

export interface BandStateCellProps extends HTMLAttributes<HTMLDivElement> {
  /** What KIND of state this is — "In command", "Scope". Tracked caps. */
  eyebrow: string;
  /** The state's own name — the feature, the command. Carries the brass. */
  value: ReactNode;
  /**
   * A mark before the value. Give two cells two marks or none: one glyph
   * standing for two different relationships is worse than no glyph at all.
   */
  marker?: ReactNode;
  /** QA hook on the value node (the text a spec reads). */
  valueTestId?: string;
  /** Retire this state. Omit where the state cannot be retired from here. */
  onClear?: () => void;
  /** The accessible name of the retraction — say what leaves, not "close". */
  clearLabel?: string;
  clearTestId?: string;
}

export function BandStateCell({
  eyebrow,
  value,
  marker,
  valueTestId,
  onClear,
  clearLabel,
  clearTestId,
  className,
  ...rest
}: BandStateCellProps) {
  return (
    <div className={cx("flex items-center gap-1 px-3", className)} {...rest}>
      <div className="flex min-w-0 flex-col justify-center gap-0.5">
        <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
          {eyebrow}
        </span>
        <span
          data-testid={valueTestId}
          className="flex items-center gap-1.5 truncate font-data text-sm leading-none text-brass"
        >
          {marker !== undefined ? (
            <span aria-hidden className="text-brass">
              {marker}
            </span>
          ) : null}
          {value}
        </span>
      </div>
      {onClear !== undefined ? (
        <button
          type="button"
          aria-label={clearLabel}
          data-testid={clearTestId}
          onClick={onClear}
          className={cx(
            "flex size-5 shrink-0 items-center justify-center rounded-sm text-gauge",
            "hover:bg-carbide hover:text-mist",
            "motion-safe:transition-colors motion-safe:duration-fast",
            "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
          )}
        >
          <CloseIcon size={12} />
        </button>
      ) : null}
    </div>
  );
}
