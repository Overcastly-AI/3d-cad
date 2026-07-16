/**
 * The chamfer editor — the fillet's twin (see FilletEditor): the same title-
 * block authoring seat, the same keyboard grammar (distance autofocuses, Enter
 * commits, Escape cancels), and the same "Selection" toggle ("By rule" predicate
 * vs. "Pick edges" click-picking). It differs only in the parametric handle: a
 * symmetric bevel distance, not a radius. Distance wears brass as THE handle.
 */
import {
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { ChamferParams } from "../api/parts";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  buildChamferParams,
  canSubmitChamfer,
  type ChamferForm,
  distanceError,
  EDGE_SELECTORS,
  type SelectionMode,
} from "../features/modify";

export interface ChamferEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-chamfer defaults, or an existing chamfer's params). */
  initial: ChamferForm;
  /** The anchor for picked-edge refs — the last body-affecting feature's id. */
  bodyFeatureId: string | null;
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
  bodyFeatureId,
  onSubmit,
  onCancel,
  saving,
  error,
}: ChamferEditorProps) {
  const [form, setForm] = useState<ChamferForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const picked = useEdgePickStore((s) => s.picked);
  const overlayError = useEdgePickStore((s) => s.overlayError);
  const setPicking = useEdgePickStore((s) => s.setPicking);
  const clearPicks = useEdgePickStore((s) => s.clearPicks);

  const submit = useCallback(() => {
    const params = buildChamferParams(form, picked, bodyFeatureId);
    if (params === null) return;
    onSubmit(params);
  }, [form, picked, bodyFeatureId, onSubmit]);

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

  const changeMode = useCallback(
    (next: SelectionMode) => {
      setForm((f) => ({ ...f, mode: next }));
      setPicking(next === "pick");
    },
    [setPicking],
  );

  const canSubmit = canSubmitChamfer(form, picked, bodyFeatureId) && !saving;

  return (
    <div
      className="absolute left-editor top-3 w-72 max-w-full"
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

            <SegmentedControl<SelectionMode>
              label="Selection"
              value={form.mode}
              onChange={changeMode}
              options={[
                {
                  value: "rule",
                  label: "By rule",
                  "data-testid": "chamfer-mode-rule",
                },
                {
                  value: "pick",
                  label: "Pick edges",
                  "data-testid": "chamfer-mode-pick",
                },
              ]}
            />

            {form.mode === "rule" ? (
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
            ) : (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-baseline justify-between">
                  <span className="font-body text-xs text-gauge">Edges</span>
                  <button
                    type="button"
                    data-testid="chamfer-pick-clear"
                    disabled={picked.length === 0}
                    onClick={clearPicks}
                    className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:text-gauge disabled:opacity-50"
                  >
                    Clear
                  </button>
                </div>
                <p
                  data-testid="selected-count"
                  aria-live="polite"
                  className="font-data text-base text-mist"
                >
                  {picked.length === 0
                    ? "No edges picked"
                    : picked.length === 1
                      ? "1 edge picked"
                      : `${picked.length} edges picked`}
                </p>
                <p className="font-body text-xs text-gauge">
                  Click edges in the view to bevel just those. A large upstream
                  change can move a picked edge.
                </p>
                {overlayError ? (
                  <p
                    role="alert"
                    data-testid="chamfer-pick-error"
                    className="font-body text-xs text-flag"
                  >
                    {overlayError}
                  </p>
                ) : null}
              </div>
            )}
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
