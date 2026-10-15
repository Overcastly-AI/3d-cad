/**
 * The component pattern dialog (ASM-A3-PATTERN): Fusion's Pattern Components,
 * Onshape's linear / circular pattern and Replicate, SolidWorks' component
 * patterns, in one card.
 *
 * Three kinds. LINEAR and CIRCULAR take a direction or axis (an origin axis,
 * or an edge picked in the viewport: a straight edge runs along it, a circle
 * turns about its centre), a count and a spacing or total angle, each typed as
 * an expression (`360 deg / 8` reads as 45°). ON HOLES (pattern-driven) takes
 * the hole the seed sits in and, optionally, further instances of the same
 * part: one copy goes to every hole of that size on that face, and the count
 * follows the part. The components to repeat are ticked in a list; the
 * selected component is ticked when the dialog opens.
 *
 * Keyboard: Enter commits, Escape cancels (a pick in progress first).
 */
import { Panel, PanelActionCell } from "@loft/design";
import type { KeyboardEvent, ReactNode } from "react";

import type { InstanceResponse } from "../api/assemblies";
import {
  type AxisChoice,
  buildPattern,
  PATTERN_KIND_LABEL,
  type PatternForm,
  type PatternKind,
  samePartInstances,
} from "../assembly/patterns";
import type { PatternPickTarget } from "../assembly/patternStore";
import { evaluateExpression } from "../features/expr";
import { EditorCard } from "./EditorCard";

export interface PatternPanelProps {
  mode: "create" | "edit";
  form: PatternForm;
  onChange: (form: PatternForm) => void;
  instances: readonly InstanceResponse[];
  /** A component or nested part's display name. */
  nameOf: (instanceId: string) => string;
  /** The pick armed in the viewport, or null. */
  picking: PatternPickTarget | null;
  onPick: (target: PatternPickTarget | null) => void;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
  onCancel: () => void;
}

const KINDS: readonly PatternKind[] = ["linear", "circular", "hole"];
const AXES: readonly { value: AxisChoice; label: string }[] = [
  { value: "x", label: "X axis" },
  { value: "y", label: "Y axis" },
  { value: "z", label: "Z axis" },
  { value: "edge", label: "Picked edge" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-hairline px-3 py-2 first:border-t-0">
      <h3 className="mb-1 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
        {title}
      </h3>
      {children}
    </section>
  );
}

/** "= 45°" under a typed expression, or nothing while it does not read. */
function reading(text: string): string | null {
  try {
    const q = evaluateExpression(text, new Map());
    const unit = q.kind === "length" ? " mm" : q.kind === "angle" ? "°" : "";
    return `= ${Number(q.value.toFixed(6))}${unit}`;
  } catch {
    return null;
  }
}

function ExprField({
  label,
  value,
  onChange,
  testId,
}: {
  label: string;
  value: string;
  onChange: (text: string) => void;
  testId: string;
}) {
  const hint = reading(value);
  return (
    <label className="flex items-center gap-2 py-0.5">
      <span className="w-[4rem] shrink-0 font-body text-xs text-mist">
        {label}
      </span>
      <input
        type="text"
        value={value}
        spellCheck={false}
        data-testid={testId}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-0 grow rounded-sm border border-etch bg-carbide px-2 py-1 font-data text-xs text-mist outline-none focus:border-brass"
      />
      <span
        className="w-[4rem] shrink-0 font-data text-2xs tabular-nums text-brass"
        data-testid={`${testId}-reading`}
      >
        {hint ?? ""}
      </span>
    </label>
  );
}

function PickButton({
  label,
  armed,
  onClick,
  testId,
}: {
  label: string;
  armed: boolean;
  onClick: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={armed}
      data-testid={testId}
      onClick={onClick}
      className={`rounded-sm border px-2 py-0.5 font-display text-2xs uppercase tracking-[0.12em] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass ${
        armed
          ? "border-brass text-brass"
          : "border-etch text-mist hover:border-brass"
      }`}
    >
      {armed ? "Picking…" : label}
    </button>
  );
}

