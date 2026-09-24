/**
 * The sketch toolbar — one thin title-block row that fills the LEFT of the
 * full-width top band while sketching, icon-forward. Plane-pick step: the
 * three datum planes (keyboard
 * path, hover-synced with the 3D sheets). Draw step, all on a single ruled
 * row so the viewport keeps the pixels: a flat status cell (plane + live
 * selection), the four sketch tools as scribed icons, the SIXTEEN constraint
 * verbs grouped by kind (Geometric / Dimensional / Relational) behind labeled
 * flyouts, the Construction toggle, then SAVE and EXIT as icon buttons —
 * their counts/reasons engraved in tooltips, never stacked into tall cells.
 *
 * One keyboard, two vocabularies survives untouched: the global key handler
 * still arms tools (L/R/C/A) with nothing selected and fires constraint verbs
 * (H/V/D/R/A/X/C/P/L/I/T/E/S/M/O + N) with a selection.
 *
 * TWO SURFACES, ONE RULE. The status cell's OFFER RAIL proposes the (up to
 * three) verbs the CURRENT selection unlocks, keycap first, each cap
 * clickable — the fast path, at the moment it applies. The flyouts are the
 * CATALOGUE: all sixteen verbs, each saying whether this selection reaches it
 * and, when it does not, the pick shape that would. Both read the same
 * `verbIsAvailable` predicate, so they cannot disagree about a selection.
 *
 * The catalogue is not redundant with the rail, and the reason is structural:
 * an offer can only appear once the selection ALREADY fits, so the rail can
 * propose a verb but can never teach you to reach one. Four verbs shipped
 * authorable-but-uncatalogued after REACH-1 (angle, diameter, collinear,
 * midpoint) and were findable only by pressing a letter nothing named — the
 * catalogue is where "what exists" lives, and it was lying by omission.
 * Quiet chrome; the viewport keeps the pixels.
 */
import {
  AngleIcon,
  ArcIcon,
  ChamferIcon,
  CheckIcon,
  CircleIcon,
  CloseIcon,
  CoincidentIcon,
  CollinearIcon,
  ConcentricIcon,
  ConstructionIcon,
  DatumIcon,
  DiameterIcon,
  DistanceIcon,
  EqualIcon,
  ExtendIcon,
  FilletIcon,
  FixedIcon,
  Flyout,
  type FlyoutItem,
  HorizontalIcon,
  InlineSelect,
  Kbd,
  LineIcon,
  MidpointIcon,
  MirrorIcon,
  NumberField,
  OffsetIcon,
  Panel,
  PanelActionCell,
  ParallelIcon,
  PerpendicularIcon,
  RadiusIcon,
  RectIcon,
  SegmentedControl,
  type SegmentOption,
  SplineIcon,
  SymmetricIcon,
  TangentIcon,
  TrimIcon,
  ToolButton,
  ToolGroup,
  VerticalIcon,
} from "@loft/design";
import { type ReactNode, useEffect, useState } from "react";

import type { DatumOffsetParams } from "../api/parts";
import { HistoryGroup } from "./HistoryGroup";
import { isTypingTarget } from "../lib/isTypingTarget";
import { useGlobalKeys } from "../lib/modalGate";
import { undoRedoStep } from "../lib/undoRedoShortcut";
import {
  authoredConstraintCount,
  deleteSelectedEntities,
  describeSelection,
  selectionAllConstruction,
  selectionVerbHints,
  verbIsAvailable,
  verbSelectionShape,
  type ConstraintAction,
} from "../sketch/constraints";
import { withoutDatums } from "../sketch/datum";
import { describeOpenEnds } from "../sketch/openEnds";
import { gridStepOptions } from "../sketch/pointEntry";
import {
  buildOffsetParams,
  datumSubmitBlocker,
  DATUM_BASES,
  defaultOffsetForm,
  type OffsetForm,
  offsetError,
} from "../features/datum";
import {
  DATUM_PLANES,
  type DatumPlaneName,
  describePlane,
  type SketchPlaneSpec,
} from "../sketch/plane";
import { useSketchStore } from "../sketch/store";
import { useDocumentLengthUnit } from "../units/documentUnit";
import type { SketchTool } from "../sketch/tools";

const TOOLS: ReadonlyArray<{
  tool: SketchTool;
  label: string;
  keyHint: string;
  name: string;
  icon: ReactNode;
}> = [
  {
    tool: "line",
    label: "Line",
    keyHint: "L",
    name: "Line tool (L)",
    icon: <LineIcon />,
  },
  {
    tool: "rect",
    label: "Rect",
    keyHint: "R",
    name: "Rectangle tool (R)",
    icon: <RectIcon />,
  },
  {
    tool: "circle",
    label: "Circle",
    keyHint: "C",
    name: "Circle tool (C)",
    icon: <CircleIcon />,
  },
  {
    tool: "arc",
    label: "Arc",
    keyHint: "A",
    name: "Arc tool (A)",
    icon: <ArcIcon />,
  },
  {
    tool: "spline",
    label: "Spline",
    keyHint: "S",
    name: "Spline tool (S) — click fit points, Enter or double-click to finish; each fit point constrains like any point (coincident / fixed / symmetric)",
    icon: <SplineIcon />,
  },
];

/**
 * The modify (clean-up) tools — the "draw rough, then tidy" set. Trim cuts a
 * curve at its intersections and deletes the picked piece; Extend grows the
 * picked end to the nearest neighbor; Offset adds a parallel copy at a signed
 * distance (the rib/web/wall-profile move); Mirror reflects a selection about a
 * line; Fillet rounds and Chamfer bevels the corner two lines share. All arm
 * like draw tools (empty selection), then the next click(s) on a curve do the
 * edit.
 */
const MODIFY_TOOLS: ReadonlyArray<{
  tool: SketchTool;
  label: string;
  keyHint: string;
  name: string;
  icon: ReactNode;
}> = [
  {
    tool: "trim",
    label: "Trim",
    keyHint: "J",
    name: "Trim tool (J) — click a curve to cut it at its intersections",
    icon: <TrimIcon />,
  },
  {
    tool: "extend",
    label: "Extend",
    keyHint: "K",
    name: "Extend tool (K) — click near a curve's end to grow it to the nearest neighbor",
    icon: <ExtendIcon />,
  },
  {
    tool: "offset",
    label: "Offset",
    keyHint: "F",
    name: "Offset tool (F) — click a curve, then set a signed distance to add a parallel copy",
    icon: <OffsetIcon />,
  },
  {
    tool: "mirror",
    label: "Mirror",
    keyHint: "I",
    name: "Mirror tool (I) — pick entities, then a line, to add their reflected copies",
    icon: <MirrorIcon />,
  },
  {
    tool: "fillet",
    label: "Fillet",
    keyHint: "U",
    name: "Fillet tool (U) — pick two lines, then set a radius to round their corner",
    icon: <FilletIcon />,
  },
  {
    tool: "chamfer",
    label: "Chamfer",
    keyHint: "B",
    name: "Chamfer tool (B) — pick two lines, then set a distance to bevel their corner",
    icon: <ChamferIcon />,
  },
];

