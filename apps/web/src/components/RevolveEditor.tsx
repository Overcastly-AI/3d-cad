/**
 * The revolve editor — the extrude editor's twin, in the same title-block seat
 * top-left of the viewport (you author a sketch OR a feature, never both). Its
 * one extra field over extrude is the AXIS, a ruled select ranked so that its
 * FIRST row is the turn we are proposing: a drawn centerline, else a world
 * origin axis, else a profile edge (see `features/revolve`). Keyboard-first:
 * the angle field autofocuses, Enter commits, Escape cancels — the sketcher's
 * dimension grammar. Angle wears brass because it is THE parametric handle.
 *
 * An axis the kernel would refuse stays IN the list, disabled, wearing its
 * reason in its own label — and when the stored axis of a feature being edited
 * is one of those, the reason is repeated below the cell as a live status line,
 * because a disabled option cannot be arrowed onto to be read.
 */
import {
  AddIcon,
  Checkbox,
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
import { type KeyboardEvent, useCallback, useEffect } from "react";

import { useCommandBridge } from "../features/commandActions";
import type { RevolveParams } from "../api/parts";
import {
  angleError,
  type AxisOption,
  axisReason,
  axisRef,
  revolveSubmitBlocker,
  defaultAxisId,
  formatAngleInput,
  parseAngleDeg,
  type ProfileOption,
  revolveParamsFromForm,
  type RevolveAxisRef,
  type RevolveDirection,
  type RevolveForm,
  type RevolveOperation,
} from "../features/revolve";
import { EditorCard } from "./EditorCard";
import { gaugeWrite, useGaugeFedForm } from "./useGaugeFedForm";

/**
 * The open form projected for the VIEWPORT — what the sweep gauge needs in order
 * to place itself, and nothing else (CRAFT-10).
 *
 * It carries the RESOLVED `axis` rather than the form's `axisId`, because the id
 * is an OPTION KEY scoped to one profile's option list and the viewport has no
 * business re-deriving a wire value from it. `axisRef` is the one place that
 * translation happens, exactly as it is on submit — so the axis the arc is drawn
 * about and the axis Save persists cannot come apart.
 */
export interface RevolveGaugeState {
  profileFeatureId: string;
  /** The axis of revolution, as it will be persisted. */
  axis: RevolveAxisRef;
  /** The sweep, degrees in (0, 360]. */
  angleDeg: number;
}

/** The form as a gauge projection, or null while it is incomplete. */
export function revolveGaugeState(
  form: RevolveForm,
  axes: readonly AxisOption[],
): RevolveGaugeState | null {
  const angleDeg = parseAngleDeg(form.angleInput);
  const axis = axisRef(axes, form.axisId);
  if (angleDeg === null || axis === null || form.profileFeatureId === "")
    return null;
  return { profileFeatureId: form.profileFeatureId, axis, angleDeg };
}

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
  /**
   * Project the live form to the viewport gauge. Called on every form change
   * and once with null on unmount, so closing the editor never leaves an arc
   * standing on a feature nobody is editing.
   */
  onGaugeChange?: (state: RevolveGaugeState | null) => void;
  /**
   * An angle set by DIRECT MANIPULATION — the viewport's sweep gauge (CRAFT-10).
   *
   * CONTRACT beta, and both halves of it look finished alone: the gauge renders
   * its own last ask until the pointer is released and then falls back to the
   * `value` prop it was given. If this override does not come back round into
   * the form, the arc springs back to where the drag STARTED the instant you let
   * go, while the field below shows the number you dragged to. The drag is
   * smooth and correct for its whole duration, so the defect fires after every
   * screenshot anyone would take.
   *
   * Boxed (`{ deg }`) so dragging out and back to a number the field already
   * holds still arrives — a bare number would compare equal and be swallowed.
   */
  angleOverride?: { deg: number } | null;
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
  onGaugeChange,
  angleOverride = null,
}: RevolveEditorProps) {
  // Re-seeded when the editor is retargeted at a different feature. The
  // viewport gauge writes THIS field. It is not a second copy of the angle;
  // it is the same one, reached by a different control — and it is written
  // through the same formatter the seed uses, so a dragged value and a typed one
  // are indistinguishable afterwards. Both writes land during render
  // (`useGaugeFedForm`), so the field commits WITH the override that carries it.
  const [form, setForm] = useGaugeFedForm(
    initial,
    gaugeWrite(angleOverride, (f: RevolveForm, o) => ({
      ...f,
      angleInput: formatAngleInput(o.deg),
    })),
  );

  const axes = axesByProfile[form.profileFeatureId] ?? [];

  const submit = useCallback(() => {
    // The axis comes back from the option list, never rebuilt from the id: the
    // select can only ever send an axis it actually offered.
    const axis = axisRef(axes, form.axisId);
    if (axis === null) return;
    const params = revolveParamsFromForm(form, axis);
    if (params === null) return;
    onSubmit(params);
  }, [axes, form, onSubmit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  // Changing the profile re-scopes the axis to the new sketch's own axes.
  const onProfileChange = useCallback(
    (profileFeatureId: string) => {
      setForm((f) => ({
        ...f,
        profileFeatureId,
        axisId: defaultAxisId(axesByProfile[profileFeatureId] ?? []),
      }));
    },
    [axesByProfile],
  );

  // Feed the viewport gauge: every form change re-projects it, and the cleanup
  // clears it so closing the editor (unmount) never leaves an arc behind.
  //
  // `axes` is DELIBERATELY not in the dependency list. It is
  // `axesByProfile[form.profileFeatureId]`, a fresh array identity on every
  // render, so depending on it would re-run this effect — and therefore fire its
  // cleanup, nulling the gauge — on every frame of a drag. `axesByProfile` and
  // the profile id are the only inputs that can change what it resolves to.
  useEffect(() => {
    const options = axesByProfile[form.profileFeatureId] ?? [];
    onGaugeChange?.(revolveGaugeState(form, options));
    return () => onGaugeChange?.(null);
  }, [form, axesByProfile, onGaugeChange]);

  const angleMsg = angleError(form.angleInput);
  const axisMsg = axisReason(axes, form.axisId);
  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Save with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already.
  const blocker = saving ? null : revolveSubmitBlocker(form, axes);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);
  const profileName =
    profiles.find((p) => p.id === form.profileFeatureId)?.name ?? "—";

  return (
    <EditorCard
      onKeyDown={onKeyDown}
      // THE ACTION ROW IS PINNED, not scrolled (REASON-GATE-1, the shape
      // `HoleEditor` has used since UI-REVIEW 2026-07-30 P1 and `HemEditor`
      // since HEM-1B). It used to ride inside the scrolling body, so at the
      // 1280x800 floor a tall form could put the commit action — and the
      // sentence explaining why it is grey — below the fold of its own card.
      // An explanation the stuck user has to scroll for is the defect wearing
      // a longer sentence.
      footer={
        <>
          {error ? (
            <p
              role="alert"
              data-testid="revolve-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
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
              // The reason takes the caption's line while gated and is wired as
              // the cell's `aria-describedby` — eye, pointer and screen reader
              // get the same sentence. `blocker` is null while SAVING: the
              // label already says so, and a second sentence saying it again
              // would be the one accessory to remove.
              disabledReason={blocker ?? undefined}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel aria-label="Revolve" data-testid="revolve-editor">
        <div>
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
                value={form.axisId}
                error={axisMsg}
                options={axes.map((a) => ({
                  value: a.id,
                  label: a.label,
                  disabled: a.reason !== null,
                }))}
                onChange={(e) =>
                  setForm((f) => ({ ...f, axisId: e.target.value }))
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

            {form.operation === "add" ? (
              <Checkbox
                label="Merge result"
                data-testid="revolve-merge"
                checked={form.merge}
                onChange={(merge) => setForm((f) => ({ ...f, merge }))}
                description={
                  form.merge
                    ? "Fuse into the touching body."
                    : "Start a new body."
                }
              />
            ) : null}
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}
