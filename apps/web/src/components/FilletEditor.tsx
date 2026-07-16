/**
 * The fillet editor — a title-block strip anchored top-left of the viewport,
 * the same authoring seat the extrude/revolve/pattern editors use. Keyboard-
 * first: the radius field autofocuses, Enter commits, Escape cancels — the
 * sketcher's dimension grammar. Radius wears brass because it is THE parametric
 * handle of the feature.
 *
 * Edges are chosen one of two ways (the "Selection" toggle): "By rule" — the
 * geometric predicate cell (round everything / an axis), the fast path — or
 * "Pick edges", where the body's edges light up in the viewport and clicking
 * toggles which ones round. The picked set lives in the edge-pick store (shared
 * with the overlay); this editor reads its count and builds the ref-based
 * selector on submit. A picked-edge fillet is best-effort: a drastic upstream
 * change can move a picked edge (topological naming §10) — the copy says so.
 */
import {
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { FilletParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  buildFilletParams,
  canSubmitFillet,
  EDGE_SELECTORS,
  type FilletForm,
  radiusError,
  type SelectionMode,
} from "../features/modify";

export interface FilletEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-fillet defaults, or an existing fillet's params). */
  initial: FilletForm;
  /** The anchor for picked-edge refs — the last body-affecting feature's id. */
  bodyFeatureId: string | null;
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
  bodyFeatureId,
  onSubmit,
  onCancel,
  saving,
  error,
}: FilletEditorProps) {
  const [form, setForm] = useState<FilletForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const picked = useEdgePickStore((s) => s.picked);
  const overlayError = useEdgePickStore((s) => s.overlayError);
  const setPicking = useEdgePickStore((s) => s.setPicking);
  const clearPicks = useEdgePickStore((s) => s.clearPicks);

  const submit = useCallback(() => {
    const params = buildFilletParams(form, picked, bodyFeatureId);
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

  const canSubmit = canSubmitFillet(form, picked, bodyFeatureId) && !saving;
  useCommandBridge(submit, canSubmit);

  return (
    <div
      className="absolute left-editor top-3 w-72 max-w-full"
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

            <SegmentedControl<SelectionMode>
              label="Selection"
              value={form.mode}
              onChange={changeMode}
              options={[
                {
                  value: "rule",
                  label: "By rule",
                  "data-testid": "fillet-mode-rule",
                },
                {
                  value: "pick",
                  label: "Pick edges",
                  "data-testid": "fillet-mode-pick",
                },
              ]}
            />

            {form.mode === "rule" ? (
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
            ) : (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-baseline justify-between">
                  <span className="font-body text-xs text-gauge">Edges</span>
                  <button
                    type="button"
                    data-testid="fillet-pick-clear"
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
                  Click edges in the view to round just those. A large upstream
                  change can move a picked edge.
                </p>
                {overlayError ? (
                  <p
                    role="alert"
                    data-testid="fillet-pick-error"
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
