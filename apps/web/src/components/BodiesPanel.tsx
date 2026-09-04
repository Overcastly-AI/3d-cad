/**
 * The Bodies list (multi-body §MB-1) — the part's solid bodies as a title-block
 * read-out, the feature tree's quiet twin. A part is usually one body; when a
 * `merge: false` add (or an import) starts a second, this names each body by its
 * base feature and lets you select one (which highlights it via the base
 * feature's selection + opens its editor — the same select the tree row does).
 *
 * UI-W2 (part half) adds the VIEW controls, in the vocabulary the assembly half
 * established — same eye forms, same disclosure rule, same verbs — because a
 * second dialect for "is this drawn" would be the design-system failure this
 * repo reviews as a defect:
 *
 *  · the EYE at the row's head, always present, one click;
 *  · SOLID · GHOST · HIDE (`SegmentedControl`) disclosed under the ADDRESSED
 *    row only. The assembly half tried hover-reveal and the arithmetic refused
 *    (a row that grows on hover reflows the list under the cursor); disclosure
 *    costs nothing at rest. On the PART side "addressed" is the row you last
 *    touched the eye of — deliberately NOT "selected", because selecting a body
 *    row selects its base feature, which opens that feature's editor, and you
 *    should not have to start editing an extrude to ghost the solid it made;
 *  · ISOLATE as a right-click verb with `V` / `⇧V`, `⇧V` doubling as the way
 *    back so no chord can strand you in an empty scene.
 *
 * Ghost is offered HERE and not on the sketch/origin rows because ghost means
 * "see through the solid to what is behind it" — the founder's actual case —
 * and a datum plane or a scribe line has nothing to see through.
 *
 * The eye is withheld, with its reason, when the fused mesh cannot be split per
 * body (`partitioned`): an eye that would hide the wrong solid is worse than an
 * eye that says why it is unavailable.
 */
import {
  ContextMenu,
  EyeGhostIcon,
  EyeIcon,
  EyeOffIcon,
  FieldRow,
  IsolateIcon,
  Panel,
  PanelSection,
  SegmentedControl,
  type ContextMenuSection,
} from "@loft/design";
import { useEffect, useMemo, useState } from "react";

import { lumpBadgeLabel, type BodyInfo } from "../features/bodies";
import type { VisibilityMode } from "../viewport/instanceVisibility";
import {
  bodyKey,
  bodyMode,
  hiddenBodyCount,
  usePartViewStore,
  type PartBodyView,
} from "../viewport/partView";

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

/** The three stops, in the order the eye walks them (the assembly's order). */
const OPACITY_OPTIONS = [
  { value: "solid", label: "Solid" },
  { value: "ghost", label: "Ghost" },
  { value: "hidden", label: "Hide" },
] as const satisfies readonly { value: VisibilityMode; label: string }[];

/** The eye's three forms — the assembly half's glyphs, unchanged. */
const EYE_GLYPH: Record<VisibilityMode, typeof EyeIcon> = {
  solid: EyeIcon,
  ghost: EyeGhostIcon,
  hidden: EyeOffIcon,
};

/** What clicking the eye will do, in the interface's plain-verb voice. */
function eyeAction(mode: VisibilityMode, label: string): string {
  return mode === "hidden" ? `Show ${label}` : `Hide ${label}`;
}

