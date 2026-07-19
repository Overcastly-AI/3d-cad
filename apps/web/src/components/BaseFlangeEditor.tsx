/**
 * The base-flange editor — the sheet-metal part's first body. Same title-block
 * strip the extrude/revolve editors use (one authoring seat, top-left of the
 * viewport), keyboard-first: the gauge field autofocuses, Enter commits, Escape
 * cancels. Gauge wears brass — it is THE parametric handle of the sheet (its one
 * material thickness); the bend radius + K-factor are the part-defaults every
 * later edge flange inherits, so they ride here on the anchor body.
 */
import {
  NormalIcon,
  NumberField,
  Panel,
  PanelActionCell,
  ReverseIcon,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { SheetMetalBaseFlangeParams } from "../api/parts";
import { useCommandBridge } from "../features/commandActions";
import type { ProfileOption } from "../features/extrude";
import {
  type BaseFlangeForm,
  bendRadiusError,
  buildBaseFlangeParams,
  canSubmitBaseFlange,
  type FlangeDirection,
  kFactorError,
  thicknessError,
} from "../features/sheetMetal";
import { useDocumentLengthUnit } from "../units/documentUnit";

export interface BaseFlangeEditorProps {
  mode: "create" | "edit";
  /** Sketch features the base flange may thicken, in build order. */
  profiles: readonly ProfileOption[];
  initial: BaseFlangeForm;
  onSubmit: (params: SheetMetalBaseFlangeParams) => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}

const DIRECTIONS: ReadonlyArray<SegmentOption<FlangeDirection>> = [
  {
    value: "normal",
    label: "Normal",
    icon: <NormalIcon />,
    "data-testid": "base-flange-dir-normal",
    "aria-label": "Direction: Normal",
  },
  {
    value: "reverse",
    label: "Reverse",
    icon: <ReverseIcon />,
    "data-testid": "base-flange-dir-reverse",
    "aria-label": "Direction: Reverse",
  },
];

export function BaseFlangeEditor({
  mode,
  profiles,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: BaseFlangeEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<BaseFlangeForm>(initial);
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const params = buildBaseFlangeParams(form, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit, unit]);

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

  const canSubmit = canSubmitBaseFlange(form, unit) && !saving;
  useCommandBridge(submit, canSubmit);
  const profileName =
    profiles.find((p) => p.id === form.profileFeatureId)?.name ?? "—";

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Base flange" data-testid="base-flange-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New base flange" : "Edit base flange"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {profiles.length > 1 ? (
              <SelectField
                label="Profile"
                data-testid="base-flange-profile"
                value={form.profileFeatureId}
                options={profiles.map((p) => ({ value: p.id, label: p.name }))}
                onChange={(e) =>
                  setForm((f) => ({ ...f, profileFeatureId: e.target.value }))
                }
              />
            ) : (
              <div className="flex flex-col gap-0.5">
                <span className="font-body text-xs text-gauge">Profile</span>
                <span
                  className="font-data text-md text-mist"
                  data-testid="base-flange-profile"
                >
                  {profileName}
                </span>
              </div>
            )}

            <NumberField
              label="Gauge (thickness)"
              unit={unit}
              data-testid="base-flange-thickness"
              autoFocus
              value={form.thicknessInput}
              error={thicknessError(form.thicknessInput, unit)}
              onChange={(e) =>
                setForm((f) => ({ ...f, thicknessInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <NumberField
              label="Bend radius"
              unit={unit}
              data-testid="base-flange-bend-radius"
              value={form.bendRadiusInput}
              error={bendRadiusError(form.bendRadiusInput, unit)}
              onChange={(e) =>
                setForm((f) => ({ ...f, bendRadiusInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <NumberField
              label="K-factor"
              data-testid="base-flange-k-factor"
              value={form.kFactorInput}
              error={kFactorError(form.kFactorInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, kFactorInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <SegmentedControl
              label="Direction"
              value={form.direction}
              options={DIRECTIONS}
              onChange={(direction) => setForm((f) => ({ ...f, direction }))}
            />

            <p className="font-body text-xs text-gauge">
              The bend radius and K-factor become the part defaults every edge
              flange inherits.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="base-flange-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="base-flange-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="base-flange-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
