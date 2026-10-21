/**
 * The Pipe editor (PIPE-ALONG-PATH) — Fusion 360's Pipe, in the same
 * title-block seat as every feature editor. Its distinctive field is the PATH:
 * a chain of picked curves. Every curve of every earlier sketch is listed by
 * sketch, kind, id and length (a skeleton's lines must be told apart), and a
 * click toggles one; with Chain selection on (the default) a pick takes its
 * tangent chain with it and stops at a corner, so one click on a skeleton line
 * is one tube. Model edges selected before the command ride along as rows.
 *
 * The section is the outside diameter and, Hollow, a wall: both are value
 * fields, so a parameter or a formula drives them. The operation is Join /
 * New body / Cut. Keyboard-first: Enter commits, Escape cancels.
 */
import {
  AddIcon,
  Checkbox,
  CutIcon,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
} from "@loft/design";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useCommandBridge } from "../features/commandActions";
import type { PipeParams } from "../api/parts";
import {
  buildPipeParams,
  curveLabel,
  pipeSubmitBlocker,
  toggleCurve,
  wallError,
  type PipeCurveOption,
  type PipeForm,
  type PipeOperation,
} from "../features/pipe";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";
import { type CutBodiesContext, ObjectsToCut } from "./ObjectsToCut";
import { ValueField } from "./ValueField";

