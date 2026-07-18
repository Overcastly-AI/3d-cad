/**
 * The combine editor — a boolean UNION between two independently-built bodies
 * (multi-body §MB-1), in the same title-block seat top-left of the viewport the
 * other feature editors use. Unlike extrude/revolve it consumes no sketch: it
 * names two BODIES — a TARGET that survives (keeping its identity) and a TOOL
 * that is consumed. Both are ruled selects over the part's body set (the sweep
 * two-slot idiom, promoted from sketches to bodies): keyboard-first,
 * deterministically testable, no viewport selection layer. The tool list
 * excludes whatever the target names — a body can't fuse with itself.
 *
 * A union whose bodies don't touch is a `boolean_disjoint` REBUILD error — the
 * create succeeds, then the tree panel surfaces the per-feature error honestly;
 * the scope note names that limit up front.
 */
import { Panel, PanelActionCell, SelectField } from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import { useCommandBridge } from "../features/commandActions";
import type { BooleanParams } from "../api/parts";
import type { BodyInfo } from "../features/bodies";
import {
  buildCombineParams,
  canSubmitCombine,
  type CombineForm,
  toolOptionsFor,
} from "../features/boolean";

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
      } else if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    },
    [saving, submit, onCancel],
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

  const canSubmit = canSubmitCombine(form) && !saving;
  useCommandBridge(submit, canSubmit);

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Combine" data-testid="combine-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Combine bodies
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SelectField
              label="Target (keeps)"
              data-testid="combine-target"
              autoFocus
              value={form.targetFeatureId}
              options={bodies.map(bodyOption)}
              onChange={(e) => onTargetChange(e.target.value)}
            />

            {tools.length > 0 ? (
              <SelectField
                label="Tool (consumed)"
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
              Union fuses the two bodies into one. They must touch — bodies that
              don&apos;t overlap can&apos;t be unioned yet.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
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
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="combine-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