export function PatternPanel({
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
}: PatternPanelProps) {
  const built = buildPattern(form);
  const problem = "error" in built ? built.error : null;
  const set = (patch: Partial<PatternForm>) => onChange({ ...form, ...patch });
  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  const drivers =
    form.hole === null
      ? []
      : samePartInstances(instances, form.hole.instanceId);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (picking !== null) onPick(null);
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
            {mode === "edit" ? "Edit pattern" : "Pattern components"}
          </h2>
        </div>
      }
      footer={
        <div className="border border-t-0 border-hairline bg-anvil">
          {error !== null || problem !== null ? (
            <p
              role={error !== null ? "alert" : undefined}
              data-testid="pattern-error"
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
              data-testid="pattern-cancel"
              disabled={submitting}
              onClick={onCancel}
            />
            <PanelActionCell
              label={submitting ? "Saving…" : "OK"}
              caption="Enter"
              data-testid="pattern-ok"
              aria-busy={submitting}
              disabled={problem !== null || submitting}
              disabledReason={problem ?? undefined}
              onClick={onSubmit}
            />
          </div>
        </div>
      }
    >
      <Panel aria-label="Pattern components" data-testid="pattern-dialog">
        <Section title="Type">
          <div
            role="radiogroup"
            aria-label="Type"
            className="grid grid-cols-3 gap-1"
          >
            {KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                role="radio"
                aria-checked={form.kind === kind}
                disabled={mode === "edit" && form.kind !== kind}
                data-testid={`pattern-kind-${kind}`}
                onClick={() => set({ kind })}
                className={`rounded-sm border px-2 py-1 font-display text-2xs uppercase tracking-[0.12em] outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-40 ${
                  form.kind === kind
                    ? "border-brass text-brass"
                    : "border-etch text-mist hover:border-brass"
                }`}
              >
                {PATTERN_KIND_LABEL[kind]}
              </button>
            ))}
          </div>
        </Section>
        <Section title="Components">
          <ul
            className="max-h-[9rem] overflow-y-auto"
            data-testid="pattern-seeds"
          >
            {instances.map((instance) => (
              <li key={instance.id}>
                <label className="flex items-center gap-2 py-0.5 font-body text-xs text-mist">
                  <input
                    type="checkbox"
                    checked={form.seeds.includes(instance.id)}
                    data-testid={`pattern-seed-${instance.id}`}
                    onChange={() =>
                      set({ seeds: toggle(form.seeds, instance.id) })
                    }
                  />
                  {instance.name}
                </label>
              </li>
            ))}
          </ul>
        </Section>
        {form.kind === "hole" ? (
          <Section title="Holes">
            <div className="flex items-center gap-2">
              <span
                className="min-w-0 grow truncate font-body text-xs text-mist"
                data-testid="pattern-hole"
              >
                {form.hole === null
                  ? "The hole the seed sits in"
                  : `Hole on ${nameOf(form.hole.instanceId)}`}
              </span>
              <PickButton
                label={form.hole === null ? "Pick hole" : "Re-pick"}
                armed={picking === "hole"}
                testId="pattern-pick-hole"
                onClick={() => onPick(picking === "hole" ? null : "hole")}
              />
            </div>
            {drivers.length > 0 ? (
              <div className="mt-1" data-testid="pattern-also-on">
                <span className="font-body text-2xs text-gauge">
                  Also on the same holes of
                </span>
                {drivers.map((driver) => (
                  <label
                    key={driver.id}
                    className="flex items-center gap-2 py-0.5 font-body text-xs text-mist"
                  >
                    <input
                      type="checkbox"
                      checked={form.alsoOn.includes(driver.id)}
                      data-testid={`pattern-also-on-${driver.id}`}
                      onChange={() =>
                        set({ alsoOn: toggle(form.alsoOn, driver.id) })
                      }
                    />
                    {driver.name}
                  </label>
                ))}
              </div>
            ) : null}
            <p className="mt-1 font-body text-2xs text-gauge">
              One copy at every hole of this size on this face; the count
              follows the part.
            </p>
          </Section>
        ) : (
          <>
            <Section title={form.kind === "linear" ? "Direction" : "Axis"}>
              <div className="flex items-center gap-2">
                <select
                  value={form.axis}
                  data-testid="pattern-axis"
                  onChange={(event) =>
                    set({ axis: event.target.value as AxisChoice })
                  }
                  className="rounded-sm border border-etch bg-carbide px-1 py-0.5 font-body text-xs text-mist"
                >
                  {AXES.map((axis) => (
                    <option key={axis.value} value={axis.value}>
                      {axis.label}
                    </option>
                  ))}
                </select>
                {form.axis === "edge" ? (
                  <PickButton
                    label={form.edge === null ? "Pick edge" : "Re-pick"}
                    armed={picking === "axis"}
                    testId="pattern-pick-axis"
                    onClick={() => onPick(picking === "axis" ? null : "axis")}
                  />
                ) : null}
                <label className="ml-auto flex items-center gap-1 font-body text-xs text-mist">
                  <input
                    type="checkbox"
                    checked={form.flip}
                    data-testid="pattern-flip"
                    onChange={() => set({ flip: !form.flip })}
                  />
                  Flip
                </label>
              </div>
              {form.axis === "edge" && form.edge !== null ? (
                <p
                  className="mt-1 truncate font-body text-2xs text-gauge"
                  data-testid="pattern-edge"
                >
                  {form.edge.signature.curve === "circle"
                    ? "Hole axis"
                    : "Edge"}{" "}
                  on {nameOf(form.edge.instanceId)}
                </p>
              ) : null}
            </Section>
            <Section title="Extent">
              <ExprField
                label="Count"
                value={form.count}
                testId="pattern-count"
                onChange={(count) => set({ count })}
              />
              {form.kind === "linear" ? (
                <ExprField
                  label="Spacing"
                  value={form.spacing}
                  testId="pattern-spacing"
                  onChange={(spacing) => set({ spacing })}
                />
              ) : (
                <ExprField
                  label="Angle"
                  value={form.angle}
                  testId="pattern-angle"
                  onChange={(angle) => set({ angle })}
                />
              )}
            </Section>
          </>
        )}
      </Panel>
    </EditorCard>
  );
}
