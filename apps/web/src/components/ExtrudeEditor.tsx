/**
 * The extrude editor — a title-block strip anchored top-left of the viewport,
 * the same seat the sketch strip uses (you author a sketch OR a feature, never
 * both, so they share one "authoring lives here" anchor and the viewport keeps
 * the pixels). Keyboard-first: the distance field autofocuses, Enter commits,
 * Escape cancels — the sketcher's dimension grammar. Distance wears brass
 * because it is THE parametric handle of the feature, matching the sketcher's
 * driving dimensions.
 */
import { NumberField, Panel, PanelActionCell, SelectField } from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { ExtrudeParams } from "../api/parts";
import {
  canSubmitExtrude,
  distanceError,
  type ExtrudeDirection,
  type ExtrudeForm,
  type ExtrudeOperation,
  parseDistanceMm,
  type ProfileOption,
} from "../features/extrude";

export interface ExtrudeEditorProps {
  mode: "create" | "edit";
  /** Sketch features the extrude may consume, in build order. */
  profiles: readonly ProfileOption[];
  /** The seed form (new-extrude defaults, or an existing extrude's params). */
  initial: ExtrudeForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: ExtrudeParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

const OPERATIONS: ReadonlyArray<{ value: ExtrudeOperation; label: string }> = [
  { value: "add", label: "Add" },
  { value: "cut", label: "Cut" },
];

const DIRECTIONS: ReadonlyArray<{ value: ExtrudeDirection; label: string }> = [
  { value: "normal", label: "Normal" },
  { value: "reverse", label: "Reverse" },
];

export function ExtrudeEditor({
  mode,
  profiles,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: ExtrudeEditorProps) {
  const [form, setForm] = useState<ExtrudeForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const submit = useCallback(() => {
    const distance = parseDistanceMm(form.distanceInput);
    if (distance === null || form.profileFeatureId === "") return;
    onSubmit({
      profile: { kind: "feature", feature_id: form.profileFeatureId },
      distance_mm: distance,
      operation: form.operation,
      direction: form.direction,
    });
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

  const distanceMsg = distanceError(form.distanceInput);
  const canSubmit = canSubmitExtrude(form) && !saving;
  const profileName =
    profiles.find((p) => p.id === form.profileFeatureId)?.name ?? "—";

  return (
    <div
      className="absolute left-3 top-3 w-72 max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Extrude" data-testid="extrude-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New extrude" : "Edit extrude"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {profiles.length > 1 ? (
              <SelectField
                label="Profile"
                data-testid="extrude-profile"
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
                  data-testid="extrude-profile"
                >
                  {profileName}
                </span>
              </div>
            )}

            <NumberField
              label="Distance"
              unit="mm"
              data-testid="extrude-distance"
              autoFocus
              value={form.distanceInput}
              error={distanceMsg}
              onChange={(e) =>
                setForm((f) => ({ ...f, distanceInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <div
              role="group"
              aria-label="Operation"
              className="flex flex-col gap-0.5"
            >
              <span className="font-body text-xs text-gauge">Operation</span>
              <div className="grid grid-cols-2 divide-x divide-hairline rounded-sm border border-etch">
                {OPERATIONS.map(({ value, label }) => (
                  <PanelActionCell
                    key={value}
                    label={label}
                    selected={form.operation === value}
                    data-testid={`extrude-op-${value}`}
                    aria-label={`Operation: ${label}`}
                    onClick={() => setForm((f) => ({ ...f, operation: value }))}
                  />
                ))}
              </div>
            </div>

            <div
              role="group"
              aria-label="Direction"
              className="flex flex-col gap-0.5"
            >
              <span className="font-body text-xs text-gauge">Direction</span>
              <div className="grid grid-cols-2 divide-x divide-hairline rounded-sm border border-etch">
                {DIRECTIONS.map(({ value, label }) => (
                  <PanelActionCell
                    key={value}
                    label={label}
                    selected={form.direction === value}
                    data-testid={`extrude-dir-${value}`}
                    aria-label={`Direction: ${label}`}
                    onClick={() => setForm((f) => ({ ...f, direction: value }))}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="extrude-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="extrude-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="extrude-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
