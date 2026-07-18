/**
 * The Bodies list (multi-body §MB-1) — the part's solid bodies as a title-block
 * read-out, the feature tree's quiet twin. A part is usually one body; when a
 * `merge: false` add (or an import) starts a second, this names each body by its
 * base feature and lets you select one (which highlights it via the base
 * feature's selection + opens its editor — the same select the tree row does).
 * Per-body pick-highlight in the viewport is MB-4; this stays a dense read-out.
 */
import { Panel, PanelSection } from "@loft/design";

import type { BodyInfo } from "../features/bodies";

export interface BodiesPanelProps {
  bodies: readonly BodyInfo[];
  /** Selected feature id (a body row lights its brass left-rule when its base
   * feature is selected). */
  selectedFeatureId: string | null;
  /** Select a body by its base feature id (highlights + opens its editor). */
  onSelectBody: (baseFeatureId: string) => void;
}

export function BodiesPanel({
  bodies,
  selectedFeatureId,
  onSelectBody,
}: BodiesPanelProps) {
  const eyebrow = `Bodies · ${bodies.length}`;
  return (
    <aside
      className="flex w-full flex-col"
      aria-label="Bodies"
      data-testid="bodies-panel"
    >
      <Panel>
        <PanelSection eyebrow={eyebrow} data-testid="bodies-section">
          {bodies.length === 0 ? (
            <p className="px-3 py-1 font-body text-xs text-gauge">
              No bodies yet. Extrude a sketch to create one.
            </p>
          ) : (
            <ol className="pb-1">
              {bodies.map((body) => {
                const selected = body.baseFeatureId === selectedFeatureId;
                return (
                  <li
                    key={body.baseFeatureId}
                    className={`flex items-baseline gap-2 border-l-2 py-1 pr-3 pl-[10px] ${
                      selected ? "border-brass" : "border-transparent"
                    }`}
                    data-testid="body-row"
                  >
                    <button
                      type="button"
                      onClick={() => onSelectBody(body.baseFeatureId)}
                      aria-pressed={selected}
                      aria-label={`Select Body ${body.ordinal}`}
                      data-testid={`body-select-${body.ordinal - 1}`}
                      className="flex grow items-baseline gap-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                    >
                      <span className="w-5 shrink-0 font-data text-xs tabular-nums text-gauge">
                        {String(body.ordinal).padStart(2, "0")}
                      </span>
                      <span className="grow truncate font-data text-base text-mist">
                        Body {body.ordinal}
                      </span>
                      <span className="shrink-0 truncate font-body text-xs text-gauge">
                        {body.name}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
