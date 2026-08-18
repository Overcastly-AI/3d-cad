/**
 * Sketch-mode state (zustand) — plane pick, tool sequence, the local entity
 * buffer, and the constraint/selection layer. All geometry and constraint
 * transitions are the pure functions of `tools.ts` / `pick.ts` /
 * `constraints.ts`; this store only holds state.
 *
 * Persistence model (the live parametric loop): entities/constraints edits
 * bump `revision`; once the sketch is bound to a persisted feature
 * (`featureId`), `PartPage` debounce-saves every revision and feeds the
 * solved evaluate payload back through `adoptSolved` — which does NOT bump
 * `revision`, so the loop terminates.
 *
 * ## Sketch-local history (`past` / `future`, 2026-08-02)
 *
 * Founder report: *"there are no undo or redo buttons"* — true in the sketcher,
 * where they are needed most. The part-level History group undoes FEATURES
 * through the server's history ring, and a sketch in progress is not yet a
 * feature, so wiring the sketcher's buttons to THAT would have been the worst
 * outcome available: a control that looks like sketch undo and silently rolls
 * back the extrude you did before you opened the sketcher.
 *
 * So the sketcher gets its own stack, and it is a stack of the only state that
 * can be edited here: `entities` + `constraints` + `nextIdIndex`. Recording is
 * DERIVED, not hand-rolled per action — the store's `set` is wrapped, and any
 * transition that bumps `revision` (which is exactly the definition of a
 * persisted sketch edit, and already had to be right for saving to work) pushes
 * the pre-edit snapshot. A new action cannot forget to be undoable, and a
 * transient one (selection, tool, cursor, `adoptSolved`) cannot accidentally
 * become a history step.
 *
 * Undo/redo bump `revision` themselves, so a restored state flows through the
 * same debounced save + re-solve as any other edit — undo is not a UI-only
 * rewind that the server never hears about.
 */
import { create, type StateCreator } from "zustand";

import {
  applyConstraintAction,
  constraintEntityRefs,
  reconcileConstraints,
  toggleConstruction,
  type ConstraintAction,
  type DimensionCommit,
  type DimensionEditorTarget,
  type SketchConstraint,
  type SolvedDimension,
  type SolveInfo,
} from "./constraints";
import { toggleCornerPick, type CornerOp } from "./corner";
import {
  datumFrame,
  datumSafeSolve,
  DEFAULT_FRAME_HALF_HEIGHT_MM,
  groundDatums,
  isDatumId,
  pickWithDatums,
  selectionTouchesDatum,
  withDatums,
} from "./datum";
import {
  drawDimensionConstraints,
  drawDimensionFields,
  drawShapeOf,
  resizeDrawn,
  shapeRigidity,
  type DrawDimensionField,
  type DrawDimensionKey,
  type DrawDimensionValues,
  type DrawShape,
} from "./drawDimensions";
import { mirrorAxisFor, toggleMirrorTarget, type MirrorAxis } from "./mirror";
import { originIdentity } from "./origin";
import type { DatumPlaneName, Point2D, SketchPlaneSpec } from "./plane";
import {
  applyPick,
  toggleSelection,
  type PickMode,
  type SketchPick,
} from "./pick";
import {
  inferredCoincidents,
  resolveSnap,
  snapAnchorOf,
  type SnapAnchor,
  type SnapCandidate,
  type SnapResolution,
} from "./snap";
import {
  escapeAction,
  finishPlacement as finishPlacementSequence,
  placePoint,
  placesPoints,
  type SketchEntity,
  type SketchTool,
} from "./tools";

/**
 * Grid snap step (mm) the sketch opens with. The LIVE step is
 * `snapStepMm` on the store and is set with `setSnapStep` — this is only the
 * starting value, so a settings surface has one number to write to rather than
 * a literal to fight (UI-W5).
 */
export const DEFAULT_SNAP_STEP_MM = 1;

export type SketchMode = "off" | "plane" | "draw";

/** The two verbs that open a value editor, hence the two that can be ARMED. */
export type DimensionPickAction = "distance" | "radius";

/** What an armed dimension verb asks for, in the user's words. */
export const DIMENSION_PICK_HINT: Readonly<
  Record<DimensionPickAction, string>
> = {
  distance: "Click a line to dimension it.",
  radius: "Click a circle or arc to dimension it.",
};

/** How a picked entity is named back to the user ("That is a circle."). */
const ENTITY_KIND_LABEL: Readonly<Record<SketchEntity["kind"], string>> = {
  point: "a point",
  line: "a line",
  circle: "a circle",
  arc: "an arc",
  spline: "a spline",
};

/**
 * What to say when an ARMED dimension verb is handed the wrong thing (DIM-3).
 *
 * NOT the selection-first refusal — "Select one line to dimension." is the exact
 * sentence arming exists to eliminate, and while armed it is also false: the
 * user DID click, and "select" names a step this flow no longer has. Answering
 * a click with it reads as the dead end the fix was supposed to have removed.
 * So the reply names what was picked and repeats the standing instruction,
 * which is the truthful pair: this is not it, here is what is.
 *
 * THE FRAME IS THE EXCEPTION, and for a different reason: the origin and axes
 * are refused as a SUBJECT rather than for their kind (SKETCH-2 — the axis is
 * not yours to move), and that refusal stays true while armed. It is passed
 * through from the verb that owns it rather than re-derived here.
 */
const wrongPickHint = (
  armed: DimensionPickAction,
  pickedId: string,
  entities: readonly SketchEntity[],
  refusal: string | null,
): string => {
  if (isDatumId(pickedId)) return refusal ?? DIMENSION_PICK_HINT[armed];
  const picked = entities.find((entity) => entity.id === pickedId);
  // An id the buffer cannot resolve names nothing, so say nothing about it and
  // keep asking — better a repeated instruction than an invented noun.
  if (picked === undefined) return DIMENSION_PICK_HINT[armed];
  return `That is ${ENTITY_KIND_LABEL[picked.kind]}. ${DIMENSION_PICK_HINT[armed]}`;
};

/**
 * The size cells a just-drawn shape is offering (FB-16). Held apart from
 * `dimensionEdit`, which edits a dimension that already EXISTS on geometry the
 * user went back and selected: this one is part of the drawing gesture itself
 * and dies with it.
 */
export interface DrawDimensionDraft {
  shape: DrawShape;
  /** Entity ids the placement emitted, in emission order. */
  ids: string[];
  /** The gesture's two points (plane mm) — the frame a retyped value rebuilds in. */
  from: Point2D;
  to: Point2D;
  fields: DrawDimensionField[];
}

/**
 * One reversible sketch edit: everything an edit can change, and nothing else.
 * Selection, tool and cursor are deliberately absent — restoring them would
 * make undo move the user's hands as well as their geometry.
 */
export interface SketchSnapshot {
  entities: SketchEntity[];
  constraints: SketchConstraint[];
  nextIdIndex: number;
}

/** Deepest history the sketcher keeps (entity buffers are small; this is ample). */
export const SKETCH_HISTORY_LIMIT = 200;

const snapshotOf = (state: SketchState): SketchSnapshot => ({
  entities: state.entities,
  constraints: state.constraints,
  nextIdIndex: state.nextIdIndex,
});

/**
 * What an undo/redo hands back besides the geometry: every transient draft that
 * addressed the state being replaced. A pending placement anchored to an entity
 * that just left, or size cells describing a shape that no longer exists, would
 * be a live editor pointing at nothing.
 */
const CLEARED_BY_HISTORY = {
  pending: [] as Point2D[],
  // The anchors belong to the pending sequence that is being thrown away with
  // them; kept, they would bind the NEXT shape to a target the user aimed at
  // before the undo.
  snapAnchors: [] as SnapAnchor[],
  selection: [] as SketchPick[],
  hoverPick: null,
  selectedConstraint: null,
  dimensionEdit: null,
  dimensionPick: null,
  drawDimension: null,
  drawDimensionFocus: null,
  offsetDraft: null,
  hint: null,
} as const;

