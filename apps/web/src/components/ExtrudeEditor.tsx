/**
 * The extrude editor — a title-block strip docked in the left chrome rail, the
 * same seat the sketch strip uses (you author a sketch OR a feature, never
 * both, so they share one "authoring lives here" anchor and the viewport keeps
 * the pixels). Keyboard-first: the distance field autofocuses, Enter commits,
 * Escape cancels — the sketcher's dimension grammar. Distance wears brass
 * because it is THE parametric handle of the feature, matching the sketcher's
 * driving dimensions.
 *
 * DENSITY (FB-19, founder photo 2026-08-01: "chrome is too sparse"). This card
 * spent six full-width rows on five short values — every caption stacked over
 * its control, the two 2-state toggles a caption line each, and a helper
 * sentence permanently resident under Direction. The anatomy is now the title
 * block's own: caption BESIDE control (`FieldRow`), the two toggles sharing one
 * label-less row (their segments name themselves), and the sweep note behind a
 * balloon affordance — except when it warns, which is never hidden.
 *
 * Nothing was compacted below the product's floor: every control on the card is
 * a 24px target (`target.dense`, WCAG 2.2 SC 2.5.8) and Distance keeps the 32px
 * comfortable target it earns as the one thing the modeller came to type.
 */
import {
  Checkbox,
  FieldRow,
  formatLength,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect } from "react";

import { useCommandBridge } from "../features/commandActions";
import { lengthInputValue } from "../units/length";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { ExtrudeParams } from "../api/parts";
import {
  extrudeSubmitBlocker,
  describeExtrudeDirection,
  distanceError,
  type ExtrudeDirection,
  type ExtrudeForm,
  type ExtrudeOperation,
  type ExtrudePreviewState,
  extrudeParamsFromForm,
  formatTwistInput,
  parseTwistDeg,
  twistError,
  twistHand,
  extrudePreviewState,
  optionProvenance,
  parseDistanceMm,
  type PlaneProvenance,
  type ProfileOption,
  withDirection,
  withOperation,
  withProfile,
} from "../features/extrude";
import { EditorCard } from "./EditorCard";
import { gaugeWrite, useGaugeFedForm } from "./useGaugeFedForm";

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
  /**
   * Live preview projection of the form as the user types (UI-REVIEW #8) — the
   * viewport draws a ghost of the result before Save. Fired null on any
   * incomplete form and once on unmount (the ghost never lingers past close).
   */
  onPreviewChange?: (preview: ExtrudePreviewState | null) => void;
  /**
   * A distance set by DIRECT MANIPULATION — the viewport's depth gauge (T-23).
   *
   * The drag and the field are ONE value, and this is the seam that makes that
   * true rather than approximately true: the handle reports millimetres, the
   * form takes them, and the ghost redraws from the form. There is no second
   * copy of the depth anywhere, so the two controls cannot disagree.
   *
   * Boxed (`{ mm }`) so dragging back to a number the field already holds still
   * arrives — a bare number would compare equal and the update would be
   * swallowed.
   */
  depthOverride?: { mm: number } | null;
  /**
   * A twist set by DIRECT MANIPULATION — the viewport's twist arc on the far
   * cap (helical-gear gap G1). The same contract as `depthOverride`: the arc
   * asks, the Twist field takes the number, and the ghost and the arc redraw
   * from the field. Boxed for the same reason.
   */
  twistOverride?: { deg: number } | null;
  /**
   * The area centroid of a profile's closed regions, in its sketch's (x, y)
   * mm, or null when it has none. Offered as the twist axis only when known:
   * the editor sees profile ids, the caller sees their geometry.
   */
  profileCentroid?: (
    profileFeatureId: string,
  ) => { x: number; y: number } | null;
  // (The returned object must be STABLE per profile — it feeds the preview
  // effect's dependencies; PartPage memoises one map for the whole tree.)
}

/**
 * Past this many degrees (two turns) the editor says a save may be slow
 * (review S9). docs/design/twisted-extrude.md §6.1: until bounded tessellation
 * lands, meshing a twist of more than about two turns on a profile wide
 * relative to its distance can occupy a worker for tens of seconds (a 20 mm
 * square over 10 mm at 720 degrees: 14.8 s). The cost is not a function of the
 * twist alone, so the note is worded as "can", keyed on turns only, and
 * blocks nothing. Revisit when the kernel's F4 fix lands.
 */
