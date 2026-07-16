/**
 * The pattern editor — the revolve editor's twin, in the same title-block seat
 * top-left of the viewport (you author one feature at a time). A pattern
 * repeats the WHOLE current body and unions the copies, so the copy is honest
 * about scope: it patterns the body, it is additive, and the copies must merge
 * into one connected solid. Its structural choice is linear ⇄ circular (a
 * SegmentedControl); COUNT is the parametric handle and wears brass focus.
 * Keyboard-first: count autofocuses, Enter commits, Escape cancels — the
 * sketcher's dimension grammar. World-space direction/axis are chosen from the
 * six principal axes (revolve's ruled-select idiom), not a raw vector widget.
 */
import {
  CircularPatternIcon,
  LinearPatternIcon,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import { useCommandBridge } from "../features/commandActions";
import type { PatternParams } from "../api/parts";
import {
  AXIS_PRESETS,
  angleError,
  buildPatternParams,
  canSubmitPattern,
  coordError,
  countError,
  type PatternForm,
  type PatternKind,
  spacingError,
} from "../features/pattern";

export interface PatternEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-pattern defaults, or an existing pattern's params). */
  initial: PatternForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: PatternParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

const KINDS: ReadonlyArray<SegmentOption<PatternKind>> = [
  {
    value: "linear",
    label: "Linear",
    icon: <LinearPatternIcon />,
    "data-testid": "pattern-kind-linear",
    "aria-label": "Pattern: Linear row",
  },
  {
    value: "circular",
    label: "Circular",
    icon: <CircularPatternIcon />,
    "data-testid": "pattern-kind-circular",
    "aria-label": "Pattern: Circular ring",
  },
];

const AXIS_OPTIONS = AXIS_PRESETS.map((a) => ({ value: a.id, label: a.label }));

export function PatternEditor({
  mode,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: PatternEditorProps) {
  const [form, setForm] = useState<PatternForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildPatternParams(form);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    },
    [saving, submit, onCancel],
  );

  const set = useCallback(
    <K extends keyof PatternForm>(key: K, value: PatternForm[K]) =>
      setForm((f) => ({ ...f, [key]: value })),
    [],
  );

  const canSubmit = canSubmitPattern(form) && !saving;
  useCommandBridge(submit, canSubmit);
  // When the count is valid (or still being typed) show the informational note;
  // an invalid count already flags "use 2 or more", so don't say it twice.
  const showCountNote = countError(form.countInput) === null;

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Pattern" data-testid="pattern-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New pattern" : "Edit pattern"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SegmentedControl
              label="Pattern"
              value={form.kind}
              options={KINDS}
              onChange={(kind) => set("kind", kind)}
            />

            <NumberField
              label="Count"
              data-testid="pattern-count"
              autoFocus
              value={form.countInput}
              error={countError(form.countInput)}
              onChange={(e) => set("countInput", e.target.value)}
              onFocus={(e) => e.currentTarget.select()}
            />
            {showCountNote ? (
              <p
                className="-mt-1 font-body text-xs text-gauge"
                data-testid="pattern-count-note"
              >
                Includes the seed body — a count of 3 makes 2 more.
              </p>
            ) : null}

            {form.kind === "linear" ? (
              <>
                <SelectField
                  label="Direction"
                  data-testid="pattern-direction"
                  value={form.direction}
                  options={AXIS_OPTIONS}
                  onChange={(e) =>
                    set("direction", e.target.value as PatternForm["direction"])
                  }
                />
                <NumberField
                  label="Spacing"
                  unit="mm"
                  data-testid="pattern-spacing"
                  value={form.spacingInput}
                  error={spacingError(form.spacingInput)}
                  onChange={(e) => set("spacingInput", e.target.value)}
                  onFocus={(e) => e.currentTarget.select()}
                />
              </>
            ) : (
              <>
                <SelectField
                  label="Axis"
                  data-testid="pattern-axis-direction"
                  value={form.axisDirection}
                  options={AXIS_OPTIONS}
                  onChange={(e) =>
                    set(
                      "axisDirection",
                      e.target.value as PatternForm["axisDirection"],
                    )
                  }
                />
                <div className="flex flex-col gap-0.5">
                  <span className="font-body text-xs text-gauge">
                    Axis point
                  </span>
                  <div className="grid grid-cols-3 gap-2">
                    <NumberField
                      label="X"
                      unit="mm"
                      data-testid="pattern-axis-x"
                      value={form.axisPointXInput}
                      error={coordError(form.axisPointXInput)}
                      onChange={(e) => set("axisPointXInput", e.target.value)}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <NumberField
                      label="Y"
                      unit="mm"
                      data-testid="pattern-axis-y"
                      value={form.axisPointYInput}
                      error={coordError(form.axisPointYInput)}
                      onChange={(e) => set("axisPointYInput", e.target.value)}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <NumberField
                      label="Z"
                      unit="mm"
                      data-testid="pattern-axis-z"
                      value={form.axisPointZInput}
                      error={coordError(form.axisPointZInput)}
                      onChange={(e) => set("axisPointZInput", e.target.value)}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                  </div>
                </div>
                <NumberField
                  label="Angle"
                  unit="°"
                  data-testid="pattern-angle"
                  value={form.angleInput}
                  error={angleError(form.angleInput)}
                  onChange={(e) => set("angleInput", e.target.value)}
                  onFocus={(e) => e.currentTarget.select()}
                />
              </>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="pattern-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="pattern-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="pattern-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
