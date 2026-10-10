import type { CSSProperties } from "react";

import { cx } from "../cx";

export interface SuggestionOption {
  /** What is inserted, and the row's name: a parameter name, `sin`. */
  value: string;
  /** Quiet reading beside it: the parameter's value, or `function`. */
  detail?: string;
}

export interface SuggestionListProps {
  /** The listbox id the input's `aria-controls` names. */
  id: string;
  options: readonly SuggestionOption[];
  /** The highlighted row (the input's `aria-activedescendant`). */
  activeIndex: number;
  onPick: (index: number) => void;
  /** Where to draw it: the caller places the list (fixed, under its cell). */
  style?: CSSProperties;
  "aria-label"?: string;
  "data-testid"?: string;
}

/** The id of row `index` of the list `id`, for `aria-activedescendant`. */
export function suggestionOptionId(id: string, index: number): string {
  return `${id}-option-${index}`;
}

/**
 * SuggestionList — the completion list under a value cell (a parameter name
 * as it is typed, Fusion's expression autocomplete). An anvil card with
 * hairline rules, the Flyout's idiom: the name in data ink, its value quiet at
 * the right. It never takes focus: the INPUT keeps it and drives the list
 * (`role="combobox"`, arrows, Enter or Tab to accept), so typing never stops.
 * A pointer press is swallowed on `mousedown` for the same reason.
 *
 * Presentational only: the caller owns the state and the position (a cell in
 * a scrolling editor card, or inside the canvas, has to portal the list out of
 * any clipping or transformed ancestor, which the app does).
 */
export function SuggestionList({
  id,
  options,
  activeIndex,
  onPick,
  style,
  "aria-label": ariaLabel = "Suggestions",
  "data-testid": testId,
}: SuggestionListProps) {
  return (
    <ul
      id={id}
      role="listbox"
      aria-label={ariaLabel}
      data-testid={testId}
      style={style}
      className="z-menu max-h-[15rem] overflow-y-auto border border-hairline bg-anvil py-1 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
    >
      {options.map((option, index) => {
        const active = index === activeIndex;
        return (
          <li
            key={option.value}
            id={suggestionOptionId(id, index)}
            role="option"
            aria-selected={active}
            data-value={option.value}
            onMouseDown={(event) => {
              event.preventDefault();
              onPick(index);
            }}
            className={cx(
              "flex min-h-target-dense cursor-pointer items-center gap-3 px-2",
              active ? "bg-carbide text-brass" : "text-mist hover:bg-carbide",
            )}
          >
            <span className="min-w-0 grow truncate font-data text-xs">
              {option.value}
            </span>
            {option.detail !== undefined ? (
              <span className="shrink-0 font-data text-2xs text-gauge tabular-nums">
                {option.detail}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
