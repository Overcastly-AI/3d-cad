/**
 * The draft editor — the mold-release taper, in the same title-block seat the
 * shell/fillet/chamfer editors use. Keyboard-first: the angle field autofocuses,
 * Enter commits, Escape cancels — the sketcher's dimension grammar. ANGLE wears
 * brass because it is THE parametric handle of a draft (thickness is for shell,
 * offset for a datum).
 *
 * Three inputs compose the feature: the ANGLE (signed degrees, ＋ tapers inward
 * toward the pull); the FACES to taper (the shell face overlay, reused — click
 * body faces in the viewport, live count); and the NEUTRAL (parting) PLANE the
 * faces rotate about (the datum offset-plane idiom: base + offset + flip). A
 * draft with no faces has nothing to taper, so Apply stays disabled until at
 * least one face is picked (the `no_draft_faces` submit-guard).
 */
import {
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type LengthUnit,
  type SegmentOption,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect } from "react";

import type { DraftParams } from "../api/parts";
import {
  angleError,
  buildDraftParams,
  buildNeutralPlane,
  draftSubmitBlocker,
  DRAFT_NEUTRAL_BASES,
  type DraftForm,
  neutralOffsetError,
  parseAngleDeg,
} from "../features/draft";
import { useCommandBridge } from "../features/commandActions";
import { useFacePickStore } from "../features/facePickStore";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { DatumPlaneName } from "../sketch/plane";
import { EditorCard } from "./EditorCard";
import { gaugeWrite, useGaugeFedForm } from "./useGaugeFedForm";

/**
 * The open form projected for the VIEWPORT — what the taper gauge needs to place
 * itself (CRAFT-10).
 *
 * The neutral plane arrives ALREADY BUILT, through `buildNeutralPlane`, which is
 * the same function submit uses. So the plane the arc pivots about and the plane
 * Save persists are one derivation, and a unit-converted offset cannot mean one
 * thing on screen and another on the wire.
 */
export interface DraftGaugeState {
  /** Signed taper, degrees in (-90, 90). */
  angleDeg: number;
  base: DatumPlaneName;
  /** Offset along the base normal, canonical mm. */
  offsetMm: number;
  flip: boolean;
}

/** The form as a gauge projection, or null while it is incomplete. */
export function draftGaugeState(
  form: DraftForm,
  unit: LengthUnit,
): DraftGaugeState | null {
  const angleDeg = parseAngleDeg(form.angleInput);
  const plane = buildNeutralPlane(form.neutral, unit);
  // Zero parses as in-range but is the one value Save refuses, and a gauge on a
  // zero taper has no arc to draw — the two reasons coincide, which is what
  // makes this the honest gate rather than a convenience.
  if (angleDeg === null || angleDeg === 0 || plane === null) return null;
  return {
    angleDeg,
    base: plane.base,
    offsetMm: plane.offset_mm,
    flip: plane.flip,
  };
}

export interface DraftEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-draft defaults, or an existing draft's params). */
  initial: DraftForm;
  /** The anchor for picked face refs — the last body-affecting feature. */
  bodyFeatureId: string | null;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: DraftParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
  /**
   * Project the live form to the viewport gauge; called with null on unmount so
   * closing the editor never leaves a taper arc standing on the body.
   */
  onGaugeChange?: (state: DraftGaugeState | null) => void;
  /**
   * An angle set by DIRECT MANIPULATION — the viewport's taper gauge (CRAFT-10).
   * CONTRACT beta; `RevolveEditorProps.angleOverride` carries the full note on
   * what breaks, silently, when this is not fed back into the form.
   */
  angleOverride?: { deg: number } | null;
}

const BASE_OPTIONS: ReadonlyArray<SegmentOption<DatumPlaneName>> =
  DRAFT_NEUTRAL_BASES.map((b) => ({
    value: b.id,
    label: b.label,
    "data-testid": `draft-neutral-base-${b.id}`,
    "aria-label": `Neutral plane parallel to the ${b.label} datum`,
  }));

const PULL_OPTIONS: ReadonlyArray<SegmentOption<"keep" | "flip">> = [
  {
    value: "keep",
    label: "Out",
    "data-testid": "draft-pull-keep",
    "aria-label": "Pull along the neutral-plane normal",
  },
  {
    value: "flip",
    label: "Flipped",
    "data-testid": "draft-pull-flip",
    "aria-label": "Reverse the pull direction (the other mold half)",
  },
];

/**
 * A gauge-supplied angle, as the field would have been typed.
 *
 * The gauge quantises to its own drawn ladder, so this is normally an integer;
 * `Ctrl` frees the snap and can deliver a fraction, which is trimmed to the four
 * places `formatAngle` shows rather than written out to float precision. A field
 * that reads `2.9999999999999996` after a drag is a field that says the drag was
 * imprecise when it was not.
 */
