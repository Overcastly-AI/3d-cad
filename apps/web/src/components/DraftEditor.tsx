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
  type SegmentOption,
} from "@loft/design";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import type { DraftParams } from "../api/parts";
import {
  angleError,
  buildDraftParams,
  canSubmitDraft,
  DRAFT_NEUTRAL_BASES,
  type DraftForm,
  neutralOffsetError,
} from "../features/draft";
import { useCommandBridge } from "../features/commandActions";
import { useFacePickStore } from "../features/facePickStore";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { DatumPlaneName } from "../sketch/plane";

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
}: DraftEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<DraftForm>(initial);
  useEffect(() => setForm(initial), [initial]);

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
      } else if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    },
    [saving, submit, onCancel],
  );

  const canSubmit =
    canSubmitDraft(form, picked, bodyFeatureId, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Draft" data-testid="draft-editor">
        <div className="border-b border-hairline">
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
              aria-label="Neutral-plane offset (mm, signed)"
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

        <div className="grid grid-cols-2 divide-x divide-hairline">
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
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="draft-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
