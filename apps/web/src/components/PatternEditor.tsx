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
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { PatternParams } from "../api/parts";
import {
  AXIS_PRESETS,
  angleError,
  buildPatternParams,
  patternSubmitBlocker,
  coordError,
  countError,
  type PatternForm,
  type PatternKind,
  spacingError,
} from "../features/pattern";
import { EditorCard } from "./EditorCard";
import { ScopeRow } from "./ScopeRow";

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
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<PatternForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildPatternParams(form, unit);
    if (params === null) return;
    onSubmit(params);
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

  const set = useCallback(
    <K extends keyof PatternForm>(key: K, value: PatternForm[K]) =>
      setForm((f) => ({ ...f, [key]: value })),
    [],
  );

  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Save with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already.
  const blocker = saving ? null : patternSubmitBlocker(form, unit);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);
  // When the count is valid (or still being typed) show the informational note;
  // an invalid count already flags "use 2 or more", so don't say it twice.
  const showCountNote = countError(form.countInput) === null;

  return (
    <EditorCard
      onKeyDown={onKeyDown}
      // THE ACTION ROW IS PINNED, not scrolled (REASON-GATE-1, the shape
      // `HoleEditor` has used since UI-REVIEW 2026-07-30 P1 and `HemEditor`
      // since HEM-1B). It used to ride inside the scrolling body, so at the
      // 1280x800 floor a tall form could put the commit action — and the
      // sentence explaining why it is grey — below the fold of its own card.
      // An explanation the stuck user has to scroll for is the defect wearing
      // a longer sentence.
      footer={
        <>
          {error ? (
            <p
              role="alert"
              data-testid="pattern-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
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
              // The reason takes the caption's line while gated and is wired as
              // the cell's `aria-describedby` — eye, pointer and screen reader
              // get the same sentence. `blocker` is null while SAVING: the
              // label already says so, and a second sentence saying it again
              // would be the one accessory to remove.
              disabledReason={blocker ?? undefined}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel aria-label="Pattern" data-testid="pattern-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New pattern" : "Edit pattern"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* WHAT is repeated, before HOW it is repeated: the subject is the
                question a pattern got wrong for a year (pattern-scope §1), and
                it is the first thing the user should read. */}
            <ScopeRow
              verb="pattern"
              mode={form.scope}
              features={form.scopeFeatures}
              onChange={(scope) => set("scope", scope)}
            />

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
                {form.scope === "features"
                  ? "Includes the original — a count of 3 makes 2 more."
                  : "Includes the seed body — a count of 3 makes 2 more."}
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
                  unit={unit}
                  data-testid="pattern-spacing"
                  value={form.spacingInput}
                  error={spacingError(form.spacingInput, unit)}
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
                      unit={unit}
                      data-testid="pattern-axis-x"
                      value={form.axisPointXInput}
                      error={coordError(form.axisPointXInput, unit)}
                      onChange={(e) => set("axisPointXInput", e.target.value)}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <NumberField
                      label="Y"
                      unit={unit}
                      data-testid="pattern-axis-y"
                      value={form.axisPointYInput}
                      error={coordError(form.axisPointYInput, unit)}
                      onChange={(e) => set("axisPointYInput", e.target.value)}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <NumberField
                      label="Z"
                      unit={unit}
                      data-testid="pattern-axis-z"
                      value={form.axisPointZInput}
                      error={coordError(form.axisPointZInput, unit)}
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
      </Panel>
    </EditorCard>
  );
}
