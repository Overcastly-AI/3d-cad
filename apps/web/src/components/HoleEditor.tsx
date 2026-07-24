/**
 * The hole editor — the extrude/datum editor's twin in the same title-block
 * seat top-left of the viewport (you author one feature at a time, so they
 * share the "authoring lives here" anchor and the viewport keeps the pixels).
 * A hole drills a cylinder into the current body at a point on a picked planar
 * face, through-all or blind (design §7.6, the shell/draft sibling). DIAMETER
 * wears brass because it is THE parametric handle of the feature — the hole's
 * defining dimension, matching how the extrude editor accents its distance.
 *
 * The face + the drill point are authored by clicking the highlighted face and
 * then a point ON it in the viewport (the parent renders `FacePickOverlay` +
 * `HolePointOverlay`); the editor arms each pick and folds the delivered value
 * into its form. Picking a face seeds the point to the face centre, so the form
 * is immediately submittable and the point step only REFINES it. Keyboard-first:
 * the diameter field autofocuses, Enter commits, Escape cancels — the sketcher's
 * dimension grammar (Escape disarms an armed pick first, handled by the parent).
 */
import {
  cx,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  type SegmentOption,
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
import type { HoleParams } from "../api/parts";
import {
  applyHoleFace,
  applyHolePosition,
  buildHoleParams,
  canSubmitHole,
  csinkAngleError,
  CSINK_STANDARD_ANGLES,
  depthError,
  diameterError,
  type HoleDepthMode,
  type HoleFacePick,
  type HoleForm,
  holeFaceReadout,
  type HolePickTarget,
  type HolePointPick,
  type HolePreview,
  type HoleTypeKind,
  positionReadout,
  recessDiameterError,
} from "../features/hole";

const DEPTH_OPTIONS: ReadonlyArray<SegmentOption<HoleDepthMode>> = [
  {
    value: "through_all",
    label: "Through all",
    "data-testid": "hole-depth-through",
    "aria-label": "Depth: through all",
  },
  {
    value: "blind",
    label: "Blind",
    "data-testid": "hole-depth-blind",
    "aria-label": "Depth: blind pocket",
  },
];

const TYPE_OPTIONS: ReadonlyArray<SegmentOption<HoleTypeKind>> = [
  {
    value: "simple",
    label: "Simple",
    "data-testid": "hole-type-simple",
    "aria-label": "Type: simple bore",
  },
  {
    value: "counterbore",
    label: "C'bore",
    "data-testid": "hole-type-counterbore",
    "aria-label": "Type: counterbore",
  },
  {
    value: "countersink",
    label: "C'sink",
    "data-testid": "hole-type-countersink",
    "aria-label": "Type: countersink",
  },
];

export interface HoleEditorProps {
  mode: "create" | "edit";
  /** The seed form (new-hole defaults, or an existing hole's params). */
  initial: HoleForm;
  /** Commit the built params (documents/geometry handle the rest). */
  onSubmit: (params: HoleParams) => void;
  onCancel: () => void;
  /** True while the create/update round-trip is in flight. */
  saving: boolean;
  /** Server-side failure envelope message, or null. */
  error: string | null;
  /** A body with pickable planar faces exists — gates the pick affordances. */
  canPickFace: boolean;
  /** The pick currently armed (the parent highlights faces / points), or null. */
  activePick: HolePickTarget | null;
  /** Arm/disarm a pick (the parent renders the overlay). */
  onTogglePick: (target: HolePickTarget) => void;
  /** The latest picked face, delivered once per pick (nonce-guarded). */
  facePick: HoleFacePick | null;
  /** The latest picked point, delivered once per pick (nonce-guarded). */
  pointPick: HolePointPick | null;
  /** Why a pick can't happen right now (no body / no anchor), or null. */
  pickError: string | null;
  /** Mirror the live face + position up so the parent can draw the point overlay. */
  onPreviewChange: (preview: HolePreview | null) => void;
}

/** A quiet, brass-when-armed toggle to arm a viewport pick (face / point). */
function PickButton({
  armed,
  onClick,
  testId,
  label,
  armedLabel,
  ariaLabel,
  disabled = false,
}: {
  armed: boolean;
  onClick: () => void;
  testId: string;
  label: string;
  armedLabel: string;
  ariaLabel: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={armed}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "self-start rounded-sm border px-2 py-1 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass",
        disabled
          ? "cursor-not-allowed border-etch text-gauge opacity-40"
          : armed
            ? "border-brass text-brass"
            : "border-etch text-gauge hover:border-gauge hover:text-mist",
      )}
    >
      {armed ? armedLabel : label}
    </button>
  );
}

/**
 * A quiet fastener-standard preset chip (82° / 90°) that fills the countersink
 * angle. Brass when it matches the current value — the standard you're on reads
 * back, so the field and the chips stay in sync.
 */