const SLOW_TWIST_DEG = 720;

const TWIST_CENTRES: ReadonlyArray<SegmentOption<"origin" | "centroid">> = [
  {
    value: "origin",
    label: "Origin",
    "data-testid": "extrude-twist-centre-origin",
    "aria-label": "Twist axis: through the sketch origin",
  },
  {
    value: "centroid",
    label: "Centroid",
    "data-testid": "extrude-twist-centre-centroid",
    // The approximation, said where the choice is made (review S5): the point
    // is the area centroid of the drawn outline, whose arcs and splines are
    // polylines, so it sits within a few micrometres of the exact centroid
    // (~1.5 um at r = 10 mm), and further off on a coarse spline.
    "aria-label":
      "Twist axis: through the profile's centroid (measured on the drawn outline; within a few micrometres where it has arcs)",
  },
];

// No `icon` on these four: they render in a DENSE segmented control, which
// spends the glyph's width on the word instead (see `SegmentedControl`, and the
// 46.1px-in-45.5px measurement that decided it). Passing one anyway would be
// configuration nothing reads.
const OPERATIONS: ReadonlyArray<SegmentOption<ExtrudeOperation>> = [
  {
    value: "add",
    label: "Add",
    "data-testid": "extrude-op-add",
    "aria-label": "Operation: Add",
  },
  {
    value: "cut",
    label: "Cut",
    "data-testid": "extrude-op-cut",
    "aria-label": "Operation: Cut",
  },
];

const DIRECTIONS: ReadonlyArray<SegmentOption<ExtrudeDirection>> = [
  {
    value: "normal",
    label: "Normal",
    "data-testid": "extrude-dir-normal",
    "aria-label": "Direction: Normal",
  },
  {
    value: "reverse",
    label: "Reverse",
    "data-testid": "extrude-dir-reverse",
    "aria-label": "Direction: Reverse",
  },
];

/**
 * The one sweep state that is a WARNING rather than a description: a CUT
 * running along a face-seated sketch's normal leaves the solid immediately and
 * removes nothing (FB-4 — "I select a sketch do a cut it somehow misses
 * everything going a different way"). A warning is never hidden behind the note
 * affordance, so the row has to be able to tell the two apart.
 *
 * Derived from the same three inputs as {@link describeExtrudeDirection} rather
 * than by sniffing its sentence, and pinned to it by
 * `ExtrudeEditor.test.tsx` over all eight combinations — so the day the wording
 * changes, the test says so instead of the warning silently going quiet.
 */
export function sweepRemovesNothing(
  operation: ExtrudeOperation,
  direction: ExtrudeDirection,
  provenance: PlaneProvenance,
): boolean {
  return provenance === "face" && operation === "cut" && direction === "normal";
}