interface ConstraintSpec {
  action: ConstraintAction;
  label: string;
  keyHint: string;
  name: string;
  icon: ReactNode;
}

/**
 * The sketch strip's rung of `CommandBand`'s measured label ladder (guarantee
 * #3 — higher keeps its words longer). Two levels, because at the 1280 floor
 * the strip has exactly two spendable sets of words and they are not worth the
 * same per pixel.
 *
 * Measured at 1280x800 BEFORE this ranking existed (QA-R1, reproduced 3/3):
 * idle the strip needs 1258.8px and fits; ONE offer takes it to 1288.2 and
 * clips CANCEL SKETCH; three offers take it to 1419.4 and clip the relational
 * flyout, Construction, FINISH and CANCEL — with `scrollWidth === clientWidth`,
 * so a real click at `sketch-save`'s own centre did nothing. Every ToolButton
 * on this strip is already icon-only, so the band's ladder had NOTHING to shed
 * (the three Flyout triggers were opted out of it) and measured itself into the
 * "icon" tier while saving 0px — a tier that reported work it had not done.
 *
 * The offer rail outranks the flyout triggers: the rail's words name what THIS
 * selection can do and disappear with it, while "Geometric"/"Dimension"/
 * "Relational" are permanent captions over icons that keep a tooltip and a
 * one-click menu. So the flyouts pay first (205.6px of words) and the rail
 * keeps its 129.2px, which is the ranking the band arrives at unaided at 1280
 * and 1366 and reverses — everything labelled — at 1440.
 */
const RAIL_LABEL_PRIORITY = 1;
const CONSTRAIN_LABEL_PRIORITY = -1;

/**
 * The constraint verbs, grouped by the family the constraint belongs to —
 * the same taxonomy the docs call out: Geometric (orientation of curves),
 * Dimensional (driving values), Relational (ties between points/entities).
 * Structure encodes the real vocabulary, not decoration.
 */
const CONSTRAINT_GROUPS: ReadonlyArray<{
  key: string;
  eyebrow: string;
  triggerLabel: string;
  triggerIcon: ReactNode;
  items: readonly ConstraintSpec[];
}> = [
  {
    key: "geometric",
    eyebrow: "Geometric",
    triggerLabel: "Geometric",
    triggerIcon: <PerpendicularIcon />,
    items: [
      {
        action: "horizontal",
        label: "Horizontal",
        keyHint: "H",
        name: "Horizontal constraint (H, on selected lines)",
        icon: <HorizontalIcon />,
      },
      {
        action: "vertical",
        label: "Vertical",
        keyHint: "V",
        name: "Vertical constraint (V, on selected lines)",
        icon: <VerticalIcon />,
      },
      {
        action: "parallel",
        label: "Parallel",
        keyHint: "P",
        name: "Parallel constraint (P, on two selected lines)",
        icon: <ParallelIcon />,
      },
      {
        action: "perpendicular",
        label: "Perpendicular",
        keyHint: "L",
        name: "Perpendicular constraint (L, on two selected lines)",
        icon: <PerpendicularIcon />,
      },
      {
        action: "tangent",
        label: "Tangent",
        keyHint: "T",
        name: "Tangent constraint (T, on a selected line and arc/circle, or two curves)",
        icon: <TangentIcon />,
      },
      {
        action: "collinear",
        label: "Collinear",
        keyHint: "I",
        name: "Collinear constraint (I, on two selected lines — puts them on one straight)",
        icon: <CollinearIcon />,
      },
    ],
  },
  {
    key: "dimensional",
    eyebrow: "Dimensional",
    triggerLabel: "Dimension",
    triggerIcon: <DistanceIcon />,
    items: [
      {
        action: "distance",
        label: "Distance",
        keyHint: "D",
        name: "Distance dimension (D, on one selected line)",
        icon: <DistanceIcon />,
      },
      {
        action: "radius",
        label: "Radius",
        keyHint: "R",
        name: "Radius dimension (R, on one selected circle or arc)",
        icon: <RadiusIcon />,
      },
      {
        // D IS "DIMENSION", AND THE SELECTION SAYS WHICH ONE — diameter has no
        // key of its own (see CONSTRAINT_SHORTCUTS). The row is still listed,
        // because the catalogue's job is to say the verb EXISTS: someone
        // hunting "how do I call out a diameter" finds it here and learns that
        // D on a round already is it, which no amount of pressing D teaches.
        action: "diameter",
        label: "Diameter",
        keyHint: "D",
        name: "Diameter dimension (D, on one selected circle or arc)",
        icon: <DiameterIcon />,
      },
      {
        action: "angle",
        label: "Angle",
        keyHint: "A",
        name: "Angle dimension (A, on two selected non-parallel lines)",
        icon: <AngleIcon />,
      },
      {
        action: "equal",
        label: "Equal",
        keyHint: "E",
        name: "Equal constraint (E, on two selected lines or two circles/arcs)",
        icon: <EqualIcon />,
      },
    ],
  },
  {
    key: "relational",
    eyebrow: "Relational",
    triggerLabel: "Relational",
    triggerIcon: <CoincidentIcon />,
    items: [
      {
        action: "coincident",
        label: "Coincident",
        keyHint: "C",
        name: "Coincident constraint (C, on two selected points)",
        icon: <CoincidentIcon />,
      },
      {
        action: "concentric",
        label: "Concentric",
        keyHint: "O",
        name: "Concentric constraint (O, on two selected circles or arcs)",
        icon: <ConcentricIcon />,
      },
      {
        action: "midpoint",
        label: "Midpoint",
        keyHint: "M",
        name: "Midpoint constraint (M, on a selected point and line — centres the point along the line)",
        icon: <MidpointIcon />,
      },
      {
        action: "symmetric",
        label: "Symmetric",
        keyHint: "S",
        // The two-lines form is NAMED. It shipped in `applyConstraintAction`
        // but this caption still promised only "two points about a line", so
        // the catalogue was actively steering people away from the selection
        // the verb had just learned to accept.
        name: "Symmetric constraint (S, on two selected points about a line, or two lines about a selected centerline)",
        icon: <SymmetricIcon />,
      },
      {
        action: "fixed",
        label: "Fixed",
        keyHint: "X",
        name: "Fix point (X, on selected points)",
        icon: <FixedIcon />,
      },
    ],
  },
];

