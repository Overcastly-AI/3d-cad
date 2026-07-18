/**
 * The sketch toolbar — one thin title-block row that fills the LEFT of the
 * full-width top band while sketching, icon-forward. Plane-pick step: the
 * three datum planes (keyboard
 * path, hover-synced with the 3D sheets). Draw step, all on a single ruled
 * row so the viewport keeps the pixels: a flat status cell (plane + live
 * selection), the four sketch tools as scribed icons, the twelve constraint
 * verbs grouped by kind (Geometric / Dimensional / Relational) behind labeled
 * flyouts, the Construction toggle, then SAVE and EXIT as icon buttons —
 * their counts/reasons engraved in tooltips, never stacked into tall cells.
 *
 * One keyboard, two vocabularies survives untouched: the global key handler
 * still arms tools (L/R/C/A) with nothing selected and fires constraint verbs
 * (H/V/D/R/X/C/P/L/T/E/S/O + N) with a selection. The toolbar is the
 * DISCOVERABLE surface — every icon's tooltip engraves its accelerator — but
 * the letters remain the fast path. Quiet chrome; the viewport keeps the
 * pixels.
 */
import {
  ArcIcon,
  ChamferIcon,
  CheckIcon,
  CircleIcon,
  CloseIcon,
  CoincidentIcon,
  ConcentricIcon,
  ConstructionIcon,
  DatumIcon,
  DistanceIcon,
  EqualIcon,
  ExtendIcon,
  FilletIcon,
  FixedIcon,
  Flyout,
  type FlyoutItem,
  HorizontalIcon,
  LineIcon,
  MirrorIcon,
  NumberField,
  OffsetIcon,
  Panel,
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
import { type ReactNode, useState } from "react";

import type { DatumOffsetParams } from "../api/parts";
import {
  describeSelection,
  selectionAllConstruction,
  type ConstraintAction,
} from "../sketch/constraints";
import {
  buildOffsetParams,
  canSubmitOffset,
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
        action: "symmetric",
        label: "Symmetric",
        keyHint: "S",
        name: "Symmetric constraint (S, on two selected points about a selected line)",
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
  const canSubmit = canSubmitOffset(form, unit) && !busy;

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
            label="Distance"
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
          <div className="mt-1 flex items-center justify-between gap-2">
            <button
              type="button"
              className="font-display text-2xs uppercase tracking-[0.14em] text-gauge hover:text-mist focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass"
              data-testid="offset-plane-cancel"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className="font-display text-2xs uppercase tracking-[0.14em] text-brass hover:text-brass-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass disabled:opacity-40"
              data-testid="offset-plane-confirm"
              aria-busy={busy}
              disabled={!canSubmit}
              onClick={author}
            >
              {busy ? "Creating…" : "Sketch here"}
            </button>
          </div>
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
  error,
  onCancel,
}: {
  busy: boolean;
  error: string | null;
  onCancel: () => void;
}) {
  return (
    <div className="w-editor max-w-full">
      <div
        role="status"
        data-testid="face-pick-prompt"
        className="border border-hairline bg-anvil px-3 py-3 font-body text-xs text-gauge"
      >
        <h2 className="font-display text-2xs uppercase tracking-[0.18em] text-gauge">
          Pick a face
        </h2>
        <p className="mt-1.5 text-mist">
          {busy
            ? "Placing the sketch on the face…"
            : "Click a highlighted planar face to sketch on it."}
        </p>
        <p className="mt-1.5 text-gauge">
          Best-effort reference — a big change upstream can move it. Curved
          faces aren’t pickable.
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
          Click a line to mirror {count} {noun} about it · reflects geometry
          only
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
}: SketchStripProps) {
  const mode = useSketchStore((state) => state.mode);
  const plane = useSketchStore((state) => state.plane);
  const tool = useSketchStore((state) => state.tool);
  const setTool = useSketchStore((state) => state.setTool);
  const choosePlane = useSketchStore((state) => state.choosePlane);
  const [offsetOpen, setOffsetOpen] = useState(false);
  const setHoveredPlane = useSketchStore((state) => state.setHoveredPlane);
  const hoveredPlane = useSketchStore((state) => state.hoveredPlane);
  const entityCount = useSketchStore((state) => state.entities.length);
  const constraintCount = useSketchStore((state) => state.constraints.length);
  const selection = useSketchStore((state) => state.selection);
  const entities = useSketchStore((state) => state.entities);
  const applyConstraint = useSketchStore((state) => state.applyConstraint);
  const toggleConstruction = useSketchStore(
    (state) => state.toggleConstruction,
  );
  const hint = useSketchStore((state) => state.hint);
  const editNote = useSketchStore((state) => state.editNote);
  const mirror = useSketchStore((state) => state.mirror);
  const corner = useSketchStore((state) => state.corner);
  const pending = useSketchStore((state) => state.pending);
  const advanceMirror = useSketchStore((state) => state.advanceMirror);
  const bound = useSketchStore((state) => state.featureId !== null);
  const exit = useSketchStore((state) => state.exit);

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

            <ToolGroup eyebrow="Constrain">
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

            <ToolGroup eyebrow="Finish" aria-label="Finish sketch">
              <ToolButton
                icon={<CheckIcon />}
                label={
                  saving ? "Saving…" : bound ? "Finish sketch" : "Save sketch"
                }
                caption={
                  bound
                    ? "edits save live"
                    : `${entityCount} ${entityCount === 1 ? "entity" : "entities"}`
                }
                data-testid="sketch-save"
                aria-label={bound ? "Finish sketch (saved)" : "Save sketch"}
                aria-busy={saving}
                disabled={saving || (!bound && entityCount === 0)}
                onClick={onSave}
              />
              <ToolButton
                icon={<CloseIcon />}
                label="Exit"
                caption={bound ? "Esc closes" : "Esc discards"}
                shortcut="Esc"
                data-testid="sketch-exit"
                aria-label={
                  bound
                    ? "Exit sketch (saved)"
                    : "Exit sketch (discards unsaved entities)"
                }
                disabled={saving}
                onClick={exit}
              />
            </ToolGroup>
          </>
        ) : null}
      </div>

      {/* The inline offset-plane authoring panel hangs from the band during
          the plane-pick step, so the origin buttons stay one-click above. */}
      {mode === "plane" && offsetOpen && onAuthorOffsetPlane ? (
        <div className="absolute left-editor top-full z-20 mt-2">
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
        <div className="absolute left-editor top-full z-20 mt-2">
          <FacePickPrompt
            busy={authoringFace}
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
        <div className="absolute left-editor top-full z-20 mt-2 flex max-w-sm flex-col gap-2">
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