function AnglePreset({
  angle,
  active,
  onClick,
}: {
  angle: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={`hole-csink-angle-${angle}`}
      aria-pressed={active}
      aria-label={`Set countersink angle to ${angle} degrees`}
      onClick={onClick}
      className={cx(
        "rounded-sm border px-2 py-1 font-data text-xs tabular-nums transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass",
        active
          ? "border-brass text-brass"
          : "border-etch text-gauge hover:border-gauge hover:text-mist",
      )}
    >
      {angle}°
    </button>
  );
}

/** A labelled picked-value readout chip (the datum editor's picked-face chip). */
function PickedChip({
  label,
  value,
  readoutTestId,
}: {
  label: string;
  value: string;
  readoutTestId: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-body text-xs text-gauge">{label}</span>
      <div className="flex items-center justify-between gap-2 rounded-sm border border-brass/60 bg-carbide px-2 py-1">
        <span
          data-testid={readoutTestId}
          className="min-w-0 truncate font-data text-md text-mist"
        >
          {value}
        </span>
      </div>
    </div>
  );
}

export function HoleEditor({
  mode,
  initial,
  onSubmit,
  onCancel,
  saving,
  error,
  canPickFace,
  activePick,
  onTogglePick,
  facePick,
  pointPick,
  pickError,
  onPreviewChange,
}: HoleEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<HoleForm>(initial);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => setForm(initial), [initial]);

  // Fold each delivered viewport pick into the form exactly once — the nonce
  // guards against a re-render re-applying the same pick.
  const lastFaceNonce = useRef(0);
  useEffect(() => {
    if (facePick === null || facePick.nonce === lastFaceNonce.current) return;
    lastFaceNonce.current = facePick.nonce;
    setForm((f) => applyHoleFace(f, facePick.face));
  }, [facePick]);

  const lastPointNonce = useRef(0);
  useEffect(() => {
    if (pointPick === null || pointPick.nonce === lastPointNonce.current)
      return;
    lastPointNonce.current = pointPick.nonce;
    setForm((f) => applyHolePosition(f, pointPick.position));
  }, [pointPick]);

  // Mirror the live face + position up for the parent's point-pick overlay, and
  // clear it on unmount so a closed editor leaves no stray overlay.
  useEffect(() => {
    onPreviewChange({
      signature: form.face?.signature ?? null,
      position: form.position,
    });
  }, [form.face, form.position, onPreviewChange]);
  useEffect(() => () => onPreviewChange(null), [onPreviewChange]);

  const submit = useCallback(() => {
    const params = buildHoleParams(form, unit);
    if (params === null) return;
    onSubmit(params);
  }, [form, onSubmit, unit]);

  // Enter commits — except when a button (footer / segment) has focus (Enter
  // must fire that control). Escape (cancel) is owned by the parent's window
  // handler, the one cancel path for every editor (FINDINGS #11); while a pick
  // is armed the parent's pick handler takes Escape first to disarm it.
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

  const canSubmit = canSubmitHole(form, unit) && !saving;
  useCommandBridge(submit, canSubmit);

  const hasFace = form.face !== null;
  const diameterMsg = diameterError(form.diameterInput, unit);
  const depthMsg =
    form.depthMode === "blind" ? depthError(form.depthInput, unit) : null;
  const cboreDiameterMsg =
    form.typeKind === "counterbore"
      ? recessDiameterError(form.cboreDiameterInput, form.diameterInput, unit)
      : null;
  const cboreDepthMsg =
    form.typeKind === "counterbore"
      ? depthError(form.cboreDepthInput, unit)
      : null;
  const csinkDiameterMsg =
    form.typeKind === "countersink"
      ? recessDiameterError(form.csinkDiameterInput, form.diameterInput, unit)
      : null;
  const csinkAngleMsg =
    form.typeKind === "countersink"
      ? csinkAngleError(form.csinkAngleInput)
      : null;

  return (
    <div
      className="absolute left-editor top-3 w-editor max-w-full"
      onKeyDown={onKeyDown}
    >
      <Panel aria-label="Hole" data-testid="hole-editor">
        <div className="border-b border-hairline">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New hole" : "Edit hole"}
          </h2>
          <div className="flex flex-col gap-2 px-3 pb-3 pt-1">
            {/* Placement face — the picked planar face (a stage-1 SubshapeRef). */}
            <div className="flex flex-col gap-1">
              {hasFace && form.face !== null ? (
                <PickedChip
                  label="Placement face"
                  value={holeFaceReadout(form.face)}
                  readoutTestId="hole-face"
                />
              ) : (
                <div className="flex flex-col gap-0.5">
                  <span className="font-body text-xs text-gauge">
                    Placement face
                  </span>
                  <p
                    data-testid="hole-face-empty"
                    className="font-data text-md text-gauge"
                  >
                    {canPickFace
                      ? "No face chosen"
                      : "Add a body to pick a face"}
                  </p>
                </div>
              )}
              {canPickFace ? (
                <PickButton
                  armed={activePick === "face"}
                  testId="hole-face-pick"
                  label={hasFace ? "Pick another face" : "Pick a face"}
                  armedLabel="Picking… (click a face)"
                  ariaLabel="Pick the planar face to drill into"
                  onClick={() => onTogglePick("face")}
                />
              ) : null}
            </div>

            {/* Drill point — a point ON the resolved face (world coords). */}
            <div className="flex flex-col gap-1">
              <PickedChip
                label="Position"
                value={positionReadout(form)}
                readoutTestId="hole-position"
              />
              {canPickFace ? (
                <PickButton
                  armed={activePick === "point"}
                  testId="hole-point-pick"
                  label="Pick a point"
                  armedLabel="Picking… (click a point)"
                  ariaLabel="Pick the drill point on the face"
                  disabled={!hasFace}
                  onClick={() => onTogglePick("point")}
                />
              ) : null}
              {hasFace ? (
                <p className="-mt-0.5 font-body text-xs text-gauge">
                  A point on the face; it's projected onto the face plane to fix
                  the drill axis.
                </p>
              ) : null}
            </div>

            {/* Diameter — THE parametric handle (brass focus). */}
            <NumberField
              label="Diameter"
              unit={unit}
              data-testid="hole-diameter"
              autoFocus
              value={form.diameterInput}
              error={diameterMsg}
              onChange={(e) =>
                setForm((f) => ({ ...f, diameterInput: e.target.value }))
              }
              onFocus={(e) => e.currentTarget.select()}
            />

            {/* Depth — through-all, or a blind pocket. */}
            <SegmentedControl
              label="Depth"
              value={form.depthMode}
              options={DEPTH_OPTIONS}
              onChange={(depthMode) => setForm((f) => ({ ...f, depthMode }))}
            />
            {form.depthMode === "blind" ? (
              <NumberField
                label="Blind depth"
                unit={unit}
                data-testid="hole-blind-depth"
                value={form.depthInput}
                error={depthMsg}
                onChange={(e) =>
                  setForm((f) => ({ ...f, depthInput: e.target.value }))
                }
                onFocus={(e) => e.currentTarget.select()}
              />
            ) : null}

            {/* Type — a plain bore, or a coaxial recess at the face (a
                counterbore cylinder for a cap screw, a countersink cone for a
                flat head). Simple is the default; the recess fields reveal. */}
            <SegmentedControl
              label="Type"
              value={form.typeKind}
              options={TYPE_OPTIONS}
              onChange={(typeKind) => setForm((f) => ({ ...f, typeKind }))}
            />
            {form.typeKind === "counterbore" ? (
              <div className="flex gap-2">
                <NumberField
                  className="flex-1"
                  label="C'bore Ø"
                  unit={unit}
                  data-testid="hole-cbore-diameter"
                  value={form.cboreDiameterInput}
                  error={cboreDiameterMsg}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      cboreDiameterInput: e.target.value,
                    }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
                <NumberField
                  className="flex-1"
                  label="C'bore depth"
                  unit={unit}
                  data-testid="hole-cbore-depth"
                  value={form.cboreDepthInput}
                  error={cboreDepthMsg}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, cboreDepthInput: e.target.value }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
              </div>
            ) : null}
            {form.typeKind === "countersink" ? (
              <div className="flex flex-col gap-2">
                <NumberField
                  label="C'sink Ø"
                  unit={unit}
                  data-testid="hole-csink-diameter"
                  value={form.csinkDiameterInput}
                  error={csinkDiameterMsg}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      csinkDiameterInput: e.target.value,
                    }))
                  }
                  onFocus={(e) => e.currentTarget.select()}
                />
                <div className="flex items-end gap-2">
                  <NumberField
                    className="flex-1"
                    label="C'sink angle"
                    unit="°"
                    data-testid="hole-csink-angle"
                    aria-label="Countersink included angle (degrees)"
                    value={form.csinkAngleInput}
                    error={csinkAngleMsg}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        csinkAngleInput: e.target.value,
                      }))
                    }
                    onFocus={(e) => e.currentTarget.select()}
                  />
                  <div
                    role="group"
                    aria-label="Standard countersink angles"
                    className="flex shrink-0 items-center gap-1 pb-1"
                  >
                    {CSINK_STANDARD_ANGLES.map((angle) => (
                      <AnglePreset
                        key={angle}
                        angle={angle}
                        active={Number(form.csinkAngleInput) === angle}
                        onClick={() =>
                          setForm((f) => ({
                            ...f,
                            csinkAngleInput: String(angle),
                          }))
                        }
                      />
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {pickError ? (
              <p
                role="alert"
                data-testid="hole-pick-error"
                className="-mt-1 font-body text-xs text-flag"
              >
                {pickError}
              </p>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x divide-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="hole-cancel"
            disabled={saving}
            onClick={onCancel}
          />
          <PanelActionCell
            label={saving ? "Saving…" : mode === "create" ? "Create" : "Save"}
            caption="Enter"
            data-testid="hole-submit"
            aria-busy={saving}
            disabled={!canSubmit}
            onClick={submit}
          />
        </div>
      </Panel>

      {error ? (
        <p
          role="alert"
          data-testid="hole-error"
          className="mt-2 max-w-full border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
