/**
 * The datum-plane editor — the pattern/revolve editor's twin in the same
 * title-block seat top-left of the viewport. A datum plane is a construction
 * plane that produces no body, only a plane later sketches sit on
 * (docs/design/datum-planes.md §3/§7). Its structural choice is the KIND
 * (a ruled Type select): an OFFSET from an origin datum, an offset FROM another
 * datum (chaining), a MIDPLANE midway between two references (each an origin
 * datum, an earlier datum, or a picked model FACE), or ON a picked model FACE.
 * Each kind wears one parametric handle in brass focus — the offset distance for
 * the offset kinds, the first reference for a midplane, the picked face for
 * on-face. The face references are authored by clicking the highlighted face in
 * the viewport (the parent renders the `FacePickOverlay`); the editor arms the
 * pick and folds the clicked face into the armed slot. Keyboard-first: the
 * handle autofocuses, Enter commits, Escape cancels — the sketcher's dimension
 * grammar (Escape disarms an armed pick first, handled by the parent).
 */
import {
  cx,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
  SelectField,
} from "@loft/design";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { useCommandBridge } from "../features/commandActions";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { DatumParams } from "../api/parts";
import {
  applyFacePick,
  buildDatumParams,
  canSubmitDatum,
  DATUM_BASES,
  type DatumFace,
  type DatumFacePick,
  type DatumFaceSlot,
  type DatumForm,
  type DatumKind,
  type DatumRef,
  type MidplaneSideForm,
  datumRefOptions,
  defaultFormForKind,
  faceReadout,
  midplaneSideOptions,
  offsetError,
  refMidplaneSide,
} from "../features/datum";
import type { DatumPlaneName } from "../sketch/plane";

export interface DatumEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-datum defaults, or an existing datum's params). */
  initial: DatumForm;
  /** Earlier datum features — the references offset-from + midplane draw on. */
  datumRefs: readonly DatumRef[];
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: DatumParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
  /** A body with pickable planar faces exists — gates the face-pick affordances. */
  canPickFace: boolean;
  /** The slot whose face pick is currently armed (the parent highlights faces). */
  activeFacePickSlot: DatumFaceSlot | null;
  /** Arm/disarm face picking for a slot (the parent renders the overlay). */
  onToggleFacePick: (slot: DatumFaceSlot) => void;
  /** The latest picked face for a slot, delivered once per pick (nonce-guarded). */
  facePick: DatumFacePick | null;
  /** Why a face can't be picked right now (no body / no anchor), or null. */
  facePickError: string | null;
}

const KIND_OPTIONS: ReadonlyArray<{ value: DatumKind; label: string }> = [
  { value: "offset", label: "Offset from origin plane" },
  { value: "offset_from", label: "Offset from a datum" },
  { value: "midplane", label: "Midplane between two references" },
  { value: "on_face", label: "On a model face" },
];

const BASE_OPTIONS: ReadonlyArray<SegmentOption<DatumPlaneName>> =
  DATUM_BASES.map((b) => ({
    value: b.id,
    label: b.label,
    "data-testid": `datum-base-${b.id}`,
    "aria-label": `Parallel to the ${b.label} datum`,
  }));

const FLIP_OPTIONS: ReadonlyArray<SegmentOption<"keep" | "flip">> = [
  {
    value: "keep",
    label: "Normal",
    "data-testid": "datum-flip-keep",
    "aria-label": "Keep the plane normal",
  },
  {
    value: "flip",
    label: "Flipped",
    "data-testid": "datum-flip-flip",
    "aria-label": "Reverse the plane normal",
  },
];

/** The Normal / Flipped toggle every kind shares. */
function FlipControl({
  flip,
  onChange,
}: {
  flip: boolean;
  onChange: (flip: boolean) => void;
}) {
  return (
    <SegmentedControl
      label="Normal"
      value={flip ? "flip" : "keep"}
      options={FLIP_OPTIONS}
      onChange={(v) => onChange(v === "flip")}
    />
  );
}

/** A quiet, brass-when-armed toggle to arm a viewport face pick for a slot. */
function FacePickButton({
  armed,
  onClick,
  testId,
  label,
  ariaLabel,
}: {
  armed: boolean;
  onClick: () => void;
  testId: string;
  label: string;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={armed}
      aria-label={ariaLabel}
      onClick={onClick}
      className={cx(
        "self-start rounded-sm border px-2 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass",
        armed
          ? "border-brass text-brass"
          : "border-etch text-gauge hover:border-gauge hover:text-mist",
      )}
    >
      {armed ? "Picking… (click a face)" : label}
    </button>
  );
}

/** A picked-face readout (labelled, brass-bordered) with a Clear back-out — the
 * shared chip both the midplane FACE-sides and the on_face base wear. */
