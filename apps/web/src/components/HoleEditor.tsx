/**
 * The hole editor — references pinned, parameters scrolling (UI-W4), docked to
 * the right rail so the viewport keeps the middle (design mandate 3).
 *
 * A hole drills a cylinder into the current body at a point on a picked planar
 * face, through-all or blind (design §7.6, the shell/draft sibling).
 *
 * The structural truth this card is built on: a feature has REFERENCES (what it
 * is attached to) and PARAMETERS (numbers), and those deserve different
 * treatment. Losing sight of a reference was the actual reported defect — this
 * was 12 stacked rows in a scrolling body, so "C'sink angle" could be on screen
 * while the placement face had scrolled off the top. Now:
 *
 *   FACE / POINT   → a pinned anchor block that never scrolls (EditorCard
 *                    `header`), scribed in brass: the references this feature
 *                    hangs off, always in sight.
 *   Ø              → THE parametric handle, `NumberField emphasis="primary"`
 *                    (the hole's defining dimension, at DRO scale in brass).
 *   Depth / Type   → secondary parameters, in the scrolling body.
 *   Thread         → progressively disclosed; it was ~5 of the 12 rows and the
 *                    everyday hole is not tapped.
 *
 * And the behavioural half (UI-W3): the anchor block opens ALREADY FILLED from
 * whatever the cursor had selected (`features/preselect`), and when it is
 * empty the parent arms the face pick on open — so clicking a face just takes
 * it. Arming a pick is the way to CHANGE a reference, not the only way to set
 * one. Keyboard-first throughout: the diameter field autofocuses, Enter
 * commits, Escape cancels (the parent's window handler; while a pick is armed
 * Escape disarms it first).
 */
import {
  Checkbox,
  cx,
  Disclosure,
  formatLength,
  NumberField,
  Panel,
  PanelActionCell,
  SegmentedControl,
  SelectField,
  type SegmentOption,
  type SelectFieldOption,
} from "@loft/design";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useCommandBridge } from "../features/commandActions";
import { EditorCard } from "./EditorCard";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { HoleParams } from "../api/parts";
import type { OverlayEdge } from "../api/measure";
import {
  checkPlacement,
  describeDirection,
  facePlacement,
  type PlacementCheck,
} from "../features/facePlacement";
import { parseSignedLengthMm } from "../units/length";
import {
  applyHoleCoordinate,
  applyHoleFace,
  applyHolePosition,
  applyTapDrill,
  applyTapped,
  applyThreadNominal,
  applyThreadPitch,
  boreIsTapDrill,
  buildHoleParams,
  canSubmitHole,
  coordinateError,
  coordinatesComplete,
  csinkAngleError,
  CSINK_STANDARD_ANGLES,
  depthError,
  diameterError,
  type HoleDepthMode,
  type HoleFacePick,
  type HoleForm,
  holeFaceReadout,
  holeFaceFrame,
  type HolePickTarget,
  type HolePointPick,
  type HolePreview,
  type HoleTypeKind,
  positionReadout,
  recessDiameterError,
  threadBoreError,
  threadDesignation,
  threadPitchError,
  threadSizeError,
  threadTapDrillMm,
} from "../features/hole";
import {
  formatThreadNumber,
  pitchesFor,
  THREAD_NOMINALS,
} from "../features/thread";

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
  /** The seed form (new-hole defaults — possibly pre-filled from the cursor
   *  selection — or an existing hole's params). */
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
  /**
   * The picked face's own body is switched OFF, so the viewport is withholding
   * the whole placement overlay (SEL-7 — `viewport/HolePointOverlay`).
   *
   * The editor's job here is to say WHY. Emptying the viewport mid-command
   * without a word is the "ambiguous exit" the design mandate treats as a defect
   * in its own right — and it is a VIEW state, not an error, so it reads in the
   * position row and a quiet note rather than in the `role="alert"` pick-error
   * slot. The pick stays armed and Create stays reachable: a hole is legitimate
   * geometry whose visibility is a view decision, and disarming would cost the
   * user a click they never asked for when they show the body again.
   */
  placementHidden: boolean;
  /**
   * The evaluated body's B-rep edges (from the overlay), or null before it
   * arrives. The ones lying in the picked face's plane are its outline and the
   * mouths of everything bored through it — which is what makes the live
   * material check and the concentric snaps possible (`../features/facePlacement`).
   */
  edges: readonly OverlayEdge[] | null;
  /** Mirror the live face + position up so the parent can draw the point overlay. */
  onPreviewChange: (preview: HolePreview | null) => void;
}

