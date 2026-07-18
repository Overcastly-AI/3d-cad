import type { SelectHTMLAttributes } from "react";

import { cx } from "../cx";

export interface InlineSelectOption {
  value: string;
  label: string;
}

export interface InlineSelectProps extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "id" | "children"
> {
  /**
   * A small leading tag shown before the value (e.g. "Units"). Doubles as the
   * accessible name unless an explicit `aria-label` is given — the tag reads as
   * the field's label the way a title-block cell's caption does.
   */
  eyebrow: string;
  /** Choices rendered in order. */
  options: readonly InlineSelectOption[];
}

/**
 * A compact, single-line select for CHROME — a top-bar / status-strip
 * instrument, not a form cell. Where {@link SelectField} stacks a label over a
 * full-width cell, this keeps the caption and value on one baseline inside a
 * quiet ruled pill, so document-level settings (units, active configuration)
 * recede into the chrome instead of shouting like a form. Brass focus and the
 * carbide inset match the rest of the title-block family; app code composes it
 * and never restyles a raw <select>.
 */
export function InlineSelect({
  eyebrow,
  options,
  className,
  "aria-label": ariaLabel,
  ...rest
}: InlineSelectProps) {
  return (
    <div
      className={cx(
        "inline-flex items-center gap-1.5 rounded-sm border border-etch bg-carbide py-1 pl-2 pr-1",
        "focus-within:outline focus-within:outline-2 focus-within:outline-offset-1 focus-within:outline-brass",
        className,
      )}
    >
      <span
        aria-hidden
        className="font-display text-2xs uppercase tracking-[0.16em] text-gauge select-none"
      >
        {eyebrow}
      </span>
      <select
        aria-label={ariaLabel ?? eyebrow}
        className="cursor-pointer bg-transparent font-data text-md text-mist outline-none"
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} className="bg-anvil">
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