export interface PipeEditorProps {
  mode: "create" | "edit";
  /** Every curve of every sketch before the pipe, in tree order. */
  curves: readonly PipeCurveOption[];
  initial: PipeForm;
  onSubmit: (params: PipeParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
  /** The rebuild error of the pipe being edited, in friendly copy, or null. */
  rebuildError?: string | null;
  /**
   * The part's bodies and the ones this cut met on its last rebuild, for
   * the Objects To Cut list (CUT-OBJECTS-TO-CUT). Absent: no list.
   */
  objectsToCut?: CutBodiesContext;
}

const OPERATIONS: ReadonlyArray<SegmentOption<PipeOperation>> = [
  {
    value: "join",
    label: "Join",
    icon: <AddIcon />,
    "data-testid": "pipe-op-join",
    "aria-label": "Operation: Join",
  },
  {
    value: "newBody",
    label: "New body",
    icon: <AddIcon />,
    "data-testid": "pipe-op-new-body",
    "aria-label": "Operation: New body",
  },
  {
    value: "cut",
    label: "Cut",
    icon: <CutIcon />,
    "data-testid": "pipe-op-cut",
    "aria-label": "Operation: Cut",
  },
];

export function PipeEditor({
  mode,
  curves,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
  rebuildError = null,
  objectsToCut,
}: PipeEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<PipeForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  // Curves grouped by sketch, in tree order.
  const groups = useMemo(() => {
    const out: { sketchId: string; name: string; items: PipeCurveOption[] }[] =
      [];
    for (const curve of curves) {
      let group = out.find((g) => g.sketchId === curve.sketchId);
      if (group === undefined) {
        group = { sketchId: curve.sketchId, name: curve.sketchName, items: [] };
        out.push(group);
      }
      group.items.push(curve);
    }
    return out;
  }, [curves]);

  const submit = useCallback(() => {
    const params = buildPipeParams(form, unit);
    if (params !== null) onSubmit(params);
  }, [form, onSubmit, unit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  const blocker = saving ? null : pipeSubmitBlocker(form, unit);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);
  const untouched = JSON.stringify(form) === JSON.stringify(initial);
  const shownRebuildError = untouched ? rebuildError : null;
  const picked = form.curves.length + form.edges.length;

  return (
    <EditorCard
      onKeyDown={onKeyDown}
      footer={
        <>
          {error || shownRebuildError ? (
            <p
              role="alert"
              data-testid="pipe-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error ?? shownRebuildError}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="pipe-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="pipe-submit"
              aria-busy={saving}
              disabled={!canSubmit}
              disabledReason={blocker ?? undefined}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel aria-label="Pipe" data-testid="pipe-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New pipe" : "Edit pipe"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <div className="flex items-baseline justify-between">
              <span className="font-display text-2xs uppercase tracking-[0.14em] text-gauge">
                Path
              </span>
              <span
                className="font-body text-xs text-gauge"
                data-testid="pipe-path-count"
              >
                {picked === 1 ? "1 curve" : `${picked} curves`}
              </span>
            </div>
            <div
              className="flex max-h-[14rem] flex-col gap-1 overflow-y-auto border border-hairline p-1"
              data-testid="pipe-path"
              role="group"
              aria-label="Path curves"
            >
              {groups.length === 0 ? (
                <p className="font-body text-xs text-flag" role="status">
                  Draw a sketch with the path first.
                </p>
              ) : null}
              {groups.map((group) => (
                <div key={group.sketchId} className="flex flex-col">
                  <span className="px-1 font-body text-2xs text-gauge">
                    {group.name}
                  </span>
                  {group.items.map((curve) => {
                    const on = form.curves.includes(curve.key);
                    return (
                      <button
                        key={curve.key}
                        type="button"
                        aria-pressed={on}
                        data-testid={`pipe-curve-${group.name}-${curve.entityId}`}
                        className={`px-2 py-0.5 text-left font-body text-xs ${
                          on
                            ? "bg-carbide text-brass"
                            : "text-mist hover:text-brass"
                        }`}
                        onClick={() =>
                          setForm((f) => toggleCurve(f, curves, curve.key))
                        }
                      >
                        {on ? "✓ " : ""}
                        {curveLabel(curve)}
                      </button>
                    );
                  })}
                </div>
              ))}
              {form.edges.map((edge, index) => (
                <button
                  key={`edge-${index}`}
                  type="button"
                  aria-pressed
                  data-testid={`pipe-edge-${index}`}
                  className="bg-carbide px-2 py-0.5 text-left font-body text-xs text-brass"
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      edges: f.edges.filter((_, i) => i !== index),
                    }))
                  }
                >
                  ✓ Model edge {index + 1} ·{" "}
                  {Math.round(edge.signature.length_mm * 10) / 10} mm
                </button>
              ))}
            </div>
            <Checkbox
              label="Chain selection"
              data-testid="pipe-chain"
              checked={form.chain}
              onChange={(chain) => setForm((f) => ({ ...f, chain }))}
              description="A pick takes the curves tangent to it; a corner stops it."
            />

            <ValueField
              label="Outside diameter"
              unit={unit}
              kind="length"
              pointer="/outer_diameter_mm"
              data-testid="pipe-od"
              value={form.odInput}
              onValueChange={(value) =>
                setForm((f) => ({ ...f, odInput: value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />
            <Checkbox
              label="Hollow"
              data-testid="pipe-hollow"
              checked={form.hollow}
              onChange={(hollow) => setForm((f) => ({ ...f, hollow }))}
              description={
                form.hollow ? "A tube of this wall." : "A solid round bar."
              }
            />
            {form.hollow ? (
              <ValueField
                label="Wall"
                unit={unit}
                kind="length"
                pointer="/wall_thickness_mm"
                data-testid="pipe-wall"
                value={form.wallInput}
                error={wallError(form, unit)}
                onValueChange={(value) =>
                  setForm((f) => ({ ...f, wallInput: value }))
                }
                onFocus={(e) => e.currentTarget.select()}
              />
            ) : null}

            <SegmentedControl
              label="Operation"
              value={form.operation}
              options={OPERATIONS}
              onChange={(operation) => setForm((f) => ({ ...f, operation }))}
            />
            {form.operation === "cut" ? (
              <ObjectsToCut
                choice={form.cutBodies}
                context={objectsToCut}
                onChange={(cutBodies) => setForm((f) => ({ ...f, cutBodies }))}
              />
            ) : null}
            <p
              className="-mt-0.5 font-body text-xs text-gauge"
              data-testid="pipe-path-note"
            >
              The curves must form one chain, open or closed, with no branch.
              Sharp corners are mitred.
            </p>
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}
