/**
 * The assembly tree as a title block: two ruled sections — COMPONENTS (the
 * instances, each a drafting balloon number + name + a grounded/anchor toggle)
 * and MATES (the joints, each named with the two balloons it relates). The
 * balloon number is the shared device that ties this DOM tree to the WebGL
 * viewport (same number floats on the instance). Selecting a component row
 * addresses it (brass left-rule) and highlights it in the viewport; the
 * grounded row carries the anchor mark. A mate that failed to resolve or
 * conflicts is flagged inline, read from the typed diagnosis — never a parsed
 * message.
 *
 * UI-W2 adds the VIEW controls to each component row (design
 * `ui-wave-tool-grade.md` Surface 2). Two controls, two jobs, and the split is
 * the point:
 *
 *  · the EYE, always present at the row's head — one click, the learned symbol,
 *    drawn in our hand (see `icons.tsx`). It reports all three stops as a SHAPE
 *    — pupil punched / lens broken and empty / lens struck through — so an
 *    unselected ghosted row still declares itself at a glance rather than
 *    relying on a tint that a screenshot review would call redundant and a
 *    contrast meter would not;
 *  · the SOLID · GHOST · HIDE `SegmentedControl`, disclosed under the ADDRESSED
 *    row. The design sketch put it on hover; the arithmetic refuses. The panel
 *    is 320px, the row already spends most of it on the balloon, name, stamp,
 *    Ground and Remove, and a three-cell control needs ~120px. A row that GREW
 *    on hover would reflow the list under the cursor, and reserving the height
 *    on every row doubles a deliberately dense list. Disclosing it for the
 *    selected instance costs nothing at rest, is keyboard-reachable, and matches
 *    what selection already means here: the addressed component.
 *
 * ISOLATE is a verb, not a glyph — it lives in the row's right-click menu with
 * its accelerator, because it is infrequent and destructive to view state.
 *
 * Visibility is VIEW state and is deliberately NOT gated on `busy`: it writes
 * nothing to the server, so it keeps working while a mate or a ground toggle is
 * in flight.
 */
import {
  EyeGhostIcon,
  EyeIcon,
  EyeOffIcon,
  Panel,
  PanelSection,
  SegmentedControl,
} from "@loft/design";

import type {
  AssemblyGraphResponse,
  EvaluateAssemblyResult,
  InstanceResponse,
  MateResponse,
} from "../api/assemblies";
import { mateDetail, mateLabel, mateInstanceIds } from "../assembly/mates";
import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  visibilityModeOf,
  type VisibilityMode,
  type VisibilityState,
} from "../viewport/instanceVisibility";

export interface AssemblyTreePanelProps {
  graph: AssemblyGraphResponse | undefined;
  graphError: Error | null;
  evaluation: EvaluateAssemblyResult | undefined;
  selectedInstanceId: string | null;
  /** Instances in a MEASURED clash from the last check — badged red inline. */
  clashingInstanceIds: ReadonlySet<string>;
  /**
   * Instances the last check could not measure (the exact boolean failed, their
   * bounding volumes overlap) and that are in no measured clash. They earn a
   * quiet dashed UNVERIFIED stamp, never the red CLASH badge: "Clash" is a
   * measurement claim, and on these pairs the kernel has no measurement — the
   * mirror image of the false-clear the panel already refuses to print.
   */
  unverifiedInstanceIds: ReadonlySet<string>;
  /** Per-instance view stops (UI-W2) — which rows are ghosted or hidden. */
  visibility: VisibilityState;
  /** The eye: draw / don't draw this instance, keeping its opacity stop. */
  onToggleVisibility: (instanceId: string) => void;
  /** The three-stop control: write one instance's opacity stop. */
  onSetVisibility: (instanceId: string, mode: VisibilityMode) => void;
  /** Right-click a component row → the view + edit verbs at the pointer. */
  onInstanceContextMenu?: (
    instance: InstanceResponse,
    x: number,
    y: number,
  ) => void;
  onSelectInstance: (instanceId: string) => void;
  onToggleGrounded: (instance: InstanceResponse) => void;
  onDeleteInstance: (instance: InstanceResponse) => void;
  onDeleteMate: (mate: MateResponse) => void;
  busy: boolean;
}

/** The three stops, in the order the eye walks them. */
const OPACITY_OPTIONS = [
  { value: "solid", label: "Solid" },
  { value: "ghost", label: "Ghost" },
  { value: "hidden", label: "Hide" },
] as const satisfies readonly { value: VisibilityMode; label: string }[];

/**
 * The eye's three forms. `gauge` ink measures 7.3:1 on the panel's `anvil` and
 * 8.0:1 on the `carbide` seat a selected row takes — both clear WCAG-AA text
 * contrast, so the glyph is never the marginal cue the 2026-07-30 audit found
 * elsewhere. Hover lifts to `mist` (13.2:1 on anvil).
 */