export interface SketchState {
  mode: SketchMode;
  /**
   * Chosen sketch plane (set on entering `draw`) — an origin datum OR an
   * authored offset datum feature. Null until a plane is picked.
   */
  plane: SketchPlaneSpec | null;
  tool: SketchTool;
  /** Points of the in-progress placement sequence (plane mm, snapped). */
  pending: Point2D[];
  /**
   * The addressable snaps this placement sequence has spent so far (SNAP-3).
   * Accumulated per click and cashed in when the sequence emits geometry, then
   * cleared: the click that most needs to be recorded — a line's start, a
   * rectangle's first corner — happens before any entity exists to constrain,
   * so the intent has to be carried forward rather than re-derived later.
   */
  snapAnchors: SnapAnchor[];
  /** Locally buffered entities; adopt solved positions once persisted. */
  entities: SketchEntity[];
  /** Constraints authored this session (persisted with the entities). */
  constraints: SketchConstraint[];
  /**
   * Has the USER authored a constraint — a verb from the strip, a typed
   * dimension, or a re-opened sketch that already carried some — as opposed to
   * the draw authoring one for them?
   *
   * TWO features arrived at this flag independently, which is the argument for
   * it. RECT-1 made every drawn rectangle carry its rigidity set; SNAP-3 made
   * every corner snapped onto something carry an inferred coincident. Snapping
   * is ON by default and endpoints outrank everything, so between them nearly
   * every real draw now authors constraints nobody asked for by name.
   *
   * `PartPage`'s live-save gate used to read `constraints.length > 0` as "this
   * sketch is worth binding", and binding also retires the "Discard N unsaved
   * entities" exit confirm. Left alone, a rectangle would bind the instant it
   * was drawn (while a line would not), and any profile would bind the moment
   * two corners met — changing what Escape and Exit MEAN because of an action
   * the user never read as constraining anything. That is the FB-13 class of
   * ambiguous exit, and CLAUDE.md's flow rule forbids it.
   *
   * So: constraints the TOOL infers do not bind; constraints the USER asks for
   * do. The inferred ones still persist, glyph, and count in the strip's
   * "N applied" — they are real, they are just not a decision to start saving.
   * Whether drawing alone SHOULD auto-bind is a real product question, filed as
   * RECT-2 rather than decided here.
   */
  userConstrained: boolean;
  /** Next sketch-local id index (`e1`, `e2`, …). */
  nextIdIndex: number;
  /** GRID snap toggle (G). Entity snapping is always live — Ctrl/Cmd suppresses. */
  snapEnabled: boolean;
  /** Live grid step (mm) — configurable, see `DEFAULT_SNAP_STEP_MM`. */
  snapStepMm: number;
  /** Ctrl/Cmd held: every snap off, freehand placement (UI-W5 polarity). */
  snapSuppressed: boolean;
  /** Shift held: the aim is locked to an axis through the placement anchor. */
  axisLock: boolean;
  /**
   * What the current aim actually took — endpoint / midpoint / centre /
   * intersection / tangent / perpendicular / axis lock — so the viewport can
   * NAME it before the click commits. Null for a grid or freehand point.
   */
  snapCandidate: SnapCandidate | null;
  /**
   * The last RAW (unsnapped) pointer point and its px→mm tolerance. Held so a
   * modifier pressed while the pointer is stationary re-resolves the aim
   * immediately, instead of lying until the next mouse move.
   */
  aimRaw: Point2D | null;
  aimToleranceMm: number;
  /** Pointer position in plane mm, already snapped; null when off-plane. */
  cursor: Point2D | null;
  /** Plane under the pointer / focused cell during plane pick. */
  hoveredPlane: DatumPlaneName | null;
  /**
   * Half-height (mm) of the frame the sketch camera parks in — the scene's own
   * `sketchFrameHalfHeightMm`, reported in by `setDatumFrame`. It sizes the
   * origin ring and the axes, and therefore the region that PICKS them
   * (`sketch/datum.ts`): the pick geometry is derived from the same number that
   * draws the ink, so what you aim at is what you hit.
   */
  datumFrameHalfMm: number;
  /** Current selection (select tool): entities and defining points. */
  selection: SketchPick[];
  /** Pick under the pointer (select tool) — hover highlight. */
  hoverPick: SketchPick | null;
  /** Selected constraint glyph (index into `constraints`), for Delete. */
  selectedConstraint: number | null;
  /** Open inline dimension editor, or null. */
  dimensionEdit: DimensionEditorTarget | null;
  /**
   * A DIMENSION VERB ARMED WITH NOTHING TO DIMENSION — the founder's
   * "I still cannot click dimension and actually have it assign a dimension"
   * (2026-08-14), which reproduced as a dead end rather than a wrong value.
   *
   * The dimension verbs were selection-first ONLY: with nothing selected the
   * strip's Dimension > Distance printed "Select one line to dimension." and
   * stopped. That instruction cannot be followed from where it appears, because
   * a draw tool stays armed after it draws (Fusion does the same) — so the
   * click the user makes to "select the line" is consumed as the first corner
   * of the next rectangle, the readout keeps saying "nothing selected", and the
   * verb keeps refusing. Measured end to end in a browser: draw a rectangle,
   * click a side, Dimension > Distance -> selection "nothing selected",
   * dimension editor count 0.
   *
   * Armed, the verb becomes a TOOL: the draw tool is dropped, the next entity
   * click opens that entity's dimension editor, and Escape disarms. The verb
   * proposes, the user disposes (CLAUDE.md flow rule) instead of dead-ending.
   *
   * ITS ONLY SURFACE IS `hint` (DIM-3) — there is no armed chip, no cursor
   * change, nothing else to read. That makes "armed" and "silent" a broken
   * pair, so the two are held apart by an invariant rather than by care at each
   * call site: see `withArmedPrompt`.
   */
  dimensionPick: DimensionPickAction | null;
  /**
   * The size cells the shape under the cursor is offering (FB-16), or null.
   * Set by the placement that emitted the shape; cleared by anything that ends
   * the drawing gesture (a new placement, a tool change, Escape, exit).
   */
  drawDimension: DrawDimensionDraft | null;
  /**
   * Which draw-time cell has focus — the scene draws that dimension's witness
   * callout, so the number being typed always names its own edge.
   */
  drawDimensionFocus: DrawDimensionKey | null;
  /** Persisted feature this session is bound to (null = unsaved). */
  featureId: string | null;
  /** Monotonic edit counter — the sync loop persists every bump. */
  revision: number;
  /**
   * Sketch-local history (module note above): states BEFORE each edit, oldest
   * first. `past.length > 0` is the honest `canUndo` — it is the stack itself,
   * not a claim about it.
   */
  past: SketchSnapshot[];
  /** States undone out of `past`, ready to be redone; cleared by any new edit. */
  future: SketchSnapshot[];
  /** Latest solve feedback for the bound feature (DRO + diagnostics). */
  solve: SolveInfo | null;
  /**
   * Per-dimension solve readouts from the last evaluate, keyed off
   * `constraint_index` (a driving dim's evaluated value / a driven dim's
   * measured value). Empty until the first solve; drives the glyph labels so an
   * expression `width/2` shows as its resolved `10`.
   */
  solvedDimensions: SolvedDimension[];
  /** Transient strip hint (invalid constraint action, duplicates, …). */
  hint: string | null;
  /**
   * A pending trim/extend the scene armed on a target click; PartPage owns the
   * network effect that consumes it (the store stays side-effect-free). The
   * `nonce` lets that effect fire exactly once per request.
   */
  edit: {
    op: "trim" | "extend";
    target: string;
    pick: Point2D;
    nonce: number;
  } | null;
  /** True while a geometry edit (trim/extend/offset) is in flight (blocks re-entry). */
  editBusy: boolean;
  /** Transient confirmation after an edit ("Trimmed. 2 constraints removed."). */
  editNote: string | null;
  /**
   * The target whose signed offset distance the inline editor is collecting.
   * Set when the Offset tool clicks a curve; cleared when the editor arms the
   * request (`armOffset`) or is dismissed (`cancelOffset`).
   */
  offsetDraft: { target: string } | null;
  /**
   * A pending offset the editor armed once the user confirmed a distance;
   * PartPage owns the network effect that consumes it (the store stays
   * side-effect-free). The `nonce` lets that effect fire exactly once. Unlike
   * `edit`, offset ADDS geometry — the result is APPENDED, never swapped.
   */
  offset: { target: string; distance: number; nonce: number } | null;
  /**
   * The Mirror tool's two-phase draft: first collect the entities to reflect
   * (`targets`), then pick the axis line. Null unless the Mirror tool is armed.
   * Held separately from `selection` so the general select grain (points +
   * curves) never mixes with mirror's whole-entity picks.
   */
  mirror: { phase: "targets" | "axis"; targets: string[] } | null;
  /**
   * A pending mirror the axis pick armed; PartPage owns the network effect that
   * consumes it (the store stays side-effect-free), reads the live entity list,
   * and appends the reflected copies. Like `offset` (and unlike `edit`), mirror
   * ADDS geometry. The `nonce` fires the request exactly once.
   */
  mirrorRequest: { targets: string[]; axis: MirrorAxis; nonce: number } | null;
  /**
   * The Fillet/Chamfer tool's corner draft: the two line legs being collected
   * (`picks`, capped at two). Once both are held the inline value editor opens
   * (radius for a fillet, setback for a chamfer). Null unless a corner tool is
   * armed. Held apart from `selection` so the corner's whole-line picks never
   * mix with the general point-first select grain.
   */
  corner: { op: CornerOp; picks: string[] } | null;
  /**
   * A pending corner op the value editor armed; PartPage owns the network
   * effect that consumes it (the store stays side-effect-free), reads the live
   * entity list, and REPLACES it with the rewritten result. Unlike offset/mirror
   * (which append), a corner rewrites in place — like `edit` (trim/extend). The
   * `nonce` fires the request exactly once.
   */
  cornerRequest: {
    op: CornerOp;
    a: string;
    b: string;
    value: number;
    nonce: number;
  } | null;