export function BodiesPanel({
  bodies,
  lumpsByFeature,
  selectedFeatureId,
  onSelectBody,
}: BodiesPanelProps) {
  const eyebrow = `Bodies · ${bodies.length}`;
  const view = usePartViewStore((state) => state.view);
  // GHOST-1: while a sketch is open, an untouched body is DRAWN ghosted, so the
  // row has to say GHOST. A row showing SOLID over a see-through solid is the
  // eye disagreeing with the pixels, which is the defect this panel's whole
  // derivation exists to prevent.
  const sketchOpen = usePartViewStore((state) => state.sketchOpen);
  const addressedKey = usePartViewStore((state) => state.addressedKey);
  const partitioned = usePartViewStore((state) => state.partitioned);
  const setBodies = usePartViewStore((state) => state.setBodies);
  const setAddressed = usePartViewStore((state) => state.setAddressed);
  const toggle = usePartViewStore((state) => state.toggle);
  const setMode = usePartViewStore((state) => state.setMode);
  const isolate = usePartViewStore((state) => state.isolate);
  const showAll = usePartViewStore((state) => state.showAll);
  const [menu, setMenu] = useState<{
    body: PartBodyView;
    x: number;
    y: number;
  } | null>(null);

  // The scene's view of the body set: keys in tree order plus each body's lump
  // count, which is what lets the renderer split ONE fused GLB back into per-
  // body face sets. Published from here because this is where both facts
  // already meet (`viewport/bodyPartition.ts` explains the arithmetic).
  const bodyViews = useMemo<PartBodyView[]>(
    () =>
      bodies.map((body) => ({
        key: bodyKey(body.baseFeatureId),
        label: `Body ${body.ordinal}`,
        lumps: lumpsByFeature?.get(body.baseFeatureId) ?? 1,
      })),
    [bodies, lumpsByFeature],
  );
  useEffect(() => {
    setBodies(bodyViews);
  }, [bodyViews, setBodies]);

  const hiddenCount = hiddenBodyCount(view, bodyViews);

  const buildSections = (body: PartBodyView): ContextMenuSection[] => {
    const hidden = bodyMode(view, body.key, sketchOpen) === "hidden";
    return [
      {
        key: "view",
        label: body.label,
        items: [
          {
            key: "hide",
            label: hidden ? "Show" : "Hide",
            icon: hidden ? <EyeIcon /> : <EyeOffIcon />,
            shortcut: "V",
            disabled: !partitioned,
            disabledReason: "This mesh cannot be split per body",
            onSelect: () => toggle(body.key),
            "data-testid": "body-ctx-hide",
          },
          {
            key: "isolate",
            label: "Isolate",
            icon: <IsolateIcon />,
            shortcut: "⇧V",
            disabled: bodyViews.length < 2 || !partitioned,
            disabledReason:
              bodyViews.length < 2
                ? "This part has only one body"
                : "This mesh cannot be split per body",
            onSelect: () => isolate(body.key),
            "data-testid": "body-ctx-isolate",
          },
          {
            key: "show-all",
            label: "Show all",
            icon: <EyeIcon />,
            disabled: hiddenCount === 0,
            disabledReason: "Every body is already shown",
            onSelect: showAll,
            "data-testid": "body-ctx-show-all",
          },
        ],
      },
    ];
  };

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
              {bodies.map((body, index) => {
                const selected = body.baseFeatureId === selectedFeatureId;
                const lumpBadge = lumpBadgeLabel(
                  lumpsByFeature?.get(body.baseFeatureId),
                );
                const key = bodyKey(body.baseFeatureId);
                const label = `Body ${body.ordinal}`;
                const mode = bodyMode(view, key, sketchOpen);
                const EyeGlyph = EYE_GLYPH[mode];
                const bodyView = bodyViews[index];
                return (
                  <li
                    key={body.baseFeatureId}
                    className={`border-l-2 ${
                      selected ? "border-brass" : "border-transparent"
                    }`}
                    data-testid="body-row"
                    data-visibility={mode}
                    onContextMenu={
                      bodyView === undefined
                        ? undefined
                        : (event) => {
                            event.preventDefault();
                            setAddressed(key);
                            setMenu({
                              body: bodyView,
                              x: event.clientX,
                              y: event.clientY,
                            });
                          }
                    }
                  >
                    {/* One 24px band, the tree's own row rhythm — the bodies
                        list and the feature list are the same instrument and
                        were two different heights (density pass 2026-08-28). */}
                    <div className="flex min-h-target-dense items-center gap-2 py-0 pr-3 pl-[10px]">
                      <button
                        type="button"
                        onClick={() => {
                          setAddressed(key);
                          toggle(key);
                        }}
                        disabled={!partitioned}
                        aria-pressed={mode !== "hidden"}
                        aria-label={eyeAction(mode, label)}
                        title={
                          partitioned
                            ? eyeAction(mode, label)
                            : "This mesh cannot be split per body"
                        }
                        data-testid={`body-visibility-${body.ordinal - 1}`}
                        // Rest is quiet (`gauge`, 7.3:1 on anvil); a row whose
                        // view has been TOUCHED lifts to `mist` (13.2:1) so it
                        // is findable when scanning. Deliberately not brass —
                        // the accent is spent on selection and the travel stop.
                        className={`flex min-h-target-dense min-w-target-dense shrink-0 items-center justify-center self-center rounded-sm outline-none transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass disabled:cursor-default disabled:opacity-50 ${
                          mode === "solid" ? "text-gauge" : "text-mist"
                        }`}
                      >
                        <EyeGlyph size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setAddressed(key);
                          onSelectBody(body.baseFeatureId);
                        }}
                        aria-pressed={selected}
                        aria-label={`Select ${label}`}
                        data-testid={`body-select-${body.ordinal - 1}`}
                        // Measured 262x19.5 before this pass — under the 24px
                        // dense floor (`target.dense`, WCAG 2.2 SC 2.5.8). It
                        // is the row's PRIMARY action, so it takes the row's
                        // full height rather than floating on a baseline in it.
                        className="flex min-h-target-dense grow items-center gap-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                      >
                        <span className="w-5 shrink-0 font-data text-xs tabular-nums text-gauge">
                          {String(body.ordinal).padStart(2, "0")}
                        </span>
                        <span
                          className={`grow truncate font-data text-sm ${
                            mode === "hidden" ? "text-gauge" : "text-mist"
                          }`}
                        >
                          {label}
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
                    </div>
                    {(addressedKey === key || selected) && partitioned ? (
                      // The addressed body's opacity stops. ADDRESSED, not
                      // SELECTED: selecting a body row selects its base feature,
                      // which OPENS that feature's editor — so gating the view
                      // control on selection would mean you could not change how
                      // a body is drawn without starting to edit the extrude
                      // that made it. Touching the row's eye addresses it, and
                      // the stops disclose under it. Only one row is addressed
                      // at a time, so the per-stop test ids need no ordinal
                      // suffix; the wrapper carries it for QA.
                      // Caption BESIDE the control, not stacked over it — the
                      // last stacked form label in the overlay panels after the
                      // 2026-08-28 density pass, and one loose row is all it
                      // takes for a panel to read as a dialog again. The
                      // control keeps its own accessible name (`hideLabel`),
                      // and the row's visible caption states the same word.
                      <FieldRow
                        label="Opacity"
                        className="pl-8"
                        data-testid={`body-opacity-${body.ordinal - 1}`}
                      >
                        <SegmentedControl<VisibilityMode>
                          label="Opacity"
                          hideLabel
                          value={mode}
                          options={OPACITY_OPTIONS.map((option) => ({
                            ...option,
                            "data-testid": `body-opacity-${option.value}`,
                            "aria-label": `${option.label} — ${label}`,
                          }))}
                          onChange={(next) => {
                            setAddressed(key);
                            setMode(key, next);
                          }}
                        />
                      </FieldRow>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          )}
        </PanelSection>
      </Panel>
      {menu !== null ? (
        <ContextMenu
          open
          x={menu.x}
          y={menu.y}
          aria-label={`Actions for ${menu.body.label}`}
          data-testid="body-context-menu"
          sections={buildSections(menu.body)}
          onClose={() => setMenu(null)}
        />
      ) : null}
    </aside>
  );
}
