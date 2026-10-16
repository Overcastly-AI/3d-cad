/**
 * ToolGroup — a labeled cluster of band tools (Fusion's toolbar "group"),
 * split from `ToolButton.tsx` so it can own a `Flyout` without an import cycle
 * (`Flyout` borrows `ToolButton`'s stamp and key chip).
 */
import type { HTMLAttributes } from "react";

import { cx } from "../cx";
import { Flyout } from "./Flyout";
import type { FlyoutItem } from "./Flyout";

export interface ToolGroupProps extends HTMLAttributes<HTMLDivElement> {
  /** Tracked-caps cluster name (encodes the real taxonomy, not decoration). */
  eyebrow?: string;
  /**
   * How hard this group holds on to its labels when the band runs out of room
   * — HIGHER keeps its words longer (`CommandBand` guarantee #3). Groups that
   * share a value are shed together, so peers are never half-dressed.
   *
   * The scale is per-band and means nothing on its own; what it encodes is
   * INFORMATION PER PIXEL. A label earns its width when the glyph cannot carry
   * the identity — a format code like "3MF" is an identifier no picture can
   * spell, while "Extrude" merely repeats a glyph the eyebrow and tooltip
   * already name. Rank accordingly, and say why at the call site.
   *
   * Left at the default, every group on a surface shares one level and the
   * band flips as a unit — the two-tier behaviour that predates this.
   */
  labelPriority?: number;
  /**
   * The group's LOW-FREQUENCY verbs, behind its eyebrow ("CREATE ▾") — the
   * way Fusion's toolbar keeps Pipe, Draft or Combine one click away without
   * paying a band cell for each. This is the band's growth path that
   * `CommandBand` names: a new verb that is not reached for every session
   * goes here, not onto the row, so the band keeps a width that can still
   * afford its labels. Needs an `eyebrow` (it is the trigger).
   */
  more?: readonly FlyoutItem[];
  /** Test hook for the "more" trigger. */
  moreTestId?: string;
}

/**
 * A labeled cluster of tools — the Fusion-style "group" rendered in
 * Plasticity density. The eyebrow names the family (Geometric / Dimensional /
 * Relational / Create); the members sit in a tight row beneath it.
 *
 * `data-labels` is written by the enclosing `CommandBand` after it measures,
 * never rendered here: React would fight the imperative probe for it, and a
 * group that has not been measured yet must default to showing its labels so
 * the band's first measurement sees the widest configuration.
 */
export function ToolGroup({
  eyebrow,
  labelPriority = 0,
  more,
  moreTestId,
  className,
  children,
  ...rest
}: ToolGroupProps) {
  const hasMore =
    eyebrow !== undefined && more !== undefined && more.length > 0;
  return (
    <div
      role="group"
      aria-label={eyebrow}
      data-label-priority={labelPriority}
      className={cx(
        "flex flex-col justify-center px-1.5 py-1",
        // The "more" menu hangs from the GROUP, below its tools.
        hasMore && "relative",
        className,
      )}
      {...rest}
    >
      {hasMore ? (
        <Flyout
          variant="eyebrow"
          label={eyebrow}
          triggerLabel={`More ${eyebrow} tools`}
          eyebrow={eyebrow}
          items={more}
          data-testid={moreTestId}
        />
      ) : eyebrow ? (
        <span className="px-1 pb-0.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
          {eyebrow}
        </span>
      ) : null}
      <div className="flex items-stretch gap-0.5">{children}</div>
    </div>
  );
}
