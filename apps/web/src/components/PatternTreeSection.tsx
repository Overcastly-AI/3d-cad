/**
 * The component tree's PATTERNS section (ASM-A3-PATTERN): one row per
 * component pattern, as Fusion lists a pattern as one browser entry. Each row
 * names the kind and what it repeats, and reads how many it places per seed
 * from the solve (a hole pattern's count follows its part, so the number is
 * the solve's, never the stored definition's). Double-click or Enter edits;
 * Remove deletes the pattern and its copies, leaving the seeds.
 */
import { PanelSection } from "@loft/design";

import type { InstanceResponse } from "../api/assemblies";
import type { PatternCount, PatternResponse } from "../api/patterns";
import { patternSeedNames, patternTitle } from "../assembly/patterns";

export interface PatternTreeSectionProps {
  patterns: readonly PatternResponse[];
  instances: readonly InstanceResponse[];
  /** Each pattern's count from the settled solve, by pattern id. */
  states: ReadonlyMap<string, PatternCount>;
  /** The solve is not settled: counts are not claimed. */
  stale: boolean;
  busy: boolean;
  onEdit: (pattern: PatternResponse) => void;
  onDelete: (pattern: PatternResponse) => void;
}

export function PatternTreeSection({
  patterns,
  instances,
  states,
  stale,
  busy,
  onEdit,
  onDelete,
}: PatternTreeSectionProps) {
  if (patterns.length === 0) return null;
  return (
    <PanelSection eyebrow={`Patterns · ${patterns.length}`}>
      <ul className="py-1" data-testid="pattern-list">
        {patterns.map((pattern, index) => {
          const title = patternTitle(patterns, pattern);
          const state = states.get(pattern.id);
          const count = stale ? null : (state?.count ?? null);
          const failed = !stale && state !== undefined && state.count === null;
          return (
            <li
              key={pattern.id}
              data-testid="pattern-row"
              data-pattern-id={pattern.id}
              data-pattern-type={pattern.pattern.type}
              data-pattern-count={count ?? ""}
              tabIndex={0}
              title={`Double-click to edit ${title}`}
              onDoubleClick={() => onEdit(pattern)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  event.target === event.currentTarget
                ) {
                  event.preventDefault();
                  onEdit(pattern);
                }
              }}
              className="flex cursor-default items-center gap-2 px-2 py-1 outline-none hover:bg-carbide focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass"
            >
              <span
                className={`flex h-5 shrink-0 items-center justify-center rounded-sm border px-1 font-data text-2xs tabular-nums ${
                  failed ? "border-flag text-flag" : "border-etch text-gauge"
                }`}
              >
                P{index + 1}
              </span>
              <span className="min-w-0 grow">
                <span
                  className={`block font-body text-sm ${failed ? "text-flag" : "text-mist"}`}
                >
                  {title}
                  {count !== null ? (
                    <span
                      className="ml-1.5 font-data text-2xs tabular-nums text-brass"
                      data-testid="pattern-count-echo"
                    >
                      × {count}
                    </span>
                  ) : null}
                </span>
                <span className="block truncate font-data text-2xs text-gauge">
                  {patternSeedNames(instances, pattern.pattern)}
                  {failed ? ` · ${state?.error_message ?? "not placed"}` : ""}
                </span>
              </span>
              <button
                type="button"
                onClick={() => onEdit(pattern)}
                disabled={busy}
                aria-label={`Edit ${title}`}
                data-testid={`pattern-edit-${pattern.id}`}
                className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => onDelete(pattern)}
                disabled={busy}
                aria-label={`Remove ${title}`}
                data-testid={`pattern-delete-${pattern.id}`}
                className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          );
        })}
      </ul>
    </PanelSection>
  );
}