/** A reusable datum plane already in the feature tree. */
export interface DatumPlaneOption {
  id: string;
  name: string;
  /** The resolved plane spec a new sketch seats on (a `FeatureRef` on the wire). */
  spec: SketchPlaneSpec;
}

export interface SketchStripProps {
  onSave: () => void;
  saving: boolean;
  saveError: string | null;
  /** Datum features already in the tree, offered as reusable sketch planes. */
  datumPlanes?: readonly DatumPlaneOption[];
  /** Sketch on an already-authored plane (an origin datum OR an existing datum). */
  onChoosePlaneSpec?: (spec: SketchPlaneSpec) => void;
  /**
   * Author a NEW offset plane inline (the primary "sketch 30 mm up" path):
   * creates a `datum` feature, then starts this sketch on it. Async — the
   * strip shows a pending state while the feature write is in flight.
   */
  onAuthorOffsetPlane?: (params: DatumOffsetParams) => void;
  /** True while an inline offset-plane create is in flight. */
  authoringOffset?: boolean;
  /** Inline offset-plane authoring failure, or null. */
  offsetPlaneError?: string | null;
  /**
   * Arm/disarm the "Pick a face" mode — the viewport then highlights the
   * body's planar faces; clicking one authors an `on_face` datum and seats
   * this sketch on it. Only offered when a body exists (`canPickFace`).
   */
  onTogglePickFace?: () => void;
  /** True when a body exists to pick a face from (gates the affordance). */
  canPickFace?: boolean;
  /** True while the face-pick mode is armed. */
  facePicking?: boolean;
  /** True while an on-face datum write is in flight. */
  authoringFace?: boolean;
  /** On-face authoring failure, or null. */
  facePickError?: string | null;
  /**
   * PICK-2 — why the armed face pick has nothing to pick, or null when it has.
   * The overlay that highlights pickable faces is fetched only while the tip
   * feature has a built body; without one the viewport is empty, and a prompt
   * that keeps saying "click a highlighted planar face" is the dead end this
   * closes. Not an error — nothing was attempted — so it reads as direction.
   */
  facePickBlocked?: string | null;
}

const OFFSET_BASE_OPTIONS: ReadonlyArray<SegmentOption<DatumPlaneName>> =
  DATUM_BASES.map((b) => ({
    value: b.id,
    label: b.label,
    "data-testid": `offset-plane-base-${b.id}`,
    "aria-label": `Offset from the ${b.label} datum`,
  }));

const OFFSET_FLIP_OPTIONS: ReadonlyArray<SegmentOption<"keep" | "flip">> = [
  {
    value: "keep",
    label: "Normal",
    "data-testid": "offset-plane-flip-keep",
    "aria-label": "Keep the plane normal",
  },
  {
    value: "flip",
    label: "Flipped",
    "data-testid": "offset-plane-flip-flip",
    "aria-label": "Reverse the plane normal",
  },
];

/**
 * The inline "+ Offset plane" authoring panel, hung from the band into the
 * viewport during the plane-pick step. Base datum · signed offset · normal
 * flip · "Sketch here" — a machinist height gauge. Keeps the common case one
 * click (the origin buttons above); this is the opt-in "sketch at a height"
 * path (docs/design/datum-planes.md §8/§10.1). Keyboard-first: the offset
 * field autofocuses, Enter authors, Escape collapses.
 */