  /** Enter sketch mode at the plane-pick step. */
  begin: () => void;
  /**
   * RE-OPEN an already persisted sketch feature (SKETCH-1). The sibling of
   * `begin`, and the difference is the whole point: `begin` opens an EMPTY
   * session at the plane-pick step, so a sketch that had already been saved
   * could only ever be drawn once — every driving dimension in a part was
   * write-once, and the solver, the expressions and the topological-naming
   * survival were reachable on the first pass only.
   *
   * `mode` goes straight to `draw` because the plane is already chosen (there
   * is nothing to pick), and `featureId` carries the EXISTING id, which is what
   * makes the next save a PATCH of this feature rather than a POST minting a
   * second one — `persistBuffer` already branches on exactly that.
   */
  beginEdit: (
    featureId: string,
    plane: SketchPlaneSpec,
    entities: readonly SketchEntity[],
    constraints: readonly SketchConstraint[],
  ) => void;
  /** One-click: sketch on one of the three origin datums (the common case). */
  choosePlane: (plane: DatumPlaneName) => void;
  /** Sketch on an already-resolved plane spec (origin OR authored offset). */
  choosePlaneSpec: (spec: SketchPlaneSpec) => void;
  setTool: (tool: SketchTool) => void;
  setHoveredPlane: (plane: DatumPlaneName | null) => void;
  setCursor: (point: Point2D | null) => void;
  /**
   * Report the camera's framing (mm) so the sketch frame's PICK region is
   * derived from the same number that draws its ink (`datumFrameHalfMm`).
   */
  setDatumFrame: (frameHalfHeightMm: number) => void;
  /** Toggle the GRID snap (G). Entity snapping is unaffected — it is always on. */
  toggleSnap: () => void;
  /** Set the grid step in mm (a settings-surface seam; <= 0 is rejected). */
  setSnapStep: (stepMm: number) => void;
  /** Record the live modifier state and re-resolve the aim under it. */
  setSnapModifiers: (modifiers: {
    suppressed: boolean;
    axisLock: boolean;
  }) => void;
  /**
   * Resolve a raw plane point into the point a click would take, recording the
   * cursor and the named snap candidate. THE one aim path: hover and click both
   * go through it, so what the mark promises is what the click places.
   */
  aim: (
    point: Point2D,
    toleranceMm: number,
    modifiers: { suppressed: boolean; axisLock: boolean },
  ) => Point2D;
  /** Place the next point of the active tool's sequence. */
  placeAt: (point: Point2D) => void;
  /**
   * Commit an open placement sequence (Enter / double-click) — the spline's
   * finish gesture. A no-op for tools that self-finish on a click.
   */
  finishPlacement: () => void;
  /**
   * Select-tool click at a raw (unsnapped) plane point. A plain click REPLACES
   * the selection; Shift or Ctrl/Cmd ADDS to it (`applyPick`, FB-14). `mode`
   * is for a caller that reads the modifier off the click event itself; when
   * omitted the live modifier state the aim already tracks decides.
   */
  selectAt: (point: Point2D, toleranceMm: number, mode?: PickMode) => void;
  /**
   * Toggle one exact pick into/out of the selection — the DOM fit-point
   * handles' path (a keyboard/pointer surface that names the pick directly,
   * rather than the coordinate raycast `selectAt` does). Stays a TOGGLE under
   * a plain click, unlike `selectAt`: those handles are `aria-pressed` buttons
   * that say what they hold, so nothing is hidden from the user — and they are
   * the modifier-free multi-select path for a keyboard-only user.
   */
  togglePick: (pick: SketchPick) => void;
  setHoverPick: (pick: SketchPick | null) => void;
  clearSelection: () => void;
  /** Apply a constraint verb to the selection (H/V/X/C add; D/R edit). */
  applyConstraint: (action: ConstraintAction) => void;
  /** Toggle the selected entities between profile and construction (N). */
  toggleConstruction: () => void;
  /**
   * Arm a trim/extend on the target under the pick (raw plane mm). `target`
   * null means the click missed every curve — a hint, no request.
   */
  requestEdit: (
    op: "trim" | "extend",
    target: string | null,
    pick: Point2D,
  ) => void;
  /** Apply a trim/extend result: swap the entity set, reconcile constraints. */
  applyEditResult: (
    op: "trim" | "extend",
    entities: readonly SketchEntity[],
  ) => void;
  /** Fail the in-flight edit with a surfaced message. */
  failEdit: (message: string) => void;
  /**
   * Arm the inline signed-distance editor on the target under the pick.
   * `target` null means the click missed every curve — a hint, no editor.
   */
  beginOffset: (target: string | null) => void;
  /** Confirm the offset editor with a validated signed distance (mm). */
  armOffset: (distanceMm: number) => void;
  /** Dismiss the offset editor without offsetting. */
  cancelOffset: () => void;
  /** Apply an offset result: APPEND the new offset entity/entities, re-solve. */
  applyOffsetResult: (entities: readonly SketchEntity[]) => void;
  /** Fail the in-flight offset with a surfaced message. */
  failOffset: (message: string) => void;
  /**
   * Toggle an entity into/out of the mirror target set (targets phase).
   * `id` null means the click missed every curve — a hint, no change.
   */
  toggleMirrorTarget: (id: string | null) => void;
  /** Advance the mirror draft from collecting targets to picking the axis. */
  advanceMirror: () => void;
  /**
   * Pick the axis line and arm the mirror (axis phase). `id` null (a miss) or a
   * non-line entity hints instead of firing; a valid line arms one request.
   */
  pickMirrorAxis: (id: string | null) => void;
  /** Apply a mirror result: APPEND the reflected copies, re-solve, re-arm. */
  applyMirrorResult: (entities: readonly SketchEntity[]) => void;
  /** Fail the in-flight mirror with a surfaced message (axis phase survives). */
  failMirror: (message: string) => void;
  /**
   * Add/remove a line leg from the corner pick set (max two). `id` null means
   * the click missed every curve, and a non-line leg pre-empts the backend's
   * `sketch_unsupported_entity` — both hint instead of picking.
   */
  pickCornerLine: (id: string | null) => void;
  /** Confirm the corner value editor with a validated radius/setback (mm). */
  armCorner: (valueMm: number) => void;
  /** Dismiss the corner value editor, clearing the picks (tool survives). */
  cancelCorner: () => void;
  /** Apply a corner result: SWAP the rewritten entity set, reconcile, re-arm. */
  applyCornerResult: (entities: readonly SketchEntity[]) => void;
  /** Fail the in-flight corner op; the picks + editor survive for a retry. */
  failCorner: (message: string) => void;
  /**
   * Commit the draw-time size cells (Enter): rewrite the drawn geometry to the
   * typed values and record them as driving dimensions. Typing nothing is a
   * valid outcome — the draft closes and the shape stays exactly as drawn.
   */
  commitDrawDimensions: (values: DrawDimensionValues) => void;
  /** Dismiss the draw-time size cells, keeping the shape undimensioned. */
  dismissDrawDimensions: () => void;
  /** Report which draw-time cell has focus (null = none). */
  focusDrawDimension: (key: DrawDimensionKey | null) => void;
  /** Open the editor for an existing dimension constraint (glyph click). */
  editDimension: (constraintIndex: number) => void;
  /**
   * Commit the open dimension editor: a positive `value_mm`, an optional
   * `expression` (driving only) that supersedes it, an optional reference
   * `name`, and the driving/driven flag.
   */
  commitDimension: (commit: DimensionCommit) => void;
  cancelDimension: () => void;
  selectConstraint: (index: number | null) => void;
  removeConstraint: (index: number) => void;
  /**
   * Undo one SKETCH edit — the entity you just drew, the constraint you just
   * applied, the trim you just made. Scoped to this sketch session and to
   * nothing else: it can never reach a feature (see the module note). A no-op
   * with an empty `past`, or while a geometry edit is in flight.
   */
  undo: () => void;
  /** Redo the last undone sketch edit (cleared the moment you draw again). */
  redo: () => void;
  /** Bind the session to its persisted feature (first save). */
  bind: (featureId: string) => void;
  /**
   * Feed solved geometry + diagnosis back in (never bumps `revision`).
   * `dimensions`, when provided, replaces the per-dimension readouts; omit it
   * (error paths) to keep the last-good readouts.
   */
  adoptSolved: (
    entities: readonly SketchEntity[] | null,
    solve: SolveInfo | null,
    dimensions?: readonly SolvedDimension[],
  ) => void;
  /**
   * Escape cascade: editor → placement → tool → selection → and then STOP.
   * Escape leaves the sketch only when there is no work to lose (`escapeAction`
   * `unstarted`); with entities drawn it answers with a hint naming the chip
   * that finishes (FB-13).
   *
   * THE ONLY CASCADE (ESC-2). Every Escape — keyboard or chip — routes here;
   * no caller re-derives the rung with its own `escapeAction(…)` call, because
   * the last rung's MEANING lives in the mapping and not in the verb. Here
   * `"exit"` is a fresh session: it DISCARDS, which is safe precisely because
   * `unstarted` means there is nothing to discard. `PartPage` used to map the
   * same verb to `finishSketch()`, which SAVES; the two agreed only by the
   * accident of an omitted default argument, which is FB-13 ("a key that
   * sometimes saves and sometimes discards") waiting for someone to pass it.
   */
  escape: () => void;
  /** Leave sketch mode, discarding the local buffer. */
  exit: () => void;
}

