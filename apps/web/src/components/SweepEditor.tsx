/**
 * The sweep editor — the revolve editor's twin, in the same title-block seat
 * top-left of the viewport (you author one feature at a time). Its distinctive
 * field is the DOUBLE feature reference: unlike extrude/revolve, which consume
 * the implicit preceding sketch, a sweep explicitly designates TWO earlier
 * sketches — a closed PROFILE and an open PATH. Both are offered as ruled
 * selects over the tree's sketch features (the revolve axis-select idiom):
 * keyboard-first, deterministically testable, no viewport selection layer.
 *
 * The path list excludes whatever the profile currently names — one sketch
 * fills one slot. Keyboard-first: the profile select autofocuses, Enter
 * commits, Escape cancels — the sketcher's dimension grammar. There is no
 * numeric handle here (the geometry lives in the two referenced sketches), so
 * the honest scope note carries the limits: the path is one chain, open or
 * closed, and a closed path must be tangent-continuous at every joint
 * (SWEEP-CLOSED-PATH; a corner is the rebuild error `sweep_path_not_tangent`).
 *
 * TWIST ALONG PATH (TWIST-TO-SWEEP) is the one number: the total turn of the
 * section over the sweep, in signed degrees (the document's angle convention,
 * as the revolve's Angle). It is where Fusion 360 and SolidWorks put it, and
 * where the Extrude's twist moved from. v1 twists exactly along one straight
 * line perpendicular to the profile, starting at it; any other path with a
 * twist is refused at rebuild (`twist_path_unsupported`), and that reason, like
 * every rebuild error of the sweep being edited, reads in this card.
 */