function OffsetPlanePanel({
  onAuthor,
  onClose,
  busy,
  error,
}: {
  onAuthor: (params: DatumOffsetParams) => void;
  onClose: () => void;
  busy: boolean;
  error: string | null;
}) {
  const unit = useDocumentLengthUnit();
  const [form, setForm] = useState<OffsetForm>(defaultOffsetForm());
  // ONE computation, two readings (REASON-GATE-1, `submitBlocker.ts`): the
  // action is enabled iff there is no blocker sentence, and the sentence is
  // shown. The offset form IS the datum editor's `offset` kind, so it asks the
  // same function that editor asks rather than a second copy of the rule.
  // Null while creating: the label already says so.
  const blocker = busy
    ? null
    : datumSubmitBlocker({ kind: "offset", ...form }, unit);
  const canSubmit = blocker === null && !busy;

  const author = () => {
    const params = buildOffsetParams(form, unit);
    if (params === null) return;
    onAuthor(params);
  };

  return (
    <div
      className="w-editor max-w-full"
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          if (canSubmit) author();
        } else if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <Panel aria-label="Offset plane" data-testid="offset-plane-panel">
        <div className="flex flex-col gap-2 px-3 py-3">
          <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
            Offset plane
          </h2>
          <SegmentedControl
            label="Offset from"
            value={form.base}
            options={OFFSET_BASE_OPTIONS}
            onChange={(base) => setForm((f) => ({ ...f, base }))}
          />
          <NumberField
            // "Offset", the word the blocker sentence uses ("Enter the
            // offset.") and the datum editor labels the same field with.
            label="Offset"
            unit={unit}
            data-testid="offset-plane-offset"
            autoFocus
            value={form.offsetInput}
            error={offsetError(form.offsetInput, unit)}
            onChange={(e) =>
              setForm((f) => ({ ...f, offsetInput: e.target.value }))
            }
            onFocus={(e) => e.currentTarget.select()}
            aria-label={`Offset distance (${unit}, signed)`}
          />
          <SegmentedControl
            label="Normal"
            value={form.flip ? "flip" : "keep"}
            options={OFFSET_FLIP_OPTIONS}
            onChange={(v) => setForm((f) => ({ ...f, flip: v === "flip" }))}
          />
        </div>
        {/* The editors' action row (`PanelActionCell`), not two restyled raw
            buttons: a gated cell stays hoverable, focusable and in the
            accessibility tree, and says WHY in the caption's line and in its
            accessible description. The native `disabled` it replaces made a
            grey "Sketch here" that could explain nothing to anyone. */}
        <div className="grid grid-cols-2 divide-x divide-hairline border-t border-hairline">
          <PanelActionCell
            label="Cancel"
            caption="Esc"
            data-testid="offset-plane-cancel"
            onClick={onClose}
          />
          <PanelActionCell
            label={busy ? "Creating…" : "Sketch here"}
            caption="Enter"
            data-testid="offset-plane-confirm"
            aria-busy={busy}
            disabled={!canSubmit}
            disabledReason={blocker ?? undefined}
            onClick={author}
          />
        </div>
      </Panel>
      {error ? (
        <p
          role="alert"
          data-testid="offset-plane-error"
          className="mt-2 border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The "Pick a face" guide, hung from the band into the viewport during the
 * plane-pick step. Honest about the stage-1 limit (datum-planes §7 /
 * topological-naming §9): a face-anchored sketch is a BEST-EFFORT reference — a
 * drastic upstream change can retarget it — so the copy never implies a rock-
 * solid link. Keyboard-first: Escape (handled by the parent) cancels.
 */
function FacePickPrompt({
  busy,
  blocked,
  error,
  onCancel,
}: {
  busy: boolean;
  /** PICK-2 — why there is nothing to pick, or null. */
  blocked: string | null;
  error: string | null;
  onCancel: () => void;
}) {
  return (
    <div className="w-editor max-w-full">
      <div
        role="status"
        data-testid="face-pick-prompt"
        data-blocked={blocked !== null ? "true" : "false"}
        className="border border-hairline bg-anvil px-3 py-3 font-body text-xs text-gauge"
      >
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          {blocked !== null ? "Nothing to pick" : "Pick a face"}
        </h2>
        <p className="mt-1.5 text-mist" data-testid="face-pick-prompt-body">
          {blocked !== null
            ? blocked
            : busy
              ? "Placing the sketch on the face…"
              : "Click a highlighted planar face to sketch on it."}
        </p>
        <p className="mt-1.5 text-gauge">
          {blocked !== null
            ? "Pick a datum plane above to keep sketching in the meantime."
            : "Best-effort reference — a big change upstream can move it. Curved faces aren’t pickable."}
        </p>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            className="font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
            data-testid="face-pick-cancel"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </div>
      {error ? (
        <p
          role="alert"
          data-testid="face-pick-error"
          className="mt-2 border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The strip's status cell — a two-tier title-block reading matching the band's
 * grouped eyebrows: a stamped mode eyebrow (Plane / Sketch) over the active
 * plane and, while drawing, the live selection. Names the mode in the band
 * itself, reinforcing the breadcrumb (UI-REVIEW 2026-07-16, Track C).
 */
function StatusCell({
  eyebrow,
  children,
}: {
  eyebrow: string;
  children: ReactNode;
}) {
  return (
    <div className="flex shrink-0 flex-col justify-center px-1.5 py-1">
      <span className="px-1 pb-0.5 font-display text-2xs uppercase tracking-[0.16em] text-gauge">
        {eyebrow}
      </span>
      <div className="flex items-center gap-2 whitespace-nowrap px-1 font-data text-xs">
        {children}
      </div>
    </div>
  );
}

/**
 * One cap on the offer rail: a stamped keycap and a plain verb, a real button
 * so the same affordance serves the keyboard (press the key) and the pointer
 * (click the cap). The label sheds with the band's measured label tier.
 */
function OfferCap({
  testId,
  keyCap,
  keyName,
  label,
  onClick,
}: {
  testId: string;
  /** What the cap reads ("D", "Del"). */
  keyCap: string;
  /** The key's spoken name, for the accessible name and tooltip. */
  keyName: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-label={`${label} — press ${keyName}`}
      title={`${label} (${keyName})`}
      onClick={onClick}
      className="flex items-center gap-1 rounded-sm hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass motion-safe:transition-colors"
    >
      <Kbd>{keyCap}</Kbd>
      <span className="[[data-labels=off]_&]:hidden">{label}</span>
    </button>
  );
}

/**
 * The Mirror tool's two-phase guide, hung from the band into the viewport.
 * Targets phase: a live count and the "Choose axis" step (Enter also advances).
 * Axis phase: the instruction to click a line, with the reflection ghost doing
 * the real talking in the viewport. Keyboard-first, honest about what v1 does
 * (geometry only — no symmetric constraints are added).
 */
function MirrorPrompt({
  mirror,
  onAdvance,
}: {
  mirror: NonNullable<ReturnType<typeof useSketchStore.getState>["mirror"]>;
  onAdvance: () => void;
}) {
  const count = mirror.targets.length;
  const noun = count === 1 ? "entity" : "entities";
  return (
    <div
      role="status"
      data-testid="mirror-prompt"
      data-phase={mirror.phase}
      className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
    >
      {mirror.phase === "targets" ? (
        <div className="flex items-center gap-3">
          <span>
            Pick entities to mirror
            {count > 0 ? (
              <>
                {" · "}
                <span className="text-mist" data-testid="mirror-count">
                  {count} {noun}
                </span>
              </>
            ) : null}
          </span>
          <button
            type="button"
            className="font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-40"
            disabled={count === 0}
            data-testid="mirror-advance"
            onClick={onAdvance}
          >
            Choose axis ↵
          </button>
        </div>
      ) : (
        <span data-testid="mirror-count">
          Click a line or an origin axis to mirror {count} {noun} about it ·
          reflects geometry only
        </span>
      )}
    </div>
  );
}

/**
 * The Fillet/Chamfer two-line guide, hung from the band into the viewport.
 * Collecting phase: how many of the two legs are held. Once both are picked the
 * in-canvas value editor takes over (radius / setback), so the prompt steps
 * back to a one-line reminder. Keyboard-first, honest about v1 (two lines only).
 */
function CornerPrompt({
  corner,
}: {
  corner: NonNullable<ReturnType<typeof useSketchStore.getState>["corner"]>;
}) {
  const count = corner.picks.length;
  const verb = corner.op === "fillet" ? "round" : "bevel";
  return (
    <div
      role="status"
      data-testid="corner-prompt"
      data-phase={count >= 2 ? "value" : "legs"}
      className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
    >
      {count >= 2 ? (
        <span>
          Set the {corner.op === "fillet" ? "radius" : "distance"} to {verb} the
          corner
        </span>
      ) : (
        <span>
          Pick two lines to {verb} their corner
          {count > 0 ? (
            <>
              {" · "}
              <span className="text-mist" data-testid="corner-count">
                {count} of 2
              </span>
            </>
          ) : null}
        </span>
      )}
    </div>
  );
}

/**
 * The Spline tool's fit-point guide, hung from the band into the viewport. It
 * counts placed points and, once two are held, offers the keyboard-first finish
 * (Enter / double-click). Once committed, each fit point constrains like any
 * point (coincident / fixed / symmetric); the spline is also valid as part of a
 * closed extrude/revolve loop.
 */
function SplinePrompt({ count }: { count: number }) {
  const ready = count >= 2;
  return (
    <div
      role="status"
      data-testid="spline-prompt"
      data-phase={ready ? "ready" : "collecting"}
      className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
    >
      {ready ? (
        <span>
          <span className="text-mist" data-testid="spline-count">
            {count} fit points
          </span>{" "}
          · Enter or double-click to finish · fit points constrain like any
          point
        </span>
      ) : (
        <span>
          Click to place fit points
          {count > 0 ? (
            <>
              {" · "}
              <span className="text-mist" data-testid="spline-count">
                {count} placed
              </span>
            </>
          ) : null}
        </span>
      )}
    </div>
  );
}

export function SketchStrip({
  onSave,
  saving,
  saveError,
  datumPlanes = [],
  onChoosePlaneSpec,
  onAuthorOffsetPlane,
  authoringOffset = false,
  offsetPlaneError = null,
  onTogglePickFace,
  canPickFace = false,
  facePicking = false,
  authoringFace = false,
  facePickError = null,
  facePickBlocked = null,
}: SketchStripProps) {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const tool = useSketchStore((state) => state.tool);
  const setTool = useSketchStore((state) => state.setTool);
  const choosePlane = useSketchStore((state) => state.choosePlane);
  const [offsetOpen, setOffsetOpen] = useState(false);
  const setHoveredPlane = useSketchStore((state) => state.setHoveredPlane);
  const hoveredPlane = useSketchStore((state) => state.hoveredPlane);
  // The frame is excluded for the same reason its pins are excluded from the
  // constraint count below: the user drew four lines, so the strip says four,
  // and "Discard 5 unsaved entities" must never offer to throw away a fifth
  // thing that only exists because they grounded one of them.
  const entityCount = useSketchStore(
    (state) => withoutDatums(state.entities).length,
  );
  // The frame's own pins are excluded: grounding a corner to the origin is ONE
  // constraint the user made, and counting the pin that came with it would be
  // the readout claiming work nobody did (`sketch/datum.ts`).
  const constraintCount = useSketchStore((state) =>
    authoredConstraintCount(state.constraints),
  );
  const selection = useSketchStore((state) => state.selection);
  const entities = useSketchStore((state) => state.entities);
  const constraints = useSketchStore((state) => state.constraints);
  const applyConstraint = useSketchStore((state) => state.applyConstraint);
  const toggleConstruction = useSketchStore(
    (state) => state.toggleConstruction,
  );
  const deleteSelection = useSketchStore((state) => state.deleteSelection);
  const snapStepMm = useSketchStore((state) => state.snapStepMm);
  const setSnapStep = useSketchStore((state) => state.setSnapStep);
  const lengthUnit = useDocumentLengthUnit();
  const gridSteps = gridStepOptions(lengthUnit, snapStepMm);
  const hint = useSketchStore((state) => state.hint);
  const editNote = useSketchStore((state) => state.editNote);
  const mirror = useSketchStore((state) => state.mirror);
  const corner = useSketchStore((state) => state.corner);
  const pending = useSketchStore((state) => state.pending);
  const advanceMirror = useSketchStore((state) => state.advanceMirror);
  const bound = useSketchStore((state) => state.featureId !== null);
  const exit = useSketchStore((state) => state.exit);
  // Sketch-local history. `canUndo` is the stack itself, not a claim about it.
  const canUndo = useSketchStore((state) => state.past.length > 0);
  const canRedo = useSketchStore((state) => state.future.length > 0);
  const editBusy = useSketchStore((state) => state.editBusy);
  const undo = useSketchStore((state) => state.undo);
  const redo = useSketchStore((state) => state.redo);

  /*
   * Ctrl/⌘+Z, Ctrl/⌘+Shift+Z, Ctrl+Y — the SAME grammar the part and assembly
   * workspaces use (`undoRedoStep`), pointed at the sketch's own stack.
   *
   * It lives here rather than in `PartPage` because the binding belongs with
   * the buttons that show its state: PartPage's history effect deliberately
   * stands down while `mode !== "off"`, so in the sketcher this key did
   * nothing at all — and the one thing it must never do is what it would have
   * done by default, which is undo a FEATURE. Draw step only: during the
   * plane pick there is nothing yet to reverse. A focused text field (a
   * dimension cell) keeps its native undo — the typing guard is resolved
   * inside the pure grammar helper.
   */
  useEffect(() => {
    if (mode !== "draw") return;
    const onKeyDown = (event: KeyboardEvent) => {
      const step = undoRedoStep(event, isTypingTarget(event.target));
      if (step === null) return;
      // Ours in the sketcher even at a stack bound — swallow it so the browser
      // never runs its own undo behind the tool.
      event.preventDefault();
      if (step === "undo") undo();
      else redo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, undo, redo]);

  /*
   * Delete / Backspace on selected ENTITIES (helical-gear gap G7). The part
   * page's sketch key handler owns the same keys for a selected CONSTRAINT
   * glyph and marks the event handled (`preventDefault`) when it removes one,
   * so one keypress can never delete a constraint AND the geometry. The
   * binding lives here, beside the offer-rail cap that shows it, for the
   * reason the undo binding above does. (`useGlobalKeys` already refuses a
   * key another handler cancelled and a key typed into a field.)
   */
  useGlobalKeys(
    "sketch-delete-entities",
    mode === "draw"
      ? (event) => {
          if (event.key !== "Delete" && event.key !== "Backspace") return;
          if (event.metaKey || event.ctrlKey || event.altKey) return;
          const state = useSketchStore.getState();
          if (state.selectedConstraint !== null) return;
          if (
            deleteSelectedEntities(
              state.selection,
              state.entities,
              state.constraints,
            ) === null
          ) {
            return;
          }
          event.preventDefault();
          deleteSelection();
        }
      : null,
  );

  // Exit-with-unsaved-work confirm (F1). Derived rather than trusted: the prompt
  // only renders while it is still TRUE that discarding would destroy something,
  // so saving or deleting the last entity behind an armed confirm dismisses it
  // instead of leaving a prompt about work that no longer exists.
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const discardArmed = confirmingDiscard && !bound && entityCount > 0;

  // The verbs the current selection unlocks. Only while drawing, and only
  // where the key would truly do something, so the rail is never a dead
  // promise (`selectionVerbHints`).
  const verbHints =
    mode === "draw" ? selectionVerbHints(selection, entities, constraints) : [];
  // The profile's open ends, counted and measured (G8).
  const openEndReport = mode === "draw" ? describeOpenEnds(entities) : null;
  // ...and whether it can be deleted, offered as the rail's last cap (G7).
  const deletable =
    mode === "draw" &&
    deleteSelectedEntities(selection, entities, constraints) !== null;

  if (mode === "off") return null;

  return (
    <>
      {/* One thin instrument row, now the LEFT of the full-width top band:
          status → draw tools → constraint families → construction → finish.
          The band (TopToolbar) supplies the edge-to-edge chrome; this strip
          brings only its own hairline-divided cells (no bordered box), so the
          band reads as one continuous CAD toolbar. */}
      <div
        aria-label="Sketch"
        data-testid="sketch-strip"
        className="flex items-stretch divide-x divide-hairline"
      >
        <StatusCell eyebrow={mode === "plane" ? "Plane" : "Sketch"}>
          <span className="text-mist" data-testid="sketch-step">
            {mode === "plane" ? "Pick a plane" : `On ${describePlane(plane)}`}
          </span>
          {mode === "draw" ? (
            <>
              <span aria-hidden className="text-etch">
                ·
              </span>
              <span className="text-gauge" data-testid="selection-readout">
                {describeSelection(selection)}
                {constraintCount > 0 ? ` · ${constraintCount} applied` : ""}
              </span>
              {/* OPEN ENDS (helical-gear gap G8): the profile's unjoined ends,
                  counted here and ringed in the viewport, so a loop open by
                  microns is known BEFORE the extrude or loft that needs it
                  closed. Flag ink only when one is a near miss: an invisible
                  gap is the dangerous kind. The tooltip names the gap. */}
              {openEndReport !== null ? (
                <>
                  <span aria-hidden className="text-etch">
                    ·
                  </span>
                  <span
                    data-testid="open-ends"
                    title={openEndReport.title}
                    className={
                      openEndReport.nearMiss ? "text-flag" : "text-gauge"
                    }
                  >
                    {openEndReport.label}
                  </span>
                </>
              ) : null}
              {/* THE OFFER RAIL — the selection's next moves, keyboard-first.
                  Quiet by construction: stamped keycaps and plain verbs, brass
                  only on the cap, sitting in the readout's own row so it reads
                  as instrument guidance and not a banner. Each cap is a real
                  button, so the same affordance serves the keyboard and the
                  pointer — press the letter, or click the letter. */}
              {verbHints.length > 0 || deletable ? (
                <>
                  <span aria-hidden className="text-etch">
                    ·
                  </span>
                  <span
                    role="status"
                    data-testid="dimension-hint"
                    // The rail is a first-class participant in the band's
                    // measured label tier (`CommandBand` guarantee #3), not a
                    // free-growing readout: it declares a priority like any
                    // ToolGroup, so the band can buy its words back or shed
                    // them by MEASUREMENT. It ranks ABOVE the Constrain
                    // flyouts (RAIL_LABEL_PRIORITY) because those words are
                    // permanent chrome naming families whose members are one
                    // click away, while these name what THIS selection can do
                    // right now and vanish with it — the higher information
                    // per pixel. Shed, each offer keeps its brass keycap, so
                    // the rail still says "these keys are live".
                    data-label-priority={RAIL_LABEL_PRIORITY}
                    className="flex items-center gap-2 text-gauge"
                  >
                    {verbHints.map((verb) => (
                      <OfferCap
                        key={verb.action}
                        testId={`verb-hint-${verb.action}`}
                        keyCap={verb.key}
                        keyName={verb.key}
                        label={verb.label}
                        onClick={() => applyConstraint(verb.action)}
                      />
                    ))}
                    {deletable ? (
                      <OfferCap
                        testId="sketch-delete"
                        keyCap="Del"
                        keyName="Delete"
                        label="Delete"
                        onClick={deleteSelection}
                      />
                    ) : null}
                  </span>
                </>
              ) : null}
            </>
          ) : null}
        </StatusCell>

        {mode === "plane" ? (
          <>
            <ToolGroup eyebrow="Origin">
              {DATUM_PLANES.map((name) => (
                <ToolButton
                  key={name}
                  icon={
                    <span className="font-display text-2xs tracking-[0.08em]">
                      {name}
                    </span>
                  }
                  label={`${name} plane`}
                  showLabel={false}
                  active={hoveredPlane === name}
                  data-testid={`plane-${name}`}
                  aria-label={`Sketch on the ${name} plane`}
                  onClick={() => choosePlane(name)}
                  onMouseEnter={() => setHoveredPlane(name)}
                  onMouseLeave={() => setHoveredPlane(null)}
                  onFocus={() => setHoveredPlane(name)}
                  onBlur={() => setHoveredPlane(null)}
                />
              ))}
            </ToolGroup>

            {/* Reusable datum features already in the tree (a standalone datum
                plane picked once can seat many sketches — DRY at the model
                level). */}
            {datumPlanes.length > 0 ? (
              <ToolGroup
                eyebrow="In tree"
                aria-label="Datum planes in the tree"
              >
                {datumPlanes.map((datum) => (
                  <ToolButton
                    key={datum.id}
                    icon={<DatumIcon />}
                    label={datum.name}
                    showLabel
                    data-testid={`plane-datum-${datum.id}`}
                    aria-label={`Sketch on ${datum.name}`}
                    onClick={() => onChoosePlaneSpec?.(datum.spec)}
                  />
                ))}
              </ToolGroup>
            ) : null}

            {/* The inline "sketch at a height" path — additive, opt-in; the
                three origin datums above stay the one-click common case. */}
            {onAuthorOffsetPlane ? (
              <ToolGroup eyebrow="Offset" aria-label="Offset plane">
                <ToolButton
                  icon={<DatumIcon />}
                  label="Offset plane"
                  showLabel
                  active={offsetOpen}
                  data-testid="datum-offset-plane"
                  aria-label="Author an offset plane — sketch at a height"
                  onClick={() => {
                    setOffsetOpen((open) => !open);
                    if (facePicking) onTogglePickFace?.();
                  }}
                />
              </ToolGroup>
            ) : null}

            {/* Sketch on a picked model face (an on_face datum). Only offered
                once a body exists — the faces are highlighted in the viewport. */}
            {onTogglePickFace && canPickFace ? (
              <ToolGroup eyebrow="Face" aria-label="Model face">
                <ToolButton
                  icon={<DatumIcon />}
                  label="Pick a face"
                  showLabel
                  active={facePicking}
                  data-testid="plane-pick-face"
                  aria-label="Pick a model face to sketch on"
                  onClick={() => {
                    setOffsetOpen(false);
                    onTogglePickFace();
                  }}
                />
              </ToolGroup>
            ) : null}
          </>
        ) : null}

        {mode === "draw" ? (
          <>
            {/* History leads the TOOLS here, exactly as it leads the part band
                — same group, same glyphs, same chord, same position relative to
                the tools, so the reflex transfers straight into the sketcher.
                What it holds is different (this sketch's edits, not the feature
                ring), and `scope` is what says so out loud. The status cell
                keeps the far-left slot: it is a readout, not a tool. */}
            <HistoryGroup
              ready
              canUndo={canUndo}
              canRedo={canRedo}
              hold={null}
              holdReason={editBusy ? "Finishing the last edit…" : null}
              scope={{
                step: "the last sketch edit",
                undoEmpty: "Nothing drawn yet",
                redoEmpty: "Nothing to redo in this sketch",
              }}
              onUndo={undo}
              onRedo={redo}
            />

            <ToolGroup eyebrow="Draw" aria-label="Sketch tools">
              {TOOLS.map(({ tool: t, keyHint, name, icon }) => (
                <ToolButton
                  key={t}
                  icon={icon}
                  label={name}
                  shortcut={keyHint}
                  active={tool === t}
                  data-testid={`tool-${t}`}
                  aria-label={name}
                  onClick={() => setTool(t)}
                />
              ))}
            </ToolGroup>

            <ToolGroup eyebrow="Modify">
              {MODIFY_TOOLS.map(({ tool: t, keyHint, name, icon }) => (
                <ToolButton
                  key={t}
                  icon={icon}
                  label={name}
                  shortcut={keyHint}
                  active={tool === t}
                  data-testid={`tool-${t}`}
                  aria-label={name}
                  onClick={() => setTool(t)}
                />
              ))}
            </ToolGroup>

            <ToolGroup
              eyebrow="Constrain"
              labelPriority={CONSTRAIN_LABEL_PRIORITY}
            >
              {CONSTRAINT_GROUPS.map((group) => (
                <Flyout
                  key={group.key}
                  label={group.triggerLabel}
                  icon={group.triggerIcon}
                  eyebrow={group.eyebrow}
                  data-testid={`constraint-group-${group.key}`}
                  items={group.items.map<FlyoutItem>((item) => ({
                    key: item.action,
                    icon: item.icon,
                    label: item.label,
                    shortcut: item.keyHint,
                    // THE CATALOGUE IS LIVE, from the SAME predicate the offer
                    // rail reads (`verbIsAvailable`). The rail proposes the
                    // three verbs a fitting selection unlocks; the catalogue
                    // holds all sixteen and says, of each, whether this
                    // selection reaches it and what it would take. Neither can
                    // drift from the other, because neither owns the rule.
                    available: verbIsAvailable(
                      item.action,
                      selection,
                      entities,
                      constraints,
                    ),
                    requires: verbSelectionShape(item.action),
                    onSelect: () => applyConstraint(item.action),
                    "data-testid": `constraint-${item.action}`,
                    "aria-label": item.name,
                  }))}
                />
              ))}
              <ToolButton
                icon={<ConstructionIcon />}
                shortcut="N"
                label="Construction"
                active={selectionAllConstruction(selection, entities)}
                data-testid="sketch-construction"
                aria-label="Toggle construction geometry (N, on selected entities) — reference-only, excluded from the extrude profile"
                onClick={toggleConstruction}
              />
            </ToolGroup>

            {/* THE GRID STEP (helical-gear gap G2). The store has always had a
                configurable step and nothing ever set it, so every sketch
                snapped to 1 mm. Offered in the document's unit; the DRO's
                SNAP cell reports the step in use. */}
            <div className="flex shrink-0 items-center px-2">
              <InlineSelect
                eyebrow="Grid"
                aria-label="Grid snap step"
                data-testid="sketch-grid-step"
                options={gridSteps.map((step) => ({
                  value: String(step.mm),
                  label: step.label,
                }))}
                value={String(snapStepMm)}
                onChange={(event) => setSnapStep(Number(event.target.value))}
              />
            </div>

            {/* NO Esc chip here — finishing is a CLICK. History, because this
                caption has been wrong twice in opposite directions. Until
                2026-07-30 it sat on Exit saying "Esc discards" while Esc in fact
                SAVED (UI-REVIEW F1); it was moved here to tell the truth. Then
                FB-13 (founder, 2026-08-01) showed the binding itself was the
                defect: Escape at rest ended the sketch, so the reflex after a
                click that appeared to do nothing cost you the sketcher. Escape
                is a CANCEL key in every tool we benchmark against and never
                commits, so it now unwinds and then stops. Advertising it here
                would restore exactly the caption-vs-binding disagreement F1
                exists to prevent. */}
            <ToolGroup eyebrow="Finish" aria-label="Finish sketch">
              {/* SAVE IS NOT GATED ON `saving`, AND THAT IS THE WHOLE FIX.
                  It used to read `disabled={saving || …}`, which opened a
                  ~280ms hole in the middle of the one control that ends the
                  sketch: QA measured the button going `aria-disabled="true"`
                  at 208/236/244ms after an edit settles and clearing at
                  481/513/526ms (three runs), and a real `page.mouse.click` at
                  the button's own centre inside that window resolved to
                  `sketch-save` — no overlay, the event reached the button —
                  and did NOTHING. The strip was still mounted 30s later.
                  `ToolButton` implements `disabled` as `aria-disabled` plus a
                  handler that returns early, so there was no queue, no re-arm
                  and no feedback: the click was dropped on the floor.

                  THE QUEUE ALREADY EXISTED ONE LAYER DOWN; the disable is what
                  made it unreachable. `persistBuffer` has carried
                  `pendingExitRef` since the duplicate-"Sketch1" fix — a finish
                  requested while a create is in flight is REMEMBERED and lands
                  the moment the feature binds. For a bound sketch the writes
                  are a serialized chain, so a finish during an in-flight PATCH
                  simply enqueues behind it with the FRESHER payload and exits
                  on completion. Both paths were already correct; the only
                  thing standing between the user and them was this flag. So
                  this is the affordance/hit-target family again (CLAUDE.md):
                  the capability was there and unreachable.

                  `saving` still does the two jobs it can honestly do — it says
                  "Saving…" and sets `aria-busy` — because a save in flight is
                  worth REPORTING and is not worth REFUSING for. A debounce is
                  an implementation detail the user cannot see, cannot predict
                  and must not have to model; gating a control on one makes a
                  Save that works most of the time and silently does nothing the
                  rest, which is the "no dead ends, no ambiguous exits" defect
                  the design mandate names by name.

                  What remains disabled is a REAL refusal with a REAL reason:
                  an empty sketch has nothing to put in the part, and the
                  caption says so where the user is looking. */}
              <ToolButton
                icon={<CheckIcon />}
                label={
                  saving ? "Saving…" : bound ? "Finish sketch" : "Save sketch"
                }
                caption={
                  bound
                    ? "edits save live"
                    : entityCount === 0
                      ? "nothing drawn yet"
                      : `${entityCount} ${entityCount === 1 ? "entity" : "entities"}`
                }
                data-testid="sketch-save"
                aria-label={
                  bound
                    ? "Finish sketch (edits are already saved)"
                    : "Save sketch"
                }
                aria-busy={saving}
                disabled={!bound && entityCount === 0}
                onClick={onSave}
              />
              {discardArmed ? (
                <>
                  {/* The ONE control on this strip that keeps its `saving`
                      gate, because here the refusal is real rather than
                      incidental: a discard cannot call back a create that is
                      already on the wire, so exiting mid-save would clear the
                      buffer and let the feature land anyway — the user would
                      watch the thing they just discarded appear in the tree.
                      The gate stays; what changes is that it now SAYS SO.
                      `ToolButton` keeps an `aria-disabled` control hoverable
                      and focusable precisely so its caption can carry the
                      reason, and that caption is the button's accessible
                      description, so the refusal reaches a screen reader too.
                      A silent refusal is the one option that is definitely
                      wrong. */}
                  <ToolButton
                    icon={<CloseIcon />}
                    label={`Discard ${entityCount}`}
                    caption={
                      saving ? "wait — a save is landing" : "cannot be undone"
                    }
                    data-testid="sketch-discard-confirm"
                    aria-label={`Discard ${entityCount} unsaved ${entityCount === 1 ? "entity" : "entities"} — this cannot be undone`}
                    aria-busy={saving}
                    disabled={saving}
                    onClick={() => {
                      setConfirmingDiscard(false);
                      exit();
                    }}
                  />
                  <ToolButton
                    icon={<CheckIcon />}
                    label="Keep drawing"
                    caption="back to the sketch"
                    active
                    data-testid="sketch-discard-cancel"
                    aria-label="Keep drawing — do not discard"
                    onClick={() => setConfirmingDiscard(false)}
                  />
                </>
              ) : (
                <ToolButton
                  icon={<CloseIcon />}
                  label="Exit"
                  caption={
                    bound
                      ? "keeps saved edits"
                      : entityCount > 0
                        ? `discards ${entityCount}`
                        : "nothing to discard"
                  }
                  // Not gated on `saving` either, for the same reason as Save
                  // and one of its own: Exit is NOT the destructive step. On a
                  // bound sketch it leaves edits that are already saving; on an
                  // unbound one with work in it, it only ARMS the confirm above
                  // — which is where the real refusal lives and says why. The
                  // old `disabled={saving}` bought no safety (the user simply
                  // clicked again 300ms later and got the identical outcome)
                  // and cost the same silent dead end Save had.
                  data-testid="sketch-exit"
                  aria-label={
                    bound
                      ? "Exit sketch (edits are already saved)"
                      : entityCount > 0
                        ? `Exit sketch and discard ${entityCount} unsaved ${entityCount === 1 ? "entity" : "entities"} — asks first`
                        : "Exit sketch (nothing drawn yet)"
                  }
                  onClick={() => {
                    // Unpersisted entities have no undo path — the history stack
                    // has nothing to restore — so this is the one exit that must
                    // ask. A bound sketch's edits are already saved: no prompt.
                    if (!bound && entityCount > 0) setConfirmingDiscard(true);
                    else exit();
                  }}
                />
              )}
            </ToolGroup>
          </>
        ) : null}
      </div>

      {/* The inline offset-plane authoring panel hangs from the band during
          the plane-pick step, so the origin buttons stay one-click above. */}
      {mode === "plane" && offsetOpen && onAuthorOffsetPlane ? (
        <div className="absolute left-editor top-full z-overlay mt-2">
          <OffsetPlanePanel
            onAuthor={onAuthorOffsetPlane}
            onClose={() => setOffsetOpen(false)}
            busy={authoringOffset}
            error={offsetPlaneError}
          />
        </div>
      ) : null}

      {/* The "Pick a face" guide, hung from the band while the mode is armed —
          the faces themselves are the affordance out in the viewport. */}
      {mode === "plane" && facePicking && onTogglePickFace ? (
        <div className="absolute left-editor top-full z-overlay mt-2">
          <FacePickPrompt
            busy={authoringFace}
            blocked={facePickBlocked}
            error={facePickError}
            onCancel={onTogglePickFace}
          />
        </div>
      ) : null}

      {/* Transient readouts hang from the band's bottom edge into the
          viewport's top-left, so the band itself stays one thin row. */}
      {mirror !== null ||
      corner !== null ||
      tool === "spline" ||
      hint ||
      saveError ||
      editNote ? (
        <div className="absolute left-editor top-full z-overlay mt-2 flex max-w-sm flex-col gap-2">
          {mirror !== null ? (
            <MirrorPrompt mirror={mirror} onAdvance={advanceMirror} />
          ) : null}
          {corner !== null ? <CornerPrompt corner={corner} /> : null}
          {tool === "spline" ? <SplinePrompt count={pending.length} /> : null}
          {editNote ? (
            <p
              role="status"
              data-testid="sketch-edit-note"
              className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
            >
              {editNote}
            </p>
          ) : null}
          {hint ? (
            <p
              role="status"
              data-testid="constraint-hint"
              className="border border-hairline bg-anvil px-3 py-2 font-body text-xs text-gauge"
            >
              {hint}
            </p>
          ) : null}
          {saveError ? (
            <p
              role="alert"
              data-testid="sketch-save-error"
              className="border border-flag bg-anvil px-3 py-2 font-body text-xs text-flag"
            >
              {saveError}
            </p>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
