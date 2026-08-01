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
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
  className,
}: SegmentedControlProps<T>) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cx("flex flex-col gap-0.5", className)}
    >
      <span className="font-body text-xs text-gauge">{label}</span>
      <div className="flex items-stretch divide-x divide-hairline rounded-sm border border-etch">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              aria-label={option["aria-label"] ?? option.label}
              data-testid={option["data-testid"]}
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={cx(
                "relative flex flex-1 items-center justify-center gap-1.5 px-3 py-1.5",
                "transition-colors duration-fast hover:bg-carbide",
                "focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass",
                "disabled:opacity-40 disabled:pointer-events-none",
                selected ? "text-brass" : "text-mist",
              )}
            >
              {option.icon ? (
                <span aria-hidden className="flex shrink-0 items-center">
                  {option.icon}
                </span>
              ) : null}
              <span className="font-display text-2xs uppercase tracking-[0.12em]">
                {option.label}
              </span>
              {/* Active scribe — a brass line, never a fill (title-block idiom). */}
              {selected ? (
                <span
                  aria-hidden
                  // Same QA hook as `ToolButton`: the accent is a line, so its
                  // measured size is the assertion (UI-REVIEW 2026-07-30).
                  data-scribe
                  className="pointer-events-none absolute inset-x-1.5 bottom-0.5 h-px bg-brass"
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