import {
  AddIcon,
  Checkbox,
  CutIcon,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import { useCommandBridge } from "../features/commandActions";
import type { SketchEntity, SweepParams } from "../api/parts";
import {
  buildSweepParams,
  sweepSubmitBlocker,
  type ProfileOption,
  type SweepForm,
  type SweepOperation,
} from "../features/sweep";
import {
  parseTwistDeg,
  TWIST_COST_LIMIT_S,
  twistCostUpperS,
  twistError,
  twistHand,
} from "../features/twist";
import { EditorCard } from "./EditorCard";
import { ValueField } from "./ValueField";

export interface SweepEditorProps {
  mode: "create" | "edit";
  /** Every sketch feature in the tree, in build order (the profile choices). */
  profiles: readonly ProfileOption[];
  /** Path choices per profile feature id (every sketch except that profile). */
  pathsByProfile: Readonly<Record<string, readonly ProfileOption[]>>;
  /** The seed form (new-sweep defaults, or an existing sweep's params). */
  initial: SweepForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: SweepParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
  /**
   * The REBUILD error of the sweep being edited (its FeatureResult), already
   * in friendly copy, or null. Shown in the error slot while the form still
   * holds what was saved: once the user changes a field, the reason describes
   * a state they are already correcting.
   */
  rebuildError?: string | null;
  /**
   * A profile's sketch entities, or null when unknown: what the twist-cost
   * heads-up (review S9) counts edges from.
   */
  profileEntities?: (
    profileFeatureId: string,
  ) => readonly SketchEntity[] | null;
}

const OPERATIONS: ReadonlyArray<SegmentOption<SweepOperation>> = [
  {
    value: "add",
    label: "Add",
    icon: <AddIcon />,
    "data-testid": "sweep-op-add",
    "aria-label": "Operation: Add",
  },
  {
    value: "cut",
    label: "Cut",
    icon: <CutIcon />,
    "data-testid": "sweep-op-cut",
    "aria-label": "Operation: Cut",
  },
];

export function SweepEditor({
  mode,
  profiles,
  pathsByProfile,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
  rebuildError = null,
  profileEntities,
}: SweepEditorProps) {
  const [form, setForm] = useState<SweepForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  const paths = pathsByProfile[form.profileFeatureId] ?? [];

  const twistMsg = twistError(form.twistInput);
  const twistDeg = parseTwistDeg(form.twistInput) ?? 0;
  const twistNote =
    twistDeg === 0
      ? null
      : `${twistHand(twistDeg)}: the far end turns ${Math.abs(twistDeg)}° ${
          twistDeg > 0 ? "anticlockwise" : "clockwise"
        } looking back along the path. The path must be one straight line perpendicular to the profile, starting at it.`;
  // Review S9, carried over from the extrude: the kernel REFUSES a twist its
  // own cost estimate puts over TWIST_COST_LIMIT_S, and the cost is in TURNS
  // and the profile's EDGES (design note §6.1). "May", because the bound
  // over-states the kernel's estimate up to 2x and the kernel's verdict rules.
  const entities = profileEntities?.(form.profileFeatureId) ?? null;
  const twistMayBeRefused =
    entities !== null &&
    twistCostUpperS(twistDeg, entities) > TWIST_COST_LIMIT_S;
  // The stored rebuild error describes the SAVED sweep; it stays up only
  // while the form still says what was saved.
  const untouched =
    form.profileFeatureId === initial.profileFeatureId &&
    form.pathFeatureId === initial.pathFeatureId &&
    form.operation === initial.operation &&
    form.merge === initial.merge &&
    form.twistInput === initial.twistInput;
  const shownRebuildError = untouched ? rebuildError : null;

  const submit = useCallback(() => {
    const params = buildSweepParams(form);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  // Changing the profile re-scopes the path list; if the current path is now
  // the profile (illegal — one sketch, one slot), fall back to a fresh default.
  const onProfileChange = useCallback(
    (profileFeatureId: string) => {
      setForm((f) => ({
        ...f,
        profileFeatureId,
        pathFeatureId:
          f.pathFeatureId !== "" && f.pathFeatureId !== profileFeatureId
            ? f.pathFeatureId
            : defaultSweepPathIdFrom(pathsByProfile, profileFeatureId),
      }));
    },
    [pathsByProfile],
  );

  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Create with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already. "No other sketch exists at all" is asked FIRST and lives here
  // rather than in `sweepSubmitBlocker`: it is a fact about the part, and
  // asking for a path the tree cannot supply is a dead end, not a next step.
  const blocker = saving
    ? null
    : paths.length === 0
      ? "Draw a path sketch to sweep along."
      : sweepSubmitBlocker(form);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);

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
              data-testid="sweep-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : shownRebuildError ? (
            // The same flag slot as a failed save: this sweep's last rebuild
            // failed, and here is what cures it.
            <p
              role="alert"
              data-testid="sweep-rebuild-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {shownRebuildError}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="sweep-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="sweep-submit"
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
      <Panel aria-label="Sweep" data-testid="sweep-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New sweep" : "Edit sweep"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SelectField
              label="Profile"
              data-testid="sweep-profile"
              autoFocus
              value={form.profileFeatureId}
              options={profiles.map((p) => ({ value: p.id, label: p.name }))}
              onChange={(e) => onProfileChange(e.target.value)}
            />

            {paths.length > 0 ? (
              <SelectField
                label="Path"
                data-testid="sweep-path"
                value={form.pathFeatureId}
                options={paths.map((p) => ({ value: p.id, label: p.name }))}
                onChange={(e) =>
                  setForm((f) => ({ ...f, pathFeatureId: e.target.value }))
                }
              />
            ) : (
              <p
                className="font-body text-xs text-flag"
                data-testid="sweep-path-empty"
                role="status"
              >
                No other sketch to sweep along. Draw a path sketch.
              </p>
            )}

            <ValueField
              label="Twist"
              unit="°"
              placeholder="0"
              // `text`, not the NumberField default `decimal`: iOS's decimal pad
              // has no minus sign, and a LEFT-hand twist is negative (review
              // N4). `parseTwistDeg` is the gate on what was typed.
              inputMode="text"
              kind="angle"
              pointer="/twist_angle_deg"
              data-testid="sweep-twist"
              value={form.twistInput}
              error={twistMsg}
              onValueChange={(value) =>
                setForm((f) => ({ ...f, twistInput: value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />
            {twistNote !== null ? (
              <p
                className="-mt-1 font-body text-xs text-gauge"
                data-testid="sweep-twist-note"
              >
                {twistNote}
              </p>
            ) : null}
            {twistMayBeRefused ? (
              // A heads-up, not a warning: quiet ink, no flag, nothing blocked.
              <p
                className="-mt-1 font-body text-xs text-gauge"
                data-testid="sweep-twist-slow"
              >
                This many turns on this profile may be slow to build, or refused
                as too costly. Fewer turns or fewer edges help.
              </p>
            ) : null}

            <SegmentedControl
              label="Operation"
              value={form.operation}
              options={OPERATIONS}
              onChange={(operation) => setForm((f) => ({ ...f, operation }))}
            />

            {form.operation === "add" ? (
              <Checkbox
                label="Merge result"
                data-testid="sweep-merge"
                checked={form.merge}
                onChange={(merge) => setForm((f) => ({ ...f, merge }))}
                description={
                  form.merge
                    ? "Fuse into the touching body."
                    : "Start a new body."
                }
              />
            ) : null}
            <p
              className="-mt-0.5 font-body text-xs text-gauge"
              data-testid="sweep-path-note"
            >
              The path sketch is one chain, open or closed. A closed path must
              be tangent at every joint, and the section rides it from the
              profile.
            </p>
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}

/** First eligible path in the precomputed map for a profile, or "". */
function defaultSweepPathIdFrom(
  pathsByProfile: Readonly<Record<string, readonly ProfileOption[]>>,
  profileFeatureId: string,
): string {
  const options = pathsByProfile[profileFeatureId] ?? [];
  return options.length > 0 ? (options[0]?.id ?? "") : "";
}