function draftAngleInput(deg: number): string {
  const rounded = Math.round(deg * 1e4) / 1e4;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

/** The live picked-face line — a draft must pick at least one face. */
function faceCountText(count: number): string {
  if (count === 0) return "No faces picked yet";
  if (count === 1) return "1 face tapered";
  return `${count} faces tapered`;
}

export function DraftEditor({
  mode,
  initial,
  bodyFeatureId,
  onSubmit,
  onCancel,
  saving,
  error,
  onGaugeChange,
  angleOverride = null,
}: DraftEditorProps) {
  const unit = useDocumentLengthUnit();
  // Re-seeded on retarget; the viewport gauge writes THIS field — one angle,
  // two controls. Both writes land during render (`useGaugeFedForm`), so the
  // field commits WITH the override that carries it.
  const [form, setForm] = useGaugeFedForm(
    initial,
    gaugeWrite(angleOverride, (f: DraftForm, o) => ({
      ...f,
      angleInput: draftAngleInput(o.deg),
    })),
  );

  // Feed the viewport gauge; the cleanup clears it on unmount.
  useEffect(() => {
    onGaugeChange?.(draftGaugeState(form, unit));
    return () => onGaugeChange?.(null);
  }, [form, unit, onGaugeChange]);

  const picked = useFacePickStore((s) => s.picked);
  const overlayError = useFacePickStore((s) => s.overlayError);
  const clearPicks = useFacePickStore((s) => s.clearPicks);

  const submit = useCallback(() => {
    const params = buildDraftParams(form, picked, bodyFeatureId, unit);
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

  // ONE computation, two readings (REASON-GATE-1): `canSubmit` is DEFINED as
  // "nothing is blocking", so a grey Save with an empty reason line is
  // unreachable rather than merely absent. Null while saving — the label says
  // that already.
  const blocker = saving
    ? null
    : draftSubmitBlocker(form, picked, bodyFeatureId, unit);
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
              data-testid="draft-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
            <PanelActionCell
              label="Cancel"
              caption="Esc"
              data-testid="draft-cancel"
              disabled={saving}
              onClick={onCancel}
            />
            <PanelActionCell
              label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
              caption="Enter"
              data-testid="draft-submit"
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
      <Panel aria-label="Draft" data-testid="draft-editor">
        <div>
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New draft" : "Edit draft"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <NumberField
              label="Angle"
              unit="°"
              data-testid="draft-angle"
              autoFocus
              value={form.angleInput}
              error={angleError(form.angleInput)}
              onChange={(e) =>
                setForm((f) => ({ ...f, angleInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
              aria-label="Draft angle (degrees, signed)"
            />
            <p className="-mt-1 font-body text-xs text-gauge">
              ＋ tapers inward toward the pull (the top narrows — mold release);
              − tapers outward.
            </p>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="font-body text-xs text-gauge">
                  Faces to taper
                </span>
                <button
                  type="button"
                  data-testid="draft-pick-clear"
                  disabled={picked.length === 0}
                  onClick={clearPicks}
                  className="font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass disabled:text-gauge disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
              <p
                data-testid="draft-taper-count"
                aria-live="polite"
                className="font-data text-base text-mist"
              >
                {faceCountText(picked.length)}
              </p>
              <p className="font-body text-xs text-gauge">
                Click body faces in the view to taper them. Pick at least one.
              </p>
              {overlayError ? (
                <p
                  role="alert"
                  data-testid="draft-pick-error"
                  className="font-body text-xs text-flag"
                >
                  {overlayError}
                </p>
              ) : null}
            </div>

            <SegmentedControl
              label="Neutral plane"
              value={form.neutral.base}
              options={BASE_OPTIONS}
              onChange={(base) =>
                setForm((f) => ({ ...f, neutral: { ...f.neutral, base } }))
              }
            />
            <NumberField
              label="Neutral offset"
              unit={unit}
              data-testid="draft-neutral-offset"
              value={form.neutral.offsetInput}
              error={neutralOffsetError(form.neutral.offsetInput, unit)}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  neutral: { ...f.neutral, offsetInput: e.target.value },
                }))
              }
              onFocus={(e) => e.currentTarget.select()}
              aria-label={`Neutral-plane offset (${unit}, signed)`}
            />
            <p className="-mt-1 font-body text-xs text-gauge">
              The fixed plane the faces pivot about; its normal is the pull. 0
              sits on the {form.neutral.base} datum.
            </p>
            <SegmentedControl
              label="Pull"
              value={form.neutral.flip ? "flip" : "keep"}
              options={PULL_OPTIONS}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  neutral: { ...f.neutral, flip: v === "flip" },
                }))
              }
            />
          </div>
        </div>
      </Panel>
    </EditorCard>
  );
}
