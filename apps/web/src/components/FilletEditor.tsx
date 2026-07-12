/**
 * The fillet editor — a title-block strip anchored top-left of the viewport,
 * the same authoring seat the extrude/revolve/pattern editors use (you author
 * one feature at a time, so they share the anchor and the viewport keeps the
 * pixels). Keyboard-first: the radius field autofocuses, Enter commits, Escape
 * cancels — the sketcher's dimension grammar. Radius wears brass because it is
 * THE parametric handle of the feature.
 *
 * The edge selector is a geometric PREDICATE, not a picked edge: "All edges" or
 * the edges parallel to a world axis. The copy says exactly that — click-
 * specific edge picking is a later item (design §2.4).
 */
import { NumberField, Panel, PanelActionCell, SelectField } from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { FilletParams } from "../api/parts";
import {
  buildFilletParams,
  canSubmitFillet,
  EDGE_SELECTORS,
  type FilletForm,
  radiusError,
} from "../features/modify";

export interface FilletEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-fillet defaults, or an existing fillet's params). */
  initial: FilletForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: FilletParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

export function FilletEditor({
  mode,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: FilletEditorProps) {
  const [form, setForm] = useState<FilletForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildFilletParams(form);
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

  const canSubmit = canSubmitFillet(form) && !saving;

  return (
    <div
      className="absolute left-3 top-3 w-72 max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Fillet" data-testid="fillet-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New fillet" : "Edit fillet"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <NumberField
              label="Radius"
              unit="mm"
              data-testid="fillet-radius"
              autoFocus
              value={form.radiusInput}
              error={radiusError(form.radiusInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, radiusInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <SelectField
              label="Edges"
              data-testid="fillet-edges"
              value={form.edges}
              options={EDGE_SELECTORS.map((o) => ({
                value: o.id,
                label: o.label,
              }))}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  edges: e.target.value as FilletForm["edges"],
                }))
              }
            />
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="fillet-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="fillet-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="fillet-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
