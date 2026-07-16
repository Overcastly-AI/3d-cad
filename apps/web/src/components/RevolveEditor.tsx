/**
 * The revolve editor — the extrude editor's twin, in the same title-block seat
 * top-left of the viewport (you author a sketch OR a feature, never both). Its
 * one extra field over extrude is the AXIS: a line entity of the profile's own
 * sketch, offered as a ruled select with the construction centerline ranked
 * first (a centerline IS an axis of revolution). Keyboard-first: the angle
 * field autofocuses, Enter commits, Escape cancels — the sketcher's dimension
 * grammar. Angle wears brass because it is THE parametric handle of the turn.
 */
import {
  AddIcon,
  CutIcon,
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

import { useCommandBridge } from "../features/commandActions";
import type { RevolveParams } from "../api/parts";
import {
  angleError,
  type AxisOption,
  canSubmitRevolve,
  defaultAxisId,
  parseAngleDeg,
  type ProfileOption,
  type RevolveDirection,
  type RevolveForm,
  type RevolveOperation,
} from "../features/revolve";

export interface RevolveEditorProps {
  mode: "create" | "edit";
  /** Sketch features the revolve may consume, in build order. */
  profiles: readonly ProfileOption[];
  /** Axis line-entity choices per profile feature id (changes with profile). */
  axesByProfile: Readonly<Record<string, readonly AxisOption[]>>;
  /** The seed form (new-revolve defaults, or an existing revolve's params). */
  initial: RevolveForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: RevolveParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
}

const OPERATIONS: ReadonlyArray<SegmentOption<RevolveOperation>> = [
  {
    value: "add",
    label: "Add",
    icon: <AddIcon />,
    "data-testid": "revolve-op-add",
    "aria-label": "Operation: Add",
  },
  {
    value: "cut",
    label: "Cut",
    icon: <CutIcon />,
    "data-testid": "revolve-op-cut",
    "aria-label": "Operation: Cut",
  },
];

const DIRECTIONS: ReadonlyArray<SegmentOption<RevolveDirection>> = [
  {
    value: "normal",
    label: "Normal",
    icon: <NormalIcon />,
    "data-testid": "revolve-dir-normal",
    "aria-label": "Direction: Normal",
  },
  {
    value: "reverse",
    label: "Reverse",
    icon: <ReverseIcon />,
    "data-testid": "revolve-dir-reverse",
    "aria-label": "Direction: Reverse",
  },
];

export function RevolveEditor({
  mode,
  profiles,
  axesByProfile,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
}: RevolveEditorProps) {
  const [form, setForm] = useState<RevolveForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const axes = axesByProfile[form.profileFeatureId] ?? [];

  const submit = useCallback(() => {
    const angle = parseAngleDeg(form.angleInput);
    if (
      angle === null ||
      form.profileFeatureId === "" ||
      form.axisEntityId === ""
    )
      return;
    onSubmit({
      profile: { kind: "feature", feature_id: form.profileFeatureId },
      axis: { kind: "sketch_line", entity: form.axisEntityId },
      angle_deg: angle,
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

  // Changing the profile re-scopes the axis to the new sketch's lines.
  const onProfileChange = useCallback(
    (profileFeatureId: string) => {
      setForm((f) => ({
        ...f,
        profileFeatureId,
        axisEntityId: defaultAxisId(axesByProfile[profileFeatureId] ?? []),
      }));
    },
    [axesByProfile],
  );

  const angleMsg = angleError(form.angleInput);
  const canSubmit = canSubmitRevolve(form) && axes.length > 0 && !saving;
  useCommandBridge(submit, canSubmit);
  const profileName =
    profiles.find((p) => p.id === form.profileFeatureId)?.name ?? "—";

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Revolve" data-testid="revolve-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New revolve" : "Edit revolve"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {profiles.length > 1 ? (
              <SelectField
                label="Profile"
                data-testid="revolve-profile"
                value={form.profileFeatureId}
                options={profiles.map((p) => ({ value: p.id, label: p.name }))}
                onChange={(e) => onProfileChange(e.target.value)}
              />
            ) : (
              <div className="flex flex-col gap-0.5">
                <span className="font-body text-xs text-gauge">Profile</span>
                <span
                  className="font-data text-md text-mist"
                  data-testid="revolve-profile"
                >
                  {profileName}
                </span>
              </div>
            )}

            {axes.length > 0 ? (
              <SelectField
                label="Axis"
                data-testid="revolve-axis"
                value={form.axisEntityId}
                options={axes.map((a) => ({ value: a.id, label: a.label }))}
                onChange={(e) =>
                  setForm((f) => ({ ...f, axisEntityId: e.target.value }))
                }
              />
            ) : (
              <p
                className="font-body text-xs text-flag"
                data-testid="revolve-axis-empty"
                role="status"
              >
                This sketch has no line to revolve about. Add a centerline.
              </p>
            )}

            <NumberField
              label="Angle"
              unit="°"
              data-testid="revolve-angle"
              autoFocus
              value={form.angleInput}
              error={angleMsg}
              onChange={(e) =>
                setForm((f) => ({ ...f, angleInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            <SegmentedControl
              label="Operation"
              value={form.operation}
              options={OPERATIONS}
              onChange={(operation) => setForm((f) => ({ ...f, operation }))}
            />

            <SegmentedControl
              label="Direction"
              value={form.direction}
              options={DIRECTIONS}
              onChange={(direction) => setForm((f) => ({ ...f, direction }))}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="revolve-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="revolve-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="revolve-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