export function ExtrudeEditor({
  mode,
  profiles,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
  onPreviewChange,
  depthOverride = null,
  twistOverride = null,
  profileCentroid,
}: ExtrudeEditorProps) {
  const unit = useDocumentLengthUnit();
  // The re-seed on retarget and the gauge's write both happen DURING RENDER
  // (`useGaugeFedForm`), so the field commits with the override that carries
  // its value rather than one commit behind the drawn rod. The gauge's write is
  // in the DOCUMENT unit through the same formatter the seed uses, so a dragged
  // value and a typed one are indistinguishable afterwards — including on an
  // inch part, where the stored millimetres are not what the field shows — and
  // is re-written on a unit change.
  const [form, setForm] = useGaugeFedForm(
    initial,
    gaugeWrite(
      depthOverride,
      (f: ExtrudeForm, o) => ({
        ...f,
        distanceInput: lengthInputValue(o.mm, unit),
      }),
      unit,
    ),
    gaugeWrite(twistOverride, (f: ExtrudeForm, o) => ({
      ...f,
      twistInput: formatTwistInput(o.deg),
    })),
  );

  const centroid = profileCentroid?.(form.profileFeatureId) ?? null;

  // Feed the live ghost: every form/unit change re-projects the preview; the
  // cleanup clears it so closing the editor (unmount) never leaves a ghost.
  useEffect(() => {
    onPreviewChange?.(extrudePreviewState(form, unit, centroid));
    return () => onPreviewChange?.(null);
  }, [form, unit, onPreviewChange, centroid]);

  const submit = useCallback(() => {
    const distance = parseDistanceMm(form.distanceInput, unit);
    if (distance === null || form.profileFeatureId === "") return;
    if (parseTwistDeg(form.twistInput) === null) return;
    // Over the STORED params, never instead of them: a field this editor does
    // not show must survive an edit of one it does.
    onSubmit(extrudeParamsFromForm(form, distance, centroid));
  }, [form, onSubmit, unit, centroid]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  // The seat of the CHOSEN profile — a sketch on a model face knows which side
  // the material is on, a datum plane does not (FB-4). Read from the offered
  // options so retargeting the profile re-reads it.
  const provenance = optionProvenance(profiles, form.profileFeatureId);
  const distanceMsg = distanceError(form.distanceInput, unit);
  const twistMsg = twistError(form.twistInput);
  const twistDeg = parseTwistDeg(form.twistInput) ?? 0;
  // A chosen CENTROID of a profile that has none (no closed region yet) is
  // sent as no centre, i.e. the sketch origin. The control shows exactly that,
  // and the note says why, so the axis Save uses is never a silent surprise
  // (review S2: the segment used to keep "centroid" with nothing pressed).
  const centroidMissing =
    form.twistCentre.kind === "centroid" && centroid === null;
  // The centre the feature was SAVED with, offered as "Kept" (review S3), and
  // read in the document's unit, never as the raw float the row stores.
  const keptCentre = form.stored?.twist_center ?? null;
  const keptText =
    keptCentre === null
      ? ""
      : `(${formatLength(keptCentre.x, unit, { unitSuffix: false })}, ${formatLength(
          keptCentre.y,
          unit,
          { unitSuffix: false },
        )}) ${unit}`;
  const twistNote =
    twistDeg === 0
      ? undefined
      : `${twistHand(twistDeg)}: the far end turns ${Math.abs(twistDeg)}° ${
          twistDeg > 0 ? "anticlockwise" : "clockwise"
        } looking back along the extrude.${
          centroidMissing
            ? " This profile has no centroid yet (no closed region), so the axis is the sketch origin."
            : ""
        }`;
  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Save with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already.
  const blocker = saving ? null : extrudeSubmitBlocker(form, unit);
  const canSubmit = blocker === null && !saving;
  useCommandBridge(submit, canSubmit);
  const profileName =
    profiles.find((p) => p.id === form.profileFeatureId)?.name ?? "—";
  const sweepNote = describeExtrudeDirection(
    form.operation,
    form.direction,
    provenance,
  );
  const sweepWarns = sweepRemovesNothing(
    form.operation,
    form.direction,
    provenance,
  );

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
              data-testid="extrude-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
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
      <Panel aria-label="Extrude" data-testid="extrude-editor">
        <div>
          <h2 className="px-3 pb-1 pt-2 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New extrude" : "Edit extrude"}
          </h2>
          <div className="pb-1">
            {profiles.length > 1 ? (
              <SelectField
                label="Profile"
                layout="inline"
                data-testid="extrude-profile"
                value={form.profileFeatureId}
                options={profiles.map((p) => ({ value: p.id, label: p.name }))}
                onChange={(e) => {
                  const id = e.target.value;
                  setForm((f) =>
                    withProfile(f, id, optionProvenance(profiles, id)),
                  );
                }}
              />
            ) : (
              // One profile is not a choice, so it is not a control: a stamped
              // value cell in the same row shape the picker would take.
              <FieldRow label="Profile">
                <span
                  className="truncate font-data text-md text-mist"
                  data-testid="extrude-profile"
                >
                  {profileName}
                </span>
              </FieldRow>
            )}

            <NumberField
              label="Distance"
              layout="inline"
              emphasis="primary"
              unit={unit}
              data-testid="extrude-distance"
              autoFocus
              value={form.distanceInput}
              error={distanceMsg}
              onChange={(e) =>
                setForm((f) => ({ ...f, distanceInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            {/*
              THE TWIST (helical-gear gap G1). Quiet, one row, and empty by
              default: most extrudes are straight, and an untwisted extrude
              sends no twist fields at all. The arc on the ghost's far cap is
              the primary control; this is its exact fallback. The axis row
              appears only once there is a twist to put an axis under.
            */}
            <NumberField
              label="Twist"
              layout="inline"
              unit="°"
              placeholder="0"
              data-testid="extrude-twist"
              value={form.twistInput}
              error={twistMsg}
              onChange={(e) =>
                setForm((f) => ({ ...f, twistInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />
            {Math.abs(twistDeg) > SLOW_TWIST_DEG ? (
              // A heads-up, not a warning: quiet ink, no flag, nothing blocked.
              // Set exactly as a FieldRow note is (px-3, gauge, xs), under the
              // row it is about.
              <p
                className="px-3 font-body text-xs text-gauge"
                data-testid="extrude-twist-slow"
              >
                Large twists over short distances can take a while to build.
              </p>
            ) : null}
            {twistDeg !== 0 ? (
              <FieldRow
                label="Axis"
                note={twistNote}
                noteLabel="About the twist"
                noteTestId="extrude-twist-hint"
              >
                {/*
                  Origin, Centroid, and KEPT when the feature was saved with a
                  centre of its own (a script's point, or an earlier Centroid).
                  Kept is pre-selected, so a no-op Save leaves the helix alone,
                  but it is one segment of three, not a read-only label: the
                  axis can always go back to the origin (review S3).
                */}
                <div className="flex min-w-0 grow flex-col gap-0.5">
                  <SegmentedControl
                    label="Twist axis"
                    hideLabel
                    size="dense"
                    value={
                      form.twistCentre.kind === "point"
                        ? "kept"
                        : centroidMissing
                          ? "origin"
                          : form.twistCentre.kind
                    }
                    options={[
                      ...(centroid === null
                        ? TWIST_CENTRES.slice(0, 1)
                        : TWIST_CENTRES),
                      ...(keptCentre === null
                        ? []
                        : [
                            {
                              value: "kept" as const,
                              label: "Kept",
                              "data-testid": "extrude-twist-centre-kept",
                              "aria-label": `Twist axis: kept at ${keptText}`,
                            },
                          ]),
                    ]}
                    onChange={(kind) =>
                      setForm((f) => ({
                        ...f,
                        twistCentre:
                          kind === "kept" && keptCentre !== null
                            ? { kind: "point", at: keptCentre }
                            : kind === "centroid"
                              ? { kind: "centroid" }
                              : { kind: "origin" },
                      }))
                    }
                  />
                  {form.twistCentre.kind === "point" ? (
                    <span
                      className="font-data text-xs text-gauge"
                      data-testid="extrude-twist-centre-point"
                    >
                      {keptText}
                    </span>
                  ) : null}
                </div>
              </FieldRow>
            ) : null}

            {/*
              THE SWEEP ROW. Operation and Direction are both 2-state and both
              name themselves in their segments, so they share one label-less
              row: four words instead of two captions and two control lines.
              Each group keeps its `aria-label`, and every segment's accessible
              name still carries the group ("Operation: Add"), which is also its
              tooltip — the caption is gone from the screen, not from the
              product.
            */}
            <FieldRow
              note={sweepNote}
              noteTone={sweepWarns ? "flag" : "quiet"}
              noteLabel="About the sweep direction"
              noteTestId="extrude-direction-hint"
            >
              <SegmentedControl
                label="Operation"
                hideLabel
                size="dense"
                value={form.operation}
                options={OPERATIONS}
                onChange={(operation) =>
                  setForm((f) => withOperation(f, operation, provenance))
                }
              />
              <SegmentedControl
                label="Direction"
                hideLabel
                size="dense"
                value={form.direction}
                options={DIRECTIONS}
                onChange={(direction) =>
                  setForm((f) => withDirection(f, direction))
                }
              />
            </FieldRow>

            {form.operation === "add" ? (
              // The old cell was "Merge result" plus a permanently-resident
              // sentence saying what the current state means. One element, one
              // job: the checkbox's own label IS the outcome, so the sentence
              // has nowhere to be redundant from.
              <FieldRow label="Merge">
                <Checkbox
                  label={
                    form.merge
                      ? "Fuse into the touching body"
                      : "Start a new body"
                  }
                  data-testid="extrude-merge"
                  checked={form.merge}
                  onChange={(merge) => setForm((f) => ({ ...f, merge }))}
                />
              </FieldRow>
            ) : null}
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}
