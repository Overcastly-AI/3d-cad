/**
 * The shell editor — a title-block strip anchored top-left of the viewport, the
 * same authoring seat the fillet/chamfer editors use. Keyboard-first: the
 * thickness field autofocuses, Enter commits, Escape cancels — the sketcher's
 * dimension grammar. Thickness wears brass because it is THE parametric handle
 * of the feature.
 *
 * A shell always picks faces to open: the body's planar faces light up in the
 * viewport and clicking toggles which ones are left open. The honest copy names
 * the meaningful default — no faces open is a fully SEALED hollow (a closed
 * cavity), not an incomplete selection — so an engineer knows Create is valid
 * with zero picks. The picked-open set lives in the face-pick store (shared with
 * the overlay); this editor reads its count and builds the params on submit.
 */
import { NumberField, Panel, PanelActionCell } from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { ShellParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import { useFacePickStore } from "../features/facePickStore";
import { useDocumentLengthUnit } from "../units/documentUnit";
import {
  buildShellParams,
  canSubmitShell,
  type ShellForm,
  thicknessError,
} from "../features/shell";
import { EditorCard } from "./EditorCard";

export interface ShellEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-shell defaults, or an existing shell's params). */
  initial: ShellForm;
  /** The anchor for picked-open face refs — the last body-affecting feature. */
  bodyFeatureId: string | null;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: ShellParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

/** The live open-count line — names the sealed-vs-open default honestly. */
function openCountText(count: number): string {
  if (count === 0) return "No faces open — a sealed hollow";
  if (count === 1) return "1 face open";
  return `${count} faces open`;
}

export function ShellEditor({
  mode,
  initial,
  bodyFeatureId,
  onSubmit,
  onCancel,
  saving,
  error,
}: ShellEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<ShellForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const picked = useFacePickStore((s) => s.picked);
  const overlayError = useFacePickStore((s) => s.overlayError);
  const clearPicks = useFacePickStore((s) => s.clearPicks);

  const submit = useCallback(() => {
    const params = buildShellParams(form, picked, bodyFeatureId, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, picked, bodyFeatureId, onSubmit, unit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  const canSubmit =
    canSubmitShell(form, picked, bodyFeatureId, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  return (
    <EditorCard onKeyDown={onKeyDown}>
      <Panel aria-label="Shell" data-testid="shell-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New shell" : "Edit shell"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <NumberField
              label="Thickness"
              unit={unit}
              data-testid="shell-thickness"
              autoFocus
              value={form.thicknessInput}
              error={thicknessError(form.thicknessInput, unit)}
              onChange={(e) =>
                setForm((f) => ({ ...f, thicknessInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="font-body text-xs text-gauge">
                  Faces to open
                </span>
                <button
                  type="button"
                  data-testid="shell-pick-clear"
                  disabled={picked.length === 0}
                  onClick={clearPicks}
                  className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:text-gauge disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
              <p
                data-testid="shell-open-count"
                aria-live="polite"
                className="font-data text-base text-mist"
              >
                {openCountText(picked.length)}
              </p>
              <p className="font-body text-xs text-gauge">
                Click faces in the view to leave those sides open. Pick none for
                a fully enclosed hollow.
              </p>
              {overlayError ? (
                <p
                  role="alert"
                  data-testid="shell-pick-error"
                  className="font-body text-xs text-flag"
                >
                  {overlayError}
                </p>
              ) : null}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="shell-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="shell-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="shell-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </EditorCard>
  );
}