const INITIAL = {
  mode: "off" as SketchMode,
  plane: null,
  tool: "select" as SketchTool,
  pending: [],
  snapAnchors: [],
  entities: [],
  constraints: [],
  userConstrained: false,
  nextIdIndex: 1,
  snapEnabled: true,
  snapStepMm: DEFAULT_SNAP_STEP_MM,
  snapSuppressed: false,
  axisLock: false,
  snapCandidate: null,
  aimRaw: null,
  aimToleranceMm: 0,
  cursor: null,
  hoveredPlane: null,
  datumFrameHalfMm: DEFAULT_FRAME_HALF_HEIGHT_MM,
  selection: [],
  hoverPick: null,
  selectedConstraint: null,
  dimensionEdit: null,
  dimensionPick: null,
  drawDimension: null,
  drawDimensionFocus: null,
  featureId: null,
  revision: 0,
  past: [],
  future: [],
  solve: null,
  solvedDimensions: [],
  hint: null,
  edit: null,
  editBusy: false,
  editNote: null,
  offsetDraft: null,
  offset: null,
  mirror: null,
  mirrorRequest: null,
  corner: null,
  cornerRequest: null,
};

/**
 * A fresh session that PRESERVES the snap preferences. Grid on/off and the
 * grid step are settings the user chose; wiping them on exit would silently
 * undo a choice, so they survive `begin` / `exit` / the Escape cascade.
 */
const freshSession = (state: SketchState) => ({
  ...INITIAL,
  snapEnabled: state.snapEnabled,
  snapStepMm: state.snapStepMm,
});

/**
 * The first sketch-local id index free above a loaded entity set. Ids are minted
 * `e1`, `e2`, … (`tools.entityId`), so a re-opened sketch has to resume ABOVE
 * the highest one it loaded: resuming at 1 — what a fresh session gives a
 * brand-new sketch — would mint `e1` a second time, and every id-keyed consumer
 * (constraint refs, `adoptSolved`'s solved-by-id map, picks, the solver's own
 * entity table) would then address two entities at once.
 *
 * Anything that is not `e<digits>` is ignored rather than guessed at: the index
 * only has to be free, and a foreign id shape contributes no claim on one.
 */
const nextIdIndexAfter = (entities: readonly SketchEntity[]): number => {
  let highest = 0;
  for (const entity of entities) {
    const match = /^e(\d+)$/.exec(entity.id);
    if (match === null) continue;
    highest = Math.max(highest, Number(match[1]));
  }
  return highest + 1;
};

/**
 * Does this click ADD to the selection, or replace it (FB-14)?
 *
 * Shift or Ctrl/Cmd adds. The store already holds both, live: `axisLock` is
 * Shift and `snapSuppressed` is Ctrl/Cmd, tracked from every key event
 * (`setSnapModifiers`) and every pointer move (`aim`). Both are PLACEMENT
 * modifiers — the axis lock pivots on a placement anchor, the suppressor turns
 * the snap magnet off — and the select tool places nothing and takes the raw
 * point, so reading them here collides with no other binding. A caller holding
 * the click event can pass the mode explicitly instead (`selectAt`'s third
 * argument), which is exact rather than one repaint fresh.
 */
const pickModeOf = (state: SketchState): PickMode =>
  state.axisLock || state.snapSuppressed ? "add" : "replace";

/** The one aim resolution — shared by `aim` and the modifier re-resolve. */
function resolveAim(
  state: SketchState,
  point: Point2D,
  toleranceMm: number,
  modifiers: { suppressed: boolean; axisLock: boolean },
): SnapResolution {
  // A tool that PLACES gets both snap sources; one that picks gets neither.
  const placing = placesPoints(state.tool);
  return resolveSnap({
    point,
    entities: state.entities,
    // The placement anchor: the last point of the open sequence. Tangent and
    // perpendicular are defined relative to where the curve comes FROM, and
    // the axis lock pivots on it.
    from: state.pending[state.pending.length - 1] ?? null,
    toleranceMm,
    gridStepMm: state.snapEnabled ? state.snapStepMm : 0,
    suppressed: modifiers.suppressed,
    axisLock: modifiers.axisLock,
    entitySnap: placing,
    // The plane's own frame, named by what its zero IS — a datum's fixed zero
    // or a seated face's area centroid (`sketch/origin.ts`).
    originSnap: placing ? { label: originIdentity(state.plane).label } : null,
  });
}

/** The `set` signature every action in this store uses (no `replace`). */
type SketchSet = (
  partial:
    Partial<SketchState> | ((state: SketchState) => Partial<SketchState>),
) => void;

/**
 * History recorder. Wraps the store's `set` so that any transition which BUMPS
 * `revision` — the existing, already-load-bearing definition of "a sketch edit
 * the server needs to hear about" — pushes the pre-edit state onto `past`.
 *
 * Derived rather than hand-rolled in each of the fifteen mutating actions: a
 * new action becomes undoable by construction, and a transient one (selection,
 * tool, cursor, `adoptSolved`) can never become a history step by accident.
 *
 * Two transitions are NOT edits and are skipped:
 *   · `revision` unchanged or RESET — `exit` / the Escape cascade zero the
 *     counter through `freshSession`, which is the opposite of an edit;
 *   · a set that rewrites `past`/`future` itself — that IS the history move
 *     (undo/redo), and recording it would push a step per undo, leaving a stack
 *     that can never empty.
 */
const withSketchHistory =
  (
    creator: (set: SketchSet, get: () => SketchState) => SketchState,
  ): StateCreator<SketchState> =>
  (rawSet, get) =>
    creator((partial) => {
      const before = get();
      rawSet(partial);
      const after = get();
      if (after.revision <= before.revision) return;
      if (after.past !== before.past || after.future !== before.future) return;
      const past = [...before.past, snapshotOf(before)];
      rawSet({
        past:
          past.length > SKETCH_HISTORY_LIMIT
            ? past.slice(past.length - SKETCH_HISTORY_LIMIT)
            : past,
        // A new edit forks the timeline: what was undone is unreachable now.
        future: [],
      });
    }, get);

/**
 * ARMED IS NEVER SILENT (DIM-3). `dimensionPick` has no surface of its own: the
 * hint is the only thing on screen saying the next canvas click will open a
 * dimension editor rather than select something. Clearing the hint is what an
 * ordinary action DOES when its own message is over — `selectConstraint` and
 * `togglePick` both did, correctly, and both left the verb armed and silent, so
 * the click after them opened an editor with no visible cause.
 *
 * Restoring the prompt at those two call sites would have fixed the two we
 * found and not the third. This is `withSketchHistory`'s argument again: a rule
 * that has to be remembered at every site will be forgotten at one, and the
 * cost here is a UI state that cannot be explained from the screen. So it is an
 * INVARIANT, re-established after every transition — "armed with no hint" is
 * not a state this store can be left in, by any action, present or future.
 *
 * Two things it deliberately does not do: it never overwrites a hint (a site
 * with something more specific to say — the wrong-kind pick — keeps its own),
 * and it never fires for a site that DISARMS, because clearing `dimensionPick`
 * and the prompt together is the arming ending, not going quiet.
 */
