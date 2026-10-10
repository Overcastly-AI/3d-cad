import type { InputHTMLAttributes, Ref, SelectHTMLAttributes } from "react";

import { cx } from "../cx";

/**
 * The editable cell of a ruled schedule — a spreadsheet cell in the
 * title-block idiom, for tables a user types INTO (the Parameters panel)
 * rather than reads (the BOM, the register).
 *
 * `TextField`/`ExpressionField` are form cells: a caption over a bordered
 * inset, ~40 px a row. A table already has its captions (the column heads) and
 * its rules (the row hairlines), so a form cell per column would draw every
 * rule twice and make a ten-row table a page long. This cell is borderless at
 * rest and reads as the table's own ink; it shows itself only when it is the
 * one being edited (carbide ground, brass inset ring) or is wrong (a flag
 * underline, and `aria-invalid`, so the fault is not colour-only).
 *
 * The accessible name is REQUIRED because a cell has no visible label of its
 * own: "W expression", not "Expression", so a screen reader (and a test)
 * addresses the cell by its row.
 */
const CELL =
  "w-full min-w-0 rounded-none bg-transparent px-1.5 py-1 font-data text-xs text-mist outline-none " +
  "placeholder:text-gauge hover:bg-carbide/60 focus:bg-carbide " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass " +
  "disabled:cursor-not-allowed disabled:hover:bg-transparent";

const INVALID =
  "underline decoration-flag decoration-2 underline-offset-4 focus-visible:outline-flag";

export interface GridCellInputProps extends Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "aria-label" | "type"
> {
  /** The cell's accessible name, naming its row: "W expression". */
  "aria-label": string;
  /** The cell's text is refused; pair with a row message that says why. */
  invalid?: boolean;
  ref?: Ref<HTMLInputElement>;
}

export function GridCellInput({
  invalid = false,
  className,
  ref,
  ...rest
}: GridCellInputProps) {
  return (
    <input
      ref={ref}
      type="text"
      autoComplete="off"
      autoCapitalize="off"
      spellCheck={false}
      aria-invalid={invalid || undefined}
      className={cx(CELL, invalid && INVALID, className)}
      {...rest}
    />
  );
}

export interface GridCellSelectOption {
  value: string;
  label: string;
}

export interface GridCellSelectProps extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "aria-label" | "children"
> {
  "aria-label": string;
  options: readonly GridCellSelectOption[];
}

/** The same cell for a short closed choice (a row's unit). */
export function GridCellSelect({
  options,
  className,
  ...rest
}: GridCellSelectProps) {
  return (
    <select className={cx(CELL, "cursor-pointer", className)} {...rest}>
      {options.map((option) => (
        <option key={option.value} value={option.value} className="bg-anvil">
          {option.label}
        </option>
      ))}
    </select>
  );
}
