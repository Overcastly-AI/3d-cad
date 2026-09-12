/**
 * The combine editor — a boolean between two independently-built bodies
 * (multi-body §MB-2), in the same title-block seat top-left of the viewport the
 * other feature editors use. Unlike extrude/revolve it consumes no sketch: it
 * names an OPERATION (union / subtract / intersect) and two BODIES — a TARGET
 * that survives (keeping its identity) and a TOOL. Both are ruled selects over
 * the part's body set (the sweep two-slot idiom, promoted from sketches to
 * bodies): keyboard-first, deterministically testable, no viewport selection
 * layer. The tool list excludes whatever the target names — a body can't
 * combine with itself.
 *
 * Union and intersect are order-independent; SUBTRACT is not (Target − Tool),
 * so the role labels + note track the operation. A boolean whose result would
 * be >1 lump is normally a `boolean_disjoint` REBUILD error (empty result:
 * `boolean_empty`) — the create succeeds, then the tree panel surfaces the
 * per-feature error honestly. The "Keep as one body" opt-in (MB-4c) threads
 * `allow_disjoint` so that >1-lump result is instead kept as ONE multi-lump
 * body; off by default (the "operands must touch" safety). Meaningful for all
 * three operations (a non-touching union, a severing subtract, a two-region
 * intersect each split into lumps).
 */
import {
  Checkbox,
  Panel,
  PanelActionCell,
  SegmentedControl,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import { useCommandBridge } from "../features/commandActions";
import type { BooleanOperation, BooleanParams } from "../api/parts";
import type { BodyInfo } from "../features/bodies";
import {
  buildCombineParams,
  combineSubmitBlocker,
  type CombineForm,
  KEEP_AS_ONE_BODY_LABEL,
  operationCopy,
  toolOptionsFor,
} from "../features/boolean";
import { EditorCard } from "./EditorCard";

export interface CombineEditorProps {
  /** The part's bodies, in tree order (the target + tool choices). */
  bodies: readonly BodyInfo[];
  /** The seed form (first two bodies by default). */
  initial: CombineForm;
  /** Commit the built union params. */
  onSubmit: (params: BooleanParams) => void;
  onCancel: () => void;
  /** True while the create round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

/** One body as a select option: "Body N · Extrude1". */
function bodyOption(body: BodyInfo): { value: string; label: string } {
  return {
    value: body.baseFeatureId,
    label: `Body ${body.ordinal} · ${body.name}`,
  };
}

/** The three boolean operations, each with its arithmetic glyph (− / ∩ / +). */
const OPERATION_OPTIONS: readonly {
  value: BooleanOperation;
  label: string;
  glyph: string;
  "data-testid": string;
}[] = [
  {
    value: "union",
    label: "Union",
    glyph: "+",
    "data-testid": "combine-op-union",
  },
  {
    value: "subtract",
    label: "Subtract",
    glyph: "−",
    "data-testid": "combine-op-subtract",
  },
  {
    value: "intersect",
    label: "Intersect",
    glyph: "∩",
    "data-testid": "combine-op-intersect",
  },
];

export function CombineEditor({
  bodies,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: CombineEditorProps) {
  const [form, setForm] = useState<CombineForm>(initial);
  // Re-seed when the editor is retargeted.
  useEffect(() => setForm(initial), [initial]);

  const tools = toolOptionsFor(bodies, form.targetFeatureId);

  const submit = useCallback(() => {
    const params = buildCombineParams(form);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  // Changing the target re-scopes the tool list; if the current tool is now the
  // target (illegal — a body can't fuse with itself), fall back to the first
  // other body.
  const onTargetChange = useCallback(
    (targetFeatureId: string) => {
      setForm((f) => ({
        ...f,
        targetFeatureId,
        toolFeatureId:
          f.toolFeatureId !== "" && f.toolFeatureId !== targetFeatureId
            ? f.toolFeatureId
            : (toolOptionsFor(bodies, targetFeatureId)[0]?.baseFeatureId ?? ""),
      }));
    },
    [bodies],
  );

  const setOperation = useCallback(
    (operation: BooleanOperation) => setForm((f) => ({ ...f, operation })),
    [],
  );

  const setAllowDisjoint = useCallback(
    (allowDisjoint: boolean) => setForm((f) => ({ ...f, allowDisjoint })),
    [],
  );

  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Save with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already.
  const blocker = saving ? null : combineSubmitBlocker(form);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);

  const copy = operationCopy(form.operation);

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
              data-testid="combine-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="combine-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : "Combine"}
              caption="Enter"
              data-testid="combine-submit"
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
      <Panel aria-label="Combine" data-testid="combine-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Combine bodies
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SegmentedControl<BooleanOperation>
              label="Operation"
              value={form.operation}
              onChange={setOperation}
              options={OPERATION_OPTIONS.map((op) => ({
                value: op.value,
                label: op.label,
                icon: op.glyph,
                "data-testid": op["data-testid"],
                "aria-label": op.label,
              }))}
            />

            <SelectField
              label={copy.targetLabel}
              data-testid="combine-target"
              autoFocus
              value={form.targetFeatureId}
              options={bodies.map(bodyOption)}
              onChange={(e) => onTargetChange(e.target.value)}
            />

            {tools.length > 0 ? (
              <SelectField
                label={copy.toolLabel}
                data-testid="combine-tool"
                value={form.toolFeatureId}
                options={tools.map(bodyOption)}
                onChange={(e) =>
                  setForm((f) => ({ ...f, toolFeatureId: e.target.value }))
                }
              />
            ) : (
              <p
                className="font-body text-xs text-flag"
                data-testid="combine-tool-empty"
                role="status"
              >
                Only one body — draw a second, then combine.
              </p>
            )}

            <p
              className="-mt-0.5 font-body text-xs text-gauge"
              data-testid="combine-note"
            >
              {copy.note}
            </p>

            {tools.length > 0 ? (
              <Checkbox
                label={KEEP_AS_ONE_BODY_LABEL}
                description={copy.disjointNote}
                checked={form.allowDisjoint}
                onChange={setAllowDisjoint}
                data-testid="combine-allow-disjoint"
              />
            ) : null}
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}
