/**
 * The mirror components dialog (ASM-MIRROR-COMPONENT): SolidWorks' Mirror
 * Components and Fusion's Mirror on components, in one card.
 *
 * The components to mirror are ticked in a list (the selected component is
 * ticked when the dialog opens). Each ticked part is mirrored as a COPY of
 * itself, right for a symmetric part, or as an OPPOSITE HAND (SolidWorks'
 * "Create opposite hand version"): a derived part, the source reflected, that
 * follows the source's edits and bills as its own item. A sub-assembly is
 * mirrored as a copy. The plane is an origin plane (with an offset, typed as
 * an expression) or a planar face picked in the viewport.
 *
 * Keyboard: Enter commits, Escape cancels (a pick in progress first).
 */
import { Panel, PanelActionCell } from "@loft/design";
import type { KeyboardEvent } from "react";

import type { InstanceResponse } from "../api/assemblies";
import {
  buildMirror,
  canBeOppositeHand,
  type MirrorForm,
  PLANE_LABEL,
  type PlaneChoice,
} from "../assembly/mirrors";
import { lengthEntryExpression } from "../features/expr";
import { EditorCard } from "./EditorCard";
import { ExprField, PickButton, Section } from "./PatternPanel";

export interface MirrorPanelProps {
  mode: "create" | "edit";
  form: MirrorForm;
  onChange: (form: MirrorForm) => void;
  instances: readonly InstanceResponse[];
  /** A component or nested part's display name. */
  nameOf: (instanceId: string) => string;
  /** A face pick is armed in the viewport. */
  picking: boolean;
  onPick: (armed: boolean) => void;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
  onCancel: () => void;
}

const PLANES: readonly PlaneChoice[] = ["yz", "zx", "xy", "face"];

export function MirrorPanel({
  mode,
  form,
  onChange,
  instances,
  nameOf,
  picking,
  onPick,
  submitting,
  error,
  onSubmit,
  onCancel,
}: MirrorPanelProps) {
  const built = buildMirror(form);
  const problem = "error" in built ? built.error : null;
  const set = (patch: Partial<MirrorForm>) => onChange({ ...form, ...patch });
  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (picking) onPick(false);
      else onCancel();
    } else if (event.key === "Enter" && problem === null && !submitting) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <EditorCard
      seat="right"
      onKeyDown={onKeyDown}
      header={
        <div className="border border-b-0 border-hairline bg-anvil px-3 pb-2 pt-3">
          <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "edit" ? "Edit mirror" : "Mirror components"}
          </h2>
        </div>
      }
      footer={
        <div className="border border-t-0 border-hairline bg-anvil">
          {error !== null || problem !== null ? (
            <p
              role={error !== null ? "alert" : undefined}
              data-testid="mirror-error"
              className={`border-b border-hairline px-3 py-2 font-body text-xs ${
                error !== null ? "text-flag" : "text-gauge"
              }`}
            >
              {error ?? problem}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="mirror-cancel"
              disabled={submitting}
              onClick={onCancel}
            />
            <PanelActionCell
              label={submitting ? "Saving…" : "OK"}
              caption="Enter"
              data-testid="mirror-ok"
              aria-busy={submitting}
              disabled={problem !== null || submitting}
              disabledReason={problem ?? undefined}
              onClick={onSubmit}
            />
          </div>
        </div>
      }
    >
      <Panel aria-label="Mirror components" data-testid="mirror-dialog">
        <Section title="Components">
          <ul
            className="max-h-[9rem] overflow-y-auto"
            data-testid="mirror-seeds"
          >
            {instances.map((instance) => {
              const chosen = form.seeds.includes(instance.id);
              const hand = canBeOppositeHand(instance);
              return (
                <li key={instance.id} className="flex items-center gap-2">
                  <label className="flex min-w-0 grow items-center gap-2 py-0.5 font-body text-xs text-mist">
                    <input
                      type="checkbox"
                      checked={chosen}
                      data-testid={`mirror-seed-${instance.id}`}
                      onChange={() =>
                        set({ seeds: toggle(form.seeds, instance.id) })
                      }
                    />
                    <span className="truncate">{instance.name}</span>
                  </label>
                  {chosen ? (
                    <label
                      className="flex shrink-0 items-center gap-1 font-body text-2xs text-gauge"
                      title={
                        hand
                          ? "A derived part, this one reflected: for a part that is not symmetric"
                          : "A sub-assembly is mirrored as a copy"
                      }
                    >
                      <input
                        type="checkbox"
                        disabled={!hand}
                        checked={form.opposite.includes(instance.id)}
                        data-testid={`mirror-opposite-${instance.id}`}
                        onChange={() =>
                          set({ opposite: toggle(form.opposite, instance.id) })
                        }
                      />
                      Opposite hand
                    </label>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <p className="mt-1 font-body text-2xs text-gauge">
            A copy reuses the part (for a symmetric part); an opposite hand is a
            new, reflected part that follows the source.
          </p>
        </Section>
        <Section title="Mirror plane">
          <div className="flex items-center gap-2">
            <select
              value={form.plane}
              data-testid="mirror-plane"
              onChange={(event) =>
                set({ plane: event.target.value as PlaneChoice })
              }
              className="rounded-sm border border-etch bg-carbide px-1 py-0.5 font-body text-xs text-mist"
            >
              {PLANES.map((plane) => (
                <option key={plane} value={plane}>
                  {PLANE_LABEL[plane]}
                </option>
              ))}
            </select>
            {form.plane === "face" ? (
              <PickButton
                label={form.face === null ? "Pick face" : "Re-pick"}
                armed={picking}
                testId="mirror-pick-face"
                onClick={() => onPick(!picking)}
              />
            ) : null}
          </div>
          {form.plane === "face" ? (
            form.face !== null ? (
              <p
                className="mt-1 truncate font-body text-2xs text-gauge"
                data-testid="mirror-face"
              >
                Face on {nameOf(form.face.instanceId)}
              </p>
            ) : null
          ) : (
            <ExprField
              label="Offset"
              value={form.offset}
              testId="mirror-offset"
              expression={(offset) => lengthEntryExpression(offset, "mm")}
              onChange={(offset) => set({ offset })}
            />
          )}
        </Section>
      </Panel>
    </EditorCard>
  );
}