const withArmedPrompt =
  (creator: (set: SketchSet, get: () => SketchState) => SketchState) =>
  (set: SketchSet, get: () => SketchState): SketchState =>
    creator((partial) => {
      set(partial);
      const after = get();
      if (after.dimensionPick === null || after.hint !== null) return;
      set({ hint: DIMENSION_PICK_HINT[after.dimensionPick] });
    }, get);

/** Every action, over the recording `set` (never the raw one). */
const createSketchState = (
  set: SketchSet,
  get: () => SketchState,
): SketchState => ({
  ...INITIAL,

  begin: () => set((state) => ({ ...freshSession(state), mode: "plane" })),
  beginEdit: (featureId, plane, entities, constraints) =>
    set((state) => ({
      ...freshSession(state),
      mode: "draw",
      featureId,
      plane,
      entities: [...entities],
      constraints: [...constraints],
      // A sketch being RE-OPENED is already bound to a feature, so the live
      // save gate is moot here — but the flag has to be true anyway, or
      // re-entering a constrained sketch would read as never-constrained.
      userConstrained: constraints.length > 0,
      // Resume the id counter above what was loaded (never re-mint `e1`).
      nextIdIndex: nextIdIndexAfter(entities),
    })),
  choosePlane: (plane) =>
    set({
      mode: "draw",
      plane: { kind: "origin", base: plane },
      hoveredPlane: null,
      cursor: null,
    }),
  choosePlaneSpec: (spec) =>
    set({ mode: "draw", plane: spec, hoveredPlane: null, cursor: null }),
  setTool: (tool) =>
    set({
      tool,
      pending: [],
      // Abandoning the sequence abandons the intents it collected.
      snapAnchors: [],
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      dimensionEdit: null,
      // Reaching for another tool abandons an armed dimension pick, the same
      // way it abandons a mirror or corner draft.
      dimensionPick: null,
      drawDimension: null,
      drawDimensionFocus: null,
      offsetDraft: null,
      // Arming Mirror opens its target-collection phase; any other tool clears
      // the draft. The armed `mirrorRequest` is left alone — its nonce guards a
      // late in-flight response from re-firing.
      mirror: tool === "mirror" ? { phase: "targets", targets: [] } : null,
      // Fillet/Chamfer open a fresh two-line corner draft; any other tool clears
      // it. The armed `cornerRequest` is left alone (nonce-guarded), like mirror.
      corner:
        tool === "fillet" || tool === "chamfer"
          ? { op: tool, picks: [] }
          : null,
      hint: null,
      editNote: null,
    }),
  setHoveredPlane: (hoveredPlane) => set({ hoveredPlane }),
  // Leaving the plane drops the aim entirely: a mark left behind would name a
  // snap for a cursor that is no longer there.
  setCursor: (cursor) =>
    set(
      cursor === null
        ? { cursor: null, snapCandidate: null, aimRaw: null }
        : { cursor },
    ),
  setDatumFrame: (frameHalfHeightMm) => {
    if (!Number.isFinite(frameHalfHeightMm) || frameHalfHeightMm <= 0) return;
    if (get().datumFrameHalfMm === frameHalfHeightMm) return;
    set({ datumFrameHalfMm: frameHalfHeightMm });
  },
  toggleSnap: () => set((state) => ({ snapEnabled: !state.snapEnabled })),
  setSnapStep: (stepMm) => {
    if (!Number.isFinite(stepMm) || stepMm <= 0) return;
    set({ snapStepMm: stepMm });
  },

  setSnapModifiers: ({ suppressed, axisLock }) => {
    const state = get();
    if (state.snapSuppressed === suppressed && state.axisLock === axisLock) {
      return;
    }
    // Re-resolve from the last raw point so a modifier pressed with the mouse
    // held still takes effect NOW — the mark must never outlive its truth.
    if (state.aimRaw === null) {
      set({ snapSuppressed: suppressed, axisLock });
      return;
    }
    const resolution = resolveAim(state, state.aimRaw, state.aimToleranceMm, {
      suppressed,
      axisLock,
    });
    set({
      snapSuppressed: suppressed,
      axisLock,
      cursor: resolution.at,
      snapCandidate: resolution.candidate,
    });
  },

  aim: (point, toleranceMm, modifiers) => {
    const resolution = resolveAim(get(), point, toleranceMm, modifiers);
    set({
      cursor: resolution.at,
      snapCandidate: resolution.candidate,
      snapSuppressed: modifiers.suppressed,
      axisLock: modifiers.axisLock,
      aimRaw: point,
      aimToleranceMm: toleranceMm,
    });
    return resolution.at;
  },

  placeAt: (point) => {
    const {
      tool,
      pending,
      snapAnchors,
      nextIdIndex,
      entities,
      constraints,
      revision,
      snapCandidate,
      datumFrameHalfMm,
    } = get();
    const result = placePoint(tool, pending, point, nextIdIndex);
    const drawn = result.entities.length > 0;

    // AUTOMATIC COINCIDENT ON SNAP (SNAP-3, and SNAP-2 with it).
    //
    // The aim that produced `point` is still on the store — `placeAt` is only
    // ever called with `aim()`'s own return — so the address the click took its
    // coordinate from is available HERE, at the one moment it is unambiguous.
    // Recovering it later would mean guessing from a coordinate, which is the
    // guess this closes.
    //
    // A REJECTED placement banks nothing. `placePoint` refuses a degenerate
    // shape (zero-area rectangle, zero-length line, a spline's repeated fit
    // point) by handing back the sequence untouched; treating that click as an
    // anchor would leave a stale intent to be cashed in by whatever the user
    // draws next.
    const consumed = drawn || result.pending.length !== pending.length;
    const anchor = consumed ? snapAnchorOf(snapCandidate, point) : null;
    const anchors = anchor === null ? snapAnchors : [...snapAnchors, anchor];

    const inferred = drawn
      ? inferredCoincidents(anchors, result.entities, constraints)
      : [];
    const placed = drawn ? [...entities, ...result.entities] : entities;
    // Snapping to the plane's zero references a datum that may not be in the
    // buffer yet; grounding it here is the same call `applyConstraint` makes,
    // so the origin is materialised and PINNED by exactly one code path.
    // Without the pin a coincident to the origin is satisfiable by moving the
    // origin, which would take the sketch's zero with it.
    const grounded =
      inferred.length === 0
        ? null
        : groundDatums(
            placed,
            inferred.flatMap(constraintEntityRefs),
            datumFrame(datumFrameHalfMm),
          );

    // A new placement supersedes the last shape's size cells: anything typed
    // into them and not committed is gone, the same way moving on abandons a
    // half-typed value anywhere else. The cells stay visible right up to that
    // moment, so nothing vanishes without the user acting.
    const shape = drawShapeOf(tool);
    const from = pending[0];
    // RECT-1 — the shape is held together AT THE DRAW, not at the first typed
    // dimension. A rectangle is a closed axis-aligned profile the moment it
    // exists; deferring its corner coincidences left the ordinary untyped
    // gesture producing four disconnected lines that tear apart on the first
    // re-drive. This is the ONLY author of the rigidity set — see the note in
    // drawDimensions.ts for why emitting it again at commit would report an
    // ordinary rectangle as over-constrained.
    const rigidity =
      drawn && shape !== null
        ? shapeRigidity(
            shape,
            result.entities.map((entity) => entity.id),
          )
        : [];
    /** The snap's inferred coincidents plus whatever datum they had to ground. */
    const authored =
      grounded === null ? [] : [...inferred, ...grounded.constraints];
    set({
      pending: result.pending,
      // Cashed in, or carried to the click that finishes the shape.
      snapAnchors: drawn ? [] : anchors,
      nextIdIndex: result.nextIdIndex,
      entities: grounded?.entities ?? placed,
      // TWO authors, ONE order, and it is deliberate: the shape's own rigidity
      // (RECT-1) describes what the thing IS, the inferred coincident (SNAP-3)
      // relates it to what was already there, and the datum pins ride last
      // because they are the frame's bookkeeping rather than anybody's intent.
      // Neither author can produce what the other does, so they compose rather
      // than compete — and each still has exactly one call site.
      constraints:
        rigidity.length + authored.length === 0
          ? constraints
          : [...constraints, ...rigidity, ...authored],
      // `userConstrained` is deliberately NOT set by either author: this is the
      // tool recording the shape it drew and the target the user aimed at, not
      // the user asking for a relation. Binding the sketch here would retire
      // the unsaved-work exit confirm at a moment the user did not choose (see
      // the field).
      revision: drawn ? revision + 1 : revision,
      drawDimension:
        drawn && shape !== null && from !== undefined
          ? {
              shape,
              ids: result.entities.map((entity) => entity.id),
              from,
              to: point,
              fields: drawDimensionFields(
                shape,
                from,
                point,
                result.entities.map((entity) => entity.id),
              ),
            }
          : null,
      drawDimensionFocus: null,
    });
  },

  commitDrawDimensions: (values) => {
    const { drawDimension, entities, constraints, revision } = get();
    if (drawDimension === null) return;
    const { shape, ids, from, to, fields } = drawDimension;
    // Only positive, finite values for cells this draft actually offers; a
    // cell left alone is not a dimension, it is a decision to leave it free.
    const typed: DrawDimensionValues = {};
    for (const field of fields) {
      const value = values[field.key];
      if (value !== undefined && Number.isFinite(value) && value > 0) {
        typed[field.key] = value;
      }
    }
    const added = drawDimensionConstraints(shape, ids, fields, typed);
    if (added.length === 0) {
      set({ drawDimension: null, drawDimensionFocus: null });
      return;
    }
    set({
      entities: resizeDrawn(shape, ids, from, to, entities, typed),
      constraints: [...constraints, ...added],
      // A typed size IS the user constraining the sketch.
      userConstrained: true,
      revision: revision + 1,
      drawDimension: null,
      drawDimensionFocus: null,
      hint: null,
    });
  },

  dismissDrawDimensions: () =>
    set({ drawDimension: null, drawDimensionFocus: null }),

  focusDrawDimension: (drawDimensionFocus) => set({ drawDimensionFocus }),

  finishPlacement: () => {
    const {
      tool,
      pending,
      snapAnchors,
      nextIdIndex,
      entities,
      constraints,
      revision,
      datumFrameHalfMm,
    } = get();
    const result = finishPlacementSequence(tool, pending, nextIdIndex);
    if (result.entities.length === 0) return;
    // The spline's own commit gesture (Enter / double-click) is the other way a
    // sequence emits geometry, so it cashes its anchors in through the SAME
    // inference — a fit point snapped onto a corner stays on that corner.
    const inferred = inferredCoincidents(
      snapAnchors,
      result.entities,
      constraints,
    );
    const placed = [...entities, ...result.entities];
    const grounded =
      inferred.length === 0
        ? null
        : groundDatums(
            placed,
            inferred.flatMap(constraintEntityRefs),
            datumFrame(datumFrameHalfMm),
          );
    set({
      pending: result.pending,
      snapAnchors: [],
      nextIdIndex: result.nextIdIndex,
      entities: grounded?.entities ?? placed,
      constraints:
        grounded === null
          ? constraints
          : [...constraints, ...inferred, ...grounded.constraints],
      revision: revision + 1,
    });
  },

  selectAt: (point, toleranceMm, mode) => {
    const state = get();
    // The sketch frame picks like any other geometry (SKETCH-2): the origin
    // ring and the two axes are candidates here, ordered behind whatever the
    // user drew. Everything downstream — the readout, the constraint verbs, the
    // Escape cascade — then treats a datum pick as an ordinary member of
    // `selection`, which is the whole reason this is a picking change and not a
    // new mode.
    const pickMode = mode ?? pickModeOf(state);
    const candidates = pickWithDatums(
      state.entities,
      point,
      toleranceMm,
      datumFrame(state.datumFrameHalfMm),
      pickMode,
      // The standing selection is part of the question: a plain click whose
      // only candidate is the invisible axis cross means "drop what I am
      // holding", not "select the axis" (`pickWithDatums`).
      state.selection,
    );
    // An ARMED dimension verb consumes this click instead of selecting with it:
    // the whole point of arming was that "select the line first" was the step
    // the user could not reach. Take the CURVE under the pointer (points are
    // not dimensionable), exactly as trim/extend/offset do.
    const armed = state.dimensionPick;
    if (armed !== null) {
      const entityPick = candidates.find((pick) => pick.kind === "entity");
      if (entityPick === undefined) {
        // Empty space: stay armed and keep asking, rather than silently
        // disarming and leaving the user's next click to mean something else.
        set({ selection: [], selectedConstraint: null });
        return;
      }
      const result = applyConstraintAction(
        armed,
        [entityPick],
        state.entities,
        state.constraints,
      );
      if (result.outcome === "editor") {
        set({
          dimensionEdit: result.target,
          dimensionPick: null,
          selection: [],
          selectedConstraint: null,
          hint: null,
        });
        return;
      }
      // Wrong KIND under the pointer (a circle while Distance is armed): say
      // WHAT was picked and stay armed, so the next click is still a dimension
      // pick — see `wrongPickHint` for why this is not the refusal sentence.
      set({
        selection: [],
        selectedConstraint: null,
        hint: wrongPickHint(
          armed,
          entityPick.id,
          state.entities,
          result.outcome === "hint" ? result.hint : null,
        ),
      });
      return;
    }
    set({
      selection: applyPick(state.selection, candidates, pickMode),
      selectedConstraint: null,
      hint: null,
    });
  },

  togglePick: (pick) =>
    set((state) => ({
      selection: toggleSelection(state.selection, [pick]),
      selectedConstraint: null,
      hint: null,
    })),

  setHoverPick: (hoverPick) => set({ hoverPick }),
  clearSelection: () => set({ selection: [], selectedConstraint: null }),

  applyConstraint: (action) => {
    const { selection, entities, constraints, revision, datumFrameHalfMm } =
      get();
    const frame = datumFrame(datumFrameHalfMm);
    // The verb reasons over the drawn geometry PLUS the frame, so a datum ref
    // resolves before the datum has been materialised into the buffer.
    const result = applyConstraintAction(
      action,
      selection,
      withDatums(entities, frame),
      constraints,
    );
    switch (result.outcome) {
      case "added": {
        // Whatever part of the frame the new constraint reached for now becomes
        // real construction geometry, pinned, so the solver has something to
        // resolve the reference against and the origin cannot be dragged off
        // zero by the constraint that names it. Nothing is added for a
        // constraint that never touches the frame.
        const referenced = result.constraints.flatMap(constraintEntityRefs);
        const grounded = groundDatums(entities, referenced, frame);
        set({
          entities: grounded.entities,
          constraints: [
            ...constraints,
            ...result.constraints,
            ...grounded.constraints,
          ],
          // A constraint verb from the strip or the keyboard.
          userConstrained: true,
          revision: revision + 1,
          selection: [],
          hint: null,
        });
        return;
      }
      case "editor":
        set({ dimensionEdit: result.target, dimensionPick: null, hint: null });
        return;
      case "hint":
        // A DIMENSION verb with nothing usable selected ARMS instead of
        // refusing (see `dimensionPick`). Dropping the draw tool is the
        // load-bearing half: while it is armed, every canvas click is the next
        // shape's first corner, so "select one line" is an instruction the user
        // cannot carry out. The size cells of the shape just drawn go too —
        // they hang over the geometry now being picked.
        // …unless the user aimed AT THE FRAME. Arming would answer "click a
        // line to dimension it" to someone who just told us which line they
        // meant, and would then eat their next click; the refusal names the
        // verbs the frame does accept, so it is guidance, not a dead end.
        if (
          (action === "distance" || action === "radius") &&
          !selectionTouchesDatum(selection)
        ) {
          set({
            dimensionPick: action,
            tool: "select",
            pending: [],
            snapAnchors: [],
            selection: [],
            selectedConstraint: null,
            drawDimension: null,
            drawDimensionFocus: null,
            hint: DIMENSION_PICK_HINT[action],
          });
          return;
        }
        set({ hint: result.hint });
        return;
    }
  },

  toggleConstruction: () => {
    const { selection, entities, revision } = get();
    const next = toggleConstruction(selection, entities);
    if (next === null) {
      set({ hint: "Select an entity to toggle construction." });
      return;
    }
    // Clear the selection so the toggled entities read in their construction
    // ink (selected entities render in brass, which would mask the dash).
    set({ entities: next, revision: revision + 1, selection: [], hint: null });
  },

  requestEdit: (op, target, pick) => {
    const { editBusy, edit } = get();
    if (editBusy) return;
    if (target === null) {
      set({ hint: `Aim at a curve to ${op}.` });
      return;
    }
    set({
      edit: { op, target, pick, nonce: (edit?.nonce ?? 0) + 1 },
      editBusy: true,
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      hint: null,
      editNote: null,
    });
  },

  applyEditResult: (op, entities) => {
    const { edit, constraints, revision } = get();
    if (edit === null) return;
    // Reconcile: the stateless edit rewrote geometry only, so a delete/split
    // can strand constraints on ids that no longer exist. Drop the danglers
    // BEFORE the revision bump re-triggers the solve — an unreconciled trim
    // that leaves a dangling constraint would throw on the next evaluate.
    const { constraints: kept, removed } = reconcileConstraints(
      constraints,
      entities,
    );
    const verb = op === "trim" ? "Trimmed" : "Extended";
    const note =
      removed > 0
        ? `${verb}. ${removed} ${removed === 1 ? "constraint" : "constraints"} removed.`
        : `${verb}.`;
    set({
      entities: [...entities],
      constraints: kept,
      revision: revision + 1,
      edit: null,
      editBusy: false,
      editNote: note,
      hoverPick: null,
    });
  },

  failEdit: (message) => set({ edit: null, editBusy: false, hint: message }),

  beginOffset: (target) => {
    const { editBusy } = get();
    if (editBusy) return;
    if (target === null) {
      set({ hint: "Aim at a curve to offset." });
      return;
    }
    set({
      offsetDraft: { target },
      selection: [],
      hoverPick: null,
      selectedConstraint: null,
      dimensionEdit: null,
      hint: null,
      editNote: null,
    });
  },

  armOffset: (distanceMm) => {
    const { offsetDraft, offset } = get();
    // Guard the sign convention at the store edge too: zero collapses the
    // request to the backend's `sketch_offset_zero_distance` — reject it here.
    if (
      offsetDraft === null ||
      !Number.isFinite(distanceMm) ||
      distanceMm === 0
    ) {
      return;
    }
    set({
      offset: {
        target: offsetDraft.target,
        distance: distanceMm,
        nonce: (offset?.nonce ?? 0) + 1,
      },
      offsetDraft: null,
      editBusy: true,
      hint: null,
      editNote: null,
    });
  },

  cancelOffset: () => set({ offsetDraft: null }),

  applyOffsetResult: (added) => {
    const { offset, entities, revision } = get();
    if (offset === null) return;
    // Offset ADDS: append the new offset entity/entities (fresh backend ids,
    // source unchanged). No constraint reconciliation — nothing was deleted or
    // split, so no existing reference can dangle. The revision bump re-solves.
    const count = added.length;
    set({
      entities: [...entities, ...added],
      revision: revision + 1,
      offset: null,
      editBusy: false,
      editNote:
        count === 1 ? "Offset added." : `Offset added. ${count} entities.`,
      hoverPick: null,
    });
  },

  failOffset: (message) =>
    set({ offset: null, offsetDraft: null, editBusy: false, hint: message }),

  toggleMirrorTarget: (id) => {
    const { mirror } = get();
    if (mirror === null || mirror.phase !== "targets") return;
    if (id === null) {
      set({ hint: "Click an entity to add it to the mirror." });
      return;
    }
    set({
      mirror: {
        phase: "targets",
        targets: toggleMirrorTarget(mirror.targets, id),
      },
      hint: null,
    });
  },

  advanceMirror: () => {
    const { mirror } = get();
    if (mirror === null || mirror.phase !== "targets") return;
    if (mirror.targets.length === 0) {
      set({ hint: "Select at least one entity to mirror." });
      return;
    }
    set({ mirror: { phase: "axis", targets: mirror.targets }, hint: null });
  },

  pickMirrorAxis: (id) => {
    const { mirror, entities, editBusy, mirrorRequest, datumFrameHalfMm } =
      get();
    if (mirror === null || mirror.phase !== "axis" || editBusy) return;
    if (id === null) {
      set({ hint: "Aim at a line to mirror about." });
      return;
    }
    // Resolve the pick against the drawn geometry PLUS the sketch's own frame
    // (MIRROR-1): the origin axes are legal mirror axes, and a datum comes back
    // as a POINTS axis so nothing has to be materialised — see `mirrorAxisFor`.
    const axis = mirrorAxisFor(id, entities, datumFrame(datumFrameHalfMm));
    if (axis === null) {
      // Pre-empt the backend's `sketch_mirror_axis_not_line` with an aim hint —
      // only a line (construction, profile or datum axis) is a valid axis.
      set({
        hint: "The mirror axis must be a line — pick a line or centerline.",
      });
      return;
    }
    set({
      mirrorRequest: {
        targets: mirror.targets,
        axis,
        nonce: (mirrorRequest?.nonce ?? 0) + 1,
      },
      editBusy: true,
      hint: null,
      editNote: null,
    });
  },

  applyMirrorResult: (added) => {
    const { mirrorRequest, entities, revision } = get();
    if (mirrorRequest === null) return;
    // Mirror ADDS: append the reflected copies (fresh backend ids, sources
    // untouched). No constraint reconciliation — nothing was deleted or split,
    // so no existing reference can dangle. Re-arm a fresh targets phase so the
    // user can mirror another group without re-selecting the tool.
    const count = added.length;
    set({
      entities: [...entities, ...added],
      revision: revision + 1,
      mirrorRequest: null,
      mirror: { phase: "targets", targets: [] },
      editBusy: false,
      editNote: count === 1 ? "Mirrored." : `Mirrored. ${count} copies added.`,
      hoverPick: null,
    });
  },

  failMirror: (message) =>
    // Keep the draft in its axis phase so the user can pick a different line.
    set({ mirrorRequest: null, editBusy: false, hint: message }),

  pickCornerLine: (id) => {
    const { corner, entities, editBusy } = get();
    if (corner === null || editBusy) return;
    // Both legs already held → the value editor is open; ignore stray clicks.
    if (corner.picks.length >= 2 && !corner.picks.includes(id ?? "")) return;
    if (id === null) {
      set({ hint: "Click a line to break the corner." });
      return;
    }
    const entity = entities.find((e) => e.id === id);
    if (entity === undefined || entity.kind !== "line") {
      // Pre-empt the backend's `sketch_unsupported_entity`: v1 rounds/bevels the
      // corner between two LINES only.
      set({ hint: "Fillet and chamfer join two lines — pick a line." });
      return;
    }
    set({
      corner: { op: corner.op, picks: toggleCornerPick(corner.picks, id) },
      selection: [],
      hoverPick: null,
      hint: null,
      editNote: null,
    });
  },

  armCorner: (valueMm) => {
    const { corner, cornerRequest } = get();
    if (corner === null || corner.picks.length !== 2) return;
    // Guard the strictly-positive contract at the store edge (the backend's
    // `radius`/`distance` are > 0); a non-positive value never leaves the UI.
    if (!Number.isFinite(valueMm) || !(valueMm > 0)) return;
    const [a, b] = corner.picks;
    if (a === undefined || b === undefined) return;
    set({
      cornerRequest: {
        op: corner.op,
        a,
        b,
        value: valueMm,
        nonce: (cornerRequest?.nonce ?? 0) + 1,
      },
      editBusy: true,
      hint: null,
      editNote: null,
    });
  },

  cancelCorner: () => {
    const { corner } = get();
    if (corner === null) return;
    set({ corner: { op: corner.op, picks: [] }, hint: null });
  },

  applyCornerResult: (result) => {
    const { cornerRequest, corner, constraints, revision } = get();
    if (cornerRequest === null) return;
    // Corner REWRITES (like trim/extend): the two source lines are trimmed in
    // place with ids preserved, so their constraints survive — but reconcile on
    // the uniform, safe path anyway, so a dangling ref can never reach the solve.
    const { constraints: kept, removed } = reconcileConstraints(
      constraints,
      result,
    );
    const verb = cornerRequest.op === "fillet" ? "Filleted" : "Chamfered";
    const note =
      removed > 0
        ? `${verb}. ${removed} ${removed === 1 ? "constraint" : "constraints"} removed.`
        : `${verb}.`;
    set({
      entities: [...result],
      constraints: kept,
      revision: revision + 1,
      cornerRequest: null,
      editBusy: false,
      editNote: note,
      hoverPick: null,
      // Re-arm a fresh corner draft so the user can break another corner without
      // reselecting the tool (mirror does the same after a copy).
      corner: corner !== null ? { op: cornerRequest.op, picks: [] } : null,
    });
  },

  failCorner: (message) =>
    // Keep the picks (the editor stays open) so a too-large radius can be retyped
    // smaller without re-picking the corner.
    set({ cornerRequest: null, editBusy: false, hint: message }),

  editDimension: (constraintIndex) => {
    const constraint = get().constraints[constraintIndex];
    if (constraint?.kind !== "distance" && constraint?.kind !== "radius") {
      return;
    }
    set({
      dimensionEdit: {
        kind: constraint.kind,
        entity: constraint.entity,
        initialMm: constraint.value_mm,
        initialExpression: constraint.expression ?? null,
        initialName: constraint.name ?? null,
        initialDriving: constraint.driving !== false,
        constraintIndex,
      },
      selectedConstraint: null,
      hint: null,
    });
  },

  commitDimension: (commit) => {
    const { dimensionEdit, constraints, revision } = get();
    if (dimensionEdit === null || !(commit.valueMm > 0)) return;
    // Fully specify every additive field (null = default/unset) so an edit that
    // clears a name/expression, or flips driving↔driven, replaces cleanly —
    // `driving: null` means driving (the wire default), `false` means driven; an
    // expression only rides a DRIVING dim (a driven dim is measured, not fed).
    const constraint: SketchConstraint = {
      kind: dimensionEdit.kind,
      entity: dimensionEdit.entity,
      value_mm: commit.valueMm,
      expression: commit.driving ? commit.expression : null,
      name: commit.name,
      driving: commit.driving ? null : false,
    };
    const next =
      dimensionEdit.constraintIndex === null
        ? [...constraints, constraint]
        : constraints.map((c, i) =>
            i === dimensionEdit.constraintIndex ? constraint : c,
          );
    set({
      constraints: next,
      // A dimension typed into the inline editor.
      userConstrained: true,
      revision: revision + 1,
      dimensionEdit: null,
      selection: [],
      hint: null,
    });
  },

  cancelDimension: () => set({ dimensionEdit: null }),

  selectConstraint: (selectedConstraint) =>
    set({ selectedConstraint, selection: [], hint: null }),

  removeConstraint: (index) => {
    const { constraints, revision, selectedConstraint } = get();
    if (index < 0 || index >= constraints.length) return;
    set({
      constraints: constraints.filter((_, i) => i !== index),
      revision: revision + 1,
      selectedConstraint:
        selectedConstraint === index
          ? null
          : selectedConstraint !== null && selectedConstraint > index
            ? selectedConstraint - 1
            : selectedConstraint,
      dimensionEdit: null,
    });
  },

  undo: () => {
    const state = get();
    const previous = state.past[state.past.length - 1];
    // A trim/offset/mirror/corner in flight will land on the CURRENT entity set
    // when it returns; rewinding underneath it would apply its result to a
    // sketch it never saw. The button holds for the same reason.
    if (previous === undefined || state.editBusy) return;
    set({
      ...previous,
      past: state.past.slice(0, -1),
      future: [...state.future, snapshotOf(state)],
      // A restored sketch is a change like any other: bump so it saves and
      // re-solves. Undo is not a local rewind the server never hears about.
      revision: state.revision + 1,
      ...CLEARED_BY_HISTORY,
      // Multi-phase tools stay armed but drop picks, which may name entities
      // the restored state no longer holds — the same rung their own Escape
      // cascade stops at.
      mirror: state.mirror === null ? null : { phase: "targets", targets: [] },
      corner: state.corner === null ? null : { op: state.corner.op, picks: [] },
    });
  },

  redo: () => {
    const state = get();
    const next = state.future[state.future.length - 1];
    if (next === undefined || state.editBusy) return;
    set({
      ...next,
      past: [...state.past, snapshotOf(state)],
      future: state.future.slice(0, -1),
      revision: state.revision + 1,
      ...CLEARED_BY_HISTORY,
      mirror: state.mirror === null ? null : { phase: "targets", targets: [] },
      corner: state.corner === null ? null : { op: state.corner.op, picks: [] },
    });
  },

  bind: (featureId) => set({ featureId }),

  adoptSolved: (entities, solve, dimensions) => {
    const dims =
      dimensions === undefined ? {} : { solvedDimensions: [...dimensions] };
    // THE seam where the solve report becomes something the user is shown.
    // Sanitised once, here, rather than at each of the three readers (the DRO
    // cell, the diagnostic banner, the flagged-glyph set) — one filter cannot
    // disagree with itself, and a fourth reader gets it for free. The buffer is
    // clean whenever this runs (PartPage adopts only then), so these indices
    // and `state.constraints` describe the same sketch.
    const safe = (state: SketchState): SolveInfo | null =>
      solve === null ? null : datumSafeSolve(solve, state.constraints);
    if (entities === null) {
      set((state) => ({ solve: safe(state), ...dims }));
      return;
    }
    const solvedById = new Map(entities.map((e) => [e.id, e]));
    set((state) => ({
      solve: safe(state),
      ...dims,
      entities: state.entities.map((e) => solvedById.get(e.id) ?? e),
    }));
  },

  escape: () => {
    // The draw-time size cells are PART of the placement gesture, not a level
    // above it (FB-13's one-rung-at-a-time rule is about levels the user built
    // up deliberately). Fusion's rectangle behaves the same way: one Escape
    // ends the command and the cells go with it, leaving the shape drawn and
    // undimensioned. Escape *inside* a cell is the field's own — it abandons
    // the typing and hands the canvas back with the tool still armed (handled
    // in the scene, which stops that key from ever reaching here).
    if (get().drawDimension !== null) {
      set({ drawDimension: null, drawDimensionFocus: null });
    }
    const {
      mode,
      tool,
      pending,
      selection,
      selectedConstraint,
      entities,
      constraints,
      featureId,
      dimensionEdit,
      dimensionPick,
      offsetDraft,
      mirror,
      corner,
    } = get();
    // An ARMED dimension verb is the most local rung there is — it owns the
    // next click, so it must be what the next Escape gives back. Without this
    // the cascade would fall through to "nothing to lose" and exit the sketch.
    if (dimensionPick !== null && dimensionEdit === null) {
      set({ dimensionPick: null, hint: null });
      return;
    }
    // Corner's own cascade, most-local first: an open editor / any picks →
    // clear the picks (close the editor); empty picks → drop the tool.
    if (corner !== null) {
      if (corner.picks.length > 0) {
        set({ corner: { op: corner.op, picks: [] }, hint: null });
        return;
      }
      set({ tool: "select", corner: null, hint: null });
      return;
    }
    // Mirror's own cascade, most-local first: axis phase → back to targets;
    // targets with picks → clear the picks; empty targets → drop the tool.
    if (mirror !== null) {
      if (mirror.phase === "axis") {
        set({
          mirror: { phase: "targets", targets: mirror.targets },
          hint: null,
        });
        return;
      }
      if (mirror.targets.length > 0) {
        set({ mirror: { phase: "targets", targets: [] }, hint: null });
        return;
      }
      set({ tool: "select", mirror: null, hint: null });
      return;
    }
    // A selected constraint glyph counts as a selection: without it the cascade
    // skipped a rung it was holding, and (before FB-13) fell straight through
    // to exit — so Escape with a glyph picked wiped the session.
    const hasSelection = selection.length > 0 || selectedConstraint !== null;
    // Nothing to lose: the plane-pick step, or a draw session that holds no
    // entities and no constraints. Only there does Escape leave the sketch.
    const unstarted =
      mode === "plane" || (entities.length === 0 && constraints.length === 0);
    switch (
      escapeAction(
        tool,
        pending.length,
        hasSelection,
        dimensionEdit !== null || offsetDraft !== null,
        unstarted,
      )
    ) {
      case "close-editor":
        set({ dimensionEdit: null, offsetDraft: null });
        return;
      case "cancel-placement":
        set({ pending: [], snapAnchors: [] });
        return;
      case "reset-tool":
        set({ tool: "select", pending: [], snapAnchors: [] });
        return;
      case "clear-selection":
        set({ selection: [], selectedConstraint: null, hint: null });
        return;
      case "exit":
        set(freshSession(get()));
        return;
      case "none":
        // Never silent (the FB-12 lesson: a gesture that does nothing at all
        // reads as a broken app) and never a dead end — name the chip that
        // does end the sketch, by the label it is wearing.
        set({
          hint:
            featureId === null
              ? "Nothing to cancel — Save sketch keeps this work, Exit discards it."
              : "Nothing to cancel — Finish sketch closes it; edits are saved.",
        });
        return;
    }
  },

  exit: () => set(freshSession(get())),
});

export const useSketchStore = create<SketchState>()(
  // Inner to outer: actions → the armed-prompt invariant → the history
  // recorder. The invariant's own repair is a hint-only write, so it bumps no
  // revision and can never become an undo step.
  withSketchHistory(withArmedPrompt(createSketchState)),
);
