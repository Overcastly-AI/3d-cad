/**
 * The Bodies list (multi-body §MB-1) — the part's solid bodies as a title-block
 * read-out, the feature tree's quiet twin. A part is usually one body; when a
 * `merge: false` add (or an import) starts a second, this names each body by its
 * base feature and lets you select one (which highlights it via the base
 * feature's selection + opens its editor — the same select the tree row does).
 * Per-body pick-highlight in the viewport is MB-4; this stays a dense read-out.
 */
import { Panel, PanelSection } from "@loft/design";

import { lumpBadgeLabel, type BodyInfo } from "../features/bodies";

export interface BodiesPanelProps {
  bodies: readonly BodyInfo[];
  /** Per-body disjoint-solid (lump) count from the evaluate wire (§MB-4c), keyed
   * by base feature id. A body with `lumps > 1` gets a quiet multi-solid badge;
   * absent/unknown → no badge. Optional so a caller without an evaluation (an
   * empty tree) can omit it. */
  lumpsByFeature?: ReadonlyMap<string, number>;
  /** Selected feature id (a body row lights its brass left-rule when its base
   * feature is selected). */
  selectedFeatureId: string | null;
  /** Select a body by its base feature id (highlights + opens its editor). */
  onSelectBody: (baseFeatureId: string) => void;
}

export function BodiesPanel({
  bodies,
  lumpsByFeature,
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
                const lumpBadge = lumpBadgeLabel(
                  lumpsByFeature?.get(body.baseFeatureId),
                );
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
                      {lumpBadge !== null ? (
                        <span
                          data-testid={`body-lumps-${body.ordinal - 1}`}
                          title="A disjoint multi-solid body"
                          className="inline-flex shrink-0 items-center rounded-sm border border-etch px-1 font-display text-2xs uppercase tracking-[0.12em] text-gauge tabular-nums"
                        >
                          {lumpBadge}
                        </span>
                      ) : null}
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
