/**
 * The edge-flange editor — folds a leg off ONE straight edge of the sheet body.
 * Same title-block strip the fillet/chamfer editors use, and it reuses their
 * exact edge-pick overlay + store (in single-select mode: one edge folds one
 * flange). Keyboard-first: the flange-length field autofocuses, Enter commits,
 * Escape cancels. Flange length wears brass — the developed leg is THE handle.
 *
 * The bend radius and K-factor INHERIT the part's base-flange defaults; each has
 * an override toggle that reveals a per-bend field, so the common case (accept
 * the sheet's radius/K) stays one glance while an override is one click away.
 */
import {
  Checkbox,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
} from "@loft/design";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { SheetMetalEdgeFlangeParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import { useEdgePickStore } from "../features/edgePickStore";
import {
  bendAngleError,
  bendRadiusError,
  buildEdgeFlangeParams,
  canSubmitEdgeFlange,
  type EdgeFlangeForm,
  type EdgeFlangeSpanPreview,
  edgeFlangeSpanPreview,
  flangeLengthError,
  flangeOffsetError,
  flangeWidthError,
  kFactorError,
  type SheetMetalDefaults,
  type WidthExtent,
} from "../features/sheetMetal";
import { useDocumentLengthUnit } from "../units/documentUnit";
import { EditorCard } from "./EditorCard";

export interface EdgeFlangeEditorProps {
  mode: "create" | "edit";
  initial: EdgeFlangeForm;
  /** The anchor for the picked edge's ref — the current sheet body's feature. */
  bodyFeatureId: string | null;
  /** The part's inherited bend radius + K-factor (shown behind the overrides). */
  defaults: SheetMetalDefaults | null;
  onSubmit: (params: SheetMetalEdgeFlangeParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
  /**
   * Reports the CURRENT chosen span (on every field/extent change, and null when
   * no edge is picked or the extent's fields are invalid) so the workspace can
   * draw it ON the picked edge in the viewport — the in-scene answer to the
   * Full / Centered / Offset choice (`FlangeSpanOverlay`).
   */
  onSpanChange?: (span: EdgeFlangeSpanPreview | null) => void;
}

/** The width-extent choices, in the SegmentedControl's order. */
const WIDTH_EXTENTS: readonly {
  value: WidthExtent;
  label: string;
  "data-testid": string;
}[] = [
  { value: "full", label: "Full", "data-testid": "edge-flange-extent-full" },
  {
    value: "centered",
    label: "Centered",
    "data-testid": "edge-flange-extent-centered",
  },
  {
    value: "offset",
    label: "Offset",
    "data-testid": "edge-flange-extent-offset",
  },
];

export function EdgeFlangeEditor({
  mode,
  initial,
  bodyFeatureId,
  defaults,
  onSubmit,
  onCancel,
  saving,
  error,
  onSpanChange,
}: EdgeFlangeEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<EdgeFlangeForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const picked = useEdgePickStore((s) => s.picked);
  const overlayError = useEdgePickStore((s) => s.overlayError);
  const clearPicks = useEdgePickStore((s) => s.clearPicks);

  // Mirror the live span up for the viewport preview, and clear it on unmount.
  const span = useMemo(
    () => edgeFlangeSpanPreview(form, picked, unit),
    [form, picked, unit],
  );
  useEffect(() => {
    onSpanChange?.(span);
  }, [span, onSpanChange]);
  useEffect(() => () => onSpanChange?.(null), [onSpanChange]);

  const submit = useCallback(() => {
    const params = buildEdgeFlangeParams(form, picked, bodyFeatureId, unit);
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
    canSubmitEdgeFlange(form, picked, bodyFeatureId, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  const inheritedRadius =
    defaults !== null ? `${defaults.bendRadiusMm} mm` : "—";
  const inheritedK = defaults !== null ? String(defaults.kFactor) : "—";

  return (
    <EditorCard onKeyDown={onKeyDown}>
      <Panel aria-label="Edge flange" data-testid="edge-flange-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New edge flange" : "Edit edge flange"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* The one folded edge — reuses the fillet/chamfer edge-pick overlay
                in single-select mode. */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="font-body text-xs text-gauge">Edge</span>
                <button
                  type="button"
                  data-testid="edge-flange-pick-clear"
                  disabled={picked.length === 0}
                  onClick={clearPicks}
                  className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:text-gauge disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
              <p
                data-testid="edge-flange-pick-count"
                aria-live="polite"
                className="font-data text-base text-mist"
              >
                {picked.length === 1 ? "1 edge picked" : "No edge picked"}
              </p>
              <p className="font-body text-xs text-gauge">
                Click one straight edge of the sheet to fold a flange off it.
              </p>
              {overlayError ? (
                <p
                  role="alert"
                  data-testid="edge-flange-pick-error"
                  className="font-body text-xs text-flag"
                >
                  {overlayError}
                </p>
              ) : null}
            </div>

            <NumberField
              label="Flange length"
              unit={unit}
              data-testid="edge-flange-length"
              autoFocus
              value={form.flangeLengthInput}
              error={flangeLengthError(form.flangeLengthInput, unit)}
              onChange={(e) =>
                setForm((f) => ({ ...f, flangeLengthInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            {/* Width extents (§4.5.1): Full spans the edge; Centered/Offset fold a
                narrower flange, with an auto bend-end relief at interior ends. */}
            <div className="flex flex-col gap-1.5">
              <SegmentedControl<WidthExtent>
                label="Width"
                value={form.widthExtent}
                options={WIDTH_EXTENTS}
                onChange={(widthExtent) =>
                  setForm((f) => ({ ...f, widthExtent }))
                }
              />
              {form.widthExtent !== "full" ? (
                <NumberField
                  label="Flange width"
                  unit={unit}
                  data-testid="edge-flange-width"
                  value={form.widthInput}
                  error={flangeWidthError(form.widthInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, widthInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
              {form.widthExtent === "offset" ? (
                <NumberField
                  label="Offset from edge start"
                  unit={unit}
                  data-testid="edge-flange-offset"
                  value={form.offsetInput}
                  error={flangeOffsetError(form.offsetInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, offsetInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
              {form.widthExtent === "centered" ? (
                <p
                  data-testid="edge-flange-extent-hint"
                  className="font-body text-xs text-gauge"
                >
                  Centered on the edge — the offset is set for you.
                </p>
              ) : null}
              {form.widthExtent !== "full" ? (
                <p
                  data-testid="edge-flange-relief-note"
                  className="font-body text-xs text-gauge"
                >
                  A rectangular relief notch (1 × gauge) is cut into the base at
                  each interior span end so the fold won't tear.
                </p>
              ) : null}
            </div>

            <NumberField
              label="Bend angle"
              unit="°"
              data-testid="edge-flange-angle"
              value={form.bendAngleInput}
              error={bendAngleError(form.bendAngleInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, bendAngleInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            {/* Bend radius — inherited unless overridden per-bend. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override bend radius"
                data-testid="edge-flange-override-radius"
                checked={form.overrideBendRadius}
                onChange={(overrideBendRadius) =>
                  setForm((f) => ({ ...f, overrideBendRadius }))
                }
                description={
                  form.overrideBendRadius
                    ? undefined
                    : `Inherits ${inheritedRadius} from the base flange.`
                }
              />
              {form.overrideBendRadius ? (
                <NumberField
                  label="Bend radius"
                  unit={unit}
                  data-testid="edge-flange-bend-radius"
                  value={form.bendRadiusInput}
                  error={bendRadiusError(form.bendRadiusInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, bendRadiusInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              ) : null}
            </div>

            {/* K-factor — inherited unless overridden per-bend. */}
            <div className="flex flex-col gap-1.5">
              <Checkbox
                label="Override K-factor"
                data-testid="edge-flange-override-k"
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
                  data-testid="edge-flange-k-factor"
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
            data-testid="edge-flange-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="edge-flange-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="edge-flange-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </EditorCard>
  );
}
