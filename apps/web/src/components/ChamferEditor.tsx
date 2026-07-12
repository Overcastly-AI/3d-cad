/**
 * The chamfer editor — the fillet's twin (see FilletEditor): the same title-
 * block authoring seat, the same keyboard grammar (distance autofocuses, Enter
 * commits, Escape cancels), the same geometric edge-selector PREDICATE. It
 * differs only in the parametric handle: a symmetric bevel distance, not a
 * radius. Distance wears brass as THE parametric handle of the feature.
 */
import { NumberField, Panel, PanelActionCell, SelectField } from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { ChamferParams } from "../api/parts";
import {
  buildChamferParams,
  canSubmitChamfer,
  type ChamferForm,
  distanceError,
  EDGE_SELECTORS,
} from "../features/modify";

export interface ChamferEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-chamfer defaults, or an existing chamfer's params). */
  initial: ChamferForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: ChamferParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

export function ChamferEditor({
  mode,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: ChamferEditorProps) {
  const [form, setForm] = useState<ChamferForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildChamferParams(form);
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

  const canSubmit = canSubmitChamfer(form) && !saving;

  return (
    <div
      className="absolute left-3 top-3 w-72 max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Chamfer" data-testid="chamfer-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New chamfer" : "Edit chamfer"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <NumberField
              label="Distance"
              unit="mm"
              data-testid="chamfer-distance"
              autoFocus
              value={form.distanceInput}
              error={distanceError(form.distanceInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, distanceInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <SelectField
              label="Edges"
              data-testid="chamfer-edges"
              value={form.edges}
              options={EDGE_SELECTORS.map((o) => ({
                value: o.id,
                label: o.label,
              }))}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  edges: e.target.value as ChamferForm["edges"],
                }))
              }
            />
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="chamfer-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="chamfer-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="chamfer-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
