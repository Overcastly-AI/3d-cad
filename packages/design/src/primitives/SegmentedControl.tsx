/**
 * SegmentedControl — a mutually-exclusive toggle rendered in the toolbar
 * idiom, for the feature editors' mode switches (add/cut, normal/reverse).
 * Built ON the machine-shop token system like `ToolButton`: square corners,
 * a hairline-ruled border, scribed icons, and the accent spent only on the
 * active segment's brass text + scribe underline — never a filled pill.
 *
 * It is the icon-forward evolution of the ad-hoc two-cell toggle the editors
 * used before: same `aria-pressed`/`role="group"` semantics (so QA hooks and
 * screen readers are unchanged), now discoverable at a glance.
 *
 * DENSITY (FB-19). Two 2-state toggles used to cost four rows — a caption line
 * and a control line each. They now share ONE row, which needs two things this
 * primitive owns rather than the editor:
 *
 *   `hideLabel`  the group keeps its accessible name and loses the caption
 *                LINE. Legitimate only where the segments name themselves
 *                (ADD/CUT, NORMAL/REVERSE): the segment's own word IS the
 *                label, and each segment's `aria-label` still carries the group
 *                ("Operation: Add"), so nothing is lost to a screen reader or
 *                to a pointer (the same string becomes the tooltip).
 *   `size="dense"`  the segment trades horizontal padding, letter tracking and
 *                its ICON for width. Measured on the extrude card: two controls
 *                sharing a 264px column give the Direction segments 45.5px of
 *                text box, and "REVERSE" lays out at 46.1px with the icon
 *                present — so the first build of this row shipped `REVER…`, and
 *                the word is worth more than a 12px glyph sitting next to it.
 *                (A word-only dense segment has ~16px of slack instead of
 *                −0.6px, which also survives the fallback font.) It keeps the
 *                24px target floor (SC 2.5.8) — this is a width trade, never a
 *                target trade.
 */
import type { ReactNode } from "react";

import { cx } from "../cx";

export interface SegmentOption<T extends string = string> {
  /** Stable value returned by `onChange`. */
  value: T;
  /** Tracked-caps label shown in the segment. */
  label: string;
  /** Optional scribed glyph, rendered aria-hidden beside the label. */
  icon?: ReactNode;
  "data-testid"?: string;
  /** Override the accessible name (defaults to `label`). */
  "aria-label"?: string;
}

export interface SegmentedControlProps<T extends string = string> {
  /** Group name — the quiet field label and the group's accessible name. */
  label: string;
  /** The currently selected value. */
  value: T;
  options: readonly SegmentOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
  /**
   * Keep the group's accessible name and drop the visible caption LINE. For a
   * control whose segments name themselves; see the density note above.
   */
  hideLabel?: boolean;
  /** `dense` narrows the segment so two controls fit one card row (FB-19). */
  size?: "default" | "dense";
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
  className,
  hideLabel = false,
  size = "default",
}: SegmentedControlProps<T>) {
  const dense = size === "dense";
  return (
    <div
      role="group"
      aria-label={label}
      className={cx(
        hideLabel ? "flex min-w-0 grow" : "flex flex-col gap-0.5",
        className,
      )}
    >
      {hideLabel ? null : (
        <span className="font-body text-xs text-gauge">{label}</span>
      )}
      <div
        className={cx(
          "flex grow items-stretch divide-x divide-hairline rounded-sm border border-etch",
          dense && "min-w-0",
        )}
      >
        {options.map((option) => {
          const selected = option.value === value;
          const name = option["aria-label"] ?? option.label;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              aria-label={name}
              // With the caption line gone the group name must still reach a
              // POINTER, not only a screen reader — same string, no second
              // source of truth.
              title={hideLabel ? name : undefined}
              data-testid={option["data-testid"]}
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={cx(
                "relative flex flex-1 items-center justify-center",
                dense
                  ? "min-h-target-dense min-w-0 gap-1 px-1.5"
                  : "gap-1.5 px-3 py-1.5",
                "transition-colors duration-fast hover:bg-carbide",
                "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
                "disabled:opacity-40 disabled:pointer-events-none",
                selected ? "text-brass" : "text-mist",
              )}
            >
              {/* Dropped in dense mode — see the width measurement above. */}
              {option.icon && !dense ? (
                <span aria-hidden className="flex shrink-0 items-center">
                  {option.icon}
                </span>
              ) : null}
              <span
                className={cx(
                  "font-display text-2xs uppercase",
                  dense ? "truncate tracking-[0.04em]" : "tracking-[0.12em]",
                )}
              >
                {option.label}
              </span>
              {/* Active scribe — a brass line, never a fill (title-block idiom). */}
              {selected ? (
                <span
                  aria-hidden
                  // Same QA hook as `ToolButton`: the accent is a line, so its
                  // measured size is the assertion (UI-REVIEW 2026-07-30).
                  data-scribe
                  className={cx(
                    "pointer-events-none absolute bottom-0.5 h-px bg-brass",
                    dense ? "inset-x-1" : "inset-x-1.5",
                  )}
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
