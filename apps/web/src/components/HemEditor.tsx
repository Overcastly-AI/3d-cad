/**
 * The closed-hem editor — folds ONE straight edge of the sheet body ~180° back
 * flat onto itself (sheet-metal parity §2). Mechanically an edge flange at a
 * fixed 180° fold, so it is the EdgeFlangeEditor with a hem framing: the SAME
 * title-block strip + edge-pick overlay/store (single-select: one edge, one
 * hem), keyboard-first (the return-length field autofocuses, Enter commits,
 * Escape cancels), but NO fold-angle field — the angle is always 180°, stated
 * as a quiet caption so the fixed fold is legible rather than hidden.
 *
 * The return `length` wears brass — the folded-back leg is THE handle. The bend
 * radius and K-factor INHERIT the part's base-flange defaults; each has an
 * override toggle. A tight closed hem sets a SMALL radius (≈0.5 × gauge), so the
 * radius override notes the gauge to nudge that, matching the edge-flange idiom.
 */
import { Checkbox, NumberField, Panel, PanelActionCell } from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { SheetMetalHemParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  bendRadiusError,
  buildHemParams,
  canSubmitHem,
  type HemForm,
  hemLengthError,
  kFactorError,
  type SheetMetalDefaults,
} from "../features/sheetMetal";
import { useDocumentLengthUnit } from "../units/documentUnit";

export interface HemEditorProps {
  mode: "create" | "edit";
  initial: HemForm;
  /** The anchor for the picked edge's ref — the current sheet body's feature. */
  bodyFeatureId: string | null;
  /** The part's inherited bend radius + K-factor (shown behind the overrides). */
  defaults: SheetMetalDefaults | null;
  onSubmit: (params: SheetMetalHemParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}

export function HemEditor({
  mode,
  initial,
  bodyFeatureId,
  defaults,
  onSubmit,
  onCancel,
  saving,
  error,
}: HemEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<HemForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const picked = useEdgePickStore((s) => s.picked);
  const overlayError = useEdgePickStore((s) => s.overlayError);
  const clearPicks = useEdgePickStore((s) => s.clearPicks);

  const submit = useCallback(() => {
    const params = buildHemParams(form, picked, bodyFeatureId, unit);
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

  const canSubmit = canSubmitHem(form, picked, bodyFeatureId, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  const inheritedRadius =
    defaults !== null ? `${defaults.bendRadiusMm} mm` : "—";
  const inheritedK = defaults !== null ? String(defaults.kFactor) : "—";
  const tightRadiusHint =
    defaults !== null
      ? `A tight closed hem uses a small radius (≈${
          Math.round(defaults.thicknessMm * 5) / 10
        } mm).`
      : "A tight closed hem uses a small radius.";

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Hem" data-testid="hem-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New closed hem" : "Edit closed hem"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* The one hemmed edge — reuses the fillet/chamfer edge-pick overlay
                in single-select mode (a click replaces the pick). */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="font-body text-xs text-gauge">Edge</span>
                <button
                  type="button"
                  data-testid="hem-pick-clear"
                  disabled={picked.length === 0}
                  onClick={clearPicks}
                  className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:text-gauge disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
              <p
                data-testid="hem-pick-count"
                aria-live="polite"
                className="font-data text-base text-mist"
              >
                {picked.length === 1 ? "1 edge picked" : "No edge picked"}
              </p>
              <p className="font-body text-xs text-gauge">
                Click one straight edge of the sheet to fold it 180° back onto
                itself.
              </p>
              {overlayError ? (
                <p
                  role="alert"
                  data-testid="hem-pick-error"
                  className="font-body text-xs text-flag"
                >
                  {overlayError}
                </p>
              ) : null}
            </div>

            <NumberField
              label="Return length"
              unit={unit}
              data-testid="hem-length"
              autoFocus
              value={form.lengthInput}
              error={hemLengthError(form.lengthInput, unit)}
              onChange={(e) =>
                setForm((f) => ({ ...f, lengthInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            {/* The fold angle is fixed at 180° for a closed hem — stated, not a
                field. Keeps the strip honest (no editable no-op). */}
            <div className="flex items-baseline justify-between">
              <span className="font-body text-xs text-gauge">Fold</span>
              <span
                data-testid="hem-fold-readout"
                className="font-data text-base text-mist"
              >
                180° (closed)
              </span>
            </div>

            {/* Bend radius — inherited unless overridden per-hem. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override bend radius"
                data-testid="hem-override-radius"
                checked={form.overrideBendRadius}
                onChange={(overrideBendRadius) =>
                  setForm((f) => ({ ...f, overrideBendRadius }))
                }
                description={
                  form.overrideBendRadius
                    ? tightRadiusHint
                    : `Inherits ${inheritedRadius} from the base flange.`
                }
              />
              {form.overrideBendRadius ? (
                <NumberField
                  label="Bend radius"
                  unit={unit}
                  data-testid="hem-bend-radius"
                  value={form.bendRadiusInput}
                  error={bendRadiusError(form.bendRadiusInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, bendRadiusInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
            </div>

            {/* K-factor — inherited unless overridden per-hem. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override K-factor"
                data-testid="hem-override-k"
                checked={form.overrideKFactor}
                onChange={(overrideKFactor) =>
                  setForm((f) => ({ ...f, overrideKFactor }))
                }
                description={
                  form.overrideKFactor
                    ? undefined
                    : `Inherits ${inheritedK} from the base flange.`
                }
              />
              {form.overrideKFactor ? (
                <NumberField
                  label="K-factor"
                  data-testid="hem-k-factor"
                  value={form.kFactorInput}
                  error={kFactorError(form.kFactorInput)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, kFactorInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="hem-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="hem-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="hem-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