/**
 * One reference of the pinned anchor block: what it is, what it currently
 * points at, and the control that re-points it.
 *
 * The re-pick control is `aria-disabled` and stays hoverable, focusable and
 * self-explaining — never a disabled trap (the treatment `ToolButton` and
 * `PanelActionCell` carry): "Pick a point" is gated until a face exists, and
 * that is exactly when the user most needs to be told why.
 */
function AnchorRow({
  label,
  value,
  valueTestId,
  filled,
  armed,
  hint,
  hintTestId,
  pickTestId,
  pickAriaLabel,
  onPick,
  showPick,
  disabled = false,
  disabledReason,
}: {
  label: string;
  value: string;
  valueTestId: string;
  /** The reference is set — the row reads as confirmation, not a to-do. */
  filled: boolean;
  armed: boolean;
  /** A quiet line under the row (what a click will do now), or null. */
  hint: string | null;
  /** Test id of the hint line; defaults to `${pickTestId}-hint`. */
  hintTestId?: string;
  pickTestId: string;
  pickAriaLabel: string;
  onPick: () => void;
  showPick: boolean;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const hasReason = disabled && disabledReason !== undefined;
  const note = hint ?? (hasReason ? disabledReason : null);
  return (
    <div className="flex flex-col">
      <div className="flex min-h-target-dense items-center gap-2">
        <span className="w-10 shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-gauge">
          {label}
        </span>
        <span
          data-testid={valueTestId}
          className={cx(
            "min-w-0 grow truncate font-data text-sm",
            filled ? "text-mist" : armed ? "text-brass" : "text-gauge",
          )}
        >
          {value}
        </span>
        {showPick ? (
          <button
            type="button"
            data-testid={pickTestId}
            aria-pressed={armed}
            aria-disabled={disabled || undefined}
            aria-label={
              hasReason ? `${pickAriaLabel} — ${disabledReason}` : pickAriaLabel
            }
            onClick={() => {
              if (disabled) return;
              onPick();
            }}
            className={cx(
              "min-h-target-dense shrink-0 rounded-sm border px-2 font-display text-2xs uppercase tracking-[0.14em] transition-colors duration-fast",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass",
              disabled
                ? "cursor-not-allowed border-etch text-gauge opacity-40"
                : armed
                  ? "border-brass text-brass"
                  : "border-etch text-gauge hover:border-gauge hover:text-mist",
            )}
          >
            {armed ? "Picking" : filled ? "Change" : "Pick"}
          </button>
        ) : null}
      </div>
      {note !== null ? (
        <p
          data-testid={
            hint !== null
              ? (hintTestId ?? `${pickTestId}-hint`)
              : `${pickTestId}-reason`
          }
          className="pl-12 font-body text-xs text-gauge"
        >
          {note}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A quiet SHOP-STANDARD preset chip that fills a field with a published value —
 * the countersink's 82°/90° fastener angles, and the tap drill of the chosen
 * thread. Brass when the field already carries that value, so the standard
 * you're on reads back and the chip doubles as "restore the derived value".
 */
function PresetChip({
  label,
  active,
  onClick,
  testId,
  ariaLabel,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  testId: string;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={active}
      aria-label={ariaLabel}
      onClick={onClick}
      className={cx(
        "min-h-target-dense rounded-sm border px-2 font-data text-xs tabular-nums transition-colors duration-fast",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass",
        active
          ? "border-brass text-brass"
          : "border-etch text-gauge hover:border-gauge hover:text-mist",
      )}
    >
      {label}
    </button>
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
  placementHidden,
  edges,
  onPreviewChange,
}: HoleEditorProps) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<HoleForm>(initial);
  // The thread block is disclosed, not deleted: an already-tapped hole opens
  // with it showing (its content is load-bearing there), a fresh hole does not.
  const [threadOpen, setThreadOpen] = useState(initial.tapped);
  // Re-seed when the editor is retargeted at a different feature.
  useEffect(() => {
    setForm(initial);
    setThreadOpen(initial.tapped);
  }, [initial]);

  // Fold each delivered viewport pick into the form exactly once — the nonce
  // guards against a re-render re-applying the same pick.
  const lastFaceNonce = useRef(0);
  useEffect(() => {
    if (facePick === null || facePick.nonce === lastFaceNonce.current) return;
    lastFaceNonce.current = facePick.nonce;
    setForm((f) => applyHoleFace(f, facePick.face, unit));
  }, [facePick, unit]);

  const lastPointNonce = useRef(0);
  useEffect(() => {
    if (pointPick === null || pointPick.nonce === lastPointNonce.current)
      return;
    lastPointNonce.current = pointPick.nonce;
    setForm((f) => applyHolePosition(f, pointPick.position, unit));
  }, [pointPick, unit]);

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
  /**
   * What each reference row SAYS. An empty required reference under an armed
   * pick is not "empty" — it is an instruction, so it reads as one and takes
   * the brass of a live control. (The old copy, "No face chosen", described the
   * form's state and left the user to work out that a viewport click was what
   * it wanted.)
   */
  const faceValue =
    form.face !== null
      ? holeFaceReadout(form.face)
      : !canPickFace
        ? "Add a body to pick a face"
        : activePick === "face"
          ? // Short enough to fit the value column beside the armed button — a
            // truncated instruction ("Click a face in the …") is not one. The
            // gated Create cell carries the full sentence.
            "Click a face"
          : "No face chosen";
  // …and when the face's body is switched off there is nothing on screen to
  // click, so the row names the view state instead of an instruction it cannot
  // honour. TWO WORDS, for the same reason `faceValue` above is short: the
  // value column shares its line with the pick button and truncates, and a
  // truncated explanation ("Body hidden — show i…") explains nothing. The row
  // says WHAT, the note under it says what to do about it.
  const pointValue = placementHidden
    ? "Body hidden"
    : form.position === null && activePick === "point"
      ? "Click a point"
      : positionReadout(form);
  /**
   * WHY the footer action is gated, said in the footer itself. The gate is
   * `buildHoleParams(...) !== null`, i.e. "a face and every field valid", and
   * until 2026-07-30 the greyed cell could not even be hovered, so a user had to
   * hunt for the missing piece (UI-REVIEW 2026-07-30 P2). Cheapest honest
   * version: name the ONE thing that is missing, face first because it is the
   * only one the fields cannot show inline.
   */
  const submitReason = !canSubmit
    ? saving
      ? undefined
      : !hasFace
        ? "Click a face in the viewport to place the hole."
        : !coordinatesComplete(form, unit)
          ? "Finish the X and Y position."
          : "Check the highlighted fields."
    : undefined;
  // --- Placement: the frame, the cells, and the live material check --------
  // QA3-1: the point used to be a read-only readout offering the face centroid
  // and its corners, which on a vendor plate whose centre IS the shaft bore
  // means the hole cannot be placed at all. Coordinates fix that, and the frame
  // row is what keeps them honest — an X/Y entry that does not say where its
  // zero is, is how QA3-2's 0.065 mm eccentric ring happened.
  const frame = holeFaceFrame(form);
  const placement = useMemo(
    () =>
      form.face === null ? null : facePlacement(form.face.signature, edges),
    [form.face, edges],
  );
  const xMsg = coordinateError(form.xInput, unit, "X");
  const yMsg = coordinateError(form.yInput, unit, "Y");
  const typedX = parseSignedLengthMm(form.xInput, unit);
  const typedY = parseSignedLengthMm(form.yInput, unit);
  const check: PlacementCheck | null =
    placement === null || typedX === null || typedY === null
      ? null
      : checkPlacement(placement, { x: typedX, y: typedY });
  const round = (n: number) => (Object.is(n, -0) ? 0 : Math.round(n * 10) / 10);
  const frameValue =
    frame === null
      ? ""
      : `${round(frame.origin.x)}, ${round(frame.origin.y)}, ${round(frame.origin.z)} mm · X→${describeDirection(frame.u)} · Y→${describeDirection(frame.v)}`;
  const frameTitle =
    frame === null
      ? ""
      : `X and Y are measured on this face from the part origin projected onto it, at ${round(frame.origin.x)}, ${round(frame.origin.y)}, ${round(frame.origin.z)} millimetres. X runs along world ${describeDirection(frame.u)}; Y runs along world ${describeDirection(frame.v)}.`;
  // The check WARNS; it never blocks the write. The kernel's typed
  // `hole_off_body` is the authority (and the control that stops a bad hole
  // shipping silently) — this only gets there first, off an approximation the
  // overlay can support. See `../features/facePlacement`.
  const checkMessage =
    check === null || check.verdict === "unknown"
      ? null
      : check.verdict === "material"
        ? "On solid material."
        : check.verdict === "opening" && check.circle !== null
          ? `Inside the Ø${formatLength(check.circle.radiusMm * 2, unit)} opening — move it onto material.`
          : check.verdict === "opening"
            ? "Inside an opening in the face — move it onto material."
            : "Off the face outline — move it onto the face.";
  const checkOk = check?.verdict === "material";

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

  // --- Thread (tapped hole) -------------------------------------------------
  // Threading is ORTHOGONAL to the recess, so this is a toggle inside its own
  // disclosed block, never a fourth segment inside Type (the wire says the same:
  // `thread` is a sibling of `type`). The bore is DERIVED from the designation
  // but stays editable — a shop's rounded stock drill is a legitimate tap drill.
  const designation = threadDesignation(form);
  const threadSizeMsg = threadSizeError(form);
  const threadPitchMsg = threadPitchError(form);
  const threadBoreMsg = threadBoreError(form, unit);
  // A section may hide controls; it may not hide an ERROR. A thread the client
  // cannot cut reports on the disclosure's own summary line, so a collapsed
  // block still says what is wrong (and the block opens by itself whenever the
  // hole arrives tapped, which is every edit of one).
  const threadFault = threadSizeMsg ?? threadPitchMsg;
  // A stored designation the client's ISO table doesn't list (authored through
  // the API, or an older client) is SHOWN as a non-choosable option rather than
  // silently rewritten — the user sees what the feature actually says and can
  // pick a listed one. This is the `hole_thread_unsupported` repair path.
  const sizeOptions = useMemo<SelectFieldOption[]>(() => {
    const listed = THREAD_NOMINALS.map((nominal) => ({
      value: String(nominal),
      label: `M${formatThreadNumber(nominal)}`,
    }));
    return pitchesFor(form.threadNominalMm).length > 0
      ? listed
      : [
          {
            value: String(form.threadNominalMm),
            label: `M${formatThreadNumber(form.threadNominalMm)}`,
            disabled: true,
          },
          ...listed,
        ];
  }, [form.threadNominalMm]);
  const pitchOptions = useMemo<SelectFieldOption[]>(() => {
    const pitches = pitchesFor(form.threadNominalMm);
    // Coarse first, and said so: it is the pitch a shop taps by default.
    const listed = pitches.map((pitch, index) => ({
      value: String(pitch),
      label:
        index === 0
          ? `${formatThreadNumber(pitch)} (coarse)`
          : formatThreadNumber(pitch),
    }));
    return pitches.some((pitch) => Math.abs(pitch - form.threadPitchMm) <= 1e-9)
      ? listed
      : [
          {
            value: String(form.threadPitchMm),
            label: formatThreadNumber(form.threadPitchMm),
            disabled: true,
          },
          ...listed,
        ];
  }, [form.threadNominalMm, form.threadPitchMm]);

  const picking = activePick !== null;
  return (
    <EditorCard
      data-testid="hole-editor-shell"
      data-picking={picking ? "true" : "false"}
      // The right rail, always. The card used to sit mid-frame at the left
      // editor inset and hop to the right edge whenever a pick was armed (so it
      // stopped covering its own pick target) — two seats, a jump between them,
      // and the model shoved out of the middle in one of them. One seat on the
      // rail with the inspector keeps the viewport's centre for the viewport.
      seat="right"
      onKeyDown={onKeyDown}
      // The references, pinned. Nothing here scrolls: this block is the answer
      // to "what is this hole attached to", and the card must never be able to
      // hide it (UI-W4).
      header={
        <div className="border border-hairline bg-anvil">
          <h2 className="px-3 pb-1 pt-3 font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            {mode === "create" ? "New hole" : "Edit hole"}
          </h2>
          {/* The brass scribe rule marks the reference block — a drafting
              leader down the two things this feature hangs off. The card's one
              loud element; everything below it stays quiet. */}
          <div
            role="group"
            aria-label="Hole placement"
            data-testid="hole-anchor"
            className="mx-3 mb-2 border-l-2 border-brass pl-2"
          >
            <AnchorRow
              label="Face"
              value={faceValue}
              valueTestId={hasFace ? "hole-face" : "hole-face-empty"}
              filled={hasFace}
              armed={activePick === "face"}
              hint={
                activePick === "face" && hasFace
                  ? "Click a face to replace it."
                  : null
              }
              pickTestId="hole-face-pick"
              pickAriaLabel="Pick the planar face to drill into"
              showPick={canPickFace}
              onPick={() => onTogglePick("face")}
            />
            <AnchorRow
              label="Point"
              value={pointValue}
              valueTestId="hole-position"
              filled={form.position !== null && !placementHidden}
              armed={activePick === "point"}
              hint={
                placementHidden
                  ? "This face is on a body you have hidden. Show that body in the Bodies panel — the point you already set is kept."
                  : activePick === "point" && form.position !== null
                    ? "Click a corner, a bore centre, or the face centre."
                    : null
              }
              hintTestId={
                placementHidden ? "hole-placement-hidden-note" : undefined
              }
              pickTestId="hole-point-pick"
              pickAriaLabel="Pick the drill point on the face"
              showPick={canPickFace}
              disabled={!hasFace}
              disabledReason="Pick a face first — the point is placed on it."
              onPick={() => onTogglePick("point")}
            />
            {/* The DRO pair. A hole is dialled in, the way it is at a jig
                borer: two coordinates in the face's own frame, re-checked on
                every keystroke against the face's outline and its openings.
                Held in the PINNED block because the position IS a reference —
                it may not scroll out from under the numbers being typed. */}
            {hasFace ? (
              <div
                className="flex flex-col gap-1 pb-1 pt-1"
                data-testid="hole-placement"
              >
                <div className="flex gap-2">
                  <NumberField
                    className="flex-1"
                    label="X"
                    unit={unit}
                    data-testid="hole-position-x"
                    aria-label={`Drill X on the face, ${unit}`}
                    value={form.xInput}
                    error={xMsg}
                    onChange={(e) =>
                      setForm((f) =>
                        applyHoleCoordinate(f, "x", e.target.value, unit),
                      )
                    }
                    onFocus={(e) => e.currentTarget.select()}
                  />
                  <NumberField
                    className="flex-1"
                    label="Y"
                    unit={unit}
                    data-testid="hole-position-y"
                    aria-label={`Drill Y on the face, ${unit}`}
                    value={form.yInput}
                    error={yMsg}
                    onChange={(e) =>
                      setForm((f) =>
                        applyHoleCoordinate(f, "y", e.target.value, unit),
                      )
                    }
                    onFocus={(e) => e.currentTarget.select()}
                  />
                </div>
                {/* WHERE zero is, and which way the axes run — the one thing
                    an X/Y entry must never leave the user to guess. The
                    viewport draws the same frame on the face itself. */}
                <div className="flex items-baseline gap-2">
                  <span className="w-10 shrink-0 font-display text-2xs uppercase tracking-[0.14em] text-gauge">
                    Frame
                  </span>
                  <span
                    data-testid="hole-frame"
                    // The compact readout is the precision instrument; the
                    // sentence is what a screen reader (and a hover) gets.
                    // `role="note"` because a bare span takes no accessible
                    // name from `aria-label` in several engines.
                    role="note"
                    title={frameTitle}
                    aria-label={frameTitle}
                    className="min-w-0 grow font-data text-2xs leading-relaxed text-gauge"
                  >
                    {frameValue}
                  </span>
                </div>
                {checkMessage !== null ? (
                  <p
                    data-testid="hole-position-check"
                    data-verdict={check?.verdict}
                    role="status"
                    aria-live="polite"
                    className={cx(
                      "flex items-baseline gap-2 pl-12 font-body text-xs",
                      checkOk ? "text-gauge" : "text-flag",
                    )}
                  >
                    <span
                      aria-hidden
                      className={cx(
                        "mt-1 h-1 w-1 shrink-0 rounded-full",
                        checkOk ? "bg-brass" : "bg-flag",
                      )}
                    />
                    {checkMessage}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
          {pickError ? (
            <p
              role="alert"
              data-testid="hole-pick-error"
              className="px-3 pb-2 font-body text-xs text-flag"
            >
              {pickError}
            </p>
          ) : null}
        </div>
      }
      // The tallest form in the app (C'sink + Tapped + Blind reached 858px), so
      // it is the editor that proves the clamp: the action row is pinned in the
      // footer while the fields scroll, and the derived tap-drill chip stays
      // reachable at 1366x768 (UI-REVIEW 2026-07-30 P1).
      footer={
        <>
          {error ? (
            <p
              role="alert"
              data-testid="hole-error"
              className="border border-b-0 border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 divide-x divide-hairline border border-t-0 border-hairline bg-anvil">
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
              disabledReason={submitReason}
              onClick={submit}
            />
          </div>
        </>
      }
    >
      <Panel aria-label="Hole" data-testid="hole-editor" className="border-t-0">
        <div className="flex flex-col gap-2 px-3 pb-3 pt-2">
          {/* Diameter — THE parametric handle. When the hole is tapped this IS
              the tap drill, so an untappable bore reports here, on the field
              that has to change. */}
          <NumberField
            label="Diameter"
            emphasis="primary"
            unit={unit}
            data-testid="hole-diameter"
            autoFocus
            value={form.diameterInput}
            error={diameterMsg ?? threadBoreMsg}
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
                    <PresetChip
                      key={angle}
                      testId={`hole-csink-angle-${angle}`}
                      label={`${angle}°`}
                      ariaLabel={`Set countersink angle to ${angle} degrees`}
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

          {/* Thread — disclosed, because the everyday hole is a clearance hole
              and this block was ~5 of the card's 12 rows. The summary reports
              the callout, so a tapped hole never hides behind a shut door.

              The thread adds no geometry: the kernel cuts the tap drill and
              records the designation on the feature. The description says
              EXACTLY that and no more — it used to promise "carries the callout
              to drawings", and no drawing note, BOM column, PDF/DXF or STEP path
              reads the thread field at all (UI-REVIEW 2026-07-30 P1). */}
          <Disclosure
            label="Thread"
            data-testid="hole-thread-toggle"
            summary={
              threadFault !== null
                ? `Can't cut ${designation}`
                : form.tapped
                  ? designation
                  : "None"
            }
            summaryTone={threadFault !== null ? "flag" : "quiet"}
            open={threadOpen}
            onOpenChange={setThreadOpen}
          >
            <div className="flex flex-col gap-2 pt-1">
              <Checkbox
                label="Tapped"
                data-testid="hole-tapped"
                description="Drills the tap drill and records the designation on the feature — the tree shows it. No helix is modelled, and the drawing note is not built yet."
                checked={form.tapped}
                onChange={(tapped) =>
                  setForm((f) => applyTapped(f, tapped, unit))
                }
              />
              {form.tapped ? (
                <>
                  {/* THE callout — a drafting thread note, stamped: a leader
                      tick into the designation, then the note rule running out.
                      The only place a tapped hole is visible at all (its solid
                      is byte-identical to a plain bore). */}
                  <div className="flex flex-col gap-0.5">
                    <span className="font-body text-xs text-gauge">
                      Thread callout
                    </span>
                    <div className="flex items-center gap-2">
                      <span
                        aria-hidden
                        data-testid="hole-thread-tick"
                        className="h-px w-3 shrink-0 bg-brass"
                      />
                      <span
                        data-testid="hole-thread-designation"
                        className="shrink-0 font-display text-lg leading-none tracking-[0.06em] text-brass"
                      >
                        {designation}
                      </span>
                      <span
                        aria-hidden
                        className="h-px grow bg-brass/40"
                        data-testid="hole-thread-rule"
                      />
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <SelectField
                      className="flex-1"
                      label="Size"
                      data-testid="hole-thread-size"
                      aria-label="Nominal thread size"
                      value={String(form.threadNominalMm)}
                      options={sizeOptions}
                      error={threadSizeMsg}
                      onChange={(e) =>
                        setForm((f) =>
                          applyThreadNominal(f, Number(e.target.value), unit),
                        )
                      }
                    />
                    <SelectField
                      className="flex-1"
                      label="Pitch"
                      data-testid="hole-thread-pitch"
                      aria-label="Thread pitch (millimetres)"
                      value={String(form.threadPitchMm)}
                      options={pitchOptions}
                      error={threadPitchMsg}
                      onChange={(e) =>
                        setForm((f) =>
                          applyThreadPitch(f, Number(e.target.value), unit),
                        )
                      }
                    />
                  </div>

                  {/* The derived bore, one click away. Brass when the Diameter
                      above already IS the tap drill, so an override reads back —
                      and the chip restores it. */}
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-body text-xs text-gauge">
                      Tap drill
                    </span>
                    <PresetChip
                      testId="hole-thread-tap-drill"
                      label={`Ø${formatLength(threadTapDrillMm(form), unit)}`}
                      ariaLabel={`Set the diameter to the ${designation} tap drill`}
                      active={boreIsTapDrill(form, unit)}
                      onClick={() => setForm((f) => applyTapDrill(f, unit))}
                    />
                  </div>
                </>
              ) : null}
            </div>
          </Disclosure>
        </div>
      </Panel>
    </EditorCard>
  );
}