const EYE_GLYPH: Record<VisibilityMode, typeof EyeIcon> = {
  solid: EyeIcon,
  ghost: EyeGhostIcon,
  hidden: EyeOffIcon,
};

/** What clicking the eye will do, in the interface's plain-verb voice. */
function eyeAction(mode: VisibilityMode, name: string): string {
  return mode === "hidden" ? `Show ${name}` : `Hide ${name}`;
}

export function AssemblyTreePanel({
  graph,
  graphError,
  evaluation,
  selectedInstanceId,
  clashingInstanceIds,
  unverifiedInstanceIds,
  visibility,
  onToggleVisibility,
  onSetVisibility,
  onInstanceContextMenu,
  onSelectInstance,
  onToggleGrounded,
  onDeleteInstance,
  onDeleteMate,
  busy,
}: AssemblyTreePanelProps) {
  const unit = useDocumentLengthUnit();
  const instances = graph?.instances ?? [];
  const mates = graph?.mates ?? [];
  // Counts fold into the section eyebrows (the INSTANCES footer cell in the
  // inspector was redundant with this list; UI-REVIEW 2026-07-16, Track B).
  const componentsEyebrow =
    instances.length > 0 ? `Components · ${instances.length}` : "Components";
  const matesEyebrow = mates.length > 0 ? `Mates · ${mates.length}` : "Mates";
  // Balloon number = 1-based position in the (order_index-sorted) instance list.
  const balloonById = new Map(instances.map((i, index) => [i.id, index + 1]));
  const failedMateIds = new Set(
    (evaluation?.mate_errors ?? []).map((e) => e.mate_id),
  );
  const conflictingMateIds = new Set(
    evaluation?.diagnosis?.conflicting_mates ?? [],
  );

  return (
    <aside
      className="flex w-full flex-col gap-3"
      aria-label="Assembly tree"
      data-testid="assembly-tree"
    >
      <Panel>
        <PanelSection eyebrow={componentsEyebrow}>
          {graphError ? (
            <p
              role="alert"
              data-testid="assembly-tree-error"
              className="px-3 py-3 font-body text-xs text-flag"
            >
              {graphError.message}
            </p>
          ) : instances.length === 0 ? (
            <p
              data-testid="assembly-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No parts yet. Add a part to start the assembly, then ground one to
              fix it to the bench.
            </p>
          ) : (
            <ul className="py-1" data-testid="instance-list">
              {instances.map((instance) => {
                const selected = selectedInstanceId === instance.id;
                const clashing = clashingInstanceIds.has(instance.id);
                const unverified = unverifiedInstanceIds.has(instance.id);
                const balloon = balloonById.get(instance.id) ?? 0;
                const mode = visibilityModeOf(visibility, instance.id);
                const EyeGlyph = EYE_GLYPH[mode];
                return (
                  <li
                    key={instance.id}
                    data-testid="instance-row"
                    data-instance-id={instance.id}
                    data-visibility={mode}
                    onContextMenu={
                      onInstanceContextMenu
                        ? (event) => {
                            event.preventDefault();
                            onInstanceContextMenu(
                              instance,
                              event.clientX,
                              event.clientY,
                            );
                          }
                        : undefined
                    }
                    className={`border-l-2 ${
                      selected
                        ? "border-brass bg-carbide"
                        : "border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2 px-2 py-1">
                      <button
                        type="button"
                        onClick={() => onToggleVisibility(instance.id)}
                        aria-pressed={mode !== "hidden"}
                        aria-label={eyeAction(mode, instance.name)}
                        title={eyeAction(mode, instance.name)}
                        data-testid={`instance-visibility-${instance.id}`}
                        // Rest is quiet (`gauge`); a row whose view has been
                        // TOUCHED lifts to `mist` so it is findable when
                        // scanning 21 rows. Deliberately not brass: the accent
                        // is spent on selection/grounded/travel-stop, and an
                        // assembly with a dozen hidden parts would otherwise
                        // read as a wall of accent. Measured on `anvil`:
                        // gauge 7.3:1, mist 13.2:1, brass hover 7.9:1 — the
                        // shape difference (punched / hollow / struck pupil)
                        // carries the state, the ink is the second cue.
                        className={`flex min-h-target-dense min-w-target-dense shrink-0 items-center justify-center rounded-sm outline-none transition-colors duration-fast hover:text-brass focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brass ${
                          mode === "solid" ? "text-gauge" : "text-mist"
                        }`}
                      >
                        <EyeGlyph size={16} />
                      </button>
                      <button
                        type="button"
                        onClick={() => onSelectInstance(instance.id)}
                        data-testid={`instance-select-${instance.id}`}
                        className="flex min-w-0 grow items-center gap-2 text-left outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
                      >
                        <span
                          aria-hidden
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border font-display text-2xs tabular-nums ${
                            instance.grounded
                              ? "border-brass text-brass"
                              : "border-etch text-gauge"
                          }`}
                        >
                          {instance.grounded ? "⏚" : balloon}
                        </span>
                        <span
                          // A hidden component's name recedes to `gauge` (7.3:1
                          // on anvil — still AA, still readable: it is hidden,
                          // not disabled). The struck-through eye beside it is
                          // the load-bearing cue, so this dim is a SECOND cue
                          // and never the only one.
                          className={`truncate font-body text-sm ${
                            mode === "hidden" ? "text-gauge" : "text-mist"
                          }`}
                        >
                          {instance.name}
                        </span>
                      </button>
                      {clashing ? (
                        <span
                          data-testid={`instance-clash-${instance.id}`}
                          title="Interferes with another part"
                          className="shrink-0 rounded-sm border border-flag px-1 font-display text-2xs uppercase tracking-[0.14em] text-flag"
                        >
                          Clash
                        </span>
                      ) : unverified ? (
                        <span
                          data-testid={`instance-unverified-${instance.id}`}
                          title="The exact overlap could not be measured — inspect this pair"
                          className="shrink-0 rounded-sm border border-dashed border-etch px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge"
                        >
                          Unverified
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => onToggleGrounded(instance)}
                        disabled={busy}
                        aria-pressed={instance.grounded}
                        data-testid={`instance-ground-${instance.id}`}
                        className={`shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50 ${
                          instance.grounded
                            ? "text-brass"
                            : "text-gauge hover:text-mist"
                        }`}
                      >
                        {instance.grounded ? "Grounded" : "Ground"}
                      </button>
                      <button
                        type="button"
                        onClick={() => onDeleteInstance(instance)}
                        disabled={busy}
                        aria-label={`Remove ${instance.name}`}
                        data-testid={`instance-delete-${instance.id}`}
                        className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
                      >
                        Remove
                      </button>
                    </div>
                    {selected ? (
                      // The addressed component's opacity stops. Only one row
                      // renders this at a time, so the per-stop test ids need no
                      // instance suffix; the wrapper carries the id for QA.
                      <div
                        className="px-2 pb-2 pl-8"
                        data-testid={`instance-opacity-${instance.id}`}
                      >
                        <SegmentedControl<VisibilityMode>
                          label="Opacity"
                          value={mode}
                          options={OPACITY_OPTIONS.map((option) => ({
                            ...option,
                            "data-testid": `instance-opacity-${option.value}`,
                            "aria-label": `${option.label} — ${instance.name}`,
                          }))}
                          onChange={(next) =>
                            onSetVisibility(instance.id, next)
                          }
                        />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </PanelSection>

        <PanelSection eyebrow={matesEyebrow}>
          {mates.length === 0 ? (
            <p
              data-testid="mates-empty"
              className="px-3 py-3 font-body text-xs text-gauge"
            >
              No mates yet. Pick a face on each of two parts for Coincident, a
              hole edge on each for Concentric, or two parts for Lock.
            </p>
          ) : (
            <ul className="py-1" data-testid="mate-list">
              {mates.map((mate) => {
                const [a, b] = mateInstanceIds(mate.mate);
                const failed = failedMateIds.has(mate.id);
                const conflicting = conflictingMateIds.has(mate.id);
                const sick = failed || conflicting;
                return (
                  <li
                    key={mate.id}
                    data-testid="mate-row"
                    data-mate-id={mate.id}
                    className="flex items-center gap-2 px-2 py-1"
                  >
                    <span className="min-w-0 grow">
                      <span
                        className={`block font-body text-sm ${
                          sick ? "text-flag" : "text-mist"
                        }`}
                      >
                        {mateLabel(mate.mate)}
                        {(() => {
                          const detail = mateDetail(mate.mate, unit);
                          return detail ? (
                            <span
                              className="ml-1.5 font-data text-2xs tabular-nums text-brass"
                              data-testid="mate-value-echo"
                            >
                              {detail}
                            </span>
                          ) : null;
                        })()}
                      </span>
                      <span className="block font-data text-2xs tabular-nums text-gauge">
                        ①{balloonById.get(a) ?? "?"} · ②
                        {balloonById.get(b) ?? "?"}
                        {failed
                          ? " · unresolved"
                          : conflicting
                            ? " · conflict"
                            : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => onDeleteMate(mate)}
                      disabled={busy}
                      aria-label={`Remove ${mateLabel(mate.mate)} mate`}
                      data-testid={`mate-delete-${mate.id}`}
                      className="shrink-0 rounded-sm px-1 font-display text-2xs uppercase tracking-[0.14em] text-gauge outline-none hover:text-flag focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </PanelSection>
      </Panel>
    </aside>
  );
}
