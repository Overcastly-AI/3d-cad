import type { HTMLAttributes, InputHTMLAttributes, Ref } from "react";
import { useId } from "react";

import { cx } from "../cx";

/**
 * THE DRAFTING DIMENSION TAG — the value cell a tool hangs on the geometry it
 * is making, while it is making it.
 *
 * This is deliberately NOT the title-block {@link Panel} the feature editors
 * use. A panel is a place you go; a tag is a note stuck on the work, and the
 * two must not read alike: the panel form (stacked label-over-cell, a padded
 * card, an Apply button) is four times too tall to sit beside a line you are
 * dragging, and it turns "type the width" into "fill in a form". The tag is one
 * ruled strip in the drafting register — terse caps label, value in the data
 * face, unit stated ONCE for the strip — so a rectangle's two dimensions read
 * as `W 40 × H 25 mm`, the way they would be written on a drawing.
 *
 * Two states, one component:
 *  · **readout** (`readout` prop set) — no input, pointer-inert: the live size
 *    while the shape is still being dragged, when the pointer owns the value;
 *  · **editable** (no `readout`) — a real input the modeller types into.
 * The number does not move between the two, so the value you watched form is
 * the value you type over.
 *
 * The cell renders no border of its own: the strip's hairline frame and its
 * `divide-x` rules are the ruling, exactly as a title block divides its cells.
 * Focus is shown on the CELL (brass ground + brass value) rather than as an
 * outline ring, because at this size a ring would fatten the strip enough to
 * cover the geometry it annotates — the focus indicator is still a ≥3:1
 * non-text contrast change, and the value's own ink shifts with it.
 */
export function DimensionTag({
  unit,
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & {
  /** Unit written once, at the end of the strip — e.g. "mm". */
  unit?: string;
}) {
  return (
    <div
      className={cx(
        "flex items-stretch divide-x divide-hairline border border-hairline bg-anvil",
        className,
      )}
      {...rest}
    >
      {children}
      {unit ? (
        <span className="flex select-none items-center px-2 font-body text-2xs text-gauge">
          {unit}
        </span>
      ) : null}
    </div>
  );
}

export interface DimensionTagCellProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "id" | "size"
> {
  /** Terse drafting label — "W", "H", "R". One or two characters. */
  label: string;
  /**
   * Read-only value. When set the cell renders as text, not an input: the
   * pointer is still driving this number, so there is nothing to type into.
   */
  readout?: string;
  /** Character width of the value cell (defaults to 5 — `1234.5`). */
  width?: number;
  ref?: Ref<HTMLInputElement>;
}

export function DimensionTagCell({
  label,
  readout,
  width = 5,
  className,
  ref,
  ...rest
}: DimensionTagCellProps) {
  const id = useId();
  // `ch` on the data face: the cell is sized by the DIGITS it holds, not by a
  // guessed rem value, so it never grows a ragged right edge across shapes.
  const valueStyle = { width: `${width}ch` };
  if (readout !== undefined) {
    return (
      <span
        className={cx("flex items-baseline gap-1.5 px-2 py-1", className)}
        aria-hidden
      >
        <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
          {label}
        </span>
        <span
          className="font-data text-sm tabular-nums text-mist"
          style={valueStyle}
        >
          {readout}
        </span>
      </span>
    );
  }
  return (
    <label
      htmlFor={id}
      className={cx(
        "flex items-baseline gap-1.5 px-2 py-1",
        "focus-within:bg-brass/15",
        className,
      )}
    >
      <span className="font-display text-2xs uppercase tracking-[0.16em] text-gauge">
        {label}
      </span>
      <input
        id={id}
        ref={ref}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        spellCheck={false}
        className="bg-transparent font-data text-sm tabular-nums text-mist outline-none placeholder:text-gauge focus:text-brass"
        style={valueStyle}
        {...rest}
      />
    </label>
  );
}