function PickedFaceChip({
  label,
  face,
  readoutTestId,
  clearTestId,
  onClear,
}: {
  label: string;
  face: DatumFace;
  readoutTestId: string;
  clearTestId: string;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-body text-xs text-gauge">{label}</span>
      <div className="flex items-center justify-between gap-2 rounded-sm border border-brass/60 bg-carbide px-2 py-1">
        <span
          data-testid={readoutTestId}
          className="min-w-0 truncate font-data text-md text-mist"
        >
          {faceReadout(face)}
        </span>
        <button
          type="button"
          data-testid={clearTestId}
          onClick={onClear}
          className="shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-brass focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

/** One midplane side: a reference dropdown OR a picked-face chip, with a pick
 * affordance. Wearing a face swaps the dropdown for a readout the engineer can
 * clear back to a reference. */
function MidplaneSideField({
  slot,
  label,
  testIdBase,
  side,
  refOptions,
  armed,
  canPickFace,
  autoFocus,
  onSelectRef,
  onClearFace,
  onToggleFacePick,
}: {
  slot: DatumFaceSlot;
  label: string;
  testIdBase: string;
  side: MidplaneSideForm;
  refOptions: { value: string; label: string }[];
  armed: boolean;
  canPickFace: boolean;
  autoFocus: boolean;
  onSelectRef: (value: string) => void;
  onClearFace: () => void;
  onToggleFacePick: (slot: DatumFaceSlot) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      {side.source === "face" ? (
        <PickedFaceChip
          label={label}
          face={side.face}
          readoutTestId={`${testIdBase}-face`}
          clearTestId={`${testIdBase}-face-clear`}
          onClear={onClearFace}
        />
      ) : (
        <SelectField
          label={label}
          data-testid={testIdBase}
          autoFocus={autoFocus}
          value={side.value}
          options={refOptions}
          onChange={(e) => onSelectRef(e.target.value)}
          aria-label={`${label.replace(/ reference$/, "")} midplane reference`}
        />
      )}
      {canPickFace ? (
        <FacePickButton
          armed={armed}
          testId={`${testIdBase}-pick`}
          label={side.source === "face" ? "Pick another face" : "Pick a face"}
          ariaLabel={`Pick a model face for the ${label.toLowerCase()}`}
          onClick={() => onToggleFacePick(slot)}
        />
      ) : null}
    </div>
  );
}

export function DatumEditor({
  mode,
  initial,
  datumRefs,
  onSubmit,
  onCancel,
  saving,
  error,
  canPickFace,
  activeFacePickSlot,
  onToggleFacePick,
  facePick,
  facePickError,
}: DatumEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<DatumForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  // Fold each delivered viewport face pick into its slot exactly once — the
  // nonce guards against a re-render re-applying the same pick.
  const lastPickNonce = useRef(0);
  useEffect(() => {
    if (facePick === null || facePick.nonce === lastPickNonce.current) return;
    lastPickNonce.current = facePick.nonce;
    setForm((f) => applyFacePick(f, facePick.slot, facePick.face));
  }, [facePick]);

  const submit = useCallback(() => {
    const params = buildDatumParams(form, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit, unit]);

  // Enter commits — except when a button (the footer / a segment) has focus:
  // Enter must fire that control's own action. Escape (cancel) is owned by the
  // parent's window handler, the one cancel path for every editor (FINDINGS
  // #11); while a face pick is armed the parent's pick handler takes Escape
  // first to disarm the pick.
  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        if (event.target instanceof HTMLButtonElement) return;
        event.preventDefault();
        if (!saving) submit();
      }
    },
    [saving, submit],
  );

  const canSubmit = canSubmitDatum(form, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  const noDatums = datumRefs.length === 0;

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Datum plane" data-testid="datum-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New datum plane" : "Edit datum plane"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            <SelectField
              label="Type"
              data-testid="datum-kind"
              value={form.kind}
              options={KIND_OPTIONS}
              onChange={(e) =>
                setForm((f) =>
                  defaultFormForKind(
                    e.target.value as DatumKind,
                    f.kind === "on_face" ? false : f.flip,
                  ),
                )
              }
              aria-label="Datum plane type"
            />

            {form.kind === "offset" ? (
              <>
                <SegmentedControl
                  label="Parallel to"
                  value={form.base}
                  options={BASE_OPTIONS}
                  onChange={(base) => setForm((f) => ({ ...f, base }))}
                />
                <NumberField
                  label="Offset"
                  unit={unit}
                  data-testid="datum-offset"
                  autoFocus
                  value={form.offsetInput}
                  error={offsetError(form.offsetInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, offsetInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Offset distance (signed)"
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  Distance along the {form.base} normal. 0 sits on the datum;
                  negative offsets the other side.
                </p>
                <FlipControl
                  flip={form.flip}
                  onChange={(flip) => setForm((f) => ({ ...f, flip }))}
                />
              </>
            ) : null}

            {form.kind === "offset_from" ? (
              <>
                <SelectField
                  label="Base plane"
                  data-testid="datum-base-plane"
                  autoFocus
                  value={form.baseFeatureId}
                  options={datumRefOptions(datumRefs)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, baseFeatureId: e.target.value }))
                  }
                  aria-label="Datum plane to offset from"
                />
                <NumberField
                  label="Offset"
                  unit={unit}
                  data-testid="datum-offset"
                  value={form.offsetInput}
                  error={offsetError(form.offsetInput, unit)}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, offsetInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Offset distance (signed)"
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  {noDatums
                    ? "Create a datum plane first — this offsets from one."
                    : "Distance along the base datum's normal. 0 sits on it."}
                </p>
                <FlipControl
                  flip={form.flip}
                  onChange={(flip) => setForm((f) => ({ ...f, flip }))}
                />
              </>
            ) : null}

            {form.kind === "midplane" ? (
              <>
                <MidplaneSideField
                  slot="midplane-a"
                  label="First reference"
                  testIdBase="datum-side-a"
                  side={form.a}
                  refOptions={midplaneSideOptions(datumRefs)}
                  armed={activeFacePickSlot === "midplane-a"}
                  canPickFace={canPickFace}
                  autoFocus
                  onSelectRef={(value) =>
                    setForm((f) => ({ ...f, a: refMidplaneSide(value) }))
                  }
                  onClearFace={() =>
                    setForm((f) => ({ ...f, a: refMidplaneSide("") }))
                  }
                  onToggleFacePick={onToggleFacePick}
                />
                <MidplaneSideField
                  slot="midplane-b"
                  label="Second reference"
                  testIdBase="datum-side-b"
                  side={form.b}
                  refOptions={midplaneSideOptions(datumRefs)}
                  armed={activeFacePickSlot === "midplane-b"}
                  canPickFace={canPickFace}
                  autoFocus={false}
                  onSelectRef={(value) =>
                    setForm((f) => ({ ...f, b: refMidplaneSide(value) }))
                  }
                  onClearFace={() =>
                    setForm((f) => ({ ...f, b: refMidplaneSide("") }))
                  }
                  onToggleFacePick={onToggleFacePick}
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  The plane midway between the two references. Parallel
                  references give a plane halfway between them; angled ones give
                  their bisector. A reference can be an origin datum, an earlier
                  datum, or a picked model face.
                </p>
                <FlipControl
                  flip={form.flip}
                  onChange={(flip) => setForm((f) => ({ ...f, flip }))}
                />
              </>
            ) : null}

            {form.kind === "on_face" ? (
              <>
                <div className="flex flex-col gap-1">
                  {form.face !== null ? (
                    <PickedFaceChip
                      label="Model face"
                      face={form.face}
                      readoutTestId="datum-on-face"
                      clearTestId="datum-on-face-clear"
                      onClear={() =>
                        setForm((f) =>
                          f.kind === "on_face" ? { ...f, face: null } : f,
                        )
                      }
                    />
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      <span className="font-body text-xs text-gauge">
                        Model face
                      </span>
                      <p
                        data-testid="datum-on-face-empty"
                        className="font-data text-md text-gauge"
                      >
                        {canPickFace
                          ? "No face chosen"
                          : "Add a body to pick a face"}
                      </p>
                    </div>
                  )}
                  {canPickFace ? (
                    <FacePickButton
                      armed={activeFacePickSlot === "on_face"}
                      testId="datum-on-face-pick"
                      label={
                        form.face !== null ? "Pick another face" : "Pick a face"
                      }
                      ariaLabel="Pick a model face for this datum"
                      onClick={() => onToggleFacePick("on_face")}
                    />
                  ) : null}
                </div>
                <NumberField
                  label="Offset"
                  unit={unit}
                  data-testid="datum-offset"
                  value={form.offsetInput}
                  error={offsetError(form.offsetInput, unit)}
                  onChange={(e) =>
                    setForm((f) =>
                      f.kind === "on_face"
                        ? { ...f, offsetInput: e.target.value }
                        : f,
                    )
                  }
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Offset distance along the face normal (signed)"
                />
                <p className="-mt-1 font-body text-xs text-gauge">
                  The plane of the picked face. 0 sits on it; a signed offset
                  slides along the face normal.
                </p>
              </>
            ) : null}

            {facePickError ? (
              <p
                role="alert"
                data-testid="datum-face-pick-error"
                className="-mt-1 font-body text-xs text-flag"
              >
                {facePickError}
              </p>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="datum-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="datum-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="datum-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
